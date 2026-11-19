"""What the OpenAI key is costing, month by month.

OpenAI does not tell us what a transcription cost, so this counts the seconds
of audio that were sent and multiplies by the price per minute from the
settings. It is an estimate, and it says so wherever it is shown.

The tally lives next to the key in %APPDATA%, not in the project folder, so
reinstalling or moving the app does not lose it and a git add cannot pick it
up. One warning per month is enough: passing the threshold never changes the
engine, because the local model is much weaker and a silent downgrade is worse
than a bigger bill.
"""

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger("heyspeaky.usage")

FOLDER = "%APPDATA%\\HeySpeaky"
FILE = "usage.json"


def path():
    """Where the tally is kept."""
    return Path(os.path.expandvars(FOLDER)) / FILE


def _read():
    try:
        with open(path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data):
    try:
        target = path()
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        return True
    except OSError as exc:
        logger.debug("Could not save the usage tally: %s", exc)
        return False


def this_month(now=None):
    return time.strftime("%Y-%m", time.localtime(now))


def record(seconds, now=None):
    """Adds one dictation. Returns the month's total seconds and count."""
    seconds = max(0.0, float(seconds))
    data = _read()
    month = this_month(now)
    entry = data.get(month) or {}
    entry["seconds"] = float(entry.get("seconds", 0.0)) + seconds
    entry["dictations"] = int(entry.get("dictations", 0)) + 1
    data[month] = entry
    _write(data)
    return entry["seconds"], entry["dictations"]


def summary(cfg, now=None):
    """This month's minutes, dictations and estimated cost."""
    cloud = cfg["transcription"]["cloud"]
    price = float(cloud.get("price_per_minute") or 0.0)
    entry = _read().get(this_month(now)) or {}
    seconds = float(entry.get("seconds", 0.0))
    return {
        "seconds": seconds,
        "minutes": seconds / 60.0,
        "dictations": int(entry.get("dictations", 0)),
        "cost": seconds / 60.0 * price,
        "warned": bool(entry.get("warned")),
    }


def describe(cfg, now=None):
    """One line for the tray, in the same plain words as everything else."""
    figures = summary(cfg, now)
    if not figures["dictations"]:
        return "This month: nothing sent to OpenAI"
    return "This month: {:.0f} min, about ${:.2f}".format(
        figures["minutes"], figures["cost"])


def warning(cfg, now=None):
    """The message to show once when the month passes the threshold.

    Returns None when there is nothing to say. Marks the month as warned, so
    the same month never nags twice.
    """
    cloud = cfg["transcription"]["cloud"]
    limit = float(cloud.get("monthly_warning_usd") or 0.0)
    if limit <= 0:
        return None
    figures = summary(cfg, now)
    if figures["warned"] or figures["cost"] < limit:
        return None
    data = _read()
    month = this_month(now)
    entry = data.get(month) or {}
    entry["warned"] = True
    data[month] = entry
    _write(data)
    logger.info("Monthly OpenAI estimate passed $%.2f", limit)
    return "OpenAI this month: about ${:.2f}".format(figures["cost"])
