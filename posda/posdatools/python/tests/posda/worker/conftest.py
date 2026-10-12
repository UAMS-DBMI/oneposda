import signal

import pytest


@pytest.fixture(autouse=True)
def restore_signal_handlers():
    """Put pytest's handlers back; the run loops install their own."""
    saved = [(sig, signal.getsignal(sig)) for sig in (signal.SIGINT, signal.SIGTERM)]
    yield
    for sig, handler in saved:
        signal.signal(sig, handler)
