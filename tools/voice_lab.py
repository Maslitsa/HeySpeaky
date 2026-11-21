r"""A listening lab: many voices, many rooms, sentences that change language.

HeySpeaky is only as good as what it hears, and the only honest way to make
it hear better is to measure. This makes the measurement big and varied:

    python tools\voice_lab.py texts            new sentences, from the web
    python tools\voice_lab.py run              voice them, hear them, score
    python tools\voice_lab.py run --limit 20   a cheap trial
    python tools\voice_lab.py replay report.zip

`texts` takes random Wikipedia articles in Kazakh, Russian, English and
German, and has a language model write, about each one, sentences of the kind
a bilingual person dictates: Russian that turns English halfway, Kazakh that
turns Russian, three languages at once, and short one-language phrases, which
is where a quiet voice gets heard as the wrong language. It also takes real
Russian sentences with English in them, as people write them, from Russian
tech news.
Every run of `texts` adds to the pile; nothing is thrown away.

`run` has OpenAI read every sentence in a voice and a manner picked for it -
hurried, tired, whispered, accented - then puts each reading through rooms
built in code: a laptop at arm's length, across the room, a noisy cafe, an
echoing hall. Every version goes through the app's own path, not a copy of
it: levels.normalise, then Router.transcribe with this computer's settings -
the cloud, the second opinion when the model is unsure, the alphabet check
and the dictionary. Then it plays the same answers again at other
UNSURE_BELOW lines, from what it has already heard, and says which line
would have done best.

`replay` puts the recordings in a problem report through the same path and
prints what each line would have typed. That is the way to look at a real
failure: save a problem report from the tray right after it happens.

Everything lives outside the project, in %LOCALAPPDATA%\HeySpeaky-lab: the
sentences, the voiced clips (kept, so a second run pays only for hearing),
and a report per run. None of it is ever committed: the sentences are other
people's writing, and the clips are recordings.

A quarter of the sentences are held out. Tune on the rest; a change that
only helps the sentences it was tuned on has not been shown to help.

It is not your voice. It is many voices that are not yours, in rooms that
are not yours, which is the most a lab can be.
"""

import argparse
import html
import hashlib
import json
import math
import os
import random
import re
import sys
import threading
import time
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Kazakh, Russian and German go to a console that is usually set to a
# single-byte codepage. Without this the first Kazakh letter ends the run.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import numpy as np                                           # noqa: E402

from heyspeaky import alphabet, levels, transcribe           # noqa: E402
from heyspeaky import config as config_module               # noqa: E402

LAB = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "HeySpeaky-lab"
RATE = 16000
WRITER = "gpt-5.5"
TTS_MODEL = "gpt-4o-mini-tts"
# A plain name: nothing about whose computer this is goes to Wikipedia.
AGENT = "voice-lab/1.0"

VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx",
          "sage", "shimmer", "verse"]

# How a sentence is said. None is a plain read.
MANNERS = {
    "plain": None,
    "hurried": "Speak quickly and a little carelessly, like a busy person "
               "dictating to their computer. Run words together at the ends "
               "of phrases. Do not pause where the language changes.",
    "tired": "Speak quietly and flatly, tired at the end of a long day, "
             "mumbling a little and trailing off at the end.",
    "whisper": "Speak softly, almost in a whisper, as if someone nearby is "
               "asleep.",
    "lively": "Speak fast and with energy, excited, with rising intonation.",
    "kazakh accent": "Speak with a strong Kazakh accent in every language, "
                     "Russian, English and German included.",
    "russian accent": "Speak with a strong Russian accent in English and "
                      "German, and naturally in Russian.",
    "slow": "Speak slowly and carefully, with short pauses between phrases, "
            "but add no words of your own.",
}

