r"""Ctrl+Alt+Win: say what the words should have been.

The owner asked for this in so many words: mark the part that came out wrong,
type the right version over it, and stop having to do it again. What it can
and cannot teach is in `dictionary.py`; this is the gesture.

Four things about it are deliberate.

**It is the pill's twin.** The same glass, a cross on the left and a tick on
the right, and a field to type into where the waveform would be, with a ring
of the waveform's colours running round it - all drawn by `glass.composer`
out of the code the pill is drawn with. It is two windows laid one over the
other. The glass is a layered window with a real alpha channel, like the
pill: never focused, and clicked through wherever it is transparent. The
field is an ordinary window placed exactly over the field in the picture,
because a window drawn with UpdateLayeredWindow cannot show a child widget,
and a field nobody can type into is not a field.

**It takes the selection through the clipboard**, because there is no way to
read another program's selection directly, and it puts the clipboard back
afterwards. Nothing is sent until Ctrl and Alt are up: a Ctrl+C on top of a
held Ctrl+Alt is Ctrl+Alt+C in the window in front, which is somebody else's
shortcut.

**The field takes focus, and neither the pill nor this glass ever does.**
Dictation has to be invisible or it is not worth having, so the pill is
`WS_EX_NOACTIVATE` and never steals the caret. Correcting a word is a
deliberate stop-and-type, and a box you cannot type into is useless. The
window in front is remembered before the box opens and put back afterwards,
so the corrected text lands where the wrong text was.

**Nothing is saved on an empty answer or on Escape.** A dictionary is only
worth trusting if every entry in it was typed on purpose. Enter on an empty
field shakes the capsule instead of closing it, so it is plain that nothing
happened.
"""

import ctypes
import logging
import math
import threading
import time
import tkinter as tk
from ctypes import wintypes

from . import dictionary, glass, keymap, overlay, theme

logger = logging.getLogger("heyspeaky.correct")

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL

# Moved this far before it counts as a drag rather than a click that wobbled.
DRAG_SLOP = 3
# A frame every 16 ms while anything moves, and none at all once it is still:
# a box left open for a minute costs nothing.
TICK_MS = 16
# Where the ring's two arcs start, a little way along from the corners.
TURN_START = 0.12
# How long focus has to stay away before the box believes it has gone. A
# click on the glass takes it for a moment and gives it back.
FOCUS_GRACE_MS = 150
# What the field says when nothing was selected.
PLACEHOLDER = "A word to remember"
# Keys that change nothing in the field, so they do not nudge the ring.
_QUIET_KEYS = {
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    "Win_L", "Win_R", "Super_L", "Super_R", "Meta_L", "Meta_R", "Caps_Lock",
    "Num_Lock", "Scroll_Lock", "Left", "Right", "Up", "Down", "Home", "End",
}


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


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def _ease_out(share):
    """Fast, then settling: how things arrive."""
    share = _clamp(share)
    return 1.0 - (1.0 - share) ** 3


def _approach(value, target, rate):
    """One frame's step of something easing towards where it is going."""
    if abs(target - value) < 0.002:
        return target
    return value + (target - value) * rate


def _shortened(text, limit=34):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + u"…"


