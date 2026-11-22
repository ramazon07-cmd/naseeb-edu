"""Naseeb Mind link (/api/mind-link/): codes, signed requests, import rules, unlinking."""
import hashlib
import json
import re
import time
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions import mind_link
from apps.admissions.instrument_versions import INSTRUMENT_VERSION
from apps.admissions.models import ChallengeAttempt, MindLink, MindLinkCode, StudentProfile

from .test_audit_base import AuditBaseMixin

SECRET = 'test-mind-link-secret'
URL = '/api/mind-link/'
SECRET_ANSWER = 'ANSWER-SENTINEL-4471'


def attempt(n=1, challenge='personality', version=None, completed=None, **extra):
    return {
        'id': str(uuid.UUID(int=n)), 'challenge': challenge,
        'instrument_version': version or INSTRUMENT_VERSION.get(challenge, '1'),
        'answers': {'p1': 3, 'p2': 4, 'note': SECRET_ANSWER}, 'scores': {'o': 61},
        'completed_at': completed or (timezone.now() - timedelta(days=n)).isoformat(), **extra,
    }


@override_settings(MIND_LINK_SECRET=SECRET, MIND_SITE_URL='https://naseebmind.uz')
class MindLinkTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.mind_id = str(uuid.uuid4())

    # --- helpers --------------------------------------------------------

    def signed(self, path, payload, timestamp=None, secret=SECRET, raw=None):
        body = raw if raw is not None else json.dumps(payload).encode()
        ts = str(int(time.time()) if timestamp is None else timestamp)
        return self.client.post(
            URL + path + '/', data=body, content_type='application/json',
            HTTP_X_NASEEB_TIMESTAMP=ts, HTTP_X_NASEEB_SIGNATURE=mind_link.sign(secret, ts, body),
        )

    def start(self, user=None):
        self.client.force_authenticate(user or self.student_user)
        response = self.client.post(URL + 'start/', {'lang': 'ru'}, format='json')
        self.client.force_authenticate(None)
        return response

    def code(self, user=None):
        response = self.start(user)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['code']

    def complete(self, code=None, attempts=None, mind_id=None, user=None, **extra):
        code = code or self.code(user)
        return self.signed('complete', {
            'code': code, 'mind_user_id': mind_id or self.mind_id, 'chosen_major': None,
            'attempts': [attempt()] if attempts is None else attempts, **extra,
        })

    def link(self, student=None, mind_id=None):
        return MindLink.objects.create(student=student or self.student, mind_user_id=mind_id or self.mind_id)

    # --- signature ------------------------------------------------------

    def test_valid_signature_is_accepted(self):
        self.assertEqual(self.complete().status_code, 200)

    def test_invalid_signature_is_rejected(self):
        code = self.code()
        response = self.signed('complete', {'code': code, 'mind_user_id': self.mind_id, 'attempts': []}, secret='wrong')
        self.assertEqual(response.status_code, 401)
        self.assertFalse(MindLink.objects.exists())

    def test_missing_signature_headers_are_rejected(self):
        response = self.client.post(URL + 'sync/', {'mind_user_id': self.mind_id, 'attempts': []}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_tampered_body_is_rejected(self):
        body = json.dumps({'mind_user_id': self.mind_id, 'attempts': []}).encode()
        ts = str(int(time.time()))
        response = self.client.post(
            URL + 'sync/', data=body + b' ', content_type='application/json',
            HTTP_X_NASEEB_TIMESTAMP=ts, HTTP_X_NASEEB_SIGNATURE=mind_link.sign(SECRET, ts, body))
        self.assertEqual(response.status_code, 401)

    def test_expired_and_future_timestamps_are_rejected(self):
        payload = {'mind_user_id': self.mind_id, 'attempts': []}
        for offset in (-301, 301, -86400):
            response = self.signed('sync', payload, timestamp=int(time.time()) + offset)
            self.assertEqual(response.status_code, 401, offset)
        self.link()
        self.assertEqual(self.signed('sync', payload, timestamp=int(time.time()) - 290).status_code, 200)

    def test_signature_matches_the_contract_formula(self):
        import hmac as m
        body = b'{"a":1}'
        self.assertEqual(mind_link.sign('s', 1700000000, body),
                         m.new(b's', b'1700000000.' + body, hashlib.sha256).hexdigest())

    # --- feature off ----------------------------------------------------

    @override_settings(MIND_LINK_SECRET='')
    def test_feature_off(self):
        self.client.force_authenticate(self.student_user)
        status = self.client.get(URL)
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.data['available'])
        self.assertEqual(self.client.post(URL + 'start/', {}, format='json').status_code, 503)
        self.client.force_authenticate(None)
        for path in ('complete', 'sync', 'unlink'):
            response = self.signed(path, {'mind_user_id': self.mind_id}, secret='')
            self.assertEqual(response.status_code, 503, path)

    # --- codes ----------------------------------------------------------

    def test_start_returns_code_and_url_and_stores_only_a_hash(self):
        response = self.start()
        self.assertEqual(response.status_code, 200)
        code = response.data['code']
        self.assertRegex(code, r'^[0-9a-f]{32}$')
        self.assertEqual(response.data['url'], f'https://naseebmind.uz/connect?code={code}&lang=ru')
        stored = MindLinkCode.objects.get(student=self.student)
        self.assertEqual(stored.code_hash, hashlib.sha256(code.encode()).hexdigest())
        self.assertNotEqual(stored.code_hash, code)
        self.assertAlmostEqual((stored.expires_at - timezone.now()).total_seconds(), 600, delta=5)

    def test_start_defaults_language_and_needs_a_student(self):
        self.client.force_authenticate(self.student_user)
        response = self.client.post(URL + 'start/', {'lang': 'xx'}, format='json')
        self.assertTrue(response.data['url'].endswith('&lang=uz'))
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(URL + 'start/', {}, format='json').status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(URL + 'start/', {}, format='json').status_code, 401)

    def test_code_works_once(self):
        code = self.code()
        self.assertEqual(self.complete(code=code).status_code, 200)
        MindLink.objects.all().delete()
        again = self.complete(code=code)
        self.assertEqual(again.status_code, 410)
        self.assertEqual(again.json()['code'], 'code_invalid')

    def test_expired_code_is_refused(self):
        code = self.code()
        MindLinkCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.complete(code=code).status_code, 410)
        self.assertFalse(MindLink.objects.exists())

    def test_unknown_or_malformed_code_is_refused(self):
        self.assertEqual(self.complete(code='0' * 32).status_code, 410)
        self.assertEqual(self.complete(code='nope').status_code, 410)

    def test_new_start_replaces_the_earlier_code(self):
        first = self.code()
        second = self.code()
        self.assertEqual(MindLinkCode.objects.filter(student=self.student).count(), 1)
        self.assertEqual(self.complete(code=first).status_code, 410)
        self.assertEqual(self.complete(code=second).status_code, 200)

    def test_start_is_refused_while_linked(self):
        self.link()
        self.assertEqual(self.start().status_code, 409)

    # --- complete -------------------------------------------------------

    def test_complete_links_and_imports(self):
        response = self.complete(attempts=[attempt(1), attempt(2, 'interests')], chosen_major=None)
        self.assertEqual(response.json(), {'linked': True, 'imported': 2, 'skipped': 0})
        link = MindLink.objects.get(student=self.student)
        self.assertTrue(link.active)
        self.assertEqual(str(link.mind_user_id), self.mind_id)
        self.assertIsNotNone(link.last_sync_at)
        rows = ChallengeAttempt.objects.filter(student=self.student)
        self.assertEqual(rows.count(), 2)
        self.assertTrue(all(r.source == 'naseeb_mind' and not r.source_version_mismatch for r in rows))
        self.assertTrue(MindLinkCode.objects.get().used_at)

    def test_student_already_linked_to_another_mind_account(self):
        self.link(mind_id=str(uuid.uuid4()))
        code = MindLinkCode.objects.create(
            student=self.student, code_hash=hashlib.sha256(b'a' * 32).hexdigest(), expires_at=timezone.now() + timedelta(minutes=5))
        response = self.complete(code='a' * 32)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'already_linked')
        code.refresh_from_db()
        self.assertIsNone(code.used_at)

    def test_mind_account_already_linked_to_another_student(self):
        self.link(student=self.student_b)
        response = self.complete()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(ChallengeAttempt.objects.count(), 0)
        self.assertEqual(MindLink.objects.get().student_id, self.student_b.id)

    def test_relinking_same_account_reactivates(self):
        self.link()
        MindLink.objects.update(active=False, unlinked_at=timezone.now())
        self.assertEqual(self.complete().status_code, 200)
        link = MindLink.objects.get()
        self.assertTrue(link.active)
        self.assertIsNone(link.unlinked_at)

    def test_inactive_link_of_another_student_moves_over(self):
        self.link(student=self.student_b)
        MindLink.objects.update(active=False)
        self.assertEqual(self.complete().status_code, 200)
        self.assertEqual(MindLink.objects.get().student_id, self.student.id)

    def test_history_follows_the_mind_account_to_the_new_student(self):
        self.link()
        payload = {'mind_user_id': self.mind_id, 'attempts': [attempt(1)]}
        self.assertEqual(self.signed('sync', payload).json(), {'imported': 1, 'skipped': 0})
        self.client.force_authenticate(self.student_user)
        self.client.delete(URL)
        self.client.force_authenticate(None)
        self.assertEqual(self.complete(user=self.student_b_user, attempts=[attempt(1)]).status_code, 200)
        self.assertEqual(MindLink.objects.get().student_id, self.student_b.id)
        mine = ChallengeAttempt.objects.filter(student=self.student, source='naseeb_mind').count()
        theirs = ChallengeAttempt.objects.filter(student=self.student_b, source='naseeb_mind').count()
        self.assertEqual((mine, theirs), (1, 1))
        # Re-sending to the same student still imports nothing.
        self.assertEqual(self.signed('sync', {**payload}).json(), {'imported': 0, 'skipped': 1})

    # --- signature headers (real header names through the test client) ---

    def test_documented_header_names_are_what_django_reads(self):
        body = json.dumps({'mind_user_id': self.mind_id, 'attempts': []}).encode()
        ts = str(int(time.time()))
        self.link()
        response = self.client.post(
            URL + 'sync/', data=body, content_type='application/json',
            headers={'X-Naseeb-Timestamp': ts, 'X-Naseeb-Signature': mind_link.sign(SECRET, ts, body)})
        self.assertEqual(response.status_code, 200)
        misspelled = self.client.post(
            URL + 'sync/', data=body, content_type='application/json',
            headers={'X-Naiseb-Timestamp': ts, 'X-Naiseb-Signature': mind_link.sign(SECRET, ts, body)})
        self.assertEqual(misspelled.status_code, 401)

    # --- import ---------------------------------------------------------

    def test_import_is_idempotent(self):
        self.link()
        payload = {'mind_user_id': self.mind_id, 'attempts': [attempt(1), attempt(2)]}
        self.assertEqual(self.signed('sync', payload).json(), {'imported': 2, 'skipped': 0})
        self.assertEqual(self.signed('sync', payload).json(), {'imported': 0, 'skipped': 2})
        self.assertEqual(ChallengeAttempt.objects.count(), 2)

    def test_duplicate_ids_in_one_payload_import_once(self):
        self.link()
        one = attempt(1)
        response = self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': [one, one]})
        self.assertEqual(response.json(), {'imported': 1, 'skipped': 1})

    def test_unknown_challenge_is_skipped(self):
        self.link()
        response = self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': [attempt(1, 'astrology'), attempt(2)]})
        self.assertEqual(response.json(), {'imported': 1, 'skipped': 1})
        self.assertFalse(ChallengeAttempt.objects.filter(challenge='astrology').exists())

    def test_minds_school_challenge_is_stored_as_edus_subjects_and_flagged_by_version(self):
        self.link()
        response = self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': [
            attempt(1, 'school', version='1'), attempt(2, 'school', version='2'),
        ]})
        self.assertEqual(response.json(), {'imported': 2, 'skipped': 0})
        self.assertFalse(ChallengeAttempt.objects.filter(challenge='school').exists())
        older = ChallengeAttempt.objects.get(external_id=str(uuid.UUID(int=1)))
        current = ChallengeAttempt.objects.get(external_id=str(uuid.UUID(int=2)))
        self.assertEqual((older.challenge, older.instrument_version, older.source_version_mismatch), ('subjects', '1', True))
        self.assertEqual((current.challenge, current.source_version_mismatch), ('subjects', False))
        # Re-sending imports nothing, and the complete flow reads the alias the same way.
        again = self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': [attempt(1, 'school', version='1')]})
        self.assertEqual(again.json(), {'imported': 0, 'skipped': 1})

    def test_version_mismatch_is_kept_and_flagged(self):
        self.link()
        self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': [attempt(1, version='99'), attempt(2)]})
        flagged = ChallengeAttempt.objects.get(external_id=str(uuid.UUID(int=1)))
        self.assertTrue(flagged.source_version_mismatch)
        self.assertEqual(flagged.instrument_version, '99')
        self.assertFalse(ChallengeAttempt.objects.get(external_id=str(uuid.UUID(int=2))).source_version_mismatch)

    def test_existing_attempts_are_never_overwritten(self):
        self.link()
        completed = timezone.now() - timedelta(days=1)
        mine = ChallengeAttempt.objects.create(student=self.student, challenge='personality', answers={'x': 1}, completed_at=completed)
        response = self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': [attempt(1, completed=completed.isoformat())]})
        self.assertEqual(response.json(), {'imported': 0, 'skipped': 1})
        mine.refresh_from_db()
        self.assertEqual((mine.answers, mine.source), ({'x': 1}, 'naseeb_edu'))

    def test_bad_payloads_are_400(self):
        self.link()
        base = {'mind_user_id': self.mind_id}
        bad = [
            {**base, 'attempts': 'x'},
            {**base, 'attempts': [{**attempt(1), 'answers': [1]}]},
            {**base, 'attempts': [{**attempt(1), 'scores': 'x'}]},
            {**base, 'attempts': [{**attempt(1), 'completed_at': 'yesterday'}]},
            {**base, 'attempts': [{k: v for k, v in attempt(1).items() if k != 'id'}]},
            {**base, 'attempts': [], 'chosen_major': 5},
            {'mind_user_id': 'not-a-uuid', 'attempts': []},
        ]
        for payload in bad:
            self.assertEqual(self.signed('sync', payload).status_code, 400, payload)
        self.assertEqual(self.signed('sync', None, raw=b'[1]').status_code, 400)
        self.assertEqual(self.signed('sync', None, raw=b'not json').status_code, 400)

    # --- limits ---------------------------------------------------------

    def test_attempt_count_limit(self):
        self.link()
        many = [attempt(n) for n in range(1, 202)]
        response = self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': many})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'too_many_attempts')
        ok = self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': many[:200]})
        self.assertEqual(ok.json(), {'imported': 200, 'skipped': 0})

    def test_body_size_limit(self):
        self.link()
        big = attempt(1)
        big['answers'] = {'p1': 'x' * (2 * 1024 * 1024 + 10)}
        response = self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': [big]})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(ChallengeAttempt.objects.count(), 0)

    # --- sync / unlink ----------------------------------------------------

    def test_sync_updates_last_sync_and_offers_major(self):
        link = self.link()
        self.signed('sync', {'mind_user_id': self.mind_id, 'chosen_major': 'Biology', 'attempts': []})
        link.refresh_from_db()
        self.assertIsNotNone(link.last_sync_at)
        self.assertEqual(link.chosen_major, 'Biology')

    def test_sync_unlinked_is_410(self):
        for setup in (lambda: None, lambda: (self.link(), MindLink.objects.update(active=False))):
            setup()
            response = self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': [attempt(1)]})
            self.assertEqual(response.status_code, 410)
            self.assertEqual(response.json()['code'], 'not_linked')
        self.assertEqual(ChallengeAttempt.objects.count(), 0)

    def test_unlink_from_mind(self):
        self.link()
        self.assertEqual(self.signed('unlink', {'mind_user_id': self.mind_id}).status_code, 200)
        self.assertFalse(MindLink.objects.get().active)
        self.assertEqual(self.signed('unlink', {'mind_user_id': self.mind_id}).status_code, 200)
        self.assertEqual(self.signed('unlink', {'mind_user_id': str(uuid.uuid4())}).status_code, 200)

    def test_unlink_from_edu_keeps_imported_results(self):
        self.assertEqual(self.complete().status_code, 200)
        self.client.force_authenticate(self.student_user)
        response = self.client.delete(URL)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['linked'])
        self.assertFalse(MindLink.objects.get().active)
        self.assertEqual(ChallengeAttempt.objects.filter(student=self.student).count(), 1)
        self.client.force_authenticate(None)
        self.assertEqual(self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': []}).status_code, 410)

    # --- status ---------------------------------------------------------

    def test_status_shape(self):
        self.client.force_authenticate(self.student_user)
        data = self.client.get(URL).data
        self.assertEqual((data['available'], data['linked'], data['linked_at'], data['last_sync_at']), (True, False, None, None))
        self.link()
        data = self.client.get(URL).data
        self.assertTrue(data['linked'])
        self.assertIsNotNone(data['linked_at'])

    def test_students_see_only_their_own_status(self):
        self.link(student=self.student_b)
        self.client.force_authenticate(self.student_user)
        self.assertFalse(self.client.get(URL).data['linked'])

    def test_chosen_major_is_offered_only_without_a_target_major(self):
        link = self.link()
        link.chosen_major = 'Biology'
        link.save()
        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.client.get(URL).data['chosen_major'], 'Biology')
        StudentProfile.objects.filter(pk=self.student.pk).update(target_major='Law')
        self.assertIsNone(self.client.get(URL).data['chosen_major'])
        self.assertEqual(StudentProfile.objects.get(pk=self.student.pk).target_major, 'Law')

    def test_challenge_attempts_api_exposes_source_and_flag_but_not_writes_them(self):
        self.link()
        self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': [attempt(1, version='99')]})
        self.client.force_authenticate(self.student_user)
        rows = self.results(self.client.get('/api/challenge-attempts/'))
        self.assertEqual((rows[0]['source'], rows[0]['source_version_mismatch']), ('naseeb_mind', True))
        created = self.client.post('/api/challenge-attempts/', {
            'challenge': 'interests', 'answers': {'a': 2}, 'source': 'naseeb_mind', 'source_version_mismatch': True,
        }, format='json')
        self.assertEqual((created.data['source'], created.data['source_version_mismatch']), ('naseeb_edu', False))
        self.assertEqual(ChallengeAttempt.objects.get(pk=created.data['id']).external_id, '')

    # --- logging ----------------------------------------------------------

    def test_no_answers_or_scores_in_logs(self):
        code = self.code()
        with self.assertLogs('apps', level='DEBUG') as logs:
            self.complete(code=code)
            self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': [attempt(2), attempt(3, 'astrology')]})
            self.signed('sync', {'mind_user_id': self.mind_id, 'attempts': [attempt(4, completed='bad')]})
        text = '\n'.join(logs.output)
        self.assertNotIn(SECRET_ANSWER, text)
        self.assertNotIn('p1', text)
        self.assertNotIn('"o"', text)

    def test_signed_throttle_applies(self):
        with override_settings(REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            'DEFAULT_THROTTLE_RATES': {**settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'], 'mind_link_signed': '2/minute'}}):
            from rest_framework.settings import api_settings
            api_settings.reload()
            try:
                cache.clear()
                codes = [self.signed('unlink', {'mind_user_id': self.mind_id}).status_code for _ in range(3)]
            finally:
                api_settings.reload()
        self.assertEqual(codes, [200, 200, 429])


class InstrumentVersionSyncTests(APITestCase):
    def test_versions_match_the_frontend(self):
        source = Path(__file__).resolve().parents[3] / 'frontend' / 'src' / 'challenges.js'
        if not source.exists():
            self.skipTest('frontend sources not present')
        block = re.search(r'export const INSTRUMENT_VERSION = \{(.*?)\n\}', source.read_text(), re.S).group(1)
        block = re.sub(r'//.*', '', block)
        found = dict(re.findall(r'"?(\w+)"?\s*:\s*"([^"]+)"', block))
        self.assertEqual(found, INSTRUMENT_VERSION)
