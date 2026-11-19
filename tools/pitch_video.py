r"""Draws the pitch video, frame by frame, from the app's own renders.

The pill, the mono pill, the tray panel and the icon all come out of
glass.py, the code that puts them on screen, so the video cannot show a
HeySpeaky that does not exist. The waveform follows demo/four_languages.wav
through the same loudness curve and easing the pill puts a microphone
through, and the text that lands is what OpenAI returned for that clip on
26 October 2026 (tools/try_demo.py --cloud), word for word.

The pill in the demo is Mono, the look the owner uses: it appears over the
mouse pointer, red while listening, a blue wave while thinking, and shrinks
away as the words land, with the blip it plays then - all as overlay.py and
sound.py do it.

    python tools\pitch_video.py --keyframes OUT_DIR
    python tools\pitch_video.py --keyframes OUT_DIR --tall
    python tools\pitch_video.py --frame 24.5 --out shot.png
    python tools\pitch_video.py --video OUT.mp4 [--tall]

--keyframes writes the storyboard's stills and a contact sheet of them.
--video draws every frame and hands it to ffmpeg, with the sound: the clip's
voice, a tap as the keys go down and up, and the blip as the words land.
The script itself lives in the owner's notes, not in the repository.
"""

import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from heyspeaky import glass, theme  # noqa: E402
from heyspeaky import panel as panel_module  # noqa: E402
from heyspeaky import languages  # noqa: E402
from heyspeaky import sound  # noqa: E402
from heyspeaky.mic import _level_from_chunk  # noqa: E402

CLIP = ROOT / "demo" / "four_languages.wav"
# The synthesised clip peaks at -1.4 dB; the owner's own dictations peak at
# -19 dB (the median of 633 in his log, 26 October 2026). Played at his
# loudness, the bars move the way they do for him instead of standing as a
# wall.
SPOKEN_PEAK_DB = -19.0
# The pill's window cuts off the bottom of its own shadow (alpha 46 of 255
# at the edge), which shows as a grey box on a light page. Drawn here with
# room for the whole shadow, as it should look once the app's margin is
# widened - remove this when it is.
SHADOW_ROOM = 40
TICK = 0.02           # the pill's own frame time (overlay.TICK_MS)
CHUNK = 512           # what the microphone hands the meter at a time
FPS = 30

PAPER = (247, 246, 243)
INK = (25, 25, 25)
GREY = (120, 119, 116)
FAINT = (199, 198, 194)
CARD = (255, 255, 255)
EDGE = (229, 228, 224)

# One colour per language, the pill rim's four stops in the order spoken.
# The colours are the video's annotation, not something the app draws.
SPOKEN = [
    ("English", theme.SIRI[0], "I already sent the invoice,"),
    ("Deutsch", theme.SIRI[1], "aber ich warte noch auf eine Antwort,"),
    ("Русский", theme.SIRI[2], "но клиент до сих пор не ответил,"),
    ("Қазақша", theme.SIRI[3], "сондықтан ертең қоңырау шаламын."),
]
# What OpenAI returned for the clip, split only where the language changes.
TYPED = [
    "I already sent the invoice,",
    "aber ich warte noch auf eine Antwort.",
    "Но клиент до сих пор не ответил.",
    "Сондықтан ертең қоңырау шаламын.",
]
# When each spoken word starts, in seconds into the clip, and when each
# language stops: whisper-1's word timestamps for the clip (26 October
# 2026). The joins between the four takes fall in the gaps between them.
WORD_STARTS = [
    [0.00, 0.56, 1.14, 1.60, 2.06],
    [2.60, 2.88, 3.10, 3.40, 3.76, 3.94, 4.20],
    [5.06, 5.28, 5.92, 6.58, 6.92, 7.20, 7.78],
    [8.74, 9.64, 10.04, 10.60],
]
SPANS = [(0.0, 2.53), (2.53, 4.87), (4.87, 8.53), (8.53, 11.1)]
# What whisper-1 itself wrote, in that same request: the Russian and the
# Kazakh spelled out in Latin letters.
WHISPER_HEARD = [
    "I already sent the invoice.",
    "Aber ich warte noch auf eine Antwort.",
    "No client do sikh por ni atvetil.",
    "Sondag dann. Yirtin kongrao shalaman.",
]
TRANSLATION = ("I already sent the invoice, but I'm still waiting for a "
               "reply. But the client still hasn't answered. So tomorrow "
               "I'll call.")

# -- the timeline -------------------------------------------------------------

PRESS = 8.35          # Ctrl+Alt goes down
PILL_IN = 8.55        # the pill shows, after the engage delay
CLIP_AT = 9.0         # the voice starts
THINK = 1.0           # the wait for OpenAI, shortened: no claim is made of it
HIDE_DELAY = 1.6      # overlay.hide_delay in config.py
FADE = 0.1            # the overlay's fade: steps of 0.16 every 16 ms
LOOKS = 26.0
PANEL = 29.5
END = 33.0
DURATION = 37.0

KEYFRAMES = [
    ("01-hook", 2.9),
    ("02-problem", 7.4),
    ("03-hold", 8.9),
    ("04-english", 10.4),
    ("05-german", 12.6),
    ("06-kazakh", 18.9),
    ("07-thinking", 20.9),
    ("08-landed", 25.0),
    ("09-looks", 28.6),
    ("10-languages", 32.4),
    ("11-end", 36.0),
]


# -- the clip -----------------------------------------------------------------

