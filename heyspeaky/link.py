"""The connection to OpenAI: one, kept open, and opened while you speak.

Every request used to open its own, the transcription and the alphabet
check a second later each paying for a new connection and handshake. That
is a tenth of a second on a good line and much more on a poor one, and it
came at the worst moment: after the keys were let go, while someone waits
for the text.

So there is one client, and its connection is kept. When recording starts
it is opened then (`keep_warm`), while the person is still talking, so the
recording goes out the moment they stop. On 26 November 2026 a 37-second
dictation lost its connection in the handshake: eight seconds of waiting,
then the weaker local model wrote it ("дектовку" for "диктовку"). A
connection opened at the start has the whole of the speaking to get
through a bad moment on the line.

Measured that evening: OpenAI kept an idle connection open for 90 seconds
and more, so `KEEP_OPEN` is well inside what the server allows. The
warm-up sends no key. It asks for the model list without one, the answer
is a 401, and the connection it came over is the point.
"""

import logging
import threading
import time

logger = logging.getLogger("heyspeaky.link")

ORIGIN = "https://api.openai.com"

# Asked without a key, only to open the connection. The answer is a 401.
WARM_URL = ORIGIN + "/v1/models"

# How long an idle connection is kept. httpx's own default, five seconds,
# is shorter than most dictations, so the connection would be gone by the
# time the recording was ready to go.
KEEP_OPEN = 60.0

# While a long recording goes on, the connection is opened again this often,
# so it is never older than this when the recording goes out.
WARM_EVERY = 25.0

_lock = threading.Lock()
_client = None


def client():
    """The one client every OpenAI request goes through."""
    global _client
    with _lock:
        if _client is None:
            import httpx
            _client = httpx.Client(limits=httpx.Limits(
                max_connections=8, max_keepalive_connections=4,
                keepalive_expiry=KEEP_OPEN))
        return _client


def post(url, **kwargs):
    """httpx.post, on the kept connection.

    A connection the server had already closed is tried once more, on a
    new one. Nothing was sent on it, so nothing is paid for twice. A
    timeout is not tried again: waiting twice is worse than the fallback.
    """
    import httpx

    try:
        return client().post(url, **kwargs)
    except (httpx.RemoteProtocolError, httpx.WriteError) as exc:
        logger.info("The kept connection had closed (%s); opening a new one",
                    type(exc).__name__)
        return client().post(url, **kwargs)


def warm():
    """Opens the connection now, so the next request does not have to."""
    import httpx

    started = time.monotonic()
    try:
        client().get(WARM_URL, timeout=httpx.Timeout(5.0, connect=4.0))
    except Exception as exc:
        logger.info("Could not open the connection ahead (%.1fs): %s",
                    time.monotonic() - started, type(exc).__name__)
        return False
    return True


def keep_warm(still_recording, every=WARM_EVERY, step=0.5):
    """Opens the connection at the start of a recording, and again every
    `every` seconds while `still_recording()` says it goes on. Runs on its
    own thread, which ends when the recording does."""
    def run():
        while True:
            warm()
            waited = 0.0
            while waited < every:
                if not still_recording():
                    return
                time.sleep(step)
                waited += step

    threading.Thread(target=run, name="link-warm", daemon=True).start()
