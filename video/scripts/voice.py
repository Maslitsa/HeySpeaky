r"""Speaks the film's lines with OpenAI, then times every word.

The key is the one HeySpeaky itself uses, found the way the app finds it,
and it is never printed. Each line becomes public/vo/<id>.wav; the local
Whisper model then writes public/vo/words.json with when each word starts
and ends, so the words on screen land with the voice.

    python scripts\voice.py            # only lines not spoken yet
    python scripts\voice.py --again    # all of them
"""

import argparse
import json
import os
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
# The HeySpeaky repository: this folder's parent when it lives in video/,
# or wherever HEYSPEAKY_REPO points.
REPO = Path(os.environ.get("HEYSPEAKY_REPO") or HERE.parent)
sys.path.insert(0, str(REPO))

from heyspeaky import config as config_module  # noqa: E402
from heyspeaky.transcribe import CloudBackend  # noqa: E402

OUT = HERE / "public" / "vo"
MODEL = "gpt-4o-mini-tts"
VOICE = "marin"
STYLE = ("A warm, bright narrator for a playful forty-second product film. "
         "Confident and friendly, a smile in the voice, crisp consonants, "
         "short natural pauses at full stops. Not salesy, not an announcer.")

LINES = [
    ("hook", "You think in three languages."),
    ("one", "Your dictation hears one."),
    ("mess", "Everything else comes out like this."),
    ("meet", "Meet HeySpeaky."),
    ("hold", "Hold Control and Alt, and just talk."),
    ("letgo", "Let go, and it types right where you were."),
    ("names", "Teach it the names you use."),
    ("langs", "Ninety-seven languages. Yours go first."),
    ("logo", "HeySpeaky. Talk the way you think."),
    ("meta", "Oh, and this video? Every single frame is code."),
]


def speak(key, text, path):
    import httpx
    response = httpx.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": "Bearer " + key},
        json={"model": MODEL, "voice": VOICE, "input": text,
              "instructions": STYLE, "response_format": "wav"},
        timeout=120)
    if response.status_code != 200:
        raise SystemExit("OpenAI answered {}: {}".format(
            response.status_code, response.text[:300]))
    # OpenAI streams the wav, so its header gives no length; rewritten by
    # ffmpeg it says how long it really is.
    raw = path.with_suffix(".raw.wav")
    raw.write_bytes(response.content)
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw),
                    "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1",
                    str(path)], check=True)
    raw.unlink()


def seconds(path):
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--again", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    key = CloudBackend(config_module.load()).api_key
    if not key:
        raise SystemExit("No OpenAI key found where HeySpeaky keeps it")
    for name, text in LINES:
        path = OUT / (name + ".wav")
        if path.exists() and not args.again:
            continue
        speak(key, text, path)
        print("spoke {:6s} {:.2f} s".format(name, seconds(path)))

    from faster_whisper import WhisperModel
    # The large model: small heard "HeySpeaky" as "Hey, speaking".
    model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
    timing = {}
    for name, text in LINES:
        path = OUT / (name + ".wav")
        segments, _info = model.transcribe(str(path), language="en",
                                           word_timestamps=True)
        words = [{"w": w.word.strip(), "start": round(w.start, 3),
                  "end": round(w.end, 3)}
                 for segment in segments for w in segment.words]
        timing[name] = {"text": text, "seconds": round(seconds(path), 3),
                        "words": words}
        print("{:6s} {:5.2f} s  {}".format(
            name, seconds(path),
            " ".join("{}@{:.2f}".format(w["w"], w["start"]) for w in words)))
    (OUT / "words.json").write_text(json.dumps(timing, indent=1,
                                               ensure_ascii=False),
                                    encoding="utf-8")


if __name__ == "__main__":
    main()
