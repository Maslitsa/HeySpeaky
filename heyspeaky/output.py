"""Delivering the finished transcript.

The text always lands on the clipboard, and by default is also pasted into
whatever window had focus. We wait for Ctrl/Alt to come up first: in latched
mode you stop the recording with the same chord, and sending Ctrl+V while
Alt is still down would fire Ctrl+Alt+V in the target app instead.
"""

import ctypes
import logging
import time
from ctypes import wintypes

import keyboard

from .hotkey import wait_for_modifiers_released

logger = logging.getLogger("heyspeaky.output")

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# These signatures are not optional. ctypes defaults every undeclared return
# value to a 32-bit int, which silently truncates the 64-bit handles and
# pointers these functions return. GlobalLock then hands back a null
# pointer and memmove faults.
_user32.OpenClipboard.argtypes = [wintypes.HWND]
_user32.OpenClipboard.restype = wintypes.BOOL
_user32.EmptyClipboard.argtypes = []
_user32.EmptyClipboard.restype = wintypes.BOOL
_user32.CloseClipboard.argtypes = []
_user32.CloseClipboard.restype = wintypes.BOOL
_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_user32.SetClipboardData.restype = wintypes.HANDLE
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wintypes.HANDLE
_kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
_kernel32.GlobalLock.restype = wintypes.LPVOID
_kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalFree.argtypes = [wintypes.HANDLE]
_kernel32.GlobalFree.restype = wintypes.HANDLE


def copy_to_clipboard(text):
    """Puts text on the Windows clipboard, retrying while it is locked."""
    for _attempt in range(10):
        if _user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        logger.warning("Clipboard stayed locked; text not copied")
        return False

    try:
        _user32.EmptyClipboard()
        buffer = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buffer)
        handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            logger.warning("GlobalAlloc failed; text not copied")
            return False
        pointer = _kernel32.GlobalLock(handle)
        if not pointer:
            _kernel32.GlobalFree(handle)
            logger.warning("GlobalLock failed; text not copied")
            return False
        ctypes.memmove(pointer, buffer, size)
        _kernel32.GlobalUnlock(handle)
        # Ownership passes to the clipboard only if this succeeds.
        if not _user32.SetClipboardData(CF_UNICODETEXT, handle):
            _kernel32.GlobalFree(handle)
            logger.warning("SetClipboardData failed; text not copied")
            return False
        return True
    finally:
        _user32.CloseClipboard()


def deliver(text, config):
    """Copies and optionally inserts the transcript. Returns a status string."""
    if not text:
        return "empty"

    payload = text + (" " if config["append_space"] else "")
    copied = False
    if config["copy_to_clipboard"]:
        copied = copy_to_clipboard(payload)

    method = config["insert_method"]
    if method == "none":
        return "copied" if copied else "failed"

    wait_for_modifiers_released(float(config["modifier_release_timeout"]))

    try:
        if method == "paste" and copied:
            # Small settle so the target window is ready for the keystroke.
            time.sleep(0.04)
            keyboard.send("ctrl+v")
        else:
            keyboard.write(payload, delay=0.005)
        return "inserted"
    except Exception as exc:
        logger.exception("Could not insert text")
        return "copied" if copied else "failed: {}".format(exc)
