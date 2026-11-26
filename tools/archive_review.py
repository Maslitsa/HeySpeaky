"""Reads the dictation archive back: a day of dictation, the good next to
the bad, with what each step made of it and how long it took.

The archive is the owner's, on his own PC (heyspeaky/archive.py), and holds
what he said. This prints it, so it is run when he asks for his dictation
to be looked at, never by the session brief or anything that runs by
itself. Standard library only: any Python will do.

    python tools/archive_review.py                 today
    python tools/archive_review.py --days 3        the last three days
    python tools/archive_review.py --day 2026-11-26
    python tools/archive_review.py --flagged       only the ones to look at
    python tools/archive_review.py --wavs          their recordings' paths

A dictation is flagged when it went to the local model, when the cloud was
unsure (-0.3, as transcribe.UNSURE_BELOW), when a word mixes Latin and
Cyrillic letters, when the next dictation came within 20 seconds in the
same program (a second try), or when a correction followed it.
"""

import argparse
import datetime
import json
import os
import re
import statistics
import sys
from pathlib import Path

DEFAULT_FOLDER = os.path.expandvars("%LOCALAPPDATA%\\HeySpeaky\\archive")
UNSURE_BELOW = -0.3
SECOND_TRY = 20.0

_LATIN = re.compile(r"[A-Za-z]")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def mixed_words(text):
    """Words with Latin and Cyrillic letters in them at once, which no
    language writes: "спрeтии" with a Latin e."""
    return [word for word in re.findall(r"\w+", text or "")
            if _LATIN.search(word) and _CYRILLIC.search(word)]


def read_day(folder):
    lines = []
    path = folder / "dictations.jsonl"
    if not path.is_file():
        return lines
    with open(str(path), encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                print("  (line {} of {} could not be read)".format(
                    number, path), file=sys.stderr)
                continue
            entry["_day"] = folder.name
            entry["_folder"] = folder
            lines.append(entry)
    return lines


def flags(entry, following):
    found = []
    if entry.get("backend") != "cloud":
        found.append("local ({})".format(entry.get("fallback") or "chosen"))
    cloud = (entry.get("steps") or {}).get("cloud") or {}
    average = cloud.get("average")
    if average is not None and average < UNSURE_BELOW:
        found.append("unsure {:.2f}".format(average))
    mixed = mixed_words(entry.get("text"))
    if mixed:
        found.append("mixed alphabets: " + ", ".join(mixed))
    if following is not None:
        if following.get("kind") == "correction":
            found.append("corrected next")
        elif (following.get("since_last") is not None
              and following["since_last"] < SECOND_TRY
              and following.get("program") == entry.get("program")):
            found.append("tried again {:.0f}s later".format(
                following["since_last"]))
    return found


def describe(entry, found):
    steps = entry.get("steps") or {}
    cloud = steps.get("cloud") or {}
    parts = ["{} {}".format(entry.get("_day", ""), entry.get("time", "")),
             entry.get("program") or "?",
             "{:.1f}s audio".format(entry.get("seconds") or 0),
             "{:.0f} dB".format(entry.get("rms_db") or 0)]
    if cloud:
        parts.append("cloud {} {:.2f} in {:.1f}s".format(
            ",".join(cloud.get("languages") or []) or "?",
            cloud.get("average") if cloud.get("average") is not None else 0,
            cloud.get("seconds") or 0))
    if "asked_again" in steps:
        again = steps["asked_again"]
        parts.append("asked again {:.1f}s, kept {}".format(
            again.get("seconds") or 0, again.get("kept") or "the first"))
    if "alphabet" in steps:
        parts.append("alphabet {:.1f}s".format(
            steps["alphabet"].get("seconds") or 0))
    if "local" in steps:
        parts.append("local {:.1f}s".format(steps["local"].get("seconds")
                                            or 0))
    parts.append("waited {:.1f}s".format(entry.get("took") or 0))
    lines = ["  ".join(parts)]
    if found:
        lines.append("    !! " + "; ".join(found))
    if cloud and cloud.get("text") != entry.get("text"):
        lines.append("    cloud:    " + (cloud.get("text") or ""))
    for answer in (steps.get("asked_again") or {}).get("answers") or []:
        lines.append("    {} first: {}".format(answer.get("first"),
                                               answer.get("text") or "-"))
    if "alphabet" in steps and steps["alphabet"].get("text") \
            != entry.get("text"):
        lines.append("    alphabet: " + (steps["alphabet"].get("text") or ""))
    lines.append("    typed:    " + (entry.get("text") or "(nothing)"))
    return "\n".join(lines)


def quantiles(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return "-"
    return "median {:.1f}s, 90% {:.1f}s, slowest {:.1f}s".format(
        statistics.median(values), values[int(0.9 * (len(values) - 1))],
        values[-1])


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Reads the dictation archive back.")
    parser.add_argument("--folder", default=DEFAULT_FOLDER)
    parser.add_argument("--day", help="one day, as 2026-11-26")
    parser.add_argument("--days", type=int, default=1,
                        help="this many days back from today")
    parser.add_argument("--flagged", action="store_true",
                        help="only the dictations worth a look")
    parser.add_argument("--wavs", action="store_true",
                        help="print the flagged recordings' paths only")
    args = parser.parse_args(argv)

    root = Path(args.folder)
    if args.day:
        days = [args.day]
    else:
        today = datetime.date.today()
        days = [(today - datetime.timedelta(days=back)).isoformat()
                for back in range(args.days - 1, -1, -1)]
    entries = []
    for day in days:
        entries.extend(read_day(root / day))
    if not entries:
        print("Nothing archived for {} in {}".format(", ".join(days), root))
        return 0

    dictations = [e for e in entries if e.get("kind") == "dictation"]
    corrections = [e for e in entries if e.get("kind") == "correction"]
    flagged = 0
    for index, entry in enumerate(entries):
        if entry.get("kind") == "correction":
            if not args.wavs:
                print("{} {}  CORRECTION  {!r} -> {!r}".format(
                    entry.get("_day"), entry.get("time"),
                    entry.get("heard"), entry.get("meant")))
            continue
        following = entries[index + 1] if index + 1 < len(entries) else None
        found = flags(entry, following)
        flagged += bool(found)
        if args.wavs:
            if found and entry.get("wav"):
                print(entry["_folder"] / entry["wav"])
            continue
        if args.flagged and not found:
            continue
        print(describe(entry, found))
    if args.wavs:
        return 0

    cloud = [e for e in dictations if e.get("backend") == "cloud"]
    steps = [e.get("steps") or {} for e in cloud]
    print()
    print("{} dictations, {} by the cloud, {} by the local model; {} "
          "flagged, {} corrections".format(
              len(dictations), len(cloud), len(dictations) - len(cloud),
              flagged, len(corrections)))
    print("waited after letting go:  " + quantiles(
        [e.get("took") for e in cloud]))
    print("  speech model:           " + quantiles(
        [(s.get("cloud") or {}).get("seconds") for s in steps]))
    checked = [s["alphabet"] for s in steps if "alphabet" in s]
    print("  alphabet check:         " + quantiles(
        [a.get("seconds") for a in checked])
        + " (ran on {}, changed {})".format(
            len(checked),
            sum(1 for s in steps if "alphabet" in s
                and s["alphabet"].get("text")
                != (s.get("cloud") or {}).get("text"))))
    again = [s["asked_again"] for s in steps if "asked_again" in s]
    if again:
        print("  asked again:            " + quantiles(
            [a.get("seconds") for a in again])
            + " ({} times)".format(len(again)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
