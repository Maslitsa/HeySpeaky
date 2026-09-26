"""Works out what hardware to run the local model on.

Kept out of engine.py on purpose: this is a pure function with no dependency
on RealtimeSTT or PyTorch beyond an optional probe, so it can be imported and
tested on a machine with neither installed.
"""

import contextlib
import logging
import os

logger = logging.getLogger("heyspeaky.hardware")

# The most threads the local model is given. Measured only up to sixteen,
# the most this laptop has; past that it is a guess, so it stops there.
MOST_THREADS = 16


def resolve_hardware(device, compute_type):
    """Turns "auto" into a concrete device and compute type.

    The default used to be a hardcoded cpu/int8, which quietly wasted an
    NVIDIA card if the machine had one. Whisper on a GPU is several times
    faster, which is the difference between a bigger model being usable and
    being unusable.

    Detection is deliberately cheap and forgiving: torch may be missing a CUDA
    build, the driver may be too old, or cuDNN may be absent, and none of that
    should stop the app from starting. Anything unexpected means cpu.
    """
    if device == "auto":
        device = "cpu"
        try:
            import torch

            if torch.cuda.is_available() and torch.cuda.device_count() > 0:
                device = "cuda"
                logger.info("CUDA available: %s", torch.cuda.get_device_name(0))
        except Exception:
            logger.debug("No usable CUDA device", exc_info=True)

    if compute_type == "auto":
        # float16 is the standard GPU choice; int8 is what makes CPU bearable.
        compute_type = "float16" if device == "cuda" else "int8"

    return device, compute_type


def worker_threads():
    """How many threads the local model gets on a processor: all of them.

    faster-whisper uses four unless told otherwise, and RealtimeSTT, which
    makes the model, has no way to tell it. Measured on the owner's laptop
    (16 threads, the small model, three clips twice): 8.4 s a clip with the
    default four, 6.3 s with eight, 6.0 s with sixteen.
    """
    return max(1, min(os.cpu_count() or 4, MOST_THREADS))


@contextlib.contextmanager
def threads_for_the_worker(device):
    """Gives the transcription worker all the threads while it is made.

    The worker is a separate process that copies this one's environment as
    it starts, and faster-whisper reads OMP_NUM_THREADS when it is given no
    number of its own. Set only while the worker starts, so nothing in this
    process changes, and left alone where somebody set it themselves.
    """
    if device != "cpu" or "OMP_NUM_THREADS" in os.environ:
        yield
        return
    os.environ["OMP_NUM_THREADS"] = str(worker_threads())
    try:
        yield
    finally:
        os.environ.pop("OMP_NUM_THREADS", None)
