"""The alphabet check: a word put back in the alphabet it was spoken in.

Someone who mixes Russian and English in one breath gets most of each
sentence right from the speech model, and then one word in the wrong
alphabet: "Kubernetes cluster upal" for "упал", "Данке дир" for "Danke dir",
"Ефтенг" for the Kazakh "Ертең". The model heard the word and wrote it in
the other script. It is the one mistake left that the text alone is enough
to fix, so after transcription a small text model is asked to fix exactly
that and nothing else.

Measured with tools/language_drill.py on 21 November 2026, 24 sentences
that change language, each read twice:

    48 recordings                  words wrong  better  worse  time
    the speech model alone         9.3%
    gpt-5.4-mini, first wording    8.2%         5       0      0.73 s
    gpt-5.4-mini, this wording     8.1%         5       0      0.77 s
    gpt-5.5, this wording          6.2%         11      0      1.32 s

(time is the median; the slowest gpt-5.5 answer took 2.6 s.) With the first
wording, which described the job, the model left "I think on Prav" and
"Prosta yazabil napisat" alone. This one has it go word by word and ask
whether a Latin word is English or German at all, with examples from
outside the drill, so the drill measures the wording and not its examples.
Eight sentences nothing had been tuned on came back unchanged: nothing
better, nothing worse. gpt-4o-mini, tried first, turned "ещё не пришла"
into "уже пришла", which says the opposite; the word check below refuses
that kind of answer.

It also runs on text with no Latin in it when the speech model says it
heard Kazakh, because then the usual fault is Kazakh letters lost in
Cyrillic: "дарылык өсүмдүк экен" for "дәрілік өсімдік екен". Measured with
tools/voice_lab.py the same evening, 80 sentences from the web, eleven
voices, five rooms. Of the 194 answers with no Latin in them, the 71 the
model said it heard Kazakh in went from 26.7% of words wrong to 22.9%, 15
better and 1 worse. The other 123 would have gained too (21.2% to 18.4%,
22 better, 6 worse, most of the worse ones place names moved into Latin),
but at a second and a half on every Russian sentence, so they are not
checked.

Three rules keep it honest:

- It runs only when it can help: one of your languages is written in
  Cyrillic and another is not, and the text has Latin letters in it or
  the speech model heard Kazakh. A Russian sentence heard as Russian is
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

# The model the check asks, unless config.json names another.
MODEL = "gpt-5.5"

# The slowest answer measured was 2.6 s. Past this the check is stuck, and
# the text goes out as the speech model wrote it.
TIMEOUT = 4.0

# Languages written in Cyrillic, by the codes languages.py uses.
CYRILLIC = {"ru", "kk", "uk", "be", "bg", "sr", "mk", "ky", "tg", "mn",
            "tt", "ba"}

# One example of each mistake, per language. None is a drill sentence.
_IN_LATIN = {
    "ru": "'ya uzhe otpravil' for 'я уже отправил', 'skazhi emu' for "
          "'скажи ему'",
    "kk": "'zhaksy' for 'жақсы'",
    "uk": "'dyakuyu' for 'дякую'",
}
_IN_CYRILLIC = {
    "en": "'дедлайн тумороу' for 'deadline tomorrow'",
    "de": "'ауфвидерзейн' for 'auf Wiedersehen'",
}
_KAZAKH_LETTERS = ("Kazakh words with their letters lost or misheard: "
                   "'рахмет' for 'рақмет', 'сәлеметсиз' for 'сәлеметсіз'.")

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


def needed(text, languages, heard=()):
    """True when the text could hold a word in the wrong alphabet: your
    languages are written in more than one, and either the text has Latin
    in it or the speech model says it heard Kazakh (`heard`, its language
    codes), whose letters it loses even in Cyrillic."""
    if not (any(code in CYRILLIC for code in languages)
            and any(code not in CYRILLIC for code in languages)):
        return False
    return (bool(_LATIN.search(text or ""))
            or ("kk" in heard and "kk" in languages))


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
    """The request's instructions, built from the user's own languages."""
    def joined(codes, last):
        listed = [names.get(code, code) for code in codes]
        if len(listed) < 2:
            return "".join(listed)
        return "{} {} {}".format(", ".join(listed[:-1]), last, listed[-1])

    def examples(table, codes):
        found = [table[code] for code in codes if code in table]
        return ": " + ", ".join(found) if found else ""

    # The languages with examples first, in the tables' order: measured,
    # "Russian or Kazakh ... English or German" did half a point better
    # than the same text in the user's own order, two runs out of two.
    def ordered(codes, table):
        return sorted(codes, key=lambda code: (
            list(table).index(code) if code in table else len(table)))

    cyrillic = ordered([c for c in languages if c in CYRILLIC], _IN_LATIN)
    latin = ordered([c for c in languages if c not in CYRILLIC],
                    _IN_CYRILLIC)
    lines = [
        "You fix the alphabet of dictated text, and nothing else. The "
        "speaker mixes {}, often inside one sentence, and the speech "
        "recogniser does not always write a word in the alphabet of the "
        "language it was spoken in:".format(joined(languages, "and")),
        "- {} words written in Latin letters, as if transliterated{}."
        .format(joined(cyrillic, "or"), examples(_IN_LATIN, cyrillic)),
        "- {} words written in Cyrillic{}.".format(
            joined(latin, "or"), examples(_IN_CYRILLIC, latin)),
    ]
    if "kk" in languages:
        lines.append("- " + _KAZAKH_LETTERS)
    lines.append(
        "Go through the text word by word. A word in Latin letters that is "
        "not {a_latin} word is almost always {cyrillic}: write it in "
        "Cyrillic, "
        "spelled correctly. A word in Cyrillic that is really {latin}: write "
        "it in Latin letters. Do not translate, rephrase, reorder, add or "
        "drop words. Keep numbers, punctuation, product names and technical "
        "terms (such as Kubernetes, staging, pull request) as they are. If "
        "every word is already in its own alphabet, return the text "
        "unchanged. Reply with the text only.".format(
            latin=joined(latin, "or"), cyrillic=joined(cyrillic, "or"),
            a_latin=("an " if joined(latin, "or")[:1] in "AEIOU" else "a ")
            + joined(latin, "or")))
    if words:
        # The words the user has taught it are spelled their way already.
        lines.append("These words are spelled exactly as the speaker "
                     "wants: {}.".format(", ".join(words)))
    return "\n".join(lines)


def check(text, languages, names, key, model, words=(), heard=()):
    """Returns the text with its alphabets fixed, or exactly as it was.
    `heard` is the languages the speech model said it heard, if it said."""
    if not needed(text, languages, heard):
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
