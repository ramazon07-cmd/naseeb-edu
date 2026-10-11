from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.admissions.management.commands.seed_demo import Command
from apps.admissions.models import ChannelMembership, Essay, EssayTab, MessageChannel
from apps.admissions.views.messaging import unread_channel_messages
from apps.users.models import User
from core.storage_testing import in_memory_storages


@override_settings(DEMO_ACCOUNTS_ENABLED=True, STORAGES=in_memory_storages())
class SeedDemoContentTests(TestCase):
    def seed(self):
        call_command('seed_demo', stdout=StringIO())

    def statements(self):
        return Essay.objects.filter(title='Main Personal Statement').select_related('student__user')

    def test_personal_statements_hold_a_real_draft(self):
        self.seed()
        essays = self.statements()
        self.assertEqual(essays.count(), 4)
        for essay in essays:
            draft = Command.DEMO_DRAFTS[essay.student.user.username]
            self.assertEqual(essay.content, draft)
            self.assertGreater(essay.word_count, 100)
            self.assertIn(len(essay.content.split('\n\n')), (2, 3))
            self.assertEqual(EssayTab.objects.get(essay=essay).content, draft)

    def test_reseeding_replaces_the_old_placeholder_but_keeps_student_edits(self):
        self.seed()
        aziza, ramazon = self.statements().get(student__user__username='aziza'), self.statements().get(student__user__username='ramazon')
        # Rows seeded by the old command: the placeholder in the essay and its lazily created tab.
        for essay in (aziza, ramazon):
            EssayTab.objects.filter(essay=essay).update(content=Command.DEMO_DRAFT_PLACEHOLDER, doc=None)
            Essay.objects.filter(pk=essay.pk).update(content=Command.DEMO_DRAFT_PLACEHOLDER, word_count=7)
        EssayTab.objects.filter(essay=ramazon).update(content='My own words.')
        Essay.objects.filter(pk=ramazon.pk).update(content='My own words.')
        self.seed()
        aziza.refresh_from_db()
        ramazon.refresh_from_db()
        self.assertEqual(aziza.content, Command.DEMO_DRAFTS['aziza'])
        self.assertEqual(EssayTab.objects.get(essay=aziza).content, Command.DEMO_DRAFTS['aziza'])
        self.assertEqual(ramazon.content, 'My own words.')
        self.assertEqual(self.statements().count(), 4)
        self.assertEqual(EssayTab.objects.filter(essay__title='Main Personal Statement').count(), 4)

    def test_counselor_has_read_the_threads_they_replied_in(self):
        self.seed()
        counselor = User.objects.get(username='counselor')
        discussion = MessageChannel.objects.get(kind=MessageChannel.Kind.DISCUSSION, name__startswith='How do I make')
        self.assertFalse(unread_channel_messages(counselor).filter(channel=discussion).exists())
        # Read only up to their own reply: a later message is still new to them.
        ChannelMembership.objects.filter(channel=discussion, user=counselor).update(last_read_at=None)
        self.seed()
        self.assertFalse(unread_channel_messages(counselor).filter(channel=discussion).exists())
        student = User.objects.get(username='ramazon')
        discussion.messages.create(sender=student, body='Thanks, that helps.')
        self.assertTrue(unread_channel_messages(counselor).filter(channel=discussion).exists())
