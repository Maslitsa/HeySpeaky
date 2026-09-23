"""Global Ctrl+Alt listener.

Ctrl+Alt is a modifier-only combo, so it cannot go through Windows'
RegisterHotKey. We install a low-level keyboard hook instead and run a small
state machine over it.

Timeline of a press:

    t0            press Ctrl+Alt
    t0 + 0.25s    engage  -> recording starts, overlay appears
    release       -> recording stops (push to talk)

Releasing before the engage delay does nothing at all, which is what keeps
ordinary Ctrl+Alt+<key> shortcuts and AltGr from tripping the recorder.

That tap window is narrow and easy to miss, so hands-free is a separate
gesture, done the way Wispr Flow does it: tap the whole chord twice inside
half a second. Each tap is shorter than the engage delay, so on its own it
does nothing at all - two of them in a row is a deliberate thing to do, which
is what makes it safe to act on. While a latched recording is running a
single tap ends it, and so does a hold, as before.
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

# The longest the watchdog waits between refreshes that are not being
# answered. See `_refresh_gap`: long enough that a scrolled page is not a
# reason to churn the hook, short enough that a hook which really did die
# after all that is back within minutes.
MAX_REFRESH_GAP = 600.0


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


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def _cursor_position():
    """Where the pointer is, or None if Windows will not say.

    This is what separates a dead hook from a moving mouse: both look the same
    to GetLastInputInfo. Reading it is free and, unlike injecting a key, it
    does not reset the idle timer.
    """
    try:
        point = _POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return None
        return (point.x, point.y)
    except Exception:
        logger.debug("GetCursorPos unavailable", exc_info=True)
        return None


# Held with Ctrl+Alt, this asks what the selected words should have been.
# It was Space until the owner found Ctrl+Alt+Space already taken by another
# program on his machine: a shortcut registered with Windows reaches its
# owner first, and a hook that only watches cannot take it back. Ctrl+Alt+Win
# is nobody's, and pressed there it did not open the Start menu. The keyboard
# library names one key several ways, so each setting brings its spellings.
CORRECTION_KEYS = {
    "windows": frozenset({"windows", "left windows", "right windows"}),
    "space": frozenset({"space", "spacebar"}),
}

# Three keys pressed "together" land a little apart, and Ctrl+Alt ahead of
# the third by more than the engage delay has already started a recording.
# A correction key this soon after the chord began is part of the same
# gesture: the recording is dropped and the box opens. Later than this it is
# somebody who was dictating, and the key cancels as any other would.
CHORD_SLOP = 1.0

CTRL_KEYS = {"ctrl", "left ctrl", "right ctrl"}
ALT_KEYS = {"alt", "left alt", "right alt"}
ALTGR_KEYS = {"alt gr", "altgr", "right alt gr"}


class HotkeyListener:
    """Watches for the Ctrl+Alt chord and reports engage/tap/hold/cancel."""

    def __init__(self, config, on_engage, on_tap, on_hold_release, on_cancel,
                 on_latch=None, on_correct=None):
        self._engage_delay = float(config["engage_delay"])
        self._tap_max = float(config["tap_max"])
        self._double_gap = float(config.get("double_tap_gap", 0.5))
        self._accept_altgr = bool(config["accept_altgr"])
        self._cancel_on_other_key = bool(config["cancel_on_other_key"])

        self._on_engage = on_engage
        self._on_tap = on_tap
        self._on_hold_release = on_hold_release
        self._on_cancel = on_cancel
        self._on_latch = on_latch
        self._on_correct = on_correct
        # One key has several names depending on the layout, so a config
        # naming any of them accepts all of them. An empty value turns the
        # correction key off without disturbing anything else.
        wanted = str(config.get("correct_key", "windows")).lower().strip()
        self._correct_keys = frozenset([wanted]) if wanted else frozenset()
        for names in CORRECTION_KEYS.values():
            if wanted in names:
                self._correct_keys = names
        # Set once the correction has fired for the key being held, so that
        # neither Windows' key repeat nor the other two keys arriving after it
        # can ask twice.
        self._correction_fired = False

        self._lock = threading.RLock()
        self._pressed = set()
        self._combo_active = False
        self._engaged = False
        self._press_started = 0.0
        self._chord_taps = []
        # True while another key was pressed during the current chord, which
        # makes it a shortcut someone was typing rather than a tap at us.
        self._chord_dirty = False
        # Set by the controller, so a single tap can mean "stop" while a
        # hands-free recording is running.
        self._latched = False
        self._timer = None
        self._hook = None
        self._paused = False

        self._last_event = time.monotonic()
        self._health_interval = float(config.get("health_check_seconds", 20))
        self._min_reinstall_gap = float(
            config.get("min_reinstall_seconds", 60)
        )
        self._last_reinstall = 0.0
        self._last_cursor = None
        self._pointer_moved_at = None
        # Keys the hook has seen, and how many it had seen at the last
        # refresh: equal means nothing came through since, and that refresh
        # was answered by silence.
        self._keys_seen = 0
        self._keys_at_refresh = 0
        self._unanswered = 0
        self._last_tick_wall = 0.0
        self._installed_at = None
        self._blocked_said_at = 0.0
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
        if self._installed_at is None:
            self._installed_at = self._last_event

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
        have, events are being delivered somewhere we are not - unless that
        input was the mouse, which no keyboard hook ever sees, so we ask where
        the pointer is before believing it.

        A genuinely idle machine reports both as equally stale, so nothing
        happens and it can still go to sleep.
        """
        self._last_cursor = _cursor_position()
        self._last_tick_wall = time.time()
        while not self._stop_watchdog.wait(self._health_interval):
            # Both of these have to be sampled on every tick, before anything
            # that can skip the rest of one, so that each comparison is
            # against the tick just gone and not against whenever we last got
            # this far.
            moved = self._cursor_moved()
            wall = time.time()
            # The thread is frozen while the machine is suspended, so a wall
            # clock that jumped much further than the interval we just waited
            # says it slept. That is the case this watchdog was written for.
            resumed = wall - self._last_tick_wall > self._health_interval * 3
            self._last_tick_wall = wall

            if self._paused:
                continue
            with self._lock:
                busy = self._combo_active or self._engaged
            if busy:
                continue          # never swap the hook mid-chord

            reason = self._dead_hook_reason(moved, resumed)
            if reason is None:
                continue

            self._count_refresh()
            logger.info("Keyboard hook %s; refreshing the hook (#%d)",
                        reason, self.reinstalls)
            with self._lock:
                self._reset_locked()
                self._pressed.clear()
            self._uninstall()
            try:
                self._install()
            except Exception:
                logger.exception("Could not reinstall the keyboard hook")

    def _cursor_moved(self):
        """Whether the pointer has moved since the previous check."""
        where = _cursor_position()
        moved = (where is not None and self._last_cursor is not None
                 and where != self._last_cursor)
        self._last_cursor = where
        if moved:
            self._pointer_moved_at = time.monotonic()
        return moved

    def _pointer_explains(self, idle_for):
        """Whether the input Windows last saw falls where the pointer moved.

        A movement is only noticed at a check, and could have happened at any
        point in the interval before it. Input older than the latest check is
        outside what the latest comparison can see: 16 of the 36 refreshes on
        the owner's machine the day after the first fix, sleep aside, were
        input Windows had seen 22 to 47 seconds earlier, which no comparison
        with the check 20 seconds ago could ever have accounted for.
        """
        if self._pointer_moved_at is None or idle_for is None:
            return False
        input_at = time.monotonic() - idle_for
        return (self._pointer_moved_at - self._health_interval - 2.0
                <= input_at <= self._pointer_moved_at + 2.0)

    def _refresh_gap(self):
        """How long after one refresh the next one may happen.

        A minute, until a refresh is answered by silence. A brand-new hook
        that hears no key for the whole time after it, while Windows keeps
        counting input, says the input was almost certainly not keys - a
        scroll wheel or a click moves no pixel of the pointer - and replacing
        the hook again a minute later changes nothing but the chance of losing
        a press. 21 of the owner's 36 were that, nine of them in a row a
        minute apart. So each one answered by silence doubles the wait, up to
        MAX_REFRESH_GAP, and the first key the hook does hear brings the
        minute back.
        """
        if self._keys_seen != self._keys_at_refresh:
            return self._min_reinstall_gap
        backoff = self._min_reinstall_gap * (2 ** min(self._unanswered, 16))
        return max(self._min_reinstall_gap, min(backoff, MAX_REFRESH_GAP))

    def _count_refresh(self):
        """Books a refresh, and whether the one before it heard anything."""
        if self.reinstalls and self._keys_seen == self._keys_at_refresh:
            self._unanswered += 1
        else:
            self._unanswered = 0
        self._keys_at_refresh = self._keys_seen
        self._last_reinstall = time.monotonic()
        self.reinstalls += 1

    def _dead_hook_reason(self, moved, resumed):
        """Why the hook looks dead, or None if it looks fine.

        Kept apart from the loop above so the decision can be tested without a
        thread, a real hook or a real mouse - which matters, because getting it
        wrong is expensive in both directions: too eager and the hook is torn
        down and rebuilt all day under the user's fingers, too shy and Ctrl+Alt
        stays dead until the app is restarted.
        """
        quiet_for = time.monotonic() - self._last_event
        if quiet_for < self._health_interval:
            return None           # traffic is flowing; it is fine
        idle_for = _system_idle_seconds()
        if idle_for is None or idle_for + 2.0 >= quiet_for:
            return None           # the whole machine is idle; nothing is wrong

        # Windows has seen input we have not, and the usual reason is that the
        # mouse moved: GetLastInputInfo counts mouse events and a keyboard hook
        # never sees them. So ask where the pointer is. If it moved, the input
        # is accounted for and the hook is not on trial. If it did not, the
        # input was almost certainly a key we should have seen, which is the
        # evidence we actually wanted.
        #
        # Measured before this test existed: 455 refreshes in three days on the
        # owner's machine, one a minute for as long as he used the mouse, none
        # of which had a dead hook behind it. A refresh unhooks and rehooks, so
        # each one is a window, however small, where a Ctrl+Alt press lands on
        # nothing.
        if moved and not resumed:
            return None
        if not resumed and self._pointer_explains(idle_for):
            return None

        # A backstop for the rest: a click that moves no pixel looks the same
        # as a key, so the hook can still be replaced without cause. Waking
        # from sleep is the case this was written for, so it never waits out
        # the backoff.
        gap = self._min_reinstall_gap if resumed else self._refresh_gap()
        if time.monotonic() - self._last_reinstall < gap:
            return None

        return ("saw nothing for %.0fs while Windows saw input %.0fs ago"
                % (quiet_for, idle_for))

    def set_paused(self, paused):
        """Suspends recognition without removing the hook."""
        with self._lock:
            self._paused = paused
            if paused:
                self._reset_locked()
        logger.info("Hotkey listener %s", "paused" if paused else "resumed")

    @property
    def paused(self):
        return self._paused

    def notify_recording_finished(self):
        """Clears engaged state after the controller ends a recording."""
        with self._lock:
            self._engaged = False
            self._latched = False
            self._chord_dirty = False
            self._chord_taps = []

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
        self._keys_seen += 1
        if self._keys_seen == 1 and self._installed_at is not None:
            # Proof, in the log, that a freshly started app hears the
            # keyboard. "I restarted it and Ctrl+Alt did nothing" could not
            # be told apart from "I restarted it and did not press anything".
            logger.info("Keyboard hook heard its first key %.1fs after "
                        "starting", self._last_event - self._installed_at)
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
            # Holding a key makes Windows repeat KEY_DOWN. A repeat is not a
            # tap, and counting it as one would latch on a single long Alt.
            repeat = name in self._pressed
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

            # Ctrl+Alt+Win is the correction chord, in whichever order the
            # three arrive. It is checked before the cancel rule below, and
            # never during a hands-free recording or deep into a held one:
            # there the key means "stop", as any other key does. Marking the
            # chord dirty stops the release from counting as a tap, which
            # would otherwise go hands-free the moment somebody corrected two
            # words in a row.
            holding_key = any(k in self._correct_keys for k in self._pressed)
            if not holding_key:
                self._correction_fired = False
            if (
                self._on_correct is not None
                and holding_key
                and has_ctrl
                and has_alt
                and event.event_type == keyboard.KEY_DOWN
                and not repeat
                and not self._correction_fired
                and not self._latched
                and (not self._engaged or time.monotonic()
                     - self._press_started < CHORD_SLOP)
            ):
                self._correction_fired = True
                dropped = self._engaged
                self._spend_chord_locked()
                logger.info("Correction asked for%s",
                            " (dropping the recording it had just started)"
                            if dropped else "")
                if dropped:
                    self._fire(self._on_cancel)
                self._fire(self._on_correct)
                return

            # A non-modifier pressed while we are engaged means the user is
            # really using a shortcut, not dictating.
            if (
                self._engaged
                and self._cancel_on_other_key
                and kind == "other"
                and event.event_type == keyboard.KEY_DOWN
            ):
                logger.info("Cancelled by '%s'", name)
                self._spend_chord_locked()
                self._fire(self._on_cancel)
                return

            if has_other and self._combo_active:
                # Ctrl+Alt+something is a shortcut being typed. Whatever
                # happens to the chord after this, it was not aimed at us.
                self._chord_dirty = True

            combo = has_ctrl and has_alt and not has_other
            if (has_ctrl and has_alt and has_other and not self._combo_active
                    and kind in ("ctrl", "alt") and not repeat
                    and event.event_type == keyboard.KEY_DOWN):
                self._say_blocked()
            if combo and not self._combo_active:
                self._combo_active = True
                self._chord_dirty = repeat and kind == "other"
                self._press_started = time.monotonic()
                self._start_timer()
            elif not combo and self._combo_active:
                self._combo_active = False
                self._cancel_timer()
                held = time.monotonic() - self._press_started
                dirty = self._chord_dirty
                self._chord_dirty = False
                if self._engaged:
                    self._engaged = False
                    if held < self._tap_max:
                        self._fire(self._on_tap)
                    else:
                        self._fire(self._on_hold_release)
                elif not dirty and held < self._engage_delay:
                    self._chord_tapped()

    def _say_blocked(self):
        """Ctrl and Alt are down, but so is something else, so this is a
        shortcut and not dictation. Worth a line when it happens, at most
        every ten seconds: a key the hook thinks is held when it is not would
        look exactly like this, and would stop Ctrl+Alt working until that
        key is pressed again. Named only when it is not a letter - the log
        never holds what anybody typed."""
        now = time.monotonic()
        if now - self._blocked_said_at < 10.0:
            return
        self._blocked_said_at = now
        others = sorted(set(
            key if len(key) > 1 else "a character key"
            for key in self._pressed if self._classify(key) == "other"))
        logger.info("Ctrl+Alt with %s already held; taken as a shortcut",
                    ", ".join(others) or "another key")

    def _chord_tapped(self):
        """A press of Ctrl+Alt too short to have started anything.

        On its own that is nothing - which is the point, since it is also what
        the start of every Ctrl+Alt+<key> shortcut looks like. Two in a row is
        a decision, and that is what hands-free is bound to.
        """
        if self._double_gap <= 0:
            return
        if self._latched:
            # Already recording hands-free: one tap is how you end it.
            self._chord_taps = []
            logger.info("Tap while latched: ending the recording")
            self._fire(self._on_engage)
            return
        if self._on_latch is None:
            return
        now = time.monotonic()
        self._chord_taps = [when for when in self._chord_taps
                            if now - when <= self._double_gap]
        self._chord_taps.append(now)
        if len(self._chord_taps) >= 2:
            self._chord_taps = []
            logger.info("Double tap: recording hands-free")
            self._fire(self._on_latch)

    def set_recording_latched(self, latched):
        """Told by the controller, so a single tap can mean "stop"."""
        with self._lock:
            self._latched = bool(latched)
            self._chord_taps = []

    def _reset_locked(self):
        self._cancel_timer()
        self._combo_active = False
        self._engaged = False
        self._chord_dirty = False
        self._chord_taps = []

    def _spend_chord_locked(self):
        """This press of Ctrl+Alt has been used; nothing more comes of it.

        The chord stays marked as active, so that letting go of the other key
        while Ctrl and Alt are still down is not mistaken for a fresh press.
        Clearing it instead is what the owner's log caught on 22 September: a
        recording cancelled by the Win key at 22:52:47, and a new one started
        0.37 seconds later by the same unbroken Ctrl+Alt - twice.
        """
        self._cancel_timer()
        self._engaged = False
        self._combo_active = True
        self._chord_dirty = True
        self._chord_taps = []

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


