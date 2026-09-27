"""Private file uploads: accepted types, rejection, naming, access and replacement."""
import io
import tempfile
import zipfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image
from rest_framework import status

from apps.users.models import User
from .models import Activity, Document
from .serializers.common import clean_upload_name
from .tests.base import RoleIsolationBase

PDF = b'%PDF-1.4\nprivate transcript\n%%EOF'
OLE_HEADER = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
HEIC = b'\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic' + b'\x00' * 64


def image_bytes(image_format):
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), (200, 160, 90)).save(buffer, format=image_format)
    return buffer.getvalue()


def docx_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types />')
        archive.writestr('word/document.xml', '<document />')
    return buffer.getvalue()


class CleanUploadNameTests(SimpleTestCase):
    def test_keeps_ordinary_names(self):
        self.assertEqual(clean_upload_name('Official transcript.pdf'), 'Official transcript.pdf')
        self.assertEqual(clean_upload_name('Паспорт скан.JPG'), 'Паспорт скан.JPG')

    def test_strips_paths_control_and_bidi_characters(self):
        self.assertEqual(clean_upload_name('C:\\Users\\me\\cv.docx'), 'cv.docx')
        self.assertEqual(clean_upload_name('../../etc/passwd.pdf'), 'passwd.pdf')
        self.assertEqual(clean_upload_name('bad\r\nname\x00.pdf'), 'badname.pdf')
        self.assertEqual(clean_upload_name('cv\u202efdp.docx'), 'cvfdp.docx')
        self.assertEqual(clean_upload_name('  many   spaces .pdf '), 'many spaces.pdf')

    def test_falls_back_and_keeps_the_extension_when_truncating(self):
        self.assertEqual(clean_upload_name('', 'document'), 'document')
        self.assertEqual(clean_upload_name('\u202e.pdf', 'document'), 'pdf')
        self.assertEqual(clean_upload_name('\x01\x01.pdf', 'document'), 'pdf')
        long_name = clean_upload_name('a' * 400 + '.docx')
        self.assertEqual(len(long_name), 255)
        self.assertTrue(long_name.endswith('.docx'))


class PrivateStorageTestCase(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.private_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.private_root.cleanup)
        storage = override_settings(DOCUMENT_STORAGE_ROOT=self.private_root.name)
        storage.enable()
        self.addCleanup(storage.disable)


