"""Adding the OpenAI key from the tray, with as little to do as possible.

The owner asked for this to be low effort for anyone, and before it the only
way to add or change a key was to run the installer again with the key in a
PowerShell command. Now: click the HeySpeaky icon, click "Add your OpenAI
key", paste it into the field that opens, and press Save - the steps the
owner described himself. The key is checked with OpenAI before it replaces
anything, saved where the installer saves it, and taken off the clipboard
if that is where it came from. A row under the field opens the page where
keys are made.

The key is never logged, never shown whole, and never put in config.json."""

import logging
import os
import re
import subprocess
import tempfile
import threading
import time
import webbrowser

logger = logging.getLogger("heyspeaky.apikey")

KEYS_PAGE = "https://platform.openai.com/api-keys"
MODELS_URL = "https://api.openai.com/v1/models"

# sk-, sk-proj-, sk-svcacct- and the rest: letters, digits, - and _.
_KEY = re.compile(r"^sk-[A-Za-z0-9_\-]{20,}$")

# How long a state that is only news lasts before the row goes back to
# saying whether there is a key.
_LASTS = {"invalid": 30.0, "refused": 60.0, "offline": 20.0,
          "checking": 60.0, "done": 4.0}

CREATE_NO_WINDOW = 0x08000000


def looks_like_key(text):
    return bool(_KEY.match((text or "").strip()))


def key_path(config):
    path = config["transcription"]["cloud"].get("api_key_file") \
        or "%APPDATA%\\HeySpeaky\\openai.key"
    return os.path.expandvars(os.path.expanduser(path))


def save(config, key):
    """Writes the key where the app reads it, as the installer does: UTF-8
    without a BOM, replaced in one step, readable by this account only."""
    path = key_path(config)
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".openai-", suffix=".tmp",
                                         dir=folder)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(key.strip())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    user = os.environ.get("USERNAME", "")
    if user:
        try:
            subprocess.call(
                ["icacls", path, "/inheritance:r", "/grant:r",
                 "{}:(R,W)".format(user)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW, timeout=10)
        except Exception:
            logger.warning("Could not narrow who may read the key file")
    return path


def check(key, timeout=10.0):
    """"ok" if OpenAI takes the key, "refused" if it says no, "offline" if
    it could not be asked. Listing models is free and needs only a key."""
    import httpx
    try:
        response = httpx.get(MODELS_URL, timeout=timeout,
                             headers={"Authorization": "Bearer " + key})
    except Exception:
        return "offline"
    if response.status_code in (401, 403):
        return "refused"
    if response.status_code == 200:
        return "ok"
    return "offline"


class KeyFlow(object):
    """What the OpenAI key page in the tray panel does, and what it says.

    `has_key` answers whether the app has a key now; `read_clipboard` and
    `clear_clipboard` are the clipboard, used only to take the key off it
    once it is saved; `on_saved` is told after a key is saved. All of them
    are passed in, so the flow can be tried without a real clipboard, a
    browser or OpenAI.
    """

    def __init__(self, config, has_key, read_clipboard, clear_clipboard,
                 on_saved=None, open_page=webbrowser.open, checker=check,
                 saver=save):
        self._config = config
        self._has_key = has_key
        self._read = read_clipboard
        self._clear = clear_clipboard
        self._on_saved = on_saved
        self._open_page = open_page
        self._check = checker
        self._save = saver
        self._lock = threading.Lock()
        self._news = None
        self._since = 0.0

    def state(self):
        """missing, invalid, checking, refused, offline, done or saved."""
        with self._lock:
            news, since = self._news, self._since
        if news is not None and time.monotonic() - since < _LASTS[news]:
            return news
        try:
            return "saved" if self._has_key() else "missing"
        except Exception:
            return "missing"

    def _say(self, news):
        with self._lock:
            self._news = news
            self._since = time.monotonic()

    def open_page(self):
        """Where keys are made, in the browser."""
        try:
            self._open_page(KEYS_PAGE)
        except Exception:
            logger.exception("Could not open the keys page")

    def submit(self, text):
        """The Save button: `text` is whatever was pasted into the field.
        Returns at once; the check with OpenAI runs on its own thread."""
        key = (text or "").strip()
        if self.state() == "checking":
            return "checking"
        if not looks_like_key(key):
            self._say("invalid")
            return "invalid"
        self._say("checking")
        threading.Thread(target=self._check_and_save, args=(key,),
                         name="apikey", daemon=True).start()
        return "checking"

    def _check_and_save(self, key):
        verdict = self._check(key)
        if verdict == "refused":
            logger.info("OpenAI refused the pasted key; the old one, if any, "
                        "is kept")
            self._say("refused")
            return
        try:
            self._save(self._config, key)
        except Exception:
            logger.exception("Could not save the key")
            self._say("refused")
            return
        logger.info("OpenAI key saved from the tray (%s)",
                    "checked" if verdict == "ok"
                    else "OpenAI could not be reached to check it")
        # Pasted from the clipboard, most likely: do not leave it there to
        # be pasted into a chat by accident. Anything else is left alone.
        try:
            if (self._read() or "").strip() == key:
                self._clear()
        except Exception:
            logger.warning("Could not take the key off the clipboard")
        self._say("offline" if verdict == "offline" else "done")
        if self._on_saved is not None:
            try:
                self._on_saved()
            except Exception:
                logger.exception("After saving the key")
