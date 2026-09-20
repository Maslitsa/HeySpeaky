"""The on-screen pill that sits just above the taskbar.

It is a borderless, always-on-top Tk window with three important Win32
properties:

  WS_EX_NOACTIVATE   never takes focus, so the text still goes to whatever
                     app you were typing in
  WS_EX_TRANSPARENT  clicks pass straight through it
  WS_EX_TOOLWINDOW   never appears in the taskbar or Alt+Tab

All public methods must be called on the Tk thread; App funnels cross-thread
updates through a queue for exactly that reason.
"""

import ctypes
import logging
import math
import tkinter as tk
import tkinter.font as tkfont
from collections import deque

logger = logging.getLogger("heyspeaky.overlay")

# Colour key for the transparent background; anything unlikely to be drawn.
TRANSPARENT_KEY = "#010203"

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

MONITOR_DEFAULTTONEAREST = 2


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def enable_dpi_awareness():
    """Opts into per-monitor DPI so our pixel maths matches the screen."""
    try:
        # PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            logger.debug("No DPI awareness API available")


def _blend(color_a, color_b, ratio):
    """Mixes two #rrggbb colours; ratio 0 gives color_a, 1 gives color_b."""
    ratio = max(0.0, min(1.0, ratio))
    a = [int(color_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(color_b[i:i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(x + (y - x) * ratio) for x, y in zip(a, b)]
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def _cursor_work_area():
    """Returns the work area (screen minus taskbar) of the active monitor."""
    user32 = ctypes.windll.user32
    point = _POINT()
    try:
        user32.GetCursorPos(ctypes.byref(point))
        monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            work = info.rcWork
            return work.left, work.top, work.right, work.bottom
    except OSError:
        logger.debug("Falling back to primary screen metrics", exc_info=True)
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    return 0, 0, width, height


def _monitor_scale():
    """Returns the active monitor's DPI scale factor."""
    try:
        point = _POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        monitor = ctypes.windll.user32.MonitorFromPoint(
            point, MONITOR_DEFAULTTONEAREST
        )
        dpi_x = ctypes.c_uint()
        dpi_y = ctypes.c_uint()
        # MDT_EFFECTIVE_DPI
        ctypes.windll.shcore.GetDpiForMonitor(
            monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
        )
        if dpi_x.value:
            return dpi_x.value / 96.0
    except (AttributeError, OSError):
        logger.debug("GetDpiForMonitor unavailable", exc_info=True)
    return 1.0


class Overlay:
    """Draws the recording pill and its live waveform and transcript."""

    def __init__(self, root, config):
        self._root = root
        self._cfg = config
        self._colors = config["colors"]

        self._scale = _monitor_scale()
        self._width = self._px(config["width"])
        self._height = self._px(config["height"])
        self._radius = self._px(config["corner_radius"])
        self._bar_count = int(config["bars"])

        self._state = "hidden"
        self._level = 0.0
        self._display_level = 0.0
        self._history = deque([0.0] * self._bar_count, maxlen=self._bar_count)
        self._text = ""
        self._status = ""
        self._phase = 0.0
        self._visible = False
        self._anim_job = None
        self._hide_job = None
        self._fade_job = None

        self._build_window()

    # -- geometry helpers --------------------------------------------------

    def _px(self, logical):
        return max(1, int(round(float(logical) * self._scale)))

    # -- window construction ----------------------------------------------

    def _build_window(self):
        root = self._root
        root.withdraw()
        root.overrideredirect(True)
        root.configure(bg=TRANSPARENT_KEY)
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            logger.warning("Transparent colour unsupported; using a solid pill")
        root.attributes("-alpha", 0.0)

        self._canvas = tk.Canvas(
            root,
            width=self._width,
            height=self._height,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self._canvas.pack()

        font_px = int(round(float(self._cfg["font_size"]) * 1.333 * self._scale))
        self._font = tkfont.Font(
            family=self._cfg["font_family"], size=-font_px
        )
        self._font_small = tkfont.Font(
            family=self._cfg["font_family"], size=-max(9, font_px - 2)
        )

        root.update_idletasks()
        self._apply_window_styles()
        self._layout()

    def _apply_window_styles(self):
        """Makes the window click-through, focus-proof and Alt+Tab invisible."""
        try:
            hwnd = int(self._root.wm_frame(), 16)
        except (ValueError, tk.TclError):
            logger.warning("Could not resolve the overlay window handle")
            return
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= (
            WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE
            | WS_EX_TRANSPARENT
            | WS_EX_LAYERED
        )
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        self._hwnd = hwnd

    def _position(self):
        """Docks the pill to the bottom centre of the active monitor."""
        self._scale = _monitor_scale()
        left, _top, right, bottom = _cursor_work_area()
        x = left + ((right - left) - self._width) // 2
        y = bottom - self._height - self._px(self._cfg["margin_bottom"])
        self._root.geometry(
            "{}x{}+{}+{}".format(self._width, self._height, x, y)
        )

    # -- painting ----------------------------------------------------------

    def _layout(self):
        """Computes the fixed x positions of the pill's three zones."""
        pad = self._px(16)
        self._dot_x = pad + self._px(5)
        self._dot_r = self._px(4.5)

        self._bar_w = self._px(3)
        self._bar_gap = self._px(2)
        meter_w = self._bar_count * (self._bar_w + self._bar_gap)
        self._meter_x0 = self._dot_x + self._px(16)
        self._meter_x1 = self._meter_x0 + meter_w
        self._meter_h = self._height - self._px(26)

        self._text_x = self._meter_x1 + self._px(16)
        self._text_x1 = self._width - pad

    def _round_rect_points(self, x0, y0, x1, y1, r):
        """Builds a polygon outline for a rounded rectangle."""
        steps = 7
        points = []
        corners = (
            (x1 - r, y0 + r, -math.pi / 2, 0.0),
            (x1 - r, y1 - r, 0.0, math.pi / 2),
            (x0 + r, y1 - r, math.pi / 2, math.pi),
            (x0 + r, y0 + r, math.pi, 3 * math.pi / 2),
        )
        for cx, cy, start, end in corners:
            for i in range(steps + 1):
                angle = start + (end - start) * i / steps
                points.extend(
                    (cx + r * math.cos(angle), cy + r * math.sin(angle))
                )
        return points

    def _accent(self):
        colors = self._colors
        if self._state == "transcribing":
            return colors["transcribing"]
        if self._state == "done":
            return colors["done"]
        if self._state == "error":
            return colors["error"]
        return colors["recording"]

    def _draw(self):
        canvas = self._canvas
        canvas.delete("all")
        colors = self._colors
        accent = self._accent()

        canvas.create_polygon(
            self._round_rect_points(
                1, 1, self._width - 1, self._height - 1, self._radius
            ),
            fill=colors["background"],
            outline=colors["border"],
            width=max(1, self._px(1)),
        )

        self._draw_dot(accent)
        self._draw_meter(accent)
        self._draw_text()

    def _draw_dot(self, accent):
        """A pulsing dot: alive while recording, steady otherwise."""
        if self._state == "listening":
            pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self._phase * 4.0))
        elif self._state == "transcribing":
            pulse = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(self._phase * 6.0))
        else:
            pulse = 1.0
        color = _blend(self._colors["background"], accent, pulse)
        cy = self._height / 2
        r = self._dot_r
        self._canvas.create_oval(
            self._dot_x - r, cy - r, self._dot_x + r, cy + r,
            fill=color, outline="",
        )

    def _draw_meter(self, accent):
        """Scrolling waveform while listening, a travelling wave while busy."""
        cy = self._height / 2
        half = self._meter_h / 2
        minimum = self._px(1.5)
        faded = _blend(self._colors["background"], accent, 0.35)

        for index in range(self._bar_count):
            if self._state == "listening":
                value = self._history[index]
            elif self._state == "transcribing":
                value = 0.18 + 0.32 * (
                    0.5
                    + 0.5
                    * math.sin(self._phase * 5.0 - index * 0.45)
                )
            elif self._state in ("done", "error"):
                value = 0.08
            else:
                value = 0.05

            height = max(minimum, value * half)
            x0 = self._meter_x0 + index * (self._bar_w + self._bar_gap)
            # Newest samples sit at the right and are the most saturated.
            ratio = 0.35 + 0.65 * (index / max(1, self._bar_count - 1))
            color = accent if self._state != "hidden" else faded
            color = _blend(faded, color, ratio)
            self._canvas.create_rectangle(
                x0, cy - height, x0 + self._bar_w, cy + height,
                fill=color, outline="",
            )

    def _fit_text(self, text, font, available):
        """Trims from the left so the newest words stay visible."""
        if font.measure(text) <= available:
            return text
        ellipsis = "…"
        low, high = 0, len(text)
        while low < high:
            mid = (low + high) // 2
            if font.measure(ellipsis + text[mid:]) <= available:
                high = mid
            else:
                low = mid + 1
        return ellipsis + text[low:]

    def _draw_text(self):
        available = self._text_x1 - self._text_x
        if available <= 0:
            return
        if self._text:
            body = self._fit_text(self._text, self._font, available)
            if self._state == "error":
                color = self._colors["error"]
            else:
                color = self._colors["text"]
            self._canvas.create_text(
                self._text_x, self._height / 2,
                text=body, anchor="w", fill=color, font=self._font,
            )
        elif self._status:
            body = self._fit_text(self._status, self._font_small, available)
            self._canvas.create_text(
                self._text_x, self._height / 2,
                text=body, anchor="w",
                fill=self._colors["muted"], font=self._font_small,
            )

    # -- animation ---------------------------------------------------------

    def _tick(self):
        self._phase += 0.033
        # Ease the meter towards the measured level so it never jitters.
        target = self._level
        if target > self._display_level:
            self._display_level += (target - self._display_level) * 0.55
        else:
            self._display_level += (target - self._display_level) * 0.25
        if self._state == "listening":
            self._history.append(self._display_level)
        self._draw()
        self._anim_job = self._root.after(33, self._tick)

    def _start_animation(self):
        if self._anim_job is None:
            self._tick()

    def _stop_animation(self):
        if self._anim_job is not None:
            self._root.after_cancel(self._anim_job)
            self._anim_job = None

    # -- fading ------------------------------------------------------------

    def _cancel_jobs(self):
        for attr in ("_hide_job", "_fade_job"):
            job = getattr(self, attr)
            if job is not None:
                self._root.after_cancel(job)
                setattr(self, attr, None)

    def _fade_to(self, target, step=0.12, then=None):
        current = float(self._root.attributes("-alpha"))
        if abs(current - target) <= step:
            self._root.attributes("-alpha", target)
            self._fade_job = None
            if then:
                then()
            return
        nxt = current + step if target > current else current - step
        self._root.attributes("-alpha", nxt)
        self._fade_job = self._root.after(
            16, lambda: self._fade_to(target, step, then)
        )

    # -- public API --------------------------------------------------------

    def show(self, state, status=""):
        """Reveals the pill in the given state."""
        self._cancel_jobs()
        self._state = state
        self._status = status
        if state == "listening":
            self._history = deque(
                [0.0] * self._bar_count, maxlen=self._bar_count
            )
            self._level = 0.0
            self._display_level = 0.0
        if not self._visible:
            self._position()
            self._root.deiconify()
            self._root.attributes("-topmost", True)
            # Re-assert the ex-styles: the frame window only reliably exists
            # once the window has been mapped at least once.
            self._apply_window_styles()
            self._visible = True
        self._start_animation()
        self._fade_to(float(self._cfg["opacity"]))

    def set_state(self, state, status=""):
        """Switches state without touching visibility."""
        self._state = state
        if status:
            self._status = status

    def set_level(self, level):
        self._level = max(0.0, min(1.0, float(level)))

    def set_text(self, text):
        self._text = text or ""

    def set_status(self, status):
        self._status = status or ""

    def flash(self, state, text, status="", hold=None):
        """Shows a terminal state briefly, then fades out."""
        self._cancel_jobs()
        self._state = state
        self._text = text or ""
        self._status = status
        self._level = 0.0
        self.show(state, status)
        delay = int((hold or float(self._cfg["hide_delay"])) * 1000)
        self._hide_job = self._root.after(delay, self.hide)

    def hide(self):
        """Fades out and withdraws the window."""
        self._cancel_jobs()

        def finish():
            self._stop_animation()
            self._root.withdraw()
            self._visible = False
            self._state = "hidden"
            self._text = ""
            self._status = ""

        if not self._visible:
            finish()
            return
        self._fade_to(0.0, step=0.15, then=finish)
