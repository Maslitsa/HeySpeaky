r"""Draws every state of the pill to a PNG, without running the app.

This is how a change to the look gets checked: run it, look at the picture,
change theme.py, run it again. It draws each state over several backdrops,
because a pill that reads well on a dark wallpaper can disappear on a white
document.

    .venv\Scripts\python.exe tools\ui_lab.py
    .venv\Scripts\python.exe tools\ui_lab.py --desktop --out lab.png

--desktop uses a picture of your actual screen as the backdrop, which is the
honest test.
"""

import argparse
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from heyspeaky import glass, theme  # noqa: E402

SENTENCE = ("I already sent the invoice, aber ich warte noch auf eine "
            "Antwort.")


def wave(count, phase=0.0, reach=1.0):
    """Heights that look like a voice rather than a graph."""
    levels = []
    for index in range(count):
        share = index / float(max(1, count - 1))
        envelope = math.sin(math.pi * share) ** 0.6
        ripple = 0.55 + 0.45 * math.sin(share * 9.0 + phase)
        levels.append(max(0.08, envelope * ripple * reach))
    return levels


def colourful(size):
    small = Image.new("RGB", (16, 8))
    pixels = small.load()
    for y in range(8):
        for x in range(16):
            share = x / 15.0
            pixels[x, y] = (
                int(20 + 200 * share),
                int(150 - 90 * share + 20 * y),
                int(160 + 80 * (1 - share)),
            )
    return small.resize(size, Image.BICUBIC).filter(
        ImageFilter.GaussianBlur(6))


def light(size):
    image = Image.new("RGB", size, (232, 232, 237))
    drawing = ImageDraw.Draw(image)
    for offset in range(0, size[0], 90):
        drawing.line([(offset, 0), (offset + 40, size[1])],
                     fill=(223, 223, 229), width=9)
    return image


def dark(size):
    image = Image.new("RGB", size, (18, 18, 22))
    drawing = ImageDraw.Draw(image)
    for offset in range(0, size[0], 70):
        drawing.line([(offset, size[1]), (offset + 30, 0)],
                     fill=(28, 28, 34), width=7)
    return image


def desktop(size):
    """A real piece of this screen, just above where the pill sits."""
    from PIL import ImageGrab

    grab = ImageGrab.grab()
    left = max(0, (grab.width - size[0]) // 2)
    top = max(0, grab.height - size[1] - 80)
    return grab.crop((left, top, left + size[0], top + size[1]))


def states():
    return [
        ("listening", dict(state="listening", levels=wave(theme.BARS))),
        ("transcribing", dict(state="transcribing", levels=wave(theme.BARS))),
        ("done", dict(state="done")),
        ("error", dict(state="error", status="Nothing heard")),
        ("opening", dict(state="listening", levels=wave(theme.BARS),
                         open_share=0.34)),
    ]


def sheet(backdrops, out):
    rows = []
    for name, make in backdrops:
        for label, options in states():
            window = (theme.WIDTH, theme.HEIGHT + theme.SHADOW_MARGIN * 2)
            frame = glass.render(make(window), **options)
            rows.append(("{} / {}".format(name, label), frame))

    gap = 18
    caption = 20
    width = rows[0][1].width + gap * 2
    height = sum(row[1].height + caption + gap for row in rows) + gap
    page = Image.new("RGB", (width, height), (245, 245, 247))
    drawing = ImageDraw.Draw(page)
    text_font = glass.font(12)
    y = gap
    for title, frame in rows:
        drawing.text((gap, y), title, font=text_font, fill=(90, 90, 96))
        y += caption
        page.paste(frame, (gap, y))
        y += frame.height + gap
    page.save(out)
    return out


def main():
    parser = argparse.ArgumentParser(description="Draw the pill to a PNG")
    parser.add_argument("--out", default="ui-lab.png")
    parser.add_argument("--desktop", action="store_true",
                        help="use a picture of this screen as the backdrop")
    args = parser.parse_args()

    backdrops = [("colour", colourful), ("light", light), ("dark", dark)]
    if args.desktop:
        backdrops = [("desktop", desktop)] + backdrops
    print(sheet(backdrops, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
