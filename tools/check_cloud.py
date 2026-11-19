r"""Verifies the OpenAI transcription backend end to end.

Run this once after setting OPENAI_API_KEY. It synthesises speech with the
Windows voices you already have, sends it to OpenAI, and prints what came
back with timings and a cost estimate, including a sentence that switches
language mid-way, which is the case the local model cannot do.

    .venv\Scripts\python.exe tools\check_cloud.py
"""

import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from heyspeaky import config as config_module          # noqa: E402
from heyspeaky.transcribe import CloudBackend          # noqa: E402

# (label, [(voice, text), ...], what it should say)
CASES = [
    ("English", [("Zira", "Can you send me the report by tomorrow morning?")],
     "Can you send me the report by tomorrow morning?"),
    ("Russian", [("Irina", "Привет, это проверка системы голосового ввода.")],
     "Привет, это проверка системы голосового ввода."),
    ("German", [("Hedda", "Können Sie mir den Bericht bis morgen früh "
                          "schicken?")],
     "Können Sie mir den Bericht bis morgen früh schicken?"),
    ("English then Russian",
     [("Zira", "I already sent the invoice yesterday but"),
      ("Irina", "клиент до сих пор не ответил на моё письмо")],
     "both halves, each in its own script"),
    ("German then English",
     [("Hedda", "Ich habe die Rechnung gestern geschickt aber"),
      ("Zira", "the client has not replied to my email yet")],
     "both halves, each in its own language"),
]

PS_TEMPLATE = """
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
{body}
$s.Dispose()
"""


def synthesise(parts, out_dir):
    """Renders each part with its voice; returns the wav paths."""
    body = []
    paths = []
    for index, (voice, text) in enumerate(parts):
        path = out_dir / "part{}.wav".format(index)
        paths.append(path)
        body.append('$s.SelectVoice("Microsoft {} Desktop")'.format(voice))
        body.append('$s.SetOutputToWaveFile("{}")'.format(path))
        body.append('$s.Speak("{}")'.format(text.replace('"', '`"')))
    script = PS_TEMPLATE.format(body="\n".join(body))
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:300])
    return paths


def join_pcm(paths, rate):
    """Concatenates the parts into one 16 kHz mono PCM16 buffer."""
    import numpy as np
    from scipy.signal import resample

    chunks = []
    for path in paths:
        with wave.open(str(path), "rb") as handle:
            raw = handle.readframes(handle.getnframes())
            source_rate = handle.getframerate()
            channels = handle.getnchannels()
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            audio = audio.reshape(-1, channels)[:, 0]
        if source_rate != rate:
            audio = resample(audio, int(len(audio) * rate / source_rate))
        chunks.append(audio)
        chunks.append(np.zeros(int(rate * 0.15), dtype=np.float32))
    joined = np.concatenate(chunks[:-1])
    return (np.clip(joined, -1, 1) * 32767).astype(np.int16).tobytes()


def main():
    cfg = config_module.load()
    cloud = CloudBackend(cfg)
    if not cloud.available():
        print("No API key found.\n")
        print("Set one, then open a NEW terminal so it is visible:")
        print('    setx {} "sk-your-key-here"'.format(
            cfg["transcription"]["cloud"]["api_key_env"]))
        return 1

    rate = int(cfg["audio"]["sample_rate"])
    model = cfg["transcription"]["cloud"]["model"]
    print("model     : {}".format(model))
    print("languages : {}".format(cfg["transcription"]["cloud"]["languages"]))
    print("-" * 68)

    total_seconds = 0.0
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        for label, parts, expected in CASES:
            try:
                pcm = join_pcm(synthesise(parts, out_dir), rate)
            except Exception as exc:
                print("{:<22} could not synthesise: {}".format(
                    label, str(exc)[:60]))
                continue
            seconds = len(pcm) / 2 / rate
            total_seconds += seconds
            started = time.monotonic()
            try:
                text = cloud.transcribe(pcm, "")
            except Exception as exc:
                failures += 1
                print("{:<22} FAILED: {}".format(label, str(exc)[:120]))
                continue
            print("{:<22} {:.1f}s audio -> {:.1f}s".format(
                label, seconds, time.monotonic() - started))
            print("   expected: {}".format(expected))
            print("   got     : {}".format(text))

    print("-" * 68)
    # $0.006/min for gpt-4o-transcribe; mini is about half.
    cost = total_seconds / 60.0 * 0.006
    print("{:.1f}s of audio, about ${:.4f} at $0.006/min".format(
        total_seconds, cost))
    if failures:
        print("\n{} request(s) failed. If the model name was rejected, try "
              '"gpt-transcribe" or "gpt-4o-mini-transcribe" in config.json '
              "under transcription.cloud.model.".format(failures))
        return 1
    print("\nCloud backend works. Pick 'OpenAI' in the tray to use it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
