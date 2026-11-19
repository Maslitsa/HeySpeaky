"""RealtimeSTT wrapper.

The recorder is driven entirely by hand: use_microphone=False means it only
ever sees audio we hand it, so it can never start listening on its own.

RealtimeSTT is used for the microphone pipeline and the voice activity
detection that ends a latched recording. There is no live preview text: the
small model that produced it was never close to the final transcript, and on a
weak CPU it competed with the recording. It does *not* produce the final
transcript either: the app keeps its own copy of the
captured audio and decides how to transcribe it (locally per segment, or in
the cloud). `transcribe_audio` exposes the already-loaded local model for that,
so no second copy of the weights is needed.
"""

import logging
import multiprocessing
import os
import queue
import threading
import time

from RealtimeSTT import AudioToTextRecorder

from .hardware import resolve_hardware, threads_for_the_worker

logger = logging.getLogger("heyspeaky.engine")

# Effectively "never auto-stop", used for push-to-talk.
_NO_AUTO_STOP = 3600.0


class TranscriptionEngine:
    """Owns the AudioToTextRecorder: capture and VAD."""

    def __init__(self, config, on_ready, on_error, on_auto_stop):
        self._config = config
        self._model_cfg = config["model"]
        self._rec_cfg = config["recording"]

        self._on_ready = on_ready
        self._on_error = on_error
        self._on_auto_stop = on_auto_stop

        self._recorder = None
        self._ready = threading.Event()
        self._shutdown = threading.Event()
        self._lock = threading.RLock()

        self._recording = False
        self._active = False

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        """Builds the recorder on a background thread (model load is slow)."""
        threading.Thread(
            target=self._initialise, name="engine-init", daemon=True
        ).start()

    @property
    def ready(self):
        return self._ready.is_set()

    @property
    def recording(self):
        return self._recording

    @property
    def detected_language(self):
        """Language of the most recent transcription, or None."""
        return getattr(self._recorder, "detected_language", None)

    def _initialise(self):
        """Loads the models, retrying offline and then with backoff.

        HeySpeaky starts from a Startup shortcut, which fires before Wi-Fi is
        up. faster-whisper contacts Hugging Face to check the model revision
        even when the weights are already cached, so a cold boot used to fail
        with "Server disconnected" and leave the app loaded but useless. The
        weights do not change under us, so the first retry just forbids the
        network and uses what is on disk.

        The same loop also covers the GPU. Detecting a CUDA device is not the
        same as being able to use it, because the driver may be too old or
        cuDNN may be missing, and either shows up only when the model loads.
        So a machine that resolves to cuda gets cpu as a second candidate
        rather than an error.
        """
        device, compute_type = resolve_hardware(
            self._model_cfg["device"], self._model_cfg["compute_type"]
        )
        hardware = [(device, compute_type)]
        if device != "cpu":
            hardware.append(("cpu", "int8"))

        env_attempts = [
            ("normal", {}),
            ("offline", {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}),
        ]
        last_error = None
        for hw_index, (dev, ctype) in enumerate(hardware):
            for index, (label, env) in enumerate(env_attempts):
                previous = {k: os.environ.get(k) for k in env}
                os.environ.update(env)
                try:
                    if self._try_initialise(dev, ctype):
                        return
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "Model load attempt (%s on %s) failed: %s",
                        label, dev, exc,
                    )
                    self._reap_workers()
                finally:
                    for key, value in previous.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value
                if index + 1 < len(env_attempts):
                    time.sleep(1.0)
            if hw_index + 1 < len(hardware):
                logger.warning(
                    "Falling back from %s to cpu for model loading", dev
                )

        logger.error("All model load attempts failed")
        self._on_error("Model load failed: {}".format(last_error))

    def _try_initialise(self, device, compute_type):
        """Builds the recorder. Returns True, or raises for the caller."""
        model = self._model_cfg
        logger.info(
            "Loading model %s on %s/%s", model["final"], device, compute_type
        )
        started = time.monotonic()
        with threads_for_the_worker(device):
            self._recorder = self._new_recorder(model, device, compute_type)
        # Nothing may auto-start; we are the only source of audio.
        self._recorder.start_recording_on_voice_activity = False
        self._recorder.stop_recording_on_voice_deactivity = False

        self._ready.set()
        logger.info("Models ready in %.1fs", time.monotonic() - started)
        self._on_ready()
        return True

    def _new_recorder(self, model, device, compute_type):
        return AudioToTextRecorder(
            model=model["final"],
            language=model["language"] or "",
            device=device,
            compute_type=compute_type,
            download_root=model["download_root"],
            initial_prompt=model["initial_prompt"] or None,
            beam_size=int(model["beam_size"]),
            # We supply the audio ourselves.
            use_microphone=False,
            # No console spinner: this process has no console.
            spinner=False,
            no_log_file=True,
            level=logging.WARNING,
            # Off, so the small preview model is never loaded at all.
            enable_realtime_transcription=False,
            # Manual start/stop must always be honoured immediately.
            min_length_of_recording=0.0,
            min_gap_between_recordings=0.0,
            post_speech_silence_duration=_NO_AUTO_STOP,
            silero_sensitivity=float(self._rec_cfg["silero_sensitivity"]),
            # Deliberately NOT passing silero_use_onnx: setting it either
            # way selects RealtimeSTT's legacy VAD backend, which calls
            # torch.hub.load() and prompts on stdin to trust the repo.
            # With no console that raises EOFError and init dies. Leaving
            # it unset picks the packaged ONNX model, which needs no
            # download and no prompt.
            webrtc_sensitivity=int(self._rec_cfg["webrtc_sensitivity"]),
            on_recording_stop=self._handle_recording_stop,
            # Callbacks must not run on the recorder thread: closing
            # the microphone joins a thread and would stall it.
            start_callback_in_new_thread=True,
            # Leave punctuation to Whisper rather than forcing a period
            # onto every fragment.
            ensure_sentence_ends_with_period=False,
            ensure_sentence_starting_uppercase=True,
        )

    @staticmethod
    def _reap_workers():
        """Terminates any transcription child process still hanging around.

        RealtimeSTT runs final transcription in a non-daemon child process. If
        one outlives us, Python blocks joining it at interpreter exit, and
        with no console that looks like the app simply never quits.
        """
        for child in multiprocessing.active_children():
            try:
                child.terminate()
                child.join(timeout=2)
            except Exception:
                logger.debug("Could not reap %s", child, exc_info=True)

    def reload(self):
        """Builds the recorder again, for a local model chosen in the tray.

        RealtimeSTT takes its model once, when the recorder is made, so a new
        model means a new recorder. Until it is ready, Ctrl+Alt says the
        models are loading, as it does at startup. Never while recording:
        the caller checks.
        """
        with self._lock:
            recorder, self._recorder = self._recorder, None
            self._ready.clear()
            self._recording = self._active = False
        if recorder is not None:
            try:
                recorder.shutdown()
            except Exception:
                logger.debug("Recorder shutdown raised", exc_info=True)
        self._reap_workers()
        self.start()

    def shutdown(self):
        """Releases the recorder and its worker process."""
        self._shutdown.set()
        recorder = self._recorder
        if recorder is not None:
            try:
                recorder.shutdown()
            except Exception:
                logger.debug("Recorder shutdown raised", exc_info=True)
        self._reap_workers()

    # -- recording control -------------------------------------------------

    def _apply_stop_rules(self, latched):
        """Points the recorder at either silence-stop or manual-stop only."""
        recorder = self._recorder
        timeout = float(self._rec_cfg["latch_silence_timeout"])
        if latched and timeout > 0:
            recorder.post_speech_silence_duration = timeout
            recorder.stop_recording_on_voice_deactivity = True
        else:
            recorder.post_speech_silence_duration = _NO_AUTO_STOP
            recorder.stop_recording_on_voice_deactivity = False

    def begin(self, latched):
        """Starts a recording. latched enables stop-on-silence."""
        if not self.ready:
            return False
        with self._lock:
            self._active = True
            self._apply_stop_rules(latched)
            self._recorder.start()
            self._recording = True
        logger.info("Recording started (latched=%s)", latched)
        return True

    def set_latched(self, latched):
        """Switches an in-flight recording between hold and latched rules."""
        with self._lock:
            if not self._recording or self._recorder is None:
                return
            self._apply_stop_rules(latched)

    def end(self):
        """Stops the recording. The caller transcribes its own audio copy."""
        with self._lock:
            if not self._active or self._recorder is None:
                return
            self._active = False
            self._recording = False
            self._recorder.stop_recording_on_voice_deactivity = False
            self._recorder.stop()
            self._drain_recorded_audio()
        logger.info("Recording stopped")

    def _drain_recorded_audio(self):
        """Throws away the queued recording RealtimeSTT would transcribe.

        We never call text(), so without this the queue would grow by one
        recording every time you dictate.
        """
        recorder = self._recorder
        try:
            while True:
                recorder.recorded_audio_queue.get_nowait()
        except queue.Empty:
            pass
        except Exception:
            logger.debug("Could not drain the recording queue", exc_info=True)

    def feed(self, chunk):
        """Hands one PCM16 chunk to the recorder."""
        recorder = self._recorder
        if recorder is None or not self._recording:
            return
        try:
            recorder.feed_audio(chunk)
        except Exception:
            logger.debug("feed_audio failed", exc_info=True)

    # -- transcription -----------------------------------------------------

    def set_language(self, code):
        """Pins the language for later transcriptions, or "" to auto-detect."""
        self._model_cfg["language"] = code or ""
        recorder = self._recorder
        if recorder is not None:
            recorder.language = code or ""
        logger.info("Language set to %r", code or "auto")

    def transcribe_audio(self, audio, language=""):
        """Transcribes a float32 array on the already-loaded local model."""
        recorder = self._recorder
        if recorder is None or audio is None or len(audio) == 0:
            return ""
        with self._lock:
            recorder.language = language or ""
            try:
                return (
                    recorder.perform_final_transcription(audio) or ""
                ).strip()
            except Exception:
                logger.exception("Local transcription failed")
                raise

    # -- callbacks ---------------------------------------------------------

    def _handle_recording_stop(self):
        """Fires for both our stop() and the recorder's own silence timeout."""
        with self._lock:
            if not self._active:
                # end() already claimed this recording; nothing to do.
                return
            self._active = False
            self._recording = False
            self._drain_recorded_audio()
        logger.info("Recorder auto-stopped on silence")
        self._on_auto_stop()
