"""Every colour, size and timing the pill uses, in one place.

Changing how HeySpeaky looks should mean changing numbers here, not hunting
through drawing code. tools/ui_lab.py renders every state from these values,
so a change can be looked at before it ships.

The pill is small and dark: a cancel button, the waveform, and a confirm
button. Nothing else. Whatever you said lands in the window you were typing
in, so the pill has no reason to repeat it back at you.
"""

# The correction composer, Ctrl+Alt+Win. The pill's twin: the same glass, a
# cross on the left and a tick on the right, and a field to type into where
# the waveform would be. More solid than the pill, because it is read rather
# than glanced at. Around the field runs a ring of the waveform's colours that
# turns once as it opens and a little with every key - after an MIT-licensed
# uiverse.io input by Lakshay-art, whose border is two arcs of a conic
# gradient chasing each other round the field.
COMPOSER_WIDTH = 440
COMPOSER_HEIGHT = 58
COMPOSER_ALPHA = 0.95
# Room around the capsule for its shadow and its glow, and above it for the
# small labels: what was heard, and what a button does.
COMPOSER_MARGIN = 24
COMPOSER_TOP = 30
COMPOSER_BUTTON = 34
COMPOSER_BUTTON_INSET = 12
FIELD_GAP = 9
FIELD_HEIGHT = 38
# Solid, and exactly the typing field's own colour, so the widget laid over it
# cannot be told apart from the picture underneath.
FIELD_FILL = (9, 9, 12)
FIELD_EDGE = 0.12
FIELD_TEXT = 15
FIELD_INSET = 6
# The selection, in a dark cut of the palette's purple rather than the blue
# Windows would pick.
SELECT_FILL = (92, 58, 150)
# The ring: a thin sharp line plus a soft glow outside it, never inside, so
# the field stays one flat colour under the text.
GLOW_RING = 1.6
GLOW_SPREAD = 11
GLOW_SETTLED = 0.72
GLOW_FLARE = 1.0
GLOW_SWEEP = 1.6
GLOW_NUDGE = 16
# The labels above the capsule.
CHIP_FILL = (24, 24, 29)
CHIP_ALPHA = 0.94
CHIP_HEIGHT = 22
CHIP_PAD = 9
CHIP_GAP = 7
# Motion, in seconds, and the size of it.
COMPOSER_OPEN = 0.32
COMPOSER_CLOSE = 0.18
COMPOSER_DONE_HOLD = 0.34
COMPOSER_SLIDE = 10
HOVER_GROW = 1.12
HOVER_TURN = 90
HOVER_LIFT = 2
PRESS_SHRINK = 0.88
TIP_DELAY = 0.35
SHAKE = 9

# The tray panel: what a click on the tray icon opens, in place of the grey
# Windows menu. The same glass as the pill and the composer, as a card. The
# buttons speak the pill's language: the chosen thing is white with dark ink,
# like the tick; everything else is the cross's grey. The one piece of colour
# is the waveform's gradient, on a switch that is on.
PANEL_WIDTH = 320
PANEL_RADIUS = 22
PANEL_ALPHA = 0.96
PANEL_PAD = 16
PANEL_MARGIN = 26
ROW_HEIGHT = 34
ROW_RADIUS = 10
ROW_HOVER = 0.08
SECTION_GAP = 12
LABEL_GAP = 7
PANEL_CHIP_HEIGHT = 28
PANEL_CHIP_GAP = 6
SWITCH_WIDTH = 38
SWITCH_HEIGHT = 22
SEGMENT_HEIGHT = 32
TITLE_SIZE = 15
HINT_SIZE = 11
LIST_HEIGHT = 330
PANEL_OPEN = 0.22
PANEL_CLOSE = 0.14
READY_DOT = (48, 209, 88)
BUSY_DOT = (255, 69, 58)
PAUSED_DOT = (142, 142, 147)

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
