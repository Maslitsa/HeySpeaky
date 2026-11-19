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
_user32.GetClipboardData.argtypes = [wintypes.UINT]
_user32.GetClipboardData.restype = wintypes.HANDLE
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wintypes.HANDLE
_kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
_kernel32.GlobalLock.restype = wintypes.LPVOID
_kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalFree.argtypes = [wintypes.HANDLE]
_kernel32.GlobalFree.restype = wintypes.HANDLE
_user32.GetClipboardSequenceNumber.argtypes = []
_user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
_user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD,
                                ctypes.c_size_t]
_user32.keybd_event.restype = None
_user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
_user32.MapVirtualKeyW.restype = wintypes.UINT
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR,
                                  ctypes.c_int]
_user32.GetClassNameW.restype = ctypes.c_int
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                             ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                  wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD)]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

VK_CONTROL = 0x11
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002


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


def read_clipboard():
    """What is on the clipboard as text, or "" if there is none to be had."""
    for _attempt in range(10):
        if _user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        logger.warning("Clipboard stayed locked; nothing read")
        return ""

    try:
        handle = _user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = _kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            _kernel32.GlobalUnlock(handle)
    except Exception:
        logger.exception("Could not read the clipboard")
        return ""
    finally:
        _user32.CloseClipboard()


def clear_clipboard():
    """Empties the clipboard, so a copy that yields nothing can be seen."""
    for _attempt in range(10):
        if _user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        return False
    try:
        _user32.EmptyClipboard()
        return True
    finally:
        _user32.CloseClipboard()


def _clipboard_sequence():
    """A number Windows moves on every time anything writes the clipboard."""
    try:
        return int(_user32.GetClipboardSequenceNumber())
    except Exception:
        return 0


def _send_copy():
    """Ctrl+C, by key code, with a moment between each step.

    By code rather than by the name "c": a name is looked up in tables the
    keyboard library built from whichever layout was active when it loaded,
    and the owner types in four languages. And a step at a time rather than
    all four in one burst, which some windows take as a key that was never
    really held.
    """
    for code, up in ((VK_CONTROL, False), (VK_C, False), (VK_C, True),
                     (VK_CONTROL, True)):
        _user32.keybd_event(code, _user32.MapVirtualKeyW(code, 0),
                            KEYEVENTF_KEYUP if up else 0, 0)
        time.sleep(0.012)


def _foreground_class():
    """What kind of window is in front: its class, never its title, which
    can be the name of somebody's document."""
    try:
        buffer = ctypes.create_unicode_buffer(128)
        _user32.GetClassNameW(_user32.GetForegroundWindow(), buffer, 128)
        return buffer.value or "?"
    except Exception:
        return "?"


def _foreground_program():
    """The program in front, by file name - chrome.exe, not the title,
    which can be the name of somebody's document. Chrome, Edge, VS Code and
    every Electron app share one window class, so the class alone cannot
    say which of them it was."""
    handle = None
    try:
        pid = wintypes.DWORD(0)
        _user32.GetWindowThreadProcessId(_user32.GetForegroundWindow(),
                                         ctypes.byref(pid))
        handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                       False, pid.value)
        if not handle:
            return "?"
        buffer = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer,
                                                    ctypes.byref(size)):
            return "?"
        return buffer.value.replace("/", "\\").rsplit("\\", 1)[-1] or "?"
    except Exception:
        return "?"
    finally:
        if handle:
            _kernel32.CloseHandle(handle)


def copy_selection(modifier_timeout=5.0, settle=0.6, tries=2):
    """Whatever is selected in the window in front, via Ctrl+C.

    There is no way to read another program's selection directly, so this
    borrows the clipboard and puts it back. It empties it first: without that,
    a Ctrl+C that copies nothing - because nothing was selected - leaves the
    previous contents sitting there looking exactly like a selection.

    Ctrl+C cannot be sent while Ctrl+Alt is still held, for the same reason
    `deliver` waits: the target would see Ctrl+Alt+C.

    Whether the window acted on it is read off the clipboard's sequence
    number. A Ctrl+C that never arrived leaves it where it was, and is tried
    once more; a window that answered with no text had nothing selected, and
    is not asked again. The owner got an empty box nine times in a row with
    nothing in the log to say which of those it was, so it says now - how
    much, from which program and what kind of window, never the words.

    An unchanged clipboard is not proof the keys went missing. Measured on
    23 September: Chrome writes nothing at all when nothing is selected,
    and the same code, with the chord pressed fast or slow and let go in
    any order, read a Chrome selection every time. So the line says the
    clipboard did not change, which is what is known.
    """
    previous = read_clipboard()
    started = time.monotonic()
    released = wait_for_modifiers_released(modifier_timeout)
    waited = time.monotonic() - started

    selection = ""
    answered = False
    attempt = 0
    for attempt in range(1, max(1, tries) + 1):
        clear_clipboard()
        before = _clipboard_sequence()
        try:
            _send_copy()
        except Exception:
            logger.exception("Could not send Ctrl+C")
            break
        deadline = time.monotonic() + settle
        while time.monotonic() < deadline:
            if _clipboard_sequence() != before:
                answered = True
                selection = read_clipboard()
                if selection:
                    break
            time.sleep(0.02)
        if selection or answered:
            break
        time.sleep(0.05)

    logger.info(
        "Selection: %d chars from %s (%s), %d %s; keys up after %.2fs%s; %s",
        len(selection.strip()), _foreground_program(), _foreground_class(),
        attempt, "try" if attempt == 1 else "tries", waited,
        "" if released else " (gave up waiting)",
        "the window answered" if answered else
        "the clipboard never changed (nothing selected, or the keys did not "
        "arrive)")

    # Put back what the person had, whether or not anything was selected.
    if previous:
        copy_to_clipboard(previous)
    elif selection:
        clear_clipboard()
    return selection.strip()


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
