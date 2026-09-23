r"""Words this person says that the model gets wrong.

The owner dictated a friend's name, Magzhan, and got back Marzhan, Makzhan
and Bagzhan in three tries. He asked for the obvious thing: let him mark what
was wrong, type what he meant, and have it stop happening.

**What is not possible.** The model cannot be taught how he sounds. It is
OpenAI's, there is no training here, and no amount of corrections will change
what the acoustic model hears. Promising otherwise would be a lie with a long
tail: he would keep correcting the same word and wonder why it never took.

**What is possible, and measured.** Two things, and together they cover the
case:

1. The words are sent with the audio as `keywords`, which tells the model to
   expect them. Measured on four synthesised clips of the name above: with
   Kazakh declared first and nothing else, it came back right 0 times out of
   4; with the name as a keyword, 2 out of 2 in a Kazakh sentence, plain and
   slurred alike. That is priming, not learning, and it is most of the win.
2. What priming does not reach is replaced afterwards. In the same run, a
   Russian sentence moved from "Marzhan" to "Magzhan" with the keyword set -
   the right consonant, but the Kazakh letter did not survive into Russian
   text. A pair recorded here closes that last step exactly.

So a correction teaches this file, and this file steers every later request.

The file lives in %APPDATA%, next to the key, not in config.json: it is
personal, it grows, and it should survive reinstalling and re-cloning. It is
plain JSON on purpose, so it can be read and edited by hand.

Replacement is deliberately timid. It only ever fires on a pair somebody
typed, on whole words, and never on a word that is itself something they said
they meant - otherwise one careless entry could eat a real word for good.
"""

import json
import logging
import os
import re
import unicodedata

logger = logging.getLogger("heyspeaky.dictionary")

PATH = "%APPDATA%\\HeySpeaky\\dictionary.json"

# Older names of the app, read once if the current file is missing, the same
# way the key is carried across. See LEGACY_KEY_FILES in transcribe.py.
LEGACY_PATHS = (
    "%APPDATA%\\SpeakIt\\dictionary.json",
    "%APPDATA%\\VoiceType\\dictionary.json",
)

# How many words to send with the audio. The steering text has a budget and
# the words compete with the prompt for it, so the whole dictionary cannot go
# every time. Most recently corrected first: what someone is fixing today is
# what they are saying today.
KEYWORD_LIMIT = 48


def _expand(path):
    return os.path.expandvars(os.path.expanduser(path))


# What comes along when a word is selected at the end of a sentence or inside
# quotes. Only ever cut from the ends: inside a word a dot, a hyphen or an
# apostrophe belongs to it. The owner's first entry was "Мағжан." - selected
# with its full stop - and it went to the model as a keyword with the dot on.
_EDGE_MARKS = ".,;:!?…\"'«»„“”‘’()[]{}—–-¡¿ \t\r\n "


def _clean(word):
    """A word as it will be stored: trimmed, with the spaces inside kept.

    "т.е." and "e.g." keep their last dot, because it is the same dot they
    are made of: the stretch before it is a single letter after another dot.
    "Node.js." at the end of a sentence loses it, and so does a plain word.
    """
    word = unicodedata.normalize("NFC", word or "")
    core = word.strip(_EDGE_MARKS)
    if "." in core:
        end = word.index(core) + len(core)
        tail = core.rsplit(".", 1)[1]
        if word[end:end + 1] == "." and len(tail) == 1 and tail.isalpha():
            core += "."
    return core


def load(path=None):
    """Every correction, newest first. A missing or broken file is empty.

    This is read on a path that runs before every transcription, so it fails
    quiet: a dictionary nobody can parse must not stop dictation working.
    """
    candidates = [path] if path else [PATH] + list(LEGACY_PATHS)
    for candidate in candidates:
        try:
            expanded = _expand(candidate)
            if not os.path.exists(expanded):
                continue
            with open(expanded, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring unreadable dictionary %s: %s",
                           candidate, exc)
            continue
        entries = data.get("words") if isinstance(data, dict) else data
        return [e for e in (entries or []) if isinstance(e, dict)
                and _clean(e.get("meant"))]
    return []


def save(entries, path=None):
    """Writes the dictionary. Returns whether it got there."""
    expanded = _expand(path or PATH)
    try:
        folder = os.path.dirname(expanded)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(expanded, "w", encoding="utf-8") as handle:
            json.dump({"words": entries}, handle,
                      indent=2, ensure_ascii=False)
        return True
    except OSError as exc:
        logger.warning("Could not save the dictionary: %s", exc)
        return False


def add(heard, meant, entries=None, path=None):
    """Records that `heard` should have been `meant`, and returns the list.

    Correcting the same mistake again moves it to the front rather than
    adding it twice, so the words sent with the audio stay the ones in use.
    `heard` may be empty: a word can be worth declaring before it has ever
    been got wrong.
    """
    meant = _clean(meant)
    if not meant:
        return entries if entries is not None else load(path)
    heard = _clean(heard)
    if heard == meant:
        heard = ""
    entries = list(entries if entries is not None else load(path))
    before = 0
    kept = []
    for existing in entries:
        if (_clean(existing.get("meant")) == meant
                and _clean(existing.get("heard")) == heard):
            before = max(before, int(existing.get("hits") or 0))
        else:
            kept.append(existing)
    entry = {"meant": meant, "hits": before + 1}
    if heard:
        entry["heard"] = heard
    return [entry] + kept


def words(entries=None, path=None, limit=KEYWORD_LIMIT):
    """The spellings to send with the audio, newest first, without repeats."""
    out = []
    for entry in (entries if entries is not None else load(path)):
        meant = _clean(entry.get("meant"))
        if meant and meant not in out:
            out.append(meant)
        if len(out) >= limit:
            break
    return out


def apply(text, entries=None, path=None):
    """Replaces what the model heard with what was meant.

    Whole words only, so correcting "Marzhan" never rewrites the middle of
    some longer word, and never a spelling that is itself a correct one -
    a pair that would undo another person's name is dropped rather than
    guessed at.
    """
    if not text:
        return text
    entries = entries if entries is not None else load(path)
    meanings = set()
    for entry in entries:
        meant = _clean(entry.get("meant"))
        if meant:
            meanings.add(meant.casefold())

    pairs = []
    seen = set()
    for entry in entries:
        heard = _clean(entry.get("heard"))
        meant = _clean(entry.get("meant"))
        if not heard or not meant or heard == meant:
            continue
        if heard.casefold() in meanings:
            # Somebody else's correct word. Replacing it would lose a real
            # one every time they said it, which is worse than the mistake.
            logger.debug("Not replacing %r: it is a word in its own right",
                         heard)
            continue
        if heard.casefold() in seen:
            continue
        seen.add(heard.casefold())
        pairs.append((heard, meant))

    for heard, meant in pairs:
        pattern = re.compile(
            r"(?<![^\W\d_])" + re.escape(heard) + r"(?![^\W\d_])",
            re.IGNORECASE | re.UNICODE)
        text = pattern.sub(lambda match, m=meant: _match_case(match.group(0),
                                                              m), text)
    return text


def _match_case(was, now):
    """Keeps a correction from shouting, or from starting a sentence small."""
    if was.isupper() and len(was) > 1:
        return now.upper()
    if was[:1].isupper():
        return now[:1].upper() + now[1:]
    return now
