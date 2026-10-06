"""P0: a counselor's essay form built from an old copy must not overwrite the student's newer text or formatting."""
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from ..essay_lab.tabs import tab_from_text
from ..models import Essay, EssayTab
from .base import RoleIsolationBase

OLD_TEXT = 'My first draft about bread.'


def bold_doc(text):
    return {'type': 'doc', 'content': [
        {'type': 'paragraph', 'content': [{'type': 'text', 'text': text, 'marks': [{'type': 'bold'}]}]},
    ]}


class StaleEssayWriteTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.essay = Essay.objects.create(
            student=self.student_a, title='Bread', prompt='Tell us about yourself.', content=OLD_TEXT,
            shared_with_counselor=True, shared_at=timezone.now(), counselor_access=Essay.CounselorAccess.EDIT,
        )
        tab_from_text(self.essay, OLD_TEXT).save()

    def tab(self):
        return EssayTab.objects.get(essay=self.essay)

    def counselor_loads_form(self):
        self.client.force_authenticate(self.counselor)
        loaded = self.client.get(f'/api/essays/{self.essay.id}/')
        self.assertEqual(loaded.status_code, status.HTTP_200_OK)
        return loaded.data

    def student_saves_newer_text(self, text='My newer draft, now in bold.'):
        self.client.force_authenticate(self.student_a_user)
        saved = self.client.put(
            f'/api/essay-lab/essays/{self.essay.id}/autosave/',
            {'doc': bold_doc(text), 'base_seq': self.tab().save_seq, 'client_save_id': 'student-1'},
            format='json',
        )
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        return text

    def form_payload(self, loaded, **changes):
        payload = {key: loaded[key] for key in ('title', 'prompt', 'content', 'status', 'counselor_comment', 'updated_at')}
        payload.update(changes)
        return payload

    def test_stale_counselor_form_gets_409_and_keeps_the_students_text_and_formatting(self):
        loaded = self.counselor_loads_form()
        newer = self.student_saves_newer_text()

        self.client.force_authenticate(self.counselor)
        response = self.client.patch(
            f'/api/essays/{self.essay.id}/', self.form_payload(loaded, counselor_comment='Tighten the opening.'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, response.data)
        self.essay.refresh_from_db()
        self.assertEqual(self.essay.content, newer)
        self.assertEqual(self.essay.counselor_comment, '')
        doc = self.tab().doc
        self.assertIsNotNone(doc)
        self.assertEqual(doc['content'][0]['content'][0]['marks'], [{'type': 'bold'}])

    def test_counselor_write_without_a_precondition_is_refused(self):
        loaded = self.counselor_loads_form()
        payload = self.form_payload(loaded, content='Counselor rewrite.')
        payload.pop('updated_at')
        response = self.client.patch(f'/api/essays/{self.essay.id}/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_428_PRECONDITION_REQUIRED, response.data)
        self.essay.refresh_from_db()
        self.assertEqual(self.essay.content, OLD_TEXT)

    def test_review_only_write_needs_no_precondition_and_keeps_the_text(self):
        self.counselor_loads_form()
        newer = self.student_saves_newer_text()
        self.client.force_authenticate(self.counselor)
        response = self.client.patch(
            f'/api/essays/{self.essay.id}/', {'counselor_comment': 'Nice.', 'status': 'needs_revision'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.essay.refresh_from_db()
        self.assertEqual((self.essay.content, self.essay.counselor_comment), (newer, 'Nice.'))

    def test_counselor_form_from_the_current_copy_saves(self):
        self.student_saves_newer_text()
        loaded = self.counselor_loads_form()
        response = self.client.patch(
            f'/api/essays/{self.essay.id}/', self.form_payload(loaded, counselor_comment='Good.'), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.essay.refresh_from_db()
        self.assertEqual(self.essay.counselor_comment, 'Good.')
        self.assertEqual(self.tab().doc['content'][0]['content'][0]['marks'], [{'type': 'bold'}])

    def test_student_stale_legacy_form_also_gets_409(self):
        self.client.force_authenticate(self.student_a_user)
        loaded = self.client.get(f'/api/essays/{self.essay.id}/').data
        newer = self.student_saves_newer_text()
        response = self.client.patch(
            f'/api/essays/{self.essay.id}/', {'content': OLD_TEXT, 'updated_at': loaded['updated_at']}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, response.data)
        self.essay.refresh_from_db()
        self.assertEqual(self.essay.content, newer)