# What `texts` asks for. Short one-language phrases are weighted up: a short,
# quiet Russian phrase heard as Kazakh is the failure the owner actually hit.
PATTERNS = {
    "ru>en": "Russian that switches to English partway through, 8 to 18 "
             "words",
    "en>ru": "English that switches to Russian partway through, 8 to 18 "
             "words",
    "ru+en word": "Russian with one or two English words inside it, the way "
                  "people in IT or at university say them, 6 to 14 words",
    "kk>ru": "Kazakh that switches to Russian partway through, 8 to 16 words",
    "ru>kk": "Russian with a Kazakh phrase inside it, 8 to 16 words",
    "de>en": "German that switches to English, 8 to 16 words",
    "ru>de": "Russian that switches to German, 8 to 16 words",
    "three": "three of Kazakh, Russian, English and German in one sentence, "
             "10 to 20 words",
    "short ru": "a short everyday Russian phrase, Russian only, 3 to 7 words",
    "short kk": "a short everyday Kazakh phrase, Kazakh only, 3 to 7 words",
    "short en": "a short everyday English phrase, English only, 3 to 7 words",
}
ROTATION = ["ru>en", "short ru", "kk>ru", "en>ru", "ru+en word", "short ru",
            "ru>kk", "three", "short kk", "de>en", "ru>de", "short en"]

WRITER_RULES = (
    "You write test sentences for a dictation app used by people who mix "
    "Kazakh, Russian, English and German as they speak. Write the way people "
    "talk, not the way they write: everyday words, as said aloud to a "
    "computer. Every word in its own language's alphabet: Russian and Kazakh "
    "in Cyrillic, with the Kazakh letters ә ғ қ ң ө ұ ү һ і where they "
    "belong; English and German in Latin letters. No digits: write a number "
    "as words or leave it out. No abbreviations, brackets, quotation marks, "
    "emoji or lists. Switch language where a bilingual person naturally "
    "would, often in the middle of a clause. Use the passage for its topic, "
    "not its names: at most one name per sentence, and only one people "
    "would know; the rest ordinary words. (The first lab run was full of "
    "Italian villages, and no method spells those.) Reply with JSON only: "
    '{"sentences": [{"pattern": "...", "text": "..."}]}'
)

# Where real mixed sentences come from: Russian tech news, which writes
# English names and terms in Latin letters inside Russian, as people say them.
# (Habr would be the obvious one; it does not answer from here.)
FEEDS = ("https://tproger.ru/feed", "https://3dnews.ru/news/rss/")

ROOMS = ("clean", "laptop", "far", "cafe", "hall")
# The second-opinion lines to compare, from most asking again to never. The
# first one is run for real; the others replay what it already heard.
LINES = (-0.05, -0.1, -0.15, -0.2, -0.25, -0.3, -0.4, -0.5, None)
NONSENSE = 0.5


# -- the pile of sentences -------------------------------------------------


def texts_path():
    return LAB / "texts.json"


def load_texts():
    try:
        return json.loads(texts_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_texts(items):
    LAB.mkdir(parents=True, exist_ok=True)
    texts_path().write_text(json.dumps(items, ensure_ascii=False, indent=1),
                            encoding="utf-8")


def text_item(text, pattern, source):
    ident = "t{:08x}".format(zlib.crc32(text.encode("utf-8")))
    # Held out by its own name, so it stays held out on every run.
    return {"id": ident, "text": text, "pattern": pattern, "source": source,
            "holdout": zlib.crc32(ident.encode("ascii")) % 4 == 0}


def speakable(text, short=False):
    """A sentence a voice can read and a word count can score."""
    words = text.split()
    if not words or re.search(r"[\d/\\#@<>{}\[\]|=_*~^()\"«»]|https?:", text):
        return False
    return len(words) <= 9 if short else 5 <= len(words) <= 24


def speakable_mix(sentence):
    """A real sentence of Russian with English in it, short enough to say."""
    if not speakable(sentence) or len(sentence.split()) > 22:
        return False
    words = sentence.split()
    latin = sum(1 for w in words
                if re.fullmatch(r"[A-Za-z][A-Za-z'-]{2,}[,.!?:;]?", w))
    cyrillic = sum(1 for w in words if re.search(r"[а-яё]", w.lower()))
    return latin >= 1 and cyrillic >= 4


def _get(url):
    import httpx

    response = httpx.get(url, headers={"User-Agent": AGENT}, timeout=20.0,
                         follow_redirects=True)
    response.raise_for_status()
    return response


def wikipedia_passage(lang):
    url = ("https://{}.wikipedia.org/api/rest_v1/page/random/summary"
           .format(lang))
    # Wikipedia turns away a burst of these; a pause gets the next one in.
    for attempt in range(3):
        try:
            data = _get(url).json()
            return data.get("title") or "", data.get("extract") or ""
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3.0 * (attempt + 1))


