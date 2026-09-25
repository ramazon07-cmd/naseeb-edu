"""ChallengeAttemptViewSet (/api/challenge-attempts/)."""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import ChallengeAttempt
from apps.users.models import User

from .test_audit_base import AuditBaseMixin

URL = '/api/challenge-attempts/'
ANSWERS = {'q1': 3, 'q2': 5, 'q3': 1}


class ChallengeAttemptTests(AuditBaseMixin, APITestCase):
    def attempt(self, student, challenge='personality', **extra):
        return ChallengeAttempt.objects.create(
            student=student, challenge=challenge, answers=ANSWERS, scores={'o': 60}, **extra,
        )

    # --- create ---------------------------------------------------------

    def test_student_creates_attempt_for_self_regardless_of_payload(self):
        self.client.force_authenticate(self.student_user)
        response = self.client.post(URL, {
            'challenge': '  personality  ', 'answers': ANSWERS, 'scores': {'o': 70},
            'student': self.student_b.id,  # read-only: must be ignored
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        attempt = ChallengeAttempt.objects.get(pk=response.data['id'])
        self.assertEqual(attempt.student_id, self.student.id)
        self.assertEqual(attempt.challenge, 'personality')
        self.assertEqual(attempt.instrument_version, '1')
        self.assertEqual(response.data['student_name'], 'base-student')

    def test_retake_keeps_both_rows(self):
        self.client.force_authenticate(self.student_user)
        for _ in range(2):
            response = self.client.post(URL, {'challenge': 'personality', 'answers': ANSWERS}, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ChallengeAttempt.objects.filter(student=self.student).count(), 2)

    def test_retrying_a_save_with_the_same_completion_time_is_idempotent(self):
        self.client.force_authenticate(self.student_user)
        payload = {'challenge': 'personality', 'answers': ANSWERS, 'completed_at': '2026-09-20T10:00:00.123456Z'}
        first = self.client.post(URL, payload, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        with self.assertNumQueries(2):  # student profile, then the stored attempt
            again = self.client.post(URL, payload, format='json')
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(again.data['id'], first.data['id'])
        self.assertEqual(ChallengeAttempt.objects.filter(student=self.student).count(), 1)
        # Another challenge at the same moment is a different attempt.
        other = self.client.post(URL, {**payload, 'challenge': 'interests'}, format='json')
        self.assertEqual(other.status_code, status.HTTP_201_CREATED)

    def test_concurrent_duplicate_save_returns_the_stored_row(self):
        from unittest import mock
        from apps.admissions.views import challenges
        self.client.force_authenticate(self.student_user)
        payload = {'challenge': 'personality', 'answers': ANSWERS, 'completed_at': '2026-09-20T10:00:00Z'}
        stored = self.client.post(URL, payload, format='json').data
        # The duplicate check ran before the other request's row was committed.
        with mock.patch.object(challenges.ChallengeAttemptViewSet, '_existing',
                               side_effect=[None, ChallengeAttempt.objects.get(pk=stored['id'])]):
            response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], stored['id'])
        self.assertEqual(ChallengeAttempt.objects.filter(student=self.student).count(), 1)

    def test_invalid_payloads_are_rejected(self):
        self.client.force_authenticate(self.student_user)
        for payload in (
            {'challenge': '   ', 'answers': ANSWERS},
            {'challenge': 'personality', 'answers': {}},
            {'challenge': 'personality', 'answers': ['a']},
            {'challenge': 'personality', 'answers': {'q1': 6}},
            {'challenge': 'personality', 'answers': {'q1': 0}},
            {'challenge': 'personality', 'answers': {'q1': '3'}},
            {'challenge': 'personality', 'answers': {'q1': 2.5}},
        ):
            response = self.client.post(URL, payload, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, payload)
        self.assertFalse(ChallengeAttempt.objects.exists())

    def test_only_students_may_create(self):
        for user in (self.admin, self.counselor, self.teacher, self.organization, self.parent):
            self.client.force_authenticate(user)
            response = self.client.post(URL, {'challenge': 'personality', 'answers': ANSWERS}, format='json')
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, user.username)
        self.assertFalse(ChallengeAttempt.objects.exists())

    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_student_account_without_profile_gets_a_client_error(self):
        """A STUDENT user with no StudentProfile gets a 4xx, not a 500.

        Such accounts can exist when created outside ensure_student_profile
        (Django admin, legacy rows).
        """
        orphan = self.make_user('base-orphan-student', User.Role.STUDENT, self.school_a)
        self.client.force_authenticate(orphan)
        response = self.client.post(URL, {'challenge': 'personality', 'answers': ANSWERS}, format='json')
        self.assertLess(response.status_code, 500)
        self.assertGreaterEqual(response.status_code, 400)

    # --- read -----------------------------------------------------------

    def test_student_sees_only_own_attempts(self):
        mine = self.attempt(self.student)
        other = self.attempt(self.student_b)
        self.client.force_authenticate(self.student_user)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in self.results(response)], [mine.id])
        # ?student= cannot widen a student's view.
        response = self.client.get(f'{URL}?student={self.student_b.id}')
        self.assertEqual([row['id'] for row in self.results(response)], [mine.id])
        self.assertEqual(self.client.get(f'{URL}{other.id}/').status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(f'{URL}{mine.id}/').status_code, status.HTTP_200_OK)

    def test_assigned_counselor_reads_but_peers_do_not(self):
        mine = self.attempt(self.student)
        self.attempt(self.student_b)
        self.client.force_authenticate(self.counselor)
        response = self.client.get(URL)
        self.assertEqual([row['id'] for row in self.results(response)], [mine.id])
        self.assertEqual(self.client.get(f'{URL}{mine.id}/').status_code, status.HTTP_200_OK)
        filtered = self.client.get(f'{URL}?student={self.student.id}')
        self.assertEqual([row['id'] for row in self.results(filtered)], [mine.id])

        # Same-school counselor who is not assigned, and a counselor elsewhere.
        for user in (self.counselor_peer, self.counselor_b):
            self.client.force_authenticate(user)
            ids = [row['id'] for row in self.results(self.client.get(URL))]
            self.assertNotIn(mine.id, ids)
            self.assertEqual(self.client.get(f'{URL}{mine.id}/').status_code, status.HTTP_404_NOT_FOUND)

    def test_teacher_organization_and_parent_cannot_read(self):
        attempt = self.attempt(self.student)
        for user in (self.teacher, self.organization, self.parent):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(URL).status_code, status.HTTP_403_FORBIDDEN, user.username)
            self.assertEqual(
                self.client.get(f'{URL}{attempt.id}/').status_code, status.HTTP_403_FORBIDDEN, user.username,
            )

    def test_admin_reads_all_and_can_filter(self):
        a = self.attempt(self.student)
        b = self.attempt(self.student_b)
        self.client.force_authenticate(self.admin)
        self.assertEqual(sorted(row['id'] for row in self.results(self.client.get(URL))), sorted([a.id, b.id]))
        filtered = self.client.get(f'{URL}?student={self.student_b.id}')
        self.assertEqual([row['id'] for row in self.results(filtered)], [b.id])

    def test_non_numeric_student_filter_is_400(self):
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get(f'{URL}?student=abc').status_code, status.HTTP_400_BAD_REQUEST)

    # --- immutability ---------------------------------------------------

    def test_nobody_can_edit_or_delete(self):
        attempt = self.attempt(self.student)
        for user in (self.student_user, self.counselor, self.admin):
            self.client.force_authenticate(user)
            for method in ('put', 'patch', 'delete'):
                response = getattr(self.client, method)(
                    f'{URL}{attempt.id}/', {'challenge': 'hacked', 'answers': ANSWERS}, format='json',
                )
                self.assertIn(
                    response.status_code,
                    {status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED},
                    f'{user.username} {method}',
                )
        attempt.refresh_from_db()
        self.assertEqual(attempt.challenge, 'personality')

    def test_list_is_newest_first(self):
        from datetime import timedelta
        from django.utils import timezone
        older = self.attempt(self.student, completed_at=timezone.now() - timedelta(days=400))
        newer = self.attempt(self.student)
        self.client.force_authenticate(self.student_user)
        self.assertEqual([row['id'] for row in self.results(self.client.get(URL))], [newer.id, older.id])
