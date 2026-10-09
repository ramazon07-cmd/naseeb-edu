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

    def test_staff_keep_full_rights_on_records_they_created(self):
        self.client.force_authenticate(self.counselor)
        created = self.client.post('/api/achievements/', {
            'student': self.student_a.id, 'title': 'Regional olympiad', 'category': 'olympiad', 'description': 'Bronze',
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(Achievement.objects.get(pk=created.data['id']).created_by, self.counselor)
        self.assertTrue(created.data['can_delete'])
        self.assertIn('description', created.data['editable_fields'])
        edited = self.client.patch(f"/api/achievements/{created.data['id']}/", {'description': 'Silver'}, format='json')
        self.assertEqual(edited.status_code, status.HTTP_200_OK, edited.data)
        # Another staff member did not create it: review only.
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(f"/api/achievements/{created.data['id']}/", {'description': 'x'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f"/api/achievements/{created.data['id']}/").status_code, 403)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.delete(f"/api/achievements/{created.data['id']}/").status_code, status.HTTP_204_NO_CONTENT)

    def test_a_staff_created_essay_becomes_the_students_once_they_write_in_it(self):
        self.client.force_authenticate(self.counselor)
        created = self.client.post('/api/essays/', {
            'student': self.student_a.id, 'title': 'Assigned: why this major', 'prompt': 'Why this major?',
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        essay_id = created.data['id']
        renamed = self.client.patch(f'/api/essays/{essay_id}/', {'title': 'Assigned: why CS'}, format='json')
        self.assertEqual(renamed.status_code, status.HTTP_200_OK, renamed.data)
        self.assertTrue(renamed.data['can_delete'])
        # The student starts writing in the Essay Lab.
        self.client.force_authenticate(self.student_a_user)
        tab = self.client.get(f'/api/essay-lab/essays/{essay_id}/').data['tab']
        saved = self.client.put(f'/api/essay-lab/essays/{essay_id}/autosave/', {
            'doc': {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'My answer.'}]}]},
            'base_seq': tab['save_seq'], 'client_save_id': 'student-1',
        }, format='json')
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        self.client.force_authenticate(self.counselor)
        detail = self.client.get(f'/api/essays/{essay_id}/').data
        self.assertEqual((detail['can_delete'], detail['editable_fields']), (False, ['status', 'counselor_comment']))
        self.assertEqual(self.client.delete(f'/api/essays/{essay_id}/').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/essays/{essay_id}/', {'title': 'x'}, format='json').status_code, 403)
        self.assertTrue(Essay.objects.filter(pk=essay_id, content='My answer.').exists())

    def test_rights_are_reported_per_record_for_the_viewer(self):
        achievement = self.make_records()['achievements']
        self.client.force_authenticate(self.student_a_user)
        own = self.client.get(f'/api/achievements/{achievement.pk}/').data
        self.assertTrue(own['can_delete'])
        self.assertIn('description', own['editable_fields'])
        self.assertNotIn('verified', own['editable_fields'])
        self.assertNotIn('counselor_comment', own['editable_fields'])
        self.client.force_authenticate(self.counselor)
        review = self.client.get(f'/api/achievements/{achievement.pk}/').data
        self.assertFalse(review['can_delete'])
        self.assertEqual(sorted(review['editable_fields']), ['counselor_comment', 'verified'])
        self.assertNotIn('created_by', review)

    def test_counselor_still_reviews_instead(self):
        achievement = self.make_records()['achievements']
        self.client.force_authenticate(self.counselor)
        response = self.client.post(f'/api/achievements/{achievement.pk}/send-back/', {'note': 'Add proof.'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        achievement.refresh_from_db()
        self.assertEqual(achievement.counselor_comment, 'Add proof.')
