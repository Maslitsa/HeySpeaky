"""The languages you dictate in.

There is one list of them, transcription.cloud.languages. The cloud model is
told to expect those languages, the prompt and keywords are generated from
them, and the tray offers them as the ones you can pin.

model.language_menu used to be a second list, just for the tray, so the two
could disagree. It is now rebuilt from the first whenever a language is added
or removed, and reconcile() folds any old hand-edited difference back in.
"""

# Every language Whisper can transcribe, which is what the tray offers under
# Language > Add or remove languages. Left out: Hawaiian (haw), Cantonese (yue)
# and Javanese (jw), whose codes are not the two-letter ones OpenAI accepts, so
# a request naming them would fail and quietly fall back to local. Any code can
# still be typed into config.json and is shown as is.
NAMES = {
    "af": "Afrikaans", "sq": "Albanian", "am": "Amharic", "ar": "Arabic",
    "hy": "Armenian", "as": "Assamese", "az": "Azerbaijani", "ba": "Bashkir",
    "eu": "Basque", "be": "Belarusian", "bn": "Bengali", "bs": "Bosnian",
    "br": "Breton", "bg": "Bulgarian", "my": "Burmese", "ca": "Catalan",
    "zh": "Chinese", "hr": "Croatian", "cs": "Czech", "da": "Danish",
    "nl": "Dutch", "en": "English", "et": "Estonian", "fo": "Faroese",
    "fi": "Finnish", "fr": "French", "gl": "Galician", "ka": "Georgian",
    "de": "German", "el": "Greek", "gu": "Gujarati", "ht": "Haitian Creole",
    "ha": "Hausa", "he": "Hebrew", "hi": "Hindi", "hu": "Hungarian",
    "is": "Icelandic", "id": "Indonesian", "it": "Italian", "ja": "Japanese",
    "kn": "Kannada", "kk": "Kazakh", "km": "Khmer", "ko": "Korean",
    "lo": "Lao", "la": "Latin", "lv": "Latvian", "ln": "Lingala",
    "lt": "Lithuanian", "lb": "Luxembourgish", "mk": "Macedonian",
    "mg": "Malagasy", "ms": "Malay", "ml": "Malayalam", "mt": "Maltese",
    "mi": "Maori", "mr": "Marathi", "mn": "Mongolian", "ne": "Nepali",
    "no": "Norwegian", "nn": "Norwegian Nynorsk", "oc": "Occitan",
    "ps": "Pashto", "fa": "Persian", "pl": "Polish", "pt": "Portuguese",
    "pa": "Punjabi", "ro": "Romanian", "ru": "Russian", "sa": "Sanskrit",
    "sr": "Serbian", "sn": "Shona", "sd": "Sindhi", "si": "Sinhala",
    "sk": "Slovak", "sl": "Slovenian", "so": "Somali", "es": "Spanish",
    "su": "Sundanese", "sw": "Swahili", "sv": "Swedish", "tl": "Tagalog",
    "tg": "Tajik", "ta": "Tamil", "tt": "Tatar", "te": "Telugu", "th": "Thai",
    "bo": "Tibetan", "tr": "Turkish", "tk": "Turkmen", "uk": "Ukrainian",
    "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese", "cy": "Welsh",
    "yi": "Yiddish", "yo": "Yoruba",
}

# A Windows menu taller than the screen grows scroll arrows, so the full list
# is split into submenus of about this many.
GROUP_SIZE = 16


def name(code):
    return NAMES.get(code, code)


def catalog(current):
    """Every language the tray offers, by name, plus any custom codes in use."""
    codes = set(NAMES) | {code for code in current if code}
    return sorted(codes, key=lambda code: name(code).lower())


def groups(codes, size=GROUP_SIZE):
    """Splits codes, already sorted by name, into (label, codes) submenus.

    Splits only between letters, so each letter lives in exactly one group
    and the labels read like a dictionary's: "A – C", "D – H".
    """
    by_letter = []
    for code in codes:
        letter = name(code)[:1].upper()
        if by_letter and by_letter[-1][0] == letter:
            by_letter[-1][1].append(code)
        else:
            by_letter.append((letter, [code]))

    result = []
    first = last = None
    current = []
    for letter, members in by_letter:
        if current and len(current) + len(members) > size:
            result.append((_label(first, last), current))
            current = []
        if not current:
            first = letter
        current.extend(members)
        last = letter
    if current:
        result.append((_label(first, last), current))
    return result


def _label(first, last):
    return first if first == last else "{} – {}".format(first, last)


def menu_for(codes):
    """The pin list as config.json has always stored it."""
    menu = {"Auto-detect": ""}
    for code in codes:
        menu[name(code)] = code
    return menu


def toggle(cfg, code):
    """Adds the language if it is missing and removes it if it is there.

    Returns "added", "removed", or "kept" when it is the last one left, since
    an empty list would leave nothing to pin and nothing to steer the model.

    The list is edited in place because the tray holds a reference to it to
    draw its checkmarks. A removed language that was pinned is unpinned, so
    the app never stays pinned to a language you just took away.
    """
    languages = cfg["transcription"]["cloud"]["languages"]
    if code in languages:
        if len(languages) == 1:
            return "kept"
        languages.remove(code)
        if cfg["model"]["language"] == code:
            cfg["model"]["language"] = ""
        result = "removed"
    else:
        # At the front, not the end. The order of this list is a priority
        # order to the model: a language near the end of it is effectively
        # ignored on a short stretch of speech, which would mean a language
        # you just went and enabled did nothing. Measured in
        # tools/language_drill.py; the numbers are in config.py next to the
        # default list.
        languages.insert(0, code)
        result = "added"
    cfg["model"]["language_menu"] = menu_for(languages)
    return result


def reconcile(cfg):
    """Brings the tray menu, a pinned language and the list into agreement.

    Before languages could be added from the tray, config.json had to be
    edited by hand, and the menu could name a language the list did not.
    Anything either one names is kept. Returns True if something changed, so
    the caller knows to save.
    """
    languages = cfg["transcription"]["cloud"]["languages"]
    before = list(languages)
    named = [code for code in cfg["model"].get("language_menu", {}).values()]
    named.append(cfg["model"].get("language") or "")
    for code in named:
        if code and code not in languages:
            # Same reason as in toggle(): the front of the list is where a
            # language actually counts.
            languages.insert(0, code)
    if not languages:
        languages.append("en")
    menu = menu_for(languages)
    changed = languages != before or cfg["model"].get("language_menu") != menu
    cfg["model"]["language_menu"] = menu
    return changed
