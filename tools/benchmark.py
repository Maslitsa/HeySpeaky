r"""Which speech model should HeySpeaky use? Measure it, do not guess.

Runs the same recordings through OpenAI and through several local models, and
prints what each one heard and how long it took. Where the right answer is
known (the demo clip), it also counts the errors.

    .venv\Scripts\python.exe tools\benchmark.py
    .venv\Scripts\python.exe tools\benchmark.py --report path\to\report.zip
    .venv\Scripts\python.exe tools\benchmark.py --models base,small --no-cloud

A problem report holds the last recordings of whoever made it, so --report
reads them straight out of the ZIP. Nothing is copied into the project.
"""

import argparse
import copy
import importlib.util
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from heyspeaky import config as config_module               # noqa: E402
from heyspeaky.transcribe import CloudBackend, LocalBackend  # noqa: E402

DEMO = ROOT / "demo" / "four_languages.wav"

# What the demo clip says, so its errors can be counted rather than judged.
# Written the way the clip sounds, in one alphabet, because a word error rate
# compares words and not scripts.
DEMO_REFERENCE = ("I already sent the invoice, "
                  "aber ich warte noch auf eine Antwort, "
                  "но клиент до сих пор не ответил, "
                  "сондықтан ертең қоңырау шаламын.")

MODEL_LOAD_TIMEOUT = 900.0


def _try_demo():
    """Borrows the wav reader from tools/try_demo.py rather than copying it."""
    spec = importlib.util.spec_from_file_location(
        "try_demo", ROOT / "tools" / "try_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalise(text):
    keep = []
    for char in text.lower():
        keep.append(char if (char.isalnum() or char.isspace()) else " ")
    return "".join(keep).split()


def error_rate(reference, heard):
    """Word error rate: how much of the reference came back wrong."""
    want, got = normalise(reference), normalise(heard)
    if not want:
        return None
    previous = list(range(len(got) + 1))
    for i, want_word in enumerate(want, 1):
        current = [i]
        for j, got_word in enumerate(got, 1):
            cost = 0 if want_word == got_word else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + cost))
        previous = current
    return previous[-1] / float(len(want))


def clips_from_report(path, into):
    """Pulls recordings out of a problem report ZIP into a temporary folder."""
    found = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name.startswith("recordings/") and name.endswith(".wav"):
                target = Path(into) / Path(name).name
                target.write_bytes(archive.read(name))
                found.append(target)
    return found


def run_cloud(cfg, clips, read_pcm):
    results = {}
    backend = CloudBackend(cfg)
    if not backend.available():
        print("  no OpenAI key found, skipping the cloud", flush=True)
        return results
    for clip in clips:
        pcm, _ = read_pcm(clip, int(cfg["audio"]["sample_rate"]))
        started = time.monotonic()
        try:
            text = backend.transcribe(pcm, "")
        except Exception as exc:
            text = "FAILED: {}".format(str(exc)[:120])
        results[clip.name] = (text, time.monotonic() - started)
        print("  {:<12} {:.1f}s".format(clip.name, results[clip.name][1]),
              flush=True)
    return results


def run_local(cfg, model_name, clips, read_pcm):
    """Loads one local model and runs every clip through it."""
    from heyspeaky.engine import TranscriptionEngine

    results = {}
    local_cfg = copy.deepcopy(cfg)
    local_cfg["model"]["final"] = model_name
    engine = TranscriptionEngine(
        local_cfg,
        on_ready=lambda *a: None,
        on_error=lambda *a: None,
        on_auto_stop=lambda *a: None,
    )
    engine.start()
    deadline = time.monotonic() + MODEL_LOAD_TIMEOUT
    while not engine.ready and time.monotonic() < deadline:
        time.sleep(0.2)
    if not engine.ready:
        engine.shutdown()
        print("  {} did not load in time".format(model_name), flush=True)
        return results
    backend = LocalBackend(engine, local_cfg)
    try:
        for clip in clips:
            pcm, _ = read_pcm(clip, int(local_cfg["audio"]["sample_rate"]))
            started = time.monotonic()
            try:
                text = backend.transcribe(pcm, "")
            except Exception as exc:
                text = "FAILED: {}".format(str(exc)[:120])
            results[clip.name] = (text, time.monotonic() - started)
            print("  {:<12} {:.1f}s".format(clip.name, results[clip.name][1]),
                  flush=True)
    finally:
        import logging
        logging.getLogger("realtimestt").setLevel(logging.CRITICAL)
        engine.shutdown()
    return results


def report(clips, runs, out):
    lines = ["# Which model hears best", ""]
    for clip in clips:
        lines.append("## {}".format(clip.name))
        lines.append("")
        lines.append("| engine | seconds | errors | what it heard |")
        lines.append("| --- | --- | --- | --- |")
        for engine_name, results in runs:
            if clip.name not in results:
                continue
            text, seconds = results[clip.name]
            rate = ""
            if clip.name == DEMO.name:
                value = error_rate(DEMO_REFERENCE, text)
                if value is not None:
                    rate = "{:.0f}%".format(value * 100)
            clean = text.replace("|", "/").replace("\n", " ")
            lines.append("| {} | {:.1f} | {} | {} |".format(
                engine_name, seconds, rate, clean))
        lines.append("")
    text = "\n".join(lines)
    print()
    print(text)
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print("saved to {}".format(out))


def main():
    parser = argparse.ArgumentParser(description="Compare speech models")
    parser.add_argument("--report", help="problem report ZIP to take clips from")
    parser.add_argument("--models", default="base,small,large-v3-turbo")
    parser.add_argument("--no-cloud", action="store_true")
    parser.add_argument("--out", help="write the table to this file")
    args = parser.parse_args()

    cfg = config_module.load()
    read_pcm = _try_demo().read_pcm

    with tempfile.TemporaryDirectory() as tmp:
        clips = [DEMO] if DEMO.exists() else []
        if args.report:
            clips += clips_from_report(args.report, tmp)
        if not clips:
            raise SystemExit("no clips to run")

        runs = []
        if not args.no_cloud:
            print("OpenAI:", flush=True)
            runs.append(("OpenAI", run_cloud(cfg, clips, read_pcm)))
        for model_name in [m.strip() for m in args.models.split(",") if m.strip()]:
            print("local {}:".format(model_name), flush=True)
            runs.append(("local " + model_name,
                         run_local(cfg, model_name, clips, read_pcm)))
        report(clips, runs, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
