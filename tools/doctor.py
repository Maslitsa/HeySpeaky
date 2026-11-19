r"""Checks a HeySpeaky installation and says what to fix.

Run this first whenever something is wrong. It is the front door; the deeper
tools (check_mic.py, check_cloud.py) are for when it points you at one.

    .venv\Scripts\python.exe tools\doctor.py

Or just double-click CHECKUP.bat.

The installer runs it with --install, which skips the checks that only make
sense once the app is running. Instead it downloads the speech models and
starts the real transcription engine, then waits for it to be ready. When the
installer is about to start HeySpeaky anyway, it adds --no-engine and watches
the app's own engine start instead, so the model is not loaded twice. HeySpeaky
has no console, so an engine that cannot start at first launch fails where
nobody can see it. The installer's window is the last place an error is still
readable.
"""

import ctypes
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Windows consoles are often not UTF-8 (cp1251 here), and a UnicodeEncodeError
# while reporting a problem is a poor way to report a problem.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OK, WARN, FAIL = "[ ok ]", "[warn]", "[FAIL]"

VC_REDIST = "https://aka.ms/vs/17/release/vc_redist.x64.exe"

# The first start on a slow laptop loads two models and a VAD, and retries
# offline if the network check fails. Measured at well under a minute.
ENGINE_TIMEOUT = 240

problems = []
warnings = []


def say(mark, label, detail="", fix=""):
    print("{} {:<26} {}".format(mark, label, detail))
    if fix:
        print("       -> {}".format(fix))
    if mark == FAIL:
        problems.append(label)
    elif mark == WARN:
        warnings.append(label)


def check_python():
    major, minor = sys.version_info[:2]
    version = "{}.{}.{}".format(major, minor, sys.version_info[2])
    if (major, minor) in ((3, 11), (3, 12)):
        say(OK, "Python version", version)
    else:
        say(FAIL, "Python version", version + " (need 3.11 or 3.12)",
            "RealtimeSTT does not support this version. Reinstall with "
            "INSTALL.bat, which picks a supported one.")


def check_venv():
    inside = Path(sys.executable).resolve()
    expected = (ROOT / ".venv").resolve()
    if expected in inside.parents:
        say(OK, "Environment", "using .venv")
    else:
        say(WARN, "Environment", "running from {}".format(inside.parent),
            "Not the project's .venv. Fine if deliberate.")


def check_imports():
    failed = []
    for name, package in [
        ("RealtimeSTT", "RealtimeSTT"), ("faster_whisper", "faster-whisper"),
        ("silero_vad", "silero-vad"), ("ctranslate2", "ctranslate2"),
        ("torch", "torch"), ("numpy", "numpy"), ("pyaudio", "PyAudio"),
        ("webrtcvad", "webrtcvad-wheels"), ("keyboard", "keyboard"),
        ("pystray", "pystray"), ("PIL", "pillow"), ("httpx", "httpx"),
        ("tkinter", "tkinter"),
    ]:
        try:
            __import__(name)
        except Exception as exc:
            reason = (str(exc).splitlines() or [""])[0]
            failed.append((package, "{}: {}".format(
                type(exc).__name__, reason[:90])))
    if not failed:
        say(OK, "Dependencies", "all present")
        return
    say(FAIL, "Dependencies", "{} failed to import".format(len(failed)),
        "Run the installer again. If it fails the same way, open an issue "
        "with this output.")
    for package, reason in failed:
        print("         {:<17} {}".format(package, reason))
    # "DLL load failed" on a fresh Windows is nearly always the missing
    # Visual C++ runtime that torch and ctranslate2 are built against.
    if any("DLL" in reason for _, reason in failed):
        print("       -> A DLL failed to load. Install the Visual C++ "
              "Redistributable and try again:\n          " + VC_REDIST)


def check_config():
    try:
        from heyspeaky import config as config_module
        cfg = config_module.load()
    except Exception as exc:
        say(FAIL, "config.json", str(exc)[:60],
            "Delete config.json; it is rewritten from defaults on next start.")
        return None
    backend = cfg["transcription"]["backend"]
    pinned = cfg["model"]["language"] or "auto-detect"
    say(OK, "Settings", "backend={}  language={}".format(backend, pinned))

    # Worth surfacing: a GPU makes local transcription several times faster,
    # and "auto" silently landing on cpu is the difference between a bigger
    # model being usable and being unusable.
    try:
        from heyspeaky.hardware import resolve_hardware
        device, compute = resolve_hardware(
            cfg["model"]["device"], cfg["model"]["compute_type"])
        detail = "{} / {} (model {})".format(
            device, compute, cfg["model"]["final"])
        if device == "cpu":
            say(OK, "Local model runs on", detail,
                "No CUDA GPU found. That is fine, just slower.")
        else:
            say(OK, "Local model runs on", detail)
    except Exception as exc:
        say(WARN, "Local model runs on", "could not tell: {}".format(
            str(exc)[:40]))
    return cfg


def download_models(cfg):
    """Fetches the models with visible progress, before the engine needs them.

    Returns False only when a download failed, which is worth a warning rather
    than a failure: HeySpeaky retries at startup, and a firewall that blocks
    Hugging Face today may not tomorrow.
    """
    try:
        from faster_whisper import download_model
    except Exception as exc:
        say(FAIL, "Speech models", "faster-whisper will not import: {}".format(
            str(exc)[:40]), "Run the installer again.")
        return False
    names = [cfg["model"]["final"]]
    for name in names:
        print("       downloading {} ...".format(name), flush=True)
        try:
            download_model(name, cache_dir=cfg["model"].get("download_root"))
        except Exception as exc:
            say(WARN, "Speech models", "could not download {}: {}".format(
                name, str(exc)[:50]),
                "HeySpeaky tries again when it starts. huggingface.co has to "
                "be reachable once.")
            return False
    say(OK, "Speech models", ", ".join(names) + " downloaded")
    return True


