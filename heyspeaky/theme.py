"""Every colour, size and timing the pill uses, in one place.

Changing how HeySpeaky looks should mean changing numbers here, not hunting
through drawing code. tools/ui_lab.py renders every state from these values,
so a change can be looked at before it ships.

The pill is small and dark: a cancel button, the waveform, and a confirm
button. Nothing else. Whatever you said lands in the window you were typing
in, so the pill has no reason to repeat it back at you.
"""

# The correction box, Ctrl+Alt+Space. Same materials as the pill - the tint,
# the bright top edge, the specular - so the two read as one app. It is a card
# rather than a capsule, so its corner is a fixed radius instead of half its
# height, and it is a window you type into, so it is nearly opaque where the
# pill is not.
BOX_WIDTH = 420
BOX_RADIUS = 16
BOX_PAD = 16
BOX_ALPHA = 0.97
BOX_GAP = 10
# The field you type in: a darker well sunk into the card, with the waveform's
# own colours running under it. That line is the one piece of colour in either
# window, and having it in both is what ties them together.
WELL_HEIGHT = 40
WELL_RADIUS = 10
WELL_FILL = (38, 38, 45)
WELL_ACCENT = 2

# The pill itself.
WIDTH = 248
HEIGHT = 54
PADDING = 10

# Glass. The desktop behind the pill is captured once, blurred by BLUR and
# tinted with TINT, which is what gives the dark pill some depth instead of
# looking like a flat sticker.
BLUR = 22
TINT = (14, 14, 17)
# How solid the capsule is. Windows composites the pill over the live desktop
# through its alpha channel, so this is real translucency, not a picture of
# the wallpaper taken a moment ago.
PILL_ALPHA = 0.90
# Kept because config and older code still name them.
TINT_STRENGTH = 0.82
TINT_STRENGTH_LIGHT = 0.91
SHADOW_OFFSET = 8
SHADOW_BLUR = 22
SHADOW_ALPHA = 0.38
# The glass edge, a thin light line brightest at the top.
EDGE_TOP = 0.22
EDGE_BOTTOM = 0.05
EDGE_WIDTH = 1.2
SPECULAR_ALPHA = 0.10

# Siri's colours, kept for the halo under the pill while it listens.
SIRI = ((10, 132, 255), (191, 90, 242), (255, 55, 95), (255, 159, 10))
RIM_BLUR = 18
RIM_ALPHA = 0.45

# Text. Only the error message uses it now.
TEXT_LIGHT = (245, 245, 247)
TEXT_DARK = (11, 11, 15)
MUTED_STRENGTH = 0.68
# Above this average brightness the backdrop counts as light.
LIGHT_BACKDROP = 138

FONT_SIZE = 13
LABEL_SIZE = 11

# The two round buttons. Left cancels and throws the recording away, right
# finishes it. Both are real buttons: you can click them.
BUTTON = 30
BUTTON_INSET = 12
CANCEL_FILL = (68, 68, 74)
CANCEL_GLYPH = (238, 238, 243)
ACCEPT_FILL = (245, 245, 247)
ACCEPT_GLYPH = (10, 10, 12)
# The confirm button turns green for the moment before the pill leaves.
DONE_FILL = (48, 209, 88)
DONE_GLYPH = (255, 255, 255)
GLYPH_STROKE = 2.2
# How solid a button is while it cannot be used.
BUTTON_DIM = 0.45

# Kept because diagnostics and older code still name it.
DOT = 10
STATE_COLOURS = {
    "listening": (255, 69, 58),
    "transcribing": (255, 159, 10),
    "done": (48, 209, 88),
    "error": (255, 69, 58),
}

# The waveform. Many thin round-capped bars rather than a few fat ones, the
# newest on the right, scrolling left - which is how every voice composer
# worth copying draws it.
BARS = 23
BAR_WIDTH = 3
BAR_GAP = 3
# A silent bar is as tall as it is wide, so it is a dot. That is what silence
# should look like: nothing was heard, and the pill says so honestly instead
# of animating to look busy.
BAR_MIN = 3
BAR_MAX = 24
BAR_FLAT = 3
BAR_LIVE = (245, 245, 247)
BAR_QUIET = (120, 120, 128)
# A soft bloom, kept subtle. Neon looks cheap at this size.
BAR_GLOW = 5
BAR_GLOW_ALPHA = 0.38
# The waveform fades out at both ends instead of stopping at a hard edge.
# One value per bar inwards from each side; the rest are full strength.
BAR_EDGE_FADE = (0.25, 0.55, 0.80)

# The buttons are lit like real ones: a highlight along the top left, a
# shadow inside the bottom right, and a soft shadow under the whole circle.
BUTTON_SHADOW = 0.34
BUTTON_INNER_LIGHT = 0.42
BUTTON_INNER_SHADE = 0.28

# Motion, in seconds.
SPRING_IN = 0.28
FADE_OUT = 0.22
HIDE_DELAY = 1.6

# Room around the capsule for its shadow. The window is this much bigger than
# the glass on every side.
SHADOW_MARGIN = 14

# A hint of a shadow under light text, for the error message.
TEXT_SHADOW = 0.45
