r"""The film's music, written as numbers: D minor at 120 beats a minute,
laid on the film's own timeline so that what happens on screen lands on a
beat.

Dark and nearly still under the opening question. It opens up when the name
appears, and a soft pulse runs under "hold Ctrl+Alt". Under the
four-language sentence it thins to a pad: anything with an edge there took
the end off the last Kazakh word when HeySpeaky listened to the mix. It
rises after "let go", drops when regular dictation's answer slams in, lifts
again for the 97 languages, and ends on one held chord under the last line.

    python scripts\music_dark.py      # writes public/music_dark.wav

The timeline is worked out from public/vo/words.json the way src/data.ts
works it out, so a new voice moves the music with it. Keep AFTER and
CLIP_SECONDS here in step with src/data.ts.
"""

import json
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

HERE = Path(__file__).resolve().parent.parent
RATE = 44100
SECONDS = 46.0
N = int(SECONDS * RATE)
BEAT = 0.5
BAR = BEAT * 4
rng = np.random.default_rng(7)

AFTER = {"hook": 0.15, "three": 0.4, "this": 0.5, "hold": 0.25, "clip": 0.3, "letgo": 0.5,
         "regular": 1.0, "names": 1.25, "langs": 0.45, "free": 0.5, "meta": 0.3, "cta": 1.1}
ORDER = ["hook", "three", "this", "hold", "clip", "letgo", "regular", "names", "langs", "free", "meta", "cta"]
CLIP_SECONDS = 8.72


def timeline():
    words = json.loads((HERE / "public" / "vo" / "words.json").read_text(encoding="utf-8"))
    at, t = {}, 0.35
    for item in ORDER:
        at[item] = t
        if item == "clip":
            t += CLIP_SECONDS + AFTER["clip"]
        else:
            w = words[item]["words"]
            t += (w[-1]["end"] + 0.1 if w else words[item]["seconds"]) + AFTER[item]
    at["end"] = t
    return at


AT = timeline()
DROP = AT["regular"] - 0.12          # regular dictation's answer slams in (SLAB_IN)
REVEAL = DROP + round((AT["this"] - DROP) / BAR) * BAR
HOLD = DROP + np.ceil((AT["hold"] - DROP) / BEAT) * BEAT
CLIP_IN = AT["clip"]
CLIP_OUT = CLIP_IN + CLIP_SECONDS
BUILD = DROP + np.ceil((CLIP_OUT + 0.05 - DROP) / BEAT) * BEAT
LIFT = DROP + round((AT["langs"] - DROP) / BAR) * BAR
FINAL = DROP + round((AT["cta"] - DROP) / BAR) * BAR
GAP = 0.08                           # silence just before the drop

# Dm, Bb, F, C, one a bar, with Dm on the drop. Pad voicing, bass root, arpeggio.
CHORDS = [
    ([146.83, 220.00, 293.66, 349.23], 73.42, [293.66, 349.23, 440.00, 587.33]),
    ([116.54, 174.61, 233.08, 293.66], 58.27, [293.66, 349.23, 466.16, 587.33]),
    ([174.61, 220.00, 261.63, 349.23], 87.31, [261.63, 349.23, 440.00, 523.25]),
    ([130.81, 196.00, 261.63, 329.63], 65.41, [261.63, 329.63, 392.00, 523.25]),
]
LAST = [146.83, 220.00, 329.63, 349.23, 440.00]      # Dm add9, held to the end


def chord_at(t):
    return CHORDS[int(np.floor((t - DROP) / BAR + 1e-6)) % 4]


# ---- sounds -----------------------------------------------------------------

def tt(seconds):
    return np.arange(int(seconds * RATE)) / RATE


def env(n, attack, release):
    t = np.arange(n) / RATE
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    r = np.clip((n / RATE - t) / max(release, 1e-4), 0, 1)
    return np.sin(a * np.pi / 2) ** 2 * np.sin(r * np.pi / 2) ** 2


