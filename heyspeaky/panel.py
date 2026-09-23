r"""The tray panel: what a click on the tray icon opens.

The owner asked for one design across the whole app. The pill and the
correction composer were already one - the same glass, a grey cross, a white
tick - and the tray was a grey Windows menu with submenus in submenus, which
nothing can restyle: Windows draws it. So a click on the icon now opens this
instead, a card of the same glass, and the Windows menu is kept only as the
fallback if this cannot open.

Everything the menu did is here: start or stop, pin a language or let it
detect, add and remove languages, OpenAI or this laptop, pause Ctrl+Alt,
update, your words, settings, logs, a problem report, quit. The chosen thing
is white with dark ink, like the tick; everything else is the cross's grey;
the only colour is the waveform's gradient, on the pause switch when it is
on.

Unlike the pill it does take focus - it is a menu, and a menu has to hear
Escape and know when you have clicked away - but it is drawn the pill's way,
with a real alpha channel through UpdateLayeredWindow, so its corners and
shadow sit on the live desktop.
"""

import logging
import time
import tkinter as tk

from . import glass, overlay, theme

logger = logging.getLogger("heyspeaky.panel")

TICK_MS = 16
# How often the panel looks at the app's state while nothing moves, so a
# language added or a pause switched shows without waiting for the mouse.
IDLE_MS = 150
FOCUS_GRACE_MS = 150

# What stays open after a click and what closes: a switch you flip should be
# seen to flip; a row that opens something else is done with the panel.
STAYS_OPEN = ("pin:", "backend:", "pause", "lang:", "more-languages", "back")

_BACKENDS = (("OpenAI", "cloud"), ("This laptop", "local"))


class Item(object):
    """One laid-out part of the panel, in window pixels."""

    __slots__ = ("kind", "key", "label", "rect", "extra", "hint")

    def __init__(self, kind, key, label, rect, extra=None, hint=""):
        self.kind = kind
        self.key = key
        self.label = label
        self.rect = rect
        self.extra = extra
        self.hint = hint

    def __repr__(self):
        return "Item({!r}, {!r})".format(self.kind, self.key)


CLICKABLE = ("chip", "segmented", "switch", "row", "back", "language")


