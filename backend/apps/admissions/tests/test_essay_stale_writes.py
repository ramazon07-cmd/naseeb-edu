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
        payload = {key: loaded[key] for key in ('title', 'prompt', 'content', 'status', 'counselor_comment')}
        payload.update(changes)
        return payload

    def student_loads_form(self):
        self.client.force_authenticate(self.student_a_user)
        return self.client.get(f'/api/essays/{self.essay.id}/').data

    def assert_newer_text_kept(self, newer):
        self.essay.refresh_from_db()
        self.assertEqual(self.essay.content, newer)
        self.assertEqual(self.tab().doc['content'][0]['content'][0]['marks'], [{'type': 'bold'}])

    def test_stale_text_write_gets_409_and_keeps_the_newer_text_and_formatting(self):
        loaded = self.student_loads_form()
        newer = self.student_saves_newer_text()
        response = self.client.patch(
            f'/api/essays/{self.essay.id}/', {'content': OLD_TEXT, 'original': {'content': loaded['content']}}, format='json',
        )
        self.assertEqual((response.status_code, response.data['code']), (status.HTTP_409_CONFLICT, 'essay_changed'))
        self.assert_newer_text_kept(newer)

    def test_text_write_without_a_precondition_is_refused_for_the_student_too(self):
        newer = self.student_saves_newer_text()
        response = self.client.patch(f'/api/essays/{self.essay.id}/', {'content': 'Old cached copy.'}, format='json')
        self.assertEqual(
            (response.status_code, response.data['code']), (status.HTTP_428_PRECONDITION_REQUIRED, 'precondition_required'),
        )
        self.assert_newer_text_kept(newer)

    def test_student_text_write_from_the_current_copy_saves(self):
        self.student_saves_newer_text()
        loaded = self.student_loads_form()
        response = self.client.patch(
            f'/api/essays/{self.essay.id}/', {'content': 'Fresh edit.', 'original': {'content': loaded['content']}}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.essay.refresh_from_db()
        self.assertEqual(self.essay.content, 'Fresh edit.')

    def test_unrelated_saves_since_loading_do_not_block_a_title_edit(self):
        loaded = self.student_loads_form()
        newer = self.student_saves_newer_text()
        response = self.client.patch(
            f'/api/essays/{self.essay.id}/', {'title': 'Daily bread', 'original': {'title': loaded['title']}}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assert_newer_text_kept(newer)
        self.assertEqual(self.essay.title, 'Daily bread')

    def test_a_field_changed_since_loading_is_a_conflict(self):
        loaded = self.student_loads_form()
        Essay.objects.filter(pk=self.essay.pk).update(title='Renamed elsewhere')
        response = self.client.patch(
            f'/api/essays/{self.essay.id}/', {'title': 'Mine', 'original': {'title': loaded['title']}}, format='json',
        )
        self.assertEqual((response.status_code, response.data['code']), (status.HTTP_409_CONFLICT, 'essay_changed'))
        self.essay.refresh_from_db()
        self.assertEqual(self.essay.title, 'Renamed elsewhere')

    def test_older_clients_without_originals_still_edit_the_title(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.patch(f'/api/essays/{self.essay.id}/', {'title': 'Old bundle title'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_counselor_review_on_a_stale_copy_saves_and_keeps_the_text(self):
        loaded = self.counselor_loads_form()
        newer = self.student_saves_newer_text()
        self.client.force_authenticate(self.counselor)
        for payload in (
            {'counselor_comment': 'Nice.', 'status': 'needs_revision'},
            # A full form whose student fields equal the current ones: those are no change.
            self.form_payload({**loaded, 'content': newer}, counselor_comment='Tighten the opening.'),
        ):
            response = self.client.patch(f'/api/essays/{self.essay.id}/', payload, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assert_newer_text_kept(newer)
        self.assertEqual(self.essay.counselor_comment, 'Tighten the opening.')

    def test_counselor_cannot_change_the_students_text(self):
        newer = self.student_saves_newer_text()
        loaded = self.counselor_loads_form()
        for changes in ({'content': 'Counselor rewrite.'}, {'title': 'Renamed'}, {'prompt': 'Other prompt'}):
            response = self.client.patch(
                f'/api/essays/{self.essay.id}/', {**changes, 'original': {key: loaded[key] for key in changes}}, format='json',
            )
            self.assertEqual((response.status_code, response.data['code']), (status.HTTP_403_FORBIDDEN, 'student_authored'))
        self.assert_newer_text_kept(newer)
        self.assertEqual(self.essay.title, 'Bread')

