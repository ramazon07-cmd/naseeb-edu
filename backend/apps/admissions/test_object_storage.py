"""Private files on object storage: presigned delivery, caching and cleanup.

Object storage is replaced by an in-memory storage that presigns fake URLs, so
nothing here touches the network.
"""
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.storage import storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from core.storage_config import PRIVATE_STORAGE_ALIAS
from core.storage_testing import in_memory_storages

from .models import Document, School, StudentProfile, Task
from .views.common import FILE_LINK_CONTENT_TYPE

User = get_user_model()
PDF_BYTES = b'%PDF-1.4\nprivate transcript\n%%EOF'


def pdf(name='transcript.pdf'):
    return SimpleUploadedFile(name, PDF_BYTES, content_type='application/pdf')


class ObjectStorageFixture(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Bucket School', code='bucket-school')
        self.counselor = User.objects.create_user(
            username='bucket-counselor', email='bucket-counselor@example.com',
            password='StrongPass123!', role=User.Role.COUNSELOR, school=self.school,
        )
        self.organization = User.objects.create_user(
            username='bucket-org', email='bucket-org@example.com',
            password='StrongPass123!', role=User.Role.ORGANIZATION, school=self.school,
        )
        self.student_user = User.objects.create_user(
            username='bucket-student', email='bucket-student@example.com',
            password='StrongPass123!', role=User.Role.STUDENT, school=self.school,
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user, school=self.school, school_name=self.school.name,
            assigned_counselor=self.counselor,
        )
        other_user = User.objects.create_user(
            username='bucket-other', email='bucket-other@example.com',
            password='StrongPass123!', role=User.Role.STUDENT, school=self.school,
        )
        self.other_student = StudentProfile.objects.create(
            user=other_user, school=self.school, school_name=self.school.name,
        )

    @property
    def bucket(self):
        return storages[PRIVATE_STORAGE_ALIAS]

    def upload_document(self, name='Official transcript.pdf'):
        self.client.force_authenticate(self.student_user)
        response = self.client.post(
            '/api/documents/',
            {
                'student': self.student.id, 'title': 'Transcript',
                'document_type': Document.Type.TRANSCRIPT, 'status': Document.Status.UPLOADED,
                'file': pdf(name),
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return Document.objects.get(pk=response.data['id'])


@override_settings(STORAGES=in_memory_storages(), PRIVATE_FILE_URL_EXPIRE_SECONDS=60)
class PresignedDeliveryTests(ObjectStorageFixture):
    def test_authorised_request_redirects_to_a_short_lived_presigned_url(self):
        document = self.upload_document()
        self.assertTrue(self.bucket.exists(document.file.name))

        response = self.client.get(f'/api/documents/{document.id}/file/')
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertTrue(response['Location'].startswith(f'https://bucket.test/{document.file.name}'))
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(self.bucket.calls[-1], {
            'name': document.file.name, 'filename': 'Official transcript.pdf',
            'content_type': 'application/pdf', 'as_attachment': False, 'expire': 60,
        })

        self.client.get(f'/api/documents/{document.id}/file/?download=1')
        self.assertTrue(self.bucket.calls[-1]['as_attachment'])

    def test_url_mode_returns_the_link_as_json_for_browser_clients(self):
        document = self.upload_document()
        response = self.client.get(f'/api/documents/{document.id}/file/?mode=url&download=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], FILE_LINK_CONTENT_TYPE)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        payload = response.json()
        self.assertEqual(set(payload), {'url', 'expires_at', 'file_name', 'content_type'})
        self.assertIn('expires=60', payload['url'])
        self.assertEqual(payload['file_name'], 'Official transcript.pdf')
        self.assertEqual(payload['content_type'], 'application/pdf')

    def test_authorisation_still_runs_before_any_url_is_signed(self):
        document = self.upload_document()
        self.bucket.calls.clear()
        self.client.force_authenticate(self.other_student.user)
        self.assertEqual(
            self.client.get(f'/api/documents/{document.id}/file/?mode=url').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get(f'/api/documents/{document.id}/file/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(self.bucket.calls, [])

    def test_hidden_task_submissions_stay_hidden_from_school_accounts(self):
        task = Task.objects.create(
            student=self.student, assigned_by=self.counselor, title='Resume', due_date=date(2027, 12, 1),
        )
        self.client.force_authenticate(self.student_user)
        uploaded = self.client.patch(
            f'/api/tasks/{task.id}/', {'submission_file': pdf('resume.pdf')}, format='multipart',
        )
        self.assertEqual(uploaded.status_code, status.HTTP_200_OK, uploaded.data)
        self.bucket.calls.clear()

        self.client.force_authenticate(self.organization)
        self.assertEqual(
            self.client.get(f'/api/tasks/{task.id}/submission-file/').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.bucket.calls, [])
        self.client.force_authenticate(self.counselor)
        self.assertEqual(
            self.client.get(f'/api/tasks/{task.id}/submission-file/').status_code,
            status.HTTP_302_FOUND,
        )

    def test_unsafe_types_are_always_signed_as_attachments(self):
        self.client.force_authenticate(self.student_user)
        response = self.client.post(
            '/api/documents/',
            {
                'student': self.student.id, 'title': 'Notes', 'document_type': Document.Type.OTHER,
                'status': Document.Status.UPLOADED,
                'file': SimpleUploadedFile('notes.rtf', b'{\\rtf1 hello}', content_type='application/rtf'),
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.client.get(f"/api/documents/{response.data['id']}/file/")
        self.assertTrue(self.bucket.calls[-1]['as_attachment'])

    def test_list_responses_never_contain_bucket_urls(self):
        self.upload_document()
        self.client.force_authenticate(self.counselor)
        body = self.client.get('/api/documents/').content.decode()
        self.assertNotIn('bucket.test', body)
        self.assertIn('/api/documents/', body)


class FilesystemDeliveryTests(ObjectStorageFixture):
    def test_local_disk_streams_and_ignores_url_mode(self):
        import tempfile

        with tempfile.TemporaryDirectory() as root, override_settings(DOCUMENT_STORAGE_ROOT=root):
            document = self.upload_document('a.pdf')
            response = self.client.get(f'/api/documents/{document.id}/file/?mode=url')
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response['Content-Type'], 'application/pdf')
            self.assertEqual(b''.join(response.streaming_content), PDF_BYTES)


def png(name='me.png', color=(10, 120, 200)):
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new('RGB', (4, 4), color).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


@override_settings(STORAGES=in_memory_storages())
class VersionedImageTests(ObjectStorageFixture):
    def upload_photo(self, color=(10, 120, 200)):
        self.client.force_authenticate(self.student_user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f'/api/students/{self.student.id}/photo/', {'photo': png(color=color)}, format='multipart',
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data['photo_version']

    def test_versioned_photo_urls_are_cached_privately_for_a_day(self):
        version = self.upload_photo()
        self.assertRegex(version, r'^[0-9a-f]{16}$')
        url = f'/api/students/{self.student.id}/photo/'

        cached = self.client.get(f'{url}?v={version}')
        self.assertEqual(cached.status_code, status.HTTP_200_OK)
        self.assertEqual(cached['Cache-Control'], 'private, max-age=86400, immutable')
        self.assertEqual(cached['ETag'], f'"{version}"')
        self.assertEqual(cached['Content-Type'], 'image/png')
        self.assertTrue(b''.join(cached.streaming_content).startswith(b'\x89PNG'))

        for stale in (url, f'{url}?v=0000000000000000'):
            self.assertEqual(self.client.get(stale)['Cache-Control'], 'private, no-cache')
        # Photos are small and cacheable: streamed, never presigned.
        self.assertEqual(self.bucket.calls, [])

    def test_revalidation_answers_304_without_reading_storage(self):
        from unittest import mock

        version = self.upload_photo()
        with mock.patch.object(type(self.bucket), '_open', side_effect=AssertionError('read')):
            response = self.client.get(
                f'/api/students/{self.student.id}/photo/', HTTP_IF_NONE_MATCH=f'"{version}"',
            )
        self.assertEqual(response.status_code, status.HTTP_304_NOT_MODIFIED)

    def test_replacing_a_photo_changes_its_version_and_removes_the_old_object(self):
        first = self.upload_photo()
        old_name = StudentProfile.objects.get(pk=self.student.pk).photo.name
        second = self.upload_photo(color=(200, 20, 20))
        self.assertNotEqual(first, second)
        self.assertFalse(self.bucket.exists(old_name))

        self.client.force_authenticate(self.counselor)
        listed = self.client.get(f'/api/students/{self.student.id}/')
        self.assertEqual(listed.data['photo_version'], second)

    def test_photo_access_is_scoped(self):
        version = self.upload_photo()
        self.client.force_authenticate(self.other_student.user)
        self.assertEqual(
            self.client.get(f'/api/students/{self.student.id}/photo/?v={version}').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_avatars_read_back_as_the_scoped_versioned_endpoint(self):
        self.client.force_authenticate(self.student_user)
        response = self.client.patch(
            f'/api/users/accounts/{self.student_user.id}/', {'avatar': png()}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.student_user.refresh_from_db()
        stored = self.student_user.avatar.name
        self.assertTrue(storages['default'].exists(stored))
        avatar_url = response.data['avatar']
        self.assertRegex(
            avatar_url, rf'^http://testserver/api/users/accounts/{self.student_user.id}/avatar/\?v=[0-9a-f]{{16}}$',
        )
        self.assertNotIn('bucket.test', avatar_url)

        own = self.client.get(avatar_url)
        self.assertEqual(own.status_code, status.HTTP_200_OK)
        self.assertEqual(own['Cache-Control'], 'private, max-age=86400, immutable')

        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get(avatar_url).status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.other_student.user)
        self.assertEqual(self.client.get(avatar_url).status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(self.student_user)
        with self.captureOnCommitCallbacks(execute=True):
            replaced = self.client.patch(
                f'/api/users/accounts/{self.student_user.id}/', {'avatar': png(color=(1, 2, 3))}, format='multipart',
            )
        self.assertEqual(replaced.status_code, status.HTTP_200_OK, replaced.data)
        self.assertNotEqual(replaced.data['avatar'], avatar_url)
        self.assertFalse(storages['default'].exists(stored))

    def test_accounts_without_an_avatar_read_null_and_404(self):
        self.client.force_authenticate(self.student_user)
        me = self.client.get('/api/users/accounts/me/')
        self.assertIsNone(me.data['avatar'])
        self.assertEqual(
            self.client.get(f'/api/users/accounts/{self.student_user.id}/avatar/').status_code,
            status.HTTP_404_NOT_FOUND,
        )


@override_settings(STORAGES=in_memory_storages())
class StoredObjectCleanupTests(ObjectStorageFixture):
    """Rows deleted directly or by cascade remove their objects after commit."""

    def populate(self):
        from django.core.files.base import ContentFile

        from .models import Honor, RecommendationLetter

        document = self.upload_document()
        honor = Honor.objects.create(student=self.student, title='Honor', issuer='School', level='national')
        honor.proof_file.save('honor.pdf', ContentFile(PDF_BYTES))
        letter = RecommendationLetter.objects.create(student=self.student, recommender_name='Dr. Smith')
        letter.file.save('letter.pdf', ContentFile(PDF_BYTES))
        self.student.photo.save('me.png', png())
        self.student_user.avatar.save('me.png', png())
        names = {
            PRIVATE_STORAGE_ALIAS: [document.file.name, honor.proof_file.name, letter.file.name, self.student.photo.name],
            'default': [self.student_user.avatar.name],
        }
        for alias, stored in names.items():
            for name in stored:
                self.assertTrue(storages[alias].exists(name), name)
        return names

    def assert_exist(self, names, expected):
        for alias, stored in names.items():
            for name in stored:
                self.assertEqual(storages[alias].exists(name), expected, name)

    def test_deleting_an_account_removes_every_cascaded_object_on_commit(self):
        names = self.populate()
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.student_user.delete()
        # Nothing is removed until the transaction commits.
        self.assert_exist(names, True)
        from .progress_cache import _bump

        self.assertEqual(len([callback for callback in callbacks if callback is not _bump]), 5)
        for callback in callbacks:
            callback()
        self.assert_exist(names, False)

    def test_a_rolled_back_delete_keeps_the_objects(self):
        from django.db import transaction

        names = self.populate()
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    Document.objects.filter(student=self.student).delete()
                    raise RuntimeError('abort')
            except RuntimeError:
                pass
        self.assert_exist(names, True)

    @override_settings(STORAGES=in_memory_storages('core.storage_testing.FlakyInMemoryStorage'))
    def test_a_storage_error_is_logged_and_does_not_stop_other_deletes(self):
        from django.core.files.base import ContentFile

        from .models import Honor

        names = []
        for title in ('First', 'Second'):
            honor = Honor.objects.create(student=self.student, title=title, issuer='School', level='national')
            honor.proof_file.save('proof.pdf', ContentFile(PDF_BYTES))
            names.append(honor.proof_file.name)
        with self.assertLogs('django', level='ERROR'):
            with self.captureOnCommitCallbacks(execute=True):
                Honor.objects.filter(student=self.student).delete()
        self.assertFalse(Honor.objects.exists())
        self.assertEqual(len(self.bucket.failed_deletes), 1)
        failed = self.bucket.failed_deletes[0]
        self.assertTrue(self.bucket.exists(failed))
        self.assertFalse(self.bucket.exists(next(name for name in names if name != failed)))


class MigrateFilesToObjectStorageTests(ObjectStorageFixture):
    def setUp(self):
        import tempfile

        super().setUp()
        self.media_root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.private_root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.documents = []
        for index in range(3):
            name = f'student_documents/{self.student.id}/doc-{index}.pdf'
            self.write(self.private_root, name, PDF_BYTES + bytes([index]))
            self.documents.append(Document.objects.create(
                student=self.student, title=f'Doc {index}', document_type=Document.Type.OTHER,
                status=Document.Status.UPLOADED, file=name,
            ))
        self.write(self.private_root, f'student_photos/{self.student.id}/p.png', b'\x89PNG photo')
        StudentProfile.objects.filter(pk=self.student.pk).update(photo=f'student_photos/{self.student.id}/p.png')
        self.write(self.media_root, 'avatars/me.png', b'\x89PNG avatar')
        User.objects.filter(pk=self.student_user.pk).update(avatar='avatars/me.png')
        # A row whose file was lost from the disk.
        Document.objects.create(
            student=self.student, title='Lost', document_type=Document.Type.OTHER,
            status=Document.Status.UPLOADED, file='student_documents/lost.pdf',
        )

    @staticmethod
    def write(root, name, content):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def migrate(self, *extra):
        from io import StringIO

        from django.core.management import call_command

        output = StringIO()
        call_command(
            'migrate_files_to_object_storage', '--media-root', str(self.media_root),
            '--private-root', str(self.private_root), *extra, stdout=output,
        )
        return output.getvalue()

    def read(self, alias, name):
        with storages[alias].open(name) as handle:
            return handle.read()

    @override_settings(STORAGES=in_memory_storages())
    def test_copies_referenced_files_under_the_same_names_and_is_idempotent(self):
        dry = self.migrate('--dry-run')
        self.assertIn('Done: would copy 5, skipped 0 already stored, 1 missing locally, 0 failed.', dry)
        self.assertFalse(self.bucket.exists(self.documents[0].file.name))

        output = self.migrate('--batch-size', '2')
        self.assertIn('Done: copied 5, skipped 0 already stored, 1 missing locally, 0 failed.', output)
        self.assertIn('admissions.Document.file batch 2:', output)
        self.assertEqual(self.read(PRIVATE_STORAGE_ALIAS, self.documents[2].file.name), PDF_BYTES + b'\x02')
        self.assertEqual(self.read(PRIVATE_STORAGE_ALIAS, f'student_photos/{self.student.id}/p.png'), b'\x89PNG photo')
        self.assertEqual(self.read('default', 'avatars/me.png'), b'\x89PNG avatar')

        again = self.migrate()
        self.assertIn('Done: copied 0, skipped 5 already stored, 1 missing locally, 0 failed.', again)

    @override_settings(STORAGES=in_memory_storages())
    def test_resume_overwrites_a_partial_object_at_the_same_key(self):
        from django.core.files.base import ContentFile

        name = self.documents[0].file.name
        self.bucket._save(name, ContentFile(b'%PDF-partial'))
        self.bucket._save(self.documents[1].file.name, ContentFile(PDF_BYTES + b'\x01'))
        output = self.migrate()
        self.assertIn('Done: copied 4, skipped 1 already stored', output)
        self.assertEqual(self.read(PRIVATE_STORAGE_ALIAS, name), PDF_BYTES + b'\x00')
        self.assertEqual(sorted(self.bucket.listdir(f'student_documents/{self.student.id}')[1]), [
            'doc-0.pdf', 'doc-1.pdf', 'doc-2.pdf',
        ])

    @override_settings(STORAGES=in_memory_storages())
    def test_reads_rows_in_bounded_batches(self):
        # One keyset-paginated query per batch: Document.file has 4 rows
        # (2 + 2 + an empty page); the seven other file fields hold at most one
        # row each, which a single short page answers.
        with self.assertNumQueries(3 + 7):
            self.migrate('--batch-size', '2', '--dry-run')

    def test_refuses_to_run_against_the_local_disk(self):
        from django.core.management.base import CommandError

        with self.assertRaisesMessage(CommandError, 'STORAGE_BACKEND=s3'):
            self.migrate()
