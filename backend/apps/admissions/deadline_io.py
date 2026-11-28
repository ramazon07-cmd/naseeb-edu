"""Run a blocking network call so it cannot outlive an absolute deadline.

Socket timeouts only limit silence: a peer that sends a byte now and then keeps a read alive for ever. This runs the
call in a daemon thread and waits for it at most until the deadline; when time is up the caller gets TimeoutError at
once, ``on_timeout`` (for example closing the socket) is called, and the thread is left to end on its own.
"""
import socket
import threading
import time


def abort_response(response):
    """Cut a response off: shut the raw socket down (no reader lock needed), then close it."""
    sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    response.close()


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
            # Fire and forget: closing a response can wait for the lock the stuck reader holds.
            def clean_up():
                try:
                    on_timeout()
                except Exception:  # noqa: BLE001 - best effort
                    pass

            threading.Thread(target=clean_up, daemon=True).start()
        raise TimeoutError(f'The call outlived its deadline ({time.monotonic() - started:.1f}s).')
    if 'error' in outcome:
        raise outcome['error']
    return outcome['value']
