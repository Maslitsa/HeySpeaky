"""The on-screen pill that sits just above the taskbar.

It is a borderless, always-on-top Tk window with three important Win32
properties:

  WS_EX_NOACTIVATE   never takes focus, so the text still goes to whatever
                     app you were typing in
  WS_EX_LAYERED      drawn with a real alpha channel, see below
  WS_EX_TOOLWINDOW   never appears in the taskbar or Alt+Tab

**The window is not painted by Tk.** Each frame is a PIL image with an alpha
channel, handed to Windows through `UpdateLayeredWindow`, which composites it
over whatever is really on the screen at that moment.

That matters, and it is worth saying why. This used to be an opaque window
that photographed the desktop underneath itself the instant before it
appeared, and drew that picture, blurred, as its own background - because a
click-through window cannot ask Windows to blur what is behind it. It looked
like glass right up until anything underneath moved. Then the picture was of
a desktop that no longer existed, and the pill showed as a bright rectangle
with somebody else's pixels inside it. There is no patching that: the picture
is stale the moment it is taken.

With a real alpha channel there is nothing to go stale. The shadow is soft
against the live desktop, the capsule is genuinely translucent, and - because
Windows hit-tests a layered window through its alpha - clicks land on the
pill's own pixels and pass straight through everywhere else, instead of the
whole rectangle swallowing them.

All public methods must be called on the Tk thread; App funnels cross-thread
updates through a queue for exactly that reason.
"""

import ctypes
import logging
import threading
import tkinter as tk
from collections import deque
from ctypes import wintypes

from PIL import Image, ImageChops

from . import glass, theme

logger = logging.getLogger("heyspeaky.overlay")

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

MONITOR_DEFAULTTONEAREST = 2

AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
ULW_ALPHA = 0x00000002
BI_RGB = 0
DIB_RGB_COLORS = 0

# How often the waveform is redrawn. A frame costs a fraction of a
# millisecond, and 50 a second is what stops it looking like it steps.
TICK_MS = 20
# How far the pill slides up as it appears, in logical pixels.
SLIDE = 10


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


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


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


def _declare():
    """Argument types, so no handle is truncated on 64-bit Windows."""
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.UpdateLayeredWindow.restype = wintypes.BOOL
    user32.UpdateLayeredWindow.argtypes = [
        wintypes.HWND, wintypes.HDC, ctypes.POINTER(_POINT),
        ctypes.POINTER(_SIZE), wintypes.HDC, ctypes.POINTER(_POINT),
        wintypes.DWORD, ctypes.POINTER(_BLENDFUNCTION), wintypes.DWORD,
    ]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC, ctypes.POINTER(_BITMAPINFO), wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
    ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]


_declare()


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


def premultiplied(frame):
    """BGRA with the colours scaled by alpha, which is what Windows wants."""
    red, green, blue, alpha = frame.split()
    return Image.merge("RGBA", (
        ImageChops.multiply(blue, alpha),
        ImageChops.multiply(green, alpha),
        ImageChops.multiply(red, alpha),
        alpha,
    )).tobytes()


def layered_styles(hwnd, clickable=True, focusable=False):
    """Layered, focus-proof and Alt+Tab invisible.

    Shared with the correction composer's glass, which is the same kind of
    window: it is clicked, never focused. The tray panel is the one layered
    window that may take focus - it is a menu, and has to hear Escape and
    know when it has been clicked away from - so it asks for `focusable`.
    """
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_TOOLWINDOW | WS_EX_LAYERED
    if focusable:
        style &= ~WS_EX_NOACTIVATE
    else:
        style |= WS_EX_NOACTIVATE
    if not clickable:
        # Then every pixel passes clicks through, not only the
        # transparent ones. For anyone who turns the buttons off.
        style |= WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


def present(hwnd, surface, frame, opacity):
    """Hands one finished frame to Windows, alpha and all."""
    if not hwnd or not surface.ensure(frame.size):
        return False
    surface.write(premultiplied(frame))
    blend = _BLENDFUNCTION(AC_SRC_OVER, 0,
                           int(max(0, min(255, opacity * 255))),
                           AC_SRC_ALPHA)
    size = _SIZE(frame.size[0], frame.size[1])
    source = _POINT(0, 0)
    ok = ctypes.windll.user32.UpdateLayeredWindow(
        hwnd, None, None, ctypes.byref(size), surface.dc,
        ctypes.byref(source), 0, ctypes.byref(blend), ULW_ALPHA)
    if not ok:
        logger.debug("UpdateLayeredWindow refused the frame (%d)",
                     ctypes.GetLastError())
    return bool(ok)


def window_handle(window):
    """The Win32 handle of a Tk toplevel's frame, or 0."""
    try:
        return int(window.wm_frame(), 16)
    except (ValueError, tk.TclError):
        logger.warning("Could not resolve a window handle")
        return 0