def check_engine(cfg):
    """Starts the real engine, the way the app does, and waits for it.

    Loading a Whisper model on its own proves too little. RealtimeSTT also
    builds a Silero voice activity detector, and on 1.1.2 that needs a package
    a model load never touches. A fresh install once passed every other check
    here and still could not dictate.
    """
    import logging
    import threading

    try:
        from heyspeaky import winjob
        from heyspeaky.engine import TranscriptionEngine
    except Exception as exc:
        say(FAIL, "Engine", "will not import: {}".format(str(exc)[:50]),
            "Run the installer again.")
        return

    # The engine spawns a worker process. If this check is interrupted, the
    # job object takes the worker down with it instead of orphaning it.
    winjob.join_kill_on_close()

    errors = []
    settled = threading.Event()

    def on_error(*args):
        errors.append(" ".join(str(a) for a in args))
        settled.set()

    engine = TranscriptionEngine(
        cfg,
        on_ready=lambda *args: settled.set(),
        on_error=on_error,
        on_auto_stop=lambda *args: None,
    )
    print("       starting the engine ...", flush=True)
    engine.start()
    settled.wait(ENGINE_TIMEOUT)
    try:
        if engine.ready:
            say(OK, "Engine", "started and ready to dictate")
        elif errors:
            say(FAIL, "Engine", "failed to start",
                "Open an issue with this output.")
            print("         " + errors[0][:400])
        else:
            say(FAIL, "Engine", "not ready after {}s".format(ENGINE_TIMEOUT),
                "Open an issue with this output.")
    finally:
        # RealtimeSTT 1.1.2 logs a traceback while closing its model, because
        # FasterWhisperEngine has no close(). Harmless, and alarming here.
        logging.getLogger("realtimestt").setLevel(logging.CRITICAL)
        engine.shutdown()


def check_microphone(cfg):
    try:
        from heyspeaky.mic import list_input_devices
        devices = list(list_input_devices())
    except Exception as exc:
        say(FAIL, "Microphone", "cannot list devices: {}".format(
            str(exc)[:50]))
        return
    if not devices:
        say(FAIL, "Microphone", "no input devices found",
            "Check Settings > System > Sound > Input.")
        return
    chosen = cfg["audio"]["input_device_index"] if cfg else None
    label = "system default" if chosen is None else "device {}".format(chosen)
    say(OK, "Microphone", "{} device(s), using {}".format(
        len(devices), label),
        "Run tools/check_mic.py while speaking to test the level.")


def check_api_key(cfg):
    if cfg is None:
        return
    try:
        from heyspeaky.transcribe import CloudBackend
        backend = CloudBackend(cfg)
        has_key = backend.available()
    except Exception as exc:
        say(WARN, "OpenAI key", "could not check: {}".format(str(exc)[:50]))
        return
    wants_cloud = cfg["transcription"]["backend"] == "cloud"
    if has_key:
        say(OK, "OpenAI key", "found")
    elif wants_cloud:
        say(FAIL, "OpenAI key", "missing, but backend is set to cloud",
            "Run the install command with your key in it (see the README), "
            "or switch to local in the tray.")
    else:
        say(OK, "OpenAI key", "not set (local backend, so not needed)")


def check_running():
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenMutexW.restype = ctypes.c_void_p
        handle = kernel32.OpenMutexW(
            0x00100000, False, "Global\\HeySpeaky.SingleInstance")
    except Exception:
        say(WARN, "Running", "could not tell")
        return
    if handle:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        say(OK, "Running", "yes")
    else:
        # The instance mutex is claimed a moment after launch, so running this
        # immediately after starting HeySpeaky can catch the gap.
        say(WARN, "Running", "not running (or still starting)",
            "If you just started it, wait a few seconds and run this again. "
            "Otherwise start it from the Start Menu.")


def check_autostart():
    startup = Path(os.environ.get("APPDATA", "")) / (
        r"Microsoft\Windows\Start Menu\Programs\Startup\HeySpeaky.lnk")
    if startup.exists():
        say(OK, "Starts with Windows", "yes")
    else:
        say(WARN, "Starts with Windows", "no shortcut",
            "Run INSTALL.bat to add it.")


def check_logs():
    stdout_log = ROOT / "logs" / "stdout.log"
    if stdout_log.exists():
        size = stdout_log.stat().st_size
        if size > 5_000_000:
            say(WARN, "Logs", "stdout.log is {:.0f} MB".format(size / 1e6),
                "Unexpected. Please open an issue with the last lines.")
            return
    say(OK, "Logs", "normal size")


def main():
    install = "--install" in sys.argv[1:]
    no_engine = "--no-engine" in sys.argv[1:]
    print()
    print("HeySpeaky check-up")
    print("=" * 62)
    check_python()
    check_venv()
    check_imports()
    cfg = check_config()
    if install:
        # Only worth starting the engine if everything it needs imported.
        if cfg is not None and not problems:
            download_models(cfg)
            if not no_engine:
                check_engine(cfg)
    else:
        check_microphone(cfg)
        check_api_key(cfg)
        check_running()
        check_autostart()
        check_logs()
    print("=" * 62)

    if problems:
        print("\n{} problem(s) to fix: {}".format(
            len(problems), ", ".join(problems)))
        print("Each one has a '->' line above telling you what to do.")
        return 1
    if warnings:
        print("\nEverything needed works. {} note(s): {}".format(
            len(warnings), ", ".join(warnings)))
        return 0
    print("\nAll good. Hold Ctrl+Alt and talk.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
