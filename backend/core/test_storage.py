from urllib.parse import parse_qs, urlparse

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.test import SimpleTestCase, override_settings

from core.environment import validate_storage_environment
from core.storage import PrivateDocumentStorage, PrivateFileSystemStorage, PrivateS3Storage, presigned_file_url
from core.storage_config import PRIVATE_STORAGE_ALIAS, build_storages
from core.storage_testing import in_memory_storages


PRODUCTION = {'app_env': 'production'}


class StorageEnvironmentTests(SimpleTestCase):
    def test_production_refuses_local_disk_without_single_instance_override(self):
        errors = validate_storage_environment(
            **PRODUCTION, backend='filesystem', media_root='/m', document_storage_root='/d',
        )
        self.assertTrue(any('STORAGE_BACKEND=s3' in error for error in errors))

    def test_single_instance_override_still_requires_persistent_roots(self):
        errors = validate_storage_environment(**PRODUCTION, backend='filesystem', single_instance=True)
        self.assertTrue(any('MEDIA_ROOT' in error for error in errors))
        self.assertTrue(any('DOCUMENT_STORAGE_ROOT' in error for error in errors))
        self.assertEqual(
            validate_storage_environment(
                **PRODUCTION, backend='filesystem', single_instance=True,
                media_root='/mnt/media', document_storage_root='/mnt/private',
            ),
            [],
        )

    def test_object_storage_needs_no_local_paths_in_production(self):
        self.assertEqual(
            validate_storage_environment(
                **PRODUCTION, backend='s3', bucket='naseeb-files', access_key='AKIA', secret_key='secret',
            ),
            [],
        )

    def test_object_storage_requires_a_bucket_and_paired_keys(self):
        errors = validate_storage_environment(**PRODUCTION, backend='s3', access_key='AKIA')
        self.assertTrue(any('AWS_STORAGE_BUCKET_NAME' in error for error in errors))
        self.assertTrue(any('AWS_SECRET_ACCESS_KEY' in error for error in errors))

    def test_unknown_backend_is_rejected_everywhere(self):
        for app_env in ('development', 'production'):
            errors = validate_storage_environment(app_env=app_env, backend='gcs')
            self.assertTrue(any('STORAGE_BACKEND' in error for error in errors), app_env)

    def test_development_keeps_local_disk_without_configuration(self):
        self.assertEqual(validate_storage_environment(app_env='development', backend='filesystem'), [])


class BuildStoragesTests(SimpleTestCase):
    def test_filesystem_backend_keeps_private_files_off_the_media_root(self):
        config = build_storages(backend='filesystem')
        self.assertEqual(config['default']['BACKEND'], 'django.core.files.storage.FileSystemStorage')
        self.assertEqual(config[PRIVATE_STORAGE_ALIAS]['BACKEND'], 'core.storage.PrivateFileSystemStorage')
        self.assertIn('staticfiles', config)

    def test_s3_backend_separates_media_and_private_prefixes(self):
        config = build_storages(
            backend='s3', s3_options={'bucket_name': 'files'}, private_bucket='private-files',
        )
        self.assertEqual(config['default']['OPTIONS'], {'bucket_name': 'files', 'location': 'media'})
        self.assertEqual(
            config[PRIVATE_STORAGE_ALIAS]['OPTIONS'], {'bucket_name': 'private-files', 'location': 'private'},
        )


def s3_storage(**overrides):
    options = {
        'bucket_name': 'naseeb-files',
        'access_key': 'test-access-key',
        'secret_key': 'test-secret-key',
        'endpoint_url': 'https://account.r2.cloudflarestorage.com',
        'region_name': 'auto',
        'signature_version': 's3v4',
        'location': 'private',
        **overrides,
    }
    return PrivateS3Storage(**options)


class PrivateS3StorageTests(SimpleTestCase):
    """Presigning is local HMAC work: no request leaves the process."""

    def test_presigned_url_is_short_lived_and_sets_response_headers(self):
        url = s3_storage().presigned_url(
            'student_documents/7/file.pdf', filename='Transcript ö.pdf',
            content_type='application/pdf', as_attachment=True, expire=60,
        )
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, 'https')
        self.assertTrue(parsed.netloc.endswith('account.r2.cloudflarestorage.com'))
        # Path-style or virtual-host addressing, depending on botocore's choice.
        self.assertIn('naseeb-files', parsed.netloc + parsed.path)
        self.assertTrue(parsed.path.endswith('/private/student_documents/7/file.pdf'))
        self.assertEqual(query['X-Amz-Expires'], ['60'])
        self.assertIn('X-Amz-Signature', query)
        self.assertEqual(query['response-content-type'], ['application/pdf'])
        self.assertEqual(query['response-cache-control'], ['private, no-store'])
        disposition = query['response-content-disposition'][0]
        self.assertTrue(disposition.startswith('attachment;'))
        self.assertIn("filename*=utf-8''Transcript%20%C3%B6.pdf", disposition)

    @override_settings(AWS_S3_CUSTOM_DOMAIN='files.example.com', AWS_QUERYSTRING_AUTH=False, AWS_S3_FILE_OVERWRITE=True)
    def test_private_storage_ignores_public_url_settings(self):
        storage = s3_storage()
        self.assertIsNone(storage.custom_domain)
        self.assertTrue(storage.querystring_auth)
        self.assertFalse(storage.file_overwrite)
        self.assertIn('X-Amz-Signature=', storage.url('a.pdf'))

    def test_inline_disposition_for_previews(self):
        url = s3_storage().presigned_url(
            'a.png', filename='a.png', content_type='image/png', as_attachment=False, expire=30,
        )
        query = parse_qs(urlparse(url).query)
        self.assertTrue(query['response-content-disposition'][0].startswith('inline;'))
        self.assertEqual(query['X-Amz-Expires'], ['30'])


