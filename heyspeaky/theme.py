"""Every colour, size and timing the pill uses, in one place.

Changing how HeySpeaky looks should mean changing numbers here, not hunting
through drawing code. tools/ui_lab.py renders every state from these values,
so a change can be looked at before it ships.
"""

# The pill itself.
WIDTH = 620
HEIGHT = 58
COMPACT_WIDTH = 240
PADDING = 20

# Glass. The desktop behind the pill is captured once, blurred by BLUR and
# tinted with TINT, which is what makes it look like frosted glass rather than
# a flat panel.
BLUR = 26
TINT = (255, 255, 255)
TINT_STRENGTH = 0.16
# Over a light desktop the glass needs more milk, or the page behind it keeps
# competing with the text on top.
TINT_STRENGTH_LIGHT = 0.34
SHADOW_OFFSET = 10
SHADOW_BLUR = 26
SHADOW_ALPHA = 0.32
# The bright glass edge, brightest at the top.
EDGE_TOP = 0.62
EDGE_BOTTOM = 0.10
EDGE_WIDTH = 1.6
SPECULAR_ALPHA = 0.30

# Siri's colours, used for the rim glow and the waveform while listening.
SIRI = ((10, 132, 255), (191, 90, 242), (255, 55, 95), (255, 159, 10))
RIM_BLUR = 16
RIM_ALPHA = 0.62

# Text. Which one is used is decided per frame from how bright the captured
# backdrop is, so the pill stays readable on a white page and on a dark one.
TEXT_LIGHT = (245, 245, 247)
TEXT_DARK = (11, 11, 15)
# How solid the quieter text is, against the same ink colour.
MUTED_STRENGTH = 0.68
# Above this average brightness the backdrop counts as light.
LIGHT_BACKDROP = 138

FONT_SIZE = 13
LABEL_SIZE = 11

# The dot on the left.
DOT = 10
STATE_COLOURS = {
    "listening": (255, 69, 58),
    "transcribing": (255, 159, 10),
    "done": (48, 209, 88),
    "error": (255, 69, 58),
}

# The waveform.
BARS = 18
BAR_WIDTH = 4
BAR_GAP = 3
BAR_MIN = 6
BAR_MAX = 26
BAR_FLAT = 5
BAR_QUIET = (150, 150, 155)

# Motion, in seconds.
SPRING_IN = 0.28
FADE_OUT = 0.22
HIDE_DELAY = 1.6

# Room around the capsule for its shadow. The window is this much bigger than
# the glass on every side.
SHADOW_MARGIN = 14

# Light text over a bright patch of wallpaper needs a hint of a shadow, or it
# dissolves into it.
TEXT_SHADOW = 0.45
