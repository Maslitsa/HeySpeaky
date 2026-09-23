r"""Ctrl+Alt+Win: say what the words should have been.

The owner asked for this in so many words: mark the part that came out wrong,
type the right version over it, and stop having to do it again. What it can
and cannot teach is in `dictionary.py`; this is the gesture.

Four things about it are deliberate.

**It is made of the pill's materials.** The tint, the bright edge along the
top, the specular inside it, and the waveform's own colours as a line under
the field - `glass.card` builds all of that out of the code the capsule is
drawn with. The one thing it does not share is transparency: the pill is a
layered window with a real alpha channel, and this one has to host a text
field, so its corners are clipped by a region and the whole window is made
slightly translucent at once.

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
import threading
import time
import tkinter as tk
from ctypes import wintypes

from PIL import ImageTk

from . import dictionary, glass, theme

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

# Moved this far before it counts as a drag rather than a click that wobbled.
DRAG_SLOP = 3


def _round_corners(window, width, height, radius):
    """Clips a Tk window to rounded corners.

    Windows 10 does not round a window with no frame, and an
    `overrideredirect` box is exactly that, so without this it comes out as a
    hard rectangle next to a pill that is all curves. Windows owns the region
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


class OneAtATime(object):
    """One correction from the key press until its box closes.

    The owner's log, 22 September: the correction key asked for twice a second
    apart, then two boxes cancelled in the same millisecond - one on top of
    the other, twice that night. The key pressed again inside a held chord is a
    fresh key-down, not a repeat, so the hotkey never had a reason to ignore
    it. Two corrections at once also means two threads borrowing the
    clipboard at once, each putting back what the other took.

    The claim is taken on the key press, not when the box appears, because the
    box only appears once Ctrl and Alt are up: the second press lands in the
    gap before it.
    """

    # Reading the selection is the one step with no box on screen, and it
    # gives up after the modifier timeout plus a moment for the clipboard. A
    # claim older than this that never produced a box was lost on the way,
    # and must not leave Ctrl+Alt+Win dead until the app is restarted.
    STALE = 15.0

    def __init__(self):
        self._lock = threading.Lock()
        self._since = None
        self.box = None

    def begin(self, now=None):
        """True if this press may start a correction."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._since is not None:
                if self.box is not None or now - self._since < self.STALE:
                    return False
                logger.warning("A correction never opened its box; "
                               "starting a new one")
            self._since = now
            self.box = None
            return True

    def opened(self, box):
        with self._lock:
            if self._since is not None:
                self.box = box

    def end(self):
        with self._lock:
            self._since = None
            self.box = None


def _rgb(colour):
    return "#{:02x}{:02x}{:02x}".format(*colour)


def _muted(colour, strength=theme.MUTED_STRENGTH):
    """A dimmer version of a colour, the way the pill dims its labels."""
    return tuple(int(round(channel * strength)) for channel in colour)


class CorrectionBox(object):
    """Asks what the selected words should have been.

    Built on the app's existing Tk root as a Toplevel, because a second Tk
    instance in one process is a way to hang the interpreter, and because
    everything here has to run on the thread that owns the root anyway.

    The background is one image from `glass.card`, with the text field placed
    over the well that image already has sunk into it. Laying the same thing
    out twice - once in pixels for the picture, once in widgets - is why every
    size below is computed once and used by both.
    """

    def __init__(self, root, heard, on_done, scale=1.0):
        self._on_done = on_done
        self._answered = False
        self._drag_from = None
        self._dragged = False

        self.scale = max(0.5, float(scale))
        pad = self._px(theme.BOX_PAD)
        gap = self._px(theme.BOX_GAP)
        self.width = self._px(theme.BOX_WIDTH)

        title = ("What should it have said?" if heard
                 else "A word to remember")
        under = ("heard: " + heard if heard else
                 "Nothing was selected. Type a word to declare it.")

        line = self._px(theme.FONT_SIZE) + self._px(6)
        small = self._px(theme.LABEL_SIZE) + self._px(6)
        well_height = self._px(theme.WELL_HEIGHT)

        title_y = pad
        under_y = title_y + line + self._px(2)
        well_y = under_y + small + gap
        hint_y = well_y + well_height + gap
        self.height = hint_y + small + pad
        self.well = (pad, well_y, self.width - pad, well_y + well_height)

        self.top = tk.Toplevel(root)
        self.top.withdraw()
        self.top.title("HeySpeaky")
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        # One value for the whole window, which an ordinary window is allowed
        # to have. The pill must never be given one: see overlay.py.
        self.top.attributes("-alpha", theme.BOX_ALPHA)
        self.top.configure(bg=_rgb(theme.TINT))

        self.canvas = tk.Canvas(self.top, width=self.width,
                                height=self.height, highlightthickness=0,
                                bd=0, bg=_rgb(theme.TINT))
        self.canvas.pack(fill="both", expand=True)
        self._background = ImageTk.PhotoImage(
            glass.card(self.width, self.height, self.well, self.scale))
        self.canvas.create_image(0, 0, image=self._background, anchor="nw")

        self.canvas.create_text(
            pad, title_y, text=title, anchor="nw",
            fill=_rgb(theme.TEXT_LIGHT),
            font=("Segoe UI Semibold", theme.FONT_SIZE))
        self.canvas.create_text(
            pad, under_y, text=under, anchor="nw",
            fill=_rgb(_muted(theme.TEXT_LIGHT)),
            font=("Segoe UI", theme.LABEL_SIZE))
        self.canvas.create_text(
            pad, hint_y,
            text="Enter saves it · Esc leaves it · drag to move",
            anchor="nw", fill=_rgb(_muted(theme.TEXT_LIGHT, 0.5)),
            font=("Segoe UI", theme.LABEL_SIZE))

        self.entry = tk.Entry(
            self.canvas, bg=_rgb(theme.WELL_FILL), fg=_rgb(theme.TEXT_LIGHT),
            insertbackground=_rgb(theme.TEXT_LIGHT), relief="flat", bd=0,
            highlightthickness=0,
            font=("Segoe UI", theme.FONT_SIZE + 1))
        inset = self._px(10)
        self.canvas.create_window(
            self.well[0] + inset, (self.well[1] + self.well[3]) // 2,
            window=self.entry, anchor="w",
            width=self.well[2] - self.well[0] - inset * 2,
            height=well_height - self._px(theme.WELL_ACCENT) - self._px(6))
        self.entry.insert(0, heard)
        self.entry.select_range(0, "end")

        for widget in (self.top, self.entry, self.canvas):
            widget.bind("<Return>", self._accept)
            widget.bind("<KP_Enter>", self._accept)
            widget.bind("<Escape>", self._cancel)
        # Anywhere on the card that is not the field is a handle. A box that
        # lands on top of the words you are trying to read is the one thing
        # that would make this worse than editing the file by hand.
        self.canvas.bind("<Button-1>", self._grab)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._drop)
        # Clicking away is the third way people close a box like this, and
        # leaving it floating over everything when they do is the fastest way
        # to make somebody hate a feature.
        self.top.bind("<FocusOut>", self._focus_left)

        self._place()
        self.top.deiconify()
        self.top.lift()
        self.top.focus_force()
        self.entry.focus_set()

    def _px(self, value):
        return max(1, int(round(value * self.scale)))

    def bring_forward(self):
        """Ctrl+Alt+Win again while this box is open lands here."""
        try:
            self.top.deiconify()
            self.top.lift()
            self.top.focus_force()
            self.entry.focus_set()
        except tk.TclError:
            pass

    # -- placing and dragging ---------------------------------------------

    def _place(self):
        """Near the pointer, and always fully on the screen it is on."""
        self.top.update_idletasks()
        self._move(self.top.winfo_pointerx() - self.width // 2,
                   self.top.winfo_pointery() + self._px(24))

    def _move(self, x, y):
        limit_x = self.top.winfo_screenwidth() - self.width - 8
        limit_y = self.top.winfo_screenheight() - self.height - 8
        x = max(8, min(int(x), max(8, limit_x)))
        y = max(8, min(int(y), max(8, limit_y)))
        self.top.geometry("{}x{}+{}+{}".format(self.width, self.height, x, y))
        self.top.update_idletasks()
        _round_corners(self.top, self.width, self.height,
                       self._px(theme.BOX_RADIUS))

    def _grab(self, event):
        self._drag_from = (event.x_root - self.top.winfo_x(),
                           event.y_root - self.top.winfo_y())
        self._dragged = False

    def _drag(self, event):
        if self._drag_from is None:
            return
        x = event.x_root - self._drag_from[0]
        y = event.y_root - self._drag_from[1]
        if not self._dragged:
            moved = abs(x - self.top.winfo_x()) + abs(y - self.top.winfo_y())
            if moved < DRAG_SLOP:
                return
            self._dragged = True
        self._move(x, y)

    def _drop(self, _event=None):
        self._drag_from = None
        # A click on the card rather than a drag should still leave the caret
        # somewhere it can be typed at.
        if not self._dragged:
            self.entry.focus_set()

    # -- answering ---------------------------------------------------------

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
