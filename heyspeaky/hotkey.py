"""Global Ctrl+Alt listener.

Ctrl+Alt is a modifier-only combo, so it cannot go through Windows'
RegisterHotKey. We install a low-level keyboard hook instead and run a small
state machine over it.

Timeline of a press:

    t0            press Ctrl+Alt
    t0 + 0.25s    engage  -> recording starts, overlay appears
    release
      before t0+0.7s   -> tap:  recording latches (hands free)
      after  t0+0.7s   -> hold: recording stops (push to talk)

Releasing before the engage delay does nothing at all, which is what keeps
ordinary Ctrl+Alt+<key> shortcuts and AltGr from tripping the recorder.
"""

import ctypes
import logging
import threading
import time
from ctypes import wintypes

import keyboard

logger = logging.getLogger("heyspeaky.hotkey")

class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    # All three members are declared so sizeof(INPUT) matches what SendInput
    # expects; it rejects the call outright if cbSize is wrong.
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT),
                ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
# VK_NONAME: reserved by Windows and bound to nothing. Kept because the probe
# guard in _on_key_event still recognises it.
VK_NONAME = 0xFC


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def _system_idle_seconds():
    """Seconds since Windows last saw any input, or None if unavailable.

    This is how the watchdog checks its hook without touching anything. The
    obvious alternative, injecting a key and seeing whether the hook observes it,
    works, but SendInput resets the system idle timer, so probing on a schedule
    would quietly stop the laptop from ever sleeping or blanking its screen.
    """
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        elapsed = ctypes.windll.kernel32.GetTickCount() - info.dwTime
        # GetTickCount wraps every 49 days; a negative result means we wrapped.
        return elapsed / 1000.0 if elapsed >= 0 else None
    except Exception:
        logger.debug("GetLastInputInfo unavailable", exc_info=True)
        return None


CTRL_KEYS = {"ctrl", "left ctrl", "right ctrl"}
ALT_KEYS = {"alt", "left alt", "right alt"}
ALTGR_KEYS = {"alt gr", "altgr", "right alt gr"}


