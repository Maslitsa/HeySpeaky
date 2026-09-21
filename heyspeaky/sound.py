"""The small sound at the end of a dictation.

There is no sound file in this repository. The tones are arithmetic, built
once into `%APPDATA%\\HeySpeaky\\sounds` the first time they are needed, so
nothing binary has to be shipped, reviewed or kept in sync with the installer.

Playing is `winsound`, which is part of Python on Windows, so this adds no
dependency. It is asynchronous: the sound never delays the text landing in
your document.

    python -m heyspeaky.sound --preview <folder>   # write every voice to listen to
"""

import array
import logging
import math
import os
import struct
import sys
import wave

logger = logging.getLogger("heyspeaky.sound")

RATE = 44100

# Each voice is a list of partials: (frequency, how loud, how fast it dies,
# when it starts, how far the pitch falls by the end).
VOICES = {
    # A drop of water into a bowl. Soft, round, no edge to it.
    "drop": {
        "seconds": 0.55,
        "partials": [
            (880.0, 1.00, 0.10, 0.000, -90.0),
            (1760.0, 0.14, 0.05, 0.000, -180.0),
        ],
    },
    # Two notes upward, the way a phone says "done".
    "rise": {
        "seconds": 0.60,
        "partials": [
            (659.25, 0.80, 0.09, 0.000, 0.0),
            (987.77, 0.90, 0.16, 0.095, 0.0),
            (1975.5, 0.08, 0.10, 0.095, 0.0),
        ],
    },
    # A wooden bar struck softly. Warmest of the three.
    "wood": {
        "seconds": 0.70,
        "partials": [
            (523.25, 1.00, 0.16, 0.000, 0.0),
            (1570.0, 0.22, 0.07, 0.000, 0.0),
            (2616.0, 0.07, 0.04, 0.000, 0.0),
        ],
    },
}
DEFAULT = "drop"
# Quiet on purpose. This is meant to be noticed, not heard.
VOLUME = 0.22


def _samples(voice, volume):
    """Builds the waveform. Pure arithmetic, no numpy, no files."""
    seconds = voice["seconds"]
    total = int(RATE * seconds)
    out = array.array("h", [0]) * total
    peak = 0.0
    raw = [0.0] * total

    for freq, loud, decay, start, drift in voice["partials"]:
        begin = int(RATE * start)
        phase = 0.0
        for index in range(begin, total):
            age = (index - begin) / float(RATE)
            envelope = math.exp(-age / decay)
            if envelope < 0.0005:
                break
            # A few milliseconds of fade-in, or the start clicks.
            if age < 0.004:
                envelope *= age / 0.004
            share = (index - begin) / float(max(1, total - begin))
            phase += 2.0 * math.pi * (freq + drift * share) / RATE
            raw[index] += loud * envelope * math.sin(phase)

    for value in raw:
        peak = max(peak, abs(value))
    if peak <= 0:
        peak = 1.0
    gain = volume / peak
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
