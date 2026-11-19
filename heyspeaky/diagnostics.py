"""A problem report someone can send you.

When HeySpeaky works well on one PC and badly on another, the difference is
nearly always one of a few things: it is not really using OpenAI, the
microphone gives it poor audio, or a busy CPU drops pieces of the recording.
The report puts what tells those apart into one ZIP on the Desktop, small
enough to send over a chat app.

The last few recordings are kept in memory only, and written out only when
someone asks for a report.
"""

import collections
import copy
import ctypes
import json
import math
import os
import platform
import re
import socket
import sys
import threading
import time
import zipfile
from pathlib import Path

import numpy as np

from .transcribe import LEGACY_KEY_FILES, pcm_to_wav

KEEP = 5

_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{20,}")

_WHAT_TO_LOOK_FOR = """\
What to look for
  - "local" where you expected OpenAI: it is not using OpenAI, and the
    reason is in brackets. Check "OpenAI key" and "OpenAI reachable" above.
  - "captured" much shorter than "held": part of the recording was lost,
    usually to a busy CPU or a bad microphone driver.
  - "average" below about -45 dB: the microphone is very quiet. Raise its
    level in Windows sound settings, or speak closer.
  - "clipped" above 1%: too loud, and the audio is distorted.
  - To hear what the microphone picked up, play the wav files, or run them
    through HeySpeaky on your own PC:
      .venv\\Scripts\\python.exe tools\\try_demo.py path\\to\\1.wav --both
    Bad on your PC too means the audio is the problem. Fine on your PC means
    the other PC's setup is.
"""


def redact(text):
    """Removes anything that looks like an OpenAI key."""
    return _KEY_PATTERN.sub("sk-...removed", text)


def _db(value):
    return 20.0 * math.log10(value) if value > 1e-6 else -120.0


def audio_stats(pcm, rate):
    """Length, loudness and clipping of a PCM16 recording."""
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.int32)
    if samples.size == 0:
        return {"seconds": 0.0, "peak_db": -120.0, "rms_db": -120.0,
                "clipped_pct": 0.0}
    floats = samples / 32768.0
    return {
        "seconds": samples.size / float(rate),
        "peak_db": _db(float(np.max(np.abs(floats)))),
        "rms_db": _db(float(np.sqrt(np.mean(floats * floats)))),
        "clipped_pct": float(np.mean(np.abs(samples) >= 32767)) * 100.0,
    }


class Recent:
    """The last few dictations, oldest first. Memory only."""

    def __init__(self, keep=KEEP):
        self._items = collections.deque(maxlen=keep)
        self._lock = threading.Lock()

    def add(self, entry):
        with self._lock:
            self._items.append(entry)

    def items(self):
        with self._lock:
            return list(self._items)


# -- facts about this PC ---------------------------------------------------


def desktop_dir():
    """The real Desktop folder, wherever OneDrive has moved it."""
    try:
        buffer = ctypes.create_unicode_buffer(260)
        # CSIDL_DESKTOPDIRECTORY
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0,
                                                  buffer) == 0 and buffer.value:
            return Path(buffer.value)
    except Exception:
        pass
    return None


def _cpu_name():
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        ) as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    except Exception:
        return platform.processor() or "unknown"


def _memory_gb():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return "{:.1f} GB, {:.1f} GB free".format(
                status.ullTotalPhys / 2**30, status.ullAvailPhys / 2**30)
    except Exception:
        pass
    return "unknown"


def device_label(name):
    """A device name on one line. Bluetooth drivers put line breaks in them."""
    return " ".join(str(name).split()) or "?"


def _microphones():
    """The default input device and every device that can record."""
    try:
        import pyaudio
    except Exception as exc:
        return "unknown ({})".format(exc), []
    pa = pyaudio.PyAudio()
    try:
        try:
            info = pa.get_default_input_device_info()
            default = "{} (index {}, native {:.0f} Hz)".format(
                device_label(info.get("name", "?")), info.get("index", "?"),
                float(info.get("defaultSampleRate", 0)))
        except Exception as exc:
            default = "none ({})".format(exc)
        inputs = []
        for index in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(index)
            if int(info.get("maxInputChannels", 0)) > 0:
                inputs.append("{}: {}".format(
                    index, device_label(info.get("name", "?"))))
        return default, inputs
    finally:
        pa.terminate()


def _spent(cfg):
    """The month's OpenAI tally, or why it is not known."""
    try:
        from . import usage

        figures = usage.summary(cfg)
        return "{:.0f} min over {} dictations, about ${:.2f} (estimate)".format(
            figures["minutes"], figures["dictations"], figures["cost"])
    except Exception as exc:
        return "not known ({})".format(str(exc)[:40])


def key_source(cfg):
    """Where the OpenAI key comes from. Never the key itself."""
    cloud = cfg["transcription"]["cloud"]
    if (cloud.get("api_key") or "").strip():
        return "found, in config.json"
    if (os.environ.get(cloud.get("api_key_env") or "") or "").strip():
        return "found, in the {} variable".format(cloud["api_key_env"])
    for candidate in (cloud.get("api_key_file") or "",) + LEGACY_KEY_FILES:
        if not candidate:
            continue
        path = Path(os.path.expandvars(os.path.expanduser(candidate)))
        try:
            if path.is_file() and path.read_text(encoding="utf-8-sig").strip():
                return "found, in {}".format(path)
        except OSError:
            continue
    return "NOT FOUND"