def saw(freq, n, phase):
    """A band-limited saw (polyBLEP), so the pad does not alias."""
    dt = freq / RATE
    ph = (phase + dt * np.arange(n)) % 1.0
    s = 2.0 * ph - 1.0
    m = ph < dt
    x = ph[m] / dt
    s[m] -= x + x - x * x - 1.0
    m = ph > 1.0 - dt
    x = (ph[m] - 1.0) / dt
    s[m] -= x * x + x + x + 1.0
    return s


def pad_note(freq, seconds, attack, release, voices=5, spread=0.007):
    n = int(seconds * RATE)
    out = np.zeros((n, 2))
    for i in range(voices):
        d = (i - (voices - 1) / 2) / ((voices - 1) / 2)
        s = saw(freq * (1 + spread * d), n, rng.uniform())
        pan = 0.7 * d
        out[:, 0] += s * np.sqrt((1 - pan) / 2)
        out[:, 1] += s * np.sqrt((1 + pan) / 2)
    return out * env(n, attack, release)[:, None] / voices


def pluck(freq, bright=1.0, seconds=0.7):
    t = tt(seconds)
    out = np.zeros(len(t))
    for h in range(1, 9):
        if freq * h > 9000:
            break
        out += np.sin(2 * np.pi * freq * h * t) / h * np.exp(-t * (5 + 11 * h / bright))
    return out * np.clip(t / 0.002, 0, 1)


def bass_note(freq, seconds, decay=0.35):
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    s = 0.55 * saw(freq, n, 0.0) + 0.8 * np.sin(2 * np.pi * freq * t)
    return s * np.clip(t / 0.003, 0, 1) * np.exp(-t / decay) * np.clip((seconds - t) / 0.02, 0, 1)


def kick():
    t = tt(0.45)
    f = 48 + 115 * np.exp(-t / 0.04)
    body = np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t / 0.22)
    click = rng.standard_normal(len(t)) * np.exp(-t / 0.002) * 0.12
    return np.tanh(1.6 * (body + click))


def clap():
    t = tt(0.35)
    band = sosfilt(butter(2, [900, 3200], "band", fs=RATE, output="sos"), rng.standard_normal(len(t)))
    e = np.zeros(len(t))
    for off in (0.0, 0.011, 0.022):
        i = int(off * RATE)
        e[i:] += 0.7 * np.exp(-t[: len(t) - i] / 0.008)
    e += np.exp(-np.maximum(t - 0.022, 0) / 0.1) * (t >= 0.022)
    return band * e


def snare():
    t = tt(0.25)
    band = sosfilt(butter(2, [1200, 6000], "band", fs=RATE, output="sos"), rng.standard_normal(len(t)))
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05)
    return (band * np.exp(-t / 0.06) + 0.5 * tone) * np.clip(t / 0.001, 0, 1)


def hat(decay=0.03):
    t = tt(decay * 6)
    hp = sosfilt(butter(2, 7500, "high", fs=RATE, output="sos"), rng.standard_normal(len(t)))
    return hp * np.exp(-t / decay)


def boom(seconds=2.2):
    t = tt(seconds)
    f = 42 + 26 * np.exp(-t / 0.3)
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t / 0.75) * np.clip(t / 0.003, 0, 1)


def crash(seconds=2.4):
    t = tt(seconds)
    hp = sosfilt(butter(2, 3500, "high", fs=RATE, output="sos"), rng.standard_normal((len(t), 2)), axis=0)
    return hp * np.exp(-t / 0.6)[:, None]


def shimmer(notes, seconds=3.0):
    t = tt(seconds)
    out = np.zeros(len(t))
    for f in notes:
        for octave in (2, 4):
            out += np.sin(2 * np.pi * f * octave * t * (1 + 0.002 * np.sin(2 * np.pi * 5 * t)))
    return out * np.clip(t / 0.03, 0, 1) * np.exp(-t / 0.9) / (2 * len(notes))


