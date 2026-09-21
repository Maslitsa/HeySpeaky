"""HeySpeaky controller.

Threads in play:

  main         Tk event loop, owns the overlay and drains the UI queue
  keyboard     the low-level hook, which only ever hands work to other threads
  mic-read     PyAudio reads, feeding the recorder and the level meter
  engine-*     model load and final transcription
  tray         the pystray message loop

Everything that touches the overlay goes through `post()` so it runs on the
Tk thread.
"""

import ctypes
import logging
import logging.handlers
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk

import numpy as np
import webrtcvad

from . import config as config_module
from . import diagnostics
from . import updates
from . import usage
from . import output
from . import sound
from . import languages
from .engine import TranscriptionEngine
from .hotkey import HotkeyListener
from .mic import Microphone
from .overlay import Overlay, enable_dpi_awareness
from .transcribe import Router
from .tray import Tray
from .winjob import join_kill_on_close

logger = logging.getLogger("heyspeaky")

IDLE = "idle"
RECORDING_HOLD = "recording_hold"
RECORDING_LATCHED = "recording_latched"
TRANSCRIBING = "transcribing"

MUTEX_NAME = "Global\\HeySpeaky.SingleInstance"


def _claim_single_instance():
    """Returns False if another HeySpeaky is already running."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True
    # ERROR_ALREADY_EXISTS
    if kernel32.GetLastError() == 183:
        return False
    _claim_single_instance.handle = handle
    return True


def setup_logging(level_name):
    """Sends logs to a rotating file; there is no console to print to."""
    config_module.LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        config_module.LOG_DIR / "heyspeaky.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)-18s %(message)s"
        )
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))
    root_logger.addHandler(handler)


class App:
    """Owns the state machine that turns key events into inserted text."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.state = IDLE
        self._state_lock = threading.RLock()
        # Serialises hotkey transitions. Opening the microphone takes a
        # moment, and a quick tap must not be processed before the recording
        # it belongs to has finished starting.
        self._transition_lock = threading.RLock()
        self._ui_queue = queue.Queue()
        self._recording_started = 0.0
        self._peak_level = 0.0
        self._consume_release = False
        self._max_timer = None
        self._quitting = False

        self.root = tk.Tk()
        self.root.title("HeySpeaky")
        self.overlay = Overlay(
            self.root,
            cfg["overlay"],
            on_cancel=self._on_button_cancel,
            on_accept=self._on_button_accept,
        )

        self.engine = TranscriptionEngine(
            cfg,
            on_ready=self._on_ready,
            on_error=self._on_error,
            on_auto_stop=self._on_auto_stop,
        )
        # We keep our own copy of the captured audio so the transcript can be
        # produced per segment, or sent to the cloud, rather than being tied
        # to RealtimeSTT's one-language-per-utterance final pass.
        self.router = Router(self.engine, cfg)
        # The last few dictations, for a problem report. Memory only.
        self.recent = diagnostics.Recent()
        self._held_seconds = 0.0
        self._audio_chunks = []
        self._audio_lock = threading.Lock()
        self._sample_rate = int(cfg["audio"]["sample_rate"])
        # WebRTC VAD only accepts 10/20/30 ms frames at 8/16/32/48 kHz.
        self._vad_frame_bytes = int(self._sample_rate * 0.02) * 2
        self._vad = self._make_vad()
        self._vad_buffer = bytearray()
        self._speech_run = 0
        self._speech_run_max = 0

        self.mic = Microphone(
            cfg["audio"],
            on_chunk=self._on_chunk,
            on_level=self._on_level,
            on_error=self._on_mic_error,
        )
        self.hotkey = HotkeyListener(
            cfg["hotkey"],
            on_engage=self._on_engage,
            on_tap=self._on_tap,
            on_hold_release=self._on_hold_release,
            on_cancel=self._on_cancel,
            on_latch=self._on_latch,
        )
        # A config.json edited by hand before the tray could add languages can
        # name a language in the menu and not in the list, or the other way.
        if languages.reconcile(cfg):
            config_module.save(cfg)
        self.tray = Tray(
            config_module.CONFIG_PATH,
            config_module.LOG_DIR,
            on_toggle=self._on_tray_toggle,
            on_pause=self._on_tray_pause,
            on_quit=self._on_tray_quit,
            on_language=self._on_tray_language,
            language=cfg["model"]["language"],
            languages=cfg["transcription"]["cloud"]["languages"],
            on_toggle_language=self._on_tray_toggle_language,
            on_backend=self._on_tray_backend,
            backend=cfg["transcription"]["backend"],
            on_report=self._on_tray_report,
            usage_text=lambda: usage.describe(self.cfg),
            on_update=self._on_tray_update,
        )

    # -- speech detection --------------------------------------------------

    def _make_vad(self):
        """Builds the WebRTC VAD, or None if this sample rate is unsupported."""
        if self._sample_rate not in (8000, 16000, 32000, 48000):
            logger.warning(
                "Sample rate %d is not supported by WebRTC VAD; the "
                "silence guard is disabled",
                self._sample_rate,
            )
            return None
        try:
            return webrtcvad.Vad(
                int(self.cfg["recording"]["vad_aggressiveness"])
            )
        except Exception:
            logger.exception("Could not create the VAD; silence guard is off")
            return None

    def _on_chunk(self, chunk):
        """Feeds the recorder, keeps the audio, and tracks the speech runs."""
        self.engine.feed(chunk)
        with self._audio_lock:
            self._audio_chunks.append(chunk)
        if self._vad is None:
            return
        self._vad_buffer.extend(chunk)
        size = self._vad_frame_bytes
        while len(self._vad_buffer) >= size:
            frame = bytes(self._vad_buffer[:size])
            del self._vad_buffer[:size]
            try:
                speech = self._vad.is_speech(frame, self._sample_rate)
            except Exception:
                logger.debug("VAD frame rejected", exc_info=True)
                continue
            # Track the longest unbroken run: room noise scatters isolated
            # positives, speech comes in long stretches.
            if speech:
                self._speech_run += 1
                self._speech_run_max = max(
                    self._speech_run_max, self._speech_run
                )
            else:
                self._speech_run = 0

    def _had_speech(self):
        """True if the last recording contained enough speech to trust."""
        if self._vad is None:
            return True
        return self._speech_run_max >= int(
            self.cfg["recording"]["min_speech_run"]
        )

    # -- cross-thread plumbing --------------------------------------------

    def post(self, func, *args):
        """Queues a callable to run on the Tk thread."""
        self._ui_queue.put((func, args))

    def _pump(self):
        while True:
            try:
                func, args = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                func(*args)
            except Exception:
                logger.exception("UI callback failed")
        if not self._quitting:
            self.root.after(16, self._pump)

    # -- engine callbacks --------------------------------------------------

    def _on_ready(self):
        self.tray.set_status("Ready · hold Ctrl+Alt to dictate")
        logger.info("Engine ready")
        # Once a day at most, and never in the way: people install by pasting
        # a command and would otherwise never learn that a fix exists.
        updates.check_in_background(
            lambda version: self.post(self.tray.offer_update, version))

    def _on_error(self, message):
        logger.error("Engine error: %s", message)
        self.tray.set_status(message[:90])
        self.post(self.overlay.flash, "error", message[:120], "", 3.5)
        with self._state_lock:
            self.state = IDLE

    def _on_mic_error(self, message):
        logger.error("Microphone error: %s", message)
        self.post(
            self.overlay.flash, "error", "Microphone unavailable", "", 2.5
        )
        self._abort_recording()

    def _on_auto_stop(self):
        """The recorder decided the utterance ended (latched mode)."""
        with self._transition_lock:
            with self._state_lock:
                if self.state not in (RECORDING_HOLD, RECORDING_LATCHED):
                    return
            self._cancel_max_timer()
            self._held_seconds = time.monotonic() - self._recording_started
            self.mic.stop()
            self._start_transcription()

    def _on_level(self, level):
        if level > self._peak_level:
            self._peak_level = level
        self.post(self.overlay.set_level, level)

    # -- hotkey callbacks --------------------------------------------------

    def _on_engage(self):
        with self._transition_lock:
            self._engage_locked()

    def _engage_locked(self):
        with self._state_lock:
            state = self.state
        if state == RECORDING_LATCHED:
            # Second tap: finish the latched recording.
            self._consume_release = True
            self._finish_recording()
            return
        if state != IDLE:
            return
        if not self.engine.ready:
            self.post(
                self.overlay.flash,
                "error",
                "",
                "Loading speech models, one moment…",
                2.0,
            )
            return
        self._begin_recording()

    def _on_tap(self):
        with self._transition_lock:
            self._tap_locked()

    def _tap_locked(self):
        """Released quickly: keep recording hands-free."""
        if self._consume_release:
            self._consume_release = False
            return
        with self._state_lock:
            if self.state != RECORDING_HOLD:
                return
            self.state = RECORDING_LATCHED
        self.engine.set_latched(True)
        self.hotkey.set_recording_latched(True)
        logger.info("Switched to latched recording")
        self.post(
            self.overlay.set_status, "Listening · tap Ctrl+Alt to stop"
        )

    def _on_latch(self):
        """Two taps of Ctrl+Alt: start hands-free, without the hold."""
        with self._transition_lock:
            with self._state_lock:
                if self.state != IDLE:
                    return
            if not self.engine.ready:
                self.post(self.overlay.flash, "error", "",
                          "Loading speech models, one moment…", 2.0)
                return
            self._begin_recording()
            with self._state_lock:
                if self.state != RECORDING_HOLD:
                    return
                self.state = RECORDING_LATCHED
            self.engine.set_latched(True)
            self.hotkey.set_recording_latched(True)
            logger.info("Latched from the start (double tap)")

    # -- the pill's own buttons -------------------------------------------

    def _on_button_cancel(self):
        """The cross on the pill: throw this recording away."""
        self._on_cancel()

    def _on_button_accept(self):
        """The tick on the pill: finish now, whichever way it was started."""
        with self._transition_lock:
            with self._state_lock:
                if self.state not in (RECORDING_HOLD, RECORDING_LATCHED):
                    return
            # A push-to-talk recording is still holding the keys down; tell
            # the listener not to act on the release that follows.
            self._consume_release = True
            self._finish_recording()

    def _on_hold_release(self):
        with self._transition_lock:
            self._hold_release_locked()

    def _hold_release_locked(self):
        """Released after a long hold: push-to-talk ends here."""
        if self._consume_release:
            self._consume_release = False
            return
        with self._state_lock:
            if self.state not in (RECORDING_HOLD, RECORDING_LATCHED):
                return
        self._finish_recording()

    def _on_cancel(self):
        with self._transition_lock:
            with self._state_lock:
                if self.state not in (RECORDING_HOLD, RECORDING_LATCHED):
                    return
            self._abort_recording()

    # -- recording transitions --------------------------------------------

    def _begin_recording(self):
        # Reset before the microphone opens: it starts delivering chunks the
        # instant it is up, and clearing afterwards would drop the first words.
        with self._state_lock:
            self._peak_level = 0.0
            self._speech_run = 0
            self._speech_run_max = 0
            self._vad_buffer.clear()
        with self._audio_lock:
            self._audio_chunks = []

        if not self.engine.begin(latched=False):
            return
        if not self.mic.start():
            self.engine.end()
            return
        with self._state_lock:
            self.state = RECORDING_HOLD
            self._recording_started = time.monotonic()
        self._consume_release = False
        self._start_max_timer()
        self.tray.set_status("Listening…", busy=True)
        self.post(
            self.overlay.show, "listening", "Listening · release to insert"
        )

    def _finish_recording(self):
        elapsed = time.monotonic() - self._recording_started
        self._held_seconds = elapsed
        self._cancel_max_timer()
        self.mic.stop()
        too_short = elapsed < float(self.cfg["recording"]["min_seconds"])
        too_quiet = not self._had_speech()
        if too_short or too_quiet:
            logger.info(
                "Discarding recording: %.2fs, peak %.2f, speech run %d "
                "(short=%s quiet=%s)",
                elapsed,
                self._peak_level,
                self._speech_run_max,
                too_short,
                too_quiet,
            )
            self.engine.end()
            self._reset_to_idle()
            if too_quiet and not too_short:
                self.post(
                    self.overlay.flash, "error", "", "Nothing heard", 1.2
                )
            else:
                self.post(self.overlay.hide)
            return
        self.engine.end()
        self._start_transcription()

    def _abort_recording(self):
        self._cancel_max_timer()
        self.mic.stop()
        self.engine.end()
        with self._audio_lock:
            self._audio_chunks = []
        self._reset_to_idle()
        self.post(self.overlay.flash, "error", "", "Cancelled", 1.0)

    def _reset_to_idle(self):
        with self._state_lock:
            self.state = IDLE
        self.hotkey.notify_recording_finished()
        self.tray.set_status("Ready · hold Ctrl+Alt to dictate")

    # -- transcription pipeline -------------------------------------------

    def _start_transcription(self):
        """Moves to the transcribing state and works off the Tk thread."""
        with self._state_lock:
            self.state = TRANSCRIBING
        self.tray.set_status("Transcribing…", busy=True)
        self.post(self.overlay.set_state, "transcribing", "Transcribing…")
        threading.Thread(
            target=self._transcribe_and_deliver,
            name="transcribe",
            daemon=True,
        ).start()

    def _take_audio(self):
        with self._audio_lock:
            chunks = self._audio_chunks
            self._audio_chunks = []
        return b"".join(chunks)

    def _normalise(self, pcm):
        """Boosts a quiet recording before it is transcribed.

        Only ever called after the speech test has passed, because scaling the
        audio up scales the noise floor with it. Run the VAD on this and
        silence reads as continuous speech.
        """
        cfg = self.cfg["recording"]
        if not cfg.get("normalize_for_transcription", True) or not pcm:
            return pcm
        samples = np.frombuffer(pcm, dtype=np.int16)
        if samples.size == 0:
            return pcm
        peak = float(np.max(np.abs(samples))) / 32768.0
        if peak <= 0.001:
            return pcm
        target = float(cfg.get("normalize_target_peak", 0.9))
        gain = min(target / peak, float(cfg.get("normalize_max_gain", 8.0)))
        if gain <= 1.05:
            return pcm
        boosted = np.clip(
            samples.astype(np.float32) * gain, -32768, 32767
        ).astype(np.int16)
        logger.info("Boosted quiet audio: peak %.3f x%.1f", peak, gain)
        return boosted.tobytes()

    def _transcribe_and_deliver(self):
        """Transcribes the captured audio, tidies it, and inserts it."""
        pcm = self._take_audio()
        if not pcm or not self._had_speech():
            logger.info(
                "Nothing to transcribe (%d bytes, speech run %d)",
                len(pcm),
                self._speech_run_max,
            )
            self._reset_to_idle()
            self.post(self.overlay.flash, "error", "", "Nothing heard", 1.4)
            return

        raw = pcm
        pcm = self._normalise(pcm)
        language = self.cfg["model"]["language"]
        started = time.monotonic()
        try:
            text, backend = self.router.transcribe(pcm, language)
        except Exception as exc:
            logger.exception("Transcription failed")
            self._remember(raw, language, "failed", str(exc)[:80],
                           time.monotonic() - started, "")
            self._reset_to_idle()
            self.post(
                self.overlay.flash, "error", str(exc)[:120], "", 3.0
            )
            return

        self._remember(raw, language, backend, self.router.last_fallback,
                       time.monotonic() - started, text)
        logger.info("Final transcript (%s): %d chars", backend, len(text))
        self._deliver(text, backend)

    def _remember(self, pcm, language, backend, fallback, took, text):
        """Logs the numbers a problem report needs, and keeps the recording.

        No transcript text goes to the log. It stays in memory with the
        recording, and leaves only in a report someone chose to save.
        """
        held = self._held_seconds
        stats = diagnostics.audio_stats(pcm, self._sample_rate)
        logger.info(
            "Dictation: held %.1fs, captured %.1fs, peak %.0f dB, average "
            "%.0f dB, clipped %.1f%%, speech run %d, %s%s in %.1fs",
            held, stats["seconds"], stats["peak_db"], stats["rms_db"],
            stats["clipped_pct"], self._speech_run_max, backend,
            " ({})".format(fallback) if fallback else "", took,
        )
        if held > 1.0 and stats["seconds"] < held * 0.9:
            logger.warning(
                "Audio dropped: captured %.1fs of %.1fs. A busy CPU or the "
                "microphone driver lost part of the recording.",
                stats["seconds"], held,
            )
        if backend == "cloud" and stats["seconds"] > 0:
            usage.record(stats["seconds"])
            spent = usage.warning(self.cfg)
            if spent:
                self.post(self.overlay.flash, "done", "", spent, 3.0)
        self.recent.add({
            "time": time.strftime("%H:%M:%S"),
            "pcm": pcm,
            "rate": self._sample_rate,
            "held": held,
            "stats": stats,
            "speech_run": self._speech_run_max,
            "language": language,
            "backend": backend,
            "fallback": fallback,
            "took": took,
            "text": text,
        })

    def _deliver(self, text, backend):
        self._reset_to_idle()
        if not text:
            self.post(self.overlay.flash, "error", "", "Nothing heard", 1.4)
            return

        status = output.deliver(text, self.cfg["output"])
        label = {
            "inserted": "Pasted · copied",
            "copied": "Copied to clipboard",
            "empty": "Nothing heard",
        }.get(status, status)
        if backend == "cloud":
            label += " · cloud"
        elif self.router.last_fallback:
            # Say so. Local is markedly weaker on Russian and German, and a
            # silent downgrade reads as the app having got worse by itself.
            label += " · local ({})".format(self.router.last_fallback)
        state = "done" if status in ("inserted", "copied") else "error"
        if state == "done":
            settings = self.cfg.get("sound", {})
            sound.play(settings.get("finish", sound.DEFAULT),
                       float(settings.get("volume", sound.VOLUME)))
        self.post(self.overlay.flash, state, text, label)

    def _start_max_timer(self):
        self._cancel_max_timer()
        limit = float(self.cfg["recording"]["max_seconds"])
        if limit <= 0:
            return
        self._max_timer = threading.Timer(limit, self._on_max_reached)
        self._max_timer.daemon = True
        self._max_timer.start()

    def _cancel_max_timer(self):
        if self._max_timer is not None:
            self._max_timer.cancel()
            self._max_timer = None

    def _on_max_reached(self):
        logger.warning("Recording hit the length limit; stopping")
        with self._state_lock:
            if self.state not in (RECORDING_HOLD, RECORDING_LATCHED):
                return
        self._finish_recording()

    # -- tray callbacks ----------------------------------------------------

    def _on_tray_toggle(self):
        with self._transition_lock:
            self._tray_toggle_locked()

    def _tray_toggle_locked(self):
        with self._state_lock:
            state = self.state
        if state == IDLE:
            if self.engine.ready:
                self._begin_recording()
                # Started from the menu, so there is no key to release.
                with self._state_lock:
                    self.state = RECORDING_LATCHED
                self.engine.set_latched(True)
                self.hotkey.set_recording_latched(True)
                self.post(
                    self.overlay.set_status,
                    "Listening · tap Ctrl+Alt to stop",
                )
        elif state in (RECORDING_HOLD, RECORDING_LATCHED):
            self._finish_recording()

    def _on_tray_pause(self, paused):
        self.hotkey.set_paused(paused)
        if paused:
            with self._state_lock:
                busy = self.state in (RECORDING_HOLD, RECORDING_LATCHED)
            if busy:
                self._abort_recording()

    def _on_tray_language(self, code):
        """Pins or unpins the language and remembers the choice."""
        self.engine.set_language(code)
        self.cfg["model"]["language"] = code
        config_module.save(self.cfg)
        label = languages.name(code) if code else "auto-detect"
        self.tray.set_status("Ready · language: {}".format(label))
        self.post(
            self.overlay.flash, "done", "", "Language: {}".format(label), 1.4
        )

    def _on_tray_toggle_language(self, code):
        """Adds or removes one of your languages, from the tray."""
        was_pinned = self.cfg["model"]["language"]
        result = languages.toggle(self.cfg, code)
        if result == "kept":
            self.post(self.overlay.flash, "error", "",
                      "Keep at least one language", 2.0)
            return
        if was_pinned and not self.cfg["model"]["language"]:
            # The pinned language is the one that was just removed.
            self.engine.set_language("")
            self.tray.set_language("")
        config_module.save(self.cfg)
        verb = "Added" if result == "added" else "Removed"
        self.post(self.overlay.flash, "done", "",
                  "{} {}".format(verb, languages.name(code)), 1.4)
        self.tray.refresh()

    def _on_tray_backend(self, backend):
        """Switches between local and cloud transcription."""
        self.cfg["transcription"]["backend"] = backend
        config_module.save(self.cfg)
        if backend == "cloud" and not self.router.cloud.available():
            logger.warning("OpenAI selected but no API key was found")
            self.tray.set_status("OpenAI selected · no API key")
            self.post(
                self.overlay.flash,
                "error",
                "",
                "No OpenAI key yet. See the README",
                3.0,
            )
            return
        label = "OpenAI" if backend == "cloud" else "this laptop"
        self.tray.set_status("Ready · transcribing on {}".format(label))
        self.post(
            self.overlay.flash, "done", "", "Using {}".format(label), 1.4
        )

    def _on_tray_update(self):
        """Runs the installer in the folder, which replaces this copy."""
        try:
            updates.install(config_module.ROOT_DIR)
        except Exception as exc:
            logger.exception("Could not start the update")
            self.post(self.overlay.flash, "error", "",
                      "Update failed: {}".format(str(exc)[:60]), 3.0)
            return
        self.post(self.overlay.flash, "done", "",
                  "Updating. HeySpeaky will restart.", 4.0)

    def _on_tray_report(self):
        """Saves a problem report to the Desktop, off the tray thread."""
        threading.Thread(
            target=self._save_report, name="report", daemon=True
        ).start()

    def _save_report(self):
        self.post(self.overlay.flash, "transcribing", "",
                  "Saving a problem report…", 10.0)
        try:
            path = diagnostics.save_report(
                self.cfg, self.recent.items(), config_module.LOG_DIR
            )
        except Exception as exc:
            logger.exception("Could not save a problem report")
            self.post(self.overlay.flash, "error", "",
                      "Report failed: {}".format(str(exc)[:60]), 3.0)
            return
        logger.info("Problem report saved to %s", path)
        self.post(self.overlay.flash, "done", "",
                  "Report saved to your Desktop", 2.5)
        try:
            subprocess.Popen('explorer /select,"{}"'.format(path))
        except OSError:
            logger.debug("Could not show the report in Explorer",
                         exc_info=True)

    def _on_tray_quit(self):
        self.post(self.shutdown)

    # -- lifecycle ---------------------------------------------------------

    def run(self):
        self.engine.start()
        self.hotkey.start()
        self.tray.start()
        self.tray.set_status("Loading speech models…")
        self.root.after(16, self._pump)
        logger.info("HeySpeaky running")
        self.root.mainloop()

    def shutdown(self):
        if self._quitting:
            return
        self._quitting = True
        logger.info("Shutting down")
        self._cancel_max_timer()
        try:
            self.hotkey.stop()
            self.mic.stop()
            self.engine.shutdown()
            self.tray.stop()
        finally:
            try:
                self.root.destroy()
            except tk.TclError:
                pass


def main():
    cfg = config_module.load()
    setup_logging(cfg["log_level"])

    # Must happen before the engine spawns its transcription worker. If we are
    # killed without running shutdown(), this is what stops that worker being
    # orphaned to spin on a broken pipe and fill the disk.
    join_kill_on_close()

    if not _claim_single_instance():
        logger.warning("Another instance is already running; exiting")
        return 0

    enable_dpi_awareness()
    app = App(cfg)
    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()
    except Exception:
        logger.exception("Fatal error")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
