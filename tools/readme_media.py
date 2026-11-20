r"""Draws the README's pictures from the app's own drawing code.

Every picture of HeySpeaky on the project page comes out of glass.py - the
code that puts the pill, the tray panel and the correction box on screen -
so the page cannot show a HeySpeaky that does not exist. The backdrop is a
plain dark desk, not anybody's screen.

    python tools\readme_media.py                 # docs/img/*.png and *.gif
    python tools\readme_media.py --film FILM.mp4 # also the film's poster

The film's poster and the social preview are frames of the film (video/).
The film itself is not in the repository, because the installer downloads
all of it: it is uploaded to GitHub and the README plays it by its address.
"""

import argparse
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from heyspeaky import glass, languages, theme  # noqa: E402
from heyspeaky import panel as panel_module  # noqa: E402

OUT = ROOT / "docs" / "img"
DESK = (13, 11, 16)


def backdrop(size, glow=(255, 74, 43), strength=0.16):
    """A dark desk with one warm light, the film's stage."""
    w, h = size
    base = Image.new("RGB", size, DESK)
    light = Image.new("L", size, 0)
    ImageDraw.Draw(light).ellipse((w * 0.15, h * 0.2, w * 0.85, h * 1.4), fill=int(255 * strength))
    light = light.filter(ImageFilter.GaussianBlur(min(w, h) * 0.18))
    tint = Image.new("RGB", size, glow)
    return Image.composite(tint, base, light)


def place(canvas, picture, x=None, y=None):
    x = (canvas.width - picture.width) // 2 if x is None else x
    y = (canvas.height - picture.height) // 2 if y is None else y
    out = canvas.convert("RGBA")
    out.alpha_composite(picture.convert("RGBA"), (int(x), int(y)))
    return out


def mono_gif(path, scale=2.4):
    """Mono, as it is used: listening, the thinking wave, then gone."""
    frames = []
    size = (720, 300)
    desk = backdrop(size)
    mono = glass.mono_prepare(scale)
    tick = 1 / 25.0
    for i in range(int(4.2 / tick)):
        t = i * tick
        if t < 2.4:
            level = 0.35 + 0.35 * abs(math.sin(t * 3.1)) + 0.15 * math.sin(t * 11.0)
            frame = glass.mono_paint(mono, "listening", max(0.0, min(1.0, level)), t)
        elif t < 3.5:
            frame = glass.mono_paint(mono, "transcribing", 0.0, t)
        elif t < 3.5 + theme.MONO_COLLAPSE:
            frame = glass.mono_paint(mono, "done", 0.0, t, (t - 3.5) / theme.MONO_COLLAPSE)
        else:
            frame = Image.new("RGBA", mono.window, (0, 0, 0, 0))
        frames.append(place(desk, frame).convert("RGB").quantize(colors=128, dither=Image.Dither.NONE))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(tick * 1000), loop=0, optimize=True)


def glass_png(path, scale=2.0):
    size = (900, 260)
    levels = [max(0.06, (math.sin(math.pi * i / (theme.BARS - 1)) ** 0.6) * (0.55 + 0.45 * math.sin(i * 0.7))) for i in range(theme.BARS)]
    pill = glass.paint(glass.prepare(rim=True, scale=scale), state="listening", levels=levels)
    place(backdrop(size, (90, 120, 255), 0.12), pill).convert("RGB").save(path)


def panel_png(path, mono, scale=1.6):
    yours = ["kk", "ru", "de", "en"]
    catalog = languages.catalog(yours)
    model = {"status": "Ready", "state": "ready", "paused": False, "pinned": "", "yours": yours,
             "backend": "cloud", "usage": "", "update": "", "key": "saved", "catalog": list(catalog),
             "look": "mono" if mono else "glass", "names": dict((c, languages.name(c)) for c in catalog)}
    size, items = panel_module.layout(model, scale)
    card = glass.panel_frame(glass.panel_card(size[0], size[1], scale, mono=mono), items, scale, mono=mono)
    pad = 60
    canvas = backdrop((card.width + pad * 2, card.height + pad * 2), strength=0.1)
    place(canvas, card).convert("RGB").save(path)


def composer_png(path, mono, scale=2.0):
    comp = glass.composer(scale, mono=mono)
    frame = glass.composer_frame(comp, text="Мағжан", done=False)
    canvas = backdrop((frame.width + 80, frame.height + 60), (2, 103, 197), 0.12)
    place(canvas, frame).convert("RGB").save(path)


def film_frames(film):
    """The poster (1280x720) and GitHub's social preview (1280x640)."""
    poster = OUT / "film-poster.jpg"
    social = OUT / "social-preview.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "8.25", "-i", str(film), "-frames:v", "1",
                    "-vf", "scale=1280:720", "-q:v", "3", str(poster)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "8.25", "-i", str(film), "-frames:v", "1",
                    "-vf", "scale=1280:720,crop=1280:640:0:20", str(social)], check=True)
    return poster, social


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--film", metavar="MP4")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    mono_gif(OUT / "pill-mono.gif")
    glass_png(OUT / "pill-glass.png")
    panel_png(OUT / "panel-mono.png", mono=True)
    composer_png(OUT / "composer-mono.png", mono=True)
    if args.film:
        film_frames(Path(args.film))
    for p in sorted(OUT.iterdir()):
        print("{:28s} {:>8.1f} KB".format(p.name, p.stat().st_size / 1024))


if __name__ == "__main__":
    main()
