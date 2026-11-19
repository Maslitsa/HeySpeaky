"""Choosing the model that transcribes on this laptop.

The owner wanted people to choose for themselves rather than have it picked
for them: a bigger model hears better and is slower and heavier, and that is
a trade only the person dictating can make. The installer still picks a
sensible one - base, or large-v3-turbo with a usable graphics card - and the
tray panel lists the rest with what each costs.

Sizes are the download, read off Hugging Face on 25 September 2026. The
speeds are only what was measured on the owner's laptop, a Ryzen 7 7730U
with no graphics card: small 4-7 s a sentence, large-v3-turbo 17-19 s.
"""

import logging
import os
import threading
import time

logger = logging.getLogger("heyspeaky.localmodels")

# name, label, download in MB, what to expect
MODELS = (
    ("tiny", "Tiny", 78, "fastest, makes the most mistakes"),
    ("base", "Base", 148, "fast, the usual choice"),
    ("small", "Small", 486, "better, a few seconds a sentence"),
    ("medium", "Medium", 1531, "good, slow without a graphics card"),
    ("large-v3-turbo", "Large v3 Turbo", 1622,
     "the best, slow without a graphics card"),
)
NAMES = tuple(model[0] for model in MODELS)


def label(name):
    for model in MODELS:
        if model[0] == name:
            return model[1]
    return name


def size_text(megabytes):
    if megabytes >= 1000:
        return "{:.1f} GB".format(megabytes / 1000.0)
    return "{} MB".format(megabytes)


def _repo(name):
    from faster_whisper.utils import _MODELS
    return _MODELS.get(name, name)


def _cache_folder(name, cache_dir):
    """Where Hugging Face keeps this model's files while and after it
    downloads them."""
    root = cache_dir or os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.environ.get("HF_HOME") or os.path.join(
            os.path.expanduser("~"), ".cache", "huggingface"), "hub")
    return os.path.join(root, "models--" + _repo(name).replace("/", "--"))


def downloaded(name, cache_dir=None):
    """Whether the model is on disk already, without touching the network."""
    try:
        from faster_whisper.utils import download_model
        download_model(name, local_files_only=True, cache_dir=cache_dir)
        return True
    except Exception:
        return False


def _bytes_so_far(folder):
    total = 0
    for base, _dirs, files in os.walk(os.path.join(folder, "blobs")):
        for file_name in files:
            try:
                total += os.path.getsize(os.path.join(base, file_name))
            except OSError:
                pass
    return total


class LocalModels(object):
    """The model this laptop uses, and any download under way.

    `on_chosen` is told the name once a model is on disk and chosen, so the
    engine can load it. Choosing one that is not downloaded yet downloads it
    first, on its own thread, and `state` says how far it has got.
    """

    def __init__(self, config, on_chosen, save,
                 is_downloaded=downloaded, fetch=None):
        self._config = config
        self._on_chosen = on_chosen
        self._save = save
        self._is_downloaded = is_downloaded
        self._fetch = fetch or self._download
        self._lock = threading.Lock()
        self._busy = ""
        self._progress = 0.0
        self._failed = ""
        self._have = {}
        self._checked_at = 0.0

    @property
    def current(self):
        return self._config["model"].get("final") or "base"

    def _cache_dir(self):
        return self._config["model"].get("download_root") or None

    def state(self):
        """What the tray panel shows. Which models are on disk is looked up
        at most every few seconds: the panel asks several times a second."""
        now = time.monotonic()
        if now - self._checked_at > 5.0:
            self._checked_at = now
            have = {}
            for name in NAMES:
                try:
                    have[name] = bool(self._is_downloaded(
                        name, self._cache_dir()))
                except Exception:
                    have[name] = False
            self._have = have
        with self._lock:
            return {"current": self.current, "have": dict(self._have),
                    "busy": self._busy, "progress": self._progress,
                    "failed": self._failed}

    def choose(self, name):
        """Switches to `name`, downloading it first if it has to."""
        if name not in NAMES:
            logger.warning("No local model called %r", name)
            return
        with self._lock:
            if self._busy:
                logger.info("Still downloading %s; %s has to wait",
                            self._busy, name)
                return
            self._failed = ""
        if name == self.current and self._is_downloaded(name,
                                                        self._cache_dir()):
            return
        if self._is_downloaded(name, self._cache_dir()):
            self._use(name)
            return
        with self._lock:
            self._busy, self._progress = name, 0.0
        threading.Thread(target=self._download_then_use, args=(name,),
                         name="model-download", daemon=True).start()

    def _use(self, name):
        self._config["model"]["final"] = name
        self._save()
        self._checked_at = 0.0
        logger.info("Local model is now %s", name)
        self._on_chosen(name)

    def _download_then_use(self, name):
        started = time.monotonic()
        try:
            self._fetch(name)
        except Exception as exc:
            logger.warning("Could not download the %s model: %s", name, exc)
            with self._lock:
                self._busy, self._failed = "", name
            return
        logger.info("Downloaded the %s model in %.0fs", name,
                    time.monotonic() - started)
        with self._lock:
            self._busy, self._progress = "", 1.0
        self._use(name)

    def _download(self, name):
        """faster-whisper's own download, with the files watched as they
        arrive, because it reports no progress of its own."""
        from faster_whisper.utils import download_model
        expected = dict((model[0], model[2]) for model in MODELS)[name] * 1e6
        folder = _cache_folder(name, self._cache_dir())
        done = threading.Event()

        def watch():
            while not done.wait(0.5):
                share = _bytes_so_far(folder) / expected
                with self._lock:
                    self._progress = max(self._progress, min(0.99, share))

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        try:
            download_model(name, cache_dir=self._cache_dir())
        finally:
            done.set()
