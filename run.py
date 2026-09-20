"""HeySpeaky entry point.

Launch with pythonw.exe so no console window ever appears.

The stream redirection below runs at import time on purpose: RealtimeSTT
transcribes in a spawned child process, and multiprocessing re-imports this
module in that child. Under pythonw.exe sys.stdout/stderr/stdin are None, and
any stray print() in a dependency would raise. Pointing them at a log file
early fixes it for the parent and every child.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"

# multiprocessing imports this module in spawned children under the name
# __mp_main__, so this is how the parent tells itself apart from its workers.
IS_WORKER = __name__ != "__main__"

# Per-process ceiling on the raw stdout/stderr log. Diagnostics live in
# logs/heyspeaky.log, which rotates; this file only catches output from
# dependencies that print instead of logging, and it exists because one of
# them once wrote 8.7 GB of the same traceback. See heyspeaky/winjob.py.
STDOUT_LOG_LIMIT = 2_000_000


class _CappedStream:
    """A write-only stream that stops writing once it hits a byte budget.

    Nothing upstream is expected to misbehave this badly, but stdout here is
    unattended and unread: it is written by a background process with no
    console, on a laptop whose owner has no reason to look at it until the
    disk is full. A ceiling turns that failure into a truncated log.
    """

    def __init__(self, path, mode, limit):
        self._file = open(path, mode, encoding="utf-8", errors="replace",
                          buffering=1)
        self._limit = limit
        self._written = self._file.tell() if mode == "a" else 0
        self._stopped = False

    def write(self, text):
        if self._stopped:
            return len(text)
        self._written += len(text)
        if self._written > self._limit:
            self._stopped = True
            try:
                self._file.write(
                    "\n[HeySpeaky] stdout log hit its {} byte limit; "
                    "further output from this process is dropped.\n".format(
                        self._limit)
                )
                self._file.flush()
            except (OSError, ValueError):
                pass
            return len(text)
        try:
            return self._file.write(text)
        except (OSError, ValueError):
            self._stopped = True
            return len(text)

    def flush(self):
        try:
            self._file.flush()
        except (OSError, ValueError):
            pass

    def isatty(self):
        return False

    def writable(self):
        return True

    def readable(self):
        return False

    def seekable(self):
        return False

    def fileno(self):
        return self._file.fileno()

    def close(self):
        try:
            self._file.close()
        except (OSError, ValueError):
            pass

    @property
    def encoding(self):
        return "utf-8"


try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

if sys.stdout is None or sys.stderr is None:
    # The parent starts a clean log each run; workers append to it so they
    # cannot truncate the log their parent is still writing.
    try:
        _stream = _CappedStream(
            LOG_DIR / "stdout.log",
            "a" if IS_WORKER else "w",
            STDOUT_LOG_LIMIT,
        )
    except OSError:
        _stream = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = sys.__stdout__ = _stream
    sys.stderr = sys.__stderr__ = _stream

if sys.stdin is None:
    try:
        sys.stdin = sys.__stdin__ = open(os.devnull, "r", encoding="utf-8")
    except OSError:
        pass


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    # The job object that stops us orphaning transcription workers is set up
    # in heyspeaky.app.main(), which runs before anything is spawned and after
    # logging exists, so the outcome is recorded.
    from heyspeaky.app import main

    sys.exit(main())
