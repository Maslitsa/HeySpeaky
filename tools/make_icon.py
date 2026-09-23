r"""Draws HeySpeaky's icon into a .ico file, for the shortcuts.

The installer runs this before it makes the Start menu and Startup
shortcuts, so they show HeySpeaky's waveform instead of the blank window
Windows puts on a program with no icon of its own. Drawn here, like the end
tone, rather than shipped as a binary.

    .venv\Scripts\python.exe tools\make_icon.py heyspeaky.ico
    .venv\Scripts\python.exe tools\make_icon.py heyspeaky.ico --png icon.png
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from heyspeaky import tray                                   # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Draw HeySpeaky's icon")
    parser.add_argument("out", help="where to write the .ico")
    parser.add_argument("--png", help="also save a large PNG to look at")
    args = parser.parse_args()
    tray.save_app_icon(args.out)
    if args.png:
        tray.app_icon(256).save(args.png)
    print("icon", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
