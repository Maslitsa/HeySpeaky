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


def button(size, kind, fill, glyph, dim=1.0):
    """A round button with a cross or a tick drawn through it.

    Drawn at four times the size and scaled down, because a thin diagonal
    stroke is exactly where Tk's lack of antialiasing shows.
    """
    key = (size, kind, fill, glyph, round(dim, 2))
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
    def at(fx, fy):
        return (pad + big * fx, pad + big * fy)

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

    # The shadow, so the pill sits above the desktop rather than on it.
    shadow = Image.new("L", big, 0)
    shadow.paste(mask, (box[0], box[1] + int(theme.SHADOW_OFFSET * scale) * SS))
    shadow = shadow.filter(
        ImageFilter.GaussianBlur(theme.SHADOW_BLUR * scale * SS / 2.0))
    shadow = shadow.point(lambda value: int(value * theme.SHADOW_ALPHA))
    base.paste((0, 0, 0, 255), (0, 0), shadow)

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

    # The capsule: dark, and not quite opaque, so the wallpaper shows through.
    body = Image.new("RGBA", capsule_size,
                     tuple(theme.TINT) + (int(255 * theme.PILL_ALPHA),))
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
         capsule_size[0] * 0.82, capsule_size[1] * 0.42),
        fill=int(255 * theme.SPECULAR_ALPHA))
    layer.paste((255, 255, 255, 255), (0, 0),
                specular.filter(ImageFilter.GaussianBlur(6 * scale * SS)))
    # Clipped to the capsule, or the highlight spills into thin air.
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    base.alpha_composite(layer, (box[0], box[1]))

    plain_box = (box[0] // SS, box[1] // SS, box[2] // SS, box[3] // SS)
    return Glass(base.resize(window, Image.LANCZOS), plain_box, scale,
                 open_share)


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
        bar_width = max(2, int(round(theme.BAR_WIDTH * scale)))
        pitch = bar_width + max(1, int(round(theme.BAR_GAP * scale)))
        tallest = max(4, int(round(theme.BAR_MAX * scale)))
        # Centred between the buttons, whatever the bar count is.
        span = len(levels) * pitch - (pitch - bar_width)
        start = inner_left + max(0, (inner_right - inner_left - span) // 2)
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
            frame.paste(bar, (start + index * pitch - spread,
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