class CorrectionBox(object):
    """Asks what the selected words should have been.

    Built on the app's existing Tk root as two Toplevels, because a second Tk
    instance in one process is a way to hang the interpreter, and because
    everything here has to run on the thread that owns the root anyway.

    `back` is the glass, `top` the field laid over it; every size both of
    them use comes from `glass.composer_layout`, once.
    """

    def __init__(self, root, heard, on_done, scale=1.0, look="glass"):
        self._root = root
        self._on_done = on_done
        self._answered = False
        self._destroyed = False
        self.heard = heard or ""
        self.scale = max(0.5, float(scale))
        # The mono look draws it black, with a blue focus ring.
        self._mono = look == "mono"
        self._composer = glass.composer(self.scale, mono=self._mono)
        self.layout = self._composer.layout
        self._surface = overlay.Surface()
        self._hwnd = 0
        self._job = None

        now = time.monotonic()
        self._opened_at = now
        self._revealed_at = None
        self._done_at = None
        self._closing_at = None
        self._shake_at = None
        self._flare = (now, theme.GLOW_FLARE)
        self._nudge = 0.0
        self._nudge_target = 0.0
        self._field_alpha = 0.0
        self._heard_alpha = 0.0
        self._hover = None
        self._hover_at = now
        self._pressed = None
        self._motion = dict(
            (name, {"grow": 1.0, "turn": 0.0, "lift": 0.0, "tip": 0.0})
            for name in ("cancel", "accept"))
        self._snapshot = ""
        self._placeholder = False
        self._position = (0, 0)
        self._shown_at = None
        self._bounds = None
        self._drag_from = None
        self._dragged = False

        self._chips = {
            "heard": glass.chip(
                [("heard  ", True), (_shortened(self.heard), False)]
                if self.heard else
                [("nothing selected  ", True), ("type a word to keep", False)],
                self.scale, self._mono),
            "cancel": glass.chip([("Close", False), ("  Esc", True)],
                                 self.scale, self._mono),
            "accept": glass.chip([("Save", False), ("  Enter", True)],
                                 self.scale, self._mono),
        }

        # The glass: layered, never focused, clicked through wherever it is
        # transparent - the pill's kind of window.
        self.back = tk.Toplevel(root)
        self.back.withdraw()
        self.back.title("HeySpeaky")
        self.back.overrideredirect(True)
        self.back.configure(bg="#000000")
        self.back.attributes("-topmost", True)
        for sequence, handler in (("<Button-1>", self._grab),
                                  ("<B1-Motion>", self._drag),
                                  ("<ButtonRelease-1>", self._drop),
                                  ("<Motion>", self._hovered),
                                  # The first move onto the glass arrives
                                  # as Enter alone, with no Motion after it
                                  # until the pointer moves again.
                                  ("<Enter>", self._hovered),
                                  ("<Leave>", self._left)):
            self.back.bind(sequence, handler)

        # The field: an ordinary window, because it has to take the keyboard.
        self.top = tk.Toplevel(root)
        self.top.withdraw()
        self.top.title("HeySpeaky")
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg=_rgb(glass.field_fill(self._mono)))
        # Invisible while the glass opens, but already holding the keyboard:
        # a word typed in that first third of a second must not land in the
        # window behind. An ordinary window may have -alpha; the glass never.
        self.top.attributes("-alpha", 0.0)
        size = max(9, int(round(theme.FIELD_TEXT * self.scale)))
        self.entry = tk.Entry(
            self.top, bg=_rgb(glass.field_fill(self._mono)),
            fg=_rgb(theme.TEXT_LIGHT),
            insertbackground=_rgb(theme.TEXT_LIGHT),
            selectbackground=_rgb(theme.MONO_ACCENT if self._mono
                                  else theme.SELECT_FILL),
            selectforeground=_rgb(theme.TEXT_LIGHT),
            relief="flat", bd=0, highlightthickness=0,
            insertwidth=max(1, int(round(2 * self.scale))),
            font=("Segoe UI", -size))
        self.entry.pack(fill="both", expand=True)
        if self.heard:
            self.entry.insert(0, self.heard)
            self.entry.select_range(0, "end")
            self.entry.icursor("end")
        else:
            self._show_placeholder()

        for sequence in ("<Return>", "<KP_Enter>"):
            self.entry.bind(sequence, self._accept)
        self.entry.bind("<Escape>", self._cancel)
        self.entry.bind("<Key>", self._typed)
        # After _typed, which has already turned the ring for this key:
        # Tk decodes Kazakh wrongly, and this types what the layout meant.
        keymap.fix_typing(self.entry)
        # Clicking away is the third way people close a box like this, and
        # leaving it floating over everything when they do is the fastest way
        # to make somebody hate a feature.
        self.top.bind("<FocusOut>", self._focus_left)

        self._place()
        self.back.deiconify()
        self.back.attributes("-topmost", True)
        self._hwnd = overlay.window_handle(self.back)
        overlay.layered_styles(self._hwnd)
        self._paint(now)
        self.top.deiconify()
        self.top.lift()
        self.top.focus_force()
        self.entry.focus_set()
        self._schedule()

    # -- the text ----------------------------------------------------------

    def _show_placeholder(self):
        self._placeholder = True
        self.entry.configure(fg=_rgb(_muted(theme.TEXT_LIGHT, 0.42)))
        self.entry.insert(0, PLACEHOLDER)
        self.entry.icursor(0)

    def _clear_placeholder(self):
        if not self._placeholder:
            return
        self._placeholder = False
        self.entry.delete(0, "end")
        self.entry.configure(fg=_rgb(theme.TEXT_LIGHT))

    def _text(self):
        return "" if self._placeholder else self.entry.get()

    def _typed(self, event):
        """Every key into the field turns the ring a little, and brightens it.

        The field answers the hand that types into it, which is most of what
        makes it feel alive; a key that changes nothing does nothing.
        """
        keysym = getattr(event, "keysym", "") or ""
        char = getattr(event, "char", "") or ""
        if keysym in _QUIET_KEYS:
            return None
        if self._placeholder:
            if keysym in ("BackSpace", "Delete"):
                self._clear_placeholder()
                return "break"
            if not (char and char.isprintable()):
                return None
            self._clear_placeholder()
        if char or keysym in ("BackSpace", "Delete"):
            now = time.monotonic()
            self._nudge_target += theme.GLOW_NUDGE / 360.0
            self._flare = (now, max(self._strength(now), 0.92))
            self._schedule()
        return None

    # -- motion ------------------------------------------------------------

    def _px(self, value):
        return max(1, int(round(value * self.scale)))

    def _shape(self, now):
        """How open, how visible and how far from its place the glass is."""
        share = _clamp((now - self._opened_at) / theme.COMPOSER_OPEN)
        grown = 0.3 + 0.7 * _ease_out(share)
        opacity = _clamp(share * 2.2)
        slide = theme.COMPOSER_SLIDE * self.scale * (1.0 - _ease_out(share))
        if self._closing_at is not None:
            gone = _clamp((now - self._closing_at) / theme.COMPOSER_CLOSE)
            grown = min(grown, 1.0 - 0.45 * gone * gone)
            opacity *= 1.0 - gone
        return grown, opacity, slide

    def _turn(self, now):
        """How far round the ring has gone: one turn as it opens, and a
        little more for every key since."""
        if self._revealed_at is None:
            return TURN_START
        sweep = _ease_out((now - self._revealed_at) / theme.GLOW_SWEEP)
        return TURN_START + sweep + self._nudge

    def _strength(self, now):
        """Bright as it opens, as it saves and as you type; settling after."""
        at, peak = self._flare
        settled = theme.GLOW_SETTLED
        return settled + (peak - settled) * math.exp(-(now - at) / 0.5)

    def _advance(self, now):
        """Moves everything on by one frame. Returns whether anything moves."""
        busy = False
        opened = now - self._opened_at >= theme.COMPOSER_OPEN
        if not opened:
            busy = True
        elif self._revealed_at is None:
            self._revealed_at = now
            self._flare = (now, theme.GLOW_FLARE)
            busy = True

        if self._revealed_at is not None and not self._answered:
            if self._field_alpha < 1.0:
                self._field_alpha = min(1.0, self._field_alpha + 0.34)
                try:
                    self.top.attributes("-alpha", self._field_alpha)
                except tk.TclError:
                    pass
                busy = True
            self._heard_alpha = _approach(self._heard_alpha, 1.0, 0.22)
            busy = busy or self._heard_alpha < 1.0
            if now - self._revealed_at < theme.GLOW_SWEEP:
                busy = True

        if self._strength(now) - theme.GLOW_SETTLED > 0.004:
            busy = True
        self._nudge = _approach(self._nudge, self._nudge_target, 0.16)
        busy = busy or self._nudge != self._nudge_target

        for name, motion in self._motion.items():
            hovered = self._hover == name and not self._answered
            pressed = hovered and self._pressed == name
            grow = (theme.PRESS_SHRINK if pressed else
                    theme.HOVER_GROW if hovered else 1.0)
            if name == "accept" and self._done_at is not None:
                # The tick goes green and pops, the way the pill's does.
                grow = 1.0 + 0.22 * math.exp(-(now - self._done_at) / 0.12)
            waiting = hovered and now - self._hover_at < theme.TIP_DELAY
            targets = {
                "grow": grow,
                "turn": theme.HOVER_TURN if hovered and name == "cancel"
                else 0.0,
                "lift": theme.HOVER_LIFT * self.scale
                if hovered and name == "accept" else 0.0,
                "tip": 1.0 if hovered and not waiting else 0.0,
            }
            for key, target in targets.items():
                rate = 0.25 if key == "turn" else 0.34
                motion[key] = _approach(motion[key], target, rate)
                busy = busy or motion[key] != target
            busy = busy or waiting

        shift = (0.0, 0.0)
        grown, _opacity, slide = self._shape(now)
        if self._shake_at is not None:
            spent = now - self._shake_at
            if spent < 0.45:
                shift = (theme.SHAKE * self.scale * math.sin(spent * 38.0)
                         * math.exp(-spent * 7.0), 0.0)
                busy = True
            else:
                self._shake_at = None
        if slide > 0.5:
            busy = True
        self._shift_to(shift[0], slide)

        if self._done_at is not None and self._closing_at is None:
            if now - self._done_at >= theme.COMPOSER_DONE_HOLD:
                self._closing_at = now
            busy = True
        if self._closing_at is not None:
            busy = True
        return busy

    def _frame(self, now):
        grown, opacity, _slide = self._shape(now)
        turn = self._turn(now)
        buttons = dict(
            (name, (motion["grow"],
                    int(round(motion["turn"] / 10.0)) * 10,
                    motion["lift"]))
            for name, motion in self._motion.items())
        chips = []
        box = self.layout["box"]
        gap = self._px(theme.CHIP_GAP)
        tips = max(self._motion["cancel"]["tip"], self._motion["accept"]["tip"])
        heard = self._chips["heard"]
        chips.append((heard, (box[0] + box[2]) / 2.0 - heard.size[0] / 2.0,
                      box[1] - gap - heard.size[1],
                      self._heard_alpha * (1.0 - 0.65 * tips)))
        for name in ("cancel", "accept"):
            tip = self._motion[name]["tip"]
            if tip <= 0.01:
                continue
            image = self._chips[name]
            button = self.layout["buttons"][name]
            rise = (1.0 - tip) * self._px(4)
            chips.append((image,
                          (button[0] + button[2]) / 2.0 - image.size[0] / 2.0,
                          box[1] - gap - image.size[1] + rise, tip))
        frame = glass.composer_frame(
            self._composer, open_share=grown, turn=turn,
            strength=self._strength(now), buttons=buttons,
            done=self._done_at is not None, chips=chips,
            text=self._snapshot if self._answered else "")
        return frame, opacity

    def _paint(self, now=None):
        now = time.monotonic() if now is None else now
        frame, opacity = self._frame(now)
        overlay.present(self._hwnd, self._surface, frame, opacity)

    def _tick(self):
        self._job = None
        if self._destroyed:
            return
        now = time.monotonic()
        try:
            busy = self._advance(now)
            if (self._closing_at is not None
                    and now - self._closing_at >= theme.COMPOSER_CLOSE):
                self._destroy()
                return
            self._paint(now)
        except Exception:
            logger.exception("The correction composer could not draw a frame")
            busy = False
        if busy:
            self._job = self.back.after(TICK_MS, self._tick)

    def _schedule(self):
        if self._job is None and not self._destroyed:
            try:
                self._job = self.back.after(TICK_MS, self._tick)
            except tk.TclError:
                self._job = None

    def _destroy(self):
        self._destroyed = True
        if self._job is not None:
            try:
                self.back.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        for window in (self.top, self.back):
            try:
                window.destroy()
            except tk.TclError:
                pass
        self._surface.close()

    def bring_forward(self):
        """Ctrl+Alt+Win again while this box is open lands here."""
        if self._answered or self._destroyed:
            return
        try:
            self.back.deiconify()
            self.back.lift()
            self.top.deiconify()
            self.top.lift()
            self.top.focus_force()
            self.entry.focus_set()
        except tk.TclError:
            return
        self._flare = (time.monotonic(), theme.GLOW_FLARE)
        self._schedule()

    # -- placing and dragging ---------------------------------------------

    def _place(self):
        """Just under the pointer, or just over it if there is no room below,
        and always wholly on the screen it is on."""
        self.back.update_idletasks()
        pointer_x = self.back.winfo_pointerx()
        pointer_y = self.back.winfo_pointery()
        self._bounds = overlay._cursor_work_area()
        box = self.layout["box"]
        x = pointer_x - (box[0] + box[2]) // 2
        y = pointer_y + self._px(40) - box[1]
        if y + box[3] > self._bounds[3] - 8:
            y = pointer_y - self._px(16) - box[3]
        self._move(x, y)

    def _move(self, x, y):
        box = self.layout["box"]
        left, top, right, bottom = self._bounds or (
            0, 0, self.back.winfo_screenwidth(),
            self.back.winfo_screenheight())
        chips = self._px(theme.CHIP_HEIGHT + theme.CHIP_GAP)
        x = max(left + 8 - box[0], min(int(x), right - 8 - box[2]))
        y = max(top + 8 + chips - box[1], min(int(y), bottom - 8 - box[3]))
        self._position = (x, y)
        self._shown_at = None
        self._shift_to(0.0, 0.0)

    def _shift_to(self, dx, dy):
        """Puts both windows where they belong, give or take a shake."""
        x = self._position[0] + int(round(dx))
        y = self._position[1] + int(round(dy))
        if self._shown_at == (x, y):
            return
        self._shown_at = (x, y)
        width, height = self.layout["window"]
        entry = self.layout["entry"]
        try:
            self.back.geometry("{}x{}+{}+{}".format(width, height, x, y))
            self.top.geometry("{}x{}+{}+{}".format(
                entry[2] - entry[0], entry[3] - entry[1],
                x + entry[0], y + entry[1]))
        except tk.TclError:
            pass

    def _button_at(self, x, y):
        slop = self._px(4)
        for name, box in self.layout["buttons"].items():
            if (box[0] - slop <= x <= box[2] + slop
                    and box[1] - slop <= y <= box[3] + slop):
                return name
        return None

    def _hovered(self, event):
        if self._answered:
            return
        name = self._button_at(event.x, event.y)
        if name != self._hover:
            self._hover = name
            self._hover_at = time.monotonic()
            try:
                self.back.configure(cursor="hand2" if name else "")
            except tk.TclError:
                pass
            self._schedule()

    def _left(self, _event=None):
        if self._hover is not None:
            self._hover = None
            try:
                self.back.configure(cursor="")
            except tk.TclError:
                pass
            self._schedule()

    def _grab(self, event):
        name = self._button_at(event.x, event.y)
        if name is not None and not self._answered:
            self._pressed = name
            self._hover = name
            self._schedule()
            return
        # Anywhere on the glass that is not a button is a handle. A box that
        # lands on top of the words you are trying to read is the one thing
        # that would make this worse than editing the file by hand.
        self._drag_from = (event.x_root - self._position[0],
                           event.y_root - self._position[1])
        self._dragged = False

    def _drag(self, event):
        if self._pressed is not None:
            self._hovered(event)
            return
        if self._drag_from is None:
            return
        x = event.x_root - self._drag_from[0]
        y = event.y_root - self._drag_from[1]
        if not self._dragged:
            moved = abs(x - self._position[0]) + abs(y - self._position[1])
            if moved < DRAG_SLOP:
                return
            self._dragged = True
        self._move(x, y)

    def _drop(self, event=None):
        pressed, self._pressed = self._pressed, None
        if pressed is not None:
            self._schedule()
            if event is not None and self._button_at(event.x,
                                                     event.y) == pressed:
                if pressed == "accept":
                    self._accept()
                else:
                    self._cancel()
            return
        self._drag_from = None
        # A click on the glass rather than a drag should still leave the
        # caret somewhere it can be typed at.
        if not self._dragged and not self._answered:
            self.entry.focus_set()

    # -- answering ---------------------------------------------------------

    def _focus_left(self, _event=None):
        """Closes the box when focus leaves it, and stays gone.

        Two kinds of FocusOut are not that. Tk reports one when focus moves
        to a widget inside the same window. And a real click on the glass -
        measured with tools/correction_check.py, which clicks it - takes
        focus away for a moment and gives it straight back: two FocusOuts,
        and a moment later the field is in front with the caret in it again.
        Acting on the first one shut the box under the click. So it looks
        again a little later, and only then decides.
        """
        if self._answered or self._destroyed:
            return
        try:
            self.back.after(FOCUS_GRACE_MS, self._focus_gone)
        except tk.TclError:
            pass

    def _focus_gone(self):
        if self._answered or self._destroyed:
            return
        try:
            if self.top.focus_get() is not None:
                return
            if _user32.GetForegroundWindow() == overlay.window_handle(
                    self.top):
                return
        except (tk.TclError, KeyError):
            pass
        self._cancel()

    def _accept(self, _event=None):
        if self._answered:
            return "break"
        text = self._text().strip()
        if not text:
            # Nothing to keep, and closing would look like it was kept.
            self._shake_at = time.monotonic()
            self._schedule()
            return "break"
        self._finish(text)
        return "break"

    def _cancel(self, _event=None):
        self._finish(None)
        return "break"

    def _finish(self, answer):
        if self._answered:
            return
        self._answered = True
        self._snapshot = self._text()
        self._hover = None
        self._pressed = None
        now = time.monotonic()
        if answer:
            self._done_at = now
            self._flare = (now, theme.GLOW_FLARE)
        else:
            self._closing_at = now
        # The field goes first, so focus can go back to where the text came
        # from; the glass finishes its own leaving on its own time.
        try:
            self.top.withdraw()
        except tk.TclError:
            pass
        self._schedule()
        try:
            self._on_done(answer)
        except Exception:
            logger.exception("The correction could not be handed on")


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
