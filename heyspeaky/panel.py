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

Added for the owner since: the OpenAI key - click the row, paste the key
into the field that opens, Save (`apikey.py`); the model this laptop uses,
each with its size and what it costs in speed (`localmodels.py`); and
typing - on the first page whatever is typed goes into a search at the top
of the language list, because scrolling ninety names is the slow way.

Quit asks twice. The panel opens right over the tray, so the bottom row is
the first thing the pointer meets on its way up, and that row was Quit.

Unlike the pill it does take focus - it is a menu, and a menu has to hear
Escape and know when you have clicked away - but it is drawn the pill's way,
with a real alpha channel through UpdateLayeredWindow, so its corners and
shadow sit on the live desktop.
"""

import logging
import time
import tkinter as tk

from . import glass, keymap, languages, localmodels, overlay, theme

logger = logging.getLogger("heyspeaky.panel")

TICK_MS = 16
# How often the panel looks at the app's state while nothing moves, so a
# language added or a pause switched shows without waiting for the mouse.
IDLE_MS = 150
FOCUS_GRACE_MS = 150

# What stays open after a click and what closes: a switch you flip should be
# seen to flip; a row that opens something else is done with the panel.
STAYS_OPEN = ("pin:", "backend:", "pause", "lang:", "more-languages", "back",
              "model:", "look:")

SEARCH_PROMPT = "Type a language"

KEY_PROMPT = "Paste your key here"

# What the key row on the first page says, by the state `apikey.KeyFlow` is
# in: its label, the hint on its right, and whether it asks to be noticed.
# Until there is a key it comes first, in the accent colour.
KEY_ROWS = {
    "missing": ("Add your OpenAI key", "", "accent"),
    "invalid": ("Add your OpenAI key", "", "accent"),
    "refused": ("Add your OpenAI key", "refused", "accent"),
    "checking": ("Checking the key", "a moment", "accent"),
    "offline": ("OpenAI key", "saved", None),
    "done": ("OpenAI key", "saved", None),
    "saved": ("OpenAI key", "saved", None),
}

# The line under the key field, by the same state.
KEY_HINTS = {
    "missing": "Ctrl+V to paste it, then Save.",
    "saved": "A key is saved. Paste a new one to replace it.",
    "invalid": "That is not an OpenAI key. Those start with sk-.",
    "checking": "Checking it with OpenAI...",
    "refused": "OpenAI refused that key. Nothing was changed.",
    "offline": "Saved. OpenAI could not be reached to check it.",
    "done": "Saved. HeySpeaky uses it from now on.",
}


def mask(key):
    """A key as the field shows it: enough to recognise, never enough to
    use - and never the whole thing on the screen of someone presenting."""
    key = key or ""
    if len(key) <= 12:
        return "\u2022" * len(key)
    return key[:7] + "\u2022" * 8 + key[-4:]

_BACKENDS = (("OpenAI", "cloud"), ("This laptop", "local"))
# The pill's two looks: the glass, and mono - the black pill from the reel.
_LOOKS = (("Glass", "glass"), ("Mono", "mono"))


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


CLICKABLE = ("chip", "segmented", "switch", "row", "back", "language",
             "button", "model")


def layout(model, scale=1.0, page="main", scroll=0.0, query="",
           quit_armed=False, key_text=""):
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
    key_state = model.get("key", "saved")

    if page == "key":
        add("back", "back", "OpenAI key", row)
        y += row + gap(6)
        add("keyfield", "keyfield", mask(key_text), px(theme.SEARCH_HEIGHT),
            KEY_PROMPT)
        y += px(theme.SEARCH_HEIGHT) + gap(8)
        add("hint", None, KEY_HINTS.get(key_state, KEY_HINTS["missing"]),
            px(16))
        y += px(16) + gap(10)
        add("button", "key-save", "Save", px(theme.PANEL_CHIP_HEIGHT + 4),
            bool(key_text.strip()) and key_state != "checking")
        y += px(theme.PANEL_CHIP_HEIGHT + 4) + gap(8)
        add("row", "key-page", "Get a key from OpenAI", row, "more")
        y += row
        return (width, y - margin + pad), items

    if page == "models":
        local = model.get("local") or {}
        add("back", "back", "Model on this laptop", row)
        y += row + gap(4)
        add("hint", None, "Bigger hears better, but is slower and heavier.",
            px(16))
        y += px(16) + gap(8)
        tall = px(theme.MODEL_ROW_HEIGHT)
        for name, label, megabytes, note in localmodels.MODELS:
            if local.get("busy") == name:
                right_text = "downloading {:.0f}%".format(
                    100 * float(local.get("progress") or 0.0))
            elif local.get("failed") == name:
                right_text = "download failed"
            elif (local.get("have") or {}).get(name):
                right_text = "downloaded"
            else:
                right_text = localmodels.size_text(megabytes)
            add("model", "model:" + name, label, tall,
                (local.get("current") == name, right_text), note)
            y += tall
        return (width, y - margin + pad), items

    if page == "languages":
        add("back", "back", "Languages", row)
        y += row + gap(6)
        add("search", "search", query, px(theme.SEARCH_HEIGHT),
            SEARCH_PROMPT)
        y += px(theme.SEARCH_HEIGHT) + gap(8)
        found = language_order(model, query)
        if not query:
            hint = "Tick every language you speak."
        elif found:
            hint = "Enter ticks {}.".format(names.get(found[0], found[0]))
        else:
            hint = "No language called that."
        add("hint", None, hint, px(16))
        y += px(16) + gap(8)
        top = y
        bottom = y + px(theme.LIST_HEIGHT)
        # Whole rows only: a row cut in half at the top is drawn as nothing,
        # and the list would open with a hole in it.
        offset = int(round(scroll / float(row))) * row
        cursor = top - offset
        for code in found:
            if cursor >= top - 1 and cursor + row <= bottom + 1:
                items.append(Item("language", "lang:" + code,
                                  names.get(code, code),
                                  (left, cursor, right - px(8), cursor + row),
                                  code in model.get("yours", ()),
                                  languages.native_label(code)))
            cursor += row
        reach = list_height(model, scale, query)
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

    key_label, key_hint, key_look = KEY_ROWS.get(key_state, KEY_ROWS["saved"])
    if key_look == "accent":
        # Nothing works without it, so it comes first until it is there.
        add("row", "key", key_label, row, "accent", hint=key_hint)
        y += row + gap(4)

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
        ([label for label, _value in _BACKENDS], chosen,
         ["backend:" + value for _label, value in _BACKENDS]))
    y += px(theme.SEGMENT_HEIGHT) + gap(4)
    local = model.get("local") or {}
    if local.get("busy"):
        model_hint = "downloading {:.0f}%".format(
            100 * float(local.get("progress") or 0.0))
    else:
        model_hint = localmodels.label(local.get("current", ""))
    add("row", "models", "Model on this laptop", row, None, hint=model_hint)
    y += row + gap(6)

    add("label", None, "Look", px(14))
    y += px(14) + px(theme.LABEL_GAP)
    looks = [value for _label, value in _LOOKS]
    look = model.get("look", "glass")
    add("segmented", "look", "", px(theme.SEGMENT_HEIGHT),
        ([label for label, _value in _LOOKS],
         looks.index(look) if look in looks else 0,
         ["look:" + value for value in looks]))
    y += px(theme.SEGMENT_HEIGHT) + gap(6)

    add("switch", "pause", "Pause Ctrl+Alt", row, bool(model.get("paused")))
    y += row + gap(6)
    add("separator", None, "", gap(6))
    y += gap(6) + gap(4)

    if model.get("update"):
        add("row", "update", "Update to {}".format(model["update"]), row,
            "accent")
        y += row
    if key_look != "accent":
        add("row", "key", key_label, row, "more", hint=key_hint)
        y += row
    for key, label in (("words", "Your words"), ("settings", "Settings"),
                       ("logs", "Logs"), ("report", "Save a problem report")):
        add("row", key, label, row, "more" if key != "report" else None)
        y += row
    y += gap(4)
    add("separator", None, "", gap(6))
    y += gap(6) + gap(4)
    if quit_armed:
        add("row", "quit", "Click again to quit", row, "danger",
            hint="Esc keeps it")
    else:
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
                labels, _chosen, actions = item.extra
                index = int((x - left) / float(right - left) * len(labels))
                index = max(0, min(len(labels) - 1, index))
                return item, actions[index]
            return item, item.key
    return None, None


def language_order(model, query=""):
    """Yours first, in your order, so taking one off never means hunting
    through the alphabet; then everything else by name. With something
    typed, only the languages that answer to it, best match first."""
    yours = [code for code in model.get("yours", ())]
    names = model.get("names", {})
    rest = sorted((code for code in model.get("catalog", ())
                   if code not in yours),
                  key=lambda code: names.get(code, code).lower())
    return languages.search(yours + rest, query)


def list_height(model, scale=1.0, query=""):
    """How far the language list scrolls."""
    row = int(round(theme.ROW_HEIGHT * scale))
    rows = len(language_order(model, query))
    return max(0.0, float(rows * row - int(round(theme.LIST_HEIGHT * scale))))


def _approach(value, target, rate):
    if abs(target - value) < 0.002:
        return target
    return value + (target - value) * rate


class TrayPanel(object):
    """The panel's window. One at a time; on the Tk thread, like all of them.

    `model` is a callable returning the tray's current state; `act` is
    called with an action key when something is clicked. `submit_key` is
    handed the key pasted into the key page - never through `act`, whose
    action names end up in the log.
    """

    def __init__(self, root, model, act, scale=1.0, anchor=None,
                 on_closed=None, submit_key=None):
        self._root = root
        self._submit_key = submit_key
        self._key_text = ""
        self._back_job = None
        self._model_source = model
        self._act = act
        self._on_closed = on_closed
        self.scale = max(0.5, float(scale))
        self._anchor = anchor
        self._page = "main"
        self._scroll = 0.0
        self._query = ""
        self._quit_armed_at = None
        self._hover_key = None
        self._hover = {}
        self._motion = {}
        self._opened_at = time.monotonic()
        self._closing_at = None
        self._closed = False
        self._job = None
        self._idle_job = None
        self._caret_job = None
        self._caret_on = True
        # The search ring: how far round it has turned, how far it is
        # going, and when it last flared at a key.
        self._turn = 0.0
        self._turn_goal = 0.0
        self._flare_at = None
        self._card = None
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
                                  ("<Escape>", self._escape),
                                  ("<KeyPress>", self._key),
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

    def _armed(self, now=None):
        now = time.monotonic() if now is None else now
        return (self._quit_armed_at is not None
                and now - self._quit_armed_at < theme.QUIT_ARMED)

    def _relayout(self):
        size = getattr(self, "_size", None)
        self._size, self._items = layout(
            self._model, self.scale, self._page, self._scroll, self._query,
            self._armed(), self._key_text)
        # The glass only changes with the size, and typing into the search
        # lays the panel out again on every key.
        if self._card is None or self._size != size:
            self._card = glass.panel_card(self._size[0], self._size[1],
                                          self.scale)
        for item in self._items:
            if item.kind == "segmented":
                self._motion.setdefault(item.key, float(item.extra[1]))
            elif item.kind == "switch":
                self._motion.setdefault(item.key,
                                        1.0 if item.extra else 0.0)
            elif item.kind == "language":
                # Ticks already there when the list opens are drawn whole;
                # only one ticked while you watch draws itself in.
                self._motion.setdefault("tick:" + item.key,
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

    def _glow(self, now):
        """How bright the search ring is: settled, or flaring at a key."""
        if self._flare_at is None:
            return theme.GLOW_SETTLED
        faded = min(1.0, (now - self._flare_at) / 0.6)
        return theme.GLOW_FLARE + (theme.GLOW_SETTLED - theme.GLOW_FLARE) \
            * faded

    def _advance(self, now):
        busy = False
        for item in self._items:
            if item.kind == "language":
                key = "tick:" + item.key
                goal = 1.0 if item.extra else 0.0
                value = _approach(self._motion.get(key, goal), goal,
                                  theme.CHECK_DRAW_RATE)
                self._motion[key] = value
                busy = busy or value != goal
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
        if self._page in ("languages", "key"):
            self._turn = _approach(self._turn, self._turn_goal, 0.12)
            busy = busy or self._turn != self._turn_goal
            if self._flare_at is not None:
                if now - self._flare_at >= 0.6:
                    self._flare_at = None
                busy = True
        if self._quit_armed_at is not None and not self._armed(now):
            # The second click did not come: back to plain Quit.
            self._quit_armed_at = None
            self._relayout()
            busy = True
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
        motion = dict(self._motion)
        motion["search-turn"] = self._turn
        motion["search-glow"] = self._glow(now)
        motion["caret"] = 1.0 if self._caret_on else 0.0
        frame = glass.panel_frame(self._card, self._items, self.scale,
                                  self._hover, motion)
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
            busy = busy or opening or self._closing_at is not None \
                or self._quit_armed_at is not None
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

    def _blink(self):
        """The search caret, on and off while the language list is open.
        A blink is one frame, not a stream of them."""
        self._caret_job = None
        if self._closed or self._page not in ("languages", "key"):
            return
        self._caret_on = not self._caret_on
        self._schedule()
        self._caret_job = self.window.after(
            int(theme.CARET_BLINK * 1000), self._blink)

    def _start_blinking(self):
        if self._caret_job is not None:
            try:
                self.window.after_cancel(self._caret_job)
            except tk.TclError:
                pass
        self._caret_on = True
        self._caret_job = self.window.after(
            int(theme.CARET_BLINK * 1000), self._blink)

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
            if (self._page == "key" and fresh.get("key") == "done"
                    and self._back_job is None):
                # Saved: say so for a moment, then back to the first page.
                self._back_job = self.window.after(1400, self._saved_back)
        self._idle_job = self.window.after(IDLE_MS, self._watch)

    def _saved_back(self):
        self._back_job = None
        if not self._closed and self._page == "key":
            self.press("back")

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
        self._scroll = max(0.0, min(list_height(self._model, self.scale,
                                                self._query),
                                    self._scroll + delta))
        self._refit()

    def _clicked(self, event):
        if self._closing_at is not None:
            return
        _item, action = hit(self._items, event.x, event.y)
        if action is None:
            return
        self.press(action)

    # -- the keyboard ------------------------------------------------------

    def _key(self, event):
        """Typing goes into the key field on its page, and into the language
        search from the first page or the language list."""
        if self._closing_at is not None:
            return "break"
        if self._page == "key":
            return self._key_into_field(event)
        if self._page == "models":
            return "break"
        keysym = getattr(event, "keysym", "") or ""
        if keysym == "BackSpace":
            if self._page == "languages" and self._query:
                self.type_into_search(None)
            return "break"
        if keysym in ("Return", "KP_Enter"):
            if self._page == "languages" and self._query:
                found = language_order(self._model, self._query)
                if found:
                    self.press("lang:" + found[0])
            return "break"
        text = keymap.typed_char(getattr(event, "keycode", 0)) \
            or (event.char if (event.char or "").isprintable() else "")
        if text and text.strip() or (text == " " and self._query):
            self.type_into_search(text)
        return "break"

    def _key_into_field(self, event):
        keysym = getattr(event, "keysym", "") or ""
        control = bool(getattr(event, "state", 0) & 0x4)
        if control and getattr(event, "keycode", 0) == 0x56:
            # Ctrl+V by the key, not the letter: on a Russian or Kazakh
            # layout the same key is "м".
            try:
                pasted = self.window.clipboard_get()
            except tk.TclError:
                pasted = ""
            self.type_key("".join(pasted.split()))
        elif keysym == "BackSpace":
            self.type_key(None)
        elif keysym in ("Return", "KP_Enter"):
            self.press("key-save")
        elif not control:
            text = keymap.typed_char(getattr(event, "keycode", 0)) \
                or (event.char if (event.char or "").isprintable() else "")
            if text.strip():
                self.type_key(text.strip())
        return "break"

    def type_key(self, text):
        """Adds `text` to the key field, or takes a character off for None.
        Public, for the live check."""
        if text is None:
            self._key_text = self._key_text[:-1]
        else:
            self._key_text = (self._key_text + text)[:300]
            self._turn_goal += theme.GLOW_NUDGE / 360.0
            self._flare_at = time.monotonic()
        self._start_blinking()
        self._refit()

    def _save_key(self):
        text = self._key_text
        if not text.strip() or self._submit_key is None:
            return
        # The panel keeps the key only until it is handed over.
        self._key_text = ""
        try:
            self._submit_key(text)
        except Exception:
            logger.exception("The tray panel could not hand the key over")
        self.window.after(60, self._watch_once)
        self._refit()

    def type_into_search(self, text):
        """Adds `text` to the search, or takes a letter off for None; opens
        the language list first if it is not what is showing. Public, for
        the live check."""
        if self._page != "languages":
            self._open_languages()
        if text is None:
            self._query = self._query[:-1]
        else:
            self._query = (self._query + text)[:40]
        self._scroll = 0.0
        self._hover_key = None
        self._turn_goal += theme.GLOW_NUDGE / 360.0
        self._flare_at = time.monotonic()
        self._start_blinking()
        self._refit()

    def _open_languages(self):
        self._page, self._scroll, self._query = "languages", 0.0, ""
        self._hover_key = None
        # The ring goes once round as the list opens, as the composer's
        # does when it appears.
        self._turn_goal += 1.0
        self._start_blinking()

    def _escape(self, _event=None):
        """Esc steps back: out of the search, then out of the list, then
        closes. And it is what keeps HeySpeaky when Quit is waiting."""
        if self._quit_armed_at is not None:
            self._quit_armed_at = None
            self._refit()
        elif self._page == "key" and self._key_text:
            self._key_text = ""
            self._refit()
        elif self._page == "languages" and self._query:
            self._query = ""
            self._scroll = 0.0
            self._refit()
        elif self._page != "main":
            self.press("back")
        else:
            self.close()
        return "break"

    def press(self, action):
        """Does what a click on `action` does. Public, for the live check."""
        if action == "more-languages":
            self._open_languages()
            self._refit()
            return
        if action == "back":
            self._page, self._query, self._key_text = "main", "", ""
            self._hover_key = None
            self._refit()
            return
        if action == "key":
            self._page, self._key_text = "key", ""
            self._hover_key = None
            self._turn_goal += 1.0
            self._start_blinking()
            self._refit()
            return
        if action == "models":
            self._page = "models"
            self._hover_key = None
            self._refit()
            return
        if action == "key-save":
            self._save_key()
            return
        if action == "quit" and not self._armed():
            self._quit_armed_at = time.monotonic()
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
        self._key_text = ""
        for job in (self._job, self._idle_job, self._caret_job,
                    self._back_job):
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