class HotkeyListener:
    """Watches for the Ctrl+Alt chord and reports engage/tap/hold/cancel."""

    def __init__(self, config, on_engage, on_tap, on_hold_release, on_cancel):
        self._engage_delay = float(config["engage_delay"])
        self._tap_max = float(config["tap_max"])
        self._accept_altgr = bool(config["accept_altgr"])
        self._cancel_on_other_key = bool(config["cancel_on_other_key"])

        self._on_engage = on_engage
        self._on_tap = on_tap
        self._on_hold_release = on_hold_release
        self._on_cancel = on_cancel

        self._lock = threading.RLock()
        self._pressed = set()
        self._combo_active = False
        self._engaged = False
        self._press_started = 0.0
        self._timer = None
        self._hook = None
        self._paused = False

        self._last_event = time.monotonic()
        self._health_interval = float(config.get("health_check_seconds", 20))
        self._min_reinstall_gap = float(
            config.get("min_reinstall_seconds", 60)
        )
        self._last_reinstall = 0.0
        self._watchdog = None
        self._stop_watchdog = threading.Event()
        self.reinstalls = 0

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        """Installs the keyboard hook and starts the watchdog."""
        self._install()
        logger.info(
            "Hotkey listener active (engage %.2fs, tap threshold %.2fs)",
            self._engage_delay,
            self._tap_max,
        )
        if self._health_interval > 0 and self._watchdog is None:
            self._stop_watchdog.clear()
            self._watchdog = threading.Thread(
                target=self._watch, name="hotkey-watchdog", daemon=True
            )
            self._watchdog.start()

    def _install(self):
        self._hook = keyboard.hook(self._on_key_event)
        self._last_event = time.monotonic()

    def _uninstall(self):
        if self._hook is not None:
            try:
                keyboard.unhook(self._hook)
            except (KeyError, ValueError):
                pass
            self._hook = None

    def stop(self):
        """Removes the keyboard hook and any pending timer."""
        self._stop_watchdog.set()
        self._cancel_timer()
        self._uninstall()

    # -- watchdog ----------------------------------------------------------

    def _watch(self):
        """Reinstalls the hook when Windows silently drops it.

        Windows removes a WH_KEYBOARD_LL hook without warning if its callback
        ever overruns LowLevelHooksTimeout, and resuming from sleep can lose it
        too. Nothing is raised and the process keeps running, so the only
        symptom is that Ctrl+Alt quietly stops working, which is exactly what
        happened here after the laptop had been asleep.

        There is no API to ask whether a hook is still alive, so we infer it:
        Windows tracks when it last saw *any* input, and we track when our hook
        last saw one. If the system has had input much more recently than we
        have, events are being delivered somewhere we are not.

        A genuinely idle machine reports both as equally stale, so nothing
        happens and it can still go to sleep.
        """
        while not self._stop_watchdog.wait(self._health_interval):
            if self._paused:
                continue
            with self._lock:
                busy = self._combo_active or self._engaged
            if busy:
                continue          # never swap the hook mid-chord
            quiet_for = time.monotonic() - self._last_event
            if quiet_for < self._health_interval:
                continue          # traffic is flowing; it is fine
            idle_for = _system_idle_seconds()
            if idle_for is None or idle_for + 2.0 >= quiet_for:
                continue          # the whole machine is idle; nothing is wrong

            # Windows has seen input we have not. Usually that just means the
            # mouse moved. GetLastInputInfo counts mouse events and a keyboard
            # hook never sees them, so this is not proof of a dead hook, and
            # reinstalling on every mouse twitch would churn the hook all day.
            # Rate limiting keeps it to a refresh whenever you come back to the
            # machine, which is exactly when a hook lost to sleep needs
            # replacing, while staying quiet during continuous mouse use.
            since_last = time.monotonic() - self._last_reinstall
            if since_last < self._min_reinstall_gap:
                continue

            self._last_reinstall = time.monotonic()
            self.reinstalls += 1
            logger.info(
                "Keyboard hook saw nothing for %.0fs while Windows saw input "
                "%.0fs ago; refreshing the hook (#%d)",
                quiet_for, idle_for, self.reinstalls,
            )
            with self._lock:
                self._reset_locked()
                self._pressed.clear()
            self._uninstall()
            try:
                self._install()
            except Exception:
                logger.exception("Could not reinstall the keyboard hook")

    def set_paused(self, paused):
        """Suspends recognition without removing the hook."""
        with self._lock:
            self._paused = paused
            if paused:
                self._cancel_timer()
                self._combo_active = False
                self._engaged = False
        logger.info("Hotkey listener %s", "paused" if paused else "resumed")

    @property
    def paused(self):
        return self._paused

    def notify_recording_finished(self):
        """Clears engaged state after the controller ends a recording."""
        with self._lock:
            self._engaged = False

    # -- internals ---------------------------------------------------------

    def _classify(self, name):
        if name in CTRL_KEYS:
            return "ctrl"
        if name in ALT_KEYS:
            return "alt"
        if name in ALTGR_KEYS:
            # AltGr arrives as an implicit Ctrl plus this key. Treating it as
            # "other" makes the whole chord fail closed.
            return "alt" if self._accept_altgr else "other"
        return "other"

    def _on_key_event(self, event):
        # Stamped before anything else, including the early returns below: the
        # watchdog uses it as proof the hook is still being delivered to.
        self._last_event = time.monotonic()
        name = (event.name or "").lower()
        if not name:
            return
        # The watchdog's own probe must not reach the state machine. It counts
        # as "some other key", which would cancel a latched recording that has
        # been running quietly while you talk. The watchdog would end the
        # very dictation it exists to protect.
        if getattr(event, "scan_code", None) == -VK_NONAME \
                or name.strip() == "reserved":
            return
        kind = self._classify(name)

        with self._lock:
            if event.event_type == keyboard.KEY_DOWN:
                self._pressed.add(name)
            else:
                self._pressed.discard(name)

            if self._paused:
                return

            has_ctrl = any(self._classify(k) == "ctrl" for k in self._pressed)
            has_alt = any(self._classify(k) == "alt" for k in self._pressed)
            has_other = any(
                self._classify(k) == "other" for k in self._pressed
            )

            # A non-modifier pressed while we are engaged means the user is
            # really using a shortcut, not dictating.
            if (
                self._engaged
                and self._cancel_on_other_key
                and kind == "other"
                and event.event_type == keyboard.KEY_DOWN
            ):
                logger.info("Cancelled by '%s'", name)
                self._reset_locked()
                self._fire(self._on_cancel)
                return

            combo = has_ctrl and has_alt and not has_other
            if combo and not self._combo_active:
                self._combo_active = True
                self._press_started = time.monotonic()
                self._start_timer()
            elif not combo and self._combo_active:
                self._combo_active = False
                self._cancel_timer()
                held = time.monotonic() - self._press_started
                if self._engaged:
                    self._engaged = False
                    if held < self._tap_max:
                        self._fire(self._on_tap)
                    else:
                        self._fire(self._on_hold_release)

    def _reset_locked(self):
        self._cancel_timer()
        self._combo_active = False
        self._engaged = False

    def _start_timer(self):
        self._cancel_timer()
        self._timer = threading.Timer(self._engage_delay, self._engage)
        self._timer.daemon = True
        self._timer.start()

    def _cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _engage(self):
        with self._lock:
            if not self._combo_active or self._paused or self._engaged:
                return
            self._engaged = True
        self._fire(self._on_engage)

    @staticmethod
    def _fire(callback):
        """Runs a callback off the hook thread so the hook never stalls."""
        if callback is None:
            return
        threading.Thread(target=callback, daemon=True).start()


def wait_for_modifiers_released(timeout=5.0):
    """Blocks until Ctrl/Alt/Shift/Win are all up, or the timeout expires."""
    deadline = time.monotonic() + timeout
    watched = ("ctrl", "alt", "shift", "windows")
    while time.monotonic() < deadline:
        try:
            if not any(keyboard.is_pressed(key) for key in watched):
                return True
        except (ValueError, ImportError):
            return True
        time.sleep(0.02)
    logger.warning("Modifiers still held after %.1fs", timeout)
    return False
