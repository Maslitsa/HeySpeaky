r"""How well does a sentence survive changing language halfway through?

This is the hard case HeySpeaky exists for, and the only honest way to tune
it is to measure. **The model itself cannot be fine-tuned** - it is OpenAI's,
and there is no training here. What can be tuned is everything we send with
the audio: which model, which languages we declare, the steering prompt, and
the keywords. That is what this compares, on sentences chosen to be awkward.

Two ways to get the audio:

    .venv\Scripts\python.exe tools\language_drill.py --tts
    .venv\Scripts\python.exe tools\language_drill.py --report path\to\report.zip

--tts has OpenAI read the sentences, twice each: once plainly, and once fast
and slurred with an accent, which is where transcription actually breaks.
Useful because it is repeatable, and limited in exactly one way worth saying
out loud: **it is not your voice.** A setting that wins here has been shown
to survive difficult speech, not to survive yours. For that, dictate the
sentences yourself with HeySpeaky, save a problem report from the tray, and
point --report at it; the sentences are matched to the recordings in order.

Costs a few cents of the key's money per run, all of it transcription.
"""

import argparse
import copy
import importlib.util
import json
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# This prints Russian, German and Kazakh into a console that is usually set to
# a single-byte codepage. Without this the first Kazakh letter ends the run.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from heyspeaky import config as config_module               # noqa: E402
from heyspeaky.transcribe import CloudBackend               # noqa: E402

TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = "alloy"
# The whole point is speech that is hard to hear. A clean read of these
# sentences is not the case that fails.
HARD_DELIVERY = (
    "Speak quickly and a little carelessly, as a busy person dictating to "
    "their computer. Run words together at the ends of phrases. Keep a "
    "noticeable Russian accent in every language, including the English and "
    "the German. Do not pause at the points where the language changes."
)

# Sentences that change language where a model least expects it: inside a
# clause, on a function word, around numbers, and across proper nouns that
# sound like ordinary words.
SENTENCES = [
    ("rechnung",
     "I'll send the Rechnung tomorrow, aber nur wenn der Kunde bis dann "
     "geantwortet hat.",
     "English into German on a noun, then a full German clause"),
    ("staging",
     "Я уже задепло"
     "ил на стейджи"
     "нг, but the migration still fails on the unique constraint.",
     "Russian into English across a comma, technical vocabulary"),
    ("termin",
     "Der Termin ist am dreiundzwanzigsten, но я ос"
     "вобожусь тол"
     "ько после шес"
     "ти.",
     "German into Russian, spoken numbers on both sides"),
    ("agenda",
     "Ертең кездес"
     "еміз, but please send the agenda before the call.",
     "Kazakh into English"),
    ("overdue",
     "The invoice is overdue, клиент г"
     "оворит что не "
     "получал, und ich glaube ihm nicht.",
     "three languages in one sentence"),
    ("actually",
     "Это довольно "
     "актуально, actually it is "
     "not relevant at all, eventuell später.",
     "false friends: aktualno, actually, eventuell"),
    ("ingress",
     "Kubernetes кластер уп"
     "ал, and the Ingress controller returned five zero two.",
     "proper nouns that sound like ordinary words"),
    ("basically",
     "Ну то есть, well, ich meine, "
     "it's basically the same thing.",
     "three switches on filler words alone"),
    ("aufenthalt",
     "Die Aufenthaltsgenehmigung ещё не п"
     "ришла, so I cannot book the flight.",
     "a long German compound, then Russian, then English"),
    ("flight",
     "Мен ертең ұша"
     "мын, потом сра"
     "зу на конфере"
     "нцию, and I land at half past seven.",
     "Kazakh into Russian into English"),
    ("calendar",
     "Встреча "
     "двадцать "
     "второго "
     "сентября "
     "в четырна"
     "дцать три"
     "дцать, put it in the calendar as "
     "fourteen thirty, nicht halb drei.",
     "the same time said three ways in three languages"),
    ("pullrequest",
     "Можешь гляну"
     "ть пул-реквес"
     "т, the one with the flaky test, danke dir.",
     "trails off into a quiet German goodbye"),
]


