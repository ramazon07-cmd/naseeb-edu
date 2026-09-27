"""WSGI entry point for load tests that reports per-request cost in headers.

Never deploy this. It wraps ``core.wsgi.application`` and adds:

* ``X-Query-Count``: SQL statements the request ran,
* ``X-DB-Ms``: wall time spent inside those statements,
* ``X-CPU-Ms``: CPU time of the request thread (Python work, excluding waits).

The Locust file collects them per endpoint. Run it from ``backend/``::

    gunicorn --pythonpath ../scripts/loadtest querystats_wsgi:application ...
"""
import os
import time

if os.environ.get('RENDER'):
    raise RuntimeError('querystats_wsgi is a load-test tool and must not run on a hosted service.')

from django.db import connection  # noqa: E402

from core.wsgi import application as django_application  # noqa: E402


def application(environ, start_response):
    stats = {'queries': 0, 'db': 0.0}

    def count(execute, sql, params, many, context):
        started = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            stats['queries'] += 1
            stats['db'] += time.perf_counter() - started

    cpu_started = time.thread_time()

    def start(status, headers, exc_info=None):
        headers = list(headers) + [
            ('X-Query-Count', str(stats['queries'])),
            ('X-DB-Ms', f"{stats['db'] * 1000:.2f}"),
            ('X-CPU-Ms', f'{(time.thread_time() - cpu_started) * 1000:.2f}'),
        ]
        return start_response(status, headers, exc_info)

    with connection.execute_wrapper(count):
        return django_application(environ, start)
