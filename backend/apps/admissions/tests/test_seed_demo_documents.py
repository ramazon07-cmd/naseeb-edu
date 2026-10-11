from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.admissions.models import ActivityLog, Document
from core.storage_testing import in_memory_storages


@override_settings(DEMO_ACCOUNTS_ENABLED=True, STORAGES=in_memory_storages())
class SeedDemoDocumentsTests(TestCase):
    def seed(self):
        call_command('seed_demo', stdout=StringIO())

    def test_document_statuses_match_files_comments_and_activity(self):
        self.seed()
        documents = Document.objects.all()
        self.assertTrue(documents.exists())
        for doc in documents:
            logs = ActivityLog.objects.filter(metadata__kind='document', metadata__record=doc.pk)
            if doc.status == Document.Status.REQUIRED:
                self.assertFalse(doc.file, doc.title)
                continue
            self.assertTrue(doc.file, doc.title)
            self.assertEqual(doc.file_content_type, 'application/pdf')
            with doc.file.open('rb') as handle:
                data = handle.read()
            self.assertTrue(data.startswith(b'%PDF-1.4') and data.rstrip().endswith(b'%%EOF'))
            self.assertEqual(doc.file_size, len(data))
            if doc.status in (Document.Status.APPROVED, Document.Status.REJECTED):
                self.assertTrue(doc.counselor_comment, doc.title)
                self.assertEqual(logs.count(), 1, doc.title)
                self.assertEqual(logs.get().action, f'Document approved: {doc.title}')
            else:
                self.assertFalse(logs.exists(), doc.title)

    def test_reseeding_adds_no_files_or_log_entries(self):
        self.seed()
        files = dict(Document.objects.values_list('pk', 'file'))
        logs = ActivityLog.objects.count()
        self.seed()
        self.assertEqual(dict(Document.objects.values_list('pk', 'file')), files)
        self.assertEqual(ActivityLog.objects.count(), logs)

    def test_reseeding_completes_documents_seeded_before_files_existed(self):
        self.seed()
        Document.objects.update(file='', file_size=0, file_content_type='', counselor_comment='')
        ActivityLog.objects.filter(metadata__kind='document').delete()
        self.seed()
        self.assertFalse(Document.objects.exclude(status=Document.Status.REQUIRED).filter(file='').exists())
        approved = Document.objects.filter(status=Document.Status.APPROVED)
        self.assertFalse(approved.filter(counselor_comment='').exists())
        self.assertEqual(ActivityLog.objects.filter(metadata__kind='document').count(), approved.count())
