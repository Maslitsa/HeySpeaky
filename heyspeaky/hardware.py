"""Works out what hardware to run the local model on.

Kept out of engine.py on purpose: this is a pure function with no dependency
on RealtimeSTT or PyTorch beyond an optional probe, so it can be imported and
tested on a machine with neither installed.
"""

import logging

logger = logging.getLogger("heyspeaky.hardware")


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
