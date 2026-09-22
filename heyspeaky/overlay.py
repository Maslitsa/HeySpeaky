"""The on-screen pill that sits just above the taskbar.

It is a borderless, always-on-top Tk window with three important Win32
properties:

  WS_EX_NOACTIVATE   never takes focus, so the text still goes to whatever
                     app you were typing in
  WS_EX_TRANSPARENT  clicks pass straight through it
  WS_EX_TOOLWINDOW   never appears in the taskbar or Alt+Tab

The cross and the tick are real buttons, and a window cannot both be clicked
and be clicked through. So WS_EX_TRANSPARENT is dropped while
overlay.buttons_clickable is on, and for as long as the pill is on screen its
own small rectangle - a few hundred pixels above the taskbar - takes clicks
instead of passing them down. WS_EX_NOACTIVATE still holds, so clicking it
never steals focus and never sends your text to the wrong window.

The window itself is opaque. It looks like glass because it photographs the
desktop underneath before it appears and draws that, blurred, as its own
background - see glass.py for why Windows leaves no better option.

All public methods must be called on the Tk thread; App funnels cross-thread
updates through a queue for exactly that reason.
"""

import ctypes
import logging
import threading
import tkinter as tk
from collections import deque

from PIL import Image, ImageTk

from . import glass, theme

logger = logging.getLogger("heyspeaky.overlay")

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

MONITOR_DEFAULTTONEAREST = 2

