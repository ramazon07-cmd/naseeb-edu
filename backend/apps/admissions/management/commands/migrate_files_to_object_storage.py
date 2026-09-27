"""Copy uploads from the local disk to the configured object storage.

Only files referenced by a database row are copied, under the same name, so
no row changes. Safe to re-run or resume after an interruption: an object that
already exists with the same size (and, for single-part uploads, the same MD5
ETag) is skipped.
"""
import hashlib
import logging
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage, storages
from django.core.management.base import BaseCommand, CommandError

from apps.admissions.signals import FILE_APPS, file_fields
from core.storage import PrivateDocumentStorage
from core.storage_config import PRIVATE_STORAGE_ALIAS

logger = logging.getLogger('naseeb.storage')


def file_md5(path):
    digest = hashlib.md5(usedforsecurity=False)
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def remote_fingerprint(storage, name):
    """(size, md5-or-None) of a stored object, or None when it is missing."""
    bucket = getattr(storage, 'bucket', None)
    if bucket is not None:
        from botocore.exceptions import ClientError

        obj = bucket.Object(storage._normalize_name(name))
        try:
            obj.load()
        except ClientError as error:
            if error.response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 404:
                return None
            raise
        etag = (obj.e_tag or '').strip('"')
        # Multipart ETags ("<hash>-<parts>") are not an MD5 of the content.
        return obj.content_length, (etag if etag and '-' not in etag else None)
    if not storage.exists(name):
        return None
    return storage.size(name), None


class Command(BaseCommand):
    help = 'Copy referenced uploads from MEDIA_ROOT/DOCUMENT_STORAGE_ROOT to the configured object storage.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report what would be copied; write nothing.')
        parser.add_argument('--batch-size', type=int, default=200, help='Rows read per query (default 200).')
        parser.add_argument('--media-root', default=None, help='Local source for avatars (default MEDIA_ROOT).')
        parser.add_argument(
            '--private-root', default=None,
            help='Local source for private documents (default DOCUMENT_STORAGE_ROOT).',
        )

    def handle(self, *args, **options):
        batch_size = max(1, options['batch_size'])
        dry_run = options['dry_run']
        destinations = {'default': storages['default'], PRIVATE_STORAGE_ALIAS: storages[PRIVATE_STORAGE_ALIAS]}
        if any(isinstance(storage, FileSystemStorage) for storage in destinations.values()):
            raise CommandError('Configure object storage first (STORAGE_BACKEND=s3); the destination is the local disk.')
        sources = {
            'default': Path(options['media_root'] or settings.MEDIA_ROOT),
            PRIVATE_STORAGE_ALIAS: Path(options['private_root'] or settings.DOCUMENT_STORAGE_ROOT),
        }
        totals = {'copied': 0, 'skipped': 0, 'missing': 0, 'failed': 0}
        for model, field in self.models_with_files():
            alias = PRIVATE_STORAGE_ALIAS if isinstance(field.storage, PrivateDocumentStorage) else 'default'
            label = f'{model._meta.label}.{field.name}'
            for batch_number, names in enumerate(self.batches(model, field.name, batch_size), start=1):
                counts = self.copy_batch(names, sources[alias], destinations[alias], dry_run=dry_run)
                for key, value in counts.items():
                    totals[key] += value
                logger.info('%s batch %s: %s', label, batch_number, counts)
                self.stdout.write(f'{label} batch {batch_number}: ' + ', '.join(f'{k} {v}' for k, v in counts.items()))
        verb = 'would copy' if dry_run else 'copied'
        summary = (
            f"Done: {verb} {totals['copied']}, skipped {totals['skipped']} already stored, "
            f"{totals['missing']} missing locally, {totals['failed']} failed."
        )
        if totals['failed']:
            raise CommandError(summary + ' Re-run to retry the failed files.')
        self.stdout.write(self.style.SUCCESS(summary))

    @staticmethod
    def models_with_files():
        for label in FILE_APPS:
            for model in apps.get_app_config(label).get_models():
                for field in file_fields(model):
                    yield model, field

    @staticmethod
    def batches(model, field_name, batch_size):
        """Stored names in primary-key order, one bounded query per batch."""
        queryset = model._default_manager.exclude(**{field_name: ''}).exclude(**{f'{field_name}__isnull': True})
        last_pk = None
        while True:
            page = queryset.order_by('pk')
            if last_pk is not None:
                page = page.filter(pk__gt=last_pk)
            rows = list(page.values_list('pk', field_name)[:batch_size])
            if rows:
                last_pk = rows[-1][0]
                yield [name for _, name in rows]
            if len(rows) < batch_size:
                return

    def copy_batch(self, names, source_root, destination, *, dry_run):
        counts = {'copied': 0, 'skipped': 0, 'missing': 0, 'failed': 0}
        for name in names:
            path = (source_root / name).resolve()
            if not path.is_relative_to(source_root.resolve()) or not path.is_file():
                counts['missing'] += 1
                logger.warning('Missing local file %s', name)
                continue
            try:
                remote = remote_fingerprint(destination, name)
                size = path.stat().st_size
                if remote and remote[0] == size and (remote[1] is None or remote[1] == file_md5(path)):
                    counts['skipped'] += 1
                    continue
                if not dry_run:
                    with open(path, 'rb') as handle:
                        # _save writes the exact key (save() would pick a new
                        # name when a partial copy already exists).
                        destination._save(name, File(handle, name=name))
                counts['copied'] += 1
            except Exception:
                counts['failed'] += 1
                logger.exception('Could not copy %s', name)
        return counts
