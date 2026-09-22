"""Making a quiet recording loud enough to transcribe.

A laptop microphone a arm's length away produces audio that peaks around a
fiftieth of full scale. OpenAI returns an empty string for that: not an
error, not a guess, just nothing. Measured on the owner's machine, every
recording that came back empty peaked below -27 dB and every one that worked
was louder, so this is worth getting right.

This runs on the transcription audio ONLY, never on the audio the speech test
sees. Amplifying before the voice activity detector scales the room hiss up
with everything else, silence then reads as continuous speech, and Whisper
invents a sentence out of it.
"""

import logging

import numpy as np

logger = logging.getLogger("heyspeaky.levels")

TARGET = 0.9
MAX_GAIN = 24.0
PERCENTILE = 99.0
# Leave the loudest moment just under the ceiling rather than squaring it off.
HEADROOM = 0.99


def normalise(pcm, settings=None):
    """Returns the audio boosted, or unchanged if it needs no help."""
    settings = settings or {}
    if not settings.get("normalize_for_transcription", True) or not pcm:
        return pcm
    samples = np.frombuffer(pcm, dtype=np.int16)
    if samples.size == 0:
        return pcm

    magnitude = np.abs(samples)
    # A percentile rather than the maximum: one chair creak should not decide
    # that a whole quiet sentence needs no help.
    share = float(settings.get("normalize_percentile", PERCENTILE))
    level = float(np.percentile(magnitude, share)) / 32768.0
    peak = float(np.max(magnitude)) / 32768.0
    if level <= 0.0005:
        return pcm

    target = float(settings.get("normalize_target_peak", TARGET))
    gain = min(target / level, float(settings.get("normalize_max_gain",
                                                  MAX_GAIN)))
    if peak > 0:
        gain = min(gain, HEADROOM / peak)
    if gain <= 1.05:
        return pcm

    boosted = np.clip(samples.astype(np.float32) * gain,
                      -32768, 32767).astype(np.int16)
    logger.info("Boosted quiet audio: level %.3f peak %.3f x%.1f",
                level, peak, gain)
    return boosted.tobytes()
