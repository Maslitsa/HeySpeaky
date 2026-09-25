"""The small sound at the end of a dictation.

There is no sound file in this repository. Every voice is arithmetic, built
once into `%APPDATA%\\HeySpeaky\\sounds` the first time it is needed, so
nothing binary has to be shipped, reviewed or kept in sync with the installer.

The first version of this was pure sine tones, which is what a notification
sounds like: bright, hard-edged, and in a hurry. None of that is restful. What
makes a sound feel close and soft is the opposite - a slow attack so nothing
clicks, most of the energy low down, filtered noise rather than a clean pitch,
and a tail that fades out instead of stopping. So each voice here is a few
quiet tones plus a burst of noise pushed through a low-pass filter whose
cutoff falls as the sound decays, the way a real object dulls as it stops
moving.

Playing is `winsound`, which is part of Python on Windows, so this adds no
dependency. It is asynchronous: the sound never delays the text landing in
your document.

    python -m heyspeaky.sound --preview <folder>   # write every voice to hear
"""

import array
import logging
import math
import os
import random
import struct
import sys
import wave

logger = logging.getLogger("heyspeaky.sound")

RATE = 44100

# A tone is: where the pitch starts and ends, how long that slide takes, how
# loud it is, how fast it dies away, when it begins, and how gently it starts.
# Noise is: how loud, its attack and decay, and the low-pass cutoff at the
# start and at the end.
VOICES = {
    # A drop of water into a bowl. The pitch of a real drop rises as the
    # cavity it makes closes up, which is the whole character of the sound.
    "drip": {
        "seconds": 0.55,
        "tones": [
            (430.0, 880.0, 0.055, 0.85, 0.15, 0.000, 0.008),
            (176.0, 168.0, 0.300, 0.40, 0.090, 0.000, 0.010),
        ],
        "noise": (0.22, 0.003, 0.030, 2400.0, 420.0),
    },
    # A quiet exhale. No pitch at all, only filtered noise swelling and
    # falling away. The most restful of the four, and the least like an alert.
    "breath": {
        "seconds": 0.95,
        "tones": [
            (150.0, 120.0, 0.700, 0.16, 0.320, 0.000, 0.120),
        ],
        "noise": (0.70, 0.130, 0.330, 1100.0, 260.0),
    },
    # A fingertip on a wooden table. Short, low, dry.
    "tap": {
        "seconds": 0.40,
        "tones": [
            (142.0, 132.0, 0.120, 0.90, 0.080, 0.000, 0.006),
            (268.0, 250.0, 0.120, 0.30, 0.045, 0.000, 0.006),
        ],
        "noise": (0.35, 0.002, 0.022, 1600.0, 300.0),
    },
    # A small bowl, struck as softly as it can be. The longest tail.
    "bowl": {
        "seconds": 1.40,
        "tones": [
            (318.0, 316.0, 1.000, 0.80, 0.620, 0.000, 0.030),
            (861.0, 856.0, 1.000, 0.22, 0.330, 0.000, 0.030),
            (159.0, 158.0, 1.000, 0.35, 0.700, 0.000, 0.040),
        ],
        "noise": (0.10, 0.004, 0.055, 1800.0, 400.0),
    },
    # The mono look's sound: two notes a fourth apart, about 500 and 670 Hz,
    # each a pluck that is gone in a few milliseconds, falling over each
    # other and fading in a fifth of a second. Measured off the reel the
    # owner sent, where it played twice, identically, the moment the words
    # landed: every pluck's start, pitch, loudness and decay below is a
    # number read from that recording. Built here from those numbers, like
    # the rest - the recording itself is not copied.
    "blip": {
        "seconds": 0.30,
        "tones": [
            (500.0, 500.0, 0.0, 0.62, 0.0093, 0.000, 0.0015),
            (669.0, 669.0, 0.0, 0.67, 0.0093, 0.000, 0.0015),
            (669.0, 669.0, 0.0, 0.99, 0.0061, 0.066, 0.0010),
            (500.0, 500.0, 0.0, 0.63, 0.0072, 0.089, 0.0010),
            (671.0, 671.0, 0.0, 0.30, 0.0054, 0.133, 0.0010),
            (500.0, 500.0, 0.0, 0.08, 0.0063, 0.178, 0.0010),
            (670.0, 670.0, 0.0, 0.05, 0.0054, 0.198, 0.0010),
        ],
        "noise": None,
    },
}
DEFAULT = "drip"


