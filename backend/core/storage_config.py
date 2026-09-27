"""STORAGES builder, kept free of Django imports so settings.py can use it."""

FILESYSTEM_STORAGE = 'filesystem'
S3_STORAGE = 's3'
STORAGE_BACKENDS = (FILESYSTEM_STORAGE, S3_STORAGE)
PRIVATE_STORAGE_ALIAS = 'private_documents'


def build_storages(*, backend, s3_options=None, media_location='media', private_location='private', private_bucket=''):
    """Return the STORAGES setting for the selected backend.

    ``default`` holds account avatars, ``private_documents`` every student
    upload. Both are private in object storage; they differ only in key prefix
    (and optionally bucket).
    """
    static = {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}
    if backend != S3_STORAGE:
        return {
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            PRIVATE_STORAGE_ALIAS: {'BACKEND': 'core.storage.PrivateFileSystemStorage'},
            'staticfiles': static,
        }
    options = dict(s3_options or {})
    private_options = {**options, 'location': private_location}
    if private_bucket:
        private_options['bucket_name'] = private_bucket
    return {
        'default': {'BACKEND': 'core.storage.PrivateS3Storage', 'OPTIONS': {**options, 'location': media_location}},
        PRIVATE_STORAGE_ALIAS: {'BACKEND': 'core.storage.PrivateS3Storage', 'OPTIONS': private_options},
        'staticfiles': static,
    }