def feed_sentences(url):
    """Real sentences of Russian with English in them, from a news feed."""
    feed = _get(url).text
    found = []
    for block in re.findall(r"<(description|content:encoded)>(.*?)</\1>",
                            feed, re.S):
        block = block[1]
        block = re.sub(r"<!\[CDATA\[|\]\]>", "", block)
        block = html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(block)))
        for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", block)):
            sentence = sentence.strip()
            if speakable_mix(sentence):
                found.append(sentence)
    return found


def write_sentences(key, title, passage, patterns):
    """A language model's sentences about a passage, one per pattern."""
    import httpx

    wanted = "\n".join("{}. {}: {}".format(i + 1, name, PATTERNS[name])
                       for i, name in enumerate(patterns))
    ask = ("A passage from Wikipedia, \"{}\":\n{}\n\nWrite one sentence for "
           "each pattern below, loosely about this passage - its names, "
           "places and ideas are welcome. Use the pattern name as given.\n{}"
           .format(title, passage[:1500], wanted))
    body = {"model": WRITER, "reasoning_effort": "low",
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": WRITER_RULES},
                         {"role": "user", "content": ask}]}
    response = httpx.post(alphabet.URL, json=body, timeout=120.0,
                          headers={"Authorization": "Bearer " + key})
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    out = []
    for entry in json.loads(content).get("sentences") or []:
        pattern = str(entry.get("pattern", "")).strip()
        text = re.sub(r"\s+", " ", str(entry.get("text", ""))).strip()
        if pattern in PATTERNS and speakable(text, pattern.startswith("short")):
            out.append((pattern, text))
    return out


