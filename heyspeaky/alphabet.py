"""The alphabet check: a word put back in the alphabet it was spoken in.

Someone who mixes Russian and English in one breath gets most of each
sentence right from the speech model, and then one word in the wrong
alphabet: "Kubernetes cluster upal" for "упал", "Данке дир" for "Danke dir",
"Ефтенг" for the Kazakh "Ертең". The model heard the word and wrote it in
the other script. It is the one mistake left that the text alone is enough
to fix, so after transcription a small text model is asked to fix exactly
that and nothing else.

Measured with tools/language_drill.py on 21 November 2026, 12 sentences
that change language, each read twice:

    model           recordings better   worse   time (median, slowest)
    gpt-5.4-mini    4 of 24             0       0.72 s, 0.84 s
    gpt-4o-mini     3 of 24             1       0.82 s, 1.76 s

gpt-4o-mini turned "ещё не пришла" into "уже пришла", which says the
opposite, and the word check below now refuses that kind of answer too.

Three rules keep it honest:

- It runs only when it can help: the text has Latin letters in it and one
  of your languages is written in Cyrillic. A purely Russian sentence is
  typed as it came, with no wait.
- It cannot rewrite you. `same_words` reads the answer and the original
  in Latin letters and refuses any answer that is not the same words, in
  the same order, some of them in the other alphabet.
- It never costs you the dictation. An error, a refused answer or a slow
  one, and the text is typed as the speech model wrote it.
"""

import difflib
import logging
import re
import time
import unicodedata

logger = logging.getLogger("heyspeaky.alphabet")

URL = "https://api.openai.com/v1/chat/completions"

# Slowest answer measured was 0.84 s. Past this the check is stuck, and the
# text goes out as the speech model wrote it.
TIMEOUT = 2.5

# Languages written in Cyrillic, by the codes languages.py uses.
CYRILLIC = {"ru", "kk", "uk", "be", "bg", "sr", "mk", "ky", "tg", "mn",
            "tt", "ba"}

INSTRUCTIONS = (
    "You fix the alphabet of dictated text and nothing else. The speaker "
    "mixes {languages}, often inside one sentence. The speech recogniser "
    "sometimes writes a word that was spoken in {cyrillic} in Latin "
    "letters, for example 'upal' for 'упал', and sometimes writes a word "
    "spoken in a Latin-script language in Cyrillic, for example 'Данке' for "
    "'Danke'. Rewrite only those words, in the alphabet of the language they "
    "were spoken in. Do not translate. Do not rephrase, reorder, correct "
    "grammar or change punctuation. Leave numbers, product names and "
    "technical terms as they are. If nothing needs changing, return the "
    "text unchanged. Reply with the text only."
)

_LATIN = re.compile(r"[A-Za-z]")

# Cyrillic read as Latin letters, only to compare an answer with the text it
# came from. Rough on purpose: "кластер" and "klaster" need to look alike,
# not to be a transliteration anyone would print.
_AS_LATIN = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ә": "a", "ғ": "g", "қ": "k", "ң": "n", "ө": "o", "ұ": "u", "ү": "u",
    "һ": "h", "і": "i", "є": "e", "ї": "i", "ґ": "g", "ў": "u", "ј": "j",
})


def needed(text, languages):
    """True when the text could hold a word in the wrong alphabet: your
    languages are written in more than one, and the text has Latin in it."""
    return (bool(_LATIN.search(text or ""))
            and any(code in CYRILLIC for code in languages)
            and any(code not in CYRILLIC for code in languages))


def _as_latin_words(text):
    text = text.lower().translate(_AS_LATIN)
    # ä to a, ß stays a letter: accents are not what this compares.
    text = "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9ß]+", text)


def same_words(before, after):
    """True if `after` is `before` with some words in another alphabet.

    Both are read as Latin letters and lined up word by word. Every word
    that differs has to still look like the word it replaced: "upal" and
    "упал" do, "schon nie" and "уже" do not. A word added or dropped is
    refused outright.
    """
    old = _as_latin_words(before)
    new = _as_latin_words(after)
    if not new:
        return False
    lined_up = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for kind, i1, i2, j1, j2 in lined_up.get_opcodes():
        if kind == "equal":
            continue
        was, now = " ".join(old[i1:i2]), " ".join(new[j1:j2])
        if not was or not now:
            return False
        if difflib.SequenceMatcher(None, was, now).ratio() < 0.6:
            return False
    return True


def instructions(languages, names, words=()):
    """The request's instructions, naming the user's own languages."""
    listed = [names.get(code, code) for code in languages]
    spoken = ", ".join(listed[:-1]) + " and " + listed[-1] \
        if len(listed) > 1 else "".join(listed)
    cyrillic = " or ".join(names.get(code, code) for code in languages
                           if code in CYRILLIC)
    text = INSTRUCTIONS.format(languages=spoken, cyrillic=cyrillic)
    if words:
        # The words the user has taught it are spelled their way already.
        text += " These words are spelled exactly as the speaker wants: {}." \
            .format(", ".join(words))
    return text


def check(text, languages, names, key, model, words=()):
    """Returns the text with its alphabets fixed, or exactly as it was."""
    if not needed(text, languages):
        return text
    import httpx

    body = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": instructions(languages, names, words)},
            {"role": "user", "content": text},
        ],
    }
    # A reasoning model left to its default thinks for seconds about a
    # one-line job. GPT-5.1 and later take "none"; older models take a
    # temperature instead.
    if model.startswith("gpt-5."):
        body["reasoning_effort"] = "none"
    else:
        body["temperature"] = 0

    started = time.monotonic()
    try:
        response = httpx.post(
            URL, headers={"Authorization": "Bearer " + key}, json=body,
            timeout=httpx.Timeout(TIMEOUT, connect=2.0))
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        # Never the text, and never the key: the error's type and status.
        logger.warning("Alphabet check skipped after %.2fs: %s",
                       time.monotonic() - started, type(exc).__name__)
        return text
    took = time.monotonic() - started

    if answer == text:
        logger.info("Alphabet check: nothing to fix (%.2fs)", took)
        return text
    if not same_words(text, answer):
        logger.info("Alphabet check: refused an answer that changed the "
                    "words (%.2fs)", took)
        return text
    changed = sum(1 for a, b in zip(text.split(), answer.split()) if a != b)
    logger.info("Alphabet check: %d word(s) moved to their own alphabet "
                "(%.2fs)", changed, took)
    return answer