class Clip(object):
    """The demo recording, and what the pill would have made of it."""

    def __init__(self, path=CLIP):
        with wave.open(str(path), "rb") as source:
            self.rate = source.getframerate()
            raw = source.readframes(source.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
        peak = np.abs(samples).max() / 32768.0
        gain = 10 ** (SPOKEN_PEAK_DB / 20.0) / max(peak, 1e-6)
        self.samples = np.round(samples * gain).astype(np.int16)
        self.seconds = len(self.samples) / float(self.rate)
        self.spans = SPANS
        self.shown = self._shown()

    def _shown(self):
        """The pill's level, one value per tick: the meter's curve, then
        the overlay's easing - quick up, slow down."""
        shown, values = 0.0, []
        for tick in range(int((self.seconds + 2.0) / TICK)):
            end = int(tick * TICK * self.rate)
            level = 0.0
            if CHUNK <= end <= len(self.samples):
                level = _level_from_chunk(
                    self.samples[end - CHUNK:end].tobytes())
            target = max(0.0, min(1.0, level)) ** 0.62
            rate = 0.42 if target > shown else 0.16
            shown += (target - shown) * rate
            values.append(shown)
        return values

    def levels(self, at, count=theme.BARS):
        """The bars the pill shows `at` seconds into the clip, newest on
        the right. Before the voice they are dots."""
        newest = int(math.floor(at / TICK))
        out = []
        for tick in range(newest - count + 1, newest + 1):
            out.append(self.shown[tick] if 0 <= tick < len(self.shown)
                       else 0.0)
        return out

    def level(self, at):
        return self.levels(at, 1)[0]

    def words(self, at):
        """Which language is being spoken `at` seconds in, and how many of
        its words have begun."""
        for index, (_start, stop) in enumerate(self.spans):
            if at < stop or index == len(self.spans) - 1:
                begun = sum(1 for start in WORD_STARTS[index] if start <= at)
                return index, begun
        return len(SPOKEN) - 1, len(WORD_STARTS[-1])


# -- drawing helpers ----------------------------------------------------------

_FACES = {}
_FILES = {"regular": "segoeui.ttf", "semibold": "seguisb.ttf",
          "bold": "segoeuib.ttf", "light": "segoeuil.ttf",
          "italic": "segoeuii.ttf"}


def face(size, weight="regular"):
    key = (size, weight)
    if key not in _FACES:
        path = Path(glass._SYSTEM_FONTS) / _FILES[weight]
        try:
            _FACES[key] = ImageFont.truetype(str(path), size)
        except OSError:
            _FACES[key] = glass.font(size, medium=weight != "regular")
    return _FACES[key]


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def ease(share):
    share = clamp(share)
    return 1.0 - (1.0 - share) ** 3


def arrive(t, start, length=0.45):
    """0 before `start`, 1 once it has arrived, eased in between."""
    return ease((t - start) / length)


def fade_layer(layer, alpha):
    if alpha < 0.999:
        layer.putalpha(layer.getchannel("A").point(
            lambda value: int(value * alpha)))
    return layer


def text(canvas, xy, words, font, fill, alpha=1.0, rise=0.0, anchor="la"):
    """Draws text on its own layer, so it can fade and rise without
    cutting through what is under it."""
    if alpha <= 0.01 or not words:
        return
    x, y = xy
    box = font.getbbox(words, anchor=anchor)
    pad = 4
    width, height = box[2] - box[0] + pad * 2, box[3] - box[1] + pad * 2
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((pad - box[0], pad - box[1]), words,
                               font=font, fill=tuple(fill) + (255,),
                               anchor=anchor)
    fade_layer(layer, alpha)
    canvas.alpha_composite(layer, (int(round(x + box[0] - pad)),
                                   int(round(y + box[1] - pad + rise))))


def width_of(words, font):
    return font.getlength(words)


def wrap(words, font, limit):
    lines, line = [], ""
    for word in words.split():
        trial = word if not line else line + " " + word
        if line and width_of(trial, font) > limit:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def headline(words, font, limit, tall):
    """Wraps a headline. A "|" marks where the tall frame breaks it, so a
    line never ends on one word; the wide frame reads it as a space."""
    if not tall:
        return wrap(words.replace("|", " "), font, limit)
    out = []
    for part in words.split("|"):
        out.extend(wrap(part.strip(), font, limit))
    return out


def flow(parts, font, limit, leading):
    """Lays out (words, tag) parts as one paragraph. Returns every word's
    (x, y, word, tag), with x and y from the paragraph's top left."""
    placed, x, y = [], 0.0, 0.0
    space = width_of(" ", font)
    for words, tag in parts:
        for word in words.split():
            size = width_of(word, font)
            if x > 0 and x + size > limit:
                x, y = 0.0, y + leading
            placed.append((x, y, word, tag))
            x += size + space
    return placed


_CARDS = {}


def card_picture(size, radius, fill=CARD, edge=EDGE, shadow=0.09, blur=36,
                 drop=12):
    """A white card with a soft shadow, drawn large and brought down so the
    corners are smooth. Cached: cards keep their size while they move."""
    key = (size, radius, fill, edge, shadow, blur, drop)
    if key in _CARDS:
        return _CARDS[key]
    width, height = size
    pad = blur * 2
    whole = (width + pad * 2, height + pad * 2 + drop)
    mask = Image.new("L", whole, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (pad, pad + drop, pad + width, pad + drop + height), radius,
        fill=int(255 * shadow))
    mask = mask.filter(ImageFilter.GaussianBlur(blur / 2.0))
    picture = Image.new("RGBA", whole, (20, 18, 14, 0))
    picture.putalpha(mask)
    k = 3
    body = Image.new("RGBA", (width * k, height * k), (0, 0, 0, 0))
    drawing = ImageDraw.Draw(body)
    drawing.rounded_rectangle((0, 0, width * k - 1, height * k - 1),
                              radius * k, fill=edge + (255,))
    drawing.rounded_rectangle((2 * k, 2 * k, width * k - 1 - 2 * k,
                               height * k - 1 - 2 * k), (radius - 2) * k,
                              fill=fill + (255,))
    body = body.resize(size, Image.LANCZOS)
    picture.alpha_composite(body, (pad, pad))
    _CARDS[key] = (picture, pad)
    return _CARDS[key]


def card(canvas, box, radius=26, alpha=1.0, rise=0.0, **style):
    x0, y0, x1, y1 = box
    picture, pad = card_picture((x1 - x0, y1 - y0), radius, **style)
    if alpha < 0.999:
        picture = fade_layer(picture.copy(), alpha)
    canvas.alpha_composite(picture, (x0 - pad, int(round(y0 - pad + rise))))


def layer_over(canvas, image, x, y, alpha=1.0):
    if alpha <= 0.01:
        return
    if alpha < 0.999:
        image = fade_layer(image.copy(), alpha)
    canvas.alpha_composite(image, (int(round(x)), int(round(y))))


def marker(canvas, box, colour, share=1.0, strength=0.20):
    """A highlighter stroke behind words, wiped in from the left. On its own
    layer: drawn straight onto the frame it would replace the paper."""
    x0, y0, x1, y1 = box
    share = clamp(share)
    if share <= 0.01:
        return
    x1 = x0 + (x1 - x0) * share
    k = 3
    size = (max(1, int((x1 - x0) * k)), max(1, int((y1 - y0) * k)))
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), 8 * k,
        fill=tuple(colour) + (int(255 * strength),))
    layer = layer.resize((max(1, int(x1 - x0)), max(1, int(y1 - y0))),
                         Image.LANCZOS)
    canvas.alpha_composite(layer, (int(x0), int(y0)))


