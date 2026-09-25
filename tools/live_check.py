r"""Shows the pill on the real screen and photographs the result.

Every bug the owner has found in the pill was invisible to the unit tests and
to tools/ui_lab.py, for the same reason: both draw it over a backdrop that
holds still. On a real desktop the background is alive, the screen is at 125%,
and the window has to be composited by Windows rather than by PIL. That is
where the faults were.

    .venv\Scripts\python.exe tools\live_check.py
    .venv\Scripts\python.exe tools\live_check.py --out shot.png

It reports what the tests cannot: that the window is layered and never takes
focus, that its corners are genuinely transparent rather than a rectangle of
stale desktop, that a click at the centre of each button reaches the
callback, and that the real pointer over the cross makes it answer while the
window in front stays in front. The picture is the pill twice: as it is, and
with the pointer on the cross. Exit code 0 if all of that holds.

    .venv\Scripts\python.exe tools\live_check.py --style mono

The mono look instead: listening, thinking, shrinking away when the words
land, and a message, photographed on the real screen; the window must let
every click through to what is under it, since mono has no buttons.
"""

import argparse
import ctypes
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from heyspeaky import glass                                  # noqa: E402
from heyspeaky.config import DEFAULTS                        # noqa: E402
from heyspeaky.overlay import Overlay, enable_dpi_awareness  # noqa: E402

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_LAYERED = 0x00080000


class _Click(object):
    """What Tk hands a <Button-1> binding."""

    def __init__(self, x, y):
        self.x = x
        self.y = y


