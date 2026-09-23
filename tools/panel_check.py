r"""Opens the tray panel on the real screen and photographs it.

Like tools/live_check.py for the pill and tools/correction_check.py for the
composer: the panel is a layered window drawn over the live desktop, which
no unit test can see. It is opened where a click on the tray would open it,
driven with a stand-in for the tray - so nothing in the real app changes -
and photographed at each step: open, a row under the pointer, a language
pinned and the pause switched on, the language list, scrolled, and closed.

    .venv\Scripts\python.exe tools\panel_check.py --out panel.png
    .venv\Scripts\python.exe tools\panel_check.py --scale 1.5

It moves the real pointer over one row, for the hover, and puts it back.
It also types into the language search with real keys - in the Kazakh
layout, if this machine has it - and clicks Quit once, which must not quit.
"""

import argparse
import ctypes
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from heyspeaky import languages                              # noqa: E402
from correction_check import kazakh_layout, type_in_layout   # noqa: E402
from heyspeaky.overlay import (                              # noqa: E402
    GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_NOACTIVATE, _cursor_work_area,
    _monitor_scale, enable_dpi_awareness, window_handle,
)
from heyspeaky.panel import TrayPanel                        # noqa: E402


class StandIn(object):
    """What the tray would be, without touching the app's settings."""

    def __init__(self):
        self.state = {"pinned": "", "paused": False, "backend": "cloud",
                      "yours": ["kk", "ru", "en", "de"], "key": "missing"}
        self.done = []

    def model(self):
        offered = languages.catalog(self.state["yours"])
        return {
            "status": "Paused" if self.state["paused"] else
            "Ready · auto-detect",
            "state": "paused" if self.state["paused"] else "ready",
            "paused": self.state["paused"],
            "pinned": self.state["pinned"],
            "yours": list(self.state["yours"]),
            "backend": self.state["backend"],
            "usage": "This month: $0.42 · 118 dictations",
            "update": "",
            "key": self.state["key"],
            "catalog": list(offered),
            "names": dict((code, languages.name(code)) for code in offered),
        }

    def act(self, action):
        self.done.append(action)
        if action == "key":
            self.state["key"] = "saved"
        elif action.startswith("pin:"):
            self.state["pinned"] = action[4:]
        elif action == "pause":
            self.state["paused"] = not self.state["paused"]
        elif action.startswith("lang:"):
            yours = self.state["yours"]
            if action[5:] in yours:
                yours.remove(action[5:])
            else:
                yours.insert(0, action[5:])
        elif action.startswith("backend:"):
            self.state["backend"] = action[8:]


def pump(root, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.008)


def photograph(panel):
    from PIL import ImageGrab
    x, y = panel.window.winfo_rootx(), panel.window.winfo_rooty()
    width, height = panel.window.winfo_width(), panel.window.winfo_height()
    return ImageGrab.grab(bbox=(x - 10, y - 10, x + width + 10,
                                y + height + 10), all_screens=True)