def _try_demo():
    """Borrows the wav reader from tools/try_demo.py rather than copying it."""
    spec = importlib.util.spec_from_file_location(
        "try_demo", ROOT / "tools" / "try_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _benchmark():
    """Borrows the word error rate from tools/benchmark.py."""
    spec = importlib.util.spec_from_file_location(
        "benchmark", ROOT / "tools" / "benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def speak(api_key, text, path, instructions=None):
    """Has OpenAI read one sentence into a wav file."""
    import httpx

    body = {"model": TTS_MODEL, "voice": TTS_VOICE, "input": text,
            "response_format": "wav"}
    if instructions:
        body["instructions"] = instructions
    response = httpx.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": "Bearer " + api_key},
        json=body, timeout=120.0)
    response.raise_for_status()
    path.write_bytes(response.content)
    return path


def synthesise(api_key, into, takes=("plain", "hard")):
    """Every sentence, read plainly and read badly."""
    into.mkdir(parents=True, exist_ok=True)
    clips = []
    for name, text, _note in SENTENCES:
        for take in takes:
            path = into / "{}-{}.wav".format(name, take)
            if not path.exists():
                speak(api_key, text, path,
                      HARD_DELIVERY if take == "hard" else None)
                print("  said {}".format(path.name), flush=True)
            clips.append((name, take, path))
    return clips


def clips_from_report(path, into):
    """Recordings out of a problem report, matched to sentences in order."""
    into.mkdir(parents=True, exist_ok=True)
    found = []
    with zipfile.ZipFile(path) as archive:
        names = [n for n in sorted(archive.namelist())
                 if n.startswith("recordings/") and n.endswith(".wav")]
    with zipfile.ZipFile(path) as archive:
        for index, name in enumerate(names):
            if index >= len(SENTENCES):
                break
            target = into / Path(name).name
            target.write_bytes(archive.read(name))
            found.append((SENTENCES[index][0], "yours", target))
    return found


def variants(base):
    """The settings worth comparing: a config, plus what to silence.

    Clearing `prompt` or `keywords` in the config does NOT turn them off.
    transcribe.py fills an empty prompt with one generated from the languages,
    and appends its glue keywords to whatever list it is given. The first run
    of this tool compared three configs that produced byte-identical requests
    and reported the sameness as a finding. A variant that means "without"
    has to silence the helpers themselves.
    """
    def cfg(**cloud):
        out = copy.deepcopy(base)
        out["transcription"]["cloud"].update(cloud)
        return out

    return [
        ("as shipped", cfg(), set()),
        ("languages only", cfg(), {"prompt", "keywords"}),
        ("no keywords", cfg(), {"keywords"}),
        ("no prompt", cfg(), {"prompt"}),
        ("nothing declared", cfg(languages=[]), {"prompt", "keywords"}),
        # The order of the list is not decoration. A language near the end of
        # it is effectively ignored on a short stretch of speech.
        ("kazakh first", cfg(languages=["kk", "ru", "en", "de"]), set()),
        ("kazakh first, no kw",
         cfg(languages=["kk", "ru", "en", "de"]), {"keywords"}),
        # English last rather than third: what a new install gets from its
        # computer's languages, and never measured before.
        ("english last", cfg(languages=["kk", "ru", "de", "en"]), set()),
        # The prompt as a line of transcript in all four scripts, rather than
        # a sentence about them: the model reads a prompt as text that came
        # before, not as an instruction, which is why a longer instruction
        # did worse. None of these words is in a drill sentence.
        ("example prompt", cfg(languages=["kk", "ru", "en", "de"],
                               prompt="Рақмет, бәрі түсінікті. Спасибо, всё "
                                      "понятно. Thanks, got it. Danke, alles "
                                      "klar."), set()),
    ]


class silence_helpers(object):
    """Turns off the prompt or the keywords at their source, for one run."""

    def __init__(self, what):
        self.what = what
        self.saved = {}

    def __enter__(self):
        from heyspeaky import transcribe

        if "prompt" in self.what:
            self.saved["_default_prompt"] = transcribe._default_prompt
            transcribe._default_prompt = lambda codes: ""
        if "keywords" in self.what:
            self.saved["_default_keywords"] = transcribe._default_keywords
            transcribe._default_keywords = lambda codes: []
        return self

    def __exit__(self, *exc):
        from heyspeaky import transcribe

        for name, original in self.saved.items():
            setattr(transcribe, name, original)
        return False


CYRILLIC = set(range(0x0400, 0x0530))


def cyrillic_share(text):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if ord(c) in CYRILLIC) / float(len(letters))


