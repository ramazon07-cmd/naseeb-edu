"""Locust load test for the Naseeb Edu API: every page, every role.

NOT a runtime dependency. Run it against a local or staging copy seeded with
``scripts/loadtest/seed.py``, never against production::

    NASEEB_ACCOUNTS=scripts/loadtest/.accounts locust -f scripts/loadtest/locustfile.py \
        --host http://127.0.0.1:8000 --headless --users 200 --spawn-rate 10 --run-time 5m

Each simulated user is one open browser tab. It signs in, loads the workspace
exactly like ``useWorkspaceData`` (every collection of its role, following
pagination), then moves between pages with a think time. While a page is open
the tab runs the same timers as the frontend:

* screen-time flush every 30 s while the student is active (ScreenTimeTracker),
  plus one flush per page change,
* screen-time summary every 60 s on the dashboard (DashboardScreenTime and the
  staff ScreenTimeShortcut),
* channel poll on the Messages page: 8 s, backing off to 30 s while the
  conversation is quiet (MessagesPage),
* Essay Lab autosave 3 s after typing stops and at most every 20 s while typing
  (essayLab/saveQueue.js), with history, checkpoints and the depth check,
* a token refresh every ``JWT_ACCESS_TOKEN_MINUTES`` and a full reload (sign in
  again) at the end of each session.

Requests are named after the endpoint (``/api/tasks/`` pages count as one
name). If the server runs ``querystats_wsgi`` the SQL query count, DB time and
CPU time per request are collected and written, with response sizes, to
``$NASEEB_RESULTS/cost.csv`` when the run stops.

The login throttle (``AUTH_LOGIN_RATE``), the per-user API throttle and the
login lockout apply to the load generator too; raise them for the test server.
"""
import csv
import itertools
import json
import os
import random
import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import date
from pathlib import Path

import gevent
from locust import HttpUser, constant, events, task
from locust.exception import StopUser

API = os.environ.get('NASEEB_API_PREFIX', '/api')
ACCOUNTS = Path(os.environ.get('NASEEB_ACCOUNTS', 'scripts/loadtest/.accounts'))
RESULTS = Path(os.environ.get('NASEEB_RESULTS', 'scripts/loadtest/results'))
SESSION_MINUTES = float(os.environ.get('NASEEB_SESSION_MINUTES', '30'))
TOKEN_MINUTES = float(os.environ.get('NASEEB_TOKEN_MINUTES', '30'))
# Runs every timer, think time and session this many times faster (0.1 = ten
# times faster), so N simulated tabs send the traffic of N / TIME_SCALE real
# tabs with the same request mix. Used to find how many tabs one instance
# serves without running thousands of Locust users.
TIME_SCALE = float(os.environ.get('NASEEB_TIME_SCALE', '1'))


def clock():
    """Seconds on the simulated clock."""
    return time.monotonic() / TIME_SCALE


def sleep(seconds):
    gevent.sleep(seconds * TIME_SCALE)
# Seconds a student stays on one page (outside Essay Lab writing sessions).
THINK = (20, 90)
MAX_PAGES = 100  # listAll in api.js gives up after 100 pages.
# api.list() asks for 200 rows per page (frontend/src/lib/listPath.js); set 0
# to replay the older frontend that used the API default of 25.
PAGE_SIZE = int(os.environ.get('NASEEB_PAGE_SIZE', '200'))
# The Messages page backs off from 8 s to 30 s on quiet conversations; set 0
# for the older fixed 8 s poll.
ADAPTIVE_POLL = os.environ.get('NASEEB_ADAPTIVE_POLL', '1') == '1'

_lock = threading.Lock()
_accounts = {}


def next_account(role):
    with _lock:
        if role not in _accounts:
            path = ACCOUNTS / f'{role}.csv'
            with open(path, newline='', encoding='utf-8') as handle:
                rows = [(row[0], row[1]) for row in csv.reader(handle) if len(row) >= 2]
            if not rows:
                raise SystemExit(f'No credentials in {path}')
            random.shuffle(rows)
            _accounts[role] = itertools.cycle(rows)
        return next(_accounts[role])


# ----------------------------------------------------------------- cost stats