# The modifiers a keystroke we send must not land on top of, by the virtual
# key codes Windows itself uses for them.
_MODIFIER_KEYS = (("ctrl", (0x11,)), ("alt", (0x12,)), ("shift", (0x10,)),
                  ("windows", (0x5B, 0x5C)))


def _key_down(vk):
    """Whether Windows says this key is down at this moment."""
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


def held_modifiers():
    """The modifiers Windows says are held, by name."""
    return [name for name, codes in _MODIFIER_KEYS
            if any(_key_down(code) for code in codes)]


def wait_for_modifiers_released(timeout=5.0):
    """Blocks until Ctrl/Alt/Shift/Win are all up, or the timeout expires.

    It asks Windows, not the keyboard library. The library keeps its own list
    of held keys, built from the events its hook has seen, and a release that
    never reached the hook - after Ctrl+Alt+Del or Win+L, or an injected event
    the library decided to drop - leaves that key held in its list for good.
    Seen on the owner's machine with a simulated chord: every key released,
    and the library still had a modifier down five seconds later.
    """
    deadline = time.monotonic() + timeout
    while True:
        held = held_modifiers()
        if not held:
            return True
        if time.monotonic() >= deadline:
            logger.warning("Modifiers still held after %.1fs: %s", timeout,
                           ", ".join(held))
            return False
        time.sleep(0.02)
