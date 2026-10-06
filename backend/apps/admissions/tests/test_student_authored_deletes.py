"""P0: staff cannot permanently delete a student's essays or portfolio records; only the student can."""
import tempfile
from django.core.files.base import ContentFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from apps.users.models import User
from ..models import Achievement, Activity, Essay, Honor, Internship, ParentStudentLink, Project, Research
from .base import RoleIsolationBase


class StudentAuthoredDeleteTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username='admin-del', email='admin-del@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.parent = User.objects.create_user(
            username='parent-del', email='parent-del@example.com', password='StrongPass123!', role=User.Role.PARENT,
        )
        ParentStudentLink.objects.create(parent=self.parent, student=self.student_a, status=ParentStudentLink.Status.ACTIVE)

    def make_records(self):
        student = {'student': self.student_a}
        return {
            'essays': Essay.objects.create(
                **student, title='Why me', content='My own words.', shared_with_counselor=True, shared_at=timezone.now(),
            ),
            'achievements': Achievement.objects.create(**student, title='Olympiad', category='olympiad', description='Gold'),
            'researches': Research.objects.create(**student, title='Soil study', summary='Mine'),
            'projects': Project.objects.create(**student, title='Radio', description='Mine'),
            'internships': Internship.objects.create(**student, organization='Lab', position='Intern'),
            'activities': Activity.objects.create(**student, name='Chess club'),
            'honors': Honor.objects.create(**student, title='Dean list'),
        }

    def test_counselor_admin_and_parent_cannot_delete_student_records(self):
        records = self.make_records()
        for actor in (self.counselor, self.admin, self.parent, self.teacher, self.organization):
            self.client.force_authenticate(actor)
            for basename, record in records.items():
                with self.subTest(actor=actor.username, basename=basename):
                    response = self.client.delete(f'/api/{basename}/{record.pk}/')
                    self.assertIn(response.status_code, {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND})
                    self.assertTrue(type(record).objects.filter(pk=record.pk).exists())

    def test_the_student_can_still_delete_their_own_records(self):
        records = self.make_records()
        self.client.force_authenticate(self.student_a_user)
        for basename, record in records.items():
            with self.subTest(basename=basename):
                response = self.client.delete(f'/api/{basename}/{record.pk}/')
                self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
                self.assertFalse(type(record).objects.filter(pk=record.pk).exists())

    def test_counselor_delete_says_why(self):
        essay = self.make_records()['essays']
        self.client.force_authenticate(self.counselor)
        response = self.client.delete(f'/api/essays/{essay.pk}/')
        self.assertEqual((response.status_code, response.data['code']), (403, 'student_authored_delete'))

    def test_staff_cannot_wipe_student_work_through_an_update(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(DOCUMENT_STORAGE_ROOT=media_root):
            self.check_staff_cannot_wipe_student_work()

    def check_staff_cannot_wipe_student_work(self):
        records = self.make_records()
        achievement = records['achievements']
        achievement.proof_file.save('proof.pdf', ContentFile(b'%PDF-1.4 proof'))
        wipes = {
            # Blank required fields are already a 400; replacing the text is the wipe.
            'achievements': [{'description': 'x'}, {'proof_file': None}, {'title': 'Renamed'}],
            'researches': [{'summary': 'x'}],
            'projects': [{'description': 'x'}],
            'internships': [{'position': 'x'}],
            'activities': [{'name': 'Renamed'}],
            'honors': [{'title': 'Renamed'}],
            'essays': [{'content': ''}, {'title': 'Renamed'}],
        }
        self.client.force_authenticate(self.counselor)
        for basename, payloads in wipes.items():
            record = records[basename]
            before = type(record).objects.filter(pk=record.pk).values().first()
            for payload in payloads:
                with self.subTest(basename=basename, payload=payload):
                    response = self.client.patch(f'/api/{basename}/{record.pk}/', payload, format='json')
                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
                    self.assertEqual(response.data['code'], 'student_authored')
            self.assertEqual(type(record).objects.filter(pk=record.pk).values().first(), before, basename)
        achievement.refresh_from_db()
        self.assertTrue(achievement.proof_file)

    def test_staff_can_still_verify_and_comment(self):
        records = self.make_records()
        self.client.force_authenticate(self.counselor)
        for basename in ('researches', 'projects', 'internships', 'activities', 'honors'):
            with self.subTest(basename=basename):
                response = self.client.patch(f'/api/{basename}/{records[basename].pk}/', {'verified': True}, format='json')
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        # Unchanged student fields sent along with a review are not a change.
        achievement = records['achievements']
        response = self.client.patch(
            f'/api/achievements/{achievement.pk}/',
            {'title': achievement.title, 'description': achievement.description, 'counselor_comment': 'Add proof.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_student_still_edits_their_own_work(self):
        records = self.make_records()
        self.client.force_authenticate(self.student_a_user)
        response = self.client.patch(f'/api/achievements/{records["achievements"].pk}/', {'description': 'Silver'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_counselor_still_reviews_instead(self):
        achievement = self.make_records()['achievements']
        self.client.force_authenticate(self.counselor)
        response = self.client.post(f'/api/achievements/{achievement.pk}/send-back/', {'note': 'Add proof.'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        achievement.refresh_from_db()
        self.assertEqual(achievement.counselor_comment, 'Add proof.')
