r"""Stand-in music for the dark film, written as numbers: A minor at 120 beats
a minute, a pulsing sub bass, a kick, offbeat hats, a pad and a little
arpeggio - the shape of a tech-trailer bed. Replaced by Lyria once there
is an OpenRouter key; until then the film is never silent between lines.

    python scripts\music_dark.py      # writes public/music_dark.wav
"""

import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
RATE = 44100
SECONDS = 60.0
BEAT = 0.5
rng = np.random.default_rng(11)

# (bass root, pad notes) per two bars: Am, F, C, G.
CHORDS = [
    (55.00, [220.00, 261.63, 329.63]),
    (43.65, [174.61, 220.00, 261.63]),
    (65.41, [196.00, 261.63, 329.63]),
    (49.00, [196.00, 246.94, 293.66]),
]
ARP = [440.00, 523.25, 659.25, 783.99, 880.00, 659.25, 523.25, 587.33]


def t_of(seconds):
    return np.arange(int(seconds * RATE)) / RATE


def put(out, samples, at, gain=1.0, pan=0.0):
    start = int(at * RATE)
    end = min(len(out), start + len(samples))
    if end <= start:
        return
    piece = samples[: end - start] * gain
    out[start:end, 0] += piece * (1 - pan)
    out[start:end, 1] += piece * (1 + pan)


def kick():
    t = t_of(0.35)
    freq = 45 + 90 * np.exp(-t / 0.035)
    return np.sin(2 * np.pi * np.cumsum(freq) / RATE) * np.exp(-t / 0.16)


def hat():
    t = t_of(0.06)
    noise = rng.uniform(-1, 1, len(t))
    bright = np.diff(noise, prepend=0)
    return bright * np.exp(-t / 0.012)


def bass(freq, seconds):
    t = t_of(seconds)
    body = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2 * t)
    return body * np.exp(-t / 0.18) * np.minimum(1, t / 0.004)


def pad(notes, seconds):
    t = t_of(seconds)
    out = np.zeros_like(t)
    for f in notes:
        for detune in (-0.004, 0.0, 0.004):
            out += np.sin(2 * np.pi * f * (1 + detune) * t + rng.uniform(0, 6))
            out += 0.25 * np.sin(2 * np.pi * f * 2 * (1 + detune) * t)
    env = np.minimum(1, t / 0.8) * np.minimum(1, (seconds - t) / 0.6)
    return out * env / (len(notes) * 3)


def pluck(freq):
    t = t_of(0.4)
    return (np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 3 * t) * np.exp(-t / 0.02)) * np.exp(-t / 0.12)


def main():
    out = np.zeros((int(SECONDS * RATE), 2))
    bar = BEAT * 4
    k, h = kick(), hat()
    beat = 0
    while beat * BEAT < SECONDS:
        at = beat * BEAT
        chord = CHORDS[int(at // (bar * 2)) % len(CHORDS)]
        if beat % 8 == 0:
            put(out, pad(chord[1], bar * 2 + 0.6), at, 0.22)
        for eighth in (0, 1):
            put(out, bass(chord[0], BEAT / 2), at + eighth * BEAT / 2, 0.55 if eighth == 0 else 0.35)
        if at >= bar:
            put(out, k, at, 0.8)
            put(out, h, at + BEAT / 2, 0.18, pan=0.3 if beat % 2 else -0.3)
        if at >= bar * 2:
            for s in range(4):
                note = ARP[(beat * 4 + s) % len(ARP)]
                put(out, pluck(note), at + s * BEAT / 4, 0.07, pan=0.4 * np.sin(beat + s))
        beat += 1
    # A little room: a short, soft echo on everything.
    delay = int(0.375 * RATE)
    out[delay:] += out[:-delay] * 0.22
    out /= np.abs(out).max() or 1
    out *= 0.85
    data = np.round(out * 32767).astype("<i2")
    with wave.open(str(HERE / "public" / "music_dark.wav"), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(data.tobytes())
    print("music_dark.wav", SECONDS, "s")


if __name__ == "__main__":
    main()