def layout(model, scale=1.0, page="main", scroll=0.0):
    """Lays the panel out: its card size, and every part in window pixels.

    `model` is what the tray knows - see `Tray.panel_model`. Arithmetic and
    text measuring only, so it can be checked anywhere.
    """
    def px(value):
        return int(round(value * scale))

    width = px(theme.PANEL_WIDTH)
    margin = px(theme.PANEL_MARGIN)
    pad = px(theme.PANEL_PAD)
    left, right = margin + pad, margin + width - pad
    row = px(theme.ROW_HEIGHT)
    items = []
    y = margin + pad

    def add(kind, key, label, height, extra=None, hint="", x0=None, x1=None):
        rect = (left if x0 is None else x0, y,
                right if x1 is None else x1, y + height)
        items.append(Item(kind, key, label, rect, extra, hint))
        return rect

    def gap(value=theme.SECTION_GAP):
        return px(value)

    names = model.get("names", {})

    if page == "languages":
        add("back", "back", "Languages", row)
        y += row + gap(4)
        add("hint", None, "Tick every language you speak.", px(16))
        y += px(16) + gap(8)
        top = y
        bottom = y + px(theme.LIST_HEIGHT)
        # Whole rows only: a row cut in half at the top is drawn as nothing,
        # and the list would open with a hole in it.
        offset = int(round(scroll / float(row))) * row
        cursor = top - offset
        for code in language_order(model):
            if cursor >= top - 1 and cursor + row <= bottom + 1:
                items.append(Item("language", "lang:" + code,
                                  names.get(code, code),
                                  (left, cursor, right - px(8), cursor + row),
                                  code in model.get("yours", ())))
            cursor += row
        reach = list_height(model, scale)
        if reach > 0:
            shown = px(theme.LIST_HEIGHT) / float(px(theme.LIST_HEIGHT) + reach)
            items.append(Item("scrollbar", None, "",
                              (right - px(3), top, right, bottom),
                              (shown, min(1.0, offset / reach))))
        y = bottom
        height = y - margin + pad
        return (width, height), items

    state = model.get("state", "ready")
    dot = {"busy": theme.BUSY_DOT, "paused": theme.PAUSED_DOT}.get(
        state, theme.READY_DOT)
    header = px(26)
    add("title", None, "HeySpeaky", header)
    add("status", None, model.get("status", ""), header, dot)
    y += header + gap(8)

    add("row", "dictate", "Start / stop dictation", row, hint="Ctrl+Alt")
    y += row + gap()

    add("label", None, "Language", px(14))
    y += px(14) + px(theme.LABEL_GAP)
    chip_height = px(theme.PANEL_CHIP_HEIGHT)
    chip_gap = px(theme.PANEL_CHIP_GAP)
    pinned = model.get("pinned", "")
    chips = [("pin:", "Auto", pinned == "")]
    chips += [("pin:" + code, names.get(code, code), pinned == code)
              for code in model.get("yours", ())]
    chips.append(("more-languages", "+", False))
    x = left
    for key, label, chosen in chips:
        chip_width = glass.panel_chip(label, chosen, scale).size[0]
        if x > left and x + chip_width > right:
            x = left
            y += chip_height + chip_gap
        items.append(Item("chip", key, label,
                          (x, y, x + chip_width, y + chip_height), chosen))
        x += chip_width + chip_gap
    y += chip_height + gap()

    add("label", None, "Transcribed by", px(14))
    y += px(14) + px(theme.LABEL_GAP)
    chosen = [value for _label, value in _BACKENDS].index(
        model.get("backend", "cloud")) \
        if model.get("backend", "cloud") in ("cloud", "local") else 0
    add("segmented", "backend", "", px(theme.SEGMENT_HEIGHT),
        ([label for label, _value in _BACKENDS], chosen))
    y += px(theme.SEGMENT_HEIGHT) + gap(6)

    add("switch", "pause", "Pause Ctrl+Alt", row, bool(model.get("paused")))
    y += row + gap(6)
    add("separator", None, "", gap(6))
    y += gap(6) + gap(4)

    if model.get("update"):
        add("row", "update", "Update to {}".format(model["update"]), row,
            "accent")
        y += row
    for key, label in (("words", "Your words"), ("settings", "Settings"),
                       ("logs", "Logs"), ("report", "Save a problem report")):
        add("row", key, label, row, "more" if key != "report" else None)
        y += row
    y += gap(4)
    add("separator", None, "", gap(6))
    y += gap(6) + gap(4)
    add("row", "quit", "Quit HeySpeaky", row)
    y += row
    usage = model.get("usage", "")
    if usage:
        y += gap(4)
        add("footer", None, usage, px(16))
        y += px(16)
    height = y - margin + pad
    return (width, height), items


def hit(items, x, y):
    """The clickable part under a point, and for the segmented control which
    of its choices, as an action key."""
    for item in items:
        if item.kind not in CLICKABLE:
            continue
        left, top, right, bottom = item.rect
        if left <= x < right and top <= y < bottom:
            if item.kind == "segmented":
                labels = item.extra[0]
                index = int((x - left) / float(right - left) * len(labels))
                index = max(0, min(len(labels) - 1, index))
                return item, "backend:" + _BACKENDS[index][1]
            return item, item.key
    return None, None


def language_order(model):
    """Yours first, in your order, so taking one off never means hunting
    through the alphabet; then everything else by name."""
    yours = [code for code in model.get("yours", ())]
    names = model.get("names", {})
    rest = sorted((code for code in model.get("catalog", ())
                   if code not in yours),
                  key=lambda code: names.get(code, code).lower())
    return yours + rest


def list_height(model, scale=1.0):
    """How far the language list scrolls."""
    row = int(round(theme.ROW_HEIGHT * scale))
    rows = len(language_order(model))
    return max(0.0, float(rows * row - int(round(theme.LIST_HEIGHT * scale))))


def _approach(value, target, rate):
    if abs(target - value) < 0.002:
        return target
    return value + (target - value) * rate


