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
                specular_blur):
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
        fill=int(255 * theme.SPECULAR_ALPHA))
    layer.paste((255, 255, 255, 255), (0, 0),
                specular.filter(
                    ImageFilter.GaussianBlur(specular_blur * scale * SS)))
    # Clipped to the capsule, or the highlight spills into thin air.
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    base.alpha_composite(layer, (box[0], box[1]))


def paint(glass, state="listening", levels=None, text="", status="",
          label=""):
    """One frame: the prepared glass, plus the parts that move."""
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
    cross = button(size, "cancel", theme.CANCEL_FILL, theme.CANCEL_GLYPH,
                   cancel_dim)
    # The sprite is wider than the button: it carries its own shadow.
    bleed = (cross.size[0] - size) // 2
    frame.paste(cross, (boxes["cancel"][0] - bleed, boxes["cancel"][1] - bleed),
                cross)

    # Right: finish. It goes green for the moment before the pill leaves.
    if state == "done":
        tick = button(size, "accept", theme.DONE_FILL, theme.DONE_GLYPH)
    elif state == "error":
        tick = button(size, "accept", theme.ACCEPT_FILL, theme.ACCEPT_GLYPH,
                      theme.BUTTON_DIM)
    else:
        tick = button(size, "accept", theme.ACCEPT_FILL, theme.ACCEPT_GLYPH)
    frame.paste(tick, (boxes["accept"][0] - bleed, boxes["accept"][1] - bleed),
                tick)

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


class GlowRing(object):
    """The coloured ring round the field, cheap enough to turn every frame.

    Everything that depends only on the shape - the sharp line, the soft glow
    outside it, and the angle of every pixel from the field's centre - is
    worked out once. A frame is then one table lookup: which colour is at
    this angle once the ring has turned this far.
    """

    def __init__(self, layout, scale):
        field = layout["field"]
        window = layout["window"]
        spread = max(2, _px(theme.GLOW_SPREAD, scale))
        reach = spread * 2
        left, top = max(0, field[0] - reach), max(0, field[1] - reach)
        right = min(window[0], field[2] + reach)
        bottom = min(window[1], field[3] + reach)
        self.origin = (left, top)
        self.size = (right - left, bottom - top)

        k = 4
        big = (self.size[0] * k, self.size[1] * k)
        rect = ((field[0] - left) * k, (field[1] - top) * k,
                (field[2] - left) * k - 1, (field[3] - top) * k - 1)
        radius = (field[3] - field[1]) * k // 2

        def outline(width):
            image = Image.new("L", big, 0)
            ImageDraw.Draw(image).rounded_rectangle(
                rect, radius=radius, outline=255, width=max(1, int(width)))
            return image.resize(self.size, Image.LANCZOS)

        inside = Image.new("L", big, 0)
        ImageDraw.Draw(inside).rounded_rectangle(rect, radius=radius,
                                                 fill=255)
        inside = np.asarray(inside.resize(self.size, Image.LANCZOS),
                            np.float32) / 255.0

        self._line = np.asarray(outline(theme.GLOW_RING * scale * k),
                                np.float32) / 255.0
        wide = outline(3 * scale * k).filter(
            ImageFilter.GaussianBlur(spread / 2.0))
        # Outside the field only, so the field stays one flat colour and the
        # typing widget laid over it cannot be told from the picture.
        glow = np.asarray(wide, np.float32) / 255.0 * (1.0 - inside)
        self._glow = np.clip(glow * 2.2, 0.0, 1.0)

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


class Composer(object):
    """The parts of the correction composer that stay still while it is up."""

    __slots__ = ("layout", "shell", "field", "ring", "scale")

    def __init__(self, layout, shell, field, ring, scale):
        self.layout = layout
        self.shell = shell
        self.field = field
        self.ring = ring
        self.scale = scale


def composer(scale=1.0):
    """Builds the composer's glass, field and ring. Once per opening.

    The glass is the pill's own - the same shadow, tint, edge and specular,
    through the same helpers - only wider and more solid.
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
    _glass_body(shell, box, mask, radius, scale, theme.COMPOSER_ALPHA, 0.42, 6)
    shell = shell.resize(window, Image.LANCZOS)

    field_box = layout["field"]
    field_size = (field_box[2] - field_box[0], field_box[3] - field_box[1])
    field = Image.new("RGBA", window, (0, 0, 0, 0))
    solid = sprite(field_size, field_size[1] // 2, theme.FIELD_FILL)
    field.alpha_composite(solid, (field_box[0], field_box[1]))
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


def chip(parts, scale=1.0):
    """A small dark label above the composer: what was heard, or what a
    button does. `parts` is a list of (text, muted) pairs, drawn in a row."""
    key = ("chip", tuple(parts), round(scale, 3))
    if key in _sprite_cache:
        return _sprite_cache[key]
    height = max(12, _px(theme.CHIP_HEIGHT, scale))
    pad = _px(theme.CHIP_PAD, scale)
    text_font = font(max(8, _px(theme.LABEL_SIZE, scale)))
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    widths = [measure.textlength(text, font=text_font) for text, _m in parts]
    width = int(math.ceil(sum(widths))) + pad * 2
    face = sprite((width, height), height // 2, theme.CHIP_FILL).copy()
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

    for name, box in layout["buttons"].items():
        grow, glyph_turn, lift = (buttons or {}).get(name, (1.0, 0, 0))
        size = box[2] - box[0]
        if name == "cancel":
            face = button(size, "cancel", theme.CANCEL_FILL,
                          theme.CANCEL_GLYPH, turn=glyph_turn)
        elif done:
            face = button(size, "accept", theme.DONE_FILL, theme.DONE_GLYPH)
        else:
            face = button(size, "accept", theme.ACCEPT_FILL,
                          theme.ACCEPT_GLYPH)
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