# How often the waveform is redrawn. A frame costs a fraction of a
# millisecond, and 50 a second is what stops it looking like it steps.
TICK_MS = 20
# How far the pill slides up as it appears, in logical pixels.
SLIDE = 10


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
    """Draws the recording pill, its live waveform and the transcript."""

    def __init__(self, root, config, on_cancel=None, on_accept=None):
        self._root = root
        self._cfg = config
        self._scale = _monitor_scale()
        self._on_cancel = on_cancel
        self._on_accept = on_accept
        self._clickable = bool(config.get("buttons_clickable", True))

        self._state = "listening"
        self._text = ""
        self._status = ""
        self._label = ""
        self._level = 0.0
        self._shown_level = 0.0
        self._levels = deque([0.0] * theme.BARS, maxlen=theme.BARS)

        self._glass = None
        self._photo = None
        self._visible = False
        self._anim_job = None
        self._hide_job = None
        self._fade_job = None
        self._geometry = (0, 0, 0, 0)

        self._build_window()

    # -- window ------------------------------------------------------------

    def _build_window(self):
        root = self._root
        root.withdraw()
        root.overrideredirect(True)
        root.configure(bg="#000000")
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.0)

        self._holder = tk.Label(root, bd=0, highlightthickness=0, bg="#000000")
        self._holder.pack()
        if self._clickable:
            self._holder.bind("<Button-1>", self._on_click)
        root.update_idletasks()
        self._apply_window_styles()

    def _apply_window_styles(self):
        """Makes the window click-through, focus-proof and Alt+Tab invisible."""
        try:
            hwnd = int(self._root.wm_frame(), 16)
        except (ValueError, tk.TclError):
            logger.warning("Could not resolve the overlay window handle")
            return
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED
        if not self._clickable:
            style |= WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

    # -- the two buttons ---------------------------------------------------

    def _on_click(self, event):
        """Works out which button was hit, if either."""
        if self._glass is None or not self._visible:
            return
        for name, box in glass.button_boxes(self._glass).items():
            if box[0] <= event.x <= box[2] and box[1] <= event.y <= box[3]:
                self._press(name)
                return

    def _press(self, name):
        if name == "cancel":
            callback = self._on_cancel
            allowed = self._state in ("listening", "transcribing")
        else:
            callback = self._on_accept
            allowed = self._state == "listening"
        if callback is None or not allowed:
            return
        logger.info("Pill %s button clicked", name)
        # Off the Tk thread: the controller takes locks and stops the
        # recorder, and the window must keep drawing while it does.
        threading.Thread(target=callback, daemon=True).start()

    def _window_size(self):
        margin = int(round(theme.SHADOW_MARGIN * self._scale))
        return (int(round(theme.WIDTH * self._scale)),
                int(round(theme.HEIGHT * self._scale)) + margin * 2)

    def _place(self, lift=0):
        """Docks the pill to the bottom centre of the monitor with the mouse."""
        width, height = self._window_size()
        left, _top, right, bottom = _cursor_work_area()
        x = left + ((right - left) - width) // 2
        margin_bottom = int(round(float(self._cfg["margin_bottom"])
                                  * self._scale))
        y = bottom - height - margin_bottom + lift
        self._geometry = (x, y, width, height)
        self._root.geometry("{}x{}+{}+{}".format(width, height, x, y))

    # -- glass -------------------------------------------------------------

    def _grab_backdrop(self):
        """Photographs the desktop where the pill is about to appear."""
        x, y, width, height = self._geometry
        try:
            from PIL import ImageGrab

            return ImageGrab.grab(bbox=(x, y, x + width, y + height),
                                  all_screens=True)
        except Exception:
            logger.debug("Could not photograph the desktop", exc_info=True)
            return Image.new("RGB", (width, height), (24, 24, 28))

    def _rebuild(self, backdrop=None):
        """Rebuilds the glass. Costs about 50 ms, so not every frame."""
        if backdrop is None:
            backdrop = self._backdrop
        self._backdrop = backdrop
        self._glass = glass.prepare(
            backdrop, rim=(self._state == "listening"), scale=self._scale)

    _backdrop = None

    # -- painting ----------------------------------------------------------

    def _paint(self):
        if self._glass is None:
            return
        frame = glass.paint(
            self._glass,
            state=self._state,
            levels=list(self._levels) if self._state in ("listening",
                                                         "transcribing")
            else None,
            text=self._text,
            status=self._status,
            label=self._label,
        )
        self._photo = ImageTk.PhotoImage(frame)
        self._holder.configure(image=self._photo)

    def _tick(self):
        # Loudness measured straight off the microphone spends most of its
        # range on shouting, so ordinary speech would barely lift the bars.
        # The curve here spreads the quiet end out, which is the half anyone
        # actually looks at.
        target = max(0.0, min(1.0, self._level)) ** 0.62
        # Then ease towards it: quick to rise so it feels immediate, slower to
        # fall so the wave settles instead of flickering.
        if target > self._shown_level:
            self._shown_level += (target - self._shown_level) * 0.42
        else:
            self._shown_level += (target - self._shown_level) * 0.16
        if self._state == "listening":
            self._levels.append(self._shown_level)
        self._paint()
        self._anim_job = self._root.after(TICK_MS, self._tick)

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

    def _fade_to(self, target, step=0.16, then=None):
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

    def _slide_in(self, remaining):
        """A short rise as it appears, the way a sheet lifts on iOS."""
        if remaining <= 0:
            self._place()
            return
        self._place(lift=int(round(SLIDE * self._scale * remaining / 6.0)))
        self._root.after(16, lambda: self._slide_in(remaining - 1))

    # -- public API --------------------------------------------------------

    def show(self, state, status=""):
        """Reveals the pill in the given state."""
        self._cancel_jobs()
        self._state = state
        self._status = status
        self._text = ""
        if state == "listening":
            self._levels = deque([0.0] * theme.BARS, maxlen=theme.BARS)
            self._level = 0.0
            self._shown_level = 0.0

        self._scale = _monitor_scale()
        self._root.withdraw()
        self._place()
        self._rebuild(self._grab_backdrop())
        self._paint()
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._apply_window_styles()
        self._visible = True
        self._start_animation()
        self._slide_in(6)
        self._fade_to(float(self._cfg["opacity"]))

    def set_state(self, state, status=""):
        """Switches state without touching visibility."""
        rim_changes = (state == "listening") != (self._state == "listening")
        self._state = state
        if status:
            self._status = status
        if rim_changes and self._visible:
            self._rebuild()

    def set_level(self, level):
        self._level = max(0.0, min(1.0, float(level)))

    def set_text(self, text):
        self._text = text or ""

    def set_status(self, status):
        self._status = status or ""

    def set_label(self, label):
        """The small note on the right, such as which engine is in use."""
        self._label = label or ""

    def flash(self, state, text, status="", hold=None):
        """Shows a terminal state briefly, then fades out."""
        self._cancel_jobs()
        was_visible = self._visible
        self._state = state
        self._text = text or ""
        self._status = status
        self._level = 0.0
        self._shown_level = 0.0
        if not was_visible:
            self.show(state, status)
            self._text = text or ""
        else:
            self._rebuild()
        self._paint()
        delay = int((hold or float(self._cfg["hide_delay"])) * 1000)
        self._hide_job = self._root.after(delay, self.hide)

    def hide(self):
        """Fades the pill out and takes the window off screen."""
        self._cancel_jobs()

        def finish():
            self._stop_animation()
            self._root.withdraw()
            self._visible = False

        if not self._visible:
            finish()
            return
        self._fade_to(0.0, then=finish)
