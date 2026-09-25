"""System tray icon.

The app has no console and no window of its own, so this is the only place
you can see that it is running, pause it, or quit it.

A click on the icon - either button - opens the tray panel (`panel.py`),
drawn in the pill's own glass. The Windows menu built below stays attached
underneath as the fallback: if the panel cannot open, the click goes on to it.
The icon is the pill's waveform: white bars at rest, the waveform's colours
while it records, grey dots while it is paused.
"""

import logging
import os
import subprocess
import threading

import pystray
from PIL import Image, ImageDraw

from . import dictionary, theme
from . import languages as language_names

logger = logging.getLogger("heyspeaky.tray")

_IDLE = (233, 236, 241)
_PAUSED = (120, 124, 132)
# Bar heights, as a share of the tallest: the pill's waveform in miniature.
_BARS = (0.36, 0.68, 1.0, 0.68, 0.36)


def _bar_colour(index):
    """The waveform's gradient, across the five bars."""
    stops = theme.SIRI
    place = index / float(len(_BARS) - 1) * (len(stops) - 1)
    low = min(int(place), len(stops) - 2)
    mix = place - low
    return tuple(int(round(a + (b - a) * mix))
                 for a, b in zip(stops[low], stops[low + 1]))


def _make_icon(state):
    """The pill's waveform at tray resolution.

    Drawn four times over and scaled down, like everything else here,
    because a 16-pixel icon with hard edges is where cheap shows first.
    """
    size, k = 64, 4
    big = size * k
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    width, gap, tallest = 8 * k, 5 * k, 50 * k
    left = (big - (width * len(_BARS) + gap * (len(_BARS) - 1))) // 2
    for index, share in enumerate(_BARS):
        if state == "paused":
            # Silence is drawn as dots, here as on the pill.
            height, colour = width, _PAUSED
        else:
            height = int(tallest * share)
            colour = _bar_colour(index) if state == "busy" else _IDLE
        x = left + index * (width + gap)
        top = (big - height) // 2
        draw.rounded_rectangle((x, top, x + width, top + height),
                               radius=width // 2, fill=colour + (255,))
    return image.resize((size, size), Image.LANCZOS)


class Tray:
    """Wraps a pystray icon and runs its message loop on its own thread."""

    def __init__(
        self,
        config_path,
        log_dir,
        on_toggle,
        on_pause,
        on_quit,
        on_language=None,
        language="",
        languages=None,
        on_toggle_language=None,
        on_backend=None,
        backend="local",
        on_report=None,
        usage_text=None,
        on_update=None,
        on_panel=None,
        on_key_page=None,
        key_state=None,
        local_models=None,
        on_local_model=None,
        look=None,
        on_look=None,
    ):
        self._config_path = config_path
        self._log_dir = log_dir
        self._on_toggle = on_toggle
        self._on_pause = on_pause
        self._on_quit = on_quit
        self._on_language = on_language
        self._language = language or ""
        # The app's own list, not a copy. Adding or removing a language edits
        # it in place, so the checkmarks below always show the current state.
        self._languages = languages if languages is not None else ["en"]
        self._on_toggle_language = on_toggle_language
        self._on_backend = on_backend
        self._backend = backend or "local"
        self._on_report = on_report
        # A callable, so the figure is current every time the menu opens.
        self._usage_text = usage_text
        self._on_update = on_update
        self._on_panel = on_panel
        self._on_key_page = on_key_page
        self._key_state = key_state
        self._local_models = local_models
        self._on_local_model = on_local_model
        self._look = look
        self._on_look = on_look
        self._update_version = ""
        self._busy = False

        self._status = "Starting…"
        self._paused = False
        self._icons = {
            "idle": _make_icon("idle"),
            "busy": _make_icon("busy"),
            "paused": _make_icon("paused"),
        }
        self._icon = pystray.Icon(
            "HeySpeaky",
            self._icons["idle"],
            "HeySpeaky",
            menu=self._build_menu(),
        )
        self._thread = None
        self._wire_panel()

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(lambda _: self._status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start / stop dictation", self._toggle),
            pystray.MenuItem(
                "Pause Ctrl+Alt",
                self._toggle_pause,
                checked=lambda _: self._paused,
            ),
            pystray.MenuItem("Language", self._language_menu()),
            pystray.MenuItem("Transcribed by", self._backend_menu()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _: "Update to {}".format(self._update_version),
                self._update,
                visible=lambda _: bool(self._update_version),
            ),
            pystray.MenuItem("Edit settings", self._open_config),
            pystray.MenuItem("Edit your words", self._open_dictionary),
            pystray.MenuItem(
                lambda _: self._usage_text() if self._usage_text else "",
                None,
                enabled=False,
                visible=lambda _: bool(self._usage_text),
            ),
            pystray.MenuItem("Open logs", self._open_logs),
            pystray.MenuItem("Save a problem report", self._report),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit HeySpeaky", self._quit),
        )

    def _language_menu(self):
        """Pins one of your languages, or adds and removes them.

        Every language on offer gets its entries up front, and the ones you do
        not speak are hidden. pystray rebuilds the native menu on every update
        and drops hidden items, so adding a language makes it appear here
        without rebuilding anything by hand.

        Adding is split into submenus by first letter, because a hundred
        languages in one Windows menu would run off the screen.
        """
        offered = language_names.catalog(self._languages)
        pin = [
            pystray.MenuItem(
                "Auto-detect",
                self._make_language_setter(""),
                checked=self._make_language_check(""),
                radio=True,
            )
        ]
        for code in offered:
            pin.append(pystray.MenuItem(
                language_names.name(code),
                self._make_language_setter(code),
                checked=self._make_language_check(code),
                radio=True,
                visible=self._make_spoken_check(code),
            ))
        # Yours first, so removing one never means hunting through letters.
        yours = [
            pystray.MenuItem(
                language_names.name(code),
                self._make_language_toggle(code),
                checked=self._make_spoken_check(code),
                visible=self._make_spoken_check(code),
            )
            for code in offered
        ]
        by_letter = [
            pystray.MenuItem(label, pystray.Menu(*[
                pystray.MenuItem(
                    language_names.name(code),
                    self._make_language_toggle(code),
                    checked=self._make_spoken_check(code),
                )
                for code in codes
            ]))
            for label, codes in language_names.groups(offered)
        ]
        return pystray.Menu(
            *pin,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Add or remove languages",
                pystray.Menu(*yours, pystray.Menu.SEPARATOR, *by_letter),
            ),
        )

    def _make_language_setter(self, code):
        def setter(_icon=None, _item=None):
            self._language = code
            if self._on_language:
                self._on_language(code)
        return setter

    def _make_language_check(self, code):
        return lambda _item: self._language == code

    def _make_spoken_check(self, code):
        return lambda _item: code in self._languages

    def _make_language_toggle(self, code):
        def toggle(_icon=None, _item=None):
            if self._on_toggle_language:
                self._on_toggle_language(code)
        return toggle

    def _backend_menu(self):
        """Chooses between local CPU transcription and the OpenAI API."""
        options = (
            ("This laptop (offline)", "local"),
            ("OpenAI (needs API key)", "cloud"),
        )
        return pystray.Menu(*[
            pystray.MenuItem(
                label,
                self._make_backend_setter(value),
                checked=self._make_backend_check(value),
                radio=True,
            )
            for label, value in options
        ])

    def _make_backend_setter(self, value):
        def setter(_icon=None, _item=None):
            self._backend = value
            if self._on_backend:
                self._on_backend(value)
        return setter

    def _make_backend_check(self, value):
        return lambda _item: self._backend == value

    # -- menu handlers -----------------------------------------------------

    def _toggle(self, _icon=None, _item=None):
        threading.Thread(target=self._on_toggle, daemon=True).start()

    def _toggle_pause(self, _icon=None, _item=None):
        self._paused = not self._paused
        self._on_pause(self._paused)
        self.set_status("Paused" if self._paused else "Ready")

    def _open_config(self, _icon=None, _item=None):
        self._open(str(self._config_path))

    def _open_dictionary(self, _icon=None, _item=None):
        """Opens the words this person has had to correct.

        The file is created empty on the way, with a line saying what it is
        for, because an explorer window that opens on nothing looks broken and
        is the fastest way to make somebody stop using a feature.
        """
        path = os.path.expandvars(dictionary.PATH)
        if not os.path.exists(path):
            dictionary.save([])
        self._open(path)

    def _open_logs(self, _icon=None, _item=None):
        self._open(str(self._log_dir))

    def _update(self, _icon=None, _item=None):
        if self._on_update:
            self._on_update()

    def offer_update(self, version):
        """Shows the update item once a newer version has been seen."""
        self._update_version = version or ""
        self.refresh()

    def _report(self, _icon=None, _item=None):
        if self._on_report:
            self._on_report()

    @staticmethod
    def _open(target):
        try:
            os.startfile(target)  # noqa: S606 - opening the user's own files
        except OSError:
            subprocess.Popen(["explorer", target])

    def _quit(self, _icon=None, _item=None):
        self._icon.visible = False
        self._icon.stop()
        self._on_quit()

    # -- public API --------------------------------------------------------

    def start(self):
        self._thread = threading.Thread(
            target=self._icon.run, name="tray", daemon=True
        )
        self._thread.start()

    def stop(self):
        try:
            self._icon.stop()
        except Exception:
            logger.debug("Tray stop raised", exc_info=True)

    def set_language(self, code):
        """Moves the pin mark, for when the app changes it rather than you."""
        self._language = code or ""
        self.refresh()

    def refresh(self):
        """Redraws the menu so checkmarks and the pin list are current."""
        try:
            self._icon.update_menu()
        except Exception:
            logger.debug("Tray menu refresh raised", exc_info=True)

    def set_status(self, status, busy=False):
        """Updates the tooltip, menu header and icon colour."""
        self._status = status
        self._busy = bool(busy)
        try:
            self._icon.title = "HeySpeaky · {}".format(status)
            if self._paused:
                self._icon.icon = self._icons["paused"]
            else:
                self._icon.icon = self._icons["busy" if busy else "idle"]
            self._icon.update_menu()
        except Exception:
            logger.debug("Tray update raised", exc_info=True)

    def notify(self, title, message):
        """A Windows notification from the tray icon."""
        try:
            self._icon.notify(message, title)
        except Exception:
            logger.debug("Could not show a notification", exc_info=True)

    # -- the panel ---------------------------------------------------------

    def _wire_panel(self):
        """Sends a click on the icon to the panel instead of the menu.

        pystray keeps a table of window-message handlers; the one for the
        icon's notifications is swapped for one that opens the panel, and
        hands the click on to the original - the Windows menu - if that
        fails. pystray is pinned in requirements.lock, so the table is where
        this expects it.
        """
        if self._on_panel is None:
            return
        handlers = getattr(self._icon, "_message_handlers", None)
        try:
            from pystray._util import win32
        except Exception:
            logger.warning("pystray has changed; the tray keeps its menu")
            return
        if not isinstance(handlers, dict) or win32.WM_NOTIFY not in handlers:
            logger.warning("pystray has changed; the tray keeps its menu")
            return
        original = handlers[win32.WM_NOTIFY]
        clicks = (win32.WM_LBUTTONUP, win32.WM_RBUTTONUP)

        def on_notify(wparam, lparam):
            if lparam in clicks:
                try:
                    # As pystray does before its own menu: the icon's window
                    # to the front, which is what lets the panel take focus.
                    hwnd = getattr(self._icon, "_hwnd", None)
                    if hwnd:
                        win32.SetForegroundWindow(hwnd)
                    self._on_panel()
                    return 0
                except Exception:
                    logger.exception("The tray panel did not open; "
                                     "showing the menu instead")
            return original(wparam, lparam)

        handlers[win32.WM_NOTIFY] = on_notify

    def panel_model(self):
        """What the panel shows, read fresh each time it asks."""
        offered = language_names.catalog(self._languages)
        return {
            "status": self._status,
            "state": ("paused" if self._paused else
                      "busy" if self._busy else "ready"),
            "paused": self._paused,
            "pinned": self._language,
            "yours": list(self._languages),
            "backend": self._backend,
            "usage": self._usage_text() if self._usage_text else "",
            "update": self._update_version,
            "key": self._key_state() if self._key_state else "saved",
            "local": self._local_models() if self._local_models else {},
            "look": self._look() if self._look else "glass",
            "catalog": list(offered),
            "names": dict((code, language_names.name(code))
                          for code in offered),
        }

    def panel_act(self, action):
        """Does what the panel was clicked for. Off the Tk thread, because
        some of these save files or build a report."""
        handlers = {
            "dictate": self._toggle,
            "pause": self._toggle_pause,
            "update": self._update,
            "words": self._open_dictionary,
            "settings": self._open_config,
            "logs": self._open_logs,
            "report": self._report,
            "quit": self._quit,
        }
        if self._on_key_page is not None:
            handlers["key-page"] = self._on_key_page
        if action in handlers:
            target = handlers[action]
        elif action.startswith("pin:"):
            target = self._make_language_setter(action[len("pin:"):])
        elif action.startswith("lang:"):
            target = self._make_language_toggle(action[len("lang:"):])
        elif action.startswith("backend:"):
            target = self._make_backend_setter(action[len("backend:"):])
        elif action.startswith("look:") and self._on_look:
            style = action[len("look:"):]

            def target():
                self._on_look(style)
        elif action.startswith("model:") and self._on_local_model:
            name = action[len("model:"):]

            def target():
                self._on_local_model(name)
        else:
            logger.warning("The tray panel asked for %r", action)
            return
        threading.Thread(target=target, name="tray-panel",
                         daemon=True).start()
