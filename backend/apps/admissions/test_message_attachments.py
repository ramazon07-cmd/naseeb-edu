"""Chat attachments: students send one private file per message to their counselor."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status

from .models import ChannelMembership, ChannelMessage, MessageChannel
from .test_private_uploads import PDF, PrivateStorageTestCase, docx_bytes, image_bytes


class MessageAttachmentTests(PrivateStorageTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.student_a_user)
        opened = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        self.channel_id = opened.data['id']

    def send(self, name, content, *, user=None, channel=None, body=''):
        self.client.force_authenticate(user or self.student_a_user)
        return self.client.post('/api/channel-messages/', {
            'channel': channel or self.channel_id,
            'body': body,
            'attachment': SimpleUploadedFile(name, content),
        }, format='multipart')

    def download(self, message_id, user):
        self.client.force_authenticate(user)
        return self.client.get(f'/api/channel-messages/{message_id}/attachment/')

    def test_student_sends_a_photo_and_both_participants_can_download_it(self):
        png = image_bytes('PNG')
        sent = self.send('scan.png', png)
        self.assertEqual(sent.status_code, status.HTTP_201_CREATED, sent.data)
        attached = sent.data['attachment_file']
        self.assertEqual(attached['name'], 'scan.png')
        self.assertEqual(attached['content_type'], 'image/png')
        self.assertEqual(attached['size'], len(png))
        self.assertTrue(attached['is_image'])
        self.assertIn(f'/api/channel-messages/{sent.data["id"]}/attachment/', attached['url'])
        self.assertEqual(sent.data['body'], '')
        message = ChannelMessage.objects.get(pk=sent.data['id'])
        self.assertTrue(message.attachment.name.startswith(f'message_attachments/{self.channel_id}/'))
        self.assertNotIn('scan', message.attachment.name)

        for user in (self.student_a_user, self.counselor):
            with self.subTest(user=user.username):
                response = self.download(sent.data['id'], user)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(b''.join(response.streaming_content), png)
                self.assertEqual(response['Cache-Control'], 'private, no-store')
                self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_pdf_and_word_files_are_accepted_with_a_caption(self):
        pdf = self.send('transcript.pdf', PDF, body='My transcript')
        self.assertEqual(pdf.status_code, status.HTTP_201_CREATED, pdf.data)
        self.assertEqual(pdf.data['body'], 'My transcript')
        self.assertFalse(pdf.data['attachment_file']['is_image'])
        word = self.send('essay.docx', docx_bytes())
        self.assertEqual(word.status_code, status.HTTP_201_CREATED, word.data)
        response = self.download(word.data['id'], self.counselor)
        self.assertIn('attachment;', response['Content-Disposition'])

    def test_listing_shows_the_attachment_and_polling_still_revalidates(self):
        sent = self.send('scan.png', image_bytes('PNG'))
        self.client.force_authenticate(self.counselor)
        listed = self.client.get(f'/api/channel-messages/?channel={self.channel_id}&page_size=50')
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(listed.data['results'][0]['attachment_file']['name'], 'scan.png')
        self.assertNotIn('attachment', listed.data['results'][0])
        again = self.client.get(
            f'/api/channel-messages/?channel={self.channel_id}&page_size=50', HTTP_IF_NONE_MATCH=listed['ETag'],
        )
        self.assertEqual(again.status_code, status.HTTP_304_NOT_MODIFIED)
        older = self.client.get(f'/api/channel-messages/?channel={self.channel_id}&page_size=50&before={sent.data["id"]}')
        self.assertEqual(older.status_code, status.HTTP_200_OK)
        channel = self.client.get(f'/api/message-channels/{self.channel_id}/')
        self.assertEqual(channel.data['last_message']['attachment_name'], 'scan.png')

    def test_non_participants_get_404(self):
        sent = self.send('scan.png', image_bytes('PNG'))
        for user in (self.student_b_user, self.counselor_b, self.teacher, self.organization):
            with self.subTest(user=user.username):
                self.assertEqual(self.download(sent.data['id'], user).status_code, status.HTTP_404_NOT_FOUND)

    def test_public_channel_readers_who_are_not_members_cannot_download(self):
        channel = MessageChannel.objects.create(
            kind=MessageChannel.Kind.COMMUNITY, name='Open', school=self.school_a, is_public=True,
            created_by=self.counselor,
        )
        ChannelMembership.objects.create(channel=channel, user=self.counselor, role=ChannelMembership.Role.OWNER)
        message = ChannelMessage.objects.create(channel=channel, sender=self.counselor, body='See file')
        message.attachment.save('notes.pdf', SimpleUploadedFile('notes.pdf', PDF))
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get(f'/api/channel-messages/{message.id}/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.download(message.id, self.teacher).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.download(message.id, self.counselor).status_code, status.HTTP_200_OK)

    def test_unsupported_or_spoofed_files_are_rejected(self):
        cases = {
            'run.exe': b'MZ\x90\x00',
            'sheet.xlsx': docx_bytes(),
            'fake.pdf': b'<html>not a pdf</html>',
            'fake.png': b'not an image at all',
            'fake.docx': b'plain text',
            'empty.pdf': b'',
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                response = self.send(name, content)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('attachment', response.data)
        self.assertFalse(ChannelMessage.objects.exists())

    @override_settings(DOCUMENT_MAX_UPLOAD_SIZE=1024)
    def test_files_over_the_document_limit_are_rejected(self):
        response = self.send('big.pdf', PDF + b'0' * 2048)
        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.assertFalse(ChannelMessage.objects.exists())

    def test_a_message_needs_text_or_a_file(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post('/api/channel-messages/', {'channel': self.channel_id, 'body': '  '}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('body', response.data)

    def test_only_students_attach_and_only_in_direct_chats(self):
        counselor_sent = self.send('plan.pdf', PDF, user=self.counselor)
        self.assertEqual(counselor_sent.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('attachment', counselor_sent.data)
        group = MessageChannel.objects.create(kind=MessageChannel.Kind.GROUP, name='Class', school=self.school_a)
        ChannelMembership.objects.create(channel=group, user=self.student_a_user)
        group_sent = self.send('plan.pdf', PDF, channel=group.id)
        self.assertEqual(group_sent.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('attachment', group_sent.data)
        self.assertFalse(ChannelMessage.objects.exists())

    def test_an_attachment_cannot_be_added_by_editing(self):
        self.client.force_authenticate(self.student_a_user)
        sent = self.client.post('/api/channel-messages/', {'channel': self.channel_id, 'body': 'Hi'}, format='json')
        edited = self.client.patch(f'/api/channel-messages/{sent.data["id"]}/', {
            'attachment': SimpleUploadedFile('late.pdf', PDF),
        }, format='multipart')
        self.assertEqual(edited.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ChannelMessage.objects.get(pk=sent.data['id']).attachment)

    def test_deleting_the_message_removes_its_file(self):
        sent = self.send('scan.png', image_bytes('PNG'))
        message = ChannelMessage.objects.get(pk=sent.data['id'])
        storage, name = message.attachment.storage, message.attachment.name
        self.client.force_authenticate(self.student_a_user)
        with self.captureOnCommitCallbacks(execute=True):
            deleted = self.client.delete(f'/api/channel-messages/{message.id}/')
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(storage.exists(name))
        self.assertEqual(self.download(message.id, self.counselor).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.counselor)
        listed = self.client.get(f'/api/channel-messages/?channel={self.channel_id}')
        self.assertIsNone(listed.data['results'][0]['attachment_file'])
