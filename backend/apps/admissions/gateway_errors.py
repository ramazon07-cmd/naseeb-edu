"""Which AI Gateway failures the provider did not bill, so the budget unit is refunded.

One rule for every feature that calls the gateway (same rule as the education
match AI): refund only failures that happen before the request reached the
model. That is a failure while connecting (refused, DNS, connect timeout,
unreachable network, TLS handshake) or an HTTP status the gateway returns
without running the model (4xx including 429, and the gateway's own
500/502/503). Keep the charge for anything after dispatch: a read timeout or
reset, 408/504, and every failure after the first streamed chunk.
"""
import socket
import urllib.error

# HTTP statuses where the gateway rejected the request without running the model.
# 504 and 408 can arrive after the provider started work, so they keep the charge.
UNBILLED_HTTP = frozenset({400, 401, 402, 403, 404, 405, 409, 413, 415, 422, 429, 500, 502, 503})


def in_connect_phase(exc):
    """True if the exception was raised while establishing the connection."""
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_name in ('create_connection', 'connect'):
            return True
        tb = tb.tb_next
    # urllib wraps connect errors in URLError; the original traceback is on the cause.
    cause = exc.__cause__ or exc.__context__
    if cause is not None and cause is not exc and getattr(cause, '__traceback__', None) is not None:
        tb = cause.__traceback__
        while tb is not None:
            if tb.tb_frame.f_code.co_name in ('create_connection', 'connect'):
                return True
            tb = tb.tb_next
    return False


def is_unbilled(exc):
    """Failures known to happen before the request was dispatched or the model ran."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in UNBILLED_HTTP
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, (ConnectionRefusedError, socket.gaierror)):
        return True
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return in_connect_phase(exc)
    if isinstance(exc, urllib.error.URLError):
        # Other URLErrors (e.g. unreachable network, TLS handshake) come from connect.
        return isinstance(reason, OSError) and in_connect_phase(exc)
    return False