def gather(key, articles, real):
    items = load_texts()
    known = {item["id"] for item in items}
    added = 0

    def add(text, pattern, source):
        nonlocal added
        item = text_item(text, pattern, source)
        if item["id"] not in known:
            known.add(item["id"])
            items.append(item)
            added += 1

    for url in FEEDS:
        if not real:
            break
        try:
            sentences = feed_sentences(url)
            random.Random(time.time()).shuffle(sentences)
            for sentence in sentences[:real // len(FEEDS)]:
                add(sentence, "real ru+en", url.split("/")[2])
        except Exception as exc:
            print("  {}: skipped ({})".format(url, type(exc).__name__))
    turn = len(items)
    for index in range(articles):
        lang = ("kk", "ru", "en", "de")[index % 4]
        patterns = [ROTATION[(turn + index * 4 + k) % len(ROTATION)]
                    for k in range(4)]
        try:
            title, passage = wikipedia_passage(lang)
            if len(passage) < 80:
                continue
            for pattern, text in write_sentences(key, title, passage,
                                                 patterns):
                add(text, pattern, "{}.wikipedia.org: {}".format(lang, title))
            print("  {} {:<40} {} sentences so far".format(
                lang, title[:40], len(items)), flush=True)
        except Exception as exc:
            print("  {}: skipped ({})".format(lang, type(exc).__name__))
    save_texts(items)
    return added, len(items)


# -- voices ----------------------------------------------------------------


def casting(item, take):
    """The voice and manner for one reading, the same on every run."""
    pick = random.Random(zlib.crc32("{}/{}".format(item["id"], take)
                                    .encode("ascii")))
    return pick.choice(VOICES), pick.choice(sorted(MANNERS))


def voiced(key, item, take):
    """One reading of one sentence, made once and kept."""
    import httpx

    voice, manner = casting(item, take)
    path = LAB / "clips" / "{}-{}-{}.wav".format(
        item["id"], voice, manner.replace(" ", "_"))
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {"model": TTS_MODEL, "voice": voice, "input": item["text"],
                "response_format": "wav"}
        if MANNERS[manner]:
            body["instructions"] = MANNERS[manner]
        response = httpx.post("https://api.openai.com/v1/audio/speech",
                              json=body, timeout=120.0,
                              headers={"Authorization": "Bearer " + key})
        response.raise_for_status()
        path.write_bytes(response.content)
    return path, voice, manner


def read_wav(path):
    """A wav as float samples at 16 kHz, mono."""
    import wave

    with wave.open(str(path), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
        source = handle.getframerate()
        channels = handle.getnchannels()
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels)[:, 0]
    if source != RATE:
        count = int(len(audio) * RATE / source)
        audio = np.interp(np.linspace(0.0, len(audio) - 1, count),
                          np.arange(len(audio)), audio).astype(np.float32)
    return audio


# -- rooms -----------------------------------------------------------------
# Each takes clean speech and a random generator and returns what a
# microphone would have caught. Built from filters and noise rather than
# recordings of rooms, so nothing has to be downloaded and every run of the
# same sentence gets the same room.


def _shape(x, response):
    """x through a filter given as gain per frequency in Hz."""
    freqs = np.fft.rfftfreq(len(x), 1.0 / RATE)
    return np.fft.irfft(np.fft.rfft(x) * response(freqs),
                        n=len(x)).astype(np.float32)


def _rms(x):
    return float(np.sqrt(np.mean(x * x))) + 1e-12


def _noise(rng, n, tilt):
    """Noise at unit level: tilt 0 is hiss, 1 is a fan, 2 is a rumble."""
    white = rng.standard_normal(n).astype(np.float32)
    shaped = _shape(white, lambda f: np.maximum(f, 20.0) ** (-tilt / 2.0))
    return shaped / _rms(shaped)


def _to_level(x, level):
    """Scaled so its loud moments sit at `level` of full scale."""
    return x * (level / (float(np.percentile(np.abs(x), 99.0)) + 1e-9))


def _laptop_mic(f):
    """Little below 200 Hz, little above 7 kHz: a laptop's microphone."""
    f = np.maximum(f, 1.0)
    return 1.0 / np.sqrt((1 + (200.0 / f) ** 4) * (1 + (f / 7000.0) ** 4))


def _reverb(x, rng, seconds, wet):
    """A room's echo: noise dying away by 60 dB over `seconds`."""
    n = int(seconds * RATE)
    tail = (rng.standard_normal(n).astype(np.float32)
            * np.exp(-6.9 * np.arange(n) / float(n)).astype(np.float32))
    size = len(x) + n
    echo = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(tail, size),
                        n=size)[:len(x)].astype(np.float32)
    return x + wet * echo * (_rms(x) / _rms(echo))


def room(name, speech, rng):
    if name == "clean":
        return _to_level(speech, 0.5)
    if name == "laptop":
        # About where the owner's laptop sits: the app boosts it some eight
        # times, as it did the recording that came back as nonsense.
        heard = _to_level(_shape(speech, _laptop_mic), 0.1)
        return heard + 0.0015 * _noise(rng, len(heard), 0)
    if name == "far":
        heard = _shape(_reverb(speech, rng, 0.35, 0.3), _laptop_mic)
        heard = _to_level(heard, 0.03)
        return heard + 0.002 * _noise(rng, len(heard), 1)
    if name == "cafe":
        heard = _to_level(_shape(speech, _laptop_mic), 0.15)
        chatter = _noise(rng, len(heard), 1)
        beat = np.arange(len(heard)) / float(RATE)
        chatter *= 1 + 0.6 * np.sin(2 * np.pi * 3.7 * beat
                                    + rng.uniform(0, 2 * np.pi))
        # Eight decibels under the voice: a busy place, not a loud one.
        return heard + chatter * (_rms(heard) / _rms(chatter)) / 2.5
    if name == "hall":
        return _to_level(_reverb(speech, rng, 0.9, 0.6), 0.1)
    raise ValueError(name)


def recording(speech, room_name, seed, settings):
    """The PCM the app would have sent: padded, roomed, then boosted as the
    app boosts it."""
    rng = np.random.default_rng(seed)
    padded = np.concatenate([np.zeros(int(0.4 * RATE), np.float32), speech,
                             np.zeros(int(0.6 * RATE), np.float32)])
    heard = room(room_name, padded, rng)
    pcm = (np.clip(heard, -1, 1) * 32767).astype(np.int16).tobytes()
    return levels.normalise(pcm, settings)