def squiggle(canvas, x, y, length, share=1.0, colour=(226, 60, 52)):
    """A wavy underline, drawn left to right as `share` runs to 1."""
    length *= clamp(share)
    if length < 2:
        return
    k = 3
    layer = Image.new("RGBA", (int(length + 4) * k, 12 * k), (0, 0, 0, 0))
    points = [(step * k, (6 + 2.6 * math.sin(step / 2.2)) * k)
              for step in range(int(length) + 1)]
    ImageDraw.Draw(layer).line(points, fill=colour + (255,), width=2 * k,
                               joint="curve")
    layer = layer.resize((int(length + 4), 12), Image.LANCZOS)
    canvas.alpha_composite(layer, (int(x), int(y - 6)))


def darker(colour, share=0.35):
    return tuple(int(c * (1 - share)) for c in colour)


_KEYS = {}


def keycap(label, pressed, scale=1.0):
    """A flat keycap. Pressed, the top drops into its lip."""
    key = (label, pressed, scale)
    if key in _KEYS:
        return _KEYS[key]
    k = 3
    width, height = int(150 * scale), int(112 * scale)
    lip = int((3 if pressed else 11) * scale)
    big = Image.new("RGBA", ((width + 40) * k, (height + 40) * k),
                    (0, 0, 0, 0))
    shadow = Image.new("L", big.size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle(
        (20 * k, 30 * k, (20 + width) * k, (20 + height + 6) * k), 22 * k,
        fill=40 if not pressed else 22)
    shadow = shadow.filter(ImageFilter.GaussianBlur(10 * k))
    shade = Image.new("RGBA", big.size, (20, 18, 14, 0))
    shade.putalpha(shadow)
    big.alpha_composite(shade)
    drawing = ImageDraw.Draw(big)
    top = 20 + (int(8 * scale) if pressed else 0)
    drawing.rounded_rectangle((20 * k, top * k, (20 + width) * k,
                               (20 + height) * k), 22 * k,
                              fill=(216, 214, 209, 255))
    drawing.rounded_rectangle((20 * k, top * k, (20 + width) * k,
                               (20 + height - lip) * k), 22 * k,
                              fill=(237, 236, 232, 255) if pressed
                              else (255, 255, 255, 255),
                              outline=(214, 212, 207, 255), width=2 * k)
    label_font = face(int(36 * scale * k), "semibold")
    drawing.text(((20 + width / 2.0) * k,
                  (top + (height - lip - (top - 20)) / 2.0) * k), label,
                 font=label_font, fill=INK + (255,), anchor="mm")
    _KEYS[key] = big.resize((width + 40, height + 40), Image.LANCZOS)
    return _KEYS[key]


_POINTERS = {}
# The Windows arrow, in its own 1-pixel units: tip at the top left.
ARROW = [(0, 0), (0, 16.5), (4.1, 12.6), (7.0, 19.2), (9.4, 18.2),
         (6.6, 11.7), (12.1, 11.7)]


def pointer_picture(scale):
    """The mouse pointer: white with a black edge and a soft shadow, the
    tip at (pad, pad) of the returned picture."""
    if scale in _POINTERS:
        return _POINTERS[scale]
    k = 4
    pad = int(round(6 * scale))
    unit = scale * k
    width = int(round(13 * scale)) + pad * 2
    height = int(round(20 * scale)) + pad * 2
    points = [(pad * k + x * unit, pad * k + y * unit) for x, y in ARROW]
    shadow = Image.new("L", (width * k, height * k), 0)
    ImageDraw.Draw(shadow).polygon(
        [(x + 1.2 * unit, y + 1.8 * unit) for x, y in points], fill=70)
    shadow = shadow.filter(ImageFilter.GaussianBlur(1.6 * unit))
    big = Image.new("RGBA", (width * k, height * k), (0, 0, 0, 0))
    big.putalpha(shadow)
    arrow = Image.new("RGBA", big.size, (0, 0, 0, 0))
    drawing = ImageDraw.Draw(arrow)
    drawing.polygon(points, fill=(255, 255, 255, 255))
    drawing.line(points + [points[0]], fill=(0, 0, 0, 255),
                 width=max(2, int(round(1.1 * unit))), joint="curve")
    big.alpha_composite(arrow)
    _POINTERS[scale] = (big.resize((width, height), Image.LANCZOS), pad)
    return _POINTERS[scale]


# -- the app's own pictures ---------------------------------------------------

class Pictures(object):
    """Everything drawn by glass.py, prepared once per size."""

    def __init__(self):
        self._glass = {}
        self._mono = {}
        self._panels = {}
        self._icon = {}

    def pill(self, scale, state, levels):
        key = (scale, state == "listening")
        if key not in self._glass:
            margin, theme.SHADOW_MARGIN = theme.SHADOW_MARGIN, SHADOW_ROOM
            try:
                self._glass[key] = glass.prepare(rim=key[1], scale=scale)
            finally:
                theme.SHADOW_MARGIN = margin
        return glass.paint(self._glass[key], state=state, levels=levels)

    def mono(self, scale, state, level, now, collapse=0.0):
        if scale not in self._mono:
            self._mono[scale] = glass.mono_prepare(scale)
        return glass.mono_paint(self._mono[scale], state, level, now,
                                collapse)

    def capsule(self, scale):
        """Where the capsule sits inside the mono window."""
        if scale not in self._mono:
            self._mono[scale] = glass.mono_prepare(scale)
        return self._mono[scale].box

    def panel(self, scale, mono=False):
        key = (scale, mono)
        if key not in self._panels:
            yours = ["kk", "ru", "de", "en"]
            catalog = languages.catalog(yours)
            model = {"status": "Ready", "state": "ready", "paused": False,
                     "pinned": "", "yours": yours, "backend": "cloud",
                     "usage": "", "update": "", "key": "saved",
                     "catalog": list(catalog), "look": "mono" if mono
                     else "glass",
                     "names": dict((c, languages.name(c)) for c in catalog)}
            size, items = panel_module.layout(model, scale)
            picture = glass.panel_card(size[0], size[1], scale, mono=mono)
            self._panels[key] = glass.panel_frame(picture, items, scale,
                                                  mono=mono)
        return self._panels[key]

    def icon(self, size):
        if size not in self._icon:
            self._icon[size] = glass.app_icon(size)
        return self._icon[size]


# -- the shots ----------------------------------------------------------------

class Stage(object):
    def __init__(self, tall=False):
        self.tall = tall
        self.size = (1080, 1920) if tall else (1920, 1080)
        self.clip = Clip()
        self.pictures = Pictures()
        self.release = CLIP_AT + self.clip.seconds + 0.35
        # The words land, then the tick, which holds for the hide delay.
        self.land = self.release + THINK
        self.done = self.land + 0.05
        self.gone = self.done + HIDE_DELAY
        # Mono has no tick to hold: it shrinks away the moment it is done.
        self.collapsed = self.done + theme.MONO_COLLAPSE

    def frame(self, t):
        canvas = Image.new("RGBA", self.size, PAPER + (255,))
        if t < 3.4:
            self.hook(canvas, t)
        elif t < PRESS - 0.35:
            self.problem(canvas, t)
        elif t < LOOKS:
            self.demo(canvas, t)
        elif t < PANEL:
            self.looks(canvas, t)
        elif t < END:
            self.languages(canvas, t)
        else:
            self.end(canvas, t)
        return canvas.convert("RGB")

    # 0.0 - 3.4: the claim, in two lines.
    def hook(self, canvas, t):
        width, height = self.size
        big = face(98 if self.tall else 96, "semibold")
        left = 90 if self.tall else 150
        limit = width - left * 2
        rows = headline("You switch|languages|mid-sentence.", big, limit,
                     self.tall)
        leading = int(big.size * 1.18)
        top = (720 if self.tall else 380)
        start, gap = 0.2, 0.09
        word_index = 0
        for row, line in enumerate(rows):
            x = left
            for word in line.split():
                share = arrive(t, start + word_index * gap, 0.35)
                text(canvas, (x, top + row * leading), word, big, INK,
                     share, (1 - share) * 22)
                x += width_of(word + " ", big)
                word_index += 1
        second = face(98 if self.tall else 96, "semibold")
        below = top + len(rows) * leading + (40 if self.tall else 20)
        for row, line in enumerate(headline(
                "Your dictation|makes you pick one.", second, limit,
                self.tall)):
            share = arrive(t, 1.55 + row * 0.12, 0.45)
            text(canvas, (left, below + row * leading), line, second, GREY,
                 share, (1 - share) * 22)

    # 3.4 - 8.0: the same sentence, through a model that keeps one language.
    def problem(self, canvas, t):
        width, height = self.size
        t0 = 3.4
        title = face(80 if self.tall else 72, "semibold")
        head = (90, 260) if self.tall else (150, 120)
        share = arrive(t, t0 + 0.05)
        for row, line in enumerate(headline("Four languages.|One breath.",
                                         title, width - 180, self.tall)):
            text(canvas, (head[0], head[1] + row * 96), line, title, INK,
                 share, (1 - share) * 18)

        box = (60, 480, 1020, 1280) if self.tall else (180, 250, 1740, 830)
        lift = arrive(t, t0 + 0.2, 0.5)
        rise = (1 - lift) * 30
        card(canvas, box, 30, lift, rise)
        if lift < 0.05:
            return
        inset = 60 if self.tall else 70
        x = box[0] + inset
        limit = box[2] - box[0] - inset * 2
        label = face(28, "semibold")
        body = face(42 if self.tall else 44)
        leading = int(body.size * 1.42)

        y = box[1] + 56
        text(canvas, (x, y + rise), "You said", label, GREY, lift)
        y += 58
        parts = [(words, index) for index, (_name, _c, words)
                 in enumerate(SPOKEN)]
        placed = flow(parts, body, limit, leading)
        self._highlights(canvas, placed, x, y + rise, body, leading,
                         [t0 + 0.8 + i * 0.35 for i in range(4)], t)
        for px, py, word, _tag in placed:
            text(canvas, (x + px, y + py + rise), word, body, INK, lift)
        y += placed[-1][1] + leading + 34

        rule = Image.new("RGBA", (limit, 2), EDGE + (255,))
        layer_over(canvas, rule, x, y + rise, lift)
        y += 44

        later = arrive(t, t0 + 2.2, 0.45)
        text(canvas, (x, y + rise), "Whisper heard", label, GREY, later)
        y += 58
        parts = [(words, index) for index, words in enumerate(WHISPER_HEARD)]
        placed = flow(parts, body, limit, leading)
        for px, py, word, _tag in placed:
            text(canvas, (x + px, y + py + rise), word, body, INK, later,
                 (1 - later) * 12)
        # A spelling checker's red line under what is not a word at all.
        wrong = arrive(t, t0 + 2.9, 0.6)
        for px, py, word, tag in placed:
            if tag >= 2:
                squiggle(canvas, x + px, y + py + rise + body.size * 1.22,
                         width_of(word, body), wrong)

        note = face(24 if not self.tall else 26)
        footnote = ("OpenAI's whisper-1 on the same 11-second clip, "
                    "demo/four_languages.wav in the repository")
        noted = arrive(t, t0 + 3.2, 0.5)
        lines = wrap(footnote, note, box[2] - box[0] - 20)
        for row, line in enumerate(lines):
            text(canvas, (box[0] + 10, box[3] + 34 + row * 36), line, note,
                 GREY, noted)

    def _highlights(self, canvas, placed, x, y, font, leading, starts, t):
        """One marker stroke per language per line, wiped in in turn."""
        runs = []
        for px, py, word, tag in placed:
            right = px + width_of(word, font)
            if runs and runs[-1][0] == tag and runs[-1][2] == py:
                runs[-1][3] = right
            else:
                runs.append([tag, px, py, right])
        for tag, left, top, right in runs:
            share = (t - starts[tag]) / 0.35
            colour = SPOKEN[tag][1]
            ascent = font.getbbox("Ay")[1]
            marker(canvas, (x + left - 8, y + top + ascent - 6,
                            x + right + 8, y + top + font.size * 1.18),
                   colour, ease(share))

    # 8.0 - 26.0: hold, talk, let go - one continuous shot.
    def demo(self, canvas, t):
        width, height = self.size
        start = PRESS - 0.35
        enter = arrive(t, start, 0.4)

        # The headline changes with what the hands are doing.
        heads = [(start, "Hold Ctrl+Alt."),
                 (CLIP_AT - 0.1, "Talk. Switch|languages whenever."),
                 (self.release, "Let go.|It's typed where you were.")]
        title = face(72 if self.tall else 64, "semibold")
        head = (80, 170) if self.tall else (150, 96)
        for index, (when, words) in enumerate(heads):
            until = heads[index + 1][0] if index + 1 < len(heads) else 1e9
            if not when <= t < until + 0.2:
                continue
            share = arrive(t, when, 0.35) * (1 - arrive(t, until, 0.2))
            for row, line in enumerate(headline(words, title, width - 160,
                                             self.tall)):
                text(canvas, (head[0], head[1] + row * 88), line, title, INK,
                     share, (1 - arrive(t, when, 0.35)) * 16)

        # The window being typed into.
        # Tall, the window takes the room the docked glass pill used to:
        # Mono sits inside it, over the pointer.
        box = (60, 400, 1020, 1100) if self.tall else (260, 220, 1660, 690)
        card(canvas, box, 22, enter, (1 - enter) * 24)
        rise = (1 - enter) * 24
        bar = face(24)
        text(canvas, (box[0] + 30, box[1] + 22 + rise), "Notes", bar, GREY,
             enter)
        self._window_controls(canvas, box, rise, enter)
        rule = Image.new("RGBA", (box[2] - box[0] - 4, 2), EDGE + (255,))
        layer_over(canvas, rule, box[0] + 2, box[1] + 70 + rise, enter)

        body = face(42 if self.tall else 44)
        leading = int(body.size * 1.45)
        x, y = box[0] + 56, box[1] + 112 + rise
        limit = box[2] - box[0] - 112
        landed = t >= self.land
        caret_at = (x, y)
        if landed:
            parts = [(words, index) for index, words in enumerate(TYPED)]
            placed = flow(parts, body, limit, leading)
            self._highlights(canvas, placed, x, y, body, leading,
                             [self.land + 1.0 + i * 0.3 for i in range(4)],
                             t)
            for px, py, word, _tag in placed:
                text(canvas, (x + px, y + py), word, body, INK)
            last = placed[-1]
            caret_at = (x + last[0] + width_of(last[2], body) + 6,
                        y + last[1])
        blink = int((t - start) / theme.CARET_BLINK) % 2 == 0
        if blink and enter > 0.5:
            caret = Image.new("RGBA", (3, int(body.size * 1.2)), INK + (255,))
            layer_over(canvas, caret, caret_at[0], caret_at[1] + 6, enter)

        self._keys(canvas, t, enter)
        self._speech(canvas, t, box)
        self._legend(canvas, t, box)
        self._mono_pill(canvas, t, box)
        self._pointer(canvas, t, box, enter)

    # The pointer comes to rest in the window just before the keys go down;
    # Mono appears over it, where it was when the recording began.
    POINTER_ARRIVES = PRESS - 0.3
    POINTER_GLIDE = 0.35

    def _ui_scale(self):
        """How much bigger than on screen the app is drawn: the pill's own."""
        return self._pill_scale()

    def _pointer_rest(self, box):
        if self.tall:
            return (box[2] - 250, box[3] - 46)
        return (box[2] - 330, box[3] - 44)

    def _pointer_at(self, t, box):
        rest = self._pointer_rest(box)
        share = arrive(t, self.POINTER_ARRIVES, self.POINTER_GLIDE)
        start = (rest[0] + 180, rest[1] + 150)
        return (start[0] + (rest[0] - start[0]) * share,
                start[1] + (rest[1] - start[1]) * share)

    def _pointer(self, canvas, t, box, enter):
        shown = clamp((t - (self.POINTER_ARRIVES - 0.1)) / 0.15) * enter
        if shown <= 0.01:
            return
        picture, pad = pointer_picture(self._ui_scale())
        x, y = self._pointer_at(t, box)
        layer_over(canvas, picture, x - pad, y - pad, shown)

    def _mono_pill(self, canvas, t, box):
        if t < PILL_IN or t >= self.collapsed:
            return
        scale = self._ui_scale()
        if t < self.release:
            state = "listening"
            level = self.clip.level(t - CLIP_AT) if t >= CLIP_AT else 0.0
        else:
            state = "transcribing"
            level = 0.0
        collapse = clamp((t - self.done) / theme.MONO_COLLAPSE) \
            if t >= self.done else 0.0
        picture = self.pictures.mono(scale, state, level, t - PILL_IN,
                                     collapse)
        # Placed as overlay._place_at_pointer does it: the capsule's centre
        # MONO_POINTER_RIGHT points right of the tip, its bottom
        # MONO_POINTER_ABOVE points above it. In as the overlay brings it.
        tip = self._pointer_rest(box)
        left, top, right, bottom = self.pictures.capsule(scale)
        x = tip[0] + theme.MONO_POINTER_RIGHT * scale - (left + right) / 2.0
        y = tip[1] - theme.MONO_POINTER_ABOVE * scale - bottom
        share = clamp((t - PILL_IN) / FADE)
        lift = int(round(10 * scale * (1 - share)))
        layer_over(canvas, picture, x, y + lift, share)

    def _window_controls(self, canvas, box, rise, alpha):
        layer = Image.new("RGBA", (150, 40), (0, 0, 0, 0))
        drawing = ImageDraw.Draw(layer)
        colour = GREY + (255,)
        drawing.line((8, 20, 26, 20), fill=colour, width=2)
        drawing.rectangle((60, 11, 78, 29), outline=colour, width=2)
        drawing.line((114, 11, 132, 29), fill=colour, width=2)
        drawing.line((114, 29, 132, 11), fill=colour, width=2)
        layer_over(canvas, layer, box[2] - 172, box[1] + 15 + rise, alpha)

    def _keys(self, canvas, t, enter):
        pressed = PRESS <= t < self.release
        shown = enter * (1 - arrive(t, self.release + 0.6, 0.4))
        if shown <= 0.01:
            return
        scale = 1.0 if self.tall else 0.9
        if self.tall:
            x, y = 540 - 175, 1690
        else:
            x, y = 130, 870
        for index, label in enumerate(("Ctrl", "Alt")):
            picture = keycap(label, pressed, scale)
            layer_over(canvas, picture, x + index * int(175 * scale), y,
                       shown)

    def _pill_scale(self):
        return 2.6 if self.tall else 2.4

    def _pill_place(self, picture):
        width, height = self.size
        x = (width - picture.width) // 2
        y = (1380 if self.tall else height - picture.height - 24)
        return x, y

    def _pill(self, canvas, t):
        if t < PILL_IN or t > self.gone + FADE:
            return
        scale = self._pill_scale()
        at = t - CLIP_AT
        if t < self.release:
            picture = self.pictures.pill(scale, "listening",
                                         self.clip.levels(at))
        elif t < self.done:
            picture = self.pictures.pill(scale, "transcribing",
                                         [0.0] * theme.BARS)
        else:
            picture = self.pictures.pill(scale, "done", None)
        # In as the overlay does it: a fade and a short slide up.
        share = clamp((t - PILL_IN) / FADE)
        lift = int(round(10 * scale * (1 - share)))
        if t > self.gone:
            share = 1 - clamp((t - self.gone) / FADE)
        x, y = self._pill_place(picture)
        layer_over(canvas, picture, x, y + lift, share)

    def _speech(self, canvas, t, box):
        """What is being said, a language at a time, above the pill."""
        at = t - CLIP_AT
        if at < 0 or t > self.release + 0.25:
            return
        alpha = 1 - arrive(t, self.release, 0.25)
        index, said = self.clip.words(at)
        name, colour, words = SPOKEN[index]
        since = at - self.clip.spans[index][0]
        share = arrive(since, 0.0, 0.18) * alpha
        size = 40 if self.tall else 38
        body = face(size)
        chip_font = face(size - 12, "semibold")
        chip_w = int(width_of(name, chip_font) + 64)
        chip_h = int(size * 1.3)
        gap = 22
        if self.tall:
            lines = wrap(words, body, 940)
            top = box[3] + 110
            centre = 540
            self._chip(canvas, (centre - chip_w // 2, top), chip_w, chip_h,
                       name, colour, chip_font, share)
            top += chip_h + 34
            spoken = 0
            for row, line in enumerate(lines):
                line_w = width_of(line, body)
                lx = centre - line_w / 2.0
                for word in line.split():
                    ink = INK if spoken < said else FAINT
                    text(canvas, (lx, top + row * int(size * 1.4)), word,
                         body, ink, share, (1 - share) * 10)
                    lx += width_of(word + " ", body)
                    spoken += 1
            return
        total = chip_w + gap + width_of(words, body)
        lx = (self.size[0] - total) / 2.0
        top = box[3] + 66
        self._chip(canvas, (lx, top - 4), chip_w, chip_h, name, colour,
                   chip_font, share)
        lx += chip_w + gap
        for count, word in enumerate(words.split()):
            ink = INK if count < said else FAINT
            text(canvas, (lx, top), word, body, ink, share, (1 - share) * 10)
            lx += width_of(word + " ", body)

    def _chip(self, canvas, xy, width, height, name, colour, font, alpha):
        if alpha <= 0.01:
            return
        k = 3
        layer = Image.new("RGBA", (width * k, height * k), (0, 0, 0, 0))
        drawing = ImageDraw.Draw(layer)
        drawing.rounded_rectangle((0, 0, width * k - 1, height * k - 1),
                                  height * k // 2,
                                  fill=tuple(colour) + (38,))
        dot = height * k * 0.28
        cx, cy = height * k * 0.55, height * k / 2.0
        drawing.ellipse((cx - dot / 2, cy - dot / 2, cx + dot / 2,
                         cy + dot / 2), fill=tuple(colour) + (255,))
        layer = layer.resize((width, height), Image.LANCZOS)
        fade_layer(layer, alpha)
        canvas.alpha_composite(layer, (int(xy[0]), int(xy[1])))
        text(canvas, (xy[0] + height * 0.95, xy[1] + height / 2.0), name,
             font, darker(colour), alpha, anchor="lm")

    def _legend(self, canvas, t, box):
        """Once the words have landed: the four languages, and what the
        sentence means for anyone who reads none of them."""
        start = self.land + 0.9
        if t < start:
            return
        size = 30 if self.tall else 30
        chip_font = face(size - 4, "semibold")
        chip_h = int(size * 1.5)
        widths = [int(width_of(name, chip_font) + 64) for name, _c, _w
                  in SPOKEN]
        arrow = face(size, "light")
        gap = 46
        top = box[3] + (90 if self.tall else 56)
        if self.tall:
            rows = [[0, 1], [2, 3]]
        else:
            rows = [[0, 1, 2, 3]]
        for row_index, row in enumerate(rows):
            total = sum(widths[i] for i in row) + gap * (len(row) - 1)
            x = (self.size[0] - total) / 2.0
            y = top + row_index * (chip_h + 22)
            for place, index in enumerate(row):
                share = arrive(t, start + index * 0.3, 0.35)
                name, colour, _words = SPOKEN[index]
                self._chip(canvas, (x, y + (1 - share) * 10), widths[index],
                           chip_h, name, colour, chip_font, share)
                x += widths[index]
                if index < len(SPOKEN) - 1:
                    text(canvas, (x + gap / 2.0, y + chip_h / 2.0), "→",
                         arrow, FAINT, arrive(t, start + index * 0.3 + 0.2),
                         anchor="mm")
                x += gap
        note = face(26, "italic")
        below = top + len(rows) * (chip_h + 22) + 24
        lines = wrap('"' + TRANSLATION + '"', note,
                     940 if self.tall else 1400)
        for row, line in enumerate(lines):
            text(canvas, (self.size[0] / 2.0, below + row * 38), line, note,
                 GREY, arrive(t, start + 1.4, 0.5), anchor="ma")

    # 26.0 - 29.5: the two looks, side by side.
    def looks(self, canvas, t):
        width, height = self.size
        t0 = LOOKS
        title = face(84 if self.tall else 80, "semibold")
        sub = face(40 if self.tall else 38)
        top = 300 if self.tall else 150
        share = arrive(t, t0 + 0.05)
        text(canvas, (width / 2.0, top), "Two looks.", title, INK, share,
             (1 - share) * 18, anchor="ma")
        text(canvas, (width / 2.0, top + 120), "Mono, or Glass. Pick one in "
             "the tray.", sub, GREY, arrive(t, t0 + 0.4), anchor="ma")

        at = (t - t0) + 1.2      # the clip again, from its first words
        level = self.clip.level(at)
        glass_scale = 3.0 if self.tall else 2.2
        pill = self.pictures.pill(glass_scale, "listening",
                                  self.clip.levels(at))
        mono = self.pictures.mono(3.4 if self.tall else 2.8, "listening",
                                  level, t)
        label = face(32, "semibold")
        if self.tall:
            spots = [(width / 2.0, 820), (width / 2.0, 1300)]
        else:
            spots = [(width * 0.30, 600), (width * 0.72, 600)]
        for index, (picture, name) in enumerate(((mono, "Mono"),
                                                 (pill, "Glass"))):
            share = arrive(t, t0 + 0.6 + index * 0.25, 0.45)
            cx, cy = spots[index]
            layer_over(canvas, picture, cx - picture.width / 2.0,
                       cy - picture.height / 2.0 + (1 - share) * 24, share)
            text(canvas, (cx, cy + 150), name, label, GREY, share,
                 anchor="ma")

    # 29.5 - 33.0: the tray panel, and how many languages it has.
    def languages(self, canvas, t):
        width, height = self.size
        t0 = PANEL
        title = face(96 if self.tall else 92, "semibold")
        sub = face(42 if self.tall else 40)
        count = len(languages.catalog([]))
        if self.tall:
            left, top = 90, 200
        else:
            left, top = 150, 360
        share = arrive(t, t0 + 0.05)
        text(canvas, (left, top), "{} languages.".format(count), title, INK,
             share, (1 - share) * 18)
        for row, line in enumerate(wrap("Yours go first, in the order you "
                                        "choose.", sub,
                                        900 if self.tall else 700)):
            text(canvas, (left, top + 130 + row * 58), line, sub, GREY,
                 arrive(t, t0 + 0.4))

        # The panel in the mono look, as it is on the owner's PC.
        picture = self.pictures.panel(1.9 if self.tall else 1.5, mono=True)
        lift = arrive(t, t0 + 0.3, 0.55)
        if self.tall:
            x = (width - picture.width) / 2.0
            y = height - picture.height - 40
        else:
            x = width - picture.width - 150
            y = (height - picture.height) / 2.0
        layer_over(canvas, picture, x, y + (1 - lift) * 60, lift)

    # 33.0 - 37.0: the name, the address, and what it costs.
    def end(self, canvas, t):
        width, height = self.size
        t0 = END
        centre = width / 2.0
        top = 560 if self.tall else 190
        icon = self.pictures.icon(200)
        share = arrive(t, t0 + 0.05, 0.5)
        layer_over(canvas, icon, centre - 100, top + (1 - share) * 20, share)
        name = face(132 if self.tall else 120, "semibold")
        text(canvas, (centre, top + 250), "HeySpeaky", name, INK,
             arrive(t, t0 + 0.2), anchor="ma")
        line = face(40 if self.tall else 40)
        tagline = ["Hold Ctrl+Alt and talk,", "in every language you speak."]
        if not self.tall:
            tagline = [" ".join(tagline)]
        for row, words in enumerate(tagline):
            text(canvas, (centre, top + 420 + row * 56), words, line, GREY,
                 arrive(t, t0 + 0.5), anchor="ma")
        url = face(40, "semibold")
        place = top + (600 if self.tall else 530)
        text(canvas, (centre, place), "github.com/Maslitsa/HeySpeaky", url, INK,
             arrive(t, t0 + 0.9), anchor="ma")
        small = face(26)
        notes = ["Free and open source (MIT) · Windows",
                 "Transcribes with OpenAI on your own key, or offline on "
                 "your laptop"]
        for row, words in enumerate(notes):
            for sub_row, piece in enumerate(wrap(words, small,
                                                 940 if self.tall else 1500)):
                text(canvas, (centre, place + 90 + row * 44 + sub_row * 38),
                     piece, small, GREY, arrive(t, t0 + 1.2 + row * 0.2),
                     anchor="ma")


def contact_sheet(stills, out, tall):
    """The storyboard on one page: every still, its time and its name."""
    columns = 4 if tall else 3
    thumb = (270, 480) if tall else (560, 315)
    gap, caption = 24, 34
    rows = int(math.ceil(len(stills) / float(columns)))
    page = Image.new("RGB", (columns * (thumb[0] + gap) + gap,
                             rows * (thumb[1] + caption + gap) + gap),
                     (232, 231, 227))
    drawing = ImageDraw.Draw(page)
    label = face(20, "semibold")
    for index, (name, at, image) in enumerate(stills):
        x = gap + (index % columns) * (thumb[0] + gap)
        y = gap + (index // columns) * (thumb[1] + caption + gap)
        drawing.text((x, y), "{:>5.1f} s   {}".format(at, name[3:]),
                     font=label, fill=INK)
        page.paste(image.resize(thumb, Image.LANCZOS), (x, y + caption))
    page.save(out)
    return out


# -- the sound and the film ---------------------------------------------------

AUDIO_RATE = sound.RATE


def voice_samples(name):
    """One of the app's own sounds, built by sound.py, at full scale."""
    return np.array(sound._samples(sound.VOICES[name], 1.0),
                    dtype=np.float64) / 32767.0


# The music under the film, written here as numbers like sound.py's voices,
# so there is nothing to license. Four chords in G at 100 beats a minute, a
# soft pad and a mallet picking out the chord. Mono's blip is two notes near
# B4 and E5, which belong to this key, so it lands inside the music.
BEAT = 60.0 / 100.0
CHORD_BEATS = 8
# (pad notes, mallet notes), in Hz.
CHORDS = [
    ([98.00, 246.94, 293.66, 369.99], [392.00, 493.88, 587.33, 739.99]),
    ([82.41, 196.00, 246.94, 293.66], [329.63, 392.00, 493.88, 587.33]),
    ([130.81, 164.81, 196.00, 246.94], [329.63, 392.00, 493.88, 523.25]),
    ([146.83, 220.00, 293.66, 329.63], [293.66, 329.63, 440.00, 587.33]),
]
# Which mallet note on which eighth of a chord's two bars; None is a rest.
PATTERN = [0, None, 2, 1, None, 3, 2, None,
           0, None, 2, 3, None, 1, 2, None]
VOICE_DUCK = 0.18     # the music under the voice, as a share of itself


def _tone(freqs, seconds, attack, decay, gain):
    """Sines that start softly and fade: the pad and the mallet's body."""
    t = np.arange(int(seconds * AUDIO_RATE)) / float(AUDIO_RATE)
    envelope = np.exp(-t / decay)
    if attack > 0:
        ramp = np.minimum(1.0, t / attack)
        envelope *= 0.5 - 0.5 * np.cos(np.pi * ramp)
    out = np.zeros_like(t)
    for freq in freqs:
        out += np.sin(2 * np.pi * freq * t)
    return out * envelope * gain


def _mallet(freq, seconds=0.9):
    """A soft mallet: the note dying away, and a click of the fourth
    harmonic at the very start that sounds like wood being struck."""
    body = _tone([freq], seconds, 0.003, 0.32, 1.0)
    click = _tone([freq * 4.0], seconds, 0.001, 0.025, 0.22)
    return body + click


def music(total, duck_from, duck_to, end_at):
    """Stereo music for `total` samples, quieter under the voice and
    settling on the first chord for the end card."""
    left, right = np.zeros(total), np.zeros(total)

    def add(samples, at, pan=0.0):
        start = int(round(at * AUDIO_RATE))
        end = min(total, start + len(samples))
        if end <= start:
            return
        piece = samples[:end - start]
        left[start:end] += piece * (1.0 - pan) * 0.5 * 2 ** 0.5
        right[start:end] += piece * (1.0 + pan) * 0.5 * 2 ** 0.5

    chord_seconds = CHORD_BEATS * BEAT
    at, index = 0.0, 0
    while at < end_at:
        pad, mallet = CHORDS[index % len(CHORDS)]
        add(_tone(pad, chord_seconds + 1.6, 0.9, 2.6, 0.11), at)
        for step, note in enumerate(PATTERN):
            when = at + step * BEAT / 2.0
            if note is None or when >= end_at:
                continue
            add(_mallet(mallet[note]) * 0.22, when,
                pan=0.35 if step % 4 < 2 else -0.35)
        at += chord_seconds
        index += 1
    # The end card: the first chord, held and let go.
    pad, mallet = CHORDS[0]
    add(_tone(pad, DURATION - end_at + 1.0, 0.05, 2.2, 0.14), end_at)
    for offset, note in enumerate((0, 1, 2, 3)):
        add(_mallet(mallet[note], 2.5) * 0.20, end_at + offset * 0.09,
            pan=(-0.3, -0.1, 0.1, 0.3)[offset])

    t = np.arange(total) / float(AUDIO_RATE)
    # Down under the voice and back, each over half a second.
    into = np.clip((t - (duck_from - 0.5)) / 0.5, 0.0, 1.0)
    out_of = np.clip((t - duck_to) / 0.5, 0.0, 1.0)
    duck = 1.0 - (1.0 - VOICE_DUCK) * into * (1.0 - out_of)
    # In from nothing at the start, out to nothing at the very end.
    fade = np.clip(t / 0.6, 0.0, 1.0) * np.clip((DURATION - t) / 0.8, 0.0, 1.0)
    return np.stack([left, right], axis=1) * (duck * fade)[:, None]


def soundtrack(stage):
    """The film's sound, in stereo: music from the first frame, the clip's
    voice where it is spoken, a tap as the keys go down and up, Mono's blip
    the moment the words land, and a soft pop as each language is named."""
    total = int(DURATION * AUDIO_RATE) + 1
    out = music(total, CLIP_AT, stage.release, END)

    def put(samples, at, gain):
        start = int(round(at * AUDIO_RATE))
        end = min(total, start + len(samples))
        if end > start:
            out[start:end] += (samples[:end - start] * gain)[:, None]

    with wave.open(str(CLIP), "rb") as source:
        rate = source.getframerate()
        raw = np.frombuffer(source.readframes(source.getnframes()),
                            dtype=np.int16).astype(np.float64) / 32768.0
    times = np.arange(int(len(raw) * AUDIO_RATE / rate)) / float(AUDIO_RATE)
    voice = np.interp(times, np.arange(len(raw)) / float(rate), raw)
    put(voice / (np.abs(voice).max() or 1.0), CLIP_AT, 1.3)
    tap = voice_samples("tap")
    put(tap, PRESS, 0.45)
    put(tap, stage.release, 0.30)
    put(voice_samples("blip"), stage.done, 0.70)
    pop = _tone([1046.5], 0.25, 0.002, 0.045, 0.16)
    for index in range(len(SPOKEN)):
        put(pop, stage.land + 0.9 + index * 0.3, 1.0)
    # A soft limiter rather than turning everything down for the voice's
    # few loud peaks: as loud as a video on the web, and never past -1 dB,
    # which clips on some phones.
    return 0.89 * np.tanh(out / 0.89)


def write_wav(path, samples):
    """16-bit stereo, or mono if handed one channel."""
    channels = 1 if samples.ndim == 1 else samples.shape[1]
    data = np.round(np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(AUDIO_RATE)
        handle.writeframes(data.tobytes())
    return path


def render_video(stage, out, fps=FPS):
    """Every frame, straight into ffmpeg, with the sound beside it."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is not on PATH")
    folder = tempfile.mkdtemp(prefix="pitch-")
    track = write_wav(os.path.join(folder, "sound.wav"), soundtrack(stage))
    width, height = stage.size
    command = [ffmpeg, "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", "{}x{}".format(width, height), "-r", str(fps),
               "-i", "-", "-i", track,
               "-c:v", "libx264", "-preset", "slow", "-crf", "18",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
               "-shortest", "-movflags", "+faststart", str(out)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    frames = int(round(DURATION * fps))
    began = time.time()
    try:
        for index in range(frames):
            process.stdin.write(stage.frame(index / float(fps)).tobytes())
            if index and index % (fps * 5) == 0:
                print("  {:>4.0f} s of {:.0f}, {:.0f} s so far".format(
                    index / float(fps), DURATION, time.time() - began))
    finally:
        process.stdin.close()
        process.wait()
        shutil.rmtree(folder, ignore_errors=True)
    if process.returncode:
        raise SystemExit("ffmpeg failed with {}".format(process.returncode))
    return out


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Draw the pitch video")
    parser.add_argument("--tall", action="store_true",
                        help="9:16 instead of 16:9")
    parser.add_argument("--keyframes", metavar="DIR",
                        help="write the storyboard's stills here")
    parser.add_argument("--frame", type=float, metavar="SECONDS",
                        help="draw one moment")
    parser.add_argument("--out", default="frame.png")
    parser.add_argument("--video", metavar="MP4",
                        help="draw the whole film, with its sound")
    args = parser.parse_args()

    stage = Stage(tall=args.tall)
    print("clip {:.2f} s, languages at {}".format(
        stage.clip.seconds,
        ", ".join("{:.2f}-{:.2f}".format(a, b) for a, b in stage.clip.spans)))
    if args.frame is not None:
        stage.frame(args.frame).save(args.out)
        print(args.out)
        return 0
    if args.video:
        print(render_video(stage, args.video))
        return 0
    if args.keyframes:
        folder = Path(args.keyframes)
        folder.mkdir(parents=True, exist_ok=True)
        shape = "9x16" if args.tall else "16x9"
        stills = []
        for name, at in KEYFRAMES:
            image = stage.frame(at)
            image.save(folder / "{}-{}.png".format(shape, name))
            stills.append((name, at, image))
        print(contact_sheet(stills, folder / "{}-storyboard.png".format(shape),
                            args.tall))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
