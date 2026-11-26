"""Transcription backends and the per-segment language trick.

Two backends produce the final text:

  local   faster-whisper running inside RealtimeSTT, on your CPU
  cloud   OpenAI's gpt-4o-transcribe, the model ChatGPT's voice input uses

The local backend also implements per-segment language detection. Whisper
emits one language token per utterance and decodes everything under it, so a
sentence that switches language mid-way gets the other half *translated*
rather than transcribed. Splitting the audio at pauses and letting Whisper
detect each piece separately fixes that, measured on this machine:

    "I already sent the invoice yesterday but" followed by the Russian for
    "the client still has not answered my letter"

    whole utterance -> "...but Client has still not answered my letter"  (wrong)
    per segment     -> "[en] I already sent the invoice yesterday but..."
                       "[ru] (the second half, in Russian, as spoken)"

It only helps when you actually pause at the switch; a seamless switch still
lands in one language. The cloud backend needs none of this.
"""

import io
import logging
import os
import time
import wave

import numpy as np
import webrtcvad

from . import alphabet, dictionary, link
from .languages import NAMES

logger = logging.getLogger("heyspeaky.transcribe")


class CloudUnreachable(RuntimeError):
    """The request never reached OpenAI: no network, DNS, or TLS failure.

    Separate from an API error because it says something about the next
    request too. If the network is down now it is probably still down in two
    seconds, and stalling on every dictation helps nobody.
    """


class NoCredit(RuntimeError):
    """OpenAI answered, and money is what stops it: no credit left, or a
    spending limit somebody set has been reached. Only a person can fix
    either, on OpenAI's site, so it is never retried.

    `reason` is what the problem report gives, beside "offline" and "cloud
    error". `say` is what the pill shows, and has to fit the glass pill's
    116 pixels of text: anything longer ends in an ellipsis."""

    def __init__(self, detail, reason="no OpenAI credit",
                 say="No OpenAI credit"):
        super(NoCredit, self).__init__(detail)
        self.reason = reason
        self.say = say


# The 429s that no retry can help, most particular first: a spending limit's
# body may call itself insufficient_quota as well. The two limit codes are
# from OpenAI's spend-limits guide. A key handed to testers lives in a project
# with a hard limit, and when it ran out they were told only "cloud error".
_MONEY_REFUSALS = (
    ("project_spend_limit_exceeded",
     "OpenAI says this key's project has reached its spending limit",
     "key's spend limit", "Key's limit used up"),
    ("organization_spend_limit_exceeded",
     "OpenAI says the account has reached its spending limit",
     "account's spend limit", "Account's limit hit"),
    ("insufficient_quota",
     "OpenAI says the account has no credit left",
     "no OpenAI credit", "No OpenAI credit"),
)


def money_refusal(status_code, body):
    """NoCredit for an answer that is about money rather than traffic, or
    None when a retry might still help."""
    if status_code != 429:
        return None
    for code, detail, reason, say in _MONEY_REFUSALS:
        if code in body:
            return NoCredit(detail, reason, say)
    return None


OPENAI_TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"

# Names for the generated prompt, shared with the tray so a language added
# there is named properly here too. A code missing from the table is used as
# is, which still reads sensibly in the prompt.
_LANGUAGE_NAMES = NAMES


# Short function words that get swallowed in connected speech, per language.
#
# German earns its place by measurement. Nobody pronounces the final -r in
# "aber": it vocalises to a schwa, so the microphone hears roughly "aba".
# Coming straight out of Kazakh, where the decoder is already in Cyrillic,
# that either turns into "aby" written in Cyrillic or vanishes. Measured on a clip with the
# reduced pronunciation, "aber" survived 0 times out of 3 without these and
# 3 out of 3 with them, and five clean clips in other languages came back
# byte-identical either way.
#
# Only German is listed because German is the only one measured. If short
# words go missing in your language, add them here and say what changed.
_GLUE_WORDS = {
    "de": ["Aber", "aber", "oder", "wenn", "dann", "doch", "noch", "auch"],
}


def _default_keywords(codes):
    """Glue words for the configured languages, in a stable order."""
    words = []
    for code in codes:
        for word in _GLUE_WORDS.get(code, ()):
            if word not in words:
                words.append(word)
    return words


