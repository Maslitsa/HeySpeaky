"""Microphone capture.

The stream is opened only while a recording is active, so Windows' "app is
using your microphone" indicator is an honest signal that we are listening.
"""

import logging
import math
import threading

import numpy as np
import pyaudio

logger = logging.getLogger("heyspeaky.mic")

# Maps RMS in dBFS onto the 0..1 range the meter draws.
_DB_FLOOR = -58.0
_DB_CEIL = -12.0


def _level_from_chunk(data):
    """Converts a PCM16 chunk into a 0..1 loudness for the meter."""
    samples = np.frombuffer(data, dtype=np.int16)
    if samples.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    if rms <= 0:
        return 0.0
    db = 20.0 * math.log10(rms / 32768.0)
    if db <= _DB_FLOOR:
        return 0.0
    if db >= _DB_CEIL:
        return 1.0
    return (db - _DB_FLOOR) / (_DB_CEIL - _DB_FLOOR)


class Microphone:
    """Reads mono 16-bit audio and pushes chunks plus a level to callbacks."""

    def __init__(self, config, on_chunk, on_level, on_error=None):
        self._sample_rate = int(config["sample_rate"])
        self._chunk_size = int(config["chunk_size"])
        self._device_index = config.get("input_device_index")
        self._on_chunk = on_chunk
        self._on_level = on_level
        self._on_error = on_error

        self._pa = None
        self._stream = None
        self._thread = None
        self._running = threading.Event()
        self._lock = threading.Lock()

    def start(self):
        """Opens the input stream and begins delivering chunks."""
        with self._lock:
            if self._running.is_set():
                return True
            try:
                self._pa = pyaudio.PyAudio()
                self._stream = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self._sample_rate,
                    input=True,
                    frames_per_buffer=self._chunk_size,
                    input_device_index=self._device_index,
                )
            except Exception as exc:  # PyAudio raises bare OSError/IOError
                logger.exception("Could not open the microphone")
                self._teardown()
                if self._on_error:
                    self._on_error(str(exc))
                return False

            self._running.set()
            self._thread = threading.Thread(
                target=self._read_loop, name="mic-read", daemon=True
            )
            self._thread.start()
            logger.info("Microphone opened at %d Hz: %s",
                        self._sample_rate, self._device_name())
            return True

    def _device_name(self):
        """Which microphone this is, for the log a problem report includes."""
        try:
            if self._device_index is None:
                info = self._pa.get_default_input_device_info()
            else:
                info = self._pa.get_device_info_by_index(self._device_index)
            # One line: Bluetooth drivers put line breaks in device names.
            return "{} (native {:.0f} Hz)".format(
                " ".join(str(info.get("name", "?")).split()),
                float(info.get("defaultSampleRate", 0)))
        except Exception:
            return "unknown device"

    def stop(self):
        """Stops delivery and closes the stream."""
        with self._lock:
            if not self._running.is_set():
                return
            self._running.clear()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        with self._lock:
            self._teardown()
        logger.info("Microphone closed")

    def _teardown(self):
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                logger.debug("Error closing stream", exc_info=True)
            self._stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                logger.debug("Error terminating PyAudio", exc_info=True)
            self._pa = None
        self._thread = None

    def _read_loop(self):
        stream = self._stream
        while self._running.is_set() and stream is not None:
            try:
                data = stream.read(
                    self._chunk_size, exception_on_overflow=False
                )
            except Exception as exc:
                if self._running.is_set():
                    logger.warning("Microphone read failed: %s", exc)
                    if self._on_error:
                        self._on_error(str(exc))
                break
            if not data:
                continue
            try:
                self._on_chunk(data)
                self._on_level(_level_from_chunk(data))
            except Exception:
                logger.exception("Audio callback failed")


def list_input_devices():
    """Returns (index, name) for every device that can record."""
    devices = []
    pa = pyaudio.PyAudio()
    try:
        for index in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(index)
            if int(info.get("maxInputChannels", 0)) > 0:
                devices.append((index, str(info.get("name", "?"))))
    finally:
        pa.terminate()
    return devices
