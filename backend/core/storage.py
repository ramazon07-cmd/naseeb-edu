"""File storage backends and the settings that select them.

Development and tests keep files on the local disk. Production uses an
S3-compatible bucket (AWS S3 or Cloudflare R2) so any number of instances can
serve the same files. Every object is private: files reach users only through
authorised API endpoints, which either stream them (local disk) or hand out a
short-lived presigned URL (object storage).
"""
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage, storages
from django.db import transaction
from django.utils.deconstruct import deconstructible
from django.utils.http import content_disposition_header
from storages.backends.s3 import S3Storage

from core.storage_config import PRIVATE_STORAGE_ALIAS


class PrivateFileSystemStorage(FileSystemStorage):
    """Local private files, outside the public /media/ route.

    The root is read on every access so tests can point it at a temporary
    directory with ``override_settings(DOCUMENT_STORAGE_ROOT=...)``.
    """

    @property
    def base_location(self):
        return settings.DOCUMENT_STORAGE_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None


class PrivateS3Storage(S3Storage):
    """Private S3/R2 storage: signed URLs only, never overwrites a key."""

    def get_default_settings(self):
        defaults = super().get_default_settings()
        # Never build unsigned or custom-domain URLs for private objects, and
        # never replace an existing object that happens to share a name.
        defaults.update(custom_domain=None, querystring_auth=True, file_overwrite=False)
        return defaults

    def presigned_url(self, name, *, filename, content_type, as_attachment, expire):
        return self.url(
            name,
            parameters={
                'ResponseContentDisposition': content_disposition_header(as_attachment, filename),
                'ResponseContentType': content_type,
                'ResponseCacheControl': 'private, no-store',
            },
            expire=expire,
        )


@deconstructible(path='apps.admissions.models.PrivateDocumentStorage')
class PrivateDocumentStorage(Storage):
    """Model-field storage that forwards to ``STORAGES['private_documents']``.

    Fields keep one stable storage reference (so switching backends needs no
    migration) while the backend itself is chosen by settings at runtime.
    """

    @property
    def backend(self):
        return storages[PRIVATE_STORAGE_ALIAS]

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return getattr(self.backend, name)

    def open(self, name, mode='rb'):
        return self.backend.open(name, mode)

    def save(self, name, content, max_length=None):
        return self.backend.save(name, content, max_length=max_length)

    def generate_filename(self, filename):
        return self.backend.generate_filename(filename)

    def get_valid_name(self, name):
        return self.backend.get_valid_name(name)

    def get_available_name(self, name, max_length=None):
        return self.backend.get_available_name(name, max_length=max_length)

    def get_alternative_name(self, file_root, file_ext):
        return self.backend.get_alternative_name(file_root, file_ext)

    def path(self, name):
        return self.backend.path(name)

    def delete(self, name):
        return self.backend.delete(name)

    def exists(self, name):
        return self.backend.exists(name)

    def listdir(self, path):
        return self.backend.listdir(path)

    def size(self, name):
        return self.backend.size(name)

    def url(self, name):
        return self.backend.url(name)

    def get_accessed_time(self, name):
        return self.backend.get_accessed_time(name)

    def get_created_time(self, name):
        return self.backend.get_created_time(name)

    def get_modified_time(self, name):
        return self.backend.get_modified_time(name)


def delete_file_on_commit(storage, name):
    """Delete a stored file once the surrounding transaction commits.

    A rolled-back change keeps its file. ``robust`` logs a storage error (for
    example the bucket being briefly unreachable) instead of failing the request
    after its data was already committed; at worst an orphaned object remains.
    """
    if name:
        transaction.on_commit(lambda: storage.delete(name), robust=True)


def resolve_backend(storage):
    return storage.backend if isinstance(storage, PrivateDocumentStorage) else storage


def presigned_file_url(field_file, *, filename, content_type, as_attachment, expire=None):
    """Return a short-lived direct URL for the file, or None on local disk."""
    backend = resolve_backend(field_file.storage)
    presign = getattr(backend, 'presigned_url', None)
    if presign is None:
        return None
    return presign(
        field_file.name,
        filename=filename,
        content_type=content_type,
        as_attachment=as_attachment,
        expire=expire or settings.PRIVATE_FILE_URL_EXPIRE_SECONDS,
    )