def for_look(finish, style):
    """The voice to play: `finish` as set, with "auto" meaning the one that
    belongs to the look - blip with mono, drip with the glass."""
    if finish in (None, "", "auto"):
        return "blip" if style == "mono" else DEFAULT
    return finish
# Quiet on purpose. This is meant to be noticed, not heard.
VOLUME = 0.18


def _envelope(age, attack, decay):
    """Raised-cosine in, exponential out. Never starts or stops abruptly."""
    if age < 0:
        return 0.0
    out = math.exp(-age / decay)
    if attack > 0 and age < attack:
        # A straight ramp still leaves a corner you can hear; this does not.
        out *= 0.5 - 0.5 * math.cos(math.pi * age / attack)
    return out


def _tones(voice, total):
    out = [0.0] * total
    for start_hz, end_hz, slide, loud, decay, begins, attack in voice["tones"]:
        first = int(RATE * begins)
        phase = 0.0
        for index in range(first, total):
            age = (index - first) / float(RATE)
            level = _envelope(age, attack, decay)
            if level < 0.0004 and age > attack:
                break
            share = min(1.0, age / slide) if slide > 0 else 1.0
            hz = start_hz + (end_hz - start_hz) * share
            phase += 2.0 * math.pi * hz / RATE
            out[index] += loud * level * math.sin(phase)
    return out


def _noise(voice, total):
    """Noise through a one-pole low-pass whose cutoff falls as it decays."""
    if not voice.get("noise"):
        return [0.0] * total
    loud, attack, decay, cutoff, cutoff_end = voice["noise"]
    # Seeded, so the same voice is always the same file.
    source = random.Random(20260921)
    out = [0.0] * total
    carried = 0.0
    for index in range(total):
        age = index / float(RATE)
        level = _envelope(age, attack, decay)
        share = min(1.0, age / max(1e-6, decay * 3))
        hz = cutoff + (cutoff_end - cutoff) * share
        weight = 1.0 - math.exp(-2.0 * math.pi * hz / RATE)
        carried += weight * (source.uniform(-1.0, 1.0) - carried)
        out[index] = loud * level * carried
    return out


def _samples(voice, volume):
    """Builds the waveform. Pure arithmetic, no numpy, no files."""
    total = int(RATE * voice["seconds"])
    tones = _tones(voice, total)
    noise = _noise(voice, total)
    raw = [tones[i] + noise[i] for i in range(total)]

    peak = max((abs(value) for value in raw), default=0.0) or 1.0
    gain = volume / peak
    out = array.array("h", [0]) * total
    for index, value in enumerate(raw):
        out[index] = int(max(-32767, min(32767, value * gain * 32767)))
    return out


def write(name, path, volume=VOLUME):
    """Writes one voice to a .wav file."""
    voice = VOICES.get(name) or VOICES[DEFAULT]
    data = _samples(voice, volume)
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(struct.pack("<%dh" % len(data), *data))
    return path


def _store(name, volume):
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                        "HeySpeaky", "sounds")
    # The volume is in the name, so changing it in settings rebuilds the file
    # instead of quietly playing the old one.
    return os.path.join(base, "%s-%02d.wav" % (name, int(round(volume * 99))))


def ensure(name=DEFAULT, volume=VOLUME):
    """The path to the sound, building it if it is not there yet."""
    path = _store(name, volume)
    if os.path.isfile(path):
        return path
    return write(name, path, volume)


def play(name=DEFAULT, volume=VOLUME):
    """Plays the sound and returns at once. Never raises."""
    if not name or name == "none" or volume <= 0:
        return False
    try:
        import winsound

        winsound.PlaySound(ensure(name, volume),
                           winsound.SND_FILENAME | winsound.SND_ASYNC
                           | winsound.SND_NODEFAULT)
        return True
    except Exception:
        logger.debug("Could not play the %s sound", name, exc_info=True)
        return False


def main(argv):
    if len(argv) >= 3 and argv[1] == "--preview":
        for name in VOICES:
            print(write(name, os.path.join(argv[2], name + ".wav")))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
