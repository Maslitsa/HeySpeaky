"""Draws the pill as a piece of frosted glass.

Windows will not blur what is behind a click-through, always-on-top window:
that composition path and a layered transparent window do not mix. So the pill
takes a picture of the desktop underneath itself the moment before it appears,
blurs that, and shows it as its own background. The result is real glass over
the real wallpaper, and it costs one screen grab per appearance.

The expensive half of a frame - the blurred wallpaper, the shadow, the glass
edge, Siri's rim light - does not change while the pill is on screen, so
prepare() builds it once and keeps it. Each frame then paints only the dot,
the waveform and the text onto a copy. Measured on this laptop, a whole frame
took 39 ms; this way it is a few, which leaves the processor free for
recording.

The costly parts are drawn at twice the size and scaled down, because Tk has
no antialiasing and hard edges on a rounded pill are what make a window look
cheap.
"""

import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from . import theme

SS = 2

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BUNDLED_FONTS = os.path.join(_ROOT, "assets", "fonts")
_SYSTEM_FONTS = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")

_REGULAR = ("Inter-Regular.ttf", "segoeui.ttf", "arial.ttf")
_MEDIUM = ("Inter-Medium.ttf", "Inter-SemiBold.ttf", "seguisb.ttf",
           "segoeuib.ttf", "arialbd.ttf")

_font_cache = {}
_sprite_cache = {}


def font(size, medium=False):
    """Inter if it is bundled, otherwise whatever Windows already has."""
    key = (size, medium)
    if key in _font_cache:
        return _font_cache[key]
    names = _MEDIUM if medium else _REGULAR
    for folder in (_BUNDLED_FONTS, _SYSTEM_FONTS):
        for name in names:
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            try:
                _font_cache[key] = ImageFont.truetype(path, size)
                return _font_cache[key]
            except OSError:
                continue
    _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def _rounded(size, radius):
    image = Image.new("L", size, 0)
    ImageDraw.Draw(image).rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return image


def _vertical_gradient(size, top, bottom):
    """A ramp from top to bottom, for the bright glass edge."""
    height = size[1]
    ramp = Image.new("L", (1, height))
    pixels = ramp.load()
    for y in range(height):
        share = y / float(max(1, height - 1))
        pixels[0, y] = int(round(255 * (top + (bottom - top) * share)))
    return ramp.resize(size, Image.BILINEAR)


def _siri_colour(position):
    """A colour from Siri's palette, position running 0 to 1 across the row."""
    stops = theme.SIRI
    scaled = position * (len(stops) - 1)
    index = min(int(scaled), len(stops) - 2)
    share = scaled - index
    first, second = stops[index], stops[index + 1]
    return tuple(int(round(first[i] + (second[i] - first[i]) * share))
                 for i in range(3))


def sprite(size, radius, colour):
    """A rounded shape with smooth edges, drawn once and then reused."""
    key = (size, radius, colour)
    if key in _sprite_cache:
        return _sprite_cache[key]
    big = (max(1, size[0] * 4), max(1, size[1] * 4))
    shape = Image.new("L", big, 0)
    ImageDraw.Draw(shape).rounded_rectangle(
        (0, 0, big[0] - 1, big[1] - 1), radius=max(1, radius) * 4, fill=255)
    coloured = Image.new("RGBA", big, tuple(colour) + (255,))
    coloured.putalpha(shape)
    coloured = coloured.resize(size, Image.LANCZOS)
    _sprite_cache[key] = coloured
    return coloured


def _fit(text, drawing, text_font, limit):
    """Shortens text with an ellipsis until it fits the space it has."""
    if drawing.textlength(text, font=text_font) <= limit:
        return text
    ellipsis = u"\u2026"
    while text and drawing.textlength(text + ellipsis, font=text_font) > limit:
        text = text[:-1]
    return text + ellipsis


def _rim_glow(size, radius):
    """Siri's coloured ring, drawn once and blurred."""
    band = Image.new("RGB", size, (0, 0, 0))
    drawing = ImageDraw.Draw(band)
    for x in range(size[0]):
        drawing.line([(x, 0), (x, size[1])],
                     fill=_siri_colour(x / float(max(1, size[0] - 1))))
    ring = _rounded(size, radius)
    inner_size = (max(1, size[0] - 8 * SS), max(1, size[1] - 8 * SS))
    hole = Image.new("L", size, 0)
    hole.paste(_rounded(inner_size, max(1, radius - 4 * SS)), (4 * SS, 4 * SS))
    ring = Image.composite(Image.new("L", size, 0), ring, hole)
    glow = Image.new("RGB", size, (0, 0, 0))
    glow.paste(band, (0, 0), ring)
    return glow