class Surface:
    """A device bitmap the size of the window, reused between frames.

    Making one costs a few hundred microseconds, which is affordable once and
    not fifty times a second.
    """

    def __init__(self):
        self.size = None
        self._screen_dc = None
        self._dc = None
        self._bitmap = None
        self._old = None
        self._bits = None

    def _release(self):
        gdi32 = ctypes.windll.gdi32
        if self._dc and self._old:
            gdi32.SelectObject(self._dc, self._old)
        if self._bitmap:
            gdi32.DeleteObject(self._bitmap)
        if self._dc:
            gdi32.DeleteDC(self._dc)
        if self._screen_dc:
            ctypes.windll.user32.ReleaseDC(None, self._screen_dc)
        self.size = None
        self._screen_dc = self._dc = self._bitmap = self._old = None
        self._bits = None

    def ensure(self, size):
        if self.size == size:
            return True
        self._release()
        width, height = size
        gdi32 = ctypes.windll.gdi32
        self._screen_dc = ctypes.windll.user32.GetDC(None)
        self._dc = gdi32.CreateCompatibleDC(self._screen_dc)
        info = _BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        # Negative height: rows run top to bottom, as PIL hands them over.
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        bits = ctypes.c_void_p()
        self._bitmap = gdi32.CreateDIBSection(
            self._dc, ctypes.byref(info), DIB_RGB_COLORS,
            ctypes.byref(bits), None, 0)
        if not self._bitmap:
            logger.error("Could not create the pill's bitmap")
            self._release()
            return False
        self._bits = bits
        self._old = gdi32.SelectObject(self._dc, self._bitmap)
        self.size = size
        return True

    def write(self, data):
        ctypes.memmove(self._bits, data, len(data))

    @property
    def dc(self):
        return self._dc

    def close(self):
        self._release()


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

        # Which button the pointer is on, and how far each has grown, turned
        # and risen towards it: the correction composer's buttons do the same.
        self._hover = None
        self._motion = {"cancel": [1.0, 0.0, 0.0], "accept": [1.0, 0.0, 0.0]}

        self._glass = None
        self._surface = Surface()
        self._opacity = 0.0
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
        # Deliberately no "-alpha": Tk sets that through
        # SetLayeredWindowAttributes, and a window that has been given one of
        # those can never be updated with UpdateLayeredWindow again. The fade
        # is done with the blend function instead.
        if self._clickable:
            root.bind("<Button-1>", self._on_click)
            # Pointing never focuses a window; only its drawing answers.
            root.bind("<Motion>", self._on_motion)
            root.bind("<Enter>", self._on_motion)
            root.bind("<Leave>", self._on_leave)
        root.update_idletasks()
        self._apply_window_styles()

    def _hwnd(self):
        return window_handle(self._root)

    def _apply_window_styles(self):
        """Layered, focus-proof and Alt+Tab invisible."""
        layered_styles(self._hwnd(), self._clickable)

    # -- the two buttons ---------------------------------------------------

    def _on_click(self, event):
        """Works out which button was hit, if either."""
        if self._glass is None or not self._visible:
            return
        for name, box in glass.button_boxes(self._glass).items():
            if box[0] <= event.x <= box[2] and box[1] <= event.y <= box[3]:
                self._press(name)
                return

    def _usable(self, name):
        if name == "cancel":
            return self._state in ("listening", "transcribing")
        return self._state == "listening"

    def _on_motion(self, event):
        name = None
        if self._glass is not None and self._visible:
            for candidate, box in glass.button_boxes(self._glass).items():
                if (box[0] <= event.x <= box[2] and box[1] <= event.y <= box[3]
                        and self._usable(candidate)):
                    name = candidate
        self._set_hover(name)

    def _on_leave(self, _event=None):
        self._set_hover(None)

    def _set_hover(self, name):
        if name == self._hover:
            return
        self._hover = name
        try:
            self._root.configure(cursor="hand2" if name else "")
        except tk.TclError:
            pass

    def _ease_buttons(self):
        """One frame of each button moving towards how it should look."""
        scale = self._scale
        for name, motion in self._motion.items():
            on = self._hover == name and self._usable(name)
            targets = (theme.HOVER_GROW if on else 1.0,
                       theme.HOVER_TURN if on and name == "cancel" else 0.0,
                       theme.HOVER_LIFT * scale if on and name == "accept"
                       else 0.0)
            for index, target in enumerate(targets):
                rate = 0.25 if index == 1 else 0.34
                step = (target - motion[index]) * rate
                motion[index] = target if abs(step) < 0.001 \
                    else motion[index] + step

    def _hover_frame(self):
        return dict((name, (motion[0], int(round(motion[1] / 10.0)) * 10,
                            motion[2]))
                    for name, motion in self._motion.items())

    def _press(self, name):
        if name == "cancel":
            callback = self._on_cancel
        else:
            callback = self._on_accept
        if callback is None or not self._usable(name):
            return
        logger.info("Pill %s button clicked", name)
        # Off the Tk thread: the controller takes locks and stops the
        # recorder, and the window must keep drawing while it does.
        threading.Thread(target=callback, daemon=True).start()

    def _window_size(self):
        margin = int(round(theme.SHADOW_MARGIN * self._scale))
        return (int(round(theme.WIDTH * self._scale)),
                int(round(theme.HEIGHT * self._scale)) + margin * 2)

    @property
    def scale(self):
        """The monitor's DPI scale, so other windows can match the pill."""
        return self._scale

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

    # -- the capsule -------------------------------------------------------

    def _rebuild(self):
        """Rebuilds the parts that do not change from frame to frame."""
        self._glass = glass.prepare(rim=(self._state == "listening"),
                                    scale=self._scale)

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
            hover=self._hover_frame(),
        )
        self._present(frame)

    def _present(self, frame):
        """Hands one finished frame to Windows, alpha and all."""
        present(self._hwnd(), self._surface, frame, self._opacity)

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
        self._ease_buttons()
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
        current = self._opacity
        if abs(current - target) <= step:
            self._opacity = target
            self._paint()
            self._fade_job = None
            if then:
                then()
            return
        self._opacity = current + step if target > current else current - step
        self._paint()
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
        self._rebuild()
        self._opacity = 0.0
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
            self._hover = None
            for motion in self._motion.values():
                motion[:] = [1.0, 0.0, 0.0]

        if not self._visible:
            finish()
            return
        self._fade_to(0.0, then=finish)
