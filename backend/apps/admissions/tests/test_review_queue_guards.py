"""The counselor review queue: approve and send-back act only on work waiting for review,
the queue lists sort oldest first on request, and they leave out deactivated students
so they agree with the dashboard's review counts.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions.models import Achievement, ActivityLog, Document, Notification, RoadmapMission, StudentProfile, Task
from apps.admissions.tenancy import set_student_active

from ..test_audit_base import AuditBaseMixin


class ApproveGuardTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.counselor)

    def approve(self, resource, record, note=''):
        return self.client.post(f'/api/{resource}/{record.pk}/approve/', {'note': note}, format='json')

    def test_a_document_that_was_never_uploaded_cannot_be_approved(self):
        for current in (Document.Status.REQUIRED, Document.Status.REJECTED):
            document = Document.objects.create(student=self.student, title=f'Passport {current}', status=current)
            response = self.approve('documents', document, 'Looks good.')
            self.assertEqual(response.status_code, 400, current)
            document.refresh_from_db()
            self.assertEqual(document.status, current)
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(ActivityLog.objects.filter(action__startswith='Document approved').exists())

    def test_a_document_without_a_file_cannot_be_approved(self):
        document = Document.objects.create(student=self.student, title='Transcript', status=Document.Status.UPLOADED)
        self.assertEqual(self.approve('documents', document).status_code, 400)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.UPLOADED)

    def test_uploaded_and_reviewing_documents_can_be_approved(self):
        for current in (Document.Status.UPLOADED, Document.Status.REVIEWING):
            document = Document.objects.create(student=self.student, title=f'Transcript {current}', status=current, google_docs_url='https://docs.google.com/document/d/x')
            response = self.approve('documents', document)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['status'], Document.Status.APPROVED)

    def test_a_second_document_approve_changes_nothing(self):
        document = Document.objects.create(student=self.student, title='Transcript', status=Document.Status.UPLOADED, google_docs_url='https://docs.google.com/document/d/x')
        self.assertEqual(self.approve('documents', document, 'Perfect scan.').status_code, 200)
        document.refresh_from_db()
        updated_at = document.updated_at

        response = self.approve('documents', document, 'Another note.')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['status'], response.data['counselor_comment']), ('approved', 'Perfect scan.'))
        document.refresh_from_db()
        self.assertEqual((document.counselor_comment, document.updated_at), ('Perfect scan.', updated_at))
        self.assertEqual(ActivityLog.objects.filter(action='Document approved: Transcript').count(), 1)
        self.assertEqual(Notification.objects.filter(kind=Notification.Kind.DOCUMENT).count(), 1)

    def test_a_second_achievement_approve_changes_nothing(self):
        achievement = Achievement.objects.create(student=self.student, title='Olympiad', category='olympiad', description='Silver')
        self.assertEqual(self.approve('achievements', achievement, 'Great.').status_code, 200)
        response = self.approve('achievements', achievement, 'Great again.')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['verified'])
        self.assertEqual(ActivityLog.objects.filter(action='Achievement approved: Olympiad').count(), 1)
        self.assertEqual(Notification.objects.count(), 1)

    def test_an_unverified_achievement_with_a_note_can_still_be_approved(self):
        # Sent back, or approved with a note and then un-verified: never stuck.
        achievement = Achievement.objects.create(
            student=self.student, title='Olympiad', category='olympiad', description='Silver', counselor_comment='Attach the diploma.',
        )
        self.assertEqual(self.approve('achievements', achievement).status_code, 200)
        achievement.refresh_from_db()
        self.assertTrue(achievement.verified)


class DocumentStatusPatchTests(AuditBaseMixin, APITestCase):
    def patch(self, document, value):
        return self.client.patch(f'/api/documents/{document.pk}/', {'status': value}, format='json')

    def test_a_student_cannot_approve_their_own_rejected_document(self):
        document = Document.objects.create(
            student=self.student, title='Transcript', status=Document.Status.REJECTED, google_docs_url='https://docs.google.com/document/d/x',
        )
        self.client.force_authenticate(self.student_user)
        for value in (Document.Status.APPROVED, Document.Status.REVIEWING):
            self.assertEqual(self.patch(document, value).status_code, 400, value)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.REJECTED)

    def test_a_counselor_patch_cannot_approve_unsubmitted_work(self):
        document = Document.objects.create(
            student=self.student, title='Transcript', status=Document.Status.REJECTED, google_docs_url='https://docs.google.com/document/d/x',
        )
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.patch(document, Document.Status.APPROVED).status_code, 400)
        Document.objects.filter(pk=document.pk).update(status=Document.Status.UPLOADED)
        self.assertEqual(self.patch(document, Document.Status.APPROVED).status_code, 200)


class SendBackGuardTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.counselor)

    def send_back(self, resource, record):
        return self.client.post(f'/api/{resource}/{record.pk}/send-back/', {'note': 'Add proof.'}, format='json')

    def test_work_already_sent_back_cannot_be_sent_back_again(self):
        achievement = Achievement.objects.create(student=self.student, title='Olympiad', category='olympiad', description='Silver')
        document = Document.objects.create(student=self.student, title='Transcript', status=Document.Status.UPLOADED, google_docs_url='https://docs.google.com/document/d/x')
        for resource, record in (('achievements', achievement), ('documents', document)):
            self.assertEqual(self.send_back(resource, record).status_code, 200, resource)
            self.assertEqual(self.send_back(resource, record).status_code, 400, resource)
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(ActivityLog.objects.filter(action__contains='sent back').count(), 2)

    def test_an_achievement_goes_back_again_once_the_student_changes_it(self):
        achievement = Achievement.objects.create(student=self.student, title='Olympiad', category='olympiad', description='Silver')
        self.assertEqual(self.send_back('achievements', achievement).status_code, 200)
        again = self.send_back('achievements', achievement)
        self.assertEqual((again.status_code, again.data['detail']), (400, 'Already sent back; waiting for the student.'))
        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.client.patch(f'/api/achievements/{achievement.pk}/', {'description': 'Silver, diploma attached'}, format='json').status_code, 200)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.send_back('achievements', achievement).status_code, 200)
        self.assertEqual(ActivityLog.objects.filter(action='Achievement sent back: Olympiad').count(), 2)

    def test_an_approved_then_unverified_achievement_is_back_in_review(self):
        achievement = Achievement.objects.create(student=self.student, title='Olympiad', category='olympiad', description='Silver')
        self.client.post(f'/api/achievements/{achievement.pk}/approve/', {'note': 'Great.'}, format='json')
        response = self.client.patch(f'/api/achievements/{achievement.pk}/', {'verified': False}, format='json')
        self.assertEqual((response.status_code, response.data['counselor_comment']), (200, ''))
        queue = self.results(self.client.get('/api/achievements/?awaiting_review=true'))
        self.assertEqual([row['id'] for row in queue], [achievement.pk])
        self.assertEqual(self.send_back('achievements', achievement).status_code, 200)

    def test_an_unverified_achievement_with_an_old_comment_can_be_sent_back(self):
        achievement = Achievement.objects.create(
            student=self.student, title='Olympiad', category='olympiad', description='Silver', counselor_comment='Great.',
        )
        self.assertEqual(self.send_back('achievements', achievement).status_code, 200)
        achievement.refresh_from_db()
        self.assertEqual(achievement.counselor_comment, 'Add proof.')

    def test_a_required_document_cannot_be_sent_back(self):
        document = Document.objects.create(student=self.student, title='Passport', status=Document.Status.REQUIRED)
        self.assertEqual(self.send_back('documents', document).status_code, 400)
        self.assertFalse(Notification.objects.exists())


class ReviewQueueListTests(AuditBaseMixin, APITestCase):
    QUEUES = {
        'documents': '/api/documents/?awaiting_review=true',
        'achievements': '/api/achievements/?awaiting_review=true',
        'roadmap': '/api/roadmap-missions/?status=submitted',
        'tasks': '/api/tasks/?status=submitted',
    }

    def make_work(self, student, title):
        return {
            'documents': Document.objects.create(student=student, title=title, status=Document.Status.UPLOADED, google_docs_url='https://docs.google.com/document/d/x'),
            'achievements': Achievement.objects.create(student=student, title=title, category='other', description='x'),
            'roadmap': RoadmapMission.objects.create(student=student, title=title, status=RoadmapMission.Status.SUBMITTED),
            'tasks': Task.objects.create(
                student=student, title=title, status=Task.Status.SUBMITTED, due_date=timezone.localdate() + timedelta(days=3),
            ),
        }

    def ids(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.data)
        return [row['id'] for row in self.results(response)]

    def test_ordering_created_lists_the_oldest_work_first(self):
        newer = self.make_work(self.student, 'Newer')
        older = self.make_work(self.student, 'Older')
        now = timezone.now()
        for kind in self.QUEUES:
            type(older[kind]).objects.filter(pk=older[kind].pk).update(created_at=now - timedelta(days=5))
            type(newer[kind]).objects.filter(pk=newer[kind].pk).update(created_at=now - timedelta(days=1))
        self.client.force_authenticate(self.counselor)
        for kind, url in self.QUEUES.items():
            self.assertEqual(self.ids(f'{url}&ordering=created'), [older[kind].pk, newer[kind].pk], kind)
            self.assertEqual(self.ids(f'{url}&ordering=-created'), [newer[kind].pk, older[kind].pk], kind)
            self.assertEqual(self.ids(f'{url}&ordering=created&cursor='), [older[kind].pk, newer[kind].pk], kind)

    def test_deactivated_students_are_left_out_like_the_review_counts(self):
        gone_user = self.make_user('queue-gone', self.student_user.role, self.school_a)
        gone = self.make_profile(gone_user, self.school_a, self.counselor)
        kept = self.make_work(self.student, 'Kept')
        hidden = self.make_work(gone, 'Hidden')
        # A deactivated profile whose account flag is out of step: the counts already skip it.
        StudentProfile.objects.filter(pk=gone.pk).update(deactivated_at=timezone.now())

        self.client.force_authenticate(self.counselor)
        review = self.client.get('/api/dashboard/stats/').data['review']
        self.assertEqual((review['documents'], review['portfolio'], review['roadmap'], review['tasks']), (1, 1, 1, 1))
        for kind, url in self.QUEUES.items():
            self.assertEqual(self.ids(url), [kept[kind].pk], kind)
            # Outside the review queue the record list is unchanged.
            base = url.split('?')[0]
            self.assertIn(hidden[kind].pk, self.ids(base), kind)
        # One student's own list, filtered by status, still shows their submitted work.
        for kind in self.QUEUES:
            self.assertEqual(self.ids(f'{self.QUEUES[kind]}&student={gone.pk}'), [hidden[kind].pk], kind)

    def test_a_product_admin_queue_skips_deactivated_students(self):
        kept = self.make_work(self.student, 'Kept')
        hidden = self.make_work(self.student_b, 'Hidden')
        set_student_active(self.student_b, False, self.admin)
        self.client.force_authenticate(self.admin)
        for kind, url in self.QUEUES.items():
            ids = self.ids(url)
            self.assertIn(kept[kind].pk, ids, kind)
            self.assertNotIn(hidden[kind].pk, ids, kind)
