"""Typing in the layout the person is actually using.

Tk 8.6 on Windows takes a typed character as a byte of the old one-byte code
page and decodes it with whichever code page it last heard about, which is
not always the layout in use. Measured on the owner's laptop with the Kazakh
layout: the key that types "і" everywhere else came into the correction box
as "³", the keys for "ң", "ү" and "қ" as "?", and "й" as "é". Most of Kazakh
is not in that code page at all, so no choice of decoding could have saved it.

So a text field here asks Windows itself what the key means in the active
layout - `ToUnicodeEx`, which answers in Unicode - and types that instead,
whenever it differs from what Tk made of it. On an English layout the two
agree and Tk is left to do its own typing.
"""

import ctypes
import logging
import tkinter as tk
from ctypes import wintypes

logger = logging.getLogger("heyspeaky.keymap")

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
_user32.GetKeyboardLayout.restype = ctypes.c_void_p
_user32.GetKeyboardState.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
_user32.GetKeyboardState.restype = wintypes.BOOL
_user32.MapVirtualKeyExW.argtypes = [wintypes.UINT, wintypes.UINT,
                                     ctypes.c_void_p]
_user32.MapVirtualKeyExW.restype = wintypes.UINT
_user32.ToUnicodeEx.argtypes = [wintypes.UINT, wintypes.UINT,
                                ctypes.POINTER(ctypes.c_ubyte),
                                wintypes.LPWSTR, ctypes.c_int, wintypes.UINT,
                                ctypes.c_void_p]
_user32.ToUnicodeEx.restype = ctypes.c_int

VK_CONTROL = 0x11
VK_MENU = 0x12
# Windows 10 1607 and later: read the key without disturbing a dead key
# that is waiting for its letter.
_KEEP_STATE = 0x4


def typed_char(keycode, layout=None):
    """What the active layout types for this key right now, or "".

    "" for anything that is not text: a shortcut with Ctrl, an arrow, a dead
    key still waiting for its letter, Backspace, Enter. `layout` is a layout
    handle to ask instead of the active one, for the tests.
    """
    try:
        if layout is None:
            layout = _user32.GetKeyboardLayout(0)
        state = (ctypes.c_ubyte * 256)()
        if not _user32.GetKeyboardState(state):
            return ""
        # Ctrl alone makes a shortcut; Ctrl with Alt is AltGr, which types.
        if state[VK_CONTROL] & 0x80 and not state[VK_MENU] & 0x80:
            return ""
        scan = _user32.MapVirtualKeyExW(keycode, 0, layout)
        buffer = ctypes.create_unicode_buffer(8)
        count = _user32.ToUnicodeEx(keycode, scan, state, buffer, 8,
                                    _KEEP_STATE, layout)
    except Exception:
        logger.debug("Could not read the layout", exc_info=True)
        return ""
    if count < 1:
        return ""
    text = buffer.value[:count]
    if not text or any(ord(char) < 0x20 or ord(char) == 0x7F
                       for char in text):
        return ""
    return text


def fix_typing(widget, on_typed=None):
    """Makes a Tk Entry type what the layout says, not what Tk decoded.

    Bind this after the widget's own key bindings: when it types for Tk it
    ends the event there, so nothing later sees the key. `on_typed` is
    called after it has typed, for whatever a keystroke should also do.
    """
    def typed(event):
        text = typed_char(event.keycode)
        if not text or text == event.char:
            return None
        try:
            if widget.selection_present():
                widget.delete("sel.first", "sel.last")
            widget.insert("insert", text)
        except tk.TclError:
            return None
        try:
            # What Tk's own typing does next: keep the caret in view.
            widget.tk.call("tk::EntrySeeInsert", widget._w)
        except tk.TclError:
            pass
        if on_typed is not None:
            try:
                on_typed(event)
            except Exception:
                logger.exception("A keystroke handler failed")
        return "break"

    widget.bind("<KeyPress>", typed, add="+")
    return typed