# -- hearing ---------------------------------------------------------------


class Ear:
    """The app's own Router, with every answer from OpenAI remembered, so the
    same recordings can be played again at another line for nothing."""

    def __init__(self, cfg):
        self.language = cfg["model"].get("language") or ""
        self.router = transcribe.Router(None, cfg)
        self.answers = {}
        self._checked = {}
        self._lock = threading.Lock()
        ask = self.router.cloud.heard

        def heard(pcm_bytes, language, first=None):
            key = (hashlib.sha1(pcm_bytes).hexdigest(), language, first)
            with self._lock:
                if key in self.answers:
                    return self.answers[key]
            answer = ask(pcm_bytes, language, first=first)
            with self._lock:
                self.answers[key] = answer
            return answer

        self.router.cloud.heard = heard
        check = alphabet.check

        def checked(text, *args, **kwargs):
            key = (text, tuple(kwargs.get("heard") or ()))
            if key not in self._checked:
                self._checked[key] = check(text, *args, **kwargs)
            return self._checked[key]

        # Router calls alphabet.check through the module, so this is the one
        # it finds.
        alphabet.check = checked

    def hear(self, pcm):
        self.router._offline_until = 0.0
        try:
            return self.router.transcribe(pcm, self.language)[0]
        except Exception as exc:
            return "FAILED: " + type(exc).__name__

    def first(self, pcm):
        return self.answers.get(
            (hashlib.sha1(pcm).hexdigest(), self.language, None))


def _plain(text):
    return text.lower().replace("ё", "е")


