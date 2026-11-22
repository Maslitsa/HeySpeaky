"""The black box: what HeySpeaky leaves behind when it stops without saying why.

In November 2026 the app vanished six times, mostly overnight. Each time the
log just stopped: no "Shutting down", no error, nothing in Windows' own crash
log, and the computer had not restarted. Nobody could say why, because
nothing in the app wrote down how a run ended. This module does. It writes
numbers, times and program names, never anything dictated.

- A native crash (an access violation in a C library, a fatal Python error)
  writes every thread's stack to logs/crash.log through faulthandler. Under
  pythonw.exe there is no console for it to write to otherwise.
- An exception nobody caught, in any thread or in a Tk callback, goes to the
  log instead of to a stderr nobody reads.
- While the app runs, logs/running.json says when it was last seen alive and
  what it held then. A clean shutdown removes the file, so finding it at the
  next start means the last run never shut down, and that start says so.
- Once an hour, a line with the memory, handles and GDI objects it holds:
  Windows twice flagged the app's memory as growing.
- A tick that comes much later than it should means the computer slept or
  the app stood still. Either way the log says so.
- At start, which program started it: the shortcut (explorer.exe) or a
  script (powershell.exe), whose window may take the app with it.
"""

import atexit
import ctypes
import faulthandler
import json
import logging
import os
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

logger = logging.getLogger("heyspeaky.blackbox")

TICK_SECONDS = 60
# A tick five minutes late is not a busy moment. The computer slept, or the
# Tk loop that runs the ticks stood still.
GAP_SECONDS = 300
MEMORY_EVERY = 3600
CRASH_LOG_LIMIT = 1_000_000
MARKER = "running.json"
CRASH_LOG = "crash.log"

# faulthandler writes to this file's descriptor when the process dies, so it
# must stay open for as long as the process lives.
_crash_file = None


# -- what the process holds -------------------------------------------------

class _MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def holdings():
    """Memory in MB, handles, GDI and USER objects, threads. Never raises."""
    found = {"threads": threading.active_count()}
    try:
        kernel32 = ctypes.WinDLL("kernel32")
        psapi = ctypes.WinDLL("psapi")
        user32 = ctypes.WinDLL("user32")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        me = kernel32.GetCurrentProcess()
        counters = _MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_MEMORY_COUNTERS), wintypes.DWORD]
        if psapi.GetProcessMemoryInfo(me, ctypes.byref(counters),
                                      counters.cb):
            found["memory_mb"] = round(counters.WorkingSetSize / 2**20)
            found["private_mb"] = round(counters.PrivateUsage / 2**20)
        handles = wintypes.DWORD()
        kernel32.GetProcessHandleCount.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        if kernel32.GetProcessHandleCount(me, ctypes.byref(handles)):
            found["handles"] = handles.value
        user32.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        found["gdi"] = user32.GetGuiResources(me, 0)
        found["user"] = user32.GetGuiResources(me, 1)
    except (OSError, AttributeError):
        pass
    return found


_LABELS = (("handles", "handles"), ("gdi", "GDI objects"),
           ("user", "USER objects"), ("threads", "threads"))


def describe(held):
    parts = []
    if "memory_mb" in held:
        parts.append("memory {} MB (private {} MB)".format(
            held["memory_mb"], held.get("private_mb", "?")))
    for key, label in _LABELS:
        if key in held:
            parts.append("{} {}".format(label, held[key]))
    return ", ".join(parts) or "nothing measured"


# -- who started us ---------------------------------------------------------

class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def _process_table():
    """{pid: (parent pid, exe name)} for every process. Empty if it fails."""
    table = {}
    try:
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD,
                                                      wintypes.DWORD]
        kernel32.Process32FirstW.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
        kernel32.Process32NextW.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)
        if not snapshot or snapshot == wintypes.HANDLE(-1).value:
            return table
        try:
            entry = _PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(entry)
            more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                table[entry.th32ProcessID] = (entry.th32ParentProcessID,
                                              entry.szExeFile)
                more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)
    except (OSError, AttributeError):
        pass
    return table


def started_by(pid=None, table=None):
    """The program that started us, skipping the venv's own pythonw launcher.

    The shortcut runs the venv's pythonw.exe, which starts the real one as
    its child, so the parent is always another pythonw. What matters is the
    one above it: explorer.exe for the shortcut, powershell.exe for the
    installer, something else for a script.
    """
    table = _process_table() if table is None else table
    pid = os.getpid() if pid is None else pid
    chain = []
    seen = set()
    while pid in table and pid not in seen and len(chain) < 4:
        seen.add(pid)
        parent, _ = table[pid]
        if parent not in table:
            break
        name = table[parent][1]
        chain.append(name)
        if name.lower() not in ("python.exe", "pythonw.exe"):
            return name
        pid = parent
    return chain[-1] if chain else "unknown"


# -- the box ------------------------------------------------------------------

