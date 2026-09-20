r"""Checks whether your microphone is good enough for dictation.

Records you speaking, then reports the level, whether the speech detector
fires, and what the transcript comes out as. Run it when dictation says
"Nothing heard".

    .venv\Scripts\python.exe tools\check_mic.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np                                      # noqa: E402
import webrtcvad                                        # noqa: E402

from heyspeaky import config as config_module           # noqa: E402
from heyspeaky.mic import Microphone, list_input_devices  # noqa: E402
from heyspeaky.transcribe import CloudBackend           # noqa: E402

SECONDS = 6


def longest_run(pcm, rate, aggressiveness):
    """Longest unbroken stretch of speech frames, as the app measures it."""
    vad = webrtcvad.Vad(aggressiveness)
    size = int(rate * 0.02) * 2
    best = current = total = 0
    for offset in range(0, len(pcm) - size + 1, size):
        try:
            speech = vad.is_speech(pcm[offset:offset + size], rate)
        except Exception:
            speech = False
        if speech:
            current += 1
            total += 1
            best = max(best, current)
        else:
            current = 0
    return best, total, len(pcm) // size


def main():
    cfg = config_module.load()
    rate = int(cfg["audio"]["sample_rate"])
    rec = cfg["recording"]
    need = int(rec["min_speech_run"])
    aggressiveness = int(rec["vad_aggressiveness"])

    print("Input devices:")
    try:
        for index, name in list_input_devices():
            print("  {:>2}  {}".format(index, name))
    except Exception as exc:
        print("  could not list devices: {}".format(exc))
    chosen = cfg["audio"]["input_device_index"]
    print("HeySpeaky uses: {}\n".format(
        "system default" if chosen is None else "device {}".format(chosen)))

    print("=" * 62)
    print("SPEAK NORMALLY for {} seconds, starting now...".format(SECONDS))
    print("=" * 62, flush=True)

    chunks = []
    mic = Microphone(cfg["audio"], on_chunk=chunks.append,
                     on_level=lambda level: None)
    if not mic.start():
        print("\nThe microphone would not open at all.")
        return 1
    for remaining in range(SECONDS, 0, -1):
        print("  {}...".format(remaining), flush=True)
        time.sleep(1.0)
    mic.stop()
    print("done.\n")

    pcm = b"".join(chunks)
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size == 0:
        print("No audio captured at all.")
        return 1

    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(samples ** 2)))
    # Speech has a big gap between its loud and quiet moments; steady noise
    # does not. This is what tells "quiet voice" apart from "dead channel".
    block = rate // 5
    blocks = [samples[i:i + block] for i in range(0, samples.size - block, block)]
    levels = sorted(float(np.sqrt(np.mean(b ** 2))) for b in blocks) or [0.0]
    quietest, loudest = levels[0], levels[-1]
    variation = loudest / quietest if quietest > 1e-9 else 0.0

    best, total, frames = longest_run(pcm, rate, aggressiveness)

    print("peak level        : {:.4f}".format(peak))
    print("average level     : {:.5f}".format(rms))
    print("quiet vs loud     : x{:.1f}".format(variation))
    print("speech frames     : {}/{}, longest run {} (need {})".format(
        total, frames, best, need))
    print()

    if variation < 2.0:
        print("VERDICT: the microphone is not picking up your voice.")
        print("  The signal never changes, so nothing is reaching it.")
        print("  - Check Settings > System > Sound > Input: pick the right")
        print("    device and confirm the bar moves when you speak.")
        print("  - Check the mic is not muted, and not disabled by a")
        print("    keyboard mute key or a privacy shutter.")
        print("  - Settings > Privacy > Microphone must allow desktop apps.")
    elif best < need:
        print("VERDICT: your voice is there but too quiet to pass the test.")
        print("  - Raise the level: Sound > Input > your mic > Properties,")
        print("    set Volume to 100 and enable any Microphone Boost.")
        print("  - Speak closer to the laptop.")
        print("  - Or lower recording.min_speech_run in config.json"
              " (currently {}).".format(need))
    else:
        print("VERDICT: microphone is fine. Dictation should work.")

    backend = CloudBackend(cfg)
    if backend.available():
        target = float(rec.get("normalize_target_peak", 0.9))
        gain = min(target / peak, float(rec.get("normalize_max_gain", 8.0))) \
            if peak > 0.001 else 1.0
        boosted = np.clip(samples * gain, -1, 1)
        payload = (boosted * 32767).astype(np.int16).tobytes()
        print("\nSending to OpenAI (boosted x{:.1f})...".format(gain))
        try:
            print("heard: {!r}".format(backend.transcribe(payload, "")))
        except Exception as exc:
            print("transcription failed: {}".format(str(exc)[:160]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