def main():
    parser = argparse.ArgumentParser(description="Show the tray panel")
    parser.add_argument("--out", help="save the strip of moments here")
    parser.add_argument("--scale", type=float)
    args = parser.parse_args()

    enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    scale = args.scale or _monitor_scale()
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    was_in_front = user32.GetForegroundWindow()

    class _Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    was_at = _Point()
    user32.GetCursorPos(ctypes.byref(was_at))
    _left, _top, right, bottom = _cursor_work_area()
    anchor = (right - 120, bottom + 20)          # where the tray icons are

    stand_in = StandIn()
    closed = []
    panel = TrayPanel(root, stand_in.model, stand_in.act, scale=scale,
                      anchor=anchor, on_closed=closed.append)
    problems = []
    shots = []
    pump(root, 0.4)
    shots.append(("open", photograph(panel)))

    style = user32.GetWindowLongW(window_handle(panel.window), GWL_EXSTYLE)
    if not style & WS_EX_LAYERED:
        problems.append("the panel is not a layered window")
    if style & WS_EX_NOACTIVATE:
        problems.append("the panel cannot take focus")
    if panel.window.focus_get() is None:
        problems.append("the panel did not get the keyboard")
    x, y = panel.window.winfo_rootx(), panel.window.winfo_rooty()
    if y + panel.window.winfo_height() > bottom + 40 * scale:
        problems.append("the panel runs under the taskbar")

    first = [item for item in panel._items if item.kind == "row"][0]
    if first.key != "key":
        problems.append("a missing key is not the first row")
    shots.append(("no key yet", photograph(panel)))
    panel.press("key")
    pump(root, 0.5)
    if stand_in.state["key"] != "saved" or not panel.open:
        problems.append("the key row did not do its job and stay open")

    row = [item for item in panel._items if item.key == "settings"][0]
    user32.SetCursorPos(x + (row.rect[0] + row.rect[2]) // 2,
                        y + (row.rect[1] + row.rect[3]) // 2)
    pump(root, 0.5)
    if panel._hover_key != "settings":
        problems.append("the pointer on a row did not reach the panel")
    shots.append(("pointer on Settings", photograph(panel)))
    user32.SetCursorPos(was_at.x, was_at.y)
    pump(root, 0.2)

    panel.press("pin:kk")
    panel.press("pause")
    panel.press("backend:local")
    pump(root, 0.6)
    if stand_in.done[-3:] != ["pin:kk", "pause", "backend:local"]:
        problems.append("clicks did not reach the tray: {}".format(
            stand_in.done))
    if not panel.open:
        problems.append("a switch closed the panel")
    chosen = [item for item in panel._items
              if item.kind == "chip" and item.extra]
    if [item.key for item in chosen] != ["pin:kk"]:
        problems.append("the pinned language did not show")
    shots.append(("Kazakh pinned, paused, this laptop", photograph(panel)))

    panel.press("quit")
    pump(root, 0.3)
    if "quit" in stand_in.done or not panel.open:
        problems.append("one click on Quit quit")
    shots.append(("Quit clicked once", photograph(panel)))
    panel._escape()
    pump(root, 0.3)
    if panel._quit_armed_at is not None:
        problems.append("Esc did not take the Quit back")

    panel.press("more-languages")
    pump(root, 0.3)
    shots.append(("languages", photograph(panel)))
    first = [item.label for item in panel._items if item.kind == "language"][:4]
    print("the list starts with", first)
    if first != [languages.name(code) for code in ("kk", "ru", "en", "de")]:
        problems.append("your languages are not at the top of the list")

    class _Wheel(object):
        delta = -120

    for _ in range(3):
        panel._wheel(_Wheel())
    pump(root, 0.3)
    shots.append(("scrolled", photograph(panel)))
    visible = [item for item in panel._items if item.kind == "language"]
    list_top = min(item.rect[1] for item in visible)
    hint = [item for item in panel._items if item.kind == "hint"][0]
    if list_top - hint.rect[3] > 12 * scale:
        problems.append("a gap opened at the top of the scrolled list")
    # Typing finds a language. With real keys, in the Kazakh layout when
    # there is one: that is where Tk alone would have typed "?".
    kazakh = kazakh_layout()
    panel.window.focus_force()
    pump(root, 0.2)
    if kazakh:
        type_in_layout(root, kazakh, (0x51, 0x41, 0x30))    # Й Ф Қ -> "йфқ"
        panel._escape()
        pump(root, 0.1)
        type_in_layout(root, kazakh, (0x30, 0x46))          # Қ А -> "қа"
    else:
        for letter in "kaz":
            panel.type_into_search(letter)
            pump(root, 0.05)
    pump(root, 0.4)
    found = [item.key for item in panel._items if item.kind == "language"]
    print("typed {!r}, found {}".format(panel._query, found))
    if found[:1] != ["lang:kk"]:
        problems.append("typing did not find Kazakh ({!r} -> {})".format(
            panel._query, found))
    shots.append(("typed " + panel._query, photograph(panel)))
    unticked = [item.key for item in panel._items
                if item.kind == "language" and not item.extra]
    if unticked:
        panel.press(unticked[0])
        pump(root, 0.16)
        shots.append(("a tick drawing itself", photograph(panel)))
        pump(root, 0.5)
        panel.press(unticked[0])
        pump(root, 0.4)
    panel._escape()
    panel.press("back")
    pump(root, 0.3)

    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow(was_in_front)
    pump(root, 0.8)
    if not closed:
        problems.append("clicking away did not close it")

    again = TrayPanel(root, stand_in.model, stand_in.act, scale=scale,
                      anchor=anchor, on_closed=closed.append)
    pump(root, 0.4)
    again.press("words")
    pump(root, 0.5)
    if len(closed) != 2:
        problems.append("a row that opens something did not close it")

    if args.out:
        from PIL import Image, ImageDraw
        width = sum(image.size[0] for _n, image in shots)
        height = max(image.size[1] for _n, image in shots) + 22
        strip = Image.new("RGB", (width, height), (18, 18, 20))
        drawing = ImageDraw.Draw(strip)
        x = 0
        for name, image in shots:
            drawing.text((x + 8, 4), name, fill=(200, 200, 205))
            strip.paste(image, (x, 22))
            x += image.size[0]
        strip.save(args.out)
        print("shot", args.out)

    root.destroy()
    for problem in problems:
        print("FAULT", problem)
    print("OK" if not problems else "{} problem(s)".format(len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
