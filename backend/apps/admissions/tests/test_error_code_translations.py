"""Coded errors on student work: one uz/ru wording, in the app (by code) and on the server (by text, for older clients)."""
import re
from pathlib import Path

from django.core.cache import cache
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework import status

from apps.users import api_messages
from ..essay_lab.tabs import tab_from_text
from ..models import Achievement, Essay
from ..serializers.common import STUDENT_AUTHORED_MESSAGE
from ..views.catalog import UNIVERSITY_IN_USE_MESSAGE
from ..views.common import STUDENT_AUTHORED_DELETE_MESSAGE
from ..views.essays import ESSAY_CHANGED_MESSAGE, PRECONDITION_REQUIRED_MESSAGE
from ..views.records import LETTER_CHANGED_MESSAGE
from .base import RoleIsolationBase

ERROR_CODES_JS = Path(__file__).resolve().parents[4] / 'frontend' / 'src' / 'translations' / 'errorCodes.js'

MESSAGES_BY_CODE = {
    'essay_changed': ESSAY_CHANGED_MESSAGE,
    'precondition_required': PRECONDITION_REQUIRED_MESSAGE,
    'student_authored': STUDENT_AUTHORED_MESSAGE,
    'student_authored_delete': STUDENT_AUTHORED_DELETE_MESSAGE,
    'letter_changed': LETTER_CHANGED_MESSAGE,
    'university_in_use': UNIVERSITY_IN_USE_MESSAGE,
}


def frontend_translations():
    """{code: (uz, ru)} from ERROR_CODE_TRANSLATIONS in errorCodes.js."""
    source = ERROR_CODES_JS.read_text(encoding='utf-8')
    table = source.split('export const ERROR_CODE_TRANSLATIONS = {', 1)[1].split('\n};', 1)[0]
    entries = re.findall(r"^\s{2}(\w+): \[\s*'((?:[^'\\]|\\.)*)',\s*'((?:[^'\\]|\\.)*)',\s*\],", table, re.MULTILINE)
    return {code: (uz, ru) for code, uz, ru in entries}


class ErrorCodeWordingTests(SimpleTestCase):
    def test_the_server_table_uses_the_apps_wording_for_every_code(self):
        app = frontend_translations()
        self.assertEqual(set(app), set(MESSAGES_BY_CODE))
        for code, english in MESSAGES_BY_CODE.items():
            with self.subTest(code=code):
                self.assertIn(english, api_messages.EXACT)
                server = api_messages.EXACT[english]
                self.assertEqual((server['uz'], server['ru']), app[code])


class ErrorCodeLocalizationTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.essay = Essay.objects.create(
            student=self.student_a, title='Bread', prompt='', content='First draft.',
            shared_with_counselor=True, shared_at=timezone.now(),
        )
        tab_from_text(self.essay, 'First draft.').save()
        self.achievement = Achievement.objects.create(
            student=self.student_a, title='Olympiad', category='olympiad', description='Gold',
        )

    def test_older_clients_get_the_detail_in_their_language(self):
        Essay.objects.filter(pk=self.essay.pk).update(content='Newer text from the Essay Lab.')
        for language in ('uz', 'ru'):
            with self.subTest(language=language):
                self.client.force_authenticate(self.student_a_user)
                stale = self.client.patch(
                    f'/api/essays/{self.essay.pk}/', {'content': 'Mine', 'original': {'content': 'First draft.'}},
                    format='json', HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)
                self.assertEqual(stale.data['code'], 'essay_changed')
                self.assertEqual(stale.data['detail'], api_messages.EXACT[ESSAY_CHANGED_MESSAGE][language])

                self.client.force_authenticate(self.counselor)
                staff = self.client.patch(
                    f'/api/achievements/{self.achievement.pk}/', {'description': 'x'},
                    format='json', HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(staff.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(staff.data['code'], 'student_authored')
                self.assertEqual(staff.data['detail'], api_messages.EXACT[STUDENT_AUTHORED_MESSAGE][language])

    def test_english_keeps_the_server_sentence(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.delete(f'/api/achievements/{self.achievement.pk}/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual((response.data['code'], response.data['detail']), ('student_authored_delete', STUDENT_AUTHORED_DELETE_MESSAGE))
