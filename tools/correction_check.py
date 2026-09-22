r"""Shows the correction box on the real screen and photographs it.

The pill has tools/live_check.py because every fault in it was invisible to
the unit tests. This box is a different kind of window - it takes focus on
purpose, it is an ordinary Tk Toplevel rather than a layered surface - so it
needs its own look, and the same rule applies: a window nobody has looked at
is a window nobody has checked.

    .venv\Scripts\python.exe tools\correction_check.py
    .venv\Scripts\python.exe tools\correction_check.py --out box.png
    .venv\Scripts\python.exe tools\correction_check.py --empty

It reports what the tests cannot: that the box actually appears, that it is
on the screen it was asked to be on, that it holds the keyboard, and that
Enter and Escape return what they should.
"""

import argparse
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
from heyspeaky.overlay import enable_dpi_awareness           # noqa: E402

HEARD = "Маржан"               # Marzhan
MEANT = "Мағжан"               # Magzhan


def shoot(path):
    """Photographs the whole screen, the way live_check.py does."""
    try:
        from PIL import ImageGrab
    except ImportError:
        return None
    image = ImageGrab.grab()
    image.save(path)
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Show the correction box on the real screen")
    parser.add_argument("--out", help="save a screenshot here")
    parser.add_argument("--empty", action="store_true",
                        help="the shape with nothing selected")
    parser.add_argument("--hold", type=float, default=1.2,
                        help="seconds to leave it up before answering")
    args = parser.parse_args()

    enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()

    answers = []
    heard = "" if args.empty else HEARD
    box = CorrectionBox(root, heard, answers.append)

    root.update()
    time.sleep(args.hold)
    root.update()

    problems = []
    if not box.top.winfo_viewable():
        problems.append("the box did not appear")
    width = box.top.winfo_width()
    height = box.top.winfo_height()
    x, y = box.top.winfo_x(), box.top.winfo_y()
    if x < 0 or y < 0:
        problems.append("it is off the left or top of the screen")
    if x + width > box.top.winfo_screenwidth():
        problems.append("it runs off the right of the screen")
    if y + height > box.top.winfo_screenheight():
        problems.append("it runs off the bottom of the screen")
    if box.top.focus_get() is not box.entry:
        problems.append("the typing cursor is not in the box")

    print("box  {}x{} at {},{}".format(width, height, x, y))
    print("text {!r}".format(box.entry.get()))

    if args.out:
        saved = shoot(args.out)
        print("shot {}".format(saved or "not taken: Pillow is missing"))

    # Enter returns what was typed; Escape returns nothing at all.
    box.entry.delete(0, "end")
    box.entry.insert(0, MEANT)
    box._accept()
    root.update()
    if answers != [MEANT]:
        problems.append("Enter returned {!r}".format(answers))

    answers[:] = []
    second = CorrectionBox(root, heard, answers.append)
    root.update()
    second._cancel()
    root.update()
    if answers != [None]:
        problems.append("Escape returned {!r}".format(answers))

    root.destroy()

    for problem in problems:
        print("FAULT {}".format(problem))
    print("OK" if not problems else "{} problem(s)".format(len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
