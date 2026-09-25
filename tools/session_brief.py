r"""What a session needs to know before it starts, in about twenty lines.

Every session used to begin the same way, by hand: read the tail of the
installed app's log and count what was unusual in it, and compare the
installed copy with this one file by file. Both are mechanical, and both
cost thousands of tokens of raw output to arrive at a handful of facts. This
does both and prints only the facts. `.claude/settings.json` runs it when a
session starts, so the facts are there before the first question.

    python tools/session_brief.py              # the last two days of log
    python tools/session_brief.py --days 7

Standard library only: it runs on whatever Python the hook finds. It never
prints what anybody dictated - the log does not hold that either - only
counts, program names and the warning lines themselves.
"""

import argparse
import collections
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLED = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "HeySpeaky"
TRACKED = ("heyspeaky/*.py", "run.py", "install.ps1", "uninstall.ps1",
           "tools/*.py")

# What gets counted, in the order it is printed.
EVENTS = (
    ("starts", r"HeySpeaky running"),
    ("quits", r"Shutting down"),
    ("second copy refused", r"Another instance is already running"),
    ("dictations", r"Final transcript"),
    ("discarded", r"Discarding recording|Nothing to transcribe"),
    ("recordings cancelled", r"Cancelled by|cancel button clicked"),
    ("correction boxes closed unsaved", r"Correction cancelled"),
    ("corrections asked", r"Correction asked for"),
    ("corrections saved", r"Correction saved"),
    ("hook refreshes", r"refreshing the hook"),
    ("Ctrl+Alt ignored", r"nothing new started|taken as a shortcut"),
    ("keys saved", r"OpenAI key saved"),
    ("model changes", r"Local model is now"),
)

_STAMP = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")
_SELECTION = re.compile(r"Selection: (\d+) chars from (\S+)")


def _git(*args):
    try:
        return subprocess.run(["git"] + list(args), cwd=str(ROOT),
                              capture_output=True, text=True,
                              errors="replace", timeout=15).stdout.strip()
    except Exception:
        return ""


def drift(root=ROOT, installed=INSTALLED, names=None):
    """Files that differ between this copy and the installed one, line
    endings aside - the installed copy keeps CRLF and git keeps LF."""
    if names is None:
        names = _git("ls-files", *TRACKED).split()
    differ, missing = [], []
    for name in names:
        there = installed / name
        if not there.exists():
            missing.append(name)
            continue
        here = (root / name).read_bytes().replace(b"\r\n", b"\n")
        if here != there.read_bytes().replace(b"\r\n", b"\n"):
            differ.append(name)
    return differ, missing


def summarise(lines, since):
    """Counts, the programs selections came from, and the warning lines,
    for every log line stamped at or after `since`."""
    counts = collections.Counter()
    read, empty = collections.Counter(), collections.Counter()
    warnings = []
    first = None
    for line in lines:
        stamp = _STAMP.match(line)
        if not stamp:
            continue
        when = datetime.datetime.strptime(stamp.group(1), "%Y-%m-%d %H:%M:%S")
        if when < since:
            continue
        first = first or stamp.group(1)
        for label, pattern in EVENTS:
            if re.search(pattern, line):
                counts[label] += 1
        selection = _SELECTION.search(line)
        if selection:
            program = selection.group(2).rstrip(",")
            (read if int(selection.group(1)) else empty)[program] += 1
        if " WARNING " in line or " ERROR " in line:
            warnings.append(line.strip()[:170])
    return {"counts": counts, "read": read, "empty": empty,
            "warnings": warnings, "first": first}


def _listed(counter):
    return ", ".join("{} {}".format(name, count)
                     for name, count in counter.most_common(4))


def main():
    parser = argparse.ArgumentParser(description="A session's starting facts")
    parser.add_argument("--days", type=float, default=2.0)
    args = parser.parse_args()
    for stream in (sys.stdout,):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    now = datetime.datetime.now()
    print("HeySpeaky session brief, {:%Y-%m-%d %H:%M}".format(now))
    changed = _git("status", "--short").splitlines()
    print("Repo: {} at {}{}".format(
        _git("branch", "--show-current") or "?",
        _git("log", "-1", "--format=%h %s")[:70] or "?",
        ", {} files changed and not committed".format(len(changed))
        if changed else ", clean"))

    if not INSTALLED.exists():
        print("Installed copy: none at {}".format(INSTALLED))
    else:
        differ, missing = drift()
        if not differ and not missing:
            print("Installed copy: the same as this one, file for file")
        else:
            print("Installed copy differs in {} file(s): {}{}".format(
                len(differ), ", ".join(differ[:8]),
                "; missing there: " + ", ".join(missing[:5])
                if missing else ""))

    log = INSTALLED / "logs" / "heyspeaky.log"
    if not log.exists():
        print("App log: none")
        return 0
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    facts = summarise(lines, now - datetime.timedelta(days=args.days))
    counts = facts["counts"]
    if not facts["first"]:
        print("App log: nothing in the last {:g} days".format(args.days))
        return 0
    print("App log since {}:".format(facts["first"]))
    print("  " + ", ".join("{} {}".format(counts[label], label)
                           for label, _pattern in EVENTS if counts[label]))
    if facts["read"] or facts["empty"]:
        print("  selections read: {}; empty: {}".format(
            _listed(facts["read"]) or "none", _listed(facts["empty"]) or "none"))
    if facts["warnings"]:
        print("  warnings and errors ({}), the last few:".format(
            len(facts["warnings"])))
        for line in facts["warnings"][-5:]:
            print("    " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