_cost = defaultdict(lambda: {'n': 0, 'queries': 0, 'max_queries': 0, 'db_ms': 0.0, 'cpu_ms': 0.0, 'bytes': 0})


@events.request.add_listener
def _collect(request_type, name, response_time, response_length, response=None, exception=None, **kwargs):
    if response is None:
        return
    row = _cost[f'{request_type} {name}']
    row['n'] += 1
    row['bytes'] += response_length or 0
    headers = response.headers or {}
    queries = int(headers.get('X-Query-Count', 0) or 0)
    row['queries'] += queries
    row['max_queries'] = max(row['max_queries'], queries)
    row['db_ms'] += float(headers.get('X-DB-Ms', 0) or 0)
    row['cpu_ms'] += float(headers.get('X-CPU-Ms', 0) or 0)


_environment = {}


@events.init.add_listener
def _remember_environment(environment, **kwargs):
    _environment['current'] = environment


@events.spawning_complete.add_listener
def _reset_cost(**kwargs):
    # With --reset-stats Locust forgets the ramp; forget its costs too.
    environment = _environment.get('current')
    if environment is not None and environment.reset_stats:
        _cost.clear()


@events.test_stop.add_listener
def _write_cost(environment, **kwargs):
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(RESULTS / 'cost.csv', 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['endpoint', 'requests', 'avg_queries', 'max_queries', 'avg_db_ms', 'avg_cpu_ms', 'avg_kb'])
        for name, row in sorted(_cost.items()):
            n = row['n'] or 1
            writer.writerow([
                name, row['n'], round(row['queries'] / n, 1), row['max_queries'], round(row['db_ms'] / n, 2),
                round(row['cpu_ms'] / n, 2), round(row['bytes'] / n / 1024, 1),
            ])


# ------------------------------------------------------------------ resources

# Mirrors frontend/src/lib/workspaceResources.js (endpoint names only).
STUDENT_RESOURCES = ['students', 'tasks', 'applications', 'documents', 'essays', 'achievements', 'researches',
                     'projects', 'internships', 'activities', 'honors', 'recommendations']
PORTAL_RESOURCES = ['roadmap-missions', 'bookings', 'message-channels', 'program-services', 'scholarships',
                    'opportunity-programs', 'store-items', 'student-team', 'support-tickets']
ADMIN_RESOURCES = ['schools', 'users/accounts', 'counselor-roadmap-templates', 'counselor-roadmaps',
                   'users/audit-events', 'support-tickets']
COUNSELOR_RESOURCES = ['schools', 'roadmap-missions', 'counselor-roadmap-templates', 'counselor-roadmaps',
                       'program-services', 'bookings', 'message-channels', 'support-tickets']
RESOURCES = {
    'student': STUDENT_RESOURCES + ['universities'] + PORTAL_RESOURCES,
    'counselor': STUDENT_RESOURCES + ['universities'] + COUNSELOR_RESOURCES,
    'admin': STUDENT_RESOURCES + ['universities'] + ADMIN_RESOURCES,
    'organization': STUDENT_RESOURCES + ['bookings', 'message-channels', 'support-tickets'],
    'teacher': ['students', 'tasks', 'roadmap-missions', 'bookings', 'message-channels'],
    'parent': ['parent-portal'],
}
_next_path = re.compile(r'/api(/.*)$')


