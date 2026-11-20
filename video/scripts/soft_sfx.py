r"""Soft sound effects, written as numbers.

The owner found the first set too sharp: a thud, a digital glitch, hard key
clicks. Everything here starts slowly - a raised-cosine attack of 8 ms or
more, so there is never a click - and lives below 6 kHz, so nothing hisses.

    python scripts\soft_sfx.py      # writes public/sfx/soft-*.wav
"""

import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "public" / "sfx"
RATE = 44100
rng = np.random.default_rng(7)


def t_of(seconds):
    return np.arange(int(seconds * RATE)) / RATE


def lowpass(x, cutoff):
    cutoff = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    weight = 1.0 - np.exp(-2.0 * np.pi * cutoff / RATE)
    out = np.empty_like(x)
    held = 0.0
    for i in range(len(x)):
        held += weight[i] * (x[i] - held)
        out[i] = held
    return out


def rise(t, seconds):
    """A raised-cosine attack: no corner, so no click."""
    p = np.clip(t / max(seconds, 1e-6), 0, 1)
    return 0.5 - 0.5 * np.cos(np.pi * p)


def fall(t, total, seconds):
    p = np.clip((total - t) / max(seconds, 1e-6), 0, 1)
    return 0.5 - 0.5 * np.cos(np.pi * p)


def write(name, left, right=None, peak=0.5):
    right = left if right is None else right
    data = np.stack([left, right], axis=1)
    data = data / (np.abs(data).max() or 1) * peak
    raw = np.round(data * 32767).astype("<i2")
    with wave.open(str(OUT / ("soft-" + name + ".wav")), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(raw.tobytes())


def whoosh(seconds=1.0):
    t = t_of(seconds)
    share = t / t[-1]
    bell = np.sin(np.pi * share) ** 2
    noise = rng.uniform(-1, 1, len(t))
    body = lowpass(noise, 250 + 1700 * bell)
    body -= lowpass(body, 90)
    body = lowpass(body, 3500)
    env = bell * rise(t, 0.08) * fall(t, seconds, 0.12)
    return body * env * (1 - 0.5 * share), body * env * (0.5 + 0.5 * share)


def pop():
    t = t_of(0.32)
    freq = 420 + 260 * (1 - np.exp(-t / 0.03))
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    body = np.sin(phase) + 0.25 * np.sin(2 * phase)
    env = rise(t, 0.012) * np.exp(-t / 0.075)
    return body * env, body * env


def bloom():
    t = t_of(2.2)
    out = np.zeros_like(t)
    for f, gain, start in ((1046.5, 0.8, 0.0), (1318.5, 0.6, 0.03), (1568.0, 0.5, 0.06), (2093.0, 0.25, 0.09)):
        local = np.clip(t - start, 0, None)
        out += gain * np.sin(2 * np.pi * f * local * (1 + 0.0015 * np.sin(2 * np.pi * 5 * local))) * rise(local, 0.04) * np.exp(-local / 0.7) * (t >= start)
    air = lowpass(rng.uniform(-1, 1, len(t)), 2500) * rise(t, 0.3) * np.exp(-t / 0.5) * 0.15
    total = (out + air) * fall(t, 2.2, 0.3)
    return total * 0.9, np.roll(total, int(0.012 * RATE))


def swell(seconds=1.1):
    t = t_of(seconds)
    share = t / t[-1]
    noise = rng.uniform(-1, 1, len(t))
    body = lowpass(noise, 200 + 2600 * share ** 2)
    body -= lowpass(body, 80)
    tone = np.sin(2 * np.pi * np.cumsum(220 + 440 * share ** 2) / RATE) * 0.3
    env = share ** 2.2 * fall(t, seconds, 0.09)
    total = (body + tone) * env
    return total, total


def boom():
    t = t_of(1.2)
    freq = 46 + 30 * np.exp(-t / 0.08)
    body = np.sin(2 * np.pi * np.cumsum(freq) / RATE)
    env = rise(t, 0.03) * np.exp(-t / 0.35)
    body = lowpass(body * env, 400)
    return body, body


def key():
    t = t_of(0.12)
    noise = lowpass(rng.uniform(-1, 1, len(t)), 1500)
    body = np.sin(2 * np.pi * 170 * t) * 0.6 + noise * 0.4
    env = rise(t, 0.008) * np.exp(-t / 0.022)
    return body * env, body * env


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    write("whoosh", *whoosh(), peak=0.45)
    write("pop", *pop(), peak=0.45)
    write("bloom", *bloom(), peak=0.4)
    write("swell", *swell(), peak=0.4)
    write("boom", *boom(), peak=0.55)
    write("key", *key(), peak=0.35)
    print("soft sfx:", ", ".join(sorted(p.stem for p in OUT.glob("soft-*.wav"))))


if __name__ == "__main__":
    main()