def open_crash_log(log_dir, version):
    """Points faulthandler at logs/crash.log, one header line per start."""
    global _crash_file
    path = Path(log_dir) / CRASH_LOG
    try:
        if path.exists() and path.stat().st_size > CRASH_LOG_LIMIT:
            os.replace(path, path.with_name(CRASH_LOG + ".1"))
        handle = open(path, "a", encoding="utf-8", errors="replace")
        handle.write("=== HeySpeaky {} pid {} started {} ===\n".format(
            version, os.getpid(), time.strftime("%Y-%m-%d %H:%M:%S")))
        handle.flush()
        faulthandler.enable(file=handle, all_threads=True)
    except (OSError, ValueError, RuntimeError):
        logger.warning("Could not open the crash log", exc_info=True)
        return None
    if _crash_file is not None and _crash_file is not handle:
        try:
            _crash_file.close()
        except OSError:
            pass
    _crash_file = handle
    return path


def last_words(crash_log, pid):
    """True if crash.log holds something after the header of run `pid`."""
    try:
        text = Path(crash_log).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    header = " pid {} started ".format(pid)
    at = text.rfind(header)
    if at < 0:
        return False
    after = text[at:].split("\n", 1)
    if len(after) < 2:
        return False
    following = after[1].split("=== HeySpeaky ", 1)[0]
    return bool(following.strip())


def catch_uncaught():
    """Sends exceptions nobody caught to the log, from any thread."""

    def on_thread(args):
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread is not None else "?"
        logger.error("Uncaught exception in thread %s", name,
                     exc_info=(args.exc_type, args.exc_value,
                               args.exc_traceback))

    def on_main(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    threading.excepthook = on_thread
    sys.excepthook = on_main


def watch_tk(root):
    """Tk prints a failed callback to stderr, which under pythonw is a file
    that the next start empties. This sends it to the log instead."""

    def report(exc_type, exc, tb):
        logger.error("Tk callback failed", exc_info=(exc_type, exc, tb))

    root.report_callback_exception = report


class BlackBox:
    """The marker file, the hourly line and the late-tick check."""

    def __init__(self, log_dir, version, clock=time.time, measure=holdings,
                 who=started_by):
        self.log_dir = Path(log_dir)
        self.version = version
        self.path = self.log_dir / MARKER
        self._clock = clock
        self._measure = measure
        self._who = who
        self._started = None
        self._last_tick = None
        self._last_memory = None
        self._starter = None
        self._stopped = False

    def start(self):
        """Reports how the last run ended, then marks this one as running."""
        self._started = self._clock()
        self._last_tick = self._started
        self._last_memory = self._started
        self._starter = self._who()
        self.report_previous()
        logger.info("Started by %s; %s", self._starter,
                    describe(self._measure()))
        self._write(self._measure())
        atexit.register(self._at_exit)

    def report_previous(self):
        try:
            before = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            logger.warning("The last run left a marker that cannot be read")
            return None
        if not isinstance(before, dict):
            return None
        seen = before.get("seen")
        ago = ""
        if isinstance(seen, (int, float)):
            minutes = max(0, round((self._clock() - seen) / 60))
            ago = " ({} min before this start)".format(minutes)
        how = ("Python exited on its own without shutting down"
               if before.get("exited") else
               "killed, or crashed before it could say so")
        words = ""
        if before.get("pid") and last_words(self.log_dir / CRASH_LOG,
                                            before["pid"]):
            words = "; crash.log holds what it said as it died"
        logger.warning(
            "The last run (HeySpeaky %s, pid %s, started by %s at %s) ended "
            "without shutting down: %s. Last seen alive %s%s with %s%s",
            before.get("version", "?"), before.get("pid", "?"),
            before.get("started_by", "?"), _when(before.get("started")),
            how, _when(seen), ago, describe(before.get("held") or {}), words)
        return before

    def tick(self):
        """Runs once a minute on the Tk thread."""
        if self._stopped or self._started is None:
            return
        now = self._clock()
        gap = now - self._last_tick
        if gap > GAP_SECONDS:
            logger.info(
                "Back after %d min without a tick: the computer slept, or the "
                "app stood still", round(gap / 60))
        self._last_tick = now
        held = self._measure()
        if now - self._last_memory >= MEMORY_EVERY:
            self._last_memory = now
            logger.info("Alive %.1f h: %s", (now - self._started) / 3600,
                        describe(held))
        self._write(held)

    def stop(self):
        """A clean shutdown: the next start has nothing to report."""
        self._stopped = True
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("Could not remove %s", self.path.name)

    def _at_exit(self):
        # Python is leaving without shutdown() having run: a fatal error the
        # app caught and returned from, or an exit nobody expected. Say so,
        # so the next start can tell this from being killed.
        if self._stopped:
            return
        logger.warning("Exiting without shutting down")
        self._write(self._measure(), exited=True)

    def _write(self, held, exited=False):
        state = {
            "pid": os.getpid(),
            "version": self.version,
            "started": self._started,
            "started_by": self._starter,
            "seen": self._clock(),
            "held": held,
        }
        if exited:
            state["exited"] = True
        partial = self.path.with_name(MARKER + ".tmp")
        try:
            partial.write_text(json.dumps(state), encoding="utf-8")
            os.replace(partial, self.path)
        except OSError:
            logger.debug("Could not write %s", self.path.name, exc_info=True)


def _when(stamp):
    if not isinstance(stamp, (int, float)):
        return "?"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp))
