"""Send a signed sample request to a local Edu, as Naseeb Mind would (for end-to-end tests).

    python manage.py mind_link_send_test complete --code <code from the site> --mind-user-id <uuid>
    python manage.py mind_link_send_test sync --mind-user-id <uuid>
    python manage.py mind_link_send_test unlink --mind-user-id <uuid>

The secret comes from MIND_LINK_SECRET (or --secret). Nothing is stored by this command itself.
"""
import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.admissions import mind_link
from apps.admissions.instrument_versions import INSTRUMENT_VERSION


class Command(BaseCommand):
    help = 'Sign and send a sample Naseeb Mind request (complete, sync or unlink) to a local Edu.'

    def add_arguments(self, parser):
        parser.add_argument('endpoint', choices=['complete', 'sync', 'unlink'])
        parser.add_argument('--url', default='http://127.0.0.1:8000', help='Edu API origin.')
        parser.add_argument('--secret', default='', help='Defaults to MIND_LINK_SECRET.')
        parser.add_argument('--code', default='', help='The 32-hex code from "Bring my Naseeb Mind results" (complete).')
        parser.add_argument('--mind-user-id', default='', help='Defaults to a fixed sample uuid.')
        parser.add_argument('--major', default='', help='chosen_major to send.')
        parser.add_argument('--challenge', default='personality')
        parser.add_argument('--attempts', type=int, default=1, help='How many sample attempts (0 for none).')
        parser.add_argument('--timestamp', type=int, default=None, help='Override the timestamp (to test the 300 s window).')

    def handle(self, *args, **opts):
        secret = opts['secret'] or settings.MIND_LINK_SECRET
        if not secret:
            raise CommandError('Set MIND_LINK_SECRET (or pass --secret).')
        endpoint = opts['endpoint']
        user_id = opts['mind_user_id'] or '00000000-0000-4000-8000-00000000c0de'
        payload = {'mind_user_id': user_id}
        if endpoint != 'unlink':
            payload['chosen_major'] = opts['major'] or None
            payload['attempts'] = [self.sample(user_id, opts['challenge'], n) for n in range(opts['attempts'])]
        if endpoint == 'complete':
            if not opts['code']:
                raise CommandError('complete needs --code.')
            payload['code'] = opts['code']
        body = json.dumps(payload).encode()
        timestamp = str(opts['timestamp'] if opts['timestamp'] is not None else int(time.time()))
        request = urllib.request.Request(
            f"{opts['url'].rstrip('/')}/api/mind-link/{endpoint}/", data=body, method='POST', headers={
                'Content-Type': 'application/json',
                'X-Naseeb-Timestamp': timestamp,
                'X-Naseeb-Signature': mind_link.sign(secret, timestamp, body),
            })
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                status, text = response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            status, text = error.code, error.read().decode()
        except urllib.error.URLError as error:
            raise CommandError(f'Could not reach {opts["url"]}: {error.reason}')
        self.stdout.write(f'{status} {text}')

    @staticmethod
    def sample(user_id, challenge, n):
        # A stable id per (user, challenge, n): sending it twice shows the import is idempotent.
        return {
            'id': str(uuid.uuid5(uuid.UUID(user_id), f'{challenge}:{n}')),
            'challenge': challenge,
            'instrument_version': INSTRUMENT_VERSION.get(challenge, '1'),
            'answers': {'sample1': 3, 'sample2': 4},
            'scores': {},
            'completed_at': (timezone.now().replace(microsecond=0) - timedelta(days=n + 1)).isoformat(),
        }
