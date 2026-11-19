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


# -- finding a language by typing it --------------------------------------
#
# The owner asked for a search: scrolling ninety names for your own every
# time is the slow way. People type the name they know, which is not always
# the English one, so each language answers to what it calls itself, to its
# Russian name, and to a few other names people use for it.

NATIVE = {
    "af": "Afrikaans", "sq": "Shqip", "am": "አማርኛ", "ar": "العربية",
    "hy": "Հայերեն", "as": "অসমীয়া", "az": "Azərbaycanca", "ba": "Башҡортса",
    "eu": "Euskara", "be": "Беларуская", "bn": "বাংলা", "bs": "Bosanski",
    "br": "Brezhoneg", "bg": "Български", "my": "မြန်မာ", "ca": "Català",
    "zh": "中文", "hr": "Hrvatski", "cs": "Čeština", "da": "Dansk",
    "nl": "Nederlands", "en": "English", "et": "Eesti", "fo": "Føroyskt",
    "fi": "Suomi", "fr": "Français", "gl": "Galego", "ka": "ქართული",
    "de": "Deutsch", "el": "Ελληνικά", "gu": "ગુજરાતી",
    "ht": "Kreyòl ayisyen", "ha": "Hausa", "he": "עברית", "hi": "हिन्दी",
    "hu": "Magyar", "is": "Íslenska", "id": "Bahasa Indonesia",
    "it": "Italiano", "ja": "日本語", "kn": "ಕನ್ನಡ", "kk": "Қазақша",
    "km": "ខ្មែរ", "ko": "한국어", "lo": "ລາວ", "la": "Latina",
    "lv": "Latviešu", "ln": "Lingála", "lt": "Lietuvių",
    "lb": "Lëtzebuergesch", "mk": "Македонски", "mg": "Malagasy",
    "ms": "Bahasa Melayu", "ml": "മലയാളം", "mt": "Malti", "mi": "Māori",
    "mr": "मराठी", "mn": "Монгол", "ne": "नेपाली", "no": "Norsk",
    "nn": "Nynorsk", "oc": "Occitan", "ps": "پښتو", "fa": "فارسی",
    "pl": "Polski", "pt": "Português", "pa": "ਪੰਜਾਬੀ", "ro": "Română",
    "ru": "Русский", "sa": "संस्कृतम्", "sr": "Српски", "sn": "chiShona",
    "sd": "سنڌي", "si": "සිංහල", "sk": "Slovenčina", "sl": "Slovenščina",
    "so": "Soomaali", "es": "Español", "su": "Basa Sunda", "sw": "Kiswahili",
    "sv": "Svenska", "tl": "Tagalog", "tg": "Тоҷикӣ", "ta": "தமிழ்",
    "tt": "Татарча", "te": "తెలుగు", "th": "ไทย", "bo": "བོད་སྐད་",
    "tr": "Türkçe", "tk": "Türkmençe", "uk": "Українська", "ur": "اردو",
    "uz": "Oʻzbekcha", "vi": "Tiếng Việt", "cy": "Cymraeg", "yi": "ייִדיש",
    "yo": "Yorùbá",
}

RUSSIAN = {
    "af": "африкаанс", "sq": "албанский", "am": "амхарский", "ar": "арабский",
    "hy": "армянский", "as": "ассамский", "az": "азербайджанский",
    "ba": "башкирский", "eu": "баскский", "be": "белорусский",
    "bn": "бенгальский", "bs": "боснийский", "br": "бретонский",
    "bg": "болгарский", "my": "бирманский", "ca": "каталанский",
    "zh": "китайский", "hr": "хорватский", "cs": "чешский", "da": "датский",
    "nl": "нидерландский", "en": "английский", "et": "эстонский",
    "fo": "фарерский", "fi": "финский", "fr": "французский",
    "gl": "галисийский", "ka": "грузинский", "de": "немецкий",
    "el": "греческий", "gu": "гуджарати", "ht": "гаитянский креольский",
    "ha": "хауса", "he": "иврит", "hi": "хинди", "hu": "венгерский",
    "is": "исландский", "id": "индонезийский", "it": "итальянский",
    "ja": "японский", "kn": "каннада", "kk": "казахский", "km": "кхмерский",
    "ko": "корейский", "lo": "лаосский", "la": "латинский", "lv": "латышский",
    "ln": "лингала", "lt": "литовский", "lb": "люксембургский",
    "mk": "македонский", "mg": "малагасийский", "ms": "малайский",
    "ml": "малаялам", "mt": "мальтийский", "mi": "маори", "mr": "маратхи",
    "mn": "монгольский", "ne": "непальский", "no": "норвежский",
    "nn": "нюнорск", "oc": "окситанский", "ps": "пушту", "fa": "персидский",
    "pl": "польский", "pt": "португальский", "pa": "панджаби",
    "ro": "румынский", "ru": "русский", "sa": "санскрит", "sr": "сербский",
    "sn": "шона", "sd": "синдхи", "si": "сингальский", "sk": "словацкий",
    "sl": "словенский", "so": "сомалийский", "es": "испанский",
    "su": "сунданский", "sw": "суахили", "sv": "шведский",
    "tl": "тагальский", "tg": "таджикский", "ta": "тамильский",
    "tt": "татарский", "te": "телугу", "th": "тайский", "bo": "тибетский",
    "tr": "турецкий", "tk": "туркменский", "uk": "украинский", "ur": "урду",
    "uz": "узбекский", "vi": "вьетнамский", "cy": "валлийский", "yi": "идиш",
    "yo": "йоруба",
}

