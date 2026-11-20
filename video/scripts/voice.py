r"""Speaks the film's lines, then times every word.

Two voices can speak them. ElevenLabs, the voice most reels like this use,
when its key is in %APPDATA%\HeySpeaky\elevenlabs.key; otherwise OpenAI,
with the key HeySpeaky itself uses. Neither key is ever printed. Each line
becomes public/vo/<id>.wav, and the local Whisper model writes
public/vo/words.json with when each word starts and ends, so the words on
screen land with the voice - whichever voice it is.

    python scripts\voice.py                       # OpenAI, lines not spoken yet
    python scripts\voice.py --again               # all of them
    python scripts\voice.py --eleven VOICE_ID     # ElevenLabs, all of them
    python scripts\voice.py --sample VOICE_ID ... # one line per voice, to choose
"""

import argparse
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
# The HeySpeaky repository: this folder's parent when it lives in video/,
# or wherever HEYSPEAKY_REPO points.
REPO = Path(os.environ.get("HEYSPEAKY_REPO") or HERE.parent)
sys.path.insert(0, str(REPO))

OUT = HERE / "public" / "vo"
ELEVEN_KEY = Path(os.path.expandvars(r"%APPDATA%\HeySpeaky\elevenlabs.key"))
OPENAI_VOICE = "ash"
OPENAI_STYLE = ("Delivery like a viral TikTok tech creator talking straight to camera: "
                "fast, punchy and conversational, confident, a hint of excitement and "
                "amusement, quick natural rhythm with short pauses for effect, emphasis "
                "on the key words. Not a radio announcer, not a commercial, not slow.")

LINES = [
    ("hook", "What if I told you... your dictation only speaks one language?"),
    ("three", "And you speak three."),
    ("this", "This is HeySpeaky."),
    ("hold", "Hold Control-Alt and just talk. Switch languages mid-sentence."),
    ("letgo", "Let go, and it types right where you were."),
    ("regular", "Regular dictation? This."),
    ("names", "Gets a name wrong? Teach it your names."),
    ("langs", "Ninety-seven languages. Yours go first."),
    ("free", "Free. Open source. Windows."),
    ("meta", "Oh, and this video? Every single frame is code."),
    ("cta", "Link's in the comments."),
]


def read_key(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return handle.read().strip()


def to_wav(data, path):
    """Whatever came back, as a 24 kHz mono wav whose header says its length."""
    raw = path.with_suffix(".raw")
    raw.write_bytes(data)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-c:a", "pcm_s16le",
                    "-ar", "24000", "-ac", "1", str(path)], check=True)
    raw.unlink()


def openai_speak(text, path):
    import httpx
    from heyspeaky import config as config_module
    from heyspeaky.transcribe import CloudBackend
    key = CloudBackend(config_module.load()).api_key
    if not key:
        raise SystemExit("No OpenAI key found where HeySpeaky keeps it")
    response = httpx.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": "Bearer " + key},
        json={"model": "gpt-4o-mini-tts", "voice": OPENAI_VOICE, "input": text,
              "instructions": OPENAI_STYLE, "response_format": "wav"},
        timeout=120)
    if response.status_code != 200:
        raise SystemExit("OpenAI answered {}: {}".format(response.status_code, response.text[:300]))
    to_wav(response.content, path)


def eleven_speak(voice, text, path, before="", after="", model="eleven_multilingual_v2"):
    import httpx
    response = httpx.post(
        "https://api.elevenlabs.io/v1/text-to-speech/{}".format(voice),
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": read_key(ELEVEN_KEY), "Content-Type": "application/json"},
        json={"text": text, "model_id": model, "previous_text": before or None,
              "next_text": after or None,
              "voice_settings": {"stability": 0.38, "similarity_boost": 0.8,
                                 "style": 0.35, "use_speaker_boost": True}},
        timeout=120)
    if response.status_code != 200:
        raise SystemExit("ElevenLabs answered {}: {}".format(response.status_code, response.text[:300]))
    to_wav(response.content, path)


def seconds(path):
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def time_words():
    from faster_whisper import WhisperModel
    # The large model: small heard "HeySpeaky" as "Hey, speaking".
    model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
    timing = {}
    for name, text in LINES:
        path = OUT / (name + ".wav")
        segments, _info = model.transcribe(str(path), language="en", word_timestamps=True)
        words = [{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
                 for segment in segments for w in segment.words]
        timing[name] = {"text": text, "seconds": round(seconds(path), 3), "words": words}
        print("{:8s} {:5.2f} s  {}".format(name, seconds(path), " ".join(
            "{}@{:.2f}".format(w["w"], w["start"]) for w in words)))
    (OUT / "words.json").write_text(json.dumps(timing, indent=1, ensure_ascii=False),
                                    encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--again", action="store_true")
    parser.add_argument("--eleven", metavar="VOICE_ID")
    parser.add_argument("--model", default="eleven_multilingual_v2")
    parser.add_argument("--sample", nargs="+", metavar="VOICE_ID")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    if args.sample:
        folder = HERE / "samples"
        folder.mkdir(exist_ok=True)
        text = LINES[0][1] + " " + LINES[1][1]
        for index, voice in enumerate(args.sample):
            path = folder / "eleven-{}.wav".format(index + 1)
            eleven_speak(voice, text, path, model=args.model)
            print(path.name, voice, "{:.2f} s".format(seconds(path)))
        return

    for index, (name, text) in enumerate(LINES):
        path = OUT / (name + ".wav")
        if path.exists() and not (args.again or args.eleven):
            continue
        if args.eleven:
            before = LINES[index - 1][1] if index else ""
            after = LINES[index + 1][1] if index + 1 < len(LINES) else ""
            eleven_speak(args.eleven, text, path, before, after, args.model)
        else:
            openai_speak(text, path)
        print("spoke {:8s} {:.2f} s".format(name, seconds(path)))
    time_words()


if __name__ == "__main__":
    main()