def error_rate(reference, heard):
    """Words wrong, from tools/benchmark.py, with ё read as е and a
    hallucinated paragraph counted as wholly wrong rather than more."""
    import importlib.util

    global _benchmark_error_rate
    if _benchmark_error_rate is None:
        spec = importlib.util.spec_from_file_location(
            "benchmark", ROOT / "tools" / "benchmark.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _benchmark_error_rate = module.error_rate
    rate = _benchmark_error_rate(_plain(reference), _plain(heard))
    return min(1.0, rate if rate is not None else 1.0)


_benchmark_error_rate = None


def set_line(line):
    transcribe.UNSURE_BELOW = -math.inf if line is None else line


def lab_config():
    cfg = config_module.load()
    cfg["transcription"]["backend"] = "cloud"
    # A failure should be counted, not quietly heard by the local model.
    cfg["transcription"]["cloud"]["fallback_to_local"] = False
    return cfg


def run(args):
    cfg = lab_config()
    ear = Ear(cfg)
    key = ear.router.cloud.api_key
    if not key:
        print("No OpenAI key found.")
        return 1
    items = load_texts()
    if not items:
        print("No sentences yet: run `voice_lab.py texts` first.")
        return 1
    if args.limit:
        items = random.Random(7).sample(items, min(args.limit, len(items)))
    rooms = [r.strip() for r in args.rooms.split(",")] if args.rooms else ROOMS
    shipped = transcribe.UNSURE_BELOW

    print("Voicing {} sentences ({} reading(s) each)...".format(
        len(items), args.takes), flush=True)
    plan = [(item, take) for item in items for take in range(args.takes)]

    def voice_one(entry):
        try:
            return voiced(key, *entry)
        except Exception as exc:
            print("  could not voice {}: {}".format(entry[0]["id"],
                                                    type(exc).__name__))
            return None

    with ThreadPoolExecutor(4) as pool:
        clips = list(pool.map(voice_one, plan))

    versions = []
    for (item, take), clip in zip(plan, clips):
        if clip is None:
            continue
        path, voice, manner = clip
        speech = read_wav(path)
        for room_name in rooms:
            seed = zlib.crc32("{}/{}/{}".format(item["id"], take, room_name)
                              .encode("ascii"))
            pcm = recording(speech, room_name, seed, cfg["recording"])
            versions.append({"item": item, "voice": voice, "manner": manner,
                             "room": room_name, "pcm": pcm,
                             "seconds": len(pcm) / 2.0 / RATE})
    minutes = sum(v["seconds"] for v in versions) / 60.0
    lines = lines_with(shipped)
    print("Hearing {} versions, {:.0f} minutes of audio, at {} lines..."
          .format(len(versions), minutes, len(lines)), flush=True)

    started = time.monotonic()
    for line in lines:
        set_line(line)
        with ThreadPoolExecutor(args.workers) as pool:
            heard = list(pool.map(ear.hear, [v["pcm"] for v in versions]))
        for version, text in zip(versions, heard):
            version.setdefault("heard", {})[str(line)] = text
            version.setdefault("errors", {})[str(line)] = error_rate(
                version["item"]["text"], text)
        print("  line {:>5}: {:.1f}% of words wrong ({:.0f}s)".format(
            str(line), 100 * _mean(v["errors"][str(line)] for v in versions),
            time.monotonic() - started), flush=True)
    set_line(shipped)

    for version in versions:
        first = ear.first(version["pcm"])
        version["first"] = None if first is None else {
            "text": first.text, "average": first.average,
            "lowest": first.lowest, "languages": list(first.languages)}
        version["first_errors"] = (None if first is None else
                                   error_rate(version["item"]["text"],
                                              first.text))
    return report(versions, lines, shipped, cfg, minutes)


def lines_with(shipped):
    """LINES, with the one the app ships among them, most asking first."""
    numbers = {line for line in LINES if line is not None} | {shipped}
    return sorted(numbers, reverse=True) + [None]


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else float("nan")


def report(versions, lines_run, shipped, cfg, minutes):
    stamp = time.strftime("%Y-%m-%d %H%M")
    folder = LAB / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    now = str(shipped)
    lines = ["# Listening lab, {}".format(stamp), "",
             "{} versions of {} sentences, {:.0f} minutes of audio. "
             "Languages {}, second opinion below {}.".format(
                 len(versions), len({v["item"]["id"] for v in versions}),
                 minutes,
                 ", ".join(cfg["transcription"]["cloud"].get("languages")
                           or []), shipped), ""]

    def table(title, key):
        groups = {}
        for v in versions:
            groups.setdefault(key(v), []).append(v)
        lines.extend(["## " + title, "",
                      "| | versions | words wrong | nonsense |",
                      "| --- | --- | --- | --- |"])
        for name, rows in sorted(groups.items(),
                                 key=lambda kv: -_mean(r["errors"][now]
                                                       for r in kv[1])):
            lines.append("| {} | {} | {:.1f}% | {} |".format(
                name, len(rows), 100 * _mean(r["errors"][now] for r in rows),
                sum(1 for r in rows if r["errors"][now] >= NONSENSE)))
        lines.append("")

    table("As shipped, by room", lambda v: v["room"])
    table("By manner", lambda v: v["manner"])
    table("By kind of sentence", lambda v: v["item"]["pattern"])
    table("By voice", lambda v: v["voice"])

    lines.extend(["## The second-opinion line", "",
                  "Asked again when the model's average log probability is "
                  "below the line. Tune on the first columns; the held-out "
                  "ones are the check.", "",
                  "| line | words wrong | nonsense | asked again | held out: "
                  "words wrong | held out: nonsense |",
                  "| --- | --- | --- | --- | --- | --- |"])
    for line in lines_run:
        tag = str(line)
        tune = [v for v in versions if not v["item"]["holdout"]]
        held = [v for v in versions if v["item"]["holdout"]]
        again = sum(1 for v in versions if v["first"]
                    and v["first"]["average"] is not None
                    and line is not None and v["first"]["average"] < line)
        lines.append("| {}{} | {:.1f}% | {} | {:.0f}% | {:.1f}% | {} |".format(
            "never" if line is None else line,
            " (now)" if tag == now else "",
            100 * _mean(v["errors"][tag] for v in tune),
            sum(1 for v in tune if v["errors"][tag] >= NONSENSE),
            100.0 * again / max(1, len(versions)),
            100 * _mean(v["errors"][tag] for v in held),
            sum(1 for v in held if v["errors"][tag] >= NONSENSE)))
    lines.append("")

    sure = sorted((v["first"]["average"], v["first_errors"])
                  for v in versions if v["first"]
                  and v["first"]["average"] is not None)
    if sure:
        bad = [a for a, e in sure if e >= NONSENSE]
        good = [a for a, e in sure if e < NONSENSE]
        lines.extend(["## How sure the model was", "",
                      "Average log probability of the first answer.", "",
                      "| | answers | lowest | median | highest |",
                      "| --- | --- | --- | --- | --- |"])
        for name, values in (("nonsense", bad), ("the rest", good)):
            if values:
                lines.append("| {} | {} | {:.3f} | {:.3f} | {:.3f} |".format(
                    name, len(values), values[0], values[len(values) // 2],
                    values[-1]))
        lines.append("")

    worst = sorted(versions, key=lambda v: -v["errors"][now])[:25]
    lines.extend(["## The worst", ""])
    for v in worst:
        first = v["first"] or {}
        lines.append("- **{:.0f}%** {} / {} / {}, heard {} at {}  \n"
                     "  said: {}  \n  typed: {}".format(
                         100 * v["errors"][now], v["room"], v["manner"],
                         v["voice"], ",".join(first.get("languages") or [])
                         or "?", "{:.3f}".format(first["average"])
                         if first.get("average") is not None else "?",
                         v["item"]["text"], v["heard"][now]))
    text = "\n".join(lines) + "\n"
    (folder / (stamp + ".md")).write_text(text, encoding="utf-8")
    keep = [{k: v[k] for k in v if k != "pcm"} for v in versions]
    (folder / (stamp + ".json")).write_text(
        json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + text)
    print("wrote", folder / (stamp + ".md"))
    return 0


def replay(args):
    """A problem report's recordings, through the path at every line."""
    cfg = lab_config()
    ear = Ear(cfg)
    with zipfile.ZipFile(args.report) as archive:
        names = sorted(n for n in archive.namelist()
                       if n.startswith("recordings/") and n.endswith(".wav"))
        for name in names:
            scratch = LAB / "replay.wav"
            LAB.mkdir(parents=True, exist_ok=True)
            scratch.write_bytes(archive.read(name))
            pcm = (np.clip(read_wav(scratch), -1, 1) * 32767).astype(
                np.int16).tobytes()
            scratch.unlink()
            pcm = levels.normalise(pcm, cfg["recording"])
            print("\n" + name)
            for line in lines_with(transcribe.UNSURE_BELOW):
                set_line(line)
                text = ear.hear(pcm)
                first = ear.first(pcm)
                print("  {:>6}  {}  {}".format(
                    "never" if line is None else line,
                    "" if first is None or first.average is None
                    else "{:.3f} {}".format(first.average,
                                            ",".join(first.languages)),
                    text))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    gather_cmd = sub.add_parser("texts", help="new sentences from the web")
    gather_cmd.add_argument("--articles", type=int, default=24)
    gather_cmd.add_argument("--real", type=int, default=16,
                            help="real sentences from Russian tech news")
    run_cmd = sub.add_parser("run", help="voice, hear and score")
    run_cmd.add_argument("--limit", type=int,
                         help="only this many sentences, picked at random")
    run_cmd.add_argument("--takes", type=int, default=1,
                         help="readings per sentence, each a new voice")
    run_cmd.add_argument("--rooms", help="comma-separated, of: " +
                         ", ".join(ROOMS))
    run_cmd.add_argument("--workers", type=int, default=6)
    replay_cmd = sub.add_parser("replay", help="a problem report's recordings")
    replay_cmd.add_argument("report")
    args = parser.parse_args()

    if args.command == "texts":
        key = transcribe.CloudBackend(lab_config()).api_key
        if not key:
            print("No OpenAI key found.")
            return 1
        added, total = gather(key, args.articles, args.real)
        print("Added {} sentences; {} in {}".format(added, total,
                                                     texts_path()))
        return 0
    if args.command == "run":
        return run(args)
    return replay(args)


if __name__ == "__main__":
    sys.exit(main())
