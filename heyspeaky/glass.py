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

import math
import os

import numpy as np
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


def glowing_bar(width, height, tallest, colour, fade=1.0):
    """One waveform bar with a bloom around it.

    The idea is borrowed from a CSS loader, where the bars carry a wide
    box-shadow in their own colour. There is no box-shadow here, so the bar is
    drawn twice: once blurred underneath, once sharp on top. Both are baked
    into one sprite and cached, because bar heights are whole pixels and there
    are only ever a couple of dozen of them.
    """
    height = max(2, int(height))
    key = ("bar", width, height, tallest, colour, round(fade, 2))
    if key in _sprite_cache:
        return _sprite_cache[key]
    spread = max(1, int(round(theme.BAR_GLOW)))
    size = (width + spread * 2, tallest + spread * 2)
    bar = sprite((width, height), width // 2, colour)

    face = Image.new("RGBA", size, (0, 0, 0, 0))
    where = (spread, spread + (tallest - height) // 2)
    face.paste(bar, where, bar)

    bloom = face.filter(ImageFilter.GaussianBlur(spread / 1.6))
    strength = theme.BAR_GLOW_ALPHA * fade
    bloom.putalpha(bloom.getchannel("A").point(
        lambda value: int(value * strength)))
    bloom.alpha_composite(face)
    if fade < 1.0:
        bloom.putalpha(bloom.getchannel("A").point(
            lambda value: int(value * fade)))
    _sprite_cache[key] = bloom
    return bloom


def _bar_fade(index, count):
    """How solid a bar is, so the waveform dissolves at both ends."""
    steps = theme.BAR_EDGE_FADE
    if not steps or count <= len(steps) * 2:
        return 1.0
    from_edge = min(index, count - 1 - index)
    if from_edge < len(steps):
        return steps[from_edge]
    return 1.0


def button(size, kind, fill, glyph, dim=1.0, turn=0):
    """A round button with a cross or a tick drawn through it.

    Drawn at four times the size and scaled down, because a thin diagonal
    stroke is exactly where Tk's lack of antialiasing shows. `turn` rotates
    the glyph alone, in whole degrees, and not the shadow under the disc.
    """
    turn = int(round(turn)) % 360
    key = (size, kind, fill, glyph, round(dim, 2), turn)
    if key in _sprite_cache:
        return _sprite_cache[key]
    big = size * 4
    pad = big // 8
    canvas = (big + pad * 2, big + pad * 2)
    face = Image.new("RGBA", canvas, (0, 0, 0, 0))

    # A soft shadow under the whole circle, so it sits on the glass rather
    # than in it. From the Teenage Engineering button set.
    shadow = Image.new("L", canvas, 0)
    ImageDraw.Draw(shadow).ellipse(
        (pad, pad + pad // 2, pad + big - 1, pad + pad // 2 + big - 1),
        fill=int(255 * theme.BUTTON_SHADOW))
    shadow = shadow.filter(ImageFilter.GaussianBlur(pad / 1.5))
    face.paste((0, 0, 0, 255), (0, 0), shadow)

    disc = Image.new("L", canvas, 0)
    ImageDraw.Draw(disc).ellipse((pad, pad, pad + big - 1, pad + big - 1),
                                 fill=255)
    face.paste(tuple(fill) + (255,), (0, 0), disc)

    # Lit from the top left: a highlight just inside that edge, and a shade
    # inside the opposite one. Both are clipped to the circle.
    lift = max(2, big // 22)
    for offset, tone, alpha in (
        (-lift, (255, 255, 255), theme.BUTTON_INNER_LIGHT),
        (lift, (0, 0, 0), theme.BUTTON_INNER_SHADE),
    ):
        ring = Image.new("L", canvas, 0)
        ImageDraw.Draw(ring).ellipse(
            (pad + offset, pad + offset,
             pad + big - 1 + offset, pad + big - 1 + offset),
            outline=int(255 * alpha), width=max(2, big // 18))
        ring = Image.composite(ring, Image.new("L", canvas, 0), disc)
        face.paste(tone + (255,), (0, 0),
                   ring.filter(ImageFilter.GaussianBlur(lift * 0.9)))

    drawing = ImageDraw.Draw(face)
    width = max(2, int(round(theme.GLYPH_STROKE * 4)))
    ink = tuple(glyph) + (255,)
    cos_t, sin_t = math.cos(math.radians(turn)), math.sin(math.radians(turn))

    def at(fx, fy):
        fx, fy = fx - 0.5, fy - 0.5
        fx, fy = fx * cos_t - fy * sin_t, fx * sin_t + fy * cos_t
        return (pad + big * (fx + 0.5), pad + big * (fy + 0.5))

    if kind == "cancel":
        drawing.line(at(0.34, 0.34) + at(0.66, 0.66), fill=ink, width=width)
        drawing.line(at(0.66, 0.34) + at(0.34, 0.66), fill=ink, width=width)
    else:
        drawing.line(at(0.30, 0.52) + at(0.45, 0.67), fill=ink, width=width)
        drawing.line(at(0.45, 0.67) + at(0.71, 0.35), fill=ink, width=width)
    scaled = max(1, int(round(size * canvas[0] / float(big))))
    face = face.resize((scaled, scaled), Image.LANCZOS)
    if dim < 1.0:
        alpha = face.getchannel("A").point(lambda value: int(value * dim))
        face.putalpha(alpha)
    _sprite_cache[key] = face
    return face


def wave_layout(glass, count):
    """Where the waveform's bars go, fitted to the space between the buttons.

    Fitted, not scaled: a fixed pixel width and gap multiplied for a high-DPI
    screen rounds each one up, and twenty-three roundings put the end of the
    waveform underneath the tick.
    """
    boxes = button_boxes(glass)
    pad = int(round(theme.PADDING * glass.scale))
    left = boxes["cancel"][2] + pad
    right = boxes["accept"][0] - pad
    room = max(8, right - left)
    pitch = room / float(max(1, count))
    share = theme.BAR_WIDTH / float(theme.BAR_WIDTH + theme.BAR_GAP)
    width = max(2, int(pitch * share))
    return {"left": left, "right": right, "pitch": pitch, "width": width}


def bar_left(layout, index):
    """The left edge of one bar, centred in its slot."""
    return layout["left"] + int(round(index * layout["pitch"]
                                      + (layout["pitch"] - layout["width"])
                                      / 2.0))


def button_boxes(glass):
    """Where the two buttons are, in window pixels, for hit testing."""
    left, top, right, bottom = glass.box
    size = max(10, int(round(theme.BUTTON * glass.scale)))
    inset = int(round(theme.BUTTON_INSET * glass.scale))
    y = (top + bottom) // 2 - size // 2
    return {
        "cancel": (left + inset, y, left + inset + size, y + size),
        "accept": (right - inset - size, y, right - inset, y + size),
    }


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

    __slots__ = ("image", "box", "scale", "open_share")

    def __init__(self, image, box, scale, open_share=1.0):
        self.image = image
        self.box = box
        self.scale = scale
        # Below 1 the pill is still growing, and nothing is drawn inside it.
        self.open_share = open_share


def prepare(width=theme.WIDTH, height=theme.HEIGHT, rim=False,
            open_share=1.0, scale=1.0):
    """Builds the capsule on a transparent canvas. Once per appearance.

    Everything outside the capsule stays fully transparent, and the capsule
    itself is only mostly opaque, so the desktop behind shows through live.
    Windows composites it for us through UpdateLayeredWindow.

    This used to photograph the desktop and draw the picture as the window's
    own background, because a click-through window cannot ask Windows to blur
    what is behind it. The picture went stale the moment anything underneath
    moved, and then the window showed as a bright rectangle with somebody
    else's pixels in it. A real alpha channel has none of that problem.
    """
    margin = int(round(theme.SHADOW_MARGIN * scale))
    window = (int(round(width * scale)),
              int(round(height * scale)) + margin * 2)
    big = (window[0] * SS, window[1] * SS)

    base = Image.new("RGBA", big, (0, 0, 0, 0))

    full_width = window[0] - margin * 2
    capsule_width = int(round(full_width * max(0.2, min(1.0, open_share))))
    left = (window[0] - capsule_width) // 2
    box = (left * SS, margin * SS,
           (left + capsule_width) * SS, (window[1] - margin) * SS)
    capsule_size = (box[2] - box[0], box[3] - box[1])
    radius = capsule_size[1] // 2
    mask = _rounded(capsule_size, radius)

    _drop_shadow(base, box, mask, scale)

    # Siri's colours around the rim, only while it is listening to you.
    if rim:
        glow = Image.new("RGBA", big, (0, 0, 0, 0))
        ring = _rim_glow(capsule_size, radius)
        glow.paste(ring, (box[0], box[1]))
        glow.putalpha(glow.convert("L").point(
            lambda value: int(value * theme.RIM_ALPHA)))
        glow = glow.filter(
            ImageFilter.GaussianBlur(theme.RIM_BLUR * scale * SS / 2.0))
        base.alpha_composite(glow)

    _glass_body(base, box, mask, radius, scale, theme.PILL_ALPHA, 0.42, 6)

    plain_box = (box[0] // SS, box[1] // SS, box[2] // SS, box[3] // SS)
    return Glass(base.resize(window, Image.LANCZOS), plain_box, scale,
                 open_share)


def _drop_shadow(base, box, mask, scale):
    """The shadow, so a capsule sits above the desktop rather than on it."""
    shadow = Image.new("L", base.size, 0)
    shadow.paste(mask, (box[0], box[1] + int(theme.SHADOW_OFFSET * scale) * SS))
    shadow = shadow.filter(
        ImageFilter.GaussianBlur(theme.SHADOW_BLUR * scale * SS / 2.0))
    shadow = shadow.point(lambda value: int(value * theme.SHADOW_ALPHA))
    base.paste((0, 0, 0, 255), (0, 0), shadow)


def _glass_body(base, box, mask, radius, scale, alpha, specular_depth,
                specular_blur, specular_alpha=theme.SPECULAR_ALPHA):
    """The glass itself: the tint, the bright edge, the specular.

    Shared by the pill and the correction composer, which is what makes the
    two read as one app. Drawn into `base` at the supersampled size.
    """
    capsule_size = (box[2] - box[0], box[3] - box[1])

    # Dark, and not quite opaque, so the wallpaper shows through.
    body = Image.new("RGBA", capsule_size,
                     tuple(theme.TINT) + (int(255 * alpha),))
    body.putalpha(ImageChops.multiply(body.getchannel("A"), mask))
    base.alpha_composite(body, (box[0], box[1]))

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
         capsule_size[0] * 0.82, capsule_size[1] * specular_depth),
        fill=int(255 * specular_alpha))
    layer.paste((255, 255, 255, 255), (0, 0),
                specular.filter(
                    ImageFilter.GaussianBlur(specular_blur * scale * SS)))
    # Clipped to the capsule, or the highlight spills into thin air.
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    base.alpha_composite(layer, (box[0], box[1]))


def _paste_button(frame, face, box, bleed, grow=1.0, lift=0.0):
    """A button in its place; bigger and higher while the pointer is on it.

    At rest it goes down exactly as it always has, so a pill nobody is
    pointing at is the same picture, pixel for pixel, as before hover existed.
    """
    if abs(grow - 1.0) <= 0.004 and abs(lift) < 0.5:
        frame.paste(face, (box[0] - bleed, box[1] - bleed), face)
        return
    if abs(grow - 1.0) > 0.004:
        face = face.resize((max(1, int(round(face.size[0] * grow))),
                            max(1, int(round(face.size[1] * grow)))),
                           Image.LANCZOS)
    x = int(round((box[0] + box[2]) / 2.0 - face.size[0] / 2.0))
    y = int(round((box[1] + box[3]) / 2.0 - lift - face.size[1] / 2.0))
    frame.paste(face, (x, y), face)


def paint(glass, state="listening", levels=None, text="", status="",
          label="", hover=None):
    """One frame: the prepared glass, plus the parts that move.

    `hover` maps "cancel" and "accept" to (grow, turn, lift), as for the
    correction composer: the pill's buttons answer the pointer the same way.
    """
    frame = glass.image.copy()
    if glass.open_share < 0.98:
        # Still growing. An empty capsule opening is the whole effect; buttons
        # drawn into a pill that is not its full width look broken.
        return frame
    drawing = ImageDraw.Draw(frame)
    scale = glass.scale
    # The pill is dark whatever is behind it, so the ink never changes.
    ink = theme.TEXT_LIGHT

    left, top, right, bottom = glass.box
    middle = (top + bottom) // 2
    boxes = button_boxes(glass)
    size = boxes["cancel"][2] - boxes["cancel"][0]

    # Left: throw this recording away. Dimmed once there is nothing to throw.
    cancel_dim = 1.0 if state in ("listening", "transcribing") \
        else theme.BUTTON_DIM
    motion = hover or {}
    grow, spin, lift = motion.get("cancel", (1.0, 0, 0))
    cross = button(size, "cancel", theme.CANCEL_FILL, theme.CANCEL_GLYPH,
                   cancel_dim, turn=spin)
    # The sprite is wider than the button: it carries its own shadow.
    bleed = (cross.size[0] - size) // 2
    _paste_button(frame, cross, boxes["cancel"], bleed, grow, lift)

    # Right: finish. It goes green for the moment before the pill leaves.
    if state == "done":
        tick = button(size, "accept", theme.DONE_FILL, theme.DONE_GLYPH)
    elif state == "error":
        tick = button(size, "accept", theme.ACCEPT_FILL, theme.ACCEPT_GLYPH,
                      theme.BUTTON_DIM)
    else:
        tick = button(size, "accept", theme.ACCEPT_FILL, theme.ACCEPT_GLYPH)
    grow, _spin, lift = motion.get("accept", (1.0, 0, 0))
    _paste_button(frame, tick, boxes["accept"], bleed, grow, lift)

    inner_left = boxes["cancel"][2] + int(round(theme.PADDING * scale))
    inner_right = boxes["accept"][0] - int(round(theme.PADDING * scale))

    if levels is None and state == "done":
        # A quiet row of dots, so the finished pill is composed rather than
        # empty. Nothing was heard since it stopped, and that is what a dot
        # means everywhere else on it.
        levels = [0.0] * theme.BARS

    if levels:
        layout = wave_layout(glass, len(levels))
        bar_width = layout["width"]
        tallest = max(4, int(round(theme.BAR_MAX * scale)))
        for index, level in enumerate(levels):
            if state == "listening":
                reach = max(0.0, min(1.0, level))
                bar_height = int(round(
                    (theme.BAR_MIN + (theme.BAR_MAX - theme.BAR_MIN) * reach)
                    * scale))
                bar_colour = theme.BAR_LIVE
            else:
                bar_height = max(2, int(round(theme.BAR_FLAT * scale)))
                bar_colour = theme.BAR_QUIET
            bar = glowing_bar(bar_width, bar_height, tallest, bar_colour,
                              _bar_fade(index, len(levels)))
            spread = (bar.size[0] - bar_width) // 2
            left_edge = bar_left(layout, index)
            frame.paste(bar, (left_edge - spread,
                              middle - bar.size[1] // 2), bar)
        return frame

    # No waveform: the only thing worth saying here is what went wrong.
    message = text or status
    if not message:
        return frame
    body = font(max(9, int(round(theme.FONT_SIZE * scale))))
    message = _fit(message, drawing, body, max(10, inner_right - inner_left))
    colour = theme.STATE_COLOURS["error"] if state == "error" else ink
    centre = (inner_left + inner_right) // 2
    drawing.text((centre, middle + 1), message, font=body,
                 fill=(0, 0, 0, int(255 * theme.TEXT_SHADOW)), anchor="mm")
    drawing.text((centre, middle), message, font=body, fill=colour + (255,),
                 anchor="mm")
    return frame


def render(state="listening", levels=None, text="", status="", label="",
           width=theme.WIDTH, height=theme.HEIGHT, open_share=1.0, scale=1.0,
           backdrop=None):
    """Prepare and paint together. For tools and tests, not for every frame.

    With a backdrop it returns the pill composited over it, which is what
    ui_lab wants; without one it returns the pill with its alpha intact.
    """
    glass = prepare(width=width, height=height, rim=(state == "listening"),
                    open_share=open_share, scale=scale)
    frame = paint(glass, state=state, levels=levels, text=text, status=status,
                  label=label)
    if backdrop is None:
        return frame
    out = backdrop.convert("RGBA").resize(frame.size, Image.LANCZOS)
    out.alpha_composite(frame)
    return out


# -- mono: the second look ----------------------------------------------------
#
# The owner liked a black pill in a reel he sent and asked for it as a second
# look, beside the glass rather than instead of it. It has no buttons and no
# glass: a black capsule, eight bars, red while listening, blue while the
# words are worked out, and a shrink to nothing when they land. Every number
# is in theme.py under MONO_, with where it was measured.


class MonoGlass(object):
    """What stays still while the mono pill is up: the window's size and
    where the capsule sits in it."""

    __slots__ = ("window", "box", "scale", "message")

    def __init__(self, window, box, scale, message=""):
        self.window = window
        self.box = box
        self.scale = scale
        self.message = message


def _mono_font(scale):
    return font(max(9, int(round(theme.FONT_SIZE * scale))), medium=True)


def mono_prepare(scale=1.0, message=""):
    """The window and the capsule's place in it. With a message the capsule
    widens to hold it, up to the window; without one it is the pill."""
    window = (int(round(theme.MONO_WINDOW * scale)),
              int(round((theme.MONO_HEIGHT + 2 * theme.MONO_MARGIN) * scale)))
    height = int(round(theme.MONO_HEIGHT * scale))
    width = int(round(theme.MONO_WIDTH * scale))
    if message:
        measure = ImageDraw.Draw(Image.new("L", (1, 1)))
        wanted = int(math.ceil(measure.textlength(message,
                                                  font=_mono_font(scale))))
        width = max(width, wanted + int(height * 0.9))
    margin = int(round(theme.MONO_MARGIN * scale))
    width = min(width, window[0] - 2 * margin)
    left = (window[0] - width) // 2
    top = (window[1] - height) // 2
    return MonoGlass(window, (left, top, left + width, top + height), scale,
                     message)


def _mono_shadow(size, scale):
    """The capsule's shadow, drawn once for each size it is shown at."""
    key = ("mono-shadow", size, round(scale, 3))
    if key in _sprite_cache:
        return _sprite_cache[key]
    blur = max(2, int(round(8 * scale)))
    canvas = (size[0] + blur * 4, size[1] + blur * 4)
    mask = Image.new("L", canvas, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (blur * 2, blur * 2 + int(round(3 * scale)),
         blur * 2 + size[0] - 1, blur * 2 + size[1] - 1 + int(round(3 * scale))),
        radius=size[1] // 2, fill=int(255 * theme.MONO_SHADOW_ALPHA))
    shadow = Image.new("RGBA", canvas, (0, 0, 0, 0))
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(blur / 1.5)))
    _sprite_cache[key] = shadow
    return shadow


def mono_bar(width, height, tallest, colour):
    """One of the eight bars, with the light around it in its own colour:
    a halo that hugs the bar like the glow of a tube, as the reel's do."""
    height = max(2, int(height))
    key = ("mono-bar", width, height, tallest, colour)
    if key in _sprite_cache:
        return _sprite_cache[key]
    halo = max(1, int(round(theme.MONO_GLOW * width / 4.1)))
    size = (width + halo * 4, tallest + halo * 4)
    face = Image.new("RGBA", size, (0, 0, 0, 0))
    glow = sprite((width + halo * 2, height + halo * 2),
                  (width + halo * 2) // 2, colour).copy()
    glow.putalpha(glow.getchannel("A").point(
        lambda value: int(value * theme.MONO_GLOW_ALPHA)))
    top = halo * 2 + (tallest - height) // 2
    face.alpha_composite(glow, (halo, top - halo))
    face = face.filter(ImageFilter.GaussianBlur(halo / 1.8))
    bar = sprite((width, height), width // 2, colour)
    face.alpha_composite(bar, (halo * 2, top))
    _sprite_cache[key] = face
    return face


def mono_heights(state, level, now, count=theme.MONO_BARS):
    """How tall each bar is, 0 at its shortest and 1 at its tallest.

    Listening, the loudness lifts the middle most, the way the reel's bars
    stood 28 pixels at the ends and 56 in the middle while he spoke; a
    little movement of their own keeps them alive when he pauses, and they
    never fall to dots. Thinking, a wave runs across them.
    """
    heights = []
    level = max(0.0, min(1.0, level))
    middle = (count - 1) / 2.0
    for index in range(count):
        if state == "listening":
            drift = 0.35 * math.sin(now * 1.7 + index * 0.9)
            bell = math.exp(-((index - middle - drift) / 1.9) ** 2)
            pulse = 0.5 + 0.5 * math.sin(now * (5.3 + index * 0.7)
                                         + index * 1.9)
            share = (level * bell * (0.82 + 0.18 * pulse)
                     + 0.14 * pulse * (0.35 + 0.65 * level))
        else:
            wave = 0.5 + 0.5 * math.sin(now * 2 * math.pi * 1.6
                                        - index * 0.75)
            share = 0.30 + 0.70 * wave
        heights.append(max(0.0, min(1.0, share)))
    return heights


def mono_paint(mono, state="listening", level=0.0, now=0.0, collapse=0.0):
    """One frame of the mono pill. `collapse` runs 0 to 1 as it shrinks
    away once the words have landed."""
    frame = Image.new("RGBA", mono.window, (0, 0, 0, 0))
    scale = mono.scale
    left, top, right, bottom = mono.box
    collapse = max(0.0, min(1.0, collapse))
    shrink = 1.0 - 0.45 * (1.0 - (1.0 - collapse) ** 2)
    width = max(2, int(round((right - left) * shrink)))
    height = max(2, int(round((bottom - top) * shrink)))
    cx, cy = (left + right) / 2.0, (top + bottom) / 2.0
    x0, y0 = int(round(cx - width / 2.0)), int(round(cy - height / 2.0))

    shadow = _mono_shadow((width, height), scale)
    blur = (shadow.size[0] - width) // 2
    frame.alpha_composite(shadow, (x0 - blur, y0 - blur))
    capsule = sprite((width, height), height // 2, theme.MONO_FILL)
    frame.alpha_composite(capsule, (x0, y0))

    if mono.message:
        drawing = ImageDraw.Draw(frame)
        colour = theme.STATE_COLOURS["error"] if state == "error" \
            else theme.TEXT_LIGHT
        text = _fit(mono.message, drawing, _mono_font(scale),
                    max(10, width - int(height * 0.8)))
        drawing.text((cx, cy), text, font=_mono_font(scale),
                     fill=colour + (255,), anchor="mm")
    else:
        bars_fade = max(0.0, 1.0 - collapse * 1.15)
        if bars_fade > 0.01:
            bar_width = max(2, int(round(theme.MONO_BAR_WIDTH * scale
                                         * shrink)))
            pitch = theme.MONO_BAR_PITCH * scale * shrink
            shortest = theme.MONO_BAR_MIN * scale * shrink
            tallest = int(math.ceil(theme.MONO_BAR_MAX * scale * shrink))
            count = theme.MONO_BARS
            first = cx - pitch * (count - 1) / 2.0
            layer = Image.new("RGBA", mono.window, (0, 0, 0, 0))
            for index, share in enumerate(mono_heights(state, level, now,
                                                       count)):
                bar_height = int(round(shortest + (tallest - shortest)
                                       * share))
                if state == "listening":
                    colour = theme.MONO_LISTEN
                else:
                    # The wave is lit as well as tall, as it is in the reel.
                    colour = _mix(theme.MONO_THINK, theme.MONO_THINK_LIT,
                                  round(share * 4) / 4.0 * 0.6)
                face = mono_bar(bar_width, bar_height, tallest, colour)
                spread = (face.size[0] - bar_width) // 2
                x = int(round(first + index * pitch - bar_width / 2.0))
                layer.alpha_composite(face, (x - spread,
                                             int(round(cy - face.size[1]
                                                       / 2.0))))
            if bars_fade < 0.999:
                layer.putalpha(layer.getchannel("A").point(
                    lambda value: int(value * bars_fade)))
            frame.alpha_composite(layer)

    if collapse > 0.7:
        # Black while it shrinks, as in the reel; gone only at the very end.
        fade = max(0.0, 1.0 - (collapse - 0.7) / 0.3)
        frame.putalpha(frame.getchannel("A").point(
            lambda value: int(value * fade)))
    return frame


def mono_render(state="listening", level=0.6, now=0.4, message="",
                collapse=0.0, scale=1.0, backdrop=None):
    """Prepare and paint together, for tools and tests."""
    mono = mono_prepare(scale, message)
    frame = mono_paint(mono, state, level, now, collapse)
    if backdrop is None:
        return frame
    out = backdrop.convert("RGBA").resize(frame.size, Image.LANCZOS)
    out.alpha_composite(frame)
    return out


# -- the correction composer -------------------------------------------------

def _px(value, scale):
    return int(round(value * scale))


def composer_layout(scale=1.0):
    """Where the composer's parts go, in window pixels.

    Arithmetic only, and the one place it is done: the picture, the typing
    widget laid over it and the hit tests for its buttons all read from here,
    because the old box computed its sizes twice and the field drifted off its
    own slot whenever one copy changed.
    """
    margin = _px(theme.COMPOSER_MARGIN, scale)
    top = _px(theme.COMPOSER_TOP, scale)
    width = _px(theme.COMPOSER_WIDTH, scale)
    height = _px(theme.COMPOSER_HEIGHT, scale)
    window = (width + margin * 2, height + margin * 2 + top)
    box = (margin, top + margin, margin + width, top + margin + height)
    middle = (box[1] + box[3]) // 2

    size = _px(theme.COMPOSER_BUTTON, scale)
    inset = _px(theme.COMPOSER_BUTTON_INSET, scale)
    y = middle - size // 2
    buttons = {
        "cancel": (box[0] + inset, y, box[0] + inset + size, y + size),
        "accept": (box[2] - inset - size, y, box[2] - inset, y + size),
    }

    gap = _px(theme.FIELD_GAP, scale)
    field_height = _px(theme.FIELD_HEIGHT, scale)
    field_top = middle - field_height // 2
    field = (buttons["cancel"][2] + gap, field_top,
             buttons["accept"][0] - gap, field_top + field_height)

    # The widget sits on the field's straight stretch, clear of its round
    # ends and of the ring along its edge, so only the flat colour is under it.
    round_end = int(field_height * 0.38)
    inset_y = _px(theme.FIELD_INSET, scale)
    entry = (field[0] + round_end, field[1] + inset_y,
             field[2] - round_end, field[3] - inset_y)
    return {"scale": scale, "window": window, "box": box,
            "buttons": buttons, "field": field, "entry": entry}


_RING_STEPS = 720


def _ring_palette():
    """Colour and strength all the way round the ring.

    Two arcs chasing each other, as in the uiverse input the ring is drawn
    after, in the waveform's own colours: blue into purple on one side, pink
    into orange on the other, and nothing in between but the field's faint
    edge. Each arc rises slowly and ends in a bright head, like a comet, that
    still fades out over its last stretch: a head that stops dead draws a
    straight line across the glow, and it looks cut with scissors.
    """
    rgb = np.zeros((_RING_STEPS, 3), np.uint8)
    power = np.zeros(_RING_STEPS, np.float32)
    stops = theme.SIRI
    arcs = ((0.00, 0.26, stops[0], stops[1]),
            (0.50, 0.76, stops[2], stops[3]))
    for start, end, first, second in arcs:
        for index in range(_RING_STEPS):
            place = index / float(_RING_STEPS)
            if not start <= place < end:
                continue
            share = (place - start) / (end - start)
            rgb[index] = [int(round(first[c] + (second[c] - first[c]) * share))
                          for c in range(3)]
            head = min(1.0, (1.0 - share) / 0.22)
            head = head * head * (3.0 - 2.0 * head)
            power[index] = (share ** 1.3) * head
    return rgb, np.clip(power / max(1e-6, power.max()), 0.0, 1.0)


_RING_RGB, _RING_POWER = _ring_palette()


def _along_the_edge(size, field):
    """How far round the field's edge each pixel lies, 0 to 1.

    Not the angle from the centre, which is what a CSS conic gradient uses:
    on a field this long and thin the angle races across the middle of each
    long side and crawls round the ends, so an arc that fades out gently in
    degrees is cut off within a few pixels in the middle. Measured along the
    edge instead - top left to right, round the right end, back along the
    bottom, round the left end - every arc has the same length wherever it
    is, and it travels round at an even speed.
    """
    ys, xs = np.mgrid[0:size[1], 0:size[0]].astype(np.float32)
    xs += 0.5
    ys += 0.5
    radius = (field[3] - field[1]) / 2.0
    middle = (field[1] + field[3]) / 2.0
    start = field[0] + radius
    end = field[2] - radius
    straight = max(0.0, end - start)
    half_turn = math.pi * radius
    total = 2 * straight + 2 * half_turn

    along = np.empty(xs.shape, np.float32)
    inside = (xs >= start) & (xs <= end)
    upper = inside & (ys < middle)
    lower = inside & ~upper
    along[upper] = xs[upper] - start
    along[lower] = straight + half_turn + (end - xs[lower])

    right = xs > end
    angle = np.arctan2(ys[right] - middle, xs[right] - end)
    along[right] = straight + radius * (angle + math.pi / 2)

    left = xs < start
    angle = np.arctan2(ys[left] - middle, xs[left] - start)
    along[left] = (2 * straight + half_turn
                   + radius * ((angle - math.pi / 2) % (2 * math.pi)))
    return (along / total) % 1.0


def _ring_shape(layout, scale, spread, line):
    """What a ring round the field needs, worked out once per shape.

    Returns where the ring's picture goes, its size, the sharp line (`line`
    points wide) and the soft glow `spread` points out, as shares 0 to 1.
    The glow is outside the field only, so the field stays one flat colour
    and the typing widget laid over it cannot be told from the picture.
    """
    field = layout["field"]
    window = layout["window"]
    spread = max(2, _px(spread, scale))
    reach = spread * 2
    left, top = max(0, field[0] - reach), max(0, field[1] - reach)
    right = min(window[0], field[2] + reach)
    bottom = min(window[1], field[3] + reach)
    size = (right - left, bottom - top)

    k = 4
    big = (size[0] * k, size[1] * k)
    rect = ((field[0] - left) * k, (field[1] - top) * k,
            (field[2] - left) * k - 1, (field[3] - top) * k - 1)
    radius = (field[3] - field[1]) * k // 2

    def outline(width):
        image = Image.new("L", big, 0)
        ImageDraw.Draw(image).rounded_rectangle(
            rect, radius=radius, outline=255, width=max(1, int(width)))
        return image.resize(size, Image.LANCZOS)

    inside = Image.new("L", big, 0)
    ImageDraw.Draw(inside).rounded_rectangle(rect, radius=radius, fill=255)
    inside = np.asarray(inside.resize(size, Image.LANCZOS),
                        np.float32) / 255.0

    sharp = np.asarray(outline(line * scale * k), np.float32) / 255.0
    wide = outline(3 * scale * k).filter(
        ImageFilter.GaussianBlur(spread / 2.0))
    glow = np.asarray(wide, np.float32) / 255.0 * (1.0 - inside)
    return (left, top), size, sharp, glow


class GlowRing(object):
    """The coloured ring round the field, cheap enough to turn every frame.

    Everything that depends only on the shape - the sharp line, the soft glow
    outside it, and the angle of every pixel from the field's centre - is
    worked out once. A frame is then one table lookup: which colour is at
    this angle once the ring has turned this far.
    """

    def __init__(self, layout, scale, spread=theme.GLOW_SPREAD):
        self.origin, self.size, self._line, glow = _ring_shape(
            layout, scale, spread, theme.GLOW_RING)
        self._glow = np.clip(glow * 2.2, 0.0, 1.0)
        field = layout["field"]
        left, top = self.origin
        self._angle = _along_the_edge(
            self.size, ((field[0] - left, field[1] - top,
                         field[2] - left, field[3] - top)))

    def render(self, turn, strength):
        """The ring turned by `turn` of a revolution, at `strength` 0 to 1."""
        index = ((self._angle + turn) * _RING_STEPS).astype(np.int32) \
            % _RING_STEPS
        power = _RING_POWER[index]
        alpha = (self._line * power * (0.45 + 0.55 * strength)
                 + self._glow * power * strength)
        rgba = np.empty(self._angle.shape + (4,), np.uint8)
        rgba[..., :3] = _RING_RGB[index]
        rgba[..., 3] = np.clip(alpha * 255.0, 0, 255).astype(np.uint8)
        return Image.fromarray(rgba, "RGBA")


class FocusRing(object):
    """The mono look's ring round a field: one blue line and a soft halo,
    the way a Mac shows the field that has the keyboard, where the glass has
    colours chasing round.

    It has GlowRing's `origin` and `render`, so a field does not care which
    ring it has. `turn` means nothing to it; `strength` still brightens it,
    so a key still makes it flare.
    """

    def __init__(self, layout, scale):
        self.origin, self.size, self._line, glow = _ring_shape(
            layout, scale, theme.MONO_FOCUS_GLOW, theme.MONO_FOCUS)
        self._glow = np.clip(glow * 1.6, 0.0, 1.0)
        self._drawn = {}

    def render(self, turn, strength):
        level = round(max(0.0, min(1.0, strength)), 2)
        image = self._drawn.get(level)
        if image is None:
            alpha = (self._line * (0.6 + 0.4 * level)
                     + self._glow * 0.55 * level)
            rgba = np.empty(self._line.shape + (4,), np.uint8)
            rgba[..., :3] = theme.MONO_ACCENT
            rgba[..., 3] = np.clip(alpha * 255.0, 0, 255).astype(np.uint8)
            image = Image.fromarray(rgba, "RGBA")
            self._drawn[level] = image
        return image


def _mono_body(base, box, mask, radius, scale):
    """The mono look where the glass would be: the capsule's black, solid,
    with a white hairline round its edge so a black card still has an
    outline on a black desktop. The hairline is translucent, so it goes on
    its own layer: drawn straight on, it would cut its alpha into the body."""
    base.paste(theme.MONO_FILL + (255,), (box[0], box[1]), mask)
    edge = Image.new("L", mask.size, 0)
    ImageDraw.Draw(edge).rounded_rectangle(
        (0, 0, mask.size[0] - 1, mask.size[1] - 1), radius=radius,
        outline=255, width=max(1, int(round(scale * SS))))
    line = Image.new("RGBA", mask.size, (255, 255, 255, 0))
    line.putalpha(ImageChops.multiply(edge, mask).point(
        lambda value: int(value * theme.MONO_HAIRLINE / 255.0)))
    base.alpha_composite(line, (box[0], box[1]))


class Composer(object):
    """The parts of the correction composer that stay still while it is up."""

    __slots__ = ("layout", "shell", "field", "ring", "scale", "mono")

    def __init__(self, layout, shell, field, ring, scale, mono=False):
        self.layout = layout
        self.shell = shell
        self.field = field
        self.ring = ring
        self.scale = scale
        self.mono = mono


def composer(scale=1.0, mono=False):
    """Builds the composer's glass, field and ring. Once per opening.

    The glass is the pill's own - the same shadow, tint, edge and specular,
    through the same helpers - only wider and more solid. In the mono look
    it is the mono capsule's black instead, with a blue focus ring.
    """
    layout = composer_layout(scale)
    window = layout["window"]
    big = (window[0] * SS, window[1] * SS)
    box = tuple(value * SS for value in layout["box"])
    capsule_size = (box[2] - box[0], box[3] - box[1])
    radius = capsule_size[1] // 2
    mask = _rounded(capsule_size, radius)

    shell = Image.new("RGBA", big, (0, 0, 0, 0))
    _drop_shadow(shell, box, mask, scale)
    if mono:
        _mono_body(shell, box, mask, radius, scale)
    else:
        _glass_body(shell, box, mask, radius, scale, theme.COMPOSER_ALPHA,
                    0.42, 6)
    shell = shell.resize(window, Image.LANCZOS)

    field_box = layout["field"]
    field_size = (field_box[2] - field_box[0], field_box[3] - field_box[1])
    field = Image.new("RGBA", window, (0, 0, 0, 0))
    solid = sprite(field_size, field_size[1] // 2, field_fill(mono))
    field.alpha_composite(solid, (field_box[0], field_box[1]))
    if mono:
        # The focus ring is its edge.
        return Composer(layout, shell, field, FocusRing(layout, scale),
                        scale, mono=True)
    # A faint edge all the way round, for where the coloured arcs are not.
    k = 4
    edge = Image.new("L", (field_size[0] * k, field_size[1] * k), 0)
    ImageDraw.Draw(edge).rounded_rectangle(
        (0, 0, edge.size[0] - 1, edge.size[1] - 1),
        radius=field_size[1] * k // 2, outline=255,
        width=max(1, int(round(scale * k))))
    edge = edge.resize(field_size, Image.LANCZOS).point(
        lambda value: int(value * theme.FIELD_EDGE))
    line = Image.new("RGBA", field_size, (255, 255, 255, 0))
    line.putalpha(edge)
    field.alpha_composite(line, (field_box[0], field_box[1]))

    return Composer(layout, shell, field, GlowRing(layout, scale), scale)


def field_fill(mono=False):
    """The flat colour of the composer's field, which the typing widget laid
    over it must match exactly."""
    return theme.MONO_FIELD if mono else theme.FIELD_FILL


def chip(parts, scale=1.0, mono=False):
    """A small dark label above the composer: what was heard, or what a
    button does. `parts` is a list of (text, muted) pairs, drawn in a row.
    In the mono look it is the capsule's black, solid."""
    key = ("chip", tuple(parts), round(scale, 3), mono)
    if key in _sprite_cache:
        return _sprite_cache[key]
    height = max(12, _px(theme.CHIP_HEIGHT, scale))
    pad = _px(theme.CHIP_PAD, scale)
    text_font = font(max(8, _px(theme.LABEL_SIZE, scale)))
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    widths = [measure.textlength(text, font=text_font) for text, _m in parts]
    width = int(math.ceil(sum(widths))) + pad * 2
    face = sprite((width, height), height // 2,
                  theme.MONO_FILL if mono else theme.CHIP_FILL).copy()
    if not mono:
        face.putalpha(face.getchannel("A").point(
            lambda value: int(value * theme.CHIP_ALPHA)))
    drawing = ImageDraw.Draw(face)
    x = pad
    for (text, muted), part_width in zip(parts, widths):
        colour = theme.TEXT_LIGHT
        if muted:
            colour = tuple(int(c * theme.MUTED_STRENGTH) for c in colour)
        drawing.text((x, height / 2.0), text, font=text_font,
                     fill=colour + (255,), anchor="lm")
        x += part_width
    _sprite_cache[key] = face
    return face


def _place_over(frame, image, x, y, alpha=1.0):
    """Composites `image` at x, y, clipped to the frame, faded by alpha."""
    if alpha <= 0.0:
        return
    if alpha < 1.0:
        image = image.copy()
        image.putalpha(image.getchannel("A").point(
            lambda value: int(value * alpha)))
    x, y = int(round(x)), int(round(y))
    left, top = max(0, -x), max(0, -y)
    right = min(image.size[0], frame.size[0] - x)
    bottom = min(image.size[1], frame.size[1] - y)
    if right <= left or bottom <= top:
        return
    if (left, top, right, bottom) != (0, 0) + image.size:
        image = image.crop((left, top, right, bottom))
    frame.alpha_composite(image, (x + left, y + top))


def _narrowed(shell, layout, open_share):
    """The empty capsule part-way open: the middle taken out, ends kept.

    Cutting a band out of the finished picture and closing the gap costs a
    couple of copies, where drawing the glass again at every width would cost
    the whole of `composer` every frame of the opening.
    """
    box = layout["box"]
    window = layout["window"]
    full = box[2] - box[0]
    height = box[3] - box[1]
    width = max(height, int(round(full * max(0.0, min(1.0, open_share)))))
    cut = full - width
    if cut <= 0:
        return shell.copy()
    centre = (box[0] + box[2]) // 2
    left = shell.crop((0, 0, centre - cut // 2, window[1]))
    right = shell.crop((centre + (cut - cut // 2), 0, window[0], window[1]))
    frame = Image.new("RGBA", window, (0, 0, 0, 0))
    frame.paste(left, (cut // 2, 0))
    frame.paste(right, (cut // 2 + left.size[0], 0))
    return frame


def composer_frame(composer, open_share=1.0, turn=0.0,
                   strength=theme.GLOW_SETTLED, buttons=None, done=False,
                   chips=(), text=""):
    """One frame of the composer.

    `buttons` maps "cancel" and "accept" to (grow, turn, lift): how much
    bigger than rest the button is, how far its glyph has turned, and how far
    it has risen. `chips` are (image, x, y, alpha). `text` is drawn into the
    field only while the typing widget is gone, as it is when the composer
    closes, so the word does not vanish a moment before the glass does.
    """
    layout = composer.layout
    if open_share < 0.98:
        # Still growing. An empty capsule opening is the whole effect, as it
        # is for the pill.
        return _narrowed(composer.shell, layout, open_share)

    frame = composer.shell.copy()
    frame.alpha_composite(composer.field)
    _place_over(frame, composer.ring.render(turn, strength),
                *composer.ring.origin)

    if text:
        scale = composer.scale
        entry = layout["entry"]
        text_font = font(max(9, _px(theme.FIELD_TEXT, scale)))
        drawing = ImageDraw.Draw(frame)
        text = _fit(text, drawing, text_font, entry[2] - entry[0])
        drawing.text((entry[0] + 1, (entry[1] + entry[3]) / 2.0), text,
                     font=text_font, fill=theme.TEXT_LIGHT + (255,),
                     anchor="lm")

    # Mono: the cross a dark grey disc, the tick the thinking blue.
    if composer.mono:
        cancel = (theme.MONO_CONTROL, theme.MONO_CONTROL_INK)
        accept = (theme.MONO_ACCENT, theme.TEXT_LIGHT)
    else:
        cancel = (theme.CANCEL_FILL, theme.CANCEL_GLYPH)
        accept = (theme.ACCEPT_FILL, theme.ACCEPT_GLYPH)
    for name, box in layout["buttons"].items():
        grow, glyph_turn, lift = (buttons or {}).get(name, (1.0, 0, 0))
        size = box[2] - box[0]
        if name == "cancel":
            face = button(size, "cancel", cancel[0], cancel[1],
                          turn=glyph_turn)
        elif done:
            face = button(size, "accept", theme.DONE_FILL, theme.DONE_GLYPH)
        else:
            face = button(size, "accept", accept[0], accept[1])
        if abs(grow - 1.0) > 0.004:
            face = face.resize(
                (max(1, int(round(face.size[0] * grow))),
                 max(1, int(round(face.size[1] * grow)))), Image.LANCZOS)
        centre_x = (box[0] + box[2]) / 2.0
        centre_y = (box[1] + box[3]) / 2.0 - lift
        _place_over(frame, face, centre_x - face.size[0] / 2.0,
                    centre_y - face.size[1] / 2.0)

    for image, x, y, alpha in chips:
        _place_over(frame, image, x, y, alpha)
    return frame


# -- the shortcuts' icon ------------------------------------------------------

# Bar heights, as a share of the tallest: the pill's waveform in miniature,
# the same five the tray icon draws.
ICON_BARS = (0.36, 0.68, 1.0, 0.68, 0.36)


def app_icon(size=256):
    """HeySpeaky's own icon, for its shortcuts: the waveform in its colours
    on a tile of the pill's dark glass.

    The shortcuts used to borrow the icon of the Python they start, which
    has none of its own, so the Start menu showed a blank window. The tray
    icon is white on nothing, which vanishes on a light Start menu; a tile
    reads on either. Here and not in tray.py, which needs pystray to import.
    """
    k = 4
    big = size * k
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    drawing = ImageDraw.Draw(image)
    inset = big // 16
    tile = (inset, inset, big - inset, big - inset)
    drawing.rounded_rectangle(tile, radius=big // 4.4,
                              fill=tuple(theme.TINT) + (255,))
    # The glass's bright edge, faintly, as on the pill.
    drawing.rounded_rectangle(tile, radius=big // 4.4,
                              outline=(255, 255, 255, 34),
                              width=max(1, big // 110))
    width = big // 11
    gap = big // 19
    tallest = big * 0.54
    count = len(ICON_BARS)
    left = (big - (width * count + gap * (count - 1))) // 2
    for index, share in enumerate(ICON_BARS):
        height = int(tallest * share)
        x = left + index * (width + gap)
        top = (big - height) // 2
        drawing.rounded_rectangle(
            (x, top, x + width, top + height), radius=width // 2,
            fill=_siri_colour(index / float(count - 1)) + (255,))
    return image.resize((size, size), Image.LANCZOS)


def save_app_icon(path):
    """Writes the icon as a .ico with every size Windows asks for."""
    import os
    folder = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(folder):
        os.makedirs(folder)
    sizes = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48),
             (64, 64), (128, 128), (256, 256)]
    app_icon(256).save(path, format="ICO", sizes=sizes)
    return path


# -- the tray panel ----------------------------------------------------------

def panel_card(width, height, scale=1.0, mono=False):
    """The tray panel's glass: the pill's own layers, as a card. In the mono
    look, the same card and shadow in the mono capsule's solid black.

    Returns the picture and where the card sits in it; the rest of the
    picture is room for the shadow, and fully transparent.
    """
    margin = _px(theme.PANEL_MARGIN, scale)
    window = (int(width) + margin * 2, int(height) + margin * 2)
    big = (window[0] * SS, window[1] * SS)
    box = (margin * SS, margin * SS, (margin + int(width)) * SS,
           (margin + int(height)) * SS)
    size = (box[2] - box[0], box[3] - box[1])
    radius = _px(theme.PANEL_RADIUS, scale) * SS
    mask = _rounded(size, radius)
    image = Image.new("RGBA", big, (0, 0, 0, 0))
    _drop_shadow(image, box, mask, scale)
    if mono:
        _mono_body(image, box, mask, radius, scale)
    else:
        # A card is tall, and the pill's specular stretched down one reads
        # as a smudge behind the title. Here it is a thin sheen along the top.
        _glass_body(image, box, mask, radius, scale, theme.PANEL_ALPHA,
                    0.035, 3, 0.07)
    return (image.resize(window, Image.LANCZOS),
            (margin, margin, margin + int(width), margin + int(height)))


def _mix(first, second, share):
    share = max(0.0, min(1.0, share))
    return tuple(int(round(a + (b - a) * share))
                 for a, b in zip(first, second))


def _gradient(size, first, second):
    """A left-to-right ramp between two colours."""
    ramp = Image.new("RGB", (max(1, size[0]), 1))
    pixels = ramp.load()
    for x in range(ramp.size[0]):
        pixels[x, 0] = _mix(first, second, x / float(max(1, ramp.size[0] - 1)))
    return ramp.resize(size, Image.BILINEAR)


def switch(width, height, on, mono=False):
    """A switch, `on` running 0 to 1 as it slides.

    Off, it is the cross's grey. On, its track is the waveform's gradient -
    the one piece of colour in the panel, and the same one the pill and the
    composer carry. In the mono look it is an iPhone's switch in the
    thinking blue.
    """
    on = round(max(0.0, min(1.0, on)), 2)
    key = ("switch", width, height, on, mono)
    if key in _sprite_cache:
        return _sprite_cache[key]
    k = 4
    big = (width * k, height * k)
    face = Image.new("RGBA", big, (0, 0, 0, 0))
    track = Image.new("L", big, 0)
    ImageDraw.Draw(track).rounded_rectangle(
        (0, 0, big[0] - 1, big[1] - 1), radius=big[1] // 2, fill=255)
    if mono:
        off = Image.new("RGB", big, theme.MONO_CONTROL)
        lit = Image.new("RGB", big, theme.MONO_ACCENT)
    else:
        off = Image.new("RGB", big, theme.CANCEL_FILL)
        lit = _gradient(big, theme.SIRI[0], theme.SIRI[1])
    face.paste(Image.blend(off, lit, on), (0, 0), track)
    inset = max(2, big[1] // 10)
    knob = big[1] - inset * 2
    left = inset + int(round((big[0] - inset * 2 - knob) * on))
    shade = Image.new("L", big, 0)
    ImageDraw.Draw(shade).ellipse(
        (left, inset + k, left + knob, inset + knob + k), fill=90)
    face.paste((0, 0, 0, 255), (0, 0),
               shade.filter(ImageFilter.GaussianBlur(k * 1.5)))
    ImageDraw.Draw(face).ellipse((left, inset, left + knob, inset + knob),
                                 fill=theme.ACCEPT_FILL + (255,))
    face = face.resize((width, height), Image.LANCZOS)
    _sprite_cache[key] = face
    return face


def _pill_label(width, height, fill, text, ink, text_font):
    face = sprite((width, height), height // 2, fill).copy()
    ImageDraw.Draw(face).text((width / 2.0, height / 2.0), text,
                              font=text_font, fill=ink + (255,), anchor="mm")
    return face


def panel_chip(text, selected, scale=1.0, mono=False):
    """A language to pin. The chosen one is white with dark ink, like the
    tick; the rest are the cross's grey. Mono: blue, and a dark grey."""
    key = ("panel-chip", text, bool(selected), round(scale, 3), mono)
    if key in _sprite_cache:
        return _sprite_cache[key]
    height = _px(theme.PANEL_CHIP_HEIGHT, scale)
    text_font = font(max(8, _px(theme.FONT_SIZE - 1, scale)), medium=True)
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    width = int(math.ceil(measure.textlength(text, font=text_font))) \
        + _px(24, scale)
    width = max(width, height)
    if selected and mono:
        face = _pill_label(width, height, theme.MONO_ACCENT, text,
                           theme.TEXT_LIGHT, text_font)
    elif selected:
        face = _pill_label(width, height, theme.ACCEPT_FILL, text,
                           theme.ACCEPT_GLYPH, text_font)
    elif mono:
        face = _pill_label(width, height, theme.MONO_CONTROL, text,
                           theme.MONO_CONTROL_INK, text_font)
    else:
        face = _pill_label(width, height, theme.CANCEL_FILL, text,
                           theme.CANCEL_GLYPH, text_font)
    _sprite_cache[key] = face
    return face


def segmented(width, height, labels, position, scale=1.0, mono=False):
    """Two or more choices in one track, a grey thumb under the chosen one.

    `position` is where the thumb is, 0 for the first choice, and may be in
    between while it slides.
    """
    key = ("segmented", width, height, tuple(labels), round(position, 2),
           round(scale, 3), mono)
    if key in _sprite_cache:
        return _sprite_cache[key]
    face = sprite((width, height), height // 2, field_fill(mono)).copy()
    count = max(1, len(labels))
    cell = width / float(count)
    inset = max(2, _px(3, scale))
    thumb = sprite((int(round(cell)) - inset * 2, height - inset * 2),
                   (height - inset * 2) // 2,
                   theme.MONO_CONTROL if mono else theme.CANCEL_FILL)
    x = int(round(inset + cell * position))
    face.alpha_composite(thumb, (x, inset))
    text_font = font(max(8, _px(theme.FONT_SIZE - 1, scale)), medium=True)
    drawing = ImageDraw.Draw(face)
    for index, label in enumerate(labels):
        near = max(0.0, 1.0 - abs(position - index))
        ink = _mix(_mix(theme.TEXT_LIGHT, (0, 0, 0), 1 - theme.MUTED_STRENGTH),
                   theme.TEXT_LIGHT, near)
        drawing.text((cell * (index + 0.5), height / 2.0), label,
                     font=text_font, fill=ink + (255,), anchor="mm")
    _sprite_cache[key] = face
    return face


def _chevron(drawing, x, y, size, ink):
    half = size / 2.0
    drawing.line([(x - half * 0.5, y - half), (x + half * 0.5, y),
                  (x - half * 0.5, y + half)], fill=ink + (255,),
                 width=max(1, int(round(size / 5.0))), joint="curve")


def _check(drawing, x, y, size, ink, share=1.0):
    """The tick, drawn as far as `share` of the way along its two strokes:
    short stroke down, long stroke up, the way a hand draws one."""
    points = [(x - size * 0.45, y), (x - size * 0.1, y + size * 0.35),
              (x + size * 0.5, y - size * 0.4)]
    share = max(0.0, min(1.0, share))
    if share < 0.02:
        return
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(points, points[1:])]
    left = share * sum(lengths)
    path = [points[0]]
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if left >= length:
            path.append(b)
            left -= length
            continue
        part = left / length
        path.append((a[0] + (b[0] - a[0]) * part, a[1] + (b[1] - a[1]) * part))
        break
    drawing.line(path, fill=ink + (255,),
                 width=max(1, int(round(size / 5.0))), joint="curve")


def _magnifier(drawing, x, y, size, ink):
    """A lens and its handle, for the search field."""
    radius = size * 0.32
    width = max(1, int(round(size / 7.0)))
    drawing.ellipse((x - radius - size * 0.08, y - radius - size * 0.08,
                     x + radius - size * 0.08, y + radius - size * 0.08),
                    outline=ink + (255,), width=width)
    drawing.line([(x + radius * 0.62, y + radius * 0.62),
                  (x + size * 0.42, y + size * 0.42)], fill=ink + (255,),
                 width=width + 1)


_search_rings = {}


def search_ring(field, window, scale, mono=False):
    """The composer's ring, for a field of this size in a window this big.
    Built once per shape: a frame only turns it."""
    key = (tuple(field), tuple(window), round(scale, 3), mono)
    ring = _search_rings.get(key)
    if ring is None:
        _search_rings.clear()
        shape = {"field": field, "window": window}
        if mono:
            ring = FocusRing(shape, scale)
        else:
            ring = GlowRing(shape, scale, spread=theme.SEARCH_SPREAD)
        _search_rings[key] = ring
    return ring


def _search_field(frame, drawing, item, scale, motion, muted, faint,
                  lens=True, mono=False):
    """The language search, and the key field: the composer's field and
    ring, a lens for the search, the words typed so far or what to type,
    and a caret."""
    left, top, right, bottom = item.rect
    height = bottom - top
    glow = motion.get("search-glow", theme.GLOW_SETTLED)
    if mono:
        # The focus ring's line is the field's edge, so it goes on top.
        face = sprite((right - left, height), height // 2, theme.MONO_FIELD)
        _place_over(frame, face, left, top)
        ring = search_ring(item.rect, frame.size, scale, mono=True)
        _place_over(frame, ring.render(0.0, glow), *ring.origin)
    else:
        ring = search_ring(item.rect, frame.size, scale)
        _place_over(frame, ring.render(motion.get("search-turn", 0.0), glow),
                    ring.origin[0], ring.origin[1])
        face = sprite((right - left, height), height // 2, theme.FIELD_FILL)
        _place_over(frame, face, left, top)
    middle = (top + bottom) / 2.0
    if lens:
        _magnifier(drawing, left + _px(16, scale), middle, _px(14, scale),
                   faint)
        text_left = left + _px(30, scale)
    else:
        text_left = left + _px(16, scale)
    body = font(max(9, _px(theme.FONT_SIZE, scale)))
    typed = item.label or ""
    if typed:
        limit = right - _px(16, scale) - text_left
        shown = typed
        while shown and drawing.textlength(shown, font=body) > limit:
            shown = shown[1:]
        drawing.text((text_left, middle), shown, font=body,
                     fill=theme.TEXT_LIGHT + (255,), anchor="lm")
        caret_x = text_left + drawing.textlength(shown, font=body) + 1
    else:
        drawing.text((text_left, middle), item.extra or "", font=body,
                     fill=muted + (255,), anchor="lm")
        caret_x = text_left - _px(1, scale)
    if motion.get("caret", 1.0) > 0.5:
        half = height * 0.26
        drawing.line([(caret_x, middle - half), (caret_x, middle + half)],
                     fill=theme.TEXT_LIGHT + (255,),
                     width=max(1, _px(1.5, scale)))


def panel_frame(card, items, scale=1.0, hover=None, motion=None,
                mono=False):
    """One frame of the tray panel.

    `card` is (picture, box) from `panel_card`; `items` the laid-out parts
    from `panel.layout`, in window pixels. `hover` maps an item's key to how
    far the pointer's highlight has come on, 0 to 1; `motion` carries what
    slides - the switch and the segmented thumb - by key. `mono` draws the
    controls in the mono look, on a card made with `panel_card(mono=True)`.
    """
    image, _box = card
    frame = image.copy()
    drawing = ImageDraw.Draw(frame)
    hover = hover or {}
    motion = motion or {}
    muted = _mix(theme.TEXT_LIGHT, (0, 0, 0), 1 - theme.MUTED_STRENGTH)
    faint = _mix(theme.TEXT_LIGHT, (0, 0, 0), 0.62)
    body = font(max(9, _px(theme.FONT_SIZE, scale)))
    small = font(max(8, _px(theme.HINT_SIZE, scale)))
    label_font = font(max(7, _px(theme.HINT_SIZE - 1, scale)), medium=True)
    title_font = font(max(10, _px(theme.TITLE_SIZE, scale)), medium=True)
    # The one colour: the gradient's end on glass, the thinking blue in mono.
    accent = theme.MONO_ACCENT_INK if mono else theme.SIRI[1]
    tick = theme.MONO_ACCENT_INK if mono else theme.TEXT_LIGHT

    for item in items:
        left, top, right, bottom = item.rect
        middle = (top + bottom) / 2.0
        lit = hover.get(item.key, 0.0)
        kind = item.kind
        if kind in ("row", "switch", "back", "language", "model") \
                and lit > 0.005:
            fill = Image.new("RGBA", (right - left, bottom - top),
                             (255, 255, 255, int(255 * theme.ROW_HOVER * lit)))
            shape = sprite((right - left, bottom - top),
                           _px(theme.ROW_RADIUS, scale), (255, 255, 255))
            fill.putalpha(ImageChops.multiply(fill.getchannel("A"),
                                              shape.getchannel("A")))
            frame.alpha_composite(fill, (left, top))

        if kind == "title":
            drawing.text((left, middle), item.label, font=title_font,
                         fill=theme.TEXT_LIGHT + (255,), anchor="lm")
        elif kind == "status":
            dot = _px(8, scale)
            colour = item.extra
            drawing.ellipse((right - dot, middle - dot / 2.0, right,
                             middle + dot / 2.0), fill=colour + (255,))
            drawing.text((right - dot - _px(7, scale), middle), item.label,
                         font=small, fill=muted + (255,), anchor="rm")
        elif kind == "label":
            drawing.text((left, middle), item.label.upper(), font=label_font,
                         fill=faint + (255,), anchor="lm")
        elif kind == "hint":
            drawing.text((left, middle), item.label, font=small,
                         fill=muted + (255,), anchor="lm")
        elif kind == "chip":
            face = panel_chip(item.label, bool(item.extra), scale, mono)
            grow = 1.0 + 0.06 * lit
            if grow > 1.004:
                face = face.resize((int(round(face.size[0] * grow)),
                                    int(round(face.size[1] * grow))),
                                   Image.LANCZOS)
            _place_over(frame, face, (left + right) / 2.0 - face.size[0] / 2.0,
                        middle - face.size[1] / 2.0)
        elif kind == "segmented":
            labels, chosen = item.extra[0], item.extra[1]
            face = segmented(right - left, bottom - top, labels,
                             motion.get(item.key, chosen), scale, mono)
            _place_over(frame, face, left, top)
        elif kind in ("row", "switch", "back", "language"):
            inset = _px(10, scale)
            text_left = left + inset
            if kind == "back":
                _chevron(drawing, text_left + _px(3, scale), middle,
                         _px(10, scale), theme.TEXT_LIGHT)
                # Pointing the other way: drawn, then mirrored in place.
                region = (text_left - _px(2, scale), int(top),
                          text_left + _px(9, scale), int(bottom))
                frame.paste(frame.crop(region).transpose(
                    Image.FLIP_LEFT_RIGHT), region[:2])
                text_left += _px(16, scale)
            ink = theme.TEXT_LIGHT
            if item.extra == "accent":
                ink = accent
            elif item.extra == "danger":
                ink = theme.DANGER
            drawing.text((text_left, middle), item.label, font=body,
                         fill=ink + (255,), anchor="lm")
            if kind == "switch":
                width = _px(theme.SWITCH_WIDTH, scale)
                height = _px(theme.SWITCH_HEIGHT, scale)
                face = switch(width, height,
                              motion.get(item.key, 1.0 if item.extra else 0.0),
                              mono)
                _place_over(frame, face, right - inset - width,
                            middle - height / 2.0)
            elif kind == "language":
                drawn = motion.get("tick:" + item.key,
                                   1.0 if item.extra else 0.0)
                _check(drawing, right - inset - _px(6, scale), middle,
                       _px(11, scale), tick, drawn)
                if item.hint:
                    drawing.text((right - inset - _px(20, scale), middle),
                                 item.hint, font=small, fill=faint + (255,),
                                 anchor="rm")
            elif kind == "row" and item.hint:
                drawing.text((right - inset, middle), item.hint, font=small,
                             fill=(muted if item.extra in ("accent", "danger")
                                   else faint) + (255,), anchor="rm")
            elif kind == "row" and item.extra == "more":
                _chevron(drawing, right - inset - _px(3, scale), middle,
                         _px(9, scale), faint)
        elif kind == "separator":
            # Laid over the glass. Drawn straight onto the picture, a
            # translucent line replaces the glass's own alpha with its own,
            # and the owner saw the desktop through the slit it left.
            line = Image.new("RGBA", (right - left, max(1, _px(1, scale))),
                             (255, 255, 255, 22))
            frame.alpha_composite(line, (int(left), int(middle)))
        elif kind == "search":
            _search_field(frame, drawing, item, scale, motion, muted, faint,
                          mono=mono)
        elif kind == "keyfield":
            _search_field(frame, drawing, item, scale, motion, muted, faint,
                          lens=False, mono=mono)
        elif kind == "button":
            # The one thing to press on its page: white with dark ink, like
            # the tick, once there is something to save; the cross's grey
            # until then.
            ready = bool(item.extra)
            if mono:
                fill = theme.MONO_ACCENT if ready else theme.MONO_CONTROL
                ink = theme.TEXT_LIGHT if ready else faint
            else:
                fill = theme.ACCEPT_FILL if ready else theme.CANCEL_FILL
                ink = theme.ACCEPT_GLYPH if ready else faint
            face = _pill_label(
                right - left, bottom - top, fill, item.label, ink,
                font(max(9, _px(theme.FONT_SIZE, scale)), medium=True))
            grow = 1.0 + 0.03 * lit if ready else 1.0
            if grow > 1.002:
                face = face.resize((int(round(face.size[0] * grow)),
                                    int(round(face.size[1] * grow))),
                                   Image.LANCZOS)
            _place_over(frame, face, (left + right) / 2.0 - face.size[0] / 2.0,
                        middle - face.size[1] / 2.0)
        elif kind == "model":
            chosen, aside = item.extra
            inset = _px(10, scale)
            upper = top + (bottom - top) * 0.36
            lower = top + (bottom - top) * 0.70
            drawing.text((left + inset, upper), item.label, font=body,
                         fill=theme.TEXT_LIGHT + (255,), anchor="lm")
            drawing.text((left + inset, lower), item.hint, font=small,
                         fill=faint + (255,), anchor="lm")
            if chosen:
                _check(drawing, right - inset - _px(6, scale), middle,
                       _px(11, scale), tick)
            elif aside:
                drawing.text((right - inset, middle), aside, font=small,
                             fill=muted + (255,), anchor="rm")
        elif kind == "footer":
            drawing.text((left, middle), item.label, font=small,
                         fill=faint + (255,), anchor="lm")
        elif kind == "scrollbar":
            shown, offset = item.extra
            track = bottom - top
            length = max(_px(24, scale), int(track * shown))
            start = top + int((track - length) * offset)
            bar = sprite((right - left, length), (right - left) // 2,
                         (255, 255, 255))
            _place_over(frame, bar, left, start, 0.22)
    return frame
