"""Network-free storage doubles for tests."""
from django.core.files.storage import InMemoryStorage

from core.storage_config import PRIVATE_STORAGE_ALIAS, build_storages


class PresigningInMemoryStorage(InMemoryStorage):
    """Stands in for object storage in tests: records presign calls."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = []

    def presigned_url(self, name, *, filename, content_type, as_attachment, expire):
        self.calls.append({
            'name': name, 'filename': filename, 'content_type': content_type,
            'as_attachment': as_attachment, 'expire': expire,
        })
        return f'https://bucket.test/{name}?signature=fake&expires={expire}'


def in_memory_storages(backend='core.storage_testing.PresigningInMemoryStorage'):
    return {
        **build_storages(backend='filesystem'),
        'default': {'BACKEND': backend},
        PRIVATE_STORAGE_ALIAS: {'BACKEND': backend},
    }


class FlakyInMemoryStorage(PresigningInMemoryStorage):
    """Fails its first delete, like a briefly unreachable bucket."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.failed_deletes = []

    def delete(self, name):
        if not self.failed_deletes:
            self.failed_deletes.append(name)
            raise OSError('storage unavailable')
        return super().delete(name)