class PrivateUploadTests(PrivateStorageTestCase):
    def upload(self, name, content, *, user=None, **extra):
        self.client.force_authenticate(user or self.student_a_user)
        return self.client.post(
            '/api/documents/',
            {
                'student': self.student_a.id,
                'title': extra.pop('title', name),
                'document_type': Document.Type.OTHER,
                'file': SimpleUploadedFile(name, content),
                **extra,
            },
            format='multipart',
        )

    def test_each_supported_type_uploads_with_its_metadata(self):
        cases = [
            ('transcript.pdf', PDF, 'application/pdf', True),
            ('letter.doc', OLE_HEADER + b'\x00' * 64, 'application/msword', False),
            ('essay.docx', docx_bytes(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', False),
            ('scan.jpg', image_bytes('JPEG'), 'image/jpeg', True),
            ('scan.jpeg', image_bytes('JPEG'), 'image/jpeg', True),
            ('scan.png', image_bytes('PNG'), 'image/png', True),
            ('scan.webp', image_bytes('WEBP'), 'image/webp', True),
            ('photo.heic', HEIC, 'image/heic', False),
        ]
        for name, content, content_type, previewable in cases:
            with self.subTest(name=name):
                response = self.upload(name, content)
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                self.assertEqual(response.data['file_name'], name)
                self.assertEqual(response.data['file_content_type'], content_type)
                self.assertEqual(response.data['file_size'], len(content))
                self.assertEqual(response.data['file_previewable'], previewable)
                self.assertEqual(response.data['status'], Document.Status.UPLOADED)
                document = Document.objects.get(pk=response.data['id'])
                # Stored under a random key, never the user's file name.
                self.assertNotIn(Path(name).stem, document.file.name)
                self.assertTrue(document.file.name.endswith(Path(name).suffix.lower()))

    def test_wrong_types_and_disguised_content_are_rejected(self):
        cases = [
            ('program.exe', b'MZ executable'),
            ('animation.gif', b'GIF89a' + b'\x00' * 32),
            ('no-extension', PDF),
            ('image.pdf', image_bytes('PNG')),
            ('fake.docx', PDF),
            ('fake.doc', PDF),
            ('fake.jpg', PDF),
            ('fake.heic', b'\x00' * 20 + b'ftyp' + b'\x00' * 40),
            ('empty.pdf', b''),
        ]
        for name, content in cases:
            with self.subTest(name=name):
                response = self.upload(name, content)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self.assertIn('file', response.data)
        self.assertFalse(Document.objects.exists())
        self.assertEqual([path for path in Path(self.private_root.name).rglob('*') if path.is_file()], [])

    def test_oversized_files_are_refused_while_streaming(self):
        with override_settings(DOCUMENT_MAX_UPLOAD_SIZE=16):
            response = self.upload('big.pdf', PDF)
        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.assertIn('limit', str(response.data['detail']))
        self.assertFalse(Document.objects.exists())

    def test_unsafe_names_are_cleaned_before_they_reach_content_disposition(self):
        response = self.upload('..\\evil\tname\u202e.pdf', PDF)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['file_name'], 'evilname.pdf')
        download = self.client.get(f"/api/documents/{response.data['id']}/file/?download=1")
        self.assertEqual(download.status_code, status.HTTP_200_OK)
        self.assertEqual(download['Content-Disposition'], 'attachment; filename="evilname.pdf"')
        self.assertEqual(download['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(download['Cache-Control'], 'private, no-store')

    def test_word_files_are_always_served_as_attachments(self):
        response = self.upload('essay.docx', docx_bytes())
        served = self.client.get(f"/api/documents/{response.data['id']}/file/")
        self.assertEqual(served.status_code, status.HTTP_200_OK)
        self.assertTrue(served['Content-Disposition'].startswith('attachment;'))

    def test_download_is_limited_to_the_owner_staff_and_their_school(self):
        created = self.upload('transcript.pdf', PDF)
        url = f"/api/documents/{created.data['id']}/file/?download=1"
        unassigned_counselor = User.objects.create_user(
            username='unassigned-counselor', email='unassigned@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school_a,
        )
        other_school_account = User.objects.create_user(
            username='organization-b', email='organization-b@example.com', password='StrongPass123!',
            role=User.Role.ORGANIZATION, school=self.school_b,
        )
        expected = [
            (self.student_a_user, status.HTTP_200_OK),
            (self.counselor, status.HTTP_200_OK),
            (self.organization, status.HTTP_200_OK),
            (self.student_b_user, status.HTTP_404_NOT_FOUND),
            (self.counselor_b, status.HTTP_404_NOT_FOUND),
            (unassigned_counselor, status.HTTP_404_NOT_FOUND),
            (other_school_account, status.HTTP_404_NOT_FOUND),
        ]
        for user, code in expected:
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                self.assertEqual(self.client.get(url).status_code, code)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_counselor_uploads_for_an_assigned_student_only(self):
        allowed = self.upload('counselor.pdf', PDF, user=self.counselor)
        self.assertEqual(allowed.status_code, status.HTTP_201_CREATED, allowed.data)
        self.assertEqual(Document.objects.get(pk=allowed.data['id']).uploaded_by, self.counselor)
        refused = self.upload('cross-school.pdf', PDF, user=self.counselor_b)
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(self.organization)
        document_id = allowed.data['id']
        replaced = self.client.patch(
            f'/api/documents/{document_id}/', {'file': SimpleUploadedFile('org.pdf', PDF)}, format='multipart',
        )
        self.assertEqual(replaced.status_code, status.HTTP_403_FORBIDDEN)

    def test_replacing_a_file_deletes_the_old_one_only_after_commit(self):
        created = self.upload('first.pdf', PDF)
        document = Document.objects.get(pk=created.data['id'])
        first_path = Path(document.file.path)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            replaced = self.client.patch(
                f'/api/documents/{document.id}/',
                {'file': SimpleUploadedFile('second.docx', docx_bytes())},
                format='multipart',
            )
            self.assertEqual(replaced.status_code, status.HTTP_200_OK, replaced.data)
            self.assertTrue(first_path.exists())
        self.assertTrue(first_path.exists())
        for callback in callbacks:
            callback()
        self.assertFalse(first_path.exists())
        document.refresh_from_db()
        self.assertTrue(Path(document.file.path).exists())
        self.assertEqual(document.original_file_name, 'second.docx')
        self.assertFalse(replaced.data['file_previewable'])

    def test_a_rejected_replacement_keeps_the_current_file(self):
        created = self.upload('first.pdf', PDF)
        document = Document.objects.get(pk=created.data['id'])
        with self.captureOnCommitCallbacks(execute=True):
            refused = self.client.patch(
                f'/api/documents/{document.id}/',
                {'file': SimpleUploadedFile('second.pdf', b'not a pdf')},
                format='multipart',
            )
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        document.refresh_from_db()
        self.assertEqual(document.original_file_name, 'first.pdf')
        self.assertTrue(Path(document.file.path).exists())

    def test_switching_to_a_google_docs_link_removes_the_file(self):
        created = self.upload('first.pdf', PDF)
        document = Document.objects.get(pk=created.data['id'])
        first_path = Path(document.file.path)
        with self.captureOnCommitCallbacks(execute=True):
            switched = self.client.patch(
                f'/api/documents/{document.id}/',
                {'file': '', 'google_docs_url': 'https://docs.google.com/document/d/abc123/edit'},
                format='multipart',
            )
        self.assertEqual(switched.status_code, status.HTTP_200_OK, switched.data)
        self.assertFalse(switched.data['has_file'])
        self.assertEqual(switched.data['file_size'], 0)
        self.assertFalse(first_path.exists())


class ActivityEvidenceTests(PrivateStorageTestCase):
    def test_activity_proof_is_validated_replaced_and_scoped(self):
        self.client.force_authenticate(self.student_a_user)
        refused = self.client.post(
            '/api/activities/',
            {'student': self.student_a.id, 'name': 'Debate', 'proof_file': SimpleUploadedFile('proof.gif', b'GIF89a')},
            format='multipart',
        )
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        created = self.client.post(
            '/api/activities/',
            {'student': self.student_a.id, 'name': 'Debate', 'proof_file': SimpleUploadedFile('photo.jpg', image_bytes('JPEG'))},
            format='multipart',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(created.data['proof_file_content_type'], 'image/jpeg')
        self.assertTrue(created.data['proof_file_previewable'])
        activity_id = created.data['id']
        url = f'/api/activities/{activity_id}/proof-file/'
        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)

        first_path = Path(Activity.objects.get(pk=activity_id).proof_file.path)
        with self.captureOnCommitCallbacks(execute=True):
            replaced = self.client.patch(
                f'/api/activities/{activity_id}/',
                {'proof_file': SimpleUploadedFile('certificate.docx', docx_bytes())},
                format='multipart',
            )
        self.assertEqual(replaced.status_code, status.HTTP_200_OK, replaced.data)
        self.assertFalse(first_path.exists())
        self.assertFalse(replaced.data['proof_file_previewable'])

        for user, code in (
            (self.counselor, status.HTTP_200_OK),
            (self.student_b_user, status.HTTP_404_NOT_FOUND),
            (self.counselor_b, status.HTTP_404_NOT_FOUND),
        ):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                self.assertEqual(self.client.get(url).status_code, code)