class Tab(HttpUser):
    """One signed-in browser tab. Subclasses set ``role`` and ``pages``."""

    abstract = True
    role = 'student'
    wait_time = constant(0)
    # page -> weight; each page name maps to a ``page_<name>`` method.
    pages = {'dashboard': 1}

    # -------------------------------------------------------------- plumbing

    def api(self, method, path, name=None, **kwargs):
        name = name or re.sub(r'/\d+/', '/:id/', path.split('?')[0])
        response = self.client.request(method, f'{API}/{path}', name=f'{API}/{name}', **kwargs)
        if response.status_code == 401 and self.refresh_token:
            self.renew()
            response = self.client.request(method, f'{API}/{path}', name=f'{API}/{name}', **kwargs)
        return response

    def get(self, path, name=None):
        return self.api('GET', path, name)

    def json(self, response, default=None):
        try:
            return response.json()
        except ValueError:
            return default

    def list_all(self, endpoint):
        """api.list(): follow `next` until the last page (at most 100 pages)."""
        path, items = f'{endpoint}/' + (f'?page_size={PAGE_SIZE}' if PAGE_SIZE else ''), []
        for _ in range(MAX_PAGES):
            payload = self.json(self.get(path, f'{endpoint}/'))
            if not isinstance(payload, dict) or 'results' not in payload:
                return payload if isinstance(payload, list) else items
            items += payload['results']
            nxt = payload.get('next')
            if not nxt:
                break
            match = _next_path.search(nxt)
            path = match.group(1).lstrip('/') if match else None
            if not path:
                break
        return items

    def renew(self):
        response = self.client.post(f'{API}/auth/token/refresh/', json={'refresh': self.refresh_token},
                                    name=f'{API}/auth/token/refresh/')
        if response.status_code == 200:
            data = response.json()
            self.refresh_token = data.get('refresh', self.refresh_token)
            self.client.headers['Authorization'] = f"Bearer {data['access']}"
        self.token_at = clock()

    def sign_in(self):
        self.client.headers.pop('Authorization', None)
        username, password = next_account(self.role)
        response = self.client.post(f'{API}/auth/token/', json={'username': username, 'password': password},
                                    name=f'{API}/auth/token/')
        if response.status_code != 200:
            raise StopUser()
        tokens = response.json()
        self.refresh_token = tokens['refresh']
        self.client.headers['Authorization'] = f"Bearer {tokens['access']}"
        self.token_at = clock()
        self.me = self.json(self.get('users/accounts/me/'), {}) or {}
        self.load_workspace()
        self.session_ends = clock() + random.expovariate(1 / (SESSION_MINUTES * 60))

    def load_workspace(self, keys=None):
        if self.role != 'parent' and (keys is None or 'dashboard' in keys):
            self.get('dashboard/stats/')
        self.data = getattr(self, 'data', {})
        for endpoint in RESOURCES[self.role]:
            if keys is None or endpoint in keys:
                self.data[endpoint] = self.list_all(endpoint)

    def reload_changed(self, endpoint):
        """reload(RELOAD_CHANGED) after a save: the written resource + dashboard + students."""
        self.load_workspace({endpoint, 'dashboard', 'students'})

    def on_start(self):
        self.refresh_token = None
        self.timers = {}
        self.page = None
        self.active_seconds = 0
        self.sign_in()
        self.open_page('dashboard')

    # ----------------------------------------------------------------- timers

    def every(self, name, seconds, job, first=None):
        self.timers[name] = [clock() + (seconds if first is None else first), seconds, job]

    def stop(self, *names):
        for name in names:
            self.timers.pop(name, None)

    def run_timers_until(self, deadline):
        while True:
            now = clock()
            due = [timer for timer in self.timers.values() if timer[0] <= now]
            for timer in due:
                timer[0] = now + timer[1]
                timer[2]()
            upcoming = min([timer[0] for timer in self.timers.values()] + [deadline])
            if upcoming >= deadline and now >= deadline:
                return
            sleep(max(0.05, min(upcoming, deadline) - clock()))
            if clock() >= deadline:
                return

    def screen_time_flush(self):
        if self.active_seconds <= 0:
            return
        entries = [{'page': self.page, 'seconds': min(300, self.active_seconds), 'date': date.today().isoformat()}]
        self.active_seconds = 0
        self.api('POST', 'screen-time/track/', json={'entries': entries})

    def open_page(self, page):
        # ScreenTimeTracker flushes when its effect re-runs for the new page.
        if self.page is not None:
            self.screen_time_flush()
        self.stop('summary', 'messages', 'autosave')
        self.page = page
        getattr(self, f'page_{page}', lambda: None)()

    @task
    def browse(self):
        now = clock()
        if now >= self.session_ends:
            # Session over: the student closes the tab and a new one signs in.
            self.timers = {}
            self.page = None
            self.sign_in()
            self.open_page('dashboard')
            return
        if now - self.token_at >= TOKEN_MINUTES * 60:
            self.renew()
        stay = random.uniform(*THINK)
        self.active_seconds += int(stay * 0.7)
        if 'track' not in self.timers:
            self.every('track', 30, self.screen_time_flush, first=random.uniform(0, 30))
        self.run_timers_until(clock() + stay)
        pages, weights = zip(*self.pages.items())
        self.open_page(random.choices(pages, weights)[0])

    # ------------------------------------------------------------------ pages

    def page_dashboard(self):
        if self.role in {'student', 'counselor', 'organization', 'teacher', 'admin'}:
            self.every('summary', 60, lambda: self.get('screen-time/summary/?days=7'), first=0)

    page_admin_dashboard = page_dashboard

    def page_screen_time(self):
        self.get('screen-time/summary/?days=7')

    def page_bookings(self):
        # The list is preloaded; only the "new meeting" form fetches participants.
        if self.role != 'student' or random.random() > 0.2:
            return
        participants = self.json(self.get('bookings/participants/'), []) or []
        if participants and random.random() < 0.5:
            self.api('POST', 'bookings/', json={
                'participant': participants[0].get('id'), 'topic': 'Essay review',
                'starts_at': '2026-12-01T10:00:00Z', 'duration_minutes': 45,
            })
            self.reload_changed('bookings')

    def page_messages(self):
        channels = self.json(self.get('message-channels/?kind=direct', 'message-channels/'), []) or []
        if isinstance(channels, dict):
            channels = channels.get('results', [])
        if self.role in {'counselor', 'organization', 'teacher'}:
            self.get('message-channels/overview/')
        member = [channel for channel in channels if channel.get('is_member')]
        if not member:
            return
        channel = random.choice(member[:5])
        state = {'last': None, 'snapshot': None}

        def load(first=False):
            payload = self.json(self.get(f"channel-messages/?channel={channel['id']}&page_size=50",
                                         'channel-messages/'), {}) or {}
            items = payload.get('results', payload) if isinstance(payload, dict) else payload
            newest = items[0]['id'] if items else None
            if newest != state['last']:
                state['last'] = newest
                self.api('POST', f"message-channels/{channel['id']}/mark-read/")
            changed = json.dumps(items) != state['snapshot']
            state['snapshot'] = json.dumps(items)
            if not first and random.random() < 0.08:
                self.api('POST', 'channel-messages/', json={'channel': channel['id'], 'body': 'Thanks, noted!'})
                changed = True
            timer = self.timers.get('messages')
            if timer and ADAPTIVE_POLL:
                # MessagesPage: 8 s, then 1.5x slower per quiet poll, up to 30 s.
                timer[1] = 8 if changed else min(30, timer[1] * 1.5)
                timer[0] = clock() + timer[1]

        load(first=True)
        self.every('messages', 8, load)

    def page_roadmap(self):
        missions = [m for m in self.data.get('roadmap-missions') or [] if m.get('status') == 'in_progress']
        if self.role == 'student' and missions and random.random() < 0.25:
            # MissionForm: a student submits a mission with a reflection.
            self.api('PATCH', f"roadmap-missions/{missions[0]['id']}/", json={
                'status': 'submitted', 'reflection': 'Done, see the doc.', 'google_docs_url': '',
            })
            self.reload_changed('roadmap-missions')

    def page_tasks(self):
        tasks = self.data.get('tasks') or []
        if not tasks or random.random() > 0.25:
            return
        target = random.choice(tasks)
        if self.role == 'student':
            self.api('PATCH', f"tasks/{target['id']}/", json={'status': 'in_progress'})
        elif target.get('status') == 'submitted':
            self.api('POST', f"tasks/{target['id']}/approve/")
        else:
            return
        self.reload_changed('tasks')

    def page_college_search(self):
        self.get('college-research/')

    def page_find_personality(self):
        self.get('challenge-attempts/')

    def page_admin_students(self):
        self.page_students()

    def page_students(self):
        students = self.data.get('students') or []
        if students and self.role in {'organization', 'admin'} and random.random() < 0.3:
            self.get(f"students/{random.choice(students)['id']}/data-visibility/")

    def page_essay_lab(self):
        essays = self.json(self.get('essay-lab/essays/?trashed=0', 'essay-lab/essays/'), []) or []
        self.get('essay-lab/folders/')
        if not essays:
            return
        self.get(f"essay-lab/essays/{essays[0]['id']}/depth-check/latest/")
        if random.random() < 0.7:
            self.write_essay(random.choice(essays[:4])['id'])

    def write_essay(self, essay_id):
        """Open an essay and write for a few minutes: autosave, history, checkpoints, coach."""
        essay = self.json(self.get(f'essay-lab/essays/{essay_id}/'), {}) or {}
        self.get(f'essay-lab/essays/{essay_id}/depth-check/latest/')
        doc, seq = essay.get('doc'), essay.get('save_seq')
        if not doc or seq is None:
            return
        doc = json.loads(json.dumps(doc))
        state = {'seq': seq}
        ends = clock() + random.uniform(120, 480)
        while clock() < ends:
            # A burst of typing, then either a pause (save 3 s later) or 20 s max-wait saves.
            sleep(random.choice([random.uniform(3, 8), 20]))
            paragraph = next((node for node in reversed(doc['content']) if node['type'] == 'paragraph'), None)
            if paragraph is not None:
                paragraph.setdefault('content', []).append({'type': 'text', 'text': ' And then I learned more.'})
            response = self.api('PUT', f'essay-lab/essays/{essay_id}/autosave/', json={
                'doc': doc, 'base_seq': state['seq'], 'client_save_id': uuid.uuid4().hex, 'cursor': 10,
            })
            body = self.json(response, {}) or {}
            if response.status_code == 200:
                state['seq'] = body.get('save_seq', state['seq'])
            elif response.status_code == 409:
                state['seq'] = body.get('save_seq', state['seq'])
            self.active_seconds += 10
            roll = random.random()
            if roll < 0.04:
                checkpoints = self.json(self.get(f'essay-lab/essays/{essay_id}/checkpoints/'), []) or []
                if checkpoints:
                    self.get(f"essay-lab/essays/{essay_id}/checkpoints/{checkpoints[0]['id']}/")
            elif roll < 0.05:
                self.api('POST', f'essay-lab/essays/{essay_id}/checkpoints/', json={'label': 'Before rewrite'})
            elif roll < 0.07:
                self.api('POST', f'essay-lab/essays/{essay_id}/depth-check/', json={'base_seq': state['seq']})
            now = clock()
            for timer in list(self.timers.values()):
                if timer[0] <= now:
                    timer[0] = now + timer[1]
                    timer[2]()


