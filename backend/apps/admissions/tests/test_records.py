"""Role isolation: tasks, documents, evidence, applications and other student records."""
from datetime import date
import io
import tempfile
import zipfile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from ..models import (
    Achievement,
    Activity,
    Application,
    Document,
    Essay,
    Honor,
    MeetingNote,
    Notification,
    Project,
    RecommendationLetter,
    Task,
    University,
    XPTransaction,
)
from .base import RoleIsolationBase


class RecordRoleIsolationTests(RoleIsolationBase):
    def test_student_reads_only_own_tasks_certificates_essays_and_meetings(self):
        records = {
            'tasks': (
                Task.objects.create(student=self.student_a, title='My task', due_date=date(2027, 12, 1)),
                Task.objects.create(student=self.student_b, title='Other task', due_date=date(2027, 12, 1)),
            ),
            'documents': (
                Document.objects.create(student=self.student_a, title='My certificate', document_type=Document.Type.CERTIFICATE),
                Document.objects.create(student=self.student_b, title='Other certificate', document_type=Document.Type.CERTIFICATE),
            ),
            'essays': (
                Essay.objects.create(student=self.student_a, title='My essay', prompt='My prompt'),
                Essay.objects.create(student=self.student_b, title='Other essay', prompt='Other prompt'),
            ),
            'meetings': (
                MeetingNote.objects.create(student=self.student_a, counselor=self.counselor, title='My meeting', summary='My summary'),
                MeetingNote.objects.create(student=self.student_b, counselor=self.counselor, title='Other meeting', summary='Other summary'),
            ),
        }
        self.client.force_authenticate(self.student_a_user)
        for path, (own_record, _) in records.items():
            with self.subTest(path=path):
                response = self.client.get(f'/api/{path}/')
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual([item['id'] for item in self.results(response)], [own_record.id])

    def test_student_cannot_create_task_for_another_student(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(
            '/api/tasks/',
            {
                'student': self.student_b.id,
                'title': 'Forbidden cross-school task',
                'due_date': date(2027, 12, 1),
                'priority': Task.Priority.LOW,
                'status': Task.Status.TODO,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Task.objects.filter(title='Forbidden cross-school task').exists())

    def test_student_can_create_and_manage_a_zero_xp_self_task(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(
            '/api/tasks/',
            {
                'student': self.student_a.id,
                'title': 'Self-assigned task',
                'due_date': date(2027, 12, 1),
                'priority': Task.Priority.LOW,
                'status': Task.Status.TODO,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        task = Task.objects.get(title='Self-assigned task')
        self.assertEqual(task.student, self.student_a)
        self.assertEqual(task.assigned_by, self.student_a_user)
        self.assertTrue(task.is_self_assigned)

        updated = self.client.patch(
            f'/api/tasks/{task.id}/',
            {'title': 'My personal study task', 'status': Task.Status.SUBMITTED},
            format='json',
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(self.teacher)
        approved = self.client.post(f'/api/tasks/{task.id}/approve/', {}, format='json')
        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        self.assertEqual(approved.data['xp_awarded'], 0)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.xp_total, 0)
        self.assertFalse(XPTransaction.objects.filter(source_id=task.id).exists())

    def test_student_can_delete_only_self_assigned_tasks(self):
        staff_task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.counselor,
            title='Counselor task cannot be deleted by student',
            due_date=date(2027, 12, 1),
        )
        self_task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.student_a_user,
            is_self_assigned=True,
            title='Personal task can be deleted',
            due_date=date(2027, 12, 2),
        )
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(
            self.client.delete(f'/api/tasks/{staff_task.id}/').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.delete(f'/api/tasks/{self_task.id}/').status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertTrue(Task.objects.filter(id=staff_task.id).exists())
        self.assertFalse(Task.objects.filter(id=self_task.id).exists())

    def test_student_can_only_update_task_progress_fields(self):
        task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.counselor,
            title='Counselor task',
            due_date=date(2027, 12, 1),
        )
        self.client.force_authenticate(self.student_a_user)
        progressed = self.client.patch(
            f'/api/tasks/{task.id}/',
            {'status': Task.Status.IN_PROGRESS},
            format='json',
        )
        self.assertEqual(progressed.status_code, status.HTTP_200_OK)
        tampered = self.client.patch(
            f'/api/tasks/{task.id}/',
            {'title': 'Student changed title', 'due_date': date(2030, 1, 1)},
            format='json',
        )
        self.assertEqual(tampered.status_code, status.HTTP_400_BAD_REQUEST)
        task.refresh_from_db()
        self.assertEqual(task.title, 'Counselor task')
        self.assertEqual(task.due_date, date(2027, 12, 1))

    def test_student_cannot_approve_own_task(self):
        task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.counselor,
            title='Counselor approval required',
            due_date=date(2027, 12, 1),
        )
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(f'/api/tasks/{task.id}/approve/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        task.refresh_from_db()
        self.assertNotEqual(task.status, Task.Status.APPROVED)

    def test_student_cannot_approve_own_document(self):
        document = Document.objects.create(
            student=self.student_a,
            title='Transcript',
            document_type=Document.Type.TRANSCRIPT,
            status=Document.Status.UPLOADED,
        )
        self.client.force_authenticate(self.student_a_user)
        response = self.client.patch(
            f'/api/documents/{document.id}/',
            {'status': Document.Status.APPROVED},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.UPLOADED)

    def test_private_document_upload_preview_download_and_role_isolation(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(DOCUMENT_STORAGE_ROOT=media_root):
            self.client.force_authenticate(self.student_a_user)
            uploaded = self.client.post(
                '/api/documents/',
                {
                    'student': self.student_a.id,
                    'title': 'Official transcript',
                    'document_type': Document.Type.TRANSCRIPT,
                    'status': Document.Status.UPLOADED,
                    'file': SimpleUploadedFile(
                        'official transcript.pdf',
                        b'%PDF-1.4\nprivate transcript\n%%EOF',
                        content_type='application/pdf',
                    ),
                },
                format='multipart',
            )
            self.assertEqual(uploaded.status_code, status.HTTP_201_CREATED)
            self.assertNotIn('file', uploaded.data)
            self.assertTrue(uploaded.data['has_file'])
            self.assertEqual(uploaded.data['file_name'], 'official transcript.pdf')
            self.assertEqual(uploaded.data['file_content_type'], 'application/pdf')
            self.assertTrue(uploaded.data['file_previewable'])
            document_id = uploaded.data['id']

            preview = self.client.get(f'/api/documents/{document_id}/file/')
            self.assertEqual(preview.status_code, status.HTTP_200_OK)
            self.assertIn('inline', preview['Content-Disposition'])
            self.assertEqual(b''.join(preview.streaming_content), b'%PDF-1.4\nprivate transcript\n%%EOF')
            download = self.client.get(f'/api/documents/{document_id}/file/?download=1')
            self.assertEqual(download.status_code, status.HTTP_200_OK)
            self.assertIn('attachment', download['Content-Disposition'])

            self.client.force_authenticate(self.student_b_user)
            self.assertEqual(self.client.get(f'/api/documents/{document_id}/file/').status_code, status.HTTP_404_NOT_FOUND)
            self.client.force_authenticate(self.counselor_b)
            self.assertEqual(self.client.get(f'/api/documents/{document_id}/file/').status_code, status.HTTP_404_NOT_FOUND)
            self.client.force_authenticate(self.counselor)
            self.assertEqual(self.client.get(f'/api/documents/{document_id}/file/').status_code, status.HTTP_200_OK)

    def test_document_upload_rejects_unsafe_damaged_empty_and_oversized_files(self):
        self.client.force_authenticate(self.student_a_user)
        cases = [
            ('malware.exe', b'MZ executable', 'application/octet-stream'),
            ('fake.pdf', b'not a pdf', 'application/pdf'),
            ('empty.txt', b'', 'text/plain'),
        ]
        for index, (name, content, content_type) in enumerate(cases):
            response = self.client.post(
                '/api/documents/',
                {
                    'student': self.student_a.id,
                    'title': f'Invalid {index}',
                    'document_type': Document.Type.OTHER,
                    'status': Document.Status.UPLOADED,
                    'file': SimpleUploadedFile(name, content, content_type=content_type),
                },
                format='multipart',
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        with override_settings(DOCUMENT_MAX_UPLOAD_SIZE=8):
            oversized = self.client.post(
                '/api/documents/',
                {
                    'student': self.student_a.id,
                    'title': 'Oversized PDF',
                    'document_type': Document.Type.OTHER,
                    'status': Document.Status.UPLOADED,
                    'file': SimpleUploadedFile('large.pdf', b'%PDF-1.4 too large', content_type='application/pdf'),
                },
                format='multipart',
            )
        # Refused while streaming, before the serializer sees the file.
        self.assertEqual(oversized.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.assertFalse(Document.objects.filter(title='Oversized PDF').exists())

    def test_office_document_upload_is_validated_and_download_only(self):
        office_file = io.BytesIO()
        with zipfile.ZipFile(office_file, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<Types />')
            archive.writestr('word/document.xml', '<document />')
        office_file.seek(0)

        with tempfile.TemporaryDirectory() as media_root, override_settings(DOCUMENT_STORAGE_ROOT=media_root):
            self.client.force_authenticate(self.counselor)
            uploaded = self.client.post(
                '/api/documents/',
                {
                    'student': self.student_a.id,
                    'title': 'Counselor recommendation',
                    'document_type': Document.Type.REC_LETTER,
                    'status': Document.Status.UPLOADED,
                    'file': SimpleUploadedFile(
                        'recommendation.docx',
                        office_file.getvalue(),
                        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    ),
                },
                format='multipart',
            )
            self.assertEqual(uploaded.status_code, status.HTTP_201_CREATED)
            self.assertFalse(uploaded.data['file_previewable'])
            response = self.client.get(f"/api/documents/{uploaded.data['id']}/file/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn('attachment', response['Content-Disposition'])

    def test_student_cannot_forge_counselor_comment_or_empty_uploaded_record(self):
        self.client.force_authenticate(self.student_a_user)
        forged = self.client.post(
            '/api/documents/',
            {
                'student': self.student_a.id,
                'title': 'Forged review',
                'document_type': Document.Type.OTHER,
                'status': Document.Status.UPLOADED,
                'counselor_comment': 'Approved by counselor',
                'google_docs_url': 'https://docs.google.com/document/d/student-file/edit',
            },
            format='json',
        )
        self.assertEqual(forged.status_code, status.HTTP_400_BAD_REQUEST)
        empty = self.client.post(
            '/api/documents/',
            {
                'student': self.student_a.id,
                'title': 'Empty upload',
                'document_type': Document.Type.OTHER,
                'status': Document.Status.UPLOADED,
            },
            format='json',
        )
        self.assertEqual(empty.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.counselor)
        requirement = self.client.post(
            '/api/documents/',
            {
                'student': self.student_a.id,
                'title': 'Passport required',
                'document_type': Document.Type.PASSPORT,
                'status': Document.Status.REQUIRED,
                'counselor_comment': 'Upload the identity page.',
            },
            format='json',
        )
        self.assertEqual(requirement.status_code, status.HTTP_201_CREATED)

    def test_student_task_response_and_google_docs_previews_are_visible_to_counselor(self):
        task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.counselor,
            title='Complete essay outline',
            description='Submit the outline and supporting link.',
            due_date=date(2027, 12, 1),
        )
        google_docs_url = 'https://docs.google.com/document/d/test-document-id/edit'
        self.client.force_authenticate(self.student_a_user)
        submitted = self.client.patch(
            f'/api/tasks/{task.id}/',
            {
                'status': Task.Status.SUBMITTED,
                'student_response': 'I completed the outline and explained my structure.',
                'submission_url': google_docs_url,
            },
            format='json',
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(submitted.data['submitted_at'])
        self.assertEqual(
            submitted.data['submission_preview_url'],
            'https://docs.google.com/document/d/test-document-id/preview',
        )

        document = self.client.post(
            '/api/documents/',
            {
                'student': self.student_a.id,
                'title': 'Google Docs planning file',
                'document_type': Document.Type.OTHER,
                'status': Document.Status.UPLOADED,
                'google_docs_url': google_docs_url,
            },
            format='json',
        )
        self.assertEqual(document.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            document.data['google_docs_preview_url'],
            'https://docs.google.com/document/d/test-document-id/preview',
        )
        essay = self.client.post(
            '/api/essays/',
            {
                'student': self.student_a.id,
                'title': 'Google Docs personal statement',
                'prompt': 'Describe your academic goals.',
                'google_docs_url': google_docs_url,
            },
            format='json',
        )
        self.assertEqual(essay.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            essay.data['google_docs_preview_url'],
            'https://docs.google.com/document/d/test-document-id/preview',
        )
        invalid_link = self.client.patch(
            f"/api/essays/{essay.data['id']}/",
            {'google_docs_url': 'https://example.com/not-google-docs'},
            format='json',
        )
        self.assertEqual(invalid_link.status_code, status.HTTP_400_BAD_REQUEST)

        shared = self.client.post(f"/api/essay-lab/essays/{essay.data['id']}/share/")
        self.assertEqual(shared.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(self.counselor)
        counselor_task = self.client.get(f'/api/tasks/{task.id}/')
        self.assertEqual(counselor_task.status_code, status.HTTP_200_OK)
        self.assertEqual(counselor_task.data['student_response'], 'I completed the outline and explained my structure.')
        self.assertEqual(self.client.get(f"/api/documents/{document.data['id']}/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f"/api/essays/{essay.data['id']}/").status_code, status.HTTP_200_OK)

    def test_shared_google_docs_support_for_student_records(self):
        google_docs_url = 'https://docs.google.com/document/d/shared-record-document/edit'
        expected_preview = 'https://docs.google.com/document/d/shared-record-document/preview'
        resources = {
            'researches': {
                'title': 'AI education research',
                'summary': 'Research summary.',
            },
            'projects': {
                'title': 'Admissions dashboard',
                'description': 'Project description.',
            },
            'internships': {
                'organization': 'Naseeb Edu',
                'position': 'Student intern',
            },
            'activities': {
                'name': 'University club',
                'activity_type': Activity.Type.CLUB,
            },
            'honors': {
                'title': 'Academic honor',
                'level': Honor.Level.SCHOOL,
            },
            'recommendations': {
                'recommender_name': 'Teacher Name',
                'status': RecommendationLetter.Status.REQUESTED,
            },
        }

        self.client.force_authenticate(self.student_a_user)
        created = {}
        for resource, payload in resources.items():
            with self.subTest(resource=resource):
                response = self.client.post(
                    f'/api/{resource}/',
                    {
                        **payload,
                        'student': self.student_a.id,
                        'google_docs_url': google_docs_url,
                    },
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                self.assertEqual(response.data['google_docs_url'], google_docs_url)
                self.assertEqual(response.data['google_docs_preview_url'], expected_preview)
                created[resource] = response.data['id']

        invalid = self.client.patch(
            f"/api/researches/{created['researches']}/",
            {'google_docs_url': 'https://example.com/not-google-docs'},
            format='json',
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.student_b_user)
        blocked = self.client.patch(
            f"/api/projects/{created['projects']}/",
            {'google_docs_url': google_docs_url},
            format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(self.counselor)
        for resource, record_id in created.items():
            with self.subTest(counselor_resource=resource):
                response = self.client.get(f'/api/{resource}/{record_id}/')
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data['google_docs_preview_url'], expected_preview)

    def test_student_can_create_own_project_but_not_verify_it(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(
            '/api/projects/',
            {
                'student': self.student_a.id,
                'title': 'Student portfolio project',
                'description': 'A real student-owned project.',
                'verified': True,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(
            '/api/projects/',
            {
                'student': self.student_a.id,
                'title': 'Student portfolio project',
                'description': 'A real student-owned project.',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Project.objects.get(id=response.data['id']).verified)

    def test_student_cannot_verify_own_achievement(self):
        achievement = Achievement.objects.create(
            student=self.student_a,
            title='Regional award',
            category=Achievement.Category.OLYMPIAD,
            description='A submitted achievement.',
        )
        self.client.force_authenticate(self.student_a_user)
        response = self.client.patch(
            f'/api/achievements/{achievement.id}/',
            {'verified': True},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        achievement.refresh_from_db()
        self.assertFalse(achievement.verified)

    def test_student_cannot_create_project_for_another_student(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(
            '/api/projects/',
            {
                'student': self.student_b.id,
                'title': 'Cross student project',
                'description': 'Must be rejected.',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_application_status_history_is_recorded(self):
        university = University.objects.create(name='History University', country='Testland')
        self.client.force_authenticate(self.counselor)
        created = self.client.post(
            '/api/applications/',
            {
                'student': self.student_a.id,
                'university': university.id,
                'program': 'Computer Science',
                'status': Application.Status.RESEARCHING,
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        application_id = created.data['id']
        updated = self.client.patch(
            f'/api/applications/{application_id}/',
            {'status': Application.Status.SUBMITTED},
            format='json',
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(len(updated.data['status_history']), 2)

    def test_essay_revisions_are_versioned(self):
        self.client.force_authenticate(self.student_a_user)
        created = self.client.post(
            '/api/essays/',
            {
                'student': self.student_a.id,
                'title': 'Personal Statement',
                'prompt': 'Tell your story.',
                'content': 'First draft',
                'status': Essay.Status.DRAFT,
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        updated = self.client.patch(
            f"/api/essays/{created.data['id']}/",
            {'content': 'Second draft'},
            format='json',
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data['version'], 2)
        self.assertEqual(len(updated.data['revisions']), 2)

    def test_student_can_mark_own_notification_read(self):
        notification = Notification.objects.create(
            student=self.student_a,
            title='Deadline',
            message='A deadline is approaching.',
        )
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(f'/api/notifications/{notification.id}/read/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_student_can_shortlist_own_university_but_not_record_decision(self):
        university = University.objects.create(name='Student Choice University', country='Testland')
        self.client.force_authenticate(self.student_a_user)
        created = self.client.post(
            '/api/applications/',
            {
                'student': self.student_a.id,
                'university': university.id,
                'program': 'Computer Science',
                'tier': 'target',
                'status': Application.Status.SHORTLISTED,
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        denied = self.client.patch(
            f"/api/applications/{created.data['id']}/",
            {'status': Application.Status.ACCEPTED},
            format='json',
        )
        self.assertEqual(denied.status_code, status.HTTP_400_BAD_REQUEST)
