r"""Ctrl+Alt+Space: say what the words should have been.

The owner asked for this in so many words: mark the part that came out wrong,
type the right version over it, and stop having to do it again. What it can
and cannot teach is in `dictionary.py`; this is the gesture.

Three things about it are deliberate.

**It takes the selection through the clipboard**, because there is no way to
read another program's selection directly, and it puts the clipboard back
afterwards. Nothing is sent until Ctrl and Alt are up: a Ctrl+C on top of a
held Ctrl+Alt is Ctrl+Alt+C in the window in front, which is somebody else's
shortcut.

**This window takes focus, and the pill never does.** They are opposite
things. Dictation has to be invisible or it is not worth having, so the pill
is `WS_EX_NOACTIVATE` and never steals the caret. Correcting a word is a
deliberate stop-and-type, and a box you cannot type into is useless. The
window in front is remembered before the box opens and put back afterwards,
so the corrected text lands where the wrong text was.

**Nothing is saved on an empty answer or on Escape.** A dictionary is only
worth trusting if every entry in it was typed on purpose.
"""

import ctypes
import logging
import tkinter as tk
from ctypes import wintypes

from . import dictionary, theme

logger = logging.getLogger("heyspeaky.correct")

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE,
                                 wintypes.BOOL]
_user32.SetWindowRgn.restype = ctypes.c_int
_gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
_gdi32.CreateRoundRectRgn.restype = wintypes.HANDLE

WIDTH = 420
PAD = 14
# A card, not a capsule. The pill is rounded to half its height because it is
# one; a box with a line of type in it wants the softer corner of everything
# else on the desktop.
RADIUS = 14


def _round_corners(window, width, height, radius=RADIUS):
    """Clips a Tk window to rounded corners.

    Windows 10 does not round a window with no frame, and an
    `overrideredirect` box is exactly that, so it comes out as a hard
    rectangle next to a pill that is all curves. Windows owns the region
    once it is set, which is why it is never freed here.
    """
    try:
        handle = int(window.winfo_id())
        region = _gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1,
                                           radius * 2, radius * 2)
        if region:
            _user32.SetWindowRgn(handle, region, True)
            return True
    except Exception:
        logger.debug("Could not round the corners", exc_info=True)
    return False


def foreground_window():
    """The window the correction came from, to hand focus back to."""
    try:
        return _user32.GetForegroundWindow()
    except Exception:
        logger.debug("GetForegroundWindow unavailable", exc_info=True)
        return None


def restore_foreground(handle):
    """Puts focus back where it was. Best effort: Windows may refuse."""
    if not handle:
        return False
    try:
        return bool(_user32.SetForegroundWindow(handle))
    except Exception:
        logger.debug("SetForegroundWindow failed", exc_info=True)
        return False


def _rgb(colour):
    return "#{:02x}{:02x}{:02x}".format(*colour)


class CorrectionBox(object):
    """Asks what the selected words should have been.

    Built on the app's existing Tk root as a Toplevel, because a second Tk
    instance in one process is a way to hang the interpreter, and because
    everything here has to run on the thread that owns the root anyway.
    """

    def __init__(self, root, heard, on_done):
        self._on_done = on_done
        self._answered = False

        self.top = tk.Toplevel(root)
        self.top.withdraw()
        self.top.title("HeySpeaky")
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg=_rgb(theme.TINT))

        frame = tk.Frame(self.top, bg=_rgb(theme.TINT),
                         padx=PAD, pady=PAD, highlightthickness=1,
                         highlightbackground=_rgb(theme.CANCEL_FILL))
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text=("What should it have said?" if heard
                  else "A word to remember"),
            bg=_rgb(theme.TINT), fg=_rgb(theme.TEXT_LIGHT),
            font=("Segoe UI", theme.FONT_SIZE),
            anchor="w",
        ).pack(fill="x")

        if heard:
            tk.Label(
                frame, text="heard: " + heard,
                bg=_rgb(theme.TINT), fg=_rgb(theme.CANCEL_GLYPH),
                font=("Segoe UI", theme.LABEL_SIZE), anchor="w",
                wraplength=WIDTH - 2 * PAD, justify="left",
            ).pack(fill="x", pady=(2, 8))
        else:
            tk.Label(
                frame,
                text="Nothing was selected. Type a word to declare it.",
                bg=_rgb(theme.TINT), fg=_rgb(theme.CANCEL_GLYPH),
                font=("Segoe UI", theme.LABEL_SIZE), anchor="w",
            ).pack(fill="x", pady=(2, 8))

        self.entry = tk.Entry(
            frame, bg=_rgb(theme.CANCEL_FILL), fg=_rgb(theme.TEXT_LIGHT),
            insertbackground=_rgb(theme.TEXT_LIGHT), relief="flat",
            font=("Segoe UI", theme.FONT_SIZE + 1),
        )
        self.entry.pack(fill="x", ipady=6)
        self.entry.insert(0, heard)
        self.entry.select_range(0, "end")

        tk.Label(
            frame, text="Enter saves it · Esc leaves it alone",
            bg=_rgb(theme.TINT), fg=_rgb(theme.CANCEL_GLYPH),
            font=("Segoe UI", theme.LABEL_SIZE), anchor="w",
        ).pack(fill="x", pady=(8, 0))

        self.top.bind("<Return>", self._accept)
        self.top.bind("<KP_Enter>", self._accept)
        self.top.bind("<Escape>", self._cancel)
        # Clicking away is the third way people close a box like this, and
        # leaving it floating over everything when they do is the fastest way
        # to make somebody hate a feature.
        self.top.bind("<FocusOut>", self._focus_left)

        self._place()
        self.top.deiconify()
        self.top.lift()
        self.top.focus_force()
        self.entry.focus_set()

    def _place(self):
        """Near the pointer, and always fully on the screen it is on."""
        self.top.update_idletasks()
        width = max(WIDTH, self.top.winfo_reqwidth())
        height = self.top.winfo_reqheight()
        x = self.top.winfo_pointerx() - width // 2
        y = self.top.winfo_pointery() + 24
        limit_x = self.top.winfo_screenwidth() - width - 8
        limit_y = self.top.winfo_screenheight() - height - 8
        x = max(8, min(x, limit_x))
        y = max(8, min(y, limit_y))
        self.top.geometry("{}x{}+{}+{}".format(width, height, x, y))
        self.top.update_idletasks()
        _round_corners(self.top, width, height)

    def _focus_left(self, _event=None):
        """Closes the box when focus leaves it, and only then.

        Tk reports a FocusOut on the Toplevel when focus moves to a widget
        inside it as well, which is every click in the entry. Taking that at
        face value would shut the box the instant somebody tried to use it.
        """
        try:
            if self.top.focus_get() is not None:
                return
        except (tk.TclError, KeyError):
            pass
        self._cancel()

    def _accept(self, _event=None):
        self._finish(self.entry.get().strip())

    def _cancel(self, _event=None):
        self._finish(None)

    def _finish(self, answer):
        if self._answered:
            return
        self._answered = True
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        self._on_done(answer)


def remember(heard, meant):
    """Records the pair and returns what the text should now read.

    Saving and correcting are one step on purpose: a correction that is stored
    but not applied leaves the wrong words on the screen, and one that is
    applied but not stored has to be typed again tomorrow.
    """
    meant = (meant or "").strip()
    if not meant:
        return None
    entries = dictionary.add(heard, meant)
    if not dictionary.save(entries):
        logger.warning("The correction was applied but could not be saved")
    return meant