class Glass(object):
    """The parts of a frame that stay still while the pill is on screen."""

    __slots__ = ("image", "box", "light", "scale")

    def __init__(self, image, box, light, scale):
        self.image = image
        self.box = box
        self.light = light
        self.scale = scale


def prepare(backdrop, width=theme.WIDTH, height=theme.HEIGHT, rim=False,
            open_share=1.0, scale=1.0):
    """Builds the glass over a picture of the desktop. Once per appearance."""
    margin = int(round(theme.SHADOW_MARGIN * scale))
    window = (int(round(width * scale)),
              int(round(height * scale)) + margin * 2)
    big = (window[0] * SS, window[1] * SS)

    if backdrop is None:
        backdrop = Image.new("RGB", window, (24, 24, 28))
    backdrop = backdrop.convert("RGB")
    if backdrop.size != window:
        backdrop = backdrop.resize(window, Image.LANCZOS)
    base = backdrop.resize(big, Image.LANCZOS)

    full_width = window[0] - margin * 2
    capsule_width = int(round(full_width * max(0.2, min(1.0, open_share))))
    left = (window[0] - capsule_width) // 2
    box = (left * SS, margin * SS,
           (left + capsule_width) * SS, (window[1] - margin) * SS)
    capsule_size = (box[2] - box[0], box[3] - box[1])
    radius = capsule_size[1] // 2
    mask = _rounded(capsule_size, radius)

    # The shadow, so the glass sits above the desktop rather than in it.
    shadow = Image.new("L", big, 0)
    shadow.paste(mask, (box[0], box[1] + int(theme.SHADOW_OFFSET * scale) * SS))
    shadow = shadow.filter(
        ImageFilter.GaussianBlur(theme.SHADOW_BLUR * scale * SS / 2.0))
    shadow = shadow.point(lambda value: int(value * theme.SHADOW_ALPHA))
    base = Image.composite(Image.new("RGB", big, (0, 0, 0)), base, shadow)

    # How bright the desktop is under the pill decides three things: how much
    # milk the glass needs, how the rim light is blended, and the colour of
    # the text. All three are measured here rather than guessed.
    under = backdrop.crop((box[0] // SS, box[1] // SS,
                           box[2] // SS, box[3] // SS)).convert("L")
    sample = under.resize((16, 4), Image.BILINEAR)
    light = (sum(sample.getdata()) / float(len(sample.getdata()))
             > theme.LIGHT_BACKDROP)

    # The rim light, only while it is listening to you. Adding light to a
    # white document does nothing, so over a light desktop the colours are
    # laid on instead of screened in.
    if rim:
        glow = Image.new("RGB", big, (0, 0, 0))
        glow.paste(_rim_glow(capsule_size, radius), (box[0], box[1]))
        glow = glow.filter(
            ImageFilter.GaussianBlur(theme.RIM_BLUR * scale * SS / 2.0))
        strength = glow.convert("L").point(
            lambda value: int(value * theme.RIM_ALPHA))
        top = glow if light else ImageChops.screen(base, glow)
        base = Image.composite(top, base, strength)

    # The glass itself: the desktop behind, blurred and lightened.
    blurred = backdrop.resize(big, Image.LANCZOS).filter(
        ImageFilter.GaussianBlur(theme.BLUR * scale * SS / 2.0))
    milk = theme.TINT_STRENGTH_LIGHT if light else theme.TINT_STRENGTH
    tinted = Image.blend(blurred, Image.new("RGB", big, theme.TINT), milk)
    glass = tinted.crop(box)
    base.paste(glass, (box[0], box[1]), mask)

    layer = Image.new("RGBA", capsule_size, (0, 0, 0, 0))

    # The bright edge, strongest along the top.
    edge = Image.new("L", capsule_size, 0)
    ImageDraw.Draw(edge).rounded_rectangle(
        (0, 0, capsule_size[0] - 1, capsule_size[1] - 1), radius=radius,
        outline=255, width=max(1, int(theme.EDGE_WIDTH * scale * SS)))
    ramp = _vertical_gradient(capsule_size, theme.EDGE_TOP, theme.EDGE_BOTTOM)
    layer.paste((255, 255, 255, 255), (0, 0),
                Image.composite(ramp, Image.new("L", capsule_size, 0), edge))

    # A soft highlight just inside the top edge.
    specular = Image.new("L", capsule_size, 0)
    ImageDraw.Draw(specular).ellipse(
        (capsule_size[0] * 0.18, 2 * SS,
         capsule_size[0] * 0.82, capsule_size[1] * 0.42),
        fill=int(255 * theme.SPECULAR_ALPHA))
    layer.paste((255, 255, 255, 255), (0, 0),
                specular.filter(ImageFilter.GaussianBlur(6 * scale * SS)))
    base.paste(layer, (box[0], box[1]), layer)

    plain_box = (box[0] // SS, box[1] // SS, box[2] // SS, box[3] // SS)
    return Glass(base.resize(window, Image.LANCZOS), plain_box, light, scale)


def paint(glass, state="listening", levels=None, text="", status="",
          label=""):
    """One frame: the prepared glass, plus the parts that move."""
    frame = glass.image.copy()
    drawing = ImageDraw.Draw(frame)
    scale = glass.scale
    ink = theme.TEXT_DARK if glass.light else theme.TEXT_LIGHT
    muted_alpha = int(255 * theme.MUTED_STRENGTH)

    left, top, right, bottom = glass.box
    middle = (top + bottom) // 2
    pad = int(round(theme.PADDING * scale))
    cursor = left + pad

    dot = max(4, int(round(theme.DOT * scale)))
    dot_sprite = sprite((dot, dot), dot // 2,
                        theme.STATE_COLOURS.get(state,
                                                theme.STATE_COLOURS["done"]))
    frame.paste(dot_sprite, (cursor, middle - dot // 2), dot_sprite)
    cursor += dot + int(round(12 * scale))

    if levels:
        bar_width = max(2, int(round(theme.BAR_WIDTH * scale)))
        pitch = bar_width + max(1, int(round(theme.BAR_GAP * scale)))
        tallest = max(4, int(round(theme.BAR_MAX * scale)))
        for index, level in enumerate(levels):
            if state == "listening":
                reach = max(0.0, min(1.0, level))
                bar_height = int(round(
                    (theme.BAR_MIN + (theme.BAR_MAX - theme.BAR_MIN) * reach)
                    * scale))
                bar_colour = _siri_colour(
                    index / float(max(1, len(levels) - 1)))
            else:
                bar_height = max(2, int(round(theme.BAR_FLAT * scale)))
                bar_colour = theme.BAR_QUIET
            bar = sprite((bar_width, tallest), bar_width // 2, bar_colour)
            if bar_height != tallest:
                bar = bar.resize((bar_width, max(2, bar_height)),
                                 Image.LANCZOS)
            frame.paste(bar, (cursor + index * pitch, middle - bar.height // 2),
                        bar)
        cursor += len(levels) * pitch + int(round(12 * scale))

    body = font(max(9, int(round(theme.FONT_SIZE * scale))))
    small = font(max(8, int(round(theme.LABEL_SIZE * scale))))
    text_right = right - pad
    if label:
        label_width = drawing.textlength(label, font=small)
        drawing.text((text_right - label_width, middle), label, font=small,
                     fill=ink + (muted_alpha,), anchor="lm")
        text_right -= label_width + int(round(16 * scale))

    message = text or status
    if message:
        message = _fit(message, drawing, body, max(10, text_right - cursor))
        colour = ink
        alpha = 255 if text else muted_alpha
        if state == "error":
            colour = theme.STATE_COLOURS["error"]
            alpha = 255
        if not glass.light:
            # A dark halo keeps light text readable where the wallpaper
            # underneath happens to be bright.
            drawing.text((cursor, middle + 1), message, font=body,
                         fill=(0, 0, 0, int(255 * theme.TEXT_SHADOW)),
                         anchor="lm")
        drawing.text((cursor, middle), message, font=body,
                     fill=colour + (alpha,), anchor="lm")
    return frame


def render(backdrop, state="listening", levels=None, text="", status="",
           label="", width=theme.WIDTH, height=theme.HEIGHT, open_share=1.0,
           scale=1.0):
    """Prepare and paint together. For tools and tests, not for every frame."""
    glass = prepare(backdrop, width=width, height=height,
                    rim=(state == "listening"), open_share=open_share,
                    scale=scale)
    return paint(glass, state=state, levels=levels, text=text, status=status,
                 label=label)