def _default_prompt(codes):
    """Builds the steering prompt from the languages the user speaks.

    This is load-bearing for accented speech. A short German phrase read in a
    Russian accent came back as Cyrillic gibberish, the German sounds
    transliterated into Cyrillic, on 6 attempts out of 6. With this prompt it
    came back in Latin script on 6 out of 6.

    The wording matters more than seems reasonable. A longer, more explicit
    version ("...switches mid-sentence. Write each language in its own
    script.") failed all 6, so this stays short. Generating it from the
    configured list rather than hardcoding a sentence means it keeps matching
    whatever languages someone actually set.
    """
    names = [_LANGUAGE_NAMES.get(c, c) for c in codes if c]
    if len(names) < 2:
        return ""
    listed = "{} and {}".format(", ".join(names[:-1]), names[-1])
    return "The speaker mixes {}.".format(listed)

# Getting a connection must fail fast. The per-request timeout covers the
# upload and the model's own work, which legitimately take seconds, but a
# machine with no network spends all of that time in getaddrinfo before
# anything can fall back, measured at 11.6s here on a DNS failure, on top of
# the local transcription that followed it. Bounding the connect phase turns
# that into a short pause.
CONNECT_TIMEOUT = 4.0

# After a connection failure, skip the cloud entirely for this long rather
# than stalling on every subsequent recording. Short on purpose: a passing
# wifi drop should cost one slow dictation, not a minute of degraded ones.
OFFLINE_MEMO_SECONDS = 20.0

# Below this, the model's own average odds on the words it wrote, it is
# asked again with another language first (Router._second_opinion). On 96
# synthesised recordings that came back right or nearly right the least sure
# averaged -0.11, so this leaves ordinary dictation alone. It is a first
# guess for real voices: every cloud dictation now logs its number, and the
# next nonsense transcript will show where the line belongs.
UNSURE_BELOW = -0.3

# What the pill says when the cloud could not be reached and the local model
# wrote the text instead. Ten of the owner's 245 dictations in the week to
# 26 November went that way and he was never told: the text just came out
# worse ("дектовку", "прихня"), and it read as the app getting worse. Short
# enough for the glass pill's 116 pixels (113).
OFFLINE_SAY = "Offline: local model"

# Where the key lived under the older names, newest first. Only ever read,
# as a fallback, so nobody has to move a file after updating.
LEGACY_KEY_FILES = (
    "%APPDATA%\\SpeakIt\\openai.key",
    "%APPDATA%\\VoiceType\\openai.key",
)


def pcm_to_float(pcm_bytes):
    """Converts PCM16 bytes into the float32 array faster-whisper wants."""
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    return (samples.astype(np.float32) / 32768.0).copy()