# Other names people reach for: the Kazakh names of the languages a Kazakh
# speaker is likeliest to want, and the English names that are not the one
# above.
ALIASES = {
    "ru": ("орыс",), "en": ("ағылшын",), "de": ("неміс",), "kk": ("қазақ",
                                                                  "kazak"),
    "tr": ("түрік",), "uz": ("өзбек",), "zh": ("қытай", "mandarin"),
    "fr": ("француз",), "es": ("испан", "castilian"), "ar": ("араб",),
    "ja": ("жапон",), "ko": ("корей",), "it": ("итальян",),
    "fa": ("farsi", "фарси"), "nl": ("flemish", "голландский"),
    "tl": ("filipino",), "ro": ("moldovan",), "my": ("myanmar",),
    "uk": ("украин",),
}

# Kazakh letters folded to the Russian ones nearest them, so "каз" finds
# Қазақша and "қаз" finds казахский: people type both, depending on which
# layout happens to be on.
_FOLD = str.maketrans("қғңәөұүһіё", "кгнаоууиие")


def _fold(text):
    import unicodedata
    text = unicodedata.normalize("NFKD", (text or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.translate(_FOLD).strip()


def _names_of(code):
    return [name(code), NATIVE.get(code, ""), RUSSIAN.get(code, "")] \
        + list(ALIASES.get(code, ())) + [code]


def search(codes, query):
    """`codes` that answer to `query`, best first, keeping their order within
    each kind of match: a name that starts with it, then a later word of a
    name that does, then a name that merely contains it."""
    wanted = _fold(query)
    if not wanted:
        return list(codes)
    ranked = ([], [], [])
    for code in codes:
        best = None
        for known in _names_of(code):
            folded = _fold(known)
            if not folded:
                continue
            if folded.startswith(wanted):
                rank = 0
            elif any(word.startswith(wanted) for word in folded.split()[1:]):
                rank = 1
            elif len(wanted) >= 3 and wanted in folded:
                rank = 2
            else:
                continue
            best = rank if best is None else min(best, rank)
        if best is not None:
            ranked[best].append(code)
    return ranked[0] + ranked[1] + ranked[2]


def _drawable(text):
    """Whether the panel's font has every letter of it: Latin, Greek and
    Cyrillic. Anything else would come out as empty boxes."""
    return all(char == " " or ord(char) < 0x0530 or char == "ʻ"
               for char in text)


def native_label(code):
    """What a language calls itself, for showing beside its English name -
    or "" when that says nothing new or cannot be drawn."""
    native = NATIVE.get(code, "")
    if not native or native.casefold() == name(code).casefold():
        return ""
    return native if _drawable(native) else ""


# -- a new install's languages ------------------------------------------------
#
# The defaults are the owner's own four. On anybody else's computer they are
# somebody else's languages: a new install in Madrid told the model to expect
# Kazakh, Russian, English and German, and a language the list leaves out is
# the one it mishears. Windows knows what a person speaks - the language its
# menus are in, and the keyboards they type with - so a new install starts
# from those, and the tray changes them after.

# Windows's names that are not the model's.
_WINDOWS_CODES = {"nb": "no", "nn": "no", "fil": "tl", "iw": "he"}


def from_locales(names, most=5):
    """The languages to start with, from Windows locale names such as
    "kk-KZ", in the order given: the model's codes, each once, English last -
    the front of the list is where a language counts, and the model leans to
    English unasked - and no more than `most`."""
    codes = []
    for locale in names:
        code = (locale or "").split("-")[0].lower()
        code = _WINDOWS_CODES.get(code, code)
        if code in NAMES and code not in codes:
            codes.append(code)
    english = "en" in codes
    codes = [code for code in codes if code != "en"]
    codes = codes[:most - 1] if english else codes[:most]
    if english:
        codes.append("en")
    return codes


def from_this_computer():
    """`from_locales` for this computer: the language its menus are in, then
    every keyboard layout it has, in Windows's order. An empty list if
    Windows will not say."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        def locale(langid):
            buffer = ctypes.create_unicode_buffer(85)
            if kernel32.LCIDToLocaleName(langid, buffer, 85, 0):
                return buffer.value
            return ""

        names = [locale(kernel32.GetUserDefaultUILanguage())]
        count = user32.GetKeyboardLayoutList(0, None)
        layouts = (ctypes.c_void_p * max(1, count))()
        count = user32.GetKeyboardLayoutList(count, layouts)
        for index in range(count):
            # A layout's low word is its language.
            names.append(locale((layouts[index] or 0) & 0xFFFF))
        return from_locales(names)
    except Exception:
        return []