class StudentTab(Tab):
    weight = int(os.environ.get('NASEEB_WEIGHT_STUDENT', '180'))
    role = 'student'
    pages = {
        'dashboard': 20, 'essay_lab': 20, 'messages': 15, 'roadmap': 10, 'applications': 8,
        'student_center': 6, 'college_search': 4, 'documents': 4, 'tasks': 4, 'programs': 3,
        'find_personality': 2, 'screen_time': 2, 'bookings': 2,
    }


class ParentTab(Tab):
    weight = int(os.environ.get('NASEEB_WEIGHT_PARENT', '6'))
    role = 'parent'
    pages = {'parent_progress': 3, 'parent_tasks': 2, 'parent_applications': 2, 'parent_documents': 1,
             'parent_meetings': 1, 'screen_time': 1}


class CounselorTab(Tab):
    weight = int(os.environ.get('NASEEB_WEIGHT_COUNSELOR', '8'))
    role = 'counselor'
    pages = {'dashboard': 5, 'students': 5, 'tasks': 5, 'roadmap': 3, 'messages': 6, 'bookings': 2,
             'applications': 2, 'screen_time': 1}


class TeacherTab(Tab):
    weight = int(os.environ.get('NASEEB_WEIGHT_TEACHER', '4'))
    role = 'teacher'
    pages = {'dashboard': 4, 'students': 4, 'roadmap': 3, 'messages': 3, 'bookings': 1}


class SchoolTab(Tab):
    weight = int(os.environ.get('NASEEB_WEIGHT_ORGANIZATION', '2'))
    role = 'organization'
    pages = {'dashboard': 4, 'students': 5, 'messages': 2, 'bookings': 1, 'documents': 1}


class AdminTab(Tab):
    weight = int(os.environ.get('NASEEB_WEIGHT_ADMIN', '0'))
    role = 'admin'
    pages = {'admin_dashboard': 3, 'admin_students': 3, 'admin_schools': 1, 'admin_counselors': 1,
             'counselor_roadmap': 1, 'admin_audit': 1}
