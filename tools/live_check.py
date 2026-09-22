r"""Shows the pill on the real screen and photographs the result.

Every bug the owner has found in the pill was invisible to the unit tests and
to tools/ui_lab.py, for the same reason: both draw it over a backdrop that
holds still. On a real desktop the background is alive, the screen is at 125%,
and the window has to be composited by Windows rather than by PIL. That is
where the faults were.

    .venv\Scripts\python.exe tools\live_check.py
    .venv\Scripts\python.exe tools\live_check.py --out shot.png

It reports three things the tests cannot: that the window is layered and never
takes focus, that its corners are genuinely transparent rather than a
rectangle of stale desktop, and that a click at the centre of each button
reaches the callback. Exit code 0 if all of that holds.
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


def main():
    parser = argparse.ArgumentParser(description="Show the pill for real")
    parser.add_argument("--out", default="live-pill.png",
                        help="where to save the photograph")
    parser.add_argument("--seconds", type=float, default=0.8,
                        help="how long to run the waveform before the shot")
    args = parser.parse_args()

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
    shot = ImageGrab.grab(
        bbox=(x - 40, y - 20, x + width + 40, y + height + 20),
        all_screens=True)
    shot.save(args.out)

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

    ok = (layered and unfocusable and clickable and corner == 0
          and sorted(hit) == ["accept", "cancel"])
    print("RESULT:", "ok" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
