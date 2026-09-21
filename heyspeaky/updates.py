"""Is there a newer HeySpeaky, and updating to it from the tray.

People install by pasting one command, which means they never learn that a
fix exists. This asks GitHub once a day, remembers the answer next to the key
in %APPDATA%, and lets the tray offer the update.

Updating runs the install.ps1 that is already in the folder, with -File rather
than a download on the command line: Windows Defender reports that shape as
Trojan:Win32/Commando.A!ml and refuses to start it. That script stops the app,
pulls the current version and starts it again.
"""

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from . import __version__

logger = logging.getLogger("heyspeaky.updates")

LATEST_URL = "https://api.github.com/repos/Maslitsa/HeySpeaky/releases/latest"
STATE = "%APPDATA%\\HeySpeaky\\update.json"
EVERY = 24 * 60 * 60
TIMEOUT = 6.0


def _numbers(version):
    """1.2.3 as (1, 2, 3), so 1.10 counts as newer than 1.9."""
    parts = []
    for piece in str(version).lstrip("vV").split("."):
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(offered, running=__version__):
    return _numbers(offered) > _numbers(running)


def _state_path():
    return Path(os.path.expandvars(STATE))


def _read():
    try:
        with open(_state_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data):
    try:
        target = _state_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
    except OSError as exc:
        logger.debug("Could not remember the update check: %s", exc)


def known_newer():
    """The version last seen on GitHub, if it is newer than this one."""
    offered = (_read().get("latest") or "").strip()
    return offered if offered and is_newer(offered) else ""


def check(force=False, now=None):
    """Asks GitHub, at most once a day. Returns a newer version or ''."""
    now = time.time() if now is None else now
    data = _read()
    if not force and now - float(data.get("checked", 0.0)) < EVERY:
        return known_newer()
    try:
        import httpx

        response = httpx.get(LATEST_URL, timeout=TIMEOUT,
                             headers={"Accept": "application/vnd.github+json"})
        if response.status_code != 200:
            logger.debug("GitHub answered %s", response.status_code)
            data["checked"] = now
            _write(data)
            return known_newer()
        offered = (response.json().get("tag_name") or "").strip()
    except Exception as exc:
        logger.debug("Could not ask GitHub about updates: %s", exc)
        data["checked"] = now
        _write(data)
        return known_newer()

    data["checked"] = now
    data["latest"] = offered
    _write(data)
    if offered and is_newer(offered):
        logger.info("HeySpeaky %s is available; running %s", offered,
                    __version__)
        return offered
    return ""


def check_in_background(when_found):
    """Checks without holding anything up, and calls back if there is news."""
    def run():
        found = check()
        if found:
            try:
                when_found(found)
            except Exception:
                logger.debug("Update callback failed", exc_info=True)

    threading.Thread(target=run, name="update-check", daemon=True).start()


def install(root):
    """Runs the installer that is already in the folder. It restarts the app."""
    script = Path(root) / "install.ps1"
    if not script.is_file():
        raise RuntimeError("install.ps1 is not in {}".format(root))
    subprocess.Popen([
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(script),
    ], cwd=str(root))
    logger.info("Update started from %s", script)
