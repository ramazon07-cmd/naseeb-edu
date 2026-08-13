import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Honor, School, StudentProfile


User = get_user_model()


class PrivateStudentEvidenceTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Evidence School', code='evidence-school')
        self.counselor = User.objects.create_user(
            username='evidence-counselor', email='evidence-counselor@example.com',
            password='StrongPass123!', role=User.Role.COUNSELOR, school=self.school,
        )
        self.organization = User.objects.create_user(
            username='evidence-school-account', email='evidence-school@example.com',
            password='StrongPass123!', role=User.Role.ORGANIZATION, school=self.school,
        )
        self.admin = User.objects.create_user(
            username='evidence-admin', email='evidence-admin@example.com',
            password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.student_user = User.objects.create_user(
            username='evidence-student', email='evidence-student@example.com',
            password='StrongPass123!', role=User.Role.STUDENT, school=self.school,
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user, school=self.school, school_name=self.school.name,
            assigned_counselor=self.counselor,
        )
        other_user = User.objects.create_user(
            username='other-evidence-student', email='other-evidence@example.com',
            password='StrongPass123!', role=User.Role.STUDENT, school=self.school,
        )
        self.other_student = StudentProfile.objects.create(
            user=other_user, school=self.school, school_name=self.school.name,
        )

    @staticmethod
    def pdf(name='evidence.pdf'):
        return SimpleUploadedFile(
            name,
            b'%PDF-1.4\nprivate student evidence\n%%EOF',
            content_type='application/pdf',
        )

    def test_student_uploads_and_permitted_roles_securely_stream_all_evidence(self):
        cases = (
            ('achievements', {
                'title': 'National olympiad award',
                'category': 'olympiad',
                'description': 'First place evidence.',
            }),
            ('honors', {
                'title': 'Academic excellence honor',
                'issuer': 'Evidence School',
                'level': 'national',
            }),
        )
        with tempfile.TemporaryDirectory() as private_root:
            with override_settings(DOCUMENT_STORAGE_ROOT=private_root):
                created = []
                self.client.force_authenticate(self.student_user)
                for resource, payload in cases:
                    with self.subTest(resource=resource):
                        response = self.client.post(
                            f'/api/{resource}/',
                            {**payload, 'student': self.student.id, 'proof_file': self.pdf(f'{resource}.pdf')},
                            format='multipart',
                        )
                        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                        self.assertNotIn('proof_file', response.data)
                        self.assertTrue(response.data['has_proof_file'])
                        self.assertTrue(response.data['proof_file_previewable'])
                        self.assertEqual(response.data['proof_file_name'], f'{resource}.pdf')
                        self.assertEqual(response.data['proof_resource'], resource)
                        created.append((resource, response.data['id']))

                stored_files = [path for path in Path(private_root).rglob('*') if path.is_file()]
                self.assertEqual(len(stored_files), 2)
                self.assertTrue(all('student_evidence' in path.parts for path in stored_files))

                for resource, record_id in created:
                    with self.subTest(owner_preview=resource):
                        preview = self.client.get(f'/api/{resource}/{record_id}/proof-file/')
                        self.assertEqual(preview.status_code, status.HTTP_200_OK)
                        self.assertIn('inline', preview['Content-Disposition'])
                        self.assertEqual(
                            b''.join(preview.streaming_content),
                            b'%PDF-1.4\nprivate student evidence\n%%EOF',
                        )
                        download = self.client.get(f'/api/{resource}/{record_id}/proof-file/?download=1')
                        self.assertEqual(download.status_code, status.HTTP_200_OK)
                        self.assertIn('attachment', download['Content-Disposition'])

                    self.client.force_authenticate(self.other_student.user)
                    self.assertEqual(
                        self.client.get(f'/api/{resource}/{record_id}/proof-file/').status_code,
                        status.HTTP_404_NOT_FOUND,
                    )
                    for permitted in (self.counselor, self.organization, self.admin):
                        self.client.force_authenticate(permitted)
                        self.assertEqual(
                            self.client.get(f'/api/{resource}/{record_id}/proof-file/').status_code,
                            status.HTTP_200_OK,
                            (resource, permitted.role),
                        )

                self.client.force_authenticate(self.organization)
                visibility = self.client.get(f'/api/students/{self.student.id}/data-visibility/')
                self.assertEqual(visibility.status_code, status.HTTP_200_OK)
                self.assertTrue(visibility.data['achievements'][0]['has_proof_file'])
                self.assertTrue(visibility.data['honors'][0]['has_proof_file'])
                self.assertNotIn('proof_file', visibility.data['achievements'][0])
                self.assertNotIn('proof_file', visibility.data['honors'][0])

    def test_invalid_evidence_is_rejected_and_activity_dates_round_trip(self):
        self.client.force_authenticate(self.student_user)
        invalid = self.client.post(
            '/api/achievements/',
            {
                'student': self.student.id,
                'title': 'Unsafe proof',
                'category': 'other',
                'description': 'Must fail.',
                'proof_file': SimpleUploadedFile('proof.exe', b'MZ executable'),
            },
            format='multipart',
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

        activity = self.client.post(
            '/api/activities/',
            {
                'student': self.student.id,
                'name': 'Community leadership',
                'activity_type': 'community',
                'start_date': '2025-09-01',
                'end_date': '2026-05-30',
            },
            format='json',
        )
        self.assertEqual(activity.status_code, status.HTTP_201_CREATED, activity.data)
        self.assertEqual(activity.data['start_date'], '2025-09-01')
        self.assertEqual(activity.data['end_date'], '2026-05-30')

    def test_replaced_and_cleared_evidence_files_are_removed_from_storage(self):
        with tempfile.TemporaryDirectory() as private_root, override_settings(DOCUMENT_STORAGE_ROOT=private_root):
            self.client.force_authenticate(self.student_user)
            created = self.client.post(
                '/api/honors/',
                {
                    'student': self.student.id,
                    'title': 'Replaceable honor',
                    'level': 'school',
                    'proof_file': self.pdf('first.pdf'),
                },
                format='multipart',
            )
            self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
            honor = Honor.objects.get(pk=created.data['id'])
            first_path = Path(honor.proof_file.path)
            self.assertTrue(first_path.exists())

            with self.captureOnCommitCallbacks(execute=True):
                replaced = self.client.patch(
                    f'/api/honors/{honor.id}/',
                    {'proof_file': self.pdf('second.pdf')},
                    format='multipart',
                )
            self.assertEqual(replaced.status_code, status.HTTP_200_OK, replaced.data)
            honor.refresh_from_db()
            second_path = Path(honor.proof_file.path)
            self.assertFalse(first_path.exists())
            self.assertTrue(second_path.exists())
            self.assertEqual(honor.proof_file_name, 'second.pdf')

            with self.captureOnCommitCallbacks(execute=True):
                cleared = self.client.patch(
                    f'/api/honors/{honor.id}/',
                    {'proof_file': None},
                    format='json',
                )
            self.assertEqual(cleared.status_code, status.HTTP_200_OK, cleared.data)
            honor.refresh_from_db()
            self.assertFalse(second_path.exists())
            self.assertFalse(honor.proof_file)
            self.assertEqual(honor.proof_file_size, 0)
