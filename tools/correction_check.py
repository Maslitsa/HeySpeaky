r"""Shows the correction composer on the real screen and photographs it.

The pill has tools/live_check.py because every fault in it was invisible to
the unit tests. The composer is two windows laid one over the other - the
glass, which must never take focus, and the field, which must - and whether
they line up, whether the glass really gets the mouse through its alpha and
whether the field really holds the keyboard are all things only the real
screen can say.

    .venv\Scripts\python.exe tools\correction_check.py --out box.png
    .venv\Scripts\python.exe tools\correction_check.py --scale 1.5

It moves the real pointer over the two buttons, for the hover, and puts it
back where it was. Clicks are handed to the composer directly instead of being
sent to the screen: a real click that missed would land in whatever window is
underneath.

The picture it saves is a strip of moments: opening, open, each button
hovered, typing, and the green tick just before it leaves.
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

from heyspeaky.correct import CorrectionBox                  # noqa: E402
from heyspeaky.overlay import (                              # noqa: E402
    GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_NOACTIVATE, _monitor_scale,
    enable_dpi_awareness, window_handle,
)

HEARD = "Маржан"               # Marzhan
MEANT = "Мағжан"               # Magzhan


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _Event(object):
    def __init__(self, x, y, x_root, y_root):
        self.x, self.y, self.x_root, self.y_root = x, y, x_root, y_root


class _Key(object):
    def __init__(self, char):
        self.keysym = self.char = char


def pump(root, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.008)


def photograph(box, margin=30):
    from PIL import ImageGrab
    x, y = box._position
    width, height = box.layout["window"]
    return ImageGrab.grab(bbox=(x - margin, y - margin, x + width + margin,
                                y + height + margin), all_screens=True)


def pointer():
    point = _Point()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def point_at(box, name):
    """Moves the real pointer to the middle of one button."""
    button = box.layout["buttons"][name]
    ctypes.windll.user32.SetCursorPos(
        box._position[0] + (button[0] + button[2]) // 2,
        box._position[1] + (button[1] + button[3]) // 2)


def main():
    parser = argparse.ArgumentParser(
        description="Show the correction composer on the real screen")
    parser.add_argument("--out", help="save the strip of moments here")
    parser.add_argument("--scale", type=float,
                        help="draw at this scale; the owner's screen is at "
                             "1.25 and geometry has broken there before")
    args = parser.parse_args()

    enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    scale = args.scale or _monitor_scale()
    print("scale {:.2f}".format(scale))

    problems = []
    shots = []
    answers = []
    was_at = pointer()
    ctypes.windll.user32.GetForegroundWindow.restype = ctypes.c_void_p
    was_in_front = ctypes.windll.user32.GetForegroundWindow()

    box = CorrectionBox(root, HEARD, answers.append, scale=scale)
    pump(root, 0.12)
    shots.append(("opening", photograph(box)))
    pump(root, 0.55)
    shots.append(("open", photograph(box)))

    back = window_handle(box.back)
    style = ctypes.windll.user32.GetWindowLongW(back, GWL_EXSTYLE)
    if not style & WS_EX_LAYERED:
        problems.append("the glass is not a layered window")
    if not style & WS_EX_NOACTIVATE:
        problems.append("the glass can take focus")
    if box.top.focus_get() is not box.entry:
        problems.append("the typing cursor is not in the field")

    # The field window must sit exactly on the field in the picture.
    entry = box.layout["entry"]
    offset = (box.top.winfo_rootx() - box.back.winfo_rootx(),
              box.top.winfo_rooty() - box.back.winfo_rooty())
    if offset != (entry[0], entry[1]):
        problems.append("the field is off its slot by {}".format(
            (offset[0] - entry[0], offset[1] - entry[1])))
    print("glass {}x{} at {}; field at {} (want {})".format(
        box.layout["window"][0], box.layout["window"][1], box._position,
        offset, (entry[0], entry[1])))

    for name in ("cancel", "accept"):
        point_at(box, name)
        pump(root, 0.7)
        if box._hover != name:
            problems.append("hovering the {} button did not reach the "
                            "glass".format(name))
        shots.append(("hover " + name, photograph(box)))
    # A real click on the glass, above the field and clear of both buttons,
    # where the picture is certainly under the pointer. It must not take the
    # keyboard from the field, and must not come up over it.
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.restype = ctypes.c_void_p
    user32.WindowFromPoint.argtypes = [_Point]
    user32.GetAncestor.restype = ctypes.c_void_p
    user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    field = box.layout["field"]
    user32.SetCursorPos(box._position[0] + (field[0] + field[2]) // 2,
                        box._position[1] + box.layout["box"][1]
                        + max(2, (field[1] - box.layout["box"][1]) // 2))
    pump(root, 0.1)
    user32.mouse_event(0x0002, 0, 0, 0, 0)      # left down
    user32.mouse_event(0x0004, 0, 0, 0, 0)      # left up
    pump(root, 0.3)
    typing_window = window_handle(box.top)
    if (user32.GetForegroundWindow() or 0) != typing_window:
        problems.append("a click on the glass took the keyboard away")
    entry = box.layout["entry"]
    middle = _Point(box._position[0] + (entry[0] + entry[2]) // 2,
                    box._position[1] + (entry[1] + entry[3]) // 2)
    on_top = user32.GetAncestor(user32.WindowFromPoint(middle), 2) or 0
    if on_top != typing_window:
        problems.append("after a click the glass covers the field")
    print("after a real click: keyboard in the field {}, field on top {}"
          .format(user32.GetForegroundWindow() == typing_window,
                  on_top == typing_window))

    user32.SetCursorPos(*was_at)
    pump(root, 0.3)
    if box._hover is not None:
        problems.append("the hover stayed after the pointer left")

    box.entry.delete(0, "end")
    for letter in MEANT:
        box.entry.insert("end", letter)
        box._typed(_Key(letter))
        pump(root, 0.06)
    shots.append(("typing", photograph(box)))

    start = box._position
    box._grab(_Event(box.layout["box"][0] + 60, box.layout["box"][1] + 4,
                     start[0] + 60, start[1] + 10))
    box._drag(_Event(0, 0, start[0] + 160, start[1] + 10))
    box._drop(_Event(0, 0, start[0] + 160, start[1] + 10))
    root.update()
    moved = box._position[0] - start[0]
    print("drag moved it {}px".format(moved))
    if moved < 50:
        problems.append("dragging did not move it")
    if box.back.winfo_rootx() - start[0] < 50:
        problems.append("the glass did not follow the drag")
    box._move(*start)
    pump(root, 0.1)

    box._accept()
    pump(root, 0.14)
    shots.append(("saved", photograph(box)))
    if answers != [MEANT]:
        problems.append("Enter returned {!r}".format(answers))
    pump(root, 0.8)
    if not box._destroyed:
        problems.append("it did not go away after saving")

    # Nothing selected: a placeholder, and Enter on it shakes instead of
    # saving the placeholder as a word.
    answers[:] = []
    empty = CorrectionBox(root, "", answers.append, scale=scale)
    pump(root, 0.6)
    shots.append(("nothing selected", photograph(empty)))
    empty._accept()
    pump(root, 0.6)
    if answers:
        problems.append("Enter on an empty field returned {!r}".format(
            answers))
    empty._cancel()
    pump(root, 0.4)
    if answers != [None]:
        problems.append("Escape returned {!r}".format(answers))
    if not empty._destroyed:
        problems.append("it did not go away after Escape")

    # Focus going to another program for good does close it: handed back to
    # the window that was in front before this check began.
    answers[:] = []
    third = CorrectionBox(root, HEARD, answers.append, scale=scale)
    pump(root, 0.6)
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow(was_in_front)
    pump(root, 0.6)
    if answers != [None] or not third._destroyed:
        problems.append("focus going elsewhere did not close it ({!r})"
                        .format(answers))

    if args.out:
        from PIL import Image, ImageDraw
        width = max(image.size[0] for _n, image in shots)
        height = sum(image.size[1] + 22 for _n, image in shots)
        strip = Image.new("RGB", (width, height), (18, 18, 20))
        drawing = ImageDraw.Draw(strip)
        y = 0
        for name, image in shots:
            drawing.text((8, y + 4), name, fill=(200, 200, 205))
            strip.paste(image, (0, y + 22))
            y += image.size[1] + 22
        strip.save(args.out)
        print("shot {}".format(args.out))

    root.destroy()
    for problem in problems:
        print("FAULT {}".format(problem))
    print("OK" if not problems else "{} problem(s)".format(len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
