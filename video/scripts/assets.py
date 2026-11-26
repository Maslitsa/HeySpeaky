r"""The film's sound effects, the levels that move Speaky's mouth, and
the app's icon and language names.

Every effect is arithmetic, like the app's own sounds in sound.py: nothing
is downloaded, nothing to license. tap and blip are the app's own voices.
levels.json holds, for the demo clip and every spoken line, the loudness
the Mono pill would show on each frame - the same meter curve and easing
the app puts a microphone through - so Speaky's bars move as the real pill
would for that audio.

    python scripts\assets.py
"""

import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
# The HeySpeaky repository: this folder's parent when it lives in video/,
# or wherever HEYSPEAKY_REPO points.
REPO = Path(os.environ.get("HEYSPEAKY_REPO") or HERE.parent)
sys.path.insert(0, str(REPO))

from heyspeaky import glass, languages, sound  # noqa: E402
from heyspeaky.mic import _level_from_chunk  # noqa: E402

PUBLIC = HERE / "public"
SFX = PUBLIC / "sfx"
RATE = 44100
FPS = 30
rng = np.random.default_rng(20261119)


def write(name, samples):
    """Stereo 16-bit; a mono array goes to both sides."""
    if samples.ndim == 1:
        samples = np.stack([samples, samples], axis=1)
    peak = np.abs(samples).max() or 1.0
    samples = samples / peak * 0.9
    data = np.round(samples * 32767).astype("<i2")
    with wave.open(str(SFX / (name + ".wav")), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(data.tobytes())


def t_of(seconds):
    return np.arange(int(seconds * RATE)) / float(RATE)


def lowpass(x, cutoff):
    """One pole, its cutoff allowed to change sample by sample."""
    cutoff = np.broadcast_to(cutoff, x.shape)
    weight = 1.0 - np.exp(-2.0 * np.pi * cutoff / RATE)
    out = np.empty_like(x)
    held = 0.0
    for i in range(len(x)):
        held += weight[i] * (x[i] - held)
        out[i] = held
    return out


def envelope(t, attack, release):
    up = np.clip(t / max(attack, 1e-6), 0, 1)
    down = np.clip((t[-1] - t) / max(release, 1e-6), 0, 1)
    return (0.5 - 0.5 * np.cos(np.pi * up)) * (0.5 - 0.5 * np.cos(np.pi * down))


def whoosh(seconds=0.5, low=300.0, high=4200.0, pan=True):
    t = t_of(seconds)
    share = t / t[-1]
    bell = np.sin(np.pi * share) ** 1.5
    noise = rng.uniform(-1, 1, len(t))
    body = lowpass(noise, low + (high - low) * bell)
    body -= lowpass(body, 120.0)
    body *= envelope(t, seconds * 0.45, seconds * 0.5)
    if not pan:
        return body
    left = body * (1.0 - 0.6 * share)
    right = body * (0.4 + 0.6 * share)
    return np.stack([left, right], axis=1)


def pop():
    t = t_of(0.14)
    freq = 520.0 + 900.0 * (1 - np.exp(-t / 0.012))
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    return np.sin(phase) * np.exp(-t / 0.035) * envelope(t, 0.002, 0.03)


def thud():
    t = t_of(0.32)
    freq = 55.0 + 70.0 * np.exp(-t / 0.03)
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    body = np.sin(phase) * np.exp(-t / 0.11)
    click = lowpass(rng.uniform(-1, 1, len(t)), 2500.0) * np.exp(-t / 0.006)
    return body + 0.5 * click


def glitch():
    t = t_of(0.42)
    out = np.zeros_like(t)
    step = int(0.028 * RATE)
    for start in range(0, len(t), step):
        piece = t[start:start + step] - t[start]
        freq = rng.choice([180, 240, 420, 880, 1320, 2100])
        square = np.sign(np.sin(2 * np.pi * freq * piece))
        crushed = np.round(rng.uniform(-1, 1, len(piece)) * 3) / 3
        mix = square * 0.6 + crushed * 0.4 if rng.random() < 0.7 else crushed
        out[start:start + step] = mix * rng.uniform(0.3, 1.0)
    return out * envelope(t, 0.005, 0.08) * 0.6


def sparkle():
    t = t_of(0.9)
    out = np.zeros_like(t)
    for index, freq in enumerate((2093.0, 2637.0, 3136.0, 3951.0, 4186.0)):
        start = int(index * 0.055 * RATE)
        piece = t[: len(t) - start]
        out[start:] += np.sin(2 * np.pi * freq * piece) * np.exp(-piece / 0.11)
    return out * 0.5


def riser():
    t = t_of(0.9)
    share = t / t[-1]
    noise = lowpass(rng.uniform(-1, 1, len(t)), 400 + 6000 * share ** 2)
    phase = 2 * np.pi * np.cumsum(180 + 700 * share ** 2) / RATE
    body = (noise * 0.6 + np.sin(phase) * 0.25) * share ** 2
    return body * envelope(t, 0.6, 0.03)


def typing():
    t = t_of(0.95)
    out = np.zeros_like(t)
    for index in range(14):
        start = int((index * 0.062 + rng.uniform(0, 0.015)) * RATE)
        length = int(0.03 * RATE)
        piece = t[:length]
        click = lowpass(rng.uniform(-1, 1, length), 3500.0) * np.exp(-piece / 0.005)
        tone = np.sin(2 * np.pi * rng.uniform(1700, 2300) * piece) * np.exp(-piece / 0.004)
        end = min(len(out), start + length)
        out[start:end] += (click + 0.3 * tone)[: end - start] * rng.uniform(0.5, 1.0)
    return out


def app_voice(name):
    data = np.array(sound._samples(sound.VOICES[name], 1.0), dtype=float)
    return data / 32767.0


def levels_for(path):
    """The pill's level on every frame of a wav: the meter, then the
    overlay's easing - quick up, slow down."""
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        raw = np.frombuffer(handle.readframes(handle.getnframes()),
                            dtype=np.int16)
    # Played at the owner's loudness, -19 dB at the peak, as the app hears.
    peak = np.abs(raw.astype(float)).max() / 32768.0
    gain = 10 ** (-19.0 / 20.0) / max(peak, 1e-6)
    samples = np.round(raw.astype(float) * gain).astype(np.int16)
    tick, chunk = 0.02, 512
    seconds = len(samples) / float(rate)
    shown, ticks = 0.0, []
    for index in range(int((seconds + 0.6) / tick)):
        end = int(index * tick * rate)
        level = 0.0
        if chunk <= end <= len(samples):
            level = _level_from_chunk(samples[end - chunk:end].tobytes())
        target = max(0.0, min(1.0, level)) ** 0.62
        shown += (target - shown) * (0.42 if target > shown else 0.16)
        ticks.append(shown)
    frames = int((seconds + 0.6) * FPS)
    return [round(ticks[min(len(ticks) - 1, int(f / FPS / tick))], 3)
            for f in range(frames)]


def main():
    SFX.mkdir(parents=True, exist_ok=True)
    # The demo sentence: Laura's take when it is here, the repository's clip
    # otherwise. Written as a plain 16-bit wav, which levels_for can read.
    take = HERE / "takes" / "laura-demo.mp3"
    source = take if take.exists() else REPO / "demo" / "four_languages.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-ac", "1", "-ar", "44100",
                    "-c:a", "pcm_s16le", str(PUBLIC / "clip.wav")], check=True)
    write("whoosh", whoosh())
    write("swish", whoosh(0.28, 900.0, 7000.0))
    write("pop", pop())
    write("thud", thud())
    write("glitch", glitch())
    write("sparkle", sparkle())
    write("riser", riser())
    write("typing", typing())
    write("tap", app_voice("tap"))
    write("blip", app_voice("blip"))
    levels = {"clip": levels_for(PUBLIC / "clip.wav")}
    for path in sorted((PUBLIC / "vo").glob("*.wav")):
        levels[path.stem] = levels_for(path)
    (PUBLIC / "levels.json").write_text(json.dumps(levels), encoding="utf-8")
    glass.app_icon(512).save(PUBLIC / "icon.png")
    names = [languages.name(code) for code in languages.catalog([])]
    (HERE / "src" / "languages.json").write_text(
        json.dumps(names, ensure_ascii=False), encoding="utf-8")
    print("sfx:", ", ".join(sorted(p.stem for p in SFX.glob("*.wav"))))
    print("levels:", ", ".join("{} {}".format(k, len(v)) for k, v in levels.items()))


if __name__ == "__main__":
    main()