def script_loss(reference, heard):
    """How much of the Cyrillic came back as Latin, which is the real fault.

    A word error rate counts "23." against "dreiundzwanzigsten", and the word
    "staging" against the same word spelled in Cyrillic. Neither is wrong.
    Russian transliterated into Latin always is, and that is the failure this
    project was built to avoid, so it gets its own number.
    """
    want = cyrillic_share(reference)
    if want <= 0.01:
        return None
    return max(0.0, want - cyrillic_share(heard)) / want


def run(cfg, clips, read_pcm, rate, quiet):
    with silence_helpers(quiet):
        backend = CloudBackend(cfg)
        heard = {}
        for name, take, path in clips:
            pcm, _ = read_pcm(path, rate)
            try:
                heard[(name, take)] = backend.transcribe(pcm, "")
            except Exception as exc:
                heard[(name, take)] = "FAILED: {}".format(str(exc)[:100])
            time.sleep(0.2)
    return heard


def main():
    parser = argparse.ArgumentParser(
        description="Measure mid-sentence language switching")
    parser.add_argument("--tts", action="store_true",
                        help="have OpenAI read the sentences")
    parser.add_argument("--report", help="use recordings from a problem report")
    parser.add_argument("--clips", help="a folder of wavs, in sentence order")
    parser.add_argument("--only", help="comma-separated variants to run")
    parser.add_argument("--out", help="write the full results as JSON")
    parser.add_argument("--limit", type=int,
                        help="only the first N sentences, for a cheap trial")
    parser.add_argument("--workspace",
                        help="reuse a folder of clips instead of paying for "
                             "the same synthesis twice")
    args = parser.parse_args()

    if args.limit:
        del SENTENCES[args.limit:]

    cfg = config_module.load()
    cfg["transcription"]["backend"] = "cloud"
    rate = int(cfg["audio"]["sample_rate"])
    backend = CloudBackend(cfg)
    if not backend.available():
        print("No OpenAI key found.")
        return 1

    workspace = (Path(args.workspace) if args.workspace
                 else Path(tempfile.mkdtemp(prefix="drill-")))
    if args.report:
        clips = clips_from_report(args.report, workspace)
        print("Using {} of your own recordings".format(len(clips)))
    elif args.clips:
        folder = sorted(Path(args.clips).glob("*.wav"))
        clips = [(SENTENCES[i][0], "yours", p)
                 for i, p in enumerate(folder) if i < len(SENTENCES)]
    elif args.tts:
        print("Having OpenAI read {} sentences, twice each:"
              .format(len(SENTENCES)))
        clips = synthesise(backend.api_key, workspace)
    else:
        parser.error("choose --tts, --report or --clips")

    table = variants(cfg)
    if args.only:
        wanted = [name.strip() for name in args.only.split(",")]
        table = [row for row in table if row[0] in wanted]

    read_pcm = _try_demo().read_pcm
    error_rate = _benchmark().error_rate
    expected = {name: text for name, text, _ in SENTENCES}

    results = {}
    for label, variant, quiet in table:
        print("\n{}".format(label), flush=True)
        heard = run(variant, clips, read_pcm, rate, quiet)
        results[label] = {}
        for (name, take), text in sorted(heard.items()):
            row = {"errors": error_rate(expected[name], text),
                   "script": script_loss(expected[name], text),
                   "heard": text}
            results[label]["{}/{}".format(name, take)] = row
            print("  {:<12} {:<6} words {:>4.0f}%  script {:>4.0f}%  {}".format(
                name, take, (row["errors"] or 0) * 100,
                (row["script"] or 0) * 100, text[:56]), flush=True)

    print("\n{:<18} {:>9} {:>9} {:>9} {:>9}".format(
        "variant", "words", "w/plain", "w/hard", "script"))
    for label, rows in results.items():
        def average(field, suffix=None):
            values = [r[field] for key, r in rows.items()
                      if r[field] is not None
                      and (suffix is None or key.endswith(suffix))]
            return sum(values) / len(values) if values else float("nan")
        print("{:<18} {:>8.0f}% {:>8.0f}% {:>8.0f}% {:>8.0f}%".format(
            label, average("errors") * 100,
            average("errors", "/plain") * 100,
            average("errors", "/hard") * 100, average("script") * 100))

    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False,
                                             indent=2), encoding="utf-8")
        print("\nwrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
