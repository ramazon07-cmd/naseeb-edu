"""Run a blocking network call so it cannot outlive an absolute deadline.

Socket timeouts only limit silence: a peer that sends a byte now and then keeps a read alive for ever. This runs the
call in a daemon thread and waits for it at most until the deadline; when time is up the caller gets TimeoutError at
once, ``on_timeout`` (for example closing the socket) is called, and the thread is left to end on its own.
"""
import threading
import time


def run_bounded(call, seconds, on_timeout=None):
    """``call()``'s result (or its exception), or TimeoutError after ``seconds``."""
    if seconds <= 0:
        raise TimeoutError('No time left for the call.')
    outcome = {}

    def work():
        try:
            outcome['value'] = call()
        except BaseException as exc:  # noqa: BLE001 - handed to the caller as it was raised
            outcome['error'] = exc

    worker = threading.Thread(target=work, daemon=True)
    started = time.monotonic()
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        if on_timeout is not None:
            try:
                on_timeout()
            except Exception:  # noqa: BLE001 - best effort
                pass
        raise TimeoutError(f'The call outlived its deadline ({time.monotonic() - started:.1f}s).')
    if 'error' in outcome:
        raise outcome['error']
    return outcome['value']
