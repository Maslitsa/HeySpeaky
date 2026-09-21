"""Configuration loading for HeySpeaky.

Settings live in config.json next to the project root so they survive
reinstalls of the environment.
"""

import copy
import json
import logging
from pathlib import Path

logger = logging.getLogger("heyspeaky.config")

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"
LOG_DIR = ROOT_DIR / "logs"

DEFAULTS = {
    "model": {
        # Multilingual models: handle English and Russian, auto-detected.
        "final": "base",
        # "" means auto-detect per utterance. Set "en", "ru" or "de" to pin it.
        "language": "",
        # The pin list in the tray's Language menu. Rebuilt from
        # transcription.cloud.languages whenever you add or remove a language
        # in the tray (Language > Add or remove languages), so change it there.
        "language_menu": {
            "Auto-detect": "",
            "English": "en",
            "Russian": "ru",
            "German": "de",
            "Kazakh": "kk",
        },
        # "auto" picks cuda when an NVIDIA card is actually usable and cpu
        # otherwise. This used to be hardcoded to cpu, which silently wasted a
        # GPU on the machines that have one, and Whisper on a GPU is several
        # times faster. Detecting a card is not the same as being able to use
        # it (old driver, missing cuDNN), so a cuda load that fails falls back
        # to cpu instead of refusing to start. Force it with "cpu" or "cuda".
        "device": "auto",
        # "auto" means float16 on a GPU and int8 on a CPU. int8 is what makes
        # CPU transcription bearable; float16 is the standard GPU choice.
        "compute_type": "auto",
        # 5 is faster-whisper's default and worth keeping. Greedy decoding
        # (beam_size 1) was measured here at 1.50-1.54s against 1.61-1.73s,
        # so it buys about a tenth of a second, and produced identical text on
        # clean clips, which means the only place it can differ is the hard
        # audio where the beam search is actually earning its keep.
        "beam_size": 5,
        # Where faster-whisper caches the model weights. null = default HF cache.
        "download_root": None,
        # Whisper's equivalent of a vocabulary hint: put your own names and
        # jargon here and the decoder is likelier to spell them right. Read
        # once at startup, so a change needs a restart.
        #
        # Empty on purpose. A bilingual Russian/English hint was tried here to
        # coax Whisper into code-switching, and it measurably made things
        # worse: on a German sentence ending in English it silently dropped
        # the entire English half, and it turned "Donnerstag" into
        # "Dunnestag". A prompt in one language biases everything you say
        # toward that language, so leave it empty unless you dictate in a
        # single language and want specific vocabulary respected.
        "initial_prompt": None,
    },
    "transcription": {
        # "local" runs on your CPU. "cloud" uses OpenAI's speech-to-text,
        # the same family ChatGPT's voice input uses.
        "backend": "local",
        # Local only: split the recording at pauses and detect the language of
        # each piece, so a sentence that switches language is not forced into
        # one.
        #
        # Off by default. It genuinely fixes English->Russian, which is the
        # one direction the single-pass decode gets wrong. But a segment is
        # transcribed without the surrounding context, and that costs accuracy
        # everywhere else: "bis morgen früh schicken" came back as "bis morgen
        # frischicken", sentence-final punctuation goes missing, and it runs
        # ~1.7x slower. Russian->English and German->English already come out
        # right in a single pass. Turn this on only if you regularly start a
        # sentence in English and finish it in another language, and prefer
        # the cloud backend, which handles all of this properly.
        "per_segment_language": False,
        "segment_min_pause": 0.35,
        # Whisper pads every piece to a 30-second window, so each segment is
        # a full extra pass. These two keep a long dictation with many natural
        # pauses from turning into a dozen of them.
        "segment_max": 3,
        "segment_min_length": 1.2,
        "cloud": {
            # "gpt-transcribe" is the current model and the only one measured
            # here that transcribes a sentence which switches language. Tested
            # on this machine with the same mixed English/Russian clip:
            #
            #   gpt-transcribe          both halves, each in its own script
            #   gpt-4o-transcribe       dropped the English half entirely
            #   gpt-4o-mini-transcribe  dropped the English half entirely
            #   whisper-1               translated the Russian into English
            #
            # gpt-4o-transcribe also rejects the `languages` and `keywords`
            # fields outright ("not supported for this model").
            "model": "gpt-transcribe",
            # Key lookup order: api_key, then this environment variable, then
            # api_key_file. Prefer the file: HeySpeaky starts from a Startup
            # shortcut and only inherits environment variables that already
            # existed when it launched, so a newly set variable is invisible
            # until you sign in again. The file is read per request.
            #
            # It deliberately lives outside the project folder. A key in
            # config.json is one 'git add -f', or one cloud-sync folder,
            # away from leaking.
            "api_key_env": "OPENAI_API_KEY",
            "api_key": "",
            "api_key_file": "%APPDATA%\\HeySpeaky\\openai.key",
            # The languages you speak. The cloud model is told to expect them,
            # the prompt and keywords are generated from them, and the tray
            # offers them as the languages you can pin. Change them from the
            # tray: Language > Add or remove languages.
            #
            # When first measured, on real speech, a Russian sentence ending in
            # English lost its English half with no list or ["ru", "en"], and
            # came back whole with ["en", "ru", "de"]. Rerun later on
            # synthesised speech, every list including none gave the right
            # answer, so treat it as a steer that costs nothing rather than a
            # switch you must set.
            #
            # A single 21.8s utterance that went English -> German -> Russian
            # -> Kazakh came back correct in all four, across three scripts, in
            # 3.4s, with Kazakh not even in the list at the time.
            "languages": ["en", "ru", "de", "kk"],
            # Literal terms you expect it to hear: names, jargon, product
            # names. e.g. ["Kubernetes", "RealtimeSTT", "Grafana"].
            #
            # Whatever you put here is added to a short built-in list of glue
            # words for the languages above, rather than replacing it, so
            # adding your own name does not undo the German fix. See
            # _GLUE_WORDS in transcribe.py for what that list is and why.
            "keywords": [],
            # Free-form hint sent with the audio. Leave it empty and one is
            # generated from the languages above, which is what you want.
            #
            # This is not cosmetic. A German phrase spoken in a Russian accent
            # came back as Cyrillic gibberish, the German sounds
            # transliterated into Cyrillic, on 6 attempts out of 6 with no
            # prompt. With the generated one it came back in Latin script on
            # 6 out of 6, and clean English, Russian and German were
            # unaffected.
            #
            # The wording matters more than it should. A longer, more explicit
            # version ("...switches mid-sentence. Write each language in its
            # own script.") failed all 6. Short wins. If you set your own,
            # keep it short and test it.
            "prompt": "",
            # 15, not 30. Measured on this machine the request takes 1.1-2.6s
            # for ordinary clips, and the worst seen in real use was 7.7s,
            # so anything past 15s is stuck rather than slow. Waiting the old 30s and
            # only then falling back to a local model that takes under two
            # seconds is a bad trade: it makes a network problem cost half a
            # minute of staring at the pill.
            "timeout": 15,
            # If the API errors or times out, transcribe locally instead of
            # losing what you just said.
            "fallback_to_local": True,
            # What a minute of audio costs, for the tally in the tray. OpenAI
            # does not return a price with a transcription, so this is an
            # estimate; check their pricing page if it changes.
            "price_per_minute": 0.006,
            # Once the month's estimate passes this, the app says so once.
            # It does not switch to the local model: that one is much weaker
            # on Russian and Kazakh, and a silent downgrade is worse than a
            # bigger bill. 0 turns the warning off.
            "monthly_warning_usd": 5.0,
        },
    },
    "hotkey": {
        # Hold Ctrl+Alt this long before recording engages. Also what stops
        # ordinary Ctrl+Alt+<key> shortcuts and AltGr from triggering us.
        "engage_delay": 0.25,
        # There used to be a third behaviour here: release between the engage
        # delay and this, and the recording latched. Nobody could hit a window
        # that narrow on purpose, so it is off (0) and hands-free has its own
        # gesture below. Set it to e.g. 0.7 to have the old behaviour back.
        "tap_max": 0.0,
        # Hands free, the way Wispr Flow does it: tap Ctrl+Alt twice within
        # this many seconds. Each tap on its own is too short to start
        # anything, which is what makes two of them safe to act on. While it
        # is recording hands-free, one more tap ends it. 0 turns this off.
        "double_tap_gap": 0.5,
        # Right Alt reports as "alt gr" on some layouts. Off by default so
        # typing accented characters never starts a recording.
        "accept_altgr": False,
        # Any other key pressed during the combo cancels the recording.
        "cancel_on_other_key": True,
        # How often to check the keyboard hook is still alive. Windows drops
        # low-level hooks silently, after a sleep or if a callback ever
        # overruns its timeout, and the only symptom is that Ctrl+Alt stops
        # working while the app carries on looking healthy. When nothing has
        # been typed for this long we inject a key bound to nothing and check
        # our own hook sees it, reinstalling if it does not. 0 disables.
        "health_check_seconds": 20,
        # Moving the mouse also counts as input to Windows but never reaches a
        # keyboard hook, so the check above cannot tell a dead hook from an
        # idle one. This caps how often the hook is actually replaced, which
        # turns that ambiguity into a harmless refresh when you return to the
        # machine instead of constant churn while you use the mouse.
        "min_reinstall_seconds": 60,
    },
    "recording": {
        # In latched mode, stop automatically after this much silence.
        # 0 disables auto-stop (then only a second Ctrl+Alt tap stops it).
        "latch_silence_timeout": 2.5,
        # Hard cap so a stuck key can never record forever.
        "max_seconds": 300,
        # Discard recordings shorter than this (accidental taps).
        "min_seconds": 0.35,
        # Whisper invents plausible sentences out of silence, so a recording
        # with no real speech in it must never reach the clipboard. We run
        # WebRTC VAD over the captured audio and require an unbroken run of
        # this many 20 ms frames. 12 frames = 240 ms.
        #
        # Measured on this laptop: real speech gives runs of 125-178 frames,
        # while four seconds of room noise peaks at 4. Neither loudness nor a
        # total frame count separates them. The idle noise floor already
        # sits near 0.48 of full scale and scatters ~11% false positives.
        # Run length does, and it does not depend on how long you spoke.
        "min_speech_run": 12,
        # WebRTC VAD aggressiveness, 0 (permissive) to 3 (strict).
        #
        # 1, not 2. WebRTC VAD gets less sensitive as the input gets quieter,
        # and this laptop's microphone records very quietly. Measured on real
        # speech captured through it, longest run of speech frames:
        #
        #                       aggr=2      aggr=1
        #   English speech        19          40
        #   Russian speech         8          23     <- 8 fails the test below
        #   silence                4           5
        #
        # At 2 a real Russian sentence scored below the threshold and was
        # thrown away as silence. At 1 both languages clear it comfortably and
        # silence still does not.
        "vad_aggressiveness": 1,
        # Boost quiet recordings to this peak before transcribing. Whisper and
        # the API both degrade on faint audio, Russian first, and this mic
        # peaks around 0.08 where 0.9 is available.
        #
        # Applied to the transcription audio ONLY, never to the speech test
        # above. Normalising before the VAD would scale the noise floor up
        # with everything else: silence then reads as 300 speech frames out of
        # 300, the silence guard never fires, and Whisper is free to invent a
        # sentence out of room hiss again.
        "normalize_for_transcription": True,
        "normalize_target_peak": 0.9,
        # Do not amplify beyond this, or near-silence becomes loud noise.
        "normalize_max_gain": 8.0,
        "silero_sensitivity": 0.4,
        "webrtc_sensitivity": 3,
    },
    "audio": {
        "sample_rate": 16000,
        "chunk_size": 512,
        # null = system default microphone.
        "input_device_index": None,
    },
    "output": {
        # Always put the transcript on the clipboard.
        "copy_to_clipboard": True,
        # "paste" = Ctrl+V into the focused window, "type" = synthesize
        # keystrokes, "none" = clipboard only.
        "insert_method": "paste",
        "append_space": True,
        # Wait for you to let go of Ctrl/Alt/Shift/Win before inserting.
        "modifier_release_timeout": 5.0,
    },
    "overlay": {
        # How the pill looks - colours, sizes, the waveform, the glass - lives
        # in heyspeaky/theme.py, where tools/ui_lab.py can draw it for you.
        # These three are here because they are about where it sits and how
        # long it stays, which is a matter of taste rather than design.
        #
        # Gap between the pill and the top of the taskbar.
        "margin_bottom": 14,
        "opacity": 0.97,
        "hide_delay": 1.6,
        # The two round buttons on the pill can be clicked: the cross throws
        # the recording away, the tick finishes it. While the pill is on
        # screen those two small circles swallow clicks instead of passing
        # them to whatever is underneath. Set to false to make the whole pill
        # untouchable again.
        "buttons_clickable": True,
    },
    "sound": {
        # Played when the text has been inserted. One of drip, breath, tap,
        # bowl, or "none" for silence. The files are built on this machine the
        # first time they are needed; nothing is downloaded.
        "finish": "drip",
        # 0 to 1. Deliberately quiet.
        "volume": 0.18,
    },
    "log_level": "INFO",
}


def _deep_merge(base, override):
    """Returns base updated with override, recursing into nested dicts."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def save(cfg):
    """Writes the full config back to disk, keeping user edits readable."""
    try:
        CONFIG_PATH.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except OSError as exc:
        logger.warning("Could not save config.json: %s", exc)
        return False


def load():
    """Loads config.json merged over the defaults, writing it if absent."""
    user_config = {}
    if CONFIG_PATH.exists():
        try:
            user_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring unreadable config.json: %s", exc)
    else:
        try:
            CONFIG_PATH.write_text(
                json.dumps(DEFAULTS, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Could not write default config.json: %s", exc)
    return _deep_merge(DEFAULTS, user_config)
