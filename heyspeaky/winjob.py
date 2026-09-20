"""Ties child processes to the lifetime of the app.

RealtimeSTT runs final transcription in a spawned child process. If HeySpeaky
dies without running its shutdown path (Task Manager, a forced sign-out, a
crash, or an installer that restarts it) that child is orphaned. Its parent
pipe is gone, so RealtimeSTT's poll loop raises BrokenPipeError, logs the
traceback, and immediately tries again. Forever.

That is not hypothetical. Twelve orphans were found on the development machine,
the oldest three days old, and between them they had written an 8.7 GB
stdout.log and taken the system disk down to its last few gigabytes.

No amount of Python can fix this: TerminateProcess runs no atexit handlers, no
finally blocks, and no signal handlers. The cleanup has to outlive us, so it
belongs to the operating system. We put the process in a job object marked
kill-on-close. Children inherit the job, and when the last handle to it closes
which Windows does for us when the process dies, however it dies, every
process still in the job is terminated.

Call join_kill_on_close() once, in the parent, before anything is spawned.
"""

import ctypes
import logging
from ctypes import wintypes

logger = logging.getLogger("heyspeaky.winjob")

_JobObjectExtendedLimitInformation = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

# Kept at module scope on purpose. The job lives exactly as long as this
# handle: if it were garbage collected the job would close and Windows would
# kill the very processes it is meant to protect.
_job = None


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def join_kill_on_close():
    """Puts this process in a job that kills its children when we exit.

    Returns True if the job is in place. A False means the app still works.
    Orphaned workers are a cleanup problem, not a correctness one, so the
    caller logs it and carries on rather than refusing to start.
    """
    global _job
    if _job is not None:
        return True

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        # Explicit signatures: handles are 64-bit and ctypes defaults to a
        # 32-bit int, which silently truncates them.
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [
            wintypes.HANDLE, wintypes.HANDLE,
        ]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        # Anonymous: a named job could collide with another user's, and we
        # never need to look it up again.
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            logger.warning(
                "CreateJobObject failed (%d); orphaned workers are possible",
                ctypes.get_last_error(),
            )
            return False

        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = \
            _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            job,
            _JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            logger.warning(
                "SetInformationJobObject failed (%d)", ctypes.get_last_error()
            )
            kernel32.CloseHandle(job)
            return False

        if not kernel32.AssignProcessToJobObject(
            job, kernel32.GetCurrentProcess()
        ):
            # Windows 8 and later allow nested jobs, so this is rare. It can
            # still happen under some launchers and debuggers that put us in a
            # job which forbids breakaway.
            logger.warning(
                "AssignProcessToJobObject failed (%d); already in a job that "
                "does not allow nesting", ctypes.get_last_error(),
            )
            kernel32.CloseHandle(job)
            return False

        _job = job
        logger.info("Child processes tied to this process via a job object")
        return True
    except Exception:
        logger.warning("Could not set up the job object", exc_info=True)
        return False
