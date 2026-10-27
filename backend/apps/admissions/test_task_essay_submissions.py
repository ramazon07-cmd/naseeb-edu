"""Essay Lab -> assigned task -> counselor comment -> student feedback."""
from datetime import date

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.users.models import User
from .models import Essay, Notification, Task
from .test_audit_base import AuditBaseMixin

LAB = '/api/essay-lab/essays'
REVIEW = '/api/essay-lab/review/essays'


class TaskEssaySubmissionTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.student_user)
        created = self.client.post(LAB + '/', {'title': 'My application essay'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.essay_id = created.data['id']
        self.tab_id = created.data['tab']['id']
        self.doc = {'type': 'doc', 'content': [{
            'type': 'paragraph', 'attrs': {'bid': 'p1'},
            'content': [{'type': 'text', 'text': 'My story begins with a difficult decision.'}],
        }]}
        saved = self.client.put(f'{LAB}/{self.essay_id}/autosave/', {
            'tab': self.tab_id, 'doc': self.doc, 'base_seq': created.data['tab']['save_seq'],
            'client_save_id': 'task-essay-first-save',
        }, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.task = Task.objects.create(student=self.student, assigned_by=self.counselor,
                                        title='Write your essay', due_date=date(2027, 12, 1))
        self.url = f'/api/tasks/{self.task.pk}/'

    def submit(self, **extra):
        return self.client.patch(self.url, {'submission_essay': self.essay_id, **extra}, format='json')

    def test_student_submits_saved_essay_and_counselor_comments_on_it(self):
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get(f'{REVIEW}/{self.essay_id}/').status_code, 404)
        self.client.force_authenticate(self.student_user)
        response = self.submit()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'submitted')
        self.assertIsNotNone(response.data['submitted_at'])
        self.assertEqual(response.data['submission_essay_detail']['id'], self.essay_id)
        essay = Essay.objects.get(pk=self.essay_id)
        self.assertTrue(essay.shared_with_counselor)
        self.assertEqual(essay.counselor_access, 'comment')
        self.assertTrue(Notification.objects.filter(recipient=self.counselor, target_id=self.task.pk,
                                                    title='Essay submitted for a task').exists())
        self.client.force_authenticate(self.counselor)
        task = self.client.get(self.url)
        self.assertTrue(task.data['submission_essay_detail']['can_comment'])
        self.assertFalse(task.data['submission_essay_detail']['is_owner'])
        review = self.client.get(f'{REVIEW}/{self.essay_id}/')
        self.assertEqual(review.status_code, 200, review.data)
        comment = self.client.post(f'{REVIEW}/{self.essay_id}/threads/', {
            'tab': self.tab_id, 'bid': 'p1', 'start': 0, 'end': 8, 'body': 'Explain what made this decision difficult.',
        }, format='json')
        self.assertEqual(comment.status_code, 201, comment.data)
        self.client.force_authenticate(self.student_user)
        feedback = self.client.get(f'{LAB}/{self.essay_id}/changes/', {'tab': self.tab_id, 'since': 0})
        self.assertEqual(feedback.status_code, 200, feedback.data)
        self.assertEqual(feedback.data['threads'][0]['comments'][0]['body'], 'Explain what made this decision difficult.')

    def test_other_student_essays_are_missing_without_sharing_them(self):
        peer = self.make_user('essay-peer', User.Role.STUDENT, self.school_a)
        peer_profile = self.make_profile(peer, self.school_a, self.counselor)
        for profile in (peer_profile, self.student_b):
            essay = Essay.objects.create(student=profile, title='Private', content='Do not share this.')
            response = self.submit(submission_essay=essay.pk)
            self.assertEqual(response.status_code, 400, response.data)
            essay.refresh_from_db()
            self.assertFalse(essay.shared_with_counselor)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'todo')
        self.assertIsNone(self.task.submission_essay_id)

    def test_empty_or_trashed_essays_cannot_be_submitted(self):
        empty = Essay.objects.create(student=self.student, title='Empty')
        trashed = Essay.objects.create(student=self.student, title='Trashed', content='Text', trashed_at=timezone.now())
        for essay in (empty, trashed):
            response = self.submit(submission_essay=essay.pk)
            self.assertEqual(response.status_code, 400, response.data)
            essay.refresh_from_db()
            self.assertFalse(essay.shared_with_counselor)
        self.assertFalse(Notification.objects.filter(title='Essay submitted for a task').exists())

    def test_personal_tasks_do_not_share_essays(self):
        self.task.is_self_assigned = True
        self.task.save(update_fields=['is_self_assigned'])
        self.assertEqual(self.submit().status_code, 400)
        self.assertFalse(Essay.objects.get(pk=self.essay_id).shared_with_counselor)

    def test_missing_counselor_does_not_partially_submit_or_share(self):
        self.student.assigned_counselor = None
        self.student.save(update_fields=['assigned_counselor'])
        response = self.submit()
        self.assertEqual(response.status_code, 400, response.data)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'todo')
        self.assertIsNone(self.task.submission_essay_id)
        self.assertFalse(Essay.objects.get(pk=self.essay_id).shared_with_counselor)

    def test_staff_cannot_replace_the_students_attached_essay(self):
        self.assertEqual(self.submit().status_code, 200)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.patch(self.url, {'submission_essay': None}, format='json').status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.submission_essay_id, self.essay_id)

    def test_pending_submissions_cannot_be_replaced_or_submitted_twice(self):
        self.assertEqual(self.submit().status_code, 200)
        other = Essay.objects.create(student=self.student, title='Another private essay', content='Text')
        self.assertEqual(self.submit(submission_essay=other.pk).status_code, 400)
        self.assertEqual(self.submit().status_code, 400)
        other.refresh_from_db()
        self.assertFalse(other.shared_with_counselor)
        self.assertEqual(Notification.objects.filter(title='Essay submitted for a task').count(), 1)

    def test_unshare_revokes_review_access_and_blocks_approval_of_unavailable_evidence(self):
        self.assertEqual(self.submit().status_code, 200)
        self.assertEqual(self.client.post(f'{LAB}/{self.essay_id}/unshare/').status_code, 200)
        self.client.force_authenticate(self.counselor)
        response = self.client.get(self.url)
        self.assertIsNone(response.data['submission_essay_detail'])
        self.assertIsNone(response.data['submission_essay'])
        self.assertEqual(self.client.get(f'{REVIEW}/{self.essay_id}/').status_code, 404)
        self.assertEqual(self.client.post(self.url + 'approve/').status_code, 400)
        self.assertEqual(self.client.post(self.url + 'send-back/', {'note': 'Please attach the essay again.'}, format='json').status_code, 200)
        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.submit().status_code, 200)
        self.assertTrue(Essay.objects.get(pk=self.essay_id).shared_with_counselor)

    def test_task_access_does_not_grant_other_roles_access_to_the_essay(self):
        self.assertEqual(self.submit().status_code, 200)
        for user in (self.organization, self.teacher, self.counselor_peer, self.counselor_b, self.parent):
            with self.subTest(role=user.role, username=user.username):
                self.client.force_authenticate(user)
                self.assertEqual(self.client.get(f'{REVIEW}/{self.essay_id}/').status_code, 404)
                response = self.client.get(self.url)
                if response.status_code == 200:
                    self.assertIsNone(response.data.get('submission_essay_detail'))
                    self.assertIsNone(response.data.get('submission_essay'))

    def test_existing_sharing_permissions_are_preserved(self):
        Essay.objects.filter(pk=self.essay_id).update(shared_with_counselor=True, counselor_access='suggest', shared_at=timezone.now())
        response = self.submit()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Essay.objects.get(pk=self.essay_id).counselor_access, 'suggest')

    def test_submission_status_can_be_reloaded_without_exposing_other_students_tasks(self):
        self.assertEqual(self.submit().status_code, 200)
        url = f'/api/tasks/?submission_essay={self.essay_id}&self_assigned=false'
        rows = self.results(self.client.get(url))
        self.assertEqual([(row['id'], row['status']) for row in rows], [(self.task.pk, 'submitted')])
        self.client.force_authenticate(self.counselor)
        approved = self.client.post(self.url + 'approve/')
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data['xp_awarded'], 0)
        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.results(self.client.get(url))[0]['status'], 'approved')
        self.client.force_authenticate(self.student_b_user)
        self.assertEqual(self.results(self.client.get(url)), [])
        self.assertEqual(self.client.get('/api/tasks/?submission_essay=invalid').status_code, 400)

    def test_an_essay_emptied_after_submission_cannot_be_approved_as_evidence(self):
        self.assertEqual(self.submit().status_code, 200)
        current = self.client.get(f'{LAB}/{self.essay_id}/').data
        response = self.client.put(f'{LAB}/{self.essay_id}/autosave/', {
            'tab': self.tab_id, 'base_seq': current['tab']['save_seq'],
            'client_save_id': 'empty-after-submitting',
            'doc': {'type': 'doc', 'content': [{'type': 'paragraph', 'attrs': {'bid': 'p1'}}]},
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(self.url + 'approve/').status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'submitted')
