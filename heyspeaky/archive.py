"""Every dictation kept on this computer, for its owner to look back on.

A problem report holds the last five recordings, and only once somebody
thinks to save one. That is enough to show a fault, not to see how a whole
day of dictation went: which came out right, which came out wrong, and
what each step of the way made of it. On 26 November 2026 the owner asked
for that, for his own PC and nobody else's, so this is off unless
config.json says

    "archive": {"enabled": true}

Where: %LOCALAPPDATA%\\HeySpeaky\\archive\\<date>\\. That is outside the
project, so it cannot be committed. It is outside OneDrive, which on his PC
holds the Desktop and Documents and would send the recordings to the
cloud. And it is outside the install folder, which an update replaces.

What: the recording as the microphone gave it, before the boost, as
<time>.wav, and one line per dictation in dictations.jsonl. A line has the
numbers the log has, and with them the words: what the cloud wrote, what
asking again made of it, what the alphabet check and the dictionary
changed, and what was typed in the end, with the time each step took. A
correction made with Ctrl+Alt+Win gets a line of its own, because it marks
the dictation before it as wrong.

Never: in the log, in a problem report, or in the repository. The log
says only that it is on.

Kept for `keep_days` (30), then a day's folder is deleted whole.
Nothing here can cost a dictation: every failure is caught and logged by
its type.
"""

import datetime
import json
import logging
import os
import re
import shutil
import threading
import time
import wave
from pathlib import Path

logger = logging.getLogger("heyspeaky.archive")

DEFAULT_FOLDER = "%LOCALAPPDATA%\\HeySpeaky\\archive"
KEEP_DAYS = 30
LINES = "dictations.jsonl"

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def settings(cfg):
    return (cfg or {}).get("archive") or {}


def folder(cfg):
    """Where the archive lives, with %VARIABLES% filled in."""
    raw = settings(cfg).get("folder") or DEFAULT_FOLDER
    return Path(os.path.expandvars(os.path.expanduser(raw)))


class Archive(object):
    """Keeps dictations when config.json switches it on; otherwise does
    nothing at all."""

    def __init__(self, cfg, today=None):
        self._cfg = cfg
        self._lock = threading.Lock()
        self._today = today or datetime.date.today
        self._pruned_for = None

    @property
    def enabled(self):
        return bool(settings(self._cfg).get("enabled"))

    def day_folder(self, day=None):
        return folder(self._cfg) / (day or self._today()).isoformat()

    def keep(self, pcm, rate, entry):
        """Saves one dictation: the recording and its line. `entry` is a
        dict of plain values; "time" and "wav" are filled in here."""
        if not self.enabled:
            return None
        try:
            with self._lock:
                self._prune_once_a_day()
                day = self.day_folder()
                day.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%H%M%S")
                wav = day / (stamp + ".wav")
                count = 2
                while wav.exists():
                    wav = day / "{}-{}.wav".format(stamp, count)
                    count += 1
                if pcm:
                    with wave.open(str(wav), "wb") as handle:
                        handle.setnchannels(1)
                        handle.setsampwidth(2)
                        handle.setframerate(int(rate))
                        handle.writeframes(pcm)
                line = dict(entry, kind="dictation",
                            time=time.strftime("%H:%M:%S"),
                            wav=wav.name if pcm else "")
                self._append(day, line)
            return wav
        except Exception as exc:
            logger.warning("Could not keep a dictation in the archive: %s",
                           type(exc).__name__)
            return None

    def correction(self, heard, meant):
        """A Ctrl+Alt+Win correction: the dictation before it was wrong."""
        if not self.enabled:
            return
        try:
            with self._lock:
                day = self.day_folder()
                day.mkdir(parents=True, exist_ok=True)
                self._append(day, {"kind": "correction",
                                   "time": time.strftime("%H:%M:%S"),
                                   "heard": heard or "", "meant": meant})
        except Exception as exc:
            logger.warning("Could not keep a correction in the archive: %s",
                           type(exc).__name__)

    @staticmethod
    def _append(day, line):
        with open(str(day / LINES), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    def prune(self):
        """Deletes the days older than keep_days. Only folders named like a
        date, inside the archive: nothing else is ever touched."""
        if not self.enabled:
            return 0
        try:
            keep = int(settings(self._cfg).get("keep_days", KEEP_DAYS))
        except (TypeError, ValueError):
            keep = KEEP_DAYS
        if keep <= 0:
            return 0
        oldest = self._today() - datetime.timedelta(days=keep)
        root = folder(self._cfg)
        removed = 0
        try:
            days = list(root.iterdir()) if root.is_dir() else []
        except OSError:
            return 0
        for path in days:
            if not (path.is_dir() and _DAY.match(path.name)):
                continue
            try:
                day = datetime.date.fromisoformat(path.name)
            except ValueError:
                continue
            if day < oldest:
                try:
                    shutil.rmtree(str(path))
                    removed += 1
                except OSError as exc:
                    logger.warning("Could not delete an old archive day: %s",
                                   type(exc).__name__)
        if removed:
            logger.info("Archive: deleted %d day(s) older than %d days",
                        removed, keep)
        return removed

    def _prune_once_a_day(self):
        today = self._today()
        if self._pruned_for != today:
            self._pruned_for = today
            self.prune()