def sweep(x, points, kind="low", order=2, block=256):
    """Filter x with a cutoff that moves through (seconds, hz) points."""
    times = np.array([p[0] for p in points], float)
    hz = np.log(np.array([p[1] for p in points], float))
    zi = np.zeros(((order + 1) // 2, 2) + x.shape[1:])
    out = np.empty_like(x)
    for i in range(0, len(x), block):
        fc = float(np.exp(np.interp((i + block / 2) / RATE, times, hz)))
        sos = butter(order, min(max(fc, 20.0), RATE * 0.45), kind, fs=RATE, output="sos")
        out[i:i + block], zi = sosfilt(sos, x[i:i + block], axis=0, zi=zi)
    return out


def riser(seconds):
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    noise = sweep(rng.standard_normal((n, 2)), [(0, 500), (seconds, 9000)])
    return noise * ((t / seconds) ** 2.5)[:, None]


# ---- placing them -------------------------------------------------------------

def put(bus, samples, at, gain=1.0, pan=0.0):
    start = int(round(at * RATE))
    if start >= len(bus):
        return
    if samples.ndim == 1:
        samples = np.stack([samples * np.sqrt(1 - pan), samples * np.sqrt(1 + pan)], axis=1)
    end = min(len(bus), start + len(samples))
    bus[start:end] += samples[: end - start] * gain


def curve(points):
    """A gain over the whole track through (seconds, gain) points."""
    t = np.arange(N) / RATE
    return np.interp(t, [p[0] for p in points], [p[1] for p in points])[:, None]


def reverb(x, rt60=2.6, length=3.4, predelay=0.025):
    n = int(length * RATE)
    t = np.arange(n) / RATE
    ir = rng.standard_normal((n, 2)) * np.exp(-6.91 * t / rt60)[:, None]
    ir = sosfilt(butter(1, 4500, "low", fs=RATE, output="sos"), ir, axis=0)
    ir = np.vstack([np.zeros((int(predelay * RATE), 2)), ir])
    ir /= np.sqrt((ir ** 2).sum(axis=0))
    x = sosfilt(butter(1, 220, "high", fs=RATE, output="sos"), x, axis=0)
    return np.stack([fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in (0, 1)], axis=1)


def pingpong(x, delay=BEAT * 0.75, feedback=0.35, taps=6):
    out = x.copy()
    d = int(delay * RATE)
    mono = x.mean(axis=1)
    for k in range(1, taps + 1):
        out[k * d:, k % 2] += mono[: len(x) - k * d] * feedback ** k
    return out


def beats(start, stop, step=BEAT):
    k = np.ceil((start - DROP) / step - 1e-6)
    out = []
    while DROP + k * step < stop - 1e-6:
        out.append(DROP + k * step)
        k += 1
    return out


def main():
    bus = {name: np.zeros((N, 2)) for name in ("pad", "drone", "arp", "bass", "drums", "fx", "wet")}

    # The pad: one long Dm under the question, then a chord a bar, then the last chord.
    for f in CHORDS[0][0]:
        put(bus["pad"], pad_note(f, REVEAL + 0.3, 3.0, 0.5), 0)
    for at in beats(REVEAL, FINAL, BAR):
        for f in chord_at(at + 0.01)[0]:
            put(bus["pad"], pad_note(f, BAR + 0.35, 0.05 if at == REVEAL else 0.2, 0.4), at)
    for f in LAST:
        put(bus["pad"], pad_note(f, SECONDS - FINAL, 0.04, 3.5), FINAL)
    pad = sweep(bus["pad"], [
        (0, 220), (REVEAL - 0.05, 900), (REVEAL + 0.6, 2600), (REVEAL + 4, 1400), (CLIP_IN - 0.2, 1400),
        (CLIP_IN + 0.3, 800), (CLIP_OUT, 800), (DROP - GAP, 5000), (DROP, 2600), (LIFT - 0.1, 2600),
        (LIFT + 0.4, 4200), (FINAL, 4200), (FINAL + 0.2, 3200), (SECONDS, 900)])
    pad *= curve([(0, 0.0), (3.0, 0.55), (REVEAL, 0.7), (REVEAL + 0.3, 1.0), (CLIP_IN - 0.3, 0.85),
                  (CLIP_IN, 0.55), (CLIP_OUT, 0.55), (DROP - GAP, 1.0), (DROP, 0.8), (FINAL, 0.8),
                  (FINAL + 0.05, 1.0), (SECONDS, 1.0)])

    # A low drone and some air under the opening, gone at the drop.
    t = np.arange(N) / RATE
    drone = (np.sin(2 * np.pi * 73.42 * t) + 0.4 * np.sin(2 * np.pi * 110 * t) + 0.25 * np.sin(2 * np.pi * 146.83 * t))
    drone *= np.clip(t / 2.5, 0, 1) * (t < DROP - GAP)
    bus["drone"] += np.stack([drone, drone], axis=1)
    air = sweep(rng.standard_normal((N, 2)), [(0, 300), (REVEAL, 1500), (SECONDS, 1500)])
    air *= curve([(0, 0.0), (2.0, 0.6), (REVEAL, 1.0), (REVEAL + 2.0, 0.0), (SECONDS, 0.0)])
    air *= (0.75 + 0.25 * np.sin(2 * np.pi * 0.11 * t))[:, None]
    bus["drone"] += air * 0.25

    # The arpeggio: eighths once the name is out, nothing under the sentence,
    # sixteenths rising into the drop and running to the last chord.
    up = [0, 1, 2, 3, 2, 1, 2, 3]
    for i, at in enumerate(beats(REVEAL, CLIP_IN - 0.3, BEAT / 2)):
        put(bus["arp"], pluck(chord_at(at)[2][up[i % 8]], bright=0.6), at, 0.35, pan=0.3 * np.sin(i))
    build = beats(BUILD, DROP - GAP, BEAT / 4)
    for i, at in enumerate(build):
        share = i / max(1, len(build) - 1)
        put(bus["arp"], pluck(chord_at(at)[2][up[i % 8]] * (2 if share > 0.5 and i % 2 else 1), bright=0.6 + share),
            at, 0.15 + 0.4 * share, pan=0.4 * np.sin(i))
    for i, at in enumerate(beats(DROP, FINAL, BEAT / 4)):
        put(bus["arp"], pluck(chord_at(at)[2][[0, 2, 1, 3][i % 4]], bright=1.2), at, 0.42, pan=0.35 * np.sin(i * 1.3))
        if at >= LIFT and i % 2:
            put(bus["arp"], pluck(chord_at(at)[2][[3, 1, 2, 0][i % 4]] * 2, bright=1.4), at, 0.16, pan=-0.5 * np.sin(i))
    # Its echoes would ring on into the sentence, so they are cut before it.
    arp = pingpong(bus["arp"]) * curve([(0, 1), (CLIP_IN - 0.6, 1), (CLIP_IN - 0.2, 0), (BUILD - 0.01, 0), (BUILD, 1), (SECONDS, 1)])

    # Bass: whole bars after the name, the last one over before the sentence,
    # eighths from the drop.
    for at in beats(REVEAL, CLIP_IN - BAR, BAR):
        n = int(BAR * RATE)
        tone = np.sin(2 * np.pi * chord_at(at)[1] * np.arange(n) / RATE) * env(n, 0.05, 0.4)
        put(bus["bass"], tone, at, 0.5)
    for at in beats(DROP, FINAL, BEAT / 2):
        put(bus["bass"], bass_note(chord_at(at)[1], BEAT / 2 - 0.02), at, 0.9)
    bass = sosfilt(butter(2, 420, "low", fs=RATE, output="sos"), bus["bass"], axis=0)

    # Drums: a soft heartbeat under "hold", the full beat from the drop.
    k, c, s = kick(), clap(), snare()
    for at in beats(HOLD, CLIP_IN - 0.4, BEAT * 2):
        put(bus["drums"], k, at, 0.35)
    groove = beats(DROP, FINAL)
    for i, at in enumerate(groove):
        put(bus["drums"], k, at, 0.9)
        if i % 2:
            put(bus["drums"], c, at, 0.32)
            put(bus["wet"], c, at, 0.15)
        put(bus["drums"], hat(), at + BEAT / 2, 0.2, pan=0.25 if i % 2 else -0.25)
        if at >= LIFT:
            for q in (0.25, 0.75):
                put(bus["drums"], hat(0.02), at + BEAT * q, 0.08, pan=-0.35 if i % 2 else 0.35)
    roll = beats(BUILD, DROP - GAP, BEAT / 2) + beats(DROP - BEAT * 2, DROP - GAP, BEAT / 4) + beats(DROP - BEAT, DROP - GAP, BEAT / 8)
    for at in sorted(set(round(a, 4) for a in roll)):
        share = (at - BUILD) / (DROP - BUILD)
        put(bus["drums"], s, at, 0.08 + 0.3 * share ** 1.5)

    # Sidechain: the pad, bass and arpeggio duck under every kick of the groove.
    duck = np.ones(N)
    shape = 1 - 0.55 * np.exp(-tt(0.45) / 0.15)
    for at in groove:
        i = int(at * RATE)
        j = min(N, i + len(shape))
        duck[i:j] = np.minimum(duck[i:j], shape[: j - i])
    pad *= duck[:, None]
    bass *= duck[:, None]
    arp *= (0.4 + 0.6 * duck)[:, None]

    # Moments: the name, the drop, the lift, the end.
    put(bus["fx"], riser(1.2) * 0.35, REVEAL - 1.2)
    put(bus["fx"], boom(), REVEAL, 0.45)
    put(bus["wet"], shimmer(chord_at(REVEAL + 0.01)[2]), REVEAL, 0.5)
    put(bus["fx"], riser(DROP - GAP - BUILD), BUILD, 0.5)
    for at, size in ((DROP, 1.0), (FINAL, 0.8)):
        put(bus["drums"], k, at, 1.0 * size)
        put(bus["fx"], boom(), at, 0.9 * size)
        put(bus["fx"], crash(), at, 0.3 * size)
        put(bus["wet"], crash(), at, 0.2 * size)
    put(bus["fx"], riser(1.0) * 0.25, LIFT - 1.0)
    put(bus["fx"], crash(), LIFT, 0.18)
    put(bus["wet"], shimmer(LAST), FINAL, 0.6)

    # Everything before the drop stops for a breath before it.
    before = ((t < DROP - GAP) | (t >= DROP))[:, None]
    dry = (0.30 * pad + 0.08 * bus["drone"] + 0.22 * arp + 0.42 * bass) * before + 0.85 * bus["drums"] + 0.5 * bus["fx"]
    wet = reverb(0.30 * 0.35 * pad + 0.22 * 0.45 * arp + 0.5 * 0.3 * bus["fx"] + bus["wet"])
    mix = dry + 0.55 * wet

    # Level: the groove at about -14 dBFS RMS, like the track it replaces,
    # and everything before the drop about 9 dB under it, as that track had
    # it: -31 under the question and the sentence, rising into the drop.
    mix *= curve([(0, 0.5), (REVEAL, 0.5), (REVEAL + 0.6, 0.4), (CLIP_IN - 0.3, 0.4), (CLIP_IN, 0.35), (CLIP_OUT, 0.35),
                  (BUILD, 0.55), (DROP - GAP, 0.9), (DROP - GAP + 0.001, 1.0), (SECONDS, 1.0)])
    i, j = int((DROP + 0.5) * RATE), int((FINAL - 0.5) * RATE)
    mix *= 10 ** (-14 / 20) / np.sqrt(np.mean(mix[i:j] ** 2))
    mix = np.tanh(mix * 1.1) / 1.1
    mix *= np.clip((SECONDS - t) / 0.5, 0, 1)[:, None]
    data = np.round(np.clip(mix, -1, 1) * 32767).astype("<i2")
    with wave.open(str(HERE / "public" / "music_dark.wav"), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(data.tobytes())
    print("music_dark.wav: drop {:.2f}, name {:.2f}, rise {:.2f}, lift {:.2f}, last chord {:.2f}, peak {:.2f}".format(
        DROP, REVEAL, BUILD, LIFT, FINAL, np.abs(mix).max()))


if __name__ == "__main__":
    main()
