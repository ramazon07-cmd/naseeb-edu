import io
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadhandler import MemoryFileUploadHandler, TemporaryFileUploadHandler
from django.http.multipartparser import MultiPartParser
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import Document, School, StudentProfile
from apps.admissions.views.students import StudentProfileViewSet
from core.storage_config import PRIVATE_STORAGE_ALIAS
from core.storage_testing import in_memory_storages

from .models import User
from .uploads import FileSizeLimitUploadHandler, RequestSizeLimitMiddleware, UploadTooLarge


class CountingStream(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.bytes_read = 0

    def read(self, size=-1):
        chunk = super().read(size)
        self.bytes_read += len(chunk)
        return chunk


class FileSizeLimitUploadHandlerTests(SimpleTestCase):
    def parse(self, payload, *, limit):
        body = encode_multipart(BOUNDARY, {'file': SimpleUploadedFile('big.pdf', payload)})
        stream = CountingStream(body)
        request = RequestFactory().post('/api/documents/')
        request.upload_size_limit = limit
        handlers = [
            FileSizeLimitUploadHandler(request),
            MemoryFileUploadHandler(request),
            TemporaryFileUploadHandler(request),
        ]
        meta = {'CONTENT_TYPE': MULTIPART_CONTENT, 'CONTENT_LENGTH': str(len(body))}
        return stream, len(body), MultiPartParser(meta, stream, handlers).parse

    def test_oversized_file_is_refused_before_the_body_is_read(self):
        stream, total, parse = self.parse(b'x' * (4 * 1024 * 1024), limit=64 * 1024)
        with self.assertRaises(UploadTooLarge) as caught:
            parse()
        self.assertEqual(caught.exception.status_code, 413)
        # Stops within a couple of parser chunks (64 KiB each) of the limit.
        self.assertLess(stream.bytes_read, 512 * 1024)
        self.assertLess(stream.bytes_read, total // 4)

    def test_files_within_the_limit_pass_through_untouched(self):
        _, _, parse = self.parse(b'y' * 1000, limit=1000)
        _, files = parse()
        self.assertEqual(files['file'].read(), b'y' * 1000)

    @override_settings(DOCUMENT_MAX_UPLOAD_SIZE=2048)
    def test_default_limit_is_the_document_limit(self):
        request = RequestFactory().post('/')
        handler = FileSizeLimitUploadHandler(request)
        handler.new_file('file', 'a.pdf', 'application/pdf', 4096)
        handler.receive_data_chunk(b'a' * 2048, 0)
        with self.assertRaises(UploadTooLarge):
            handler.receive_data_chunk(b'a', 2048)

    def test_plain_django_views_get_a_json_413(self):
        middleware = RequestSizeLimitMiddleware(lambda request: None)
        response = middleware.process_exception(RequestFactory().post('/admin/'), UploadTooLarge(2 * 1024 * 1024))
        self.assertEqual(response.status_code, 413)
        self.assertIn(b'2 MB', response.content)
        self.assertIsNone(middleware.process_exception(RequestFactory().get('/'), ValueError()))


@override_settings(STORAGES=in_memory_storages(), MAX_REQUEST_BODY_SIZE=10 * 1024 * 1024)
class UploadLimitApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Limit School', code='limit-school')
        self.user = User.objects.create_user(
            username='limit-student', email='limit-student@example.com',
            password='StrongPass123!', role=User.Role.STUDENT, school=self.school,
        )
        self.student = StudentProfile.objects.create(user=self.user, school=self.school, school_name='Limit School')
        self.client.force_authenticate(self.user)

    def stored_names(self):
        from django.core.files.storage import storages

        return storages[PRIVATE_STORAGE_ALIAS].listdir('')

    @override_settings(DOCUMENT_MAX_UPLOAD_SIZE=1024)
    def test_oversized_document_gets_413_and_nothing_is_stored(self):
        response = self.client.post(
            '/api/documents/',
            {
                'student': self.student.id, 'title': 'Too big', 'document_type': Document.Type.OTHER,
                'status': Document.Status.UPLOADED,
                'file': SimpleUploadedFile('big.pdf', b'%PDF-1.4\n' + b'x' * 4096),
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.assertEqual(response.json()['detail'], 'File is larger than the 1 MB limit.')
        self.assertFalse(Document.objects.exists())
        self.assertEqual(self.stored_names(), ([], []))

    def test_photo_endpoint_applies_its_own_smaller_limit_while_streaming(self):
        with mock.patch.object(StudentProfileViewSet, 'PHOTO_MAX_BYTES', 1024):
            response = self.client.post(
                f'/api/students/{self.student.id}/photo/',
                {'photo': SimpleUploadedFile('me.png', b'\x89PNG' + b'x' * 4096)},
                format='multipart',
            )
        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.student.refresh_from_db()
        self.assertFalse(self.student.photo)

    @override_settings(AVATAR_MAX_UPLOAD_SIZE=1024)
    def test_avatar_updates_apply_the_avatar_limit(self):
        response = self.client.patch(
            f'/api/users/accounts/{self.user.id}/',
            {'avatar': SimpleUploadedFile('me.png', b'\x89PNG' + b'x' * 4096)},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)
