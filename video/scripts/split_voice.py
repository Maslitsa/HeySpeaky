r"""Cuts one narration take into the film's lines, then times every word.

A voice read in one take sounds like one person telling a story; read a
line at a time, it sounds like eleven announcements. So the whole script is
spoken once (ElevenLabs, Laura), and this finds where each line begins by
its first words, cuts there in the silence between, and writes
public/vo/<line>.wav and public/vo/words.json - the same files voice.py
writes, so the film takes either.

    python scripts\split_voice.py TAKE.mp3
"""

import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "public" / "vo"

sys.path.insert(0, str(HERE / "scripts"))
from voice import LINES  # noqa: E402

# How each line is recognised in the transcript: the first word or two it
# starts with, as Whisper may write them.
ANCHORS = {
    "hook": ["what"],
    "three": ["and you"],
    "this": ["this is"],
    "hold": ["hold"],
    "letgo": ["let"],
    "regular": ["regular"],
    "names": ["gets", "get"],
    "langs": ["97", "ninety"],
    "free": ["free"],
    "meta": ["oh"],
    "cta": ["link", "links"],
}


def norm(word):
    return re.sub(r"[^a-z0-9]", "", word.lower())


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    take = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    full = OUT / "_take.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(take), "-ac", "1", "-ar", "44100",
                    "-c:a", "pcm_s16le", str(full)], check=True)

    from faster_whisper import WhisperModel
    model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(full), language="en", word_timestamps=True)
    words = [(w.word.strip(), w.start, w.end) for s in segments for w in s.words]
    print(" ".join("{}@{:.2f}".format(w, a) for w, a, _ in words))

    # Each line starts at the first match of its anchor after the previous line.
    starts = []
    at = 0
    for name, _text in LINES:
        found = None
        for i in range(at, len(words)):
            for anchor in ANCHORS[name]:
                parts = anchor.split()
                got = [norm(w[0]) for w in words[i:i + len(parts)]]
                if got == [norm(p) for p in parts]:
                    found = i
                    break
            if found is not None:
                break
        if found is None:
            raise SystemExit("could not find where '{}' starts".format(name))
        starts.append(found)
        at = found + 1

    with wave.open(str(full), "rb") as handle:
        rate = handle.getframerate()
        audio = handle.readframes(handle.getnframes())
    total = len(audio) // 2 / rate

    timing = {}
    for index, (name, text) in enumerate(LINES):
        first = starts[index]
        last = (starts[index + 1] - 1) if index + 1 < len(LINES) else len(words) - 1
        begin = words[first][1]
        end = words[last][2]
        # Cut in the middle of the silence on either side, never into a word.
        before = words[first - 1][2] if first > 0 else 0.0
        after = words[last + 1][1] if last + 1 < len(words) else total
        cut_in = max(before, begin - 0.12)
        cut_out = min(after, end + 0.25)
        a, b = int(cut_in * rate), int(cut_out * rate)
        piece = audio[a * 2:b * 2]
        path = OUT / (name + ".wav")
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(piece)
        # A 6 ms fade at each end, so a cut never clicks.
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-af",
                        "afade=t=in:d=0.006,areverse,afade=t=in:d=0.02,areverse",
                        str(path) + ".tmp.wav"], check=True)
        os.replace(str(path) + ".tmp.wav", path)
        line_words = [{"w": w, "start": round(s - cut_in, 3), "end": round(e - cut_in, 3)}
                      for w, s, e in words[first:last + 1]]
        timing[name] = {"text": text, "seconds": round(cut_out - cut_in, 3), "words": line_words}
        print("{:8s} {:5.2f} s  {}".format(name, cut_out - cut_in, " ".join(w["w"] for w in line_words)))
    full.unlink()
    (OUT / "words.json").write_text(json.dumps(timing, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
