"""System tray icon.

The app has no console and no window of its own, so this is the only place
you can see that it is running, pause it, or quit it.
"""

import logging
import os
import subprocess
import threading

import pystray
from PIL import Image, ImageDraw

from . import dictionary
from . import languages as language_names

logger = logging.getLogger("heyspeaky.tray")

_IDLE = (233, 236, 241)
_BUSY = (255, 77, 79)
_PAUSED = (120, 124, 132)


def _make_icon(color):
    """Draws a simple microphone glyph at tray resolution."""
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # Capsule body.
    draw.rounded_rectangle((24, 10, 40, 38), radius=8, fill=color)
    # Cradle.
    draw.arc((18, 22, 46, 46), start=0, end=180, fill=color, width=5)
    # Stem and base.
    draw.rectangle((30, 45, 34, 52), fill=color)
    draw.rectangle((22, 52, 42, 56), fill=color)
    return image


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
        self._update_version = ""

        self._status = "Starting…"
        self._paused = False
        self._icons = {
            "idle": _make_icon(_IDLE),
            "busy": _make_icon(_BUSY),
            "paused": _make_icon(_PAUSED),
        }
        self._icon = pystray.Icon(
            "HeySpeaky",
            self._icons["idle"],
            "HeySpeaky",
            menu=self._build_menu(),
        )
        self._thread = None

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
        try:
            self._icon.title = "HeySpeaky · {}".format(status)
            if self._paused:
                self._icon.icon = self._icons["paused"]
            else:
                self._icon.icon = self._icons["busy" if busy else "idle"]
            self._icon.update_menu()
        except Exception:
            logger.debug("Tray update raised", exc_info=True)