class TrayPanel(object):
    """The panel's window. One at a time; on the Tk thread, like all of them.

    `model` is a callable returning the tray's current state; `act` is
    called with an action key when something is clicked.
    """

    def __init__(self, root, model, act, scale=1.0, anchor=None,
                 on_closed=None):
        self._root = root
        self._model_source = model
        self._act = act
        self._on_closed = on_closed
        self.scale = max(0.5, float(scale))
        self._anchor = anchor
        self._page = "main"
        self._scroll = 0.0
        self._hover_key = None
        self._hover = {}
        self._motion = {}
        self._opened_at = time.monotonic()
        self._closing_at = None
        self._closed = False
        self._job = None
        self._idle_job = None
        self._surface = overlay.Surface()
        self._placed_above = True
        self._position = (0, 0)

        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title("HeySpeaky")
        self.window.overrideredirect(True)
        self.window.configure(bg="#000000")
        self.window.attributes("-topmost", True)
        for sequence, handler in (("<Motion>", self._pointed),
                                  ("<Enter>", self._pointed),
                                  ("<Leave>", self._left),
                                  ("<ButtonRelease-1>", self._clicked),
                                  ("<MouseWheel>", self._wheel),
                                  ("<Escape>", self.close),
                                  ("<FocusOut>", self._focus_left)):
            self.window.bind(sequence, handler)

        self._model = self._model_source()
        self._relayout()
        self._place()
        self.window.deiconify()
        self.window.attributes("-topmost", True)
        # Tk finishes making the window at idle time, and the handle it
        # reports before that is not the one that ends up on the screen:
        # measured, the styles went onto one handle and the panel showed on
        # another, without them, and nothing was drawn. So wait for it.
        self.window.update_idletasks()
        self._hwnd = 0
        self._paint()
        self.window.lift()
        self.window.focus_force()
        self._schedule()
        self._idle_job = self.window.after(IDLE_MS, self._watch)

    # -- layout ------------------------------------------------------------

    def _relayout(self):
        self._size, self._items = layout(self._model, self.scale, self._page,
                                         self._scroll)
        self._card = glass.panel_card(self._size[0], self._size[1],
                                      self.scale)
        for item in self._items:
            if item.kind == "segmented":
                self._motion.setdefault(item.key, float(item.extra[1]))
            elif item.kind == "switch":
                self._motion.setdefault(item.key,
                                        1.0 if item.extra else 0.0)

    def _place(self):
        """Over the tray, or under it if the taskbar is at the top."""
        window = self._card[0].size
        margin = int(round(theme.PANEL_MARGIN * self.scale))
        left, top, right, bottom = overlay._cursor_work_area()
        if self._anchor is None:
            anchor = (right, bottom)
        else:
            anchor = self._anchor
        self._placed_above = anchor[1] > (top + bottom) / 2.0
        x = anchor[0] - window[0] // 2
        x = max(left + 8 - margin, min(x, right - 8 - window[0] + margin))
        if self._placed_above:
            y = bottom - 8 - window[1] + margin
        else:
            y = top + 8 - margin
        self._position = (x, y)
        self._move(0.0)

    def _move(self, slide):
        width, height = self._card[0].size
        y = self._position[1] + int(round(slide if self._placed_above
                                          else -slide))
        try:
            self.window.geometry("{}x{}+{}+{}".format(
                width, height, self._position[0], y))
        except tk.TclError:
            pass

    # -- drawing and motion ------------------------------------------------

    def _shape(self, now):
        share = min(1.0, (now - self._opened_at) / theme.PANEL_OPEN)
        eased = 1.0 - (1.0 - share) ** 3
        opacity = eased
        slide = 8 * self.scale * (1.0 - eased)
        if self._closing_at is not None:
            gone = min(1.0, (now - self._closing_at) / theme.PANEL_CLOSE)
            opacity *= 1.0 - gone
            slide += 4 * self.scale * gone
        return opacity, slide, share < 1.0

    def _advance(self, now):
        busy = False
        for item in self._items:
            if item.key is None or item.kind not in CLICKABLE:
                continue
            target = 1.0 if item.key == self._hover_key else 0.0
            value = _approach(self._hover.get(item.key, 0.0), target, 0.3)
            self._hover[item.key] = value
            busy = busy or value != target
            if item.kind == "segmented":
                value = _approach(self._motion.get(item.key, 0.0),
                                  float(item.extra[1]), 0.28)
                self._motion[item.key] = value
                busy = busy or value != float(item.extra[1])
            elif item.kind == "switch":
                goal = 1.0 if item.extra else 0.0
                value = _approach(self._motion.get(item.key, goal), goal,
                                  0.28)
                self._motion[item.key] = value
                busy = busy or value != goal
        return busy

    def _handle(self):
        """The window's handle, styled - again, if Tk has made a new one."""
        hwnd = overlay.window_handle(self.window)
        if hwnd and hwnd != self._hwnd:
            overlay.layered_styles(hwnd, focusable=True)
            self._hwnd = hwnd
        return self._hwnd

    def _paint(self, now=None):
        now = time.monotonic() if now is None else now
        opacity, slide, _opening = self._shape(now)
        self._move(slide)
        self._handle()
        frame = glass.panel_frame(self._card, self._items, self.scale,
                                  self._hover, self._motion)
        overlay.present(self._hwnd, self._surface, frame, opacity)

    def _tick(self):
        self._job = None
        if self._closed:
            return
        now = time.monotonic()
        try:
            busy = self._advance(now)
            _opacity, _slide, opening = self._shape(now)
            if (self._closing_at is not None
                    and now - self._closing_at >= theme.PANEL_CLOSE):
                self._destroy()
                return
            self._paint(now)
            busy = busy or opening or self._closing_at is not None
        except Exception:
            logger.exception("The tray panel could not draw a frame")
            busy = False
        if busy:
            self._job = self.window.after(TICK_MS, self._tick)

    def _schedule(self):
        if self._job is None and not self._closed:
            try:
                self._job = self.window.after(TICK_MS, self._tick)
            except tk.TclError:
                self._job = None

    def _watch(self):
        """Picks up changes made elsewhere: a pause, a language, an update."""
        self._idle_job = None
        if self._closed or self._closing_at is not None:
            return
        try:
            fresh = self._model_source()
        except Exception:
            logger.exception("The tray panel could not read the app's state")
            fresh = self._model
        if fresh != self._model:
            self._model = fresh
            self._refit()
        self._idle_job = self.window.after(IDLE_MS, self._watch)

    def _refit(self):
        size = self._size
        self._relayout()
        if self._size != size:
            self._place()
        self._schedule()

    # -- the pointer -------------------------------------------------------

    def _pointed(self, event):
        item, _action = hit(self._items, event.x, event.y)
        key = item.key if item is not None else None
        if key != self._hover_key:
            self._hover_key = key
            try:
                self.window.configure(cursor="hand2" if key else "")
            except tk.TclError:
                pass
            self._schedule()

    def _left(self, _event=None):
        if self._hover_key is not None:
            self._hover_key = None
            self._schedule()

    def _wheel(self, event):
        if self._page != "languages":
            return
        step = 2 * int(round(theme.ROW_HEIGHT * self.scale))
        delta = -step if getattr(event, "delta", 0) > 0 else step
        self._scroll = max(0.0, min(list_height(self._model, self.scale),
                                    self._scroll + delta))
        self._refit()

    def _clicked(self, event):
        if self._closing_at is not None:
            return
        _item, action = hit(self._items, event.x, event.y)
        if action is None:
            return
        self.press(action)

    def press(self, action):
        """Does what a click on `action` does. Public, for the live check."""
        if action == "more-languages":
            self._page, self._scroll = "languages", 0.0
            self._hover_key = None
            self._refit()
            return
        if action == "back":
            self._page = "main"
            self._hover_key = None
            self._refit()
            return
        try:
            self._act(action)
        except Exception:
            logger.exception("The tray panel could not do %s", action)
        if action.startswith(STAYS_OPEN):
            # The app changes its state on its own thread; look again soon.
            self.window.after(60, self._watch_once)
        else:
            self.close()

    def _watch_once(self):
        if self._closed:
            return
        try:
            fresh = self._model_source()
        except Exception:
            return
        if fresh != self._model:
            self._model = fresh
            self._refit()

    # -- closing -----------------------------------------------------------

    def _focus_left(self, _event=None):
        if self._closing_at is None and not self._closed:
            try:
                self.window.after(FOCUS_GRACE_MS, self._focus_gone)
            except tk.TclError:
                pass

    def _focus_gone(self):
        if self._closed or self._closing_at is not None:
            return
        try:
            if self.window.focus_get() is not None:
                return
        except (tk.TclError, KeyError):
            pass
        self.close()

    def close(self, _event=None):
        if self._closing_at is not None or self._closed:
            return
        self._closing_at = time.monotonic()
        self._hover_key = None
        self._schedule()

    @property
    def open(self):
        return not self._closed and self._closing_at is None

    def _destroy(self):
        self._closed = True
        for job in (self._job, self._idle_job):
            if job is not None:
                try:
                    self.window.after_cancel(job)
                except tk.TclError:
                    pass
        try:
            self.window.destroy()
        except tk.TclError:
            pass
        self._surface.close()
        if self._on_closed is not None:
            try:
                self._on_closed(self)
            except Exception:
                logger.exception("The tray panel's close callback failed")


def pointer_position():
    """Where the pointer is, in screen pixels: where the tray icon was
    clicked, which is where the panel should appear."""
    import ctypes

    class _Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    point = _Point()
    try:
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    except Exception:
        return None
    return (point.x, point.y)

