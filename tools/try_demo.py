r"""Runs the bundled demo clip and prints what came back.

The README claims HeySpeaky handles a sentence that changes language three
times without being told. This is how you check that yourself in about five
seconds, without installing anything extra or recording anything.

    .venv\Scripts\python.exe tools\try_demo.py

By default it uses whichever backend config.json is set to. You can force one,
or run both to see the difference for yourself:

    tools\try_demo.py --cloud
    tools\try_demo.py --local
    tools\try_demo.py --both

Point it at your own recording instead, if you have a wav lying around. Any
sample rate, mono or stereo, 16-bit:

    tools\try_demo.py path\to\your.wav

--sweep runs the same clip under a range of language lists, from none up to
everything in your config, so you can see for yourself whether the `languages`
field is earning its keep on your voice:

    tools\try_demo.py my_recording.wav --sweep
"""

import argparse
import logging
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from heyspeaky import config as config_module          # noqa: E402
from heyspeaky.transcribe import CloudBackend, LocalBackend  # noqa: E402

DEMO = ROOT / "demo" / "four_languages.wav"

EXPECTED = ("I already sent the invoice, "
            "aber ich warte noch auf eine Antwort, "
            "но клиент до сих пор не ответил, "
            "сондықтан ертең қоңырау шаламын.")

MODEL_LOAD_TIMEOUT = 180.0


def read_pcm(path, rate):
    """Reads a wav as the 16 kHz mono PCM16 the backends expect."""
    import numpy as np

    with wave.open(str(path), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
        source_rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
    if width != 2:
        raise SystemExit("{} is not 16-bit. Convert it first.".format(path))
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels)[:, 0]
    if source_rate != rate:
        # Linear interpolation rather than scipy, which is a dev-only
        # dependency. Most recordings are 44.1 or 48 kHz and this tool is the
        # first thing a new person runs, so it must not need extra installs.
        count = int(len(audio) * rate / source_rate)
        audio = np.interp(
            np.linspace(0.0, len(audio) - 1, count),
            np.arange(len(audio)),
            audio,
        ).astype(np.float32)
    seconds = len(audio) / float(rate)
    return (np.clip(audio, -1, 1) * 32767).astype("int16").tobytes(), seconds


def run_cloud(cfg, pcm):
    backend = CloudBackend(cfg)
    if not backend.available():
        return None, ("no API key. Set {} and open a new terminal.".format(
            cfg["transcription"]["cloud"]["api_key_env"]))
    started = time.monotonic()
    try:
        return (backend.transcribe(pcm, ""), time.monotonic() - started), None
    except Exception as exc:
        return None, str(exc)[:160]


def run_local(cfg, pcm):
    """Starts the real engine headlessly. It reads no microphone."""
    from heyspeaky.engine import TranscriptionEngine

    engine = TranscriptionEngine(
        cfg,
        on_ready=lambda: None,
        on_error=lambda exc: None,
        on_auto_stop=lambda: None,
    )
    print("   loading the local model, this takes a while the first time ...")
    engine.start()
    deadline = time.monotonic() + MODEL_LOAD_TIMEOUT
    while not engine.ready and time.monotonic() < deadline:
        time.sleep(0.2)
    if not engine.ready:
        engine.shutdown()
        return None, "the model did not load within {:.0f}s".format(
            MODEL_LOAD_TIMEOUT)
    started = time.monotonic()
    try:
        text = LocalBackend(engine, cfg).transcribe(pcm, "")
        return (text, time.monotonic() - started), None
    except Exception as exc:
        return None, str(exc)[:160]
    finally:
        # RealtimeSTT 1.1.2 logs a traceback closing the model, because
        # FasterWhisperEngine has no close(). It is harmless and we already
        # have the text, but it looks alarming in a tool meant to reassure.
        logging.getLogger("realtimestt").setLevel(logging.CRITICAL)
        engine.shutdown()


def sweep(cfg, pcm, runs):
    """Runs the same clip under several language lists and prints a table.

    The point is to answer, for your own voice, whether the `languages` field
    is doing anything. It is a hosted model that changes under us, so a
    measurement from last month is not evidence about today, and synthesised
    speech is too clean to tell the difference either way.
    """
    import copy

    configured = list(cfg["transcription"]["cloud"]["languages"])
    lists = [("(none)", [])]
    for size in range(1, len(configured) + 1):
        lists.append((",".join(configured[:size]), configured[:size]))

    print("\nSweeping {} language lists, {} runs each.".format(
        len(lists), runs))
    print("Watch whether the shorter lists lose a language.\n")

    for label, langs in lists:
        trial = copy.deepcopy(cfg)
        trial["transcription"]["cloud"]["languages"] = langs
        backend = CloudBackend(trial)
        print("languages {}".format(label))
        for _ in range(runs):
            try:
                print("   {}".format(backend.transcribe(pcm, "")))
            except Exception as exc:
                print("   failed: {}".format(str(exc)[:90]))
            time.sleep(0.4)
        print("")


def report(label, result, error):
    if error:
        print("\n{:<7} skipped: {}".format(label, error))
        return
    text, seconds = result
    print("\n{:<7} {:.1f}s".format(label, seconds))
    print("        {}".format(text))


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe the demo clip and print the result.")
    parser.add_argument("wav", nargs="?", default=None,
                        help="a wav of your own (default: the bundled demo)")
    parser.add_argument("--cloud", action="store_true", help="force OpenAI")
    parser.add_argument("--local", action="store_true", help="force local")
    parser.add_argument("--both", action="store_true", help="run both")
    parser.add_argument("--sweep", action="store_true",
                        help="try the same clip under several language lists")
    parser.add_argument("--runs", type=int, default=3,
                        help="repeats per list when sweeping (default 3)")
    args = parser.parse_args()

    path = Path(args.wav) if args.wav else DEMO
    if not path.exists():
        raise SystemExit("no such file: {}".format(path))

    cfg = config_module.load()
    rate = int(cfg["audio"]["sample_rate"])
    pcm, seconds = read_pcm(path, rate)

    print("clip      : {}  ({:.1f}s)".format(path.name, seconds))
    print("languages : {}".format(cfg["transcription"]["cloud"]["languages"]))
    if path == DEMO:
        print("spoken    : {}".format(EXPECTED))
    print("-" * 70)

    if args.sweep:
        if not CloudBackend(cfg).available():
            raise SystemExit("--sweep needs an API key.")
        sweep(cfg, pcm, args.runs)
        return 0

    want_cloud = args.cloud or args.both
    want_local = args.local or args.both
    if not (want_cloud or want_local):
        # Whatever the tray is set to, which is what the app would do.
        want_cloud = cfg["transcription"]["backend"] == "cloud"
        want_local = not want_cloud

    if want_cloud:
        result, error = run_cloud(cfg, pcm)
        report("cloud", result, error)
    if want_local:
        result, error = run_local(cfg, pcm)
        report("local", result, error)

    print("\n" + "-" * 70)
    print("How this clip was made, and why it is not quite a fair test:")
    print("   demo/README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