class PrivateDocumentStorageProxyTests(SimpleTestCase):
    def test_deconstructs_to_the_historic_model_path(self):
        path, args, kwargs = PrivateDocumentStorage().deconstruct()
        self.assertEqual(path, 'apps.admissions.models.PrivateDocumentStorage')
        self.assertEqual((args, kwargs), ((), {}))

    def test_default_backend_is_private_filesystem(self):
        self.assertIsInstance(PrivateDocumentStorage().backend, PrivateFileSystemStorage)
        self.assertIsNone(presigned_file_url(
            type('F', (), {'storage': PrivateDocumentStorage(), 'name': 'x.pdf'})(),
            filename='x.pdf', content_type='application/pdf', as_attachment=False,
        ))

    @override_settings(STORAGES=in_memory_storages(), PRIVATE_FILE_URL_EXPIRE_SECONDS=45)
    def test_forwards_to_the_configured_backend(self):
        proxy = PrivateDocumentStorage()
        name = proxy.save('student_documents/1/a.txt', ContentFile(b'hello'))
        self.assertIs(proxy.backend, storages[PRIVATE_STORAGE_ALIAS])
        self.assertTrue(proxy.exists(name))
        self.assertEqual(proxy.size(name), 5)
        with proxy.open(name) as handle:
            self.assertEqual(handle.read(), b'hello')
        field_file = type('F', (), {'storage': proxy, 'name': name})()
        url = presigned_file_url(field_file, filename='a.txt', content_type='text/plain', as_attachment=True)
        self.assertTrue(url.startswith('https://bucket.test/student_documents/1/a.txt'))
        self.assertIn('expires=45', url)
        proxy.delete(name)
        self.assertFalse(proxy.exists(name))


class ProductionStartupTests(SimpleTestCase):
    """The settings module itself refuses local disk in production."""

    def run_check(self, **extra):
        import os
        import subprocess
        import sys
        from django.conf import settings
        env = {key: value for key, value in os.environ.items() if key in {'PATH', 'HOME', 'SYSTEMROOT'}}
        env.update({
            'APP_ENV': 'production',
            'DEBUG': 'False',
            'SECRET_KEY': 'a-unique-production-secret-with-more-than-32-characters',
            'DATABASE_URL': 'postgres://user:pass@db.invalid:5432/naseeb',
            'ENABLE_DEMO_ACCOUNTS': 'False',
            'ALLOWED_HOSTS': 'api.test',
            **extra,
        })
        return subprocess.run(
            [sys.executable, '-c', 'import django; django.setup(); from django.conf import settings; '
             'print(settings.STORAGES["private_documents"]["BACKEND"])'],
            cwd=settings.BASE_DIR, env={**env, 'DJANGO_SETTINGS_MODULE': 'core.settings'},
            capture_output=True, text=True, timeout=120,
        )

    def test_local_disk_is_refused_without_override(self):
        result = self.run_check(MEDIA_ROOT='/mnt/media', DOCUMENT_STORAGE_ROOT='/mnt/private')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FILE_STORAGE_SINGLE_INSTANCE', result.stderr)

    def test_single_instance_override_keeps_local_disk(self):
        result = self.run_check(
            FILE_STORAGE_SINGLE_INSTANCE='True', MEDIA_ROOT='/mnt/media', DOCUMENT_STORAGE_ROOT='/mnt/private',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PrivateFileSystemStorage', result.stdout)

    def test_object_storage_starts_without_local_paths(self):
        result = self.run_check(
            STORAGE_BACKEND='s3', AWS_STORAGE_BUCKET_NAME='naseeb-files',
            AWS_ACCESS_KEY_ID='key', AWS_SECRET_ACCESS_KEY='secret',
            AWS_S3_ENDPOINT_URL='https://account.r2.cloudflarestorage.com', AWS_S3_REGION_NAME='auto',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PrivateS3Storage', result.stdout)


class RemoteFingerprintTests(SimpleTestCase):
    """The resume check of migrate_files_to_object_storage, against stubbed S3."""

    def test_head_object_size_and_single_part_md5(self):
        from botocore.stub import Stubber

        from apps.admissions.management.commands.migrate_files_to_object_storage import remote_fingerprint

        storage = s3_storage()
        with Stubber(storage.connection.meta.client) as stub:
            expected = {'Bucket': 'naseeb-files', 'Key': 'private/a.pdf'}
            stub.add_response('head_object', {'ContentLength': 5, 'ETag': '"5d41402abc4b2a76b9719d911017c592"'}, expected)
            stub.add_response('head_object', {'ContentLength': 9, 'ETag': '"0f343b0931126a20f133d67c2b018a3b-2"'}, expected)
            stub.add_client_error('head_object', http_status_code=404, service_error_code='404', expected_params=expected)
            self.assertEqual(remote_fingerprint(storage, 'a.pdf'), (5, '5d41402abc4b2a76b9719d911017c592'))
            self.assertEqual(remote_fingerprint(storage, 'a.pdf'), (9, None))
            self.assertIsNone(remote_fingerprint(storage, 'a.pdf'))