def pcm_to_wav(pcm_bytes, rate):
    """Wraps raw PCM16 in a WAV container for upload."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm_bytes)
    return buffer.getvalue()


def pcm_to_upload(pcm_bytes, rate):
    """The recording as it goes to OpenAI: (file name, bytes, type).

    FLAC where it can be written, which is lossless - the samples OpenAI
    decodes are exactly the ones recorded - and two thirds the size: 1740 KB
    against 2685 KB on nineteen of the owner's own recordings, boosted the
    way the app boosts them, in 5 ms. Less to send is less to wait for after
    the keys come up, most of all on a poor line. WAV when soundfile is
    missing, as it always used to be.
    """
    try:
        import soundfile
        buffer = io.BytesIO()
        soundfile.write(buffer, np.frombuffer(pcm_bytes, dtype=np.int16),
                        rate, format="FLAC", subtype="PCM_16")
        return "speech.flac", buffer.getvalue(), "audio/flac"
    except Exception:
        logger.debug("FLAC unavailable; sending WAV", exc_info=True)
        return "speech.wav", pcm_to_wav(pcm_bytes, rate), "audio/wav"


def split_on_pauses(pcm_bytes, rate, min_pause=0.35, aggressiveness=2,
                    pad=0.1, min_segment=0.2, max_segments=3, min_keep=1.2):
    """Splits PCM16 audio into speech runs separated by silence.

    Returns a list of (start_sample, end_sample) pairs. A single pair means
    there is nothing to split and the caller should take the fast path.
    """
    frame_bytes = int(rate * 0.02) * 2
    if frame_bytes <= 0 or len(pcm_bytes) < frame_bytes:
        return [(0, len(pcm_bytes) // 2)]

    try:
        vad = webrtcvad.Vad(aggressiveness)
    except Exception:
        logger.debug("Could not build the splitting VAD", exc_info=True)
        return [(0, len(pcm_bytes) // 2)]

    flags = []
    for offset in range(0, len(pcm_bytes) - frame_bytes + 1, frame_bytes):
        try:
            flags.append(
                vad.is_speech(pcm_bytes[offset:offset + frame_bytes], rate)
            )
        except Exception:
            flags.append(False)

    needed = max(1, int(min_pause / 0.02))
    runs = []
    start = None
    silence = 0
    for index, speech in enumerate(flags):
        if speech:
            if start is None:
                start = index
            silence = 0
        elif start is not None:
            silence += 1
            if silence >= needed:
                runs.append((start, index - silence + 1))
                start = None
                silence = 0
    if start is not None:
        runs.append((start, len(flags)))

    if not runs:
        return [(0, len(pcm_bytes) // 2)]

    total = len(pcm_bytes) // 2
    spans = []
    for begin, end in runs:
        lo = max(0, int((begin * 0.02 - pad) * rate))
        hi = min(total, int((end * 0.02 + pad) * rate))
        if hi - lo >= int(min_segment * rate):
            spans.append((lo, hi))
    if not spans:
        return [(0, total)]
    return _merge_spans(spans, rate, max_segments, min_keep)


def _merge_spans(spans, rate, max_segments, min_keep):
    """Merges spans until there are few enough, and none are too short.

    Whisper pads every piece it is given to a full 30-second window, so each
    extra segment costs a whole extra pass no matter how brief it is. Speaking
    for a minute with natural pauses produced seventeen of them once, which
    took 22 seconds instead of 3. Merging across the *smallest* gaps first
    keeps the longest pauses as the boundaries, and those are exactly where a
    language actually changes. It also removes the one-word fragments that
    Whisper likes to misidentify (a stray Russian "because" came back as Welsh).
    """
    merged = list(spans)

    def gap_before(index):
        return merged[index][0] - merged[index - 1][1]

    # Absorb fragments too short to identify a language from.
    floor = int(min_keep * rate)
    while len(merged) > 1:
        index = min(
            range(len(merged)),
            key=lambda i: merged[i][1] - merged[i][0],
        )
        if merged[index][1] - merged[index][0] >= floor:
            break
        if index == 0:
            join = 1
        elif index == len(merged) - 1:
            join = len(merged) - 1
        else:
            join = index if gap_before(index) <= gap_before(index + 1) else index + 1
        merged[join - 1] = (merged[join - 1][0], merged[join][1])
        del merged[join]

    # Then cap the count, always closing the tightest gap first.
    while len(merged) > max_segments:
        index = min(range(1, len(merged)), key=gap_before)
        merged[index - 1] = (merged[index - 1][0], merged[index][1])
        del merged[index]

    return merged


class LocalBackend:
    """Transcribes on the CPU using the model RealtimeSTT already loaded."""

    name = "local"

    def __init__(self, engine, config):
        self._engine = engine
        self._cfg = config
        self._rate = int(config["audio"]["sample_rate"])

    def transcribe(self, pcm_bytes, language):
        tcfg = self._cfg["transcription"]
        if not tcfg["per_segment_language"] or language:
            # A pinned language means the user has told us there is only one.
            return self._engine.transcribe_audio(
                pcm_to_float(pcm_bytes), language
            )

        spans = split_on_pauses(
            pcm_bytes,
            self._rate,
            min_pause=float(tcfg["segment_min_pause"]),
            aggressiveness=int(self._cfg["recording"]["vad_aggressiveness"]),
            max_segments=int(tcfg["segment_max"]),
            min_keep=float(tcfg["segment_min_length"]),
        )
        if len(spans) < 2:
            return self._engine.transcribe_audio(pcm_to_float(pcm_bytes), "")

        logger.info("Transcribing %d segments separately", len(spans))
        audio = pcm_to_float(pcm_bytes)
        parts = []
        languages = []
        for lo, hi in spans:
            text = self._engine.transcribe_audio(audio[lo:hi], "")
            if text:
                parts.append(text.strip())
                languages.append(self._engine.detected_language)
        if not parts:
            return ""
        logger.info("Segment languages: %s", languages)
        return _join_segments(parts)


def _join_segments(parts):
    """Joins segment texts, avoiding doubled spaces and stray ellipses."""
    cleaned = []
    for index, part in enumerate(parts):
        text = part.strip()
        if not text:
            continue
        # Whisper often ends a clipped segment with "..." - drop it unless it
        # is the very last piece, where it may be genuine.
        if index < len(parts) - 1 and text.endswith("..."):
            text = text[:-3].rstrip()
        cleaned.append(text)
    return " ".join(cleaned).strip()


class Heard(object):
    """What the cloud wrote, how sure it was, and the languages it heard.

    `average` and `lowest` are log probabilities of the words written, from
    0 (certain) downwards: the model's own odds on what it heard. None when
    the request shape could not ask for them.
    """

    __slots__ = ("text", "average", "lowest", "languages")

    def __init__(self, text, average=None, lowest=None, languages=()):
        self.text = text
        self.average = average
        self.lowest = lowest
        self.languages = tuple(languages)

    @classmethod
    def from_payload(cls, payload):
        scores = [float(token.get("logprob", 0.0))
                  for token in payload.get("logprobs") or ()
                  if isinstance(token, dict)]
        detected = payload.get("languages") or payload.get("language") or ()
        if isinstance(detected, str):
            detected = [detected]
        codes = [str(item.get("code", "")) if isinstance(item, dict)
                 else str(item) for item in detected]
        return cls((payload.get("text") or "").strip(),
                   sum(scores) / len(scores) if scores else None,
                   min(scores) if scores else None, codes)

    def words(self):
        return len(self.text.split())


def _timeout(seconds, connect):
    import httpx
    return httpx.Timeout(seconds, connect=connect)


class CloudBackend:
    """Transcribes with OpenAI's speech-to-text API."""

    name = "cloud"

    def __init__(self, config):
        self._cfg = config
        self._cloud = config["transcription"]["cloud"]
        self._rate = int(config["audio"]["sample_rate"])

    @property
    def api_key(self):
        """Finds the key: config, then environment, then the key file.

        The key file matters more than it looks. HeySpeaky starts from a
        Startup shortcut, and a process only inherits environment variables
        that existed when it was created, so a freshly set OPENAI_API_KEY is
        invisible until the next sign-in. The file is read at request time, so
        it works straight away. It also lives outside the project folder, so
        it cannot be committed by accident or picked up by a cloud-sync
        client.
        """
        key = (self._cloud.get("api_key") or "").strip()
        if key:
            return key
        key = (os.environ.get(self._cloud["api_key_env"]) or "").strip()
        if key:
            return key
        return self._key_from_file()

    def _key_from_file(self):
        path = (self._cloud.get("api_key_file") or "").strip()
        if not path:
            return ""
        # HeySpeaky was VoiceType, then SpeakIt, and the key stayed under
        # those names. Looking there too means a rename costs nobody theirs.
        for candidate in (path,) + LEGACY_KEY_FILES:
            try:
                expanded = os.path.expandvars(os.path.expanduser(candidate))
                # utf-8-sig: PowerShell's Set-Content writes a BOM, which
                # would otherwise ride along into the Authorization header.
                with open(expanded, "r", encoding="utf-8-sig") as handle:
                    for line in handle:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            return line
            except OSError:
                logger.debug("No readable key file at %s", candidate,
                             exc_info=True)
        return ""

    def available(self):
        return bool(self.api_key)
    def _field_variants(self, language, first=None):
        """Request shapes to try, newest first. `first` moves one of the
        configured languages to the front, for a second opinion.

        The transcription API moved from a single `language` hint to a
        `languages` list and added `keywords`. That list is the whole point
        for us: naming every language you actually speak lets the model switch
        between them mid-sentence instead of committing to whichever it hears
        first. OpenAI writes form-data arrays with a trailing "[]", but the
        docs have been inconsistent through the rename, so we try the bracket
        form, then the bare name, then the old singular field, and keep the
        first one the server accepts.
        """
        configured = [str(c) for c in self._cloud.get("languages") or []]
        if first in configured:
            configured = [first] + [c for c in configured if c != first]
        codes = [language] if language else configured
        # Configured keywords come first, then the words this person has had
        # to correct, then the glue words for the languages in use. Merged
        # rather than replaced at every step: someone adding their own name
        # should not silently lose the fix for reduced German.
        codes_for_glue = [str(c) for c in self._cloud.get("languages") or []]
        keywords = [str(w) for w in self._cloud.get("keywords") or []]
        for word in dictionary.words():
            if word not in keywords:
                keywords.append(word)
        for word in _default_keywords(codes_for_glue):
            if word not in keywords:
                keywords.append(word)
        prompt = (self._cloud.get("prompt") or "").strip()
        if not prompt:
            # No prompt configured: steer with the languages instead of
            # sending nothing, which is what breaks accented speech.
            prompt = _default_prompt(configured)

        def base():
            fields = {"model": self._cloud["model"]}
            if prompt:
                fields["prompt"] = prompt
            return fields

        variants = []
        for lang_key, kw_key in (("languages[]", "keywords[]"),
                                 ("languages", "keywords")):
            fields = base()
            # How sure the model was of each word it wrote. Only the newest
            # shapes ask: whisper-1 refuses it, and that is a fallback.
            fields[lang_key.replace("languages", "include")] = ["logprobs"]
            if codes:
                fields[lang_key] = codes
            if keywords:
                fields[kw_key] = keywords
            variants.append(fields)

        # Oldest shape: one language, no keywords.
        fields = base()
        if codes:
            fields["language"] = codes[0]
        variants.append(fields)

        # Last resort: let the model work it out unaided.
        variants.append(base())
        return variants

    def transcribe(self, pcm_bytes, language):
        return self.heard(pcm_bytes, language).text

    def heard(self, pcm_bytes, language, first=None):
        """The transcript, how sure the model was, and what it heard."""
        key = self.api_key
        if not key:
            raise RuntimeError(
                "No API key. Set {} or transcription.cloud.api_key.".format(
                    self._cloud["api_key_env"]
                )
            )
        upload = pcm_to_upload(pcm_bytes, self._rate)
        return self._post(key, upload, self._field_variants(language, first))

    def _post(self, key, upload, variants):
        """Tries each request shape, retrying transient failures. `upload`
        is (file name, bytes, type), or bare WAV bytes."""
        if isinstance(upload, bytes):
            upload = ("speech.wav", upload, "audio/wav")
        last_error = "no attempt made"
        for index, fields in enumerate(variants):
            transient = 0
            while True:
                try:
                    response = link.post(
                        OPENAI_TRANSCRIBE_URL,
                        headers={"Authorization": "Bearer {}".format(key)},
                        data=fields,
                        files={"file": upload},
                        timeout=_timeout(
                            float(self._cloud["timeout"]), CONNECT_TIMEOUT),
                    )
                except Exception as exc:
                    raise CloudUnreachable(
                        "OpenAI request failed: {}".format(exc)
                    )

                if response.status_code == 200:
                    payload = response.json()
                    if index:
                        logger.info(
                            "Cloud accepted fallback shape %d: %s",
                            index, sorted(fields),
                        )
                    return Heard.from_payload(payload)

                body = response.text[:400]
                # Out of credit is a 429 too, and no retry will change it:
                # on 21 November three of them cost a dictation 25 seconds.
                # A spent limit is the same. The whole answer is read: the
                # code comes after a message that can be long.
                refusal = money_refusal(response.status_code, response.text)
                if refusal is not None:
                    raise refusal
                # Rate limits and server hiccups deserve a retry: the
                # alternative is throwing away what the user just said.
                if (response.status_code == 429
                        or response.status_code >= 500) and transient < 2:
                    delay = 0.6 * (transient + 1)
                    logger.info("OpenAI returned %s; retrying in %.1fs",
                                response.status_code, delay)
                    transient += 1
                    time.sleep(delay)
                    continue

                last_error = "{}: {}".format(response.status_code, body)
                if response.status_code == 400 and index < len(variants) - 1:
                    logger.info(
                        "OpenAI rejected request shape %d (%s); trying an "
                        "older one", index, body[:120],
                    )
                    break                      # next variant
                raise RuntimeError("OpenAI API {}".format(last_error))
        raise RuntimeError("OpenAI API {}".format(last_error))