def _openai_reachable():
    """How long a plain connection to OpenAI takes. Sends nothing."""
    started = time.monotonic()
    try:
        with socket.create_connection(("api.openai.com", 443), timeout=5):
            return "connected in {:.2f}s".format(time.monotonic() - started)
    except OSError as exc:
        return "NO ({})".format(exc)


def _local_hardware(cfg):
    try:
        from .hardware import resolve_hardware

        device, compute = resolve_hardware(cfg["model"]["device"],
                                           cfg["model"]["compute_type"])
        return "{} on {}/{}".format(cfg["model"]["final"], device, compute)
    except Exception as exc:
        return "unknown ({})".format(exc)


# -- the report ------------------------------------------------------------


def _describe(index, entry):
    stats = entry["stats"]
    if entry["backend"] == "cloud":
        engine = "OpenAI"
    elif entry["backend"] == "local":
        engine = "local ({})".format(entry["fallback"]) if entry["fallback"] \
            else "local"
    else:
        engine = "{} ({})".format(entry["backend"], entry["fallback"])
    return (
        "  {n}. {time}  held {held:.1f}s, captured {cap:.1f}s  "
        "peak {peak:.0f} dB  average {rms:.0f} dB  clipped {clip:.1f}%\n"
        "     speech run {run}  language {lang}  {engine} in {took:.1f}s\n"
        "     {text}\n"
    ).format(
        n=index, time=entry["time"], held=entry["held"],
        cap=stats["seconds"], peak=stats["peak_db"], rms=stats["rms_db"],
        clip=stats["clipped_pct"], run=entry["speech_run"],
        lang=entry["language"] or "auto", engine=engine, took=entry["took"],
        text=json.dumps(entry["text"], ensure_ascii=False),
    )


def report_text(cfg, entries, check_network=True):
    """The human-readable part of the report."""
    cloud = cfg["transcription"]["cloud"]
    backend = cfg["transcription"]["backend"]
    default_mic, inputs = _microphones()
    lines = [
        "HeySpeaky problem report",
        "Made {}".format(time.strftime("%Y-%m-%d %H:%M")),
        "",
        "This PC",
        "  Windows          {}".format(platform.platform()),
        "  CPU              {} ({} threads)".format(_cpu_name(), os.cpu_count()),
        "  Memory           {}".format(_memory_gb()),
        "  Python           {}".format(sys.version.split()[0]),
        "  Local model      {}".format(_local_hardware(cfg)),
        "",
        "Microphone",
        "  Default          {}".format(default_mic),
        "  Chosen           {}".format(
            "system default" if cfg["audio"]["input_device_index"] is None
            else "index {}".format(cfg["audio"]["input_device_index"])),
    ]
    lines += ["  Input            {}".format(name) for name in inputs]
    lines += [
        "",
        "Settings",
        "  Transcribed by   {}".format(
            "OpenAI" if backend == "cloud" else "this computer"),
        "  Languages        {}".format(", ".join(cloud.get("languages") or [])),
        "  Pinned language  {}".format(cfg["model"]["language"] or "auto"),
        "  Split at pauses  {}".format(
            "on" if cfg["transcription"].get("per_segment_language") else "off"),
        "  OpenAI key       {}".format(key_source(cfg)),
        "  Spent this month {}".format(_spent(cfg)),
        "  OpenAI reachable {}".format(
            _openai_reachable() if check_network else "not checked"),
        "",
    ]
    if entries:
        lines.append("Last {} dictations, oldest first".format(len(entries)))
        text = "\n".join(lines) + "\n"
        for index, entry in enumerate(entries, 1):
            text += _describe(index, entry)
    else:
        lines.append("No dictations since HeySpeaky started. Dictate a few "
                     "sentences, then save the report again.")
        text = "\n".join(lines) + "\n"
    return redact(text + "\n" + _WHAT_TO_LOOK_FOR)


def save_report(cfg, entries, log_dir, out_dir=None, check_network=True):
    """Writes the ZIP and returns its path."""
    out_dir = Path(out_dir) if out_dir else (desktop_dir() or Path(log_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "HeySpeaky-report-{}.zip".format(
        time.strftime("%Y%m%d-%H%M%S"))

    safe_cfg = copy.deepcopy(cfg)
    safe_cfg["transcription"]["cloud"]["api_key"] = ""

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.txt",
                         report_text(cfg, entries, check_network))
        archive.writestr("config.json", redact(
            json.dumps(safe_cfg, indent=2, ensure_ascii=False)))
        log_dir = Path(log_dir)
        if log_dir.is_dir():
            for log in sorted(log_dir.iterdir()):
                if log.is_file() and (log.name.startswith("heyspeaky.log")
                                      or log.name == "stdout.log"):
                    try:
                        content = log.read_text(encoding="utf-8",
                                                errors="replace")
                    except OSError:
                        continue
                    archive.writestr("logs/" + log.name, redact(content))
        for index, entry in enumerate(entries, 1):
            archive.writestr("recordings/{}.wav".format(index),
                             pcm_to_wav(entry["pcm"], entry["rate"]))
    return path
