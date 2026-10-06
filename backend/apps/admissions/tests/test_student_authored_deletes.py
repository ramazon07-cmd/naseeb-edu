"""P0: staff cannot permanently delete a student's essays or portfolio records; only the student can."""
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

    def test_counselor_still_reviews_instead(self):
        achievement = self.make_records()['achievements']
        self.client.force_authenticate(self.counselor)
        response = self.client.post(f'/api/achievements/{achievement.pk}/send-back/', {'note': 'Add proof.'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        achievement.refresh_from_db()
        self.assertEqual(achievement.counselor_comment, 'Add proof.')