class Router:
    """Picks a backend per recording and falls back to local if cloud fails."""

    def __init__(self, engine, config):
        self._cfg = config
        self.local = LocalBackend(engine, config)
        self.cloud = CloudBackend(config)
        # Why the last call did not use the cloud, for the overlay to show.
        # Silent degradation is the thing to avoid here: local is much weaker
        # on Russian and German, so being dropped onto it without being told
        # looks like the app suddenly got worse for no reason.
        self.last_fallback = ""
        # What the pill should say about it, when it is something only the
        # person can fix. A finished pill shows no words, so without this the
        # reason reached only the problem report and the text simply got
        # worse.
        self.last_warning = ""
        # What each step of the last call wrote and how long it took, for
        # the archive (archive.py). It holds the words, so it is never
        # logged and never goes into a problem report.
        self.trace = {}
        self._offline_until = 0.0

    @property
    def preferred(self):
        return self._cfg["transcription"]["backend"]

    def keep_warm(self, still_recording):
        """Opens the connection to OpenAI while somebody is still speaking,
        when the cloud is what will hear them. See heyspeaky/link.py."""
        if self.preferred == "cloud" and self.cloud.available():
            link.keep_warm(still_recording)

    def transcribe(self, pcm_bytes, language):
        """Returns (text, backend_name_used), with corrections applied.

        The user's dictionary is applied here rather than inside a backend, so
        it reaches local transcription too - which needs it more, being the
        weaker of the two on exactly the words people end up correcting.
        """
        self.trace = {}
        text, backend, heard_in = self._transcribe(pcm_bytes, language)
        if backend == "cloud" and not language:
            started = time.monotonic()
            checked = self._check_alphabet(text, heard_in)
            took = time.monotonic() - started
            if took > 0.05 or checked != text:
                # The check asked the model: what it cost, and what it made.
                self.trace["alphabet"] = {"seconds": round(took, 2),
                                          "text": checked}
            text = checked
        # Naming the words in the request gets most of the way and not always
        # all of it: the measurement that put them there also showed a Kazakh
        # letter failing to survive into a Russian sentence. What the user has
        # spelled out is applied after the model has had its say. See
        # heyspeaky/dictionary.py.
        final = dictionary.apply(text)
        if final != text:
            self.trace["dictionary"] = final
        return final, backend

    def _check_alphabet(self, text, heard_in=()):
        """A word written in the wrong alphabet, put back in its own. Only
        with the cloud, which is already online with a key, and not when a
        language is pinned: then the user has said which one it is.
        `heard_in` is the languages the cloud said it heard.
        See heyspeaky/alphabet.py."""
        cloud = self._cfg["transcription"]["cloud"]
        if not cloud.get("alphabet_check", True):
            return text
        languages = [str(code) for code in cloud.get("languages") or []]
        return alphabet.check(
            text, languages, _LANGUAGE_NAMES, self.cloud.api_key,
            cloud.get("alphabet_model") or alphabet.MODEL,
            dictionary.words(), heard=heard_in)

    def _ask_cloud(self, pcm_bytes, language):
        """The cloud's answer, as a Heard: asked again if it was unsure."""
        started = time.monotonic()
        heard = self.cloud.heard(pcm_bytes, language)
        self.trace["cloud"] = {
            "seconds": round(time.monotonic() - started, 2),
            "languages": list(heard.languages), "average": heard.average,
            "lowest": heard.lowest, "text": heard.text}
        if heard.average is not None:
            # Numbers and language codes, never the words.
            logger.info("Cloud heard %s, sure on average %.3f, least sure "
                        "word %.2f", ",".join(heard.languages) or "?",
                        heard.average, heard.lowest)
        if language or heard.average is None or heard.average >= UNSURE_BELOW:
            return heard
        return self._second_opinion(pcm_bytes, heard)

    def _second_opinion(self, pcm_bytes, heard):
        """The model was unsure: ask again with another language first.

        The owner said "Они потребуют одинаковое количество энергий" and got
        "Альбатрос бродит акварель часовой мерки": a short, quiet Russian
        phrase that the model, with Kazakh first in the list, heard as
        Kazakh. The model's own odds are what can catch that, so when they
        are low the same audio goes out again with the next languages first,
        both at once, and the answer the model is surest of is kept - unless
        it is shorter. A shorter answer can look surer for having less in
        it: asked with Kazakh first, one drill sentence came back without
        its English half, and surer than the whole one.
        """
        from concurrent.futures import ThreadPoolExecutor

        configured = [str(code) for code in
                      self._cfg["transcription"]["cloud"].get("languages")
                      or []]
        others = [code for code in configured
                  if code not in heard.languages][:2]
        if not others:
            return heard
        started = time.monotonic()
        with ThreadPoolExecutor(len(others)) as pool:
            answers = list(pool.map(
                lambda code: self._ask_with_first(pcm_bytes, code), others))
        took = time.monotonic() - started
        best, kept = heard, ""
        for code, answer in zip(others, answers):
            if answer is None or answer.average is None:
                continue
            if answer.words() < 0.8 * heard.words():
                continue
            if answer.average > best.average:
                best, kept = answer, code
        logger.info("Unsure (average %.3f, heard %s): asked again with %s "
                    "first; kept %s", heard.average,
                    ",".join(heard.languages) or "?", " and ".join(others),
                    "the {} one ({:.3f})".format(kept, best.average)
                    if kept else "the first answer")
        self.trace["asked_again"] = {
            "seconds": round(took, 2), "kept": kept,
            "answers": [{"first": code,
                         "average": getattr(answer, "average", None),
                         "text": getattr(answer, "text", None)}
                        for code, answer in zip(others, answers)]}
        return best

    def _ask_with_first(self, pcm_bytes, code):
        try:
            return self.cloud.heard(pcm_bytes, "", first=code)
        except Exception as exc:
            logger.info("Asking again with %s first failed: %s", code,
                        type(exc).__name__)
            return None

    def _transcribe(self, pcm_bytes, language):
        self.last_fallback = ""
        self.last_warning = ""
        if self.preferred == "cloud":
            if not self.cloud.available():
                self.last_fallback = "no API key"
                self.last_warning = "No key: local"
                logger.warning("Cloud backend has no API key; using local")
            elif time.monotonic() < self._offline_until:
                self.last_fallback = "offline"
                self.last_warning = OFFLINE_SAY
                logger.info(
                    "Skipping the cloud for another %.0fs after a connection "
                    "failure", self._offline_until - time.monotonic(),
                )
            else:
                try:
                    heard = self._ask_cloud(pcm_bytes, language)
                    self._offline_until = 0.0
                    return heard.text, "cloud", heard.languages
                except CloudUnreachable as exc:
                    self._offline_until = (
                        time.monotonic() + OFFLINE_MEMO_SECONDS
                    )
                    self.last_fallback = "offline"
                    self.last_warning = OFFLINE_SAY
                    logger.warning("Cloud unreachable: %s", exc)
                    if not self._cfg["transcription"]["cloud"][
                        "fallback_to_local"
                    ]:
                        raise
                except NoCredit as exc:
                    # Said in so many words, so the person knows it is the
                    # account or the key and not the app, where "cloud error"
                    # told him nothing.
                    self.last_fallback = exc.reason
                    self.last_warning = exc.say
                    logger.warning("%s; using local", exc)
                    if not self._cfg["transcription"]["cloud"][
                        "fallback_to_local"
                    ]:
                        raise
                except Exception as exc:
                    self.last_fallback = "cloud error"
                    self.last_warning = "Cloud error: local"
                    logger.warning("Cloud transcription failed: %s", exc)
                    if not self._cfg["transcription"]["cloud"][
                        "fallback_to_local"
                    ]:
                        raise
        started = time.monotonic()
        text = self.local.transcribe(pcm_bytes, language)
        self.trace["local"] = {"seconds": round(time.monotonic() - started, 2),
                               "text": text}
        return text, "local", ()