def mono_check(args):
    """The mono look on the real screen."""
    enable_dpi_awareness()
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.WindowFromPoint.restype = ctypes.c_void_p
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    in_front = user32.GetForegroundWindow()
    root = tk.Tk()
    config = dict(DEFAULTS["overlay"], style="mono")
    overlay = Overlay(root, config)
    # A new process's first window is handed the front by Windows. Give it
    # back, so what is checked is the pill, not this script starting up.
    root.update()
    user32.SetForegroundWindow(in_front)
    root.update()

    from PIL import Image, ImageDraw, ImageGrab

    def run(seconds, level=None):
        for step in range(max(1, int(seconds / 0.02))):
            if level is not None:
                overlay.set_level(level(step))
            root.update()
            time.sleep(0.02)

    def photo():
        x, y, width, height = overlay._geometry
        return ImageGrab.grab(bbox=(x - 20, y - 10, x + width + 20,
                                    y + height + 10), all_screens=True)

    shots = []

    class _Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    pointer = _Point()
    user32.GetCursorPos(ctypes.byref(pointer))
    overlay.show("listening")
    run(args.seconds, lambda step: abs(__import__("math").sin(step * 0.3)))
    x, y, width, height = overlay._geometry
    left, top, right, bottom = overlay._glass.box
    over_pointer = (x + left <= pointer.x <= x + right
                    and (y + bottom <= pointer.y or y + top >= pointer.y))
    shots.append(("listening", photo()))

    middle = _Point(x + (left + right) // 2, y + (top + bottom) // 2)
    under = user32.WindowFromPoint(middle)
    hwnd = int(root.wm_frame(), 16)
    passes_clicks = under != hwnd
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

    overlay.set_state("transcribing")
    run(0.5)
    shots.append(("thinking", photo()))
    overlay.flash("done", "the words", "")
    run(0.09)
    shots.append(("words landed", photo()))
    run(0.5)
    gone = not overlay._visible
    overlay.flash("error", "", "Too quiet", hold=0.8)
    run(0.35)
    shots.append(("a message", photo()))
    run(1.2)
    now_front = user32.GetForegroundWindow()
    kept_front = now_front == in_front
    if not kept_front:
        name = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(ctypes.c_void_p(now_front), name, 128)
        print("in front now: a {} window{}".format(
            name.value, " - this one" if now_front == hwnd else ""))
    root.destroy()

    widest = max(image.size[0] for _name, image in shots)
    strip = Image.new("RGB", (widest, sum(image.size[1] + 18
                                          for _name, image in shots)),
                      (24, 24, 26))
    drawing = ImageDraw.Draw(strip)
    top = 0
    for name, image in shots:
        drawing.text((6, top + 3), name, fill=(220, 220, 225))
        strip.paste(image, (0, top + 18))
        top += image.size[1] + 18
    strip.save(args.out)

    print("saved", args.out)
    print("layered                   {} (want True)".format(
        bool(style & WS_EX_LAYERED)))
    print("never takes focus         {} (want True)".format(
        bool(style & WS_EX_NOACTIVATE)))
    print("clicks pass straight on   {} (want True)".format(passes_clicks))
    print("gone after the words      {} (want True)".format(gone))
    print("appears at the pointer    {} (want True)".format(over_pointer))
    print("focus stayed where it was {} (want True)".format(kept_front))
    ok = (bool(style & WS_EX_LAYERED) and bool(style & WS_EX_NOACTIVATE)
          and passes_clicks and gone and kept_front and over_pointer)
    print("RESULT:", "ok" if ok else "FAILED")
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(description="Show the pill for real")
    parser.add_argument("--out", default="live-pill.png",
                        help="where to save the photograph")
    parser.add_argument("--seconds", type=float, default=0.8,
                        help="how long to run the waveform before the shot")
    parser.add_argument("--style", choices=("glass", "mono"),
                        default="glass", help="which look to check")
    args = parser.parse_args()
    if args.style == "mono":
        return mono_check(args)

    hit = []
    enable_dpi_awareness()
    root = tk.Tk()
    overlay = Overlay(root, DEFAULTS["overlay"],
                      on_cancel=lambda: hit.append("cancel"),
                      on_accept=lambda: hit.append("accept"))
    overlay.show("listening")

    # Run the waveform for a moment so the shot is of a working pill and not
    # of its first frame.
    steps = max(1, int(args.seconds / 0.02))
    for step in range(steps):
        overlay.set_level(0.2 + 0.6 * ((step % 10) / 10.0))
        root.update()
        time.sleep(0.02)

    from PIL import ImageGrab

    x, y, width, height = overlay._geometry
    bbox = (x - 40, y - 20, x + width + 40, y + height + 20)
    shot = ImageGrab.grab(bbox=bbox, all_screens=True)

    # The real pointer over the cross: the button has to answer it, and the
    # window in front must stay the window in front throughout.
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    in_front = user32.GetForegroundWindow()

    class _Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    was_at = _Point()
    user32.GetCursorPos(ctypes.byref(was_at))
    cross = glass.button_boxes(overlay._glass)["cancel"]
    user32.SetCursorPos(x + (cross[0] + cross[2]) // 2,
                        y + (cross[1] + cross[3]) // 2)
    for _ in range(25):
        overlay.set_level(0.4)
        root.update()
        time.sleep(0.02)
    hovered = overlay._hover
    pointed = ImageGrab.grab(bbox=bbox, all_screens=True)
    user32.SetCursorPos(was_at.x, was_at.y)
    for _ in range(10):
        root.update()
        time.sleep(0.02)
    kept_front = user32.GetForegroundWindow() == in_front

    from PIL import Image
    both = Image.new("RGB", (shot.size[0], shot.size[1] * 2))
    both.paste(shot, (0, 0))
    both.paste(pointed, (0, shot.size[1]))
    both.save(args.out)

    hwnd = int(root.wm_frame(), 16)
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    layered = bool(style & WS_EX_LAYERED)
    unfocusable = bool(style & WS_EX_NOACTIVATE)
    clickable = not (style & WS_EX_TRANSPARENT)

    for box in glass.button_boxes(overlay._glass).values():
        overlay._on_click(_Click((box[0] + box[2]) // 2,
                                 (box[1] + box[3]) // 2))
    # And the middle of the pill, which must do nothing at all.
    left, top, right, bottom = overlay._glass.box
    overlay._on_click(_Click((left + right) // 2, (top + bottom) // 2))
    root.update()
    time.sleep(0.6)

    corner = glass.paint(overlay._glass, state="listening",
                         levels=[0.5] * 8).getpixel((0, 0))[3]

    overlay.hide()
    for _ in range(20):
        root.update()
        time.sleep(0.02)
    root.destroy()

    print("saved", args.out)
    print("layered                  {} (want True)".format(layered))
    print("never takes focus        {} (want True)".format(unfocusable))
    print("buttons take clicks      {} (want True)".format(clickable))
    print("corner is see-through    {} (want 0)".format(corner))
    print("buttons that fired       {}".format(sorted(hit)))
    print("pointer on the cross     {} (want cancel)".format(hovered))
    print("focus stayed where it was {} (want True)".format(kept_front))

    ok = (layered and unfocusable and clickable and corner == 0
          and sorted(hit) == ["accept", "cancel"] and hovered == "cancel"
          and kept_front)
    print("RESULT:", "ok" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
