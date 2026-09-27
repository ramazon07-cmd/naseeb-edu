import json
import random
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .essay_lab import coach
from .essay_lab.doc import (
    DocError, apply_delta, apply_ops, canonical_json, derive, doc_from_text, doc_hash, doc_stats, validate_doc,
)
from .essay_lab.tabs import tab_from_text
from .essay_lab.views import CHECKPOINT_CAP, DEPTH_CHECK_KEEP
from .models import (
    Application,
    Essay,
    EssayCheckpoint,
    EssayDepthCheck,
    EssayFolder,
    EssayRevision,
    EssayTab,
    School,
    StudentProfile,
    University,
)


User = get_user_model()
FIXTURES = Path(__file__).parent / 'essay_lab' / 'fixtures' / 'doc_text_cases.json'
DELTA_FIXTURES = Path(__file__).parent / 'essay_lab' / 'fixtures' / 'doc_delta_cases.json'
BASE = '/api/essay-lab'

ESSAY_TEXT = (
    'My grandmother never wasted bread. Every evening she folded the leftover crust into a cloth.\n\n'
    'I learned that patience matters.\n\n'
    'When I was 14, I rebuilt the school radio with two friends and a borrowed soldering iron.'
)


def paragraph(text):
    return {'type': 'paragraph', 'content': [{'type': 'text', 'text': text}]} if text else {'type': 'paragraph'}


def make_doc(*texts):
    return {'type': 'doc', 'content': [paragraph(text) for text in texts]}


def gateway_response(content):
    """A fake urlopen() context manager returning a chat-completions payload."""
    body = json.dumps({'choices': [{'message': {'content': content}}]}).encode('utf-8')
    response = mock.MagicMock()
    response.read.return_value = body
    response.__enter__.return_value = response
    return response


class EssayLabFixtureMixin:
    def create_people(self):
        self.school = School.objects.create(name='Essay Lab School', code='essay-lab-school')
        self.other_school = School.objects.create(name='Other Essay School', code='other-essay-school')
        self.counselor = User.objects.create_user(
            username='lab-counselor', email='lab-counselor@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school,
        )
        self.organization = User.objects.create_user(
            username='lab-org', email='lab-org@example.com', password='StrongPass123!',
            role=User.Role.ORGANIZATION, school=self.school,
        )
        self.teacher = User.objects.create_user(
            username='lab-teacher', email='lab-teacher@example.com', password='StrongPass123!',
            role=User.Role.TEACHER, school=self.school,
        )
        self.student_user = User.objects.create_user(
            username='lab-student', email='lab-student@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school,
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user, school=self.school, school_name=self.school.name,
            assigned_counselor=self.counselor,
        )
        self.other_user = User.objects.create_user(
            username='lab-other', email='lab-other@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.other_school,
        )
        self.other_student = StudentProfile.objects.create(
            user=self.other_user, school=self.other_school, school_name=self.other_school.name,
        )

    def make_essay(self, student=None, **fields):
        content = fields.pop('content', ESSAY_TEXT)
        defaults = {'title': 'Bread', 'prompt': 'Tell us about yourself.', 'content': content}
        defaults.update(fields)
        essay = Essay.objects.create(student=student or self.student, **defaults)
        _, word_count, preview = derive(doc_from_text(content))
        Essay.objects.filter(pk=essay.pk).update(word_count=word_count, preview=preview)
        essay.refresh_from_db()
        # Like a migrated essay: one tab holding the plain text, doc rebuilt on read.
        tab_from_text(essay, content).save()
        return essay

    @staticmethod
    def tab_of(essay):
        return EssayTab.objects.filter(essay_id=essay.pk, parent__isnull=True).order_by('position', 'id').first()


class EssayLabTestCase(EssayLabFixtureMixin, APITestCase):
    def setUp(self):
        cache.clear()
        self.create_people()
        self.client.force_authenticate(self.student_user)

    def autosave(self, essay, doc, base_seq=None, save_id='save-1', **extra):
        body = {'doc': doc, 'base_seq': self.tab_of(essay).save_seq if base_seq is None else base_seq,
                'client_save_id': save_id}
        body.update(extra)
        return self.client.put(f'{BASE}/essays/{essay.pk}/autosave/', body, format='json')


class DocDerivationTests(EssayLabTestCase):
    def test_plain_text_writes_outside_the_api_fill_library_columns(self):
        essay = Essay.objects.create(student=self.student, title='Seeded', prompt='', content='One two three.')
        self.assertEqual((essay.word_count, essay.preview), (3, 'One two three.'))
        essay.content = 'Four words right here.'
        essay.save(update_fields=['content'])
        essay.refresh_from_db()
        self.assertEqual((essay.word_count, essay.preview), (4, 'Four words right here.'))

    def test_shared_fixtures_match(self):
        cases = json.loads(FIXTURES.read_text())['cases']
        self.assertGreaterEqual(len(cases), 8)
        for case in cases:
            with self.subTest(case['name']):
                stats = doc_stats(validate_doc(case['doc']))
                self.assertEqual(stats.content, case['content'])
                self.assertEqual(stats.word_count, case['word_count'])
                self.assertEqual(stats.preview, case['preview'])
                self.assertEqual(stats.char_count, case['char_count'])
                self.assertEqual(stats.char_count_no_spaces, case['char_count_no_spaces'])

    def test_shared_invalid_cases_are_rejected(self):
        cases = json.loads(DELTA_FIXTURES.read_text())['invalid_cases']
        self.assertGreaterEqual(len(cases), 20)
        for case in cases:
            with self.subTest(case['name']), self.assertRaises(DocError) as caught:
                validate_doc(case['doc'])
            self.assertEqual(caught.exception.code, 'invalid_doc')

    def test_formatting_round_trips_through_autosave(self):
        essay = self.make_essay()
        doc = {'type': 'doc', 'content': [
            {'type': 'title', 'attrs': {'textAlign': 'center'}, 'content': [{'type': 'text', 'text': 'Title'}]},
            {'type': 'heading', 'attrs': {'level': 3}, 'content': [{'type': 'text', 'text': 'Small heading'}]},
            {'type': 'pageBreak'},
            {'type': 'paragraph', 'attrs': {'lineHeight': '1.15', 'indent': 1}, 'content': [
                {'type': 'text', 'text': 'Styled', 'marks': [
                    {'type': 'textStyle', 'attrs': {'fontFamily': 'Merriweather', 'fontSize': 14, 'color': '#b91c1c'}},
                    {'type': 'highlight', 'attrs': {'color': '#fef08a'}},
                    {'type': 'link', 'attrs': {'href': 'https://example.com'}}]},
            ]},
        ]}
        response = self.autosave(essay, doc)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.tab_of(essay).doc, doc)
        self.assertEqual(self.tab_of(essay).content, 'Title\n\nSmall heading\n\nStyled')

    def test_rejects_unknown_nodes_marks_and_bad_attrs(self):
        bad_docs = [
            {'type': 'doc', 'content': [{'type': 'image', 'attrs': {'src': 'x'}}]},
            {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [
                {'type': 'text', 'text': 'x', 'marks': [{'type': 'link', 'attrs': {'href': 'javascript:1'}}]}]}]},
            {'type': 'doc', 'content': [{'type': 'heading', 'attrs': {'level': 4}, 'content': []}]},
            {'type': 'doc', 'content': [{'type': 'text', 'text': 'loose text'}]},
            {'type': 'paragraph'},
            ['not', 'a', 'doc'],
        ]
        for doc in bad_docs:
            with self.subTest(doc=doc), self.assertRaises(DocError) as caught:
                validate_doc(doc)
            self.assertEqual(caught.exception.code, 'invalid_doc')

    def test_depth_and_size_limits(self):
        node = paragraph('deep')
        for _ in range(12):
            node = {'type': 'blockquote', 'content': [node]}
        with self.assertRaises(DocError) as caught:
            validate_doc({'type': 'doc', 'content': [node]})
        self.assertEqual(caught.exception.code, 'invalid_doc')
        with self.assertRaises(DocError) as caught:
            validate_doc(make_doc('x' * (260 * 1024)))
        self.assertEqual(caught.exception.code, 'doc_too_large')
        self.assertEqual(caught.exception.status, 413)

    def test_sanitizes_attrs_and_control_characters(self):
        cleaned = validate_doc({'type': 'doc', 'content': [
            {'type': 'paragraph', 'attrs': {'onclick': 'x'}, 'content': [
                {'type': 'text', 'text': 'a\x00b<script>', 'marks': [{'type': 'bold', 'attrs': {'x': 1}}]}]},
        ]})
        self.assertEqual(cleaned, {'type': 'doc', 'content': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'ab<script>', 'marks': [{'type': 'bold'}]}]},
        ]})

    def test_doc_from_text_round_trip(self):
        doc = doc_from_text('First line\nsecond line\n\n\nNext paragraph')
        self.assertEqual(len(doc['content']), 2)
        self.assertEqual(derive(doc)[0], 'First line\nsecond line\n\nNext paragraph')
        self.assertEqual(doc_from_text(''), {'type': 'doc', 'content': [{'type': 'paragraph'}]})


class EssayLabAccessTests(EssayLabTestCase):
    def test_non_students_get_403(self):
        essay = self.make_essay()
        for user in (self.counselor, self.organization, self.teacher):
            self.client.force_authenticate(user)
            for method, url in (
                ('get', f'{BASE}/essays/'),
                ('get', f'{BASE}/essays/{essay.pk}/'),
                ('get', f'{BASE}/folders/'),
                ('post', f'{BASE}/essays/'),
            ):
                with self.subTest(role=user.role, url=url):
                    response = getattr(self.client, method)(url, {}, format='json')
                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                    self.assertEqual(response.data['code'], 'students_only')

    def test_anonymous_is_rejected(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'{BASE}/essays/').status_code, status.HTTP_401_UNAUTHORIZED)

    def test_other_students_essays_are_404(self):
        foreign = self.make_essay(student=self.other_student, title='Not yours')
        folder = EssayFolder.objects.create(student=self.other_student, name='Theirs')
        urls = [
            ('get', f'{BASE}/essays/{foreign.pk}/', None),
            ('patch', f'{BASE}/essays/{foreign.pk}/', {'title': 'Mine now'}),
            ('put', f'{BASE}/essays/{foreign.pk}/autosave/', {'doc': make_doc('x'), 'base_seq': 0, 'client_save_id': 'a'}),
            ('post', f'{BASE}/essays/{foreign.pk}/trash/', None),
            ('post', f'{BASE}/essays/{foreign.pk}/duplicate/', {}),
            ('get', f'{BASE}/essays/{foreign.pk}/checkpoints/', None),
            ('post', f'{BASE}/essays/{foreign.pk}/depth-check/', {'base_seq': 0}),
            ('get', f'{BASE}/essays/{foreign.pk}/depth-check/latest/', None),
            ('delete', f'{BASE}/essays/{foreign.pk}/', None),
            ('patch', f'{BASE}/folders/{folder.pk}/', {'name': 'x'}),
            ('delete', f'{BASE}/folders/{folder.pk}/', None),
        ]
        for method, url, body in urls:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(response.data['code'], 'not_found')
        self.assertEqual(self.client.get(f'{BASE}/essays/').data, [])
        foreign.refresh_from_db()
        self.assertEqual(foreign.title, 'Not yours')

    def test_cannot_file_essay_into_another_students_folder(self):
        folder = EssayFolder.objects.create(student=self.other_student, name='Theirs')
        response = self.client.post(f'{BASE}/essays/', {'title': 'x', 'folder': folder.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'invalid')
        self.assertIn('folder', response.data['errors'])


class EssayLabCrudTests(EssayLabTestCase):
    def test_create_every_type(self):
        folder = EssayFolder.objects.create(student=self.student, name='Supplements')
        bodies = [
            {'title': 'Common App', 'essay_type': 'personal_statement', 'prompt': 'Share a story.', 'word_limit': 650},
            {'title': 'Why us', 'essay_type': 'supplement', 'prompt': 'Why this college?',
             'university_name': 'Example University', 'word_limit': 250, 'folder': folder.pk},
            {'title': 'Merit award', 'essay_type': 'scholarship', 'prompt': 'Describe your goals.'},
            {'title': '', 'essay_type': 'free_writing'},
        ]
        for body in bodies:
            with self.subTest(essay_type=body['essay_type']):
                response = self.client.post(f'{BASE}/essays/', body, format='json')
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                data = response.data
                self.assertEqual(data['essay_type'], body['essay_type'])
                self.assertEqual(data['tab']['save_seq'], 0)
                self.assertEqual(data['tab']['doc'], {'type': 'doc', 'content': [{'type': 'paragraph'}]})
                self.assertEqual(data['tab']['title'], 'Tab 1')
                self.assertEqual([tab['id'] for tab in data['tabs']], [data['tab']['id']])
                self.assertEqual(set(data), {
                    'id', 'title', 'essay_type', 'prompt', 'university_name', 'word_limit', 'folder', 'word_count',
                    'preview', 'last_edited_at', 'updated_at', 'trashed_at', 'status', 'page_size', 'tabs', 'tab',
                    'shared_with_counselor', 'shared_at',
                })
                self.assertFalse(data['shared_with_counselor'])
                essay = Essay.objects.get(pk=data['id'])
                self.assertEqual(essay.student, self.student)
                self.assertEqual(EssayRevision.objects.filter(essay=essay).count(), 1)
        self.assertEqual(Essay.objects.get(essay_type='free_writing').title, 'Untitled essay')
        self.assertEqual(Essay.objects.get(essay_type='supplement').folder, folder)

    def test_create_rejects_bad_type_and_limit(self):
        response = self.client.post(f'{BASE}/essays/', {'title': 'x', 'essay_type': 'poem'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(f'{BASE}/essays/', {'title': 'x', 'word_limit': 0}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_filters_and_shape(self):
        folder = EssayFolder.objects.create(student=self.student, name='F')
        in_folder = self.make_essay(title='Folder essay', folder=folder, essay_type='supplement',
                                    university_name='Oxford')
        loose = self.make_essay(title='Loose essay')
        trashed = self.make_essay(title='Old essay', trashed_at=timezone.now())

        data = self.client.get(f'{BASE}/essays/').data
        self.assertEqual({item['id'] for item in data}, {in_folder.pk, loose.pk})
        self.assertNotIn('doc', data[0])
        self.assertNotIn('content', data[0])
        self.assertEqual(data[0]['word_count'], in_folder.word_count or loose.word_count)

        def ids(query):
            return [item['id'] for item in self.client.get(f'{BASE}/essays/{query}').data]

        self.assertEqual(ids(f'?folder={folder.pk}'), [in_folder.pk])
        self.assertEqual(ids('?folder=none'), [loose.pk])
        self.assertEqual(ids('?type=supplement'), [in_folder.pk])
        self.assertEqual(ids('?q=oxford'), [in_folder.pk])
        self.assertEqual(ids('?trashed=1'), [trashed.pk])
        for bad in ('?folder=abc', '?type=poem', '?trashed=2'):
            response = self.client.get(f'{BASE}/essays/{bad}')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.data['code'], 'invalid_filter')

    def test_detail_rebuilds_doc_from_legacy_content(self):
        essay = self.make_essay(content='Hello there.\n\nSecond part.')
        data = self.client.get(f'{BASE}/essays/{essay.pk}/').data
        self.assertEqual(len(data['tab']['doc']['content']), 2)
        self.assertIsNone(self.tab_of(essay).doc)

    def test_patch_metadata_only(self):
        essay = self.make_essay()
        response = self.client.patch(f'{BASE}/essays/{essay.pk}/', {
            'title': 'Renamed', 'word_limit': None, 'essay_type': 'scholarship',
            'content': 'ignored', 'save_seq': 99, 'status': 'approved',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        essay.refresh_from_db()
        self.assertEqual(essay.title, 'Renamed')
        self.assertEqual(essay.essay_type, 'scholarship')
        self.assertEqual(essay.content, ESSAY_TEXT)
        self.assertEqual(self.tab_of(essay).save_seq, 0)
        self.assertEqual(essay.status, Essay.Status.DRAFT)

    def test_trash_restore_delete(self):
        essay = self.make_essay()
        response = self.client.delete(f'{BASE}/essays/{essay.pk}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'not_trashed')

        response = self.client.post(f'{BASE}/essays/{essay.pk}/trash/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['trashed_at'])
        self.assertNotIn('doc', response.data)
        # Trashed essays are read-only and hidden from the legacy API.
        self.assertEqual(self.autosave(essay, make_doc('x')).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(f'{BASE}/essays/{essay.pk}/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f'/api/essays/{essay.pk}/').status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.post(f'{BASE}/essays/{essay.pk}/restore/')
        self.assertIsNone(response.data['trashed_at'])
        self.client.post(f'{BASE}/essays/{essay.pk}/trash/')
        self.assertEqual(self.client.delete(f'{BASE}/essays/{essay.pk}/').status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Essay.objects.filter(pk=essay.pk).exists())

    def test_duplicate(self):
        folder = EssayFolder.objects.create(student=self.student, name='Copies')
        essay = self.make_essay(essay_type='supplement', university_name='MIT', word_limit=250)
        self.autosave(essay, make_doc('Original text here.'))
        response = self.client.post(f'{BASE}/essays/{essay.pk}/duplicate/', {
            'university_name': 'Stanford', 'folder': folder.pk,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        copy = Essay.objects.get(pk=response.data['id'])
        self.assertEqual(copy.title, 'Bread (copy)')
        self.assertEqual(copy.university_name, 'Stanford')
        self.assertEqual(copy.folder, folder)
        self.assertEqual(copy.content, 'Original text here.')
        self.assertEqual(copy.word_count, 3)
        self.assertEqual(self.tab_of(copy).save_seq, 0)
        self.assertEqual(copy.word_limit, 250)
        self.assertEqual(response.data['tab']['doc'], make_doc('Original text here.'))
        self.assertEqual(self.tab_of(copy).content, 'Original text here.')


class EssayLabAutosaveTests(EssayLabTestCase):
    def test_autosave_saves_and_derives(self):
        essay = self.make_essay()
        doc = {'type': 'doc', 'content': [
            {'type': 'heading', 'attrs': {'level': 1}, 'content': [{'type': 'text', 'text': 'Bread'}]},
            {'type': 'bulletList', 'content': [{'type': 'listItem', 'content': [paragraph('one small thing')]}]},
        ]}
        response = self.autosave(essay, doc, cursor=12)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['save_seq'], 1)
        self.assertEqual(response.data['word_count'], 4)
        self.assertIn('saved_at', response.data)
        essay.refresh_from_db()
        self.assertEqual(essay.content, 'Bread\n\n• one small thing')
        self.assertEqual(self.tab_of(essay).doc, doc)
        self.assertEqual(self.tab_of(essay).last_cursor, 12)
        self.assertEqual(self.tab_of(essay).last_client_save_id, 'save-1')
        self.assertIsNotNone(essay.last_edited_at)
        # Counselor-visible versioning is untouched by autosave.
        self.assertEqual(essay.version, 1)
        self.assertFalse(EssayRevision.objects.filter(essay=essay).exists())

    def test_idempotent_retry(self):
        essay = self.make_essay()
        first = self.autosave(essay, make_doc('One'), base_seq=0, save_id='abc')
        retry = self.autosave(essay, make_doc('One'), base_seq=0, save_id='abc')
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.assertEqual(retry.data['save_seq'], first.data['save_seq'])
        essay.refresh_from_db()
        self.assertEqual(self.tab_of(essay).save_seq, 1)

    def test_conflict(self):
        essay = self.make_essay()
        self.autosave(essay, make_doc('Server copy'), base_seq=0, save_id='one')
        response = self.autosave(essay, make_doc('Stale copy'), base_seq=0, save_id='two')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'conflict')
        self.assertEqual(response.data['save_seq'], 1)
        self.assertEqual(response.data['doc'], make_doc('Server copy'))
        self.assertIn('saved_at', response.data)

    def test_invalid_and_too_large_doc(self):
        essay = self.make_essay()
        response = self.autosave(essay, {'type': 'doc', 'content': [{'type': 'iframe'}]})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'invalid_doc')
        response = self.autosave(essay, make_doc('y' * (300 * 1024)))
        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.assertEqual(response.data['code'], 'doc_too_large')
        response = self.client.put(f'{BASE}/essays/{essay.pk}/autosave/', {'doc': make_doc('x')}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        essay.refresh_from_db()
        self.assertEqual(self.tab_of(essay).save_seq, 0)

    @override_settings(ESSAY_AUTOSAVE_LIMIT=2)
    def test_autosave_throttle(self):
        essay = self.make_essay()
        self.autosave(essay, make_doc('a'), base_seq=0, save_id='1')
        self.autosave(essay, make_doc('b'), base_seq=1, save_id='2')
        response = self.autosave(essay, make_doc('c'), base_seq=2, save_id='3')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data['code'], 'slow_down')
        self.assertIn('Retry-After', response)

    def test_checkpoint_cadence(self):
        essay = self.make_essay()
        self.autosave(essay, make_doc('First words'), base_seq=0, save_id='1')
        self.assertEqual(EssayCheckpoint.objects.filter(essay=essay, reason='auto').count(), 1)
        # Within 10 minutes: no new checkpoint.
        self.autosave(essay, make_doc('First words and more'), base_seq=1, save_id='2')
        self.assertEqual(EssayCheckpoint.objects.filter(essay=essay).count(), 1)
        # Older than 10 minutes and the text changed: new checkpoint.
        EssayCheckpoint.objects.filter(essay=essay).update(created_at=timezone.now() - timedelta(minutes=11))
        self.autosave(essay, make_doc('First words and even more'), base_seq=2, save_id='3')
        self.assertEqual(EssayCheckpoint.objects.filter(essay=essay).count(), 2)
        latest = EssayCheckpoint.objects.filter(essay=essay).first()
        self.assertEqual(latest.content, 'First words and even more')
        # Older than 10 minutes but the text matches the newest checkpoint: nothing new.
        EssayCheckpoint.objects.filter(essay=essay).update(created_at=timezone.now() - timedelta(minutes=11))
        self.autosave(essay, make_doc('First words and even more'), base_seq=3, save_id='4')
        self.assertEqual(EssayCheckpoint.objects.filter(essay=essay).count(), 2)

    def test_checkpoint_cap_drops_oldest_auto_first(self):
        essay = self.make_essay()
        doc = make_doc('x')
        EssayCheckpoint.objects.bulk_create(
            [EssayCheckpoint(essay=essay, tab=self.tab_of(essay), doc=doc, content='x', reason='manual', label='keep')]
            + [EssayCheckpoint(essay=essay, tab=self.tab_of(essay), doc=doc, content='x', reason='auto')
               for _ in range(CHECKPOINT_CAP - 1)]
        )
        oldest_manual = EssayCheckpoint.objects.get(essay=essay, reason='manual')
        oldest_auto = EssayCheckpoint.objects.filter(essay=essay, reason='auto').order_by('created_at', 'id').first()
        response = self.client.post(f'{BASE}/essays/{essay.pk}/checkpoints/', {'label': 'Before big edit'},
                                    format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['reason'], 'manual')
        self.assertEqual(response.data['label'], 'Before big edit')
        self.assertEqual(EssayCheckpoint.objects.filter(essay=essay).count(), CHECKPOINT_CAP)
        self.assertTrue(EssayCheckpoint.objects.filter(pk=oldest_manual.pk).exists())
        self.assertFalse(EssayCheckpoint.objects.filter(pk=oldest_auto.pk).exists())

    def test_checkpoint_list_detail_and_restore(self):
        essay = self.make_essay()
        self.autosave(essay, make_doc('Version one'), base_seq=0, save_id='1')
        first = EssayCheckpoint.objects.get(essay=essay)
        self.autosave(essay, make_doc('Version two'), base_seq=1, save_id='2')

        listing = self.client.get(f'{BASE}/essays/{essay.pk}/checkpoints/').data
        self.assertEqual([item['id'] for item in listing], [first.pk])
        self.assertEqual(set(listing[0]), {'id', 'tab', 'reason', 'label', 'word_count', 'created_at'})
        detail = self.client.get(f'{BASE}/essays/{essay.pk}/checkpoints/{first.pk}/').data
        self.assertEqual(detail['doc'], make_doc('Version one'))

        stale = self.client.post(f'{BASE}/essays/{essay.pk}/checkpoints/{first.pk}/restore/', {'base_seq': 1},
                                 format='json')
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)
        response = self.client.post(f'{BASE}/essays/{essay.pk}/checkpoints/{first.pk}/restore/', {'base_seq': 2},
                                    format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['save_seq'], 3)
        self.assertEqual(response.data['doc'], make_doc('Version one'))
        essay.refresh_from_db()
        self.assertEqual(essay.content, 'Version one')
        backup = EssayCheckpoint.objects.get(essay=essay, reason='restore')
        self.assertEqual(backup.content, 'Version two')
        missing = self.client.get(f'{BASE}/essays/{essay.pk}/checkpoints/999999/')
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)


def patch_op(at, before, after):
    """A block patch like the frontend's: shared prefix/suffix of the canonical JSON."""
    old, new = canonical_json(before), canonical_json(after)
    limit = min(len(old), len(new))
    prefix = 0
    while prefix < limit and old[prefix] == new[prefix]:
        prefix += 1
    suffix = 0
    while suffix < limit - prefix and old[-1 - suffix] == new[-1 - suffix]:
        suffix += 1
    return {'at': at, 'patch': [prefix, suffix, new[prefix:len(new) - suffix]]}


def reference_apply(blocks, ops):
    """Independent reference: apply ops right to left so earlier indices stay valid."""
    result = list(blocks)
    for op in reversed(ops):
        at = op['at']
        if 'patch' in op:
            result[at:at + 1] = [op['_after']]
        else:
            result[at:at + op['delete']] = op['insert']
    return result


def random_block(rng):
    words = ' '.join(rng.choice(['bread', 'Ўзбек', 'naseeb', '😀', 'a"b', 'c\\d', 'radio'])
                     for _ in range(rng.randint(1, 8)))
    kind = rng.random()
    if kind < 0.7:
        return paragraph(words)
    if kind < 0.85:
        return {'type': 'heading', 'attrs': {'level': rng.choice([1, 2])},
                'content': [{'type': 'text', 'text': words}]}
    return {'type': 'bulletList', 'content': [{'type': 'listItem', 'content': [paragraph(words)]}]}


def random_ops(rng, blocks):
    """Random ascending, non-overlapping ops over `blocks` (splices and patches)."""
    ops = []
    at = 0
    while len(ops) < 6:
        at += rng.randint(0, 3)
        if at > len(blocks):
            break
        if at < len(blocks) and rng.random() < 0.5:
            if blocks[at]['type'] == 'bulletList':
                after = random_block(rng)
            else:
                after = dict(blocks[at], content=[{'type': 'text', 'text': f'edited {rng.randint(0, 999)} 😀'}])
            op = patch_op(at, blocks[at], after)
            op['_after'] = after
            ops.append(op)
            at += 1
        else:
            delete = rng.randint(0, min(2, len(blocks) - at))
            ops.append({'at': at, 'delete': delete, 'insert': [random_block(rng) for _ in range(rng.randint(0, 2))]})
            at += max(delete, 1)
    return ops


def wire(ops):
    return [{key: value for key, value in op.items() if key != '_after'} for op in ops]


class EssayLabDeltaTests(EssayLabTestCase):
    def delta(self, essay, ops, result_doc, base_seq=None, save_id='delta-1', **extra):
        body = {'ops': ops, 'doc_hash': doc_hash(result_doc), 'client_save_id': save_id,
                'base_seq': self.tab_of(essay).save_seq if base_seq is None else base_seq}
        body.update(extra)
        return self.client.put(f'{BASE}/essays/{essay.pk}/autosave/', body, format='json')

    def saved_essay(self, *texts):
        essay = self.make_essay()
        self.autosave(essay, make_doc(*texts), base_seq=0, save_id='full-1')
        essay.refresh_from_db()
        return essay

    def test_shared_hash_fixtures(self):
        cases = json.loads(DELTA_FIXTURES.read_text())['hash_cases']
        self.assertGreaterEqual(len(cases), 5)
        for case in cases:
            with self.subTest(case['name']):
                self.assertEqual(validate_doc(case['input']), case['normalized'])
                self.assertEqual(canonical_json(case['normalized']), case['canonical'])
                self.assertEqual(doc_hash(case['normalized']), case['hash'])

    def test_shared_delta_fixtures(self):
        for case in json.loads(DELTA_FIXTURES.read_text())['delta_cases']:
            with self.subTest(case['name']):
                doc, saved_hash = apply_delta(case['base'], case['ops'], case['doc_hash'])
                self.assertEqual(doc, case['result'])
                self.assertEqual(saved_hash, case['doc_hash'])

    def test_randomized_edit_sequences_apply_exactly(self):
        rng = random.Random(20260925)
        for sequence in range(40):
            blocks = [random_block(rng) for _ in range(rng.randint(1, 12))]
            for _step in range(15):
                ops = random_ops(rng, blocks)
                expected = reference_apply(blocks, ops)
                sent = json.loads(json.dumps(wire(ops)))  # through JSON, as on the wire
                self.assertEqual(apply_ops(blocks, sent), expected, (sequence, sent))
                blocks = expected or [paragraph('x')]

    def test_delta_save_applies_and_derives(self):
        essay = self.saved_essay('One.', 'Two.', 'Three.')
        result = make_doc('One.', 'Two and a half.', 'Three.')
        response = self.delta(essay, [patch_op(1, paragraph('Two.'), paragraph('Two and a half.'))], result, cursor=9)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['save_seq'], 2)
        self.assertEqual(response.data['word_count'], 6)
        self.assertEqual(response.data['doc_hash'], doc_hash(result))
        essay.refresh_from_db()
        self.assertEqual(self.tab_of(essay).doc, result)
        self.assertEqual(essay.content, 'One.\n\nTwo and a half.\n\nThree.')
        self.assertEqual(essay.preview, 'One. Two and a half. Three.')
        self.assertEqual(self.tab_of(essay).last_client_save_id, 'delta-1')
        self.assertEqual(self.tab_of(essay).last_cursor, 9)

    def test_full_save_returns_the_stored_hash(self):
        essay = self.make_essay()
        messy = {'type': 'doc', 'content': [{'type': 'paragraph', 'attrs': {'textAlign': None},
                                             'content': [{'type': 'text', 'text': 'Hi'}]}]}
        response = self.autosave(essay, messy, base_seq=0)
        self.assertEqual(response.data['doc_hash'], doc_hash(make_doc('Hi')))

    def test_delta_on_a_legacy_essay_uses_the_rebuilt_doc(self):
        essay = self.make_essay(content='First.\n\nSecond.')
        self.assertIsNone(self.tab_of(essay).doc)
        result = make_doc('First.', 'Second.', 'Third.')
        response = self.delta(essay, [{'at': 2, 'delete': 0, 'insert': [paragraph('Third.')]}], result)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        essay.refresh_from_db()
        self.assertEqual(self.tab_of(essay).doc, result)

    def test_idempotent_retry_of_a_delta(self):
        essay = self.saved_essay('One.')
        ops = [{'at': 1, 'delete': 0, 'insert': [paragraph('Two.')]}]
        first = self.delta(essay, ops, make_doc('One.', 'Two.'), base_seq=1, save_id='d')
        retry = self.delta(essay, ops, make_doc('One.', 'Two.'), base_seq=1, save_id='d')
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.assertEqual(retry.data['save_seq'], first.data['save_seq'])
        essay.refresh_from_db()
        self.assertEqual(self.tab_of(essay).save_seq, 2)
        self.assertEqual(self.tab_of(essay).doc, make_doc('One.', 'Two.'))

    def test_stale_seq_is_a_conflict_not_a_resync(self):
        essay = self.saved_essay('One.')
        # Another tab saves first; this tab's delta was built on seq 1.
        self.autosave(essay, make_doc('Other tab.'), base_seq=1, save_id='tab-b')
        response = self.delta(essay, [{'at': 1, 'delete': 0, 'insert': [paragraph('Two.')]}],
                              make_doc('One.', 'Two.'), base_seq=1)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'conflict')
        self.assertEqual(response.data['save_seq'], 2)
        self.assertEqual(response.data['doc'], make_doc('Other tab.'))

    def test_hash_mismatch_asks_for_a_full_save(self):
        essay = self.saved_essay('One.', 'Two.')
        # The client believes block 0 reads "Uno." and patches it.
        client_result = make_doc('Uno!', 'Two.')
        response = self.delta(essay, [patch_op(0, paragraph('Uno.'), paragraph('Uno!'))], client_result)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'resync')
        self.assertEqual(response.data['save_seq'], 1)
        self.assertEqual(response.data['doc'], make_doc('One.', 'Two.'))
        essay.refresh_from_db()
        self.assertEqual((self.tab_of(essay).save_seq, self.tab_of(essay).doc, self.tab_of(essay).last_client_save_id),
                         (1, make_doc('One.', 'Two.'), 'full-1'))
        # The client then resends the same text in full with the same id; it lands.
        retry = self.autosave(essay, client_result, base_seq=1, save_id='delta-1')
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.assertEqual(retry.data['save_seq'], 2)

    def test_ops_that_do_not_fit_ask_for_a_full_save(self):
        essay = self.saved_essay('One.', 'Two.')
        result = make_doc('One.', 'Two.')
        for ops in (
            [{'at': 5, 'delete': 0, 'insert': []}],
            [{'at': 1, 'delete': 3, 'insert': []}],
            [{'at': 1, 'delete': 0, 'insert': []}, {'at': 0, 'delete': 0, 'insert': []}],
            [{'at': 2, 'patch': [0, 0, '{}']}],
            [{'at': 0, 'patch': [500, 500, '']}],
            [{'at': 0, 'patch': [3, 3, '{{{']}],
        ):
            with self.subTest(ops=ops):
                response = self.delta(essay, ops, result)
                self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, response.data)
                self.assertEqual(response.data['code'], 'resync')

    def test_malformed_bodies_are_400(self):
        essay = self.saved_essay('One.')
        url = f'{BASE}/essays/{essay.pk}/autosave/'
        good_hash = doc_hash(make_doc('One.'))
        bodies = [
            {'ops': [], 'doc': make_doc('x'), 'doc_hash': good_hash},
            {'ops': []},
            {'ops': 'nope', 'doc_hash': good_hash},
            {'ops': [{'at': -1, 'delete': 0, 'insert': []}], 'doc_hash': good_hash},
            {'ops': [{'at': 0, 'delete': True, 'insert': []}], 'doc_hash': good_hash},
            {'ops': [{'at': 0, 'patch': [0, 0]}], 'doc_hash': good_hash},
            {'ops': [{'at': 0, 'insert': []}], 'doc_hash': good_hash},
            {'ops': [{'at': 0, 'delete': 0, 'insert': [], 'extra': 1}], 'doc_hash': good_hash},
            {'ops': [{'at': 0, 'delete': 0, 'insert': []}] * 1001, 'doc_hash': good_hash},
            {'ops': [], 'doc_hash': 'ABC'},
        ]
        for body in bodies:
            with self.subTest(body=str(body)[:80]):
                response = self.client.put(url, {**body, 'base_seq': 1, 'client_save_id': 'bad'}, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        essay.refresh_from_db()
        self.assertEqual(self.tab_of(essay).save_seq, 1)

    def test_delta_results_are_validated_and_size_limited(self):
        essay = self.saved_essay('One.')
        bad = {'type': 'doc', 'content': [paragraph('One.'), {'type': 'iframe'}]}
        response = self.delta(essay, [{'at': 1, 'delete': 0, 'insert': [{'type': 'iframe'}]}], bad)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'invalid_doc')
        huge = make_doc('One.', 'y' * (300 * 1024))
        response = self.delta(essay, [{'at': 1, 'delete': 0, 'insert': [paragraph('y' * (300 * 1024))]}], huge)
        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        essay.refresh_from_db()
        self.assertEqual(self.tab_of(essay).save_seq, 1)

    def test_validation_changes_are_reported_through_the_hash(self):
        essay = self.saved_essay('One.')
        # The inserted block carries an attribute the server drops.
        raw = {'type': 'paragraph', 'attrs': {'textAlign': 'left'}, 'content': [{'type': 'text', 'text': 'Two.'}]}
        client_view = {'type': 'doc', 'content': [paragraph('One.'), raw]}
        response = self.delta(essay, [{'at': 1, 'delete': 0, 'insert': [raw]}], client_view)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['doc_hash'], doc_hash(make_doc('One.', 'Two.')))
        self.assertNotEqual(response.data['doc_hash'], doc_hash(client_view))

    def test_unchanged_delta_writes_nothing(self):
        essay = self.saved_essay('One.')
        before, before_essay = self.tab_of(essay), Essay.objects.get(pk=essay.pk)
        response = self.delta(essay, [], make_doc('One.'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['save_seq'], 1)
        after = self.tab_of(essay)
        self.assertEqual((after.save_seq, after.updated_at, after.last_client_save_id),
                         (before.save_seq, before.updated_at, before.last_client_save_id))
        self.assertEqual(Essay.objects.get(pk=essay.pk).updated_at, before_essay.updated_at)

    def test_checkpoint_cadence_holds_for_deltas(self):
        essay = self.saved_essay('First words')
        self.assertEqual(EssayCheckpoint.objects.filter(essay=essay).count(), 1)
        self.delta(essay, [patch_op(0, paragraph('First words'), paragraph('First words and more'))],
                   make_doc('First words and more'), save_id='d1')
        self.assertEqual(EssayCheckpoint.objects.filter(essay=essay).count(), 1)
        EssayCheckpoint.objects.filter(essay=essay).update(created_at=timezone.now() - timedelta(minutes=11))
        essay.refresh_from_db()
        self.delta(essay, [patch_op(0, paragraph('First words and more'), paragraph('Even more'))],
                   make_doc('Even more'), save_id='d2')
        self.assertEqual(EssayCheckpoint.objects.filter(essay=essay).count(), 2)
        self.assertEqual(EssayCheckpoint.objects.filter(essay=essay).first().content, 'Even more')

    def test_sequence_of_deltas_through_the_api(self):
        rng = random.Random(7)
        essay = self.saved_essay('Start.')
        blocks = [paragraph('Start.')]
        saves = 0
        for step in range(30):
            ops = random_ops(rng, blocks)
            expected = reference_apply(blocks, ops)
            result = validate_doc({'type': 'doc', 'content': expected})
            if result['content'] != expected:
                continue  # emptied the doc: the server adds a paragraph, covered elsewhere
            essay.refresh_from_db()
            response = self.delta(essay, wire(ops), result, save_id=f'seq-{step}')
            self.assertEqual(response.status_code, status.HTTP_200_OK, (step, response.data))
            blocks = expected
            saves += 1
        self.assertGreater(saves, 20)
        essay.refresh_from_db()
        self.assertEqual(self.tab_of(essay).doc['content'], blocks)
        self.assertEqual(essay.content, derive(self.tab_of(essay).doc)[0])

    def test_typing_in_one_paragraph_of_a_long_essay_sends_under_five_percent(self):
        sentences = [f'Sentence {i} of this long essay tells one more small true thing.' for i in range(180)]
        texts = [' '.join(sentences[i:i + 9]) for i in range(0, 180, 9)]  # 20 paragraphs, ~2,000 words
        full = make_doc(*texts)
        self.assertGreaterEqual(derive(full)[1], 2000)
        edited_texts = list(texts)
        edited_texts[11] = texts[11][:200] + ' a few new words' + texts[11][200:]
        edited = make_doc(*edited_texts)
        delta_body = {'ops': [patch_op(11, paragraph(texts[11]), paragraph(edited_texts[11]))],
                      'doc_hash': doc_hash(edited), 'base_seq': 1, 'client_save_id': 'long-2', 'cursor': 9999}
        full_body = {'doc': edited, 'base_seq': 1, 'client_save_id': 'long-2', 'cursor': 9999}
        self.assertLess(len(json.dumps(delta_body)), 0.05 * len(json.dumps(full_body)))
        essay = self.make_essay()
        self.autosave(essay, full, base_seq=0, save_id='long-1')
        response = self.client.put(f'{BASE}/essays/{essay.pk}/autosave/', delta_body, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        essay.refresh_from_db()
        self.assertEqual(self.tab_of(essay).doc, edited)


class EssayLabFolderTests(EssayLabTestCase):
    def test_folder_crud_and_counts(self):
        response = self.client.post(f'{BASE}/folders/', {'name': 'Ivy League'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        parent_id = response.data['id']
        self.assertEqual(response.data['position'], 0)
        second = self.client.post(f'{BASE}/folders/', {'name': 'Scholarships'}, format='json').data
        self.assertEqual(second['position'], 1)
        child = self.client.post(f'{BASE}/folders/', {'name': 'Harvard', 'parent': parent_id}, format='json').data
        self.assertEqual(child['parent'], parent_id)

        self.make_essay(folder_id=parent_id)
        self.make_essay(folder_id=parent_id, trashed_at=timezone.now())
        folders = {item['id']: item for item in self.client.get(f'{BASE}/folders/').data}
        self.assertEqual(folders[parent_id]['essay_count'], 1)
        self.assertEqual(set(folders[parent_id]), {'id', 'name', 'parent', 'position', 'essay_count'})

        response = self.client.patch(f'{BASE}/folders/{second["id"]}/', {'name': 'Money'}, format='json')
        self.assertEqual(response.data['name'], 'Money')
        response = self.client.patch(f'{BASE}/folders/{child["id"]}/', {'parent': None}, format='json')
        self.assertIsNone(response.data['parent'])
        self.assertEqual(response.data['position'], 2)

    def test_nesting_limit(self):
        top = EssayFolder.objects.create(student=self.student, name='Top')
        child = EssayFolder.objects.create(student=self.student, name='Child', parent=top)
        other = EssayFolder.objects.create(student=self.student, name='Other', position=1)
        cases = [
            ('post', f'{BASE}/folders/', {'name': 'Grandchild', 'parent': child.pk}),
            ('patch', f'{BASE}/folders/{top.pk}/', {'parent': other.pk}),
            ('patch', f'{BASE}/folders/{other.pk}/', {'parent': child.pk}),
            ('patch', f'{BASE}/folders/{other.pk}/', {'parent': other.pk}),
        ]
        for method, url, body in cases:
            with self.subTest(url=url, body=body):
                response = getattr(self.client, method)(url, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data['code'], 'nesting_limit')

    def test_delete_moves_essays_and_subfolders_up(self):
        top = EssayFolder.objects.create(student=self.student, name='Top', position=0)
        EssayFolder.objects.create(student=self.student, name='Sibling', position=1)
        child = EssayFolder.objects.create(student=self.student, name='Child', parent=top)
        essay = self.make_essay(folder=top)
        child_essay = self.make_essay(folder=child)
        response = self.client.delete(f'{BASE}/folders/{top.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        essay.refresh_from_db()
        child.refresh_from_db()
        child_essay.refresh_from_db()
        self.assertIsNone(essay.folder_id)
        self.assertIsNone(child.parent_id)
        self.assertEqual(child.position, 2)
        self.assertEqual(child_essay.folder_id, child.pk)

    def test_reorder(self):
        a = EssayFolder.objects.create(student=self.student, name='A', position=0)
        b = EssayFolder.objects.create(student=self.student, name='B', position=1)
        c = EssayFolder.objects.create(student=self.student, name='C', position=2)
        sub = EssayFolder.objects.create(student=self.student, name='Sub', parent=a)
        response = self.client.put(f'{BASE}/folders/order/', {'parent': None, 'ids': [c.pk, a.pk, b.pk]},
                                   format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        top_level = [item['id'] for item in response.data if item['parent'] is None]
        self.assertEqual(top_level, [c.pk, a.pk, b.pk])
        for ids in ([c.pk, a.pk], [c.pk, a.pk, b.pk, b.pk], [c.pk, a.pk, b.pk, sub.pk]):
            response = self.client.put(f'{BASE}/folders/order/', {'parent': None, 'ids': ids}, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.data['code'], 'order_mismatch')
        response = self.client.put(f'{BASE}/folders/order/', {'parent': a.pk, 'ids': [sub.pk]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class EssayLabDepthCheckTests(EssayLabTestCase):
    def setUp(self):
        super().setUp()
        self.essay = self.make_essay()

    def check(self, base_seq=None):
        seq = self.tab_of(self.essay).save_seq if base_seq is None else base_seq
        return self.client.post(f'{BASE}/essays/{self.essay.pk}/depth-check/', {'base_seq': seq}, format='json')

    def ai_payload(self, **overrides):
        payload = {
            'summary': 'A warm story about patience.',
            'strengths': ['"folded the leftover crust" is vivid'],
            'scores': {'reflection': 2, 'specificity': 3, 'voice': 4, 'structure': 3, 'prompt_fit': 3},
            'notes': [
                {'id': 'x', 'kind': 'reflect', 'quote': 'I learned that patience matters.',
                 'question': 'When did you first notice this?', 'why': 'Shows the moment.',
                 'rewrite': 'I discovered patience.'},
                # Curly quotes and extra whitespace still match after normalization.
                {'id': 'y', 'kind': 'specific', 'quote': 'My grandmother  never wasted bread.',
                 'question': 'What did the kitchen smell like?', 'why': 'Sensory detail.'},
                {'id': 'z', 'kind': 'clarity', 'quote': 'This sentence is not in the essay.',
                 'question': 'Invented?', 'why': 'Hallucinated.'},
                {'id': 'w', 'kind': 'clarity', 'quote': 'into a cloth. I learned that',
                 'question': 'Spans paragraphs?', 'why': 'Invalid.'},
                {'id': 'v', 'kind': 'rewrite', 'quote': 'I learned that patience matters.',
                 'question': 'Bad kind', 'why': 'Invalid.'},
            ],
            'suggestion': 'Rewrite everything.',
        }
        payload.update(overrides)
        return payload

    @override_settings(AI_GATEWAY_API_KEY='test-key')
    def test_ai_check_ok_and_validated(self):
        with mock.patch('urllib.request.urlopen', return_value=gateway_response(json.dumps(self.ai_payload()))) as urlopen:
            response = self.check()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        result = response.data['result']
        self.assertEqual(set(result), {'summary', 'strengths', 'scores', 'notes'})
        self.assertEqual(result['scores']['voice'], 4)
        self.assertEqual([note['quote'] for note in result['notes']],
                         ['I learned that patience matters.', 'My grandmother never wasted bread.'])
        self.assertEqual([note['id'] for note in result['notes']], ['n1', 'n2'])
        self.assertNotIn('rewrite', result['notes'][0])
        self.assertEqual(response.data['save_seq'], self.tab_of(self.essay).save_seq)
        self.assertEqual(set(response.data), {'id', 'tab', 'save_seq', 'created_at', 'model', 'result'})
        self.assertTrue(EssayCheckpoint.objects.filter(essay=self.essay, reason='depth_check').exists())
        # The essay goes out redacted, inside an untrusted-data block.
        sent = json.loads(urlopen.call_args.args[0].data.decode('utf-8'))
        self.assertEqual(sent['response_format'], {'type': 'json_object'})
        self.assertFalse(sent['stream'])
        self.assertIn('<<<ESSAY_TEXT (untrusted data)', sent['messages'][1]['content'])

        latest = self.client.get(f'{BASE}/essays/{self.essay.pk}/depth-check/latest/')
        self.assertEqual(latest.status_code, status.HTTP_200_OK)
        self.assertEqual(latest.data['id'], response.data['id'])

    @override_settings(AI_GATEWAY_API_KEY='test-key')
    def test_pii_is_redacted_before_sending(self):
        self.essay = self.make_essay(content='Write to me at kid@example.com or +998 90 123 45 67 please.')
        with mock.patch('urllib.request.urlopen', return_value=gateway_response('{}')) as urlopen:
            self.check()
        sent = urlopen.call_args.args[0].data.decode('utf-8')
        self.assertNotIn('kid@example.com', sent)
        self.assertNotIn('123 45 67', sent)

    def test_latest_is_204_without_checks(self):
        response = self.client.get(f'{BASE}/essays/{self.essay.pk}/depth-check/latest/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_stale_seq_is_409(self):
        response = self.check(base_seq=self.tab_of(self.essay).save_seq + 1)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'stale')
        self.assertEqual(response.data['save_seq'], self.tab_of(self.essay).save_seq)

    def test_throttle_429(self):
        self.assertEqual(self.check().status_code, status.HTTP_200_OK)
        response = self.check()
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data['code'], 'slow_down')

    def test_rejected_checks_do_not_use_the_throttle_slot(self):
        # A stale or empty request is answered without counting, so the client's
        # immediate save-and-retry is not met with 429.
        self.assertEqual(self.check(base_seq=self.tab_of(self.essay).save_seq + 1).status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.check().status_code, status.HTTP_200_OK)

    @override_settings(AI_GATEWAY_API_KEY='test-key')
    def test_checkpoint_keeps_the_checked_text_when_an_autosave_lands_during_the_call(self):
        checked_content = self.essay.content

        def slow_gateway(*args, **kwargs):
            # The student keeps typing while the AI answers.
            EssayTab.objects.filter(essay=self.essay).update(doc=make_doc('Brand new text.'), content='Brand new text.')
            return gateway_response(json.dumps(self.ai_payload()))

        with mock.patch('urllib.request.urlopen', side_effect=slow_gateway):
            self.assertEqual(self.check().status_code, status.HTTP_200_OK)
        checkpoint = EssayCheckpoint.objects.get(essay=self.essay, reason='depth_check')
        self.assertEqual(checkpoint.content, checked_content)
        self.assertEqual(derive(checkpoint.doc)[0], checked_content)

    @override_settings(ESSAY_COACH_HOURLY_LIMIT=2, ESSAY_COACH_MIN_INTERVAL_SECONDS=1)
    def test_hourly_limit(self):
        clock = mock.Mock(time=mock.Mock(side_effect=[1000.0, 1002.0, 1004.0]))
        with mock.patch('apps.users.throttles.time', clock):
            self.assertEqual(self.check().status_code, status.HTTP_200_OK)
            self.assertEqual(self.check().status_code, status.HTTP_200_OK)
            self.assertEqual(self.check().status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @override_settings(ESSAY_COACH_MIN_INTERVAL_SECONDS=0)
    def test_zero_interval_turns_the_interval_off(self):
        self.assertEqual(self.check().status_code, status.HTTP_200_OK)
        self.assertEqual(self.check().status_code, status.HTTP_200_OK)

    @override_settings(AI_GATEWAY_API_KEY='test-key', ESSAY_COACH_DAILY_BUDGET=0)
    def test_budget_503(self):
        with mock.patch('urllib.request.urlopen') as urlopen:
            response = self.check()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['code'], 'coach_resting')
        urlopen.assert_not_called()

    @override_settings(AI_GATEWAY_API_KEY='test-key')
    def test_malformed_ai_json(self):
        with mock.patch('urllib.request.urlopen', return_value=gateway_response('this is { not json')):
            response = self.check()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['code'], 'coach_unavailable')
        self.assertFalse(EssayDepthCheck.objects.exists())

        cache.clear()
        garbage = json.dumps({'summary': 42, 'scores': {'voice': 9, 'reflection': True, 'structure': 2.0},
                              'notes': 'nope', 'strengths': [1, 'fine']})
        with mock.patch('urllib.request.urlopen', return_value=gateway_response(f'```json\n{garbage}\n```')):
            response = self.check()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['result'], {
            'summary': '', 'strengths': ['fine'], 'scores': {'structure': 2}, 'notes': [],
        })

    @override_settings(AI_GATEWAY_API_KEY='test-key')
    def test_gateway_error_is_503(self):
        import urllib.error
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('down')):
            response = self.check()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['code'], 'coach_unavailable')

    def test_quote_validation(self):
        content = 'He said “hello there” to me.\n\nSecond paragraph starts here.'
        raw = {'notes': [
            {'kind': 'reflect', 'quote': 'He said "hello there"', 'question': 'q'},
            {'kind': 'reflect', 'quote': 'to me.\nSecond paragraph', 'question': 'q'},
            {'kind': 'reflect', 'quote': 'to me. Second paragraph', 'question': 'q'},
            {'kind': 'reflect', 'quote': 'x' * 301, 'question': 'q'},
            {'kind': 'reflect', 'quote': 'Second paragraph', 'question': ''},
            {'kind': 'strength', 'quote': 'Second paragraph', 'question': 'Nice'},
        ]}
        notes = coach.validate_result(raw, content)['notes']
        self.assertEqual([note['quote'] for note in notes], ['He said "hello there"', 'Second paragraph'])
        many = {'notes': [{'kind': 'clarity', 'quote': f'w{i}', 'question': 'q'} for i in range(20)]}
        text = ' '.join(f'w{i}' for i in range(20))
        self.assertEqual(len(coach.validate_result(many, text)['notes']), 12)

    def test_local_fallback(self):
        long_paragraph = ' '.join(['Sentence number one goes on.'] * 40)
        self.essay = self.make_essay(content=(
            'I have always wanted to make a difference in the world.\n\n'
            'I learned a lot about myself.\n\n' + long_paragraph
        ))
        response = self.check()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['model'], 'local')
        kinds = {note['kind'] for note in response.data['result']['notes']}
        self.assertTrue({'reflect', 'specific', 'clarity'} <= kinds)
        self.assertEqual(set(response.data['result']['scores']),
                         {'reflection', 'specificity', 'voice', 'structure', 'prompt_fit'})

    def test_empty_essay_is_400(self):
        self.essay = self.make_essay(content='')
        response = self.check()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'empty_essay')

    def test_keeps_latest_twenty(self):
        EssayDepthCheck.objects.bulk_create(
            [EssayDepthCheck(essay=self.essay, tab=self.tab_of(self.essay), save_seq=0, result={}, model='local')
             for _ in range(DEPTH_CHECK_KEEP)]
        )
        response = self.check()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(EssayDepthCheck.objects.filter(essay=self.essay).count(), DEPTH_CHECK_KEEP)
        self.assertTrue(EssayDepthCheck.objects.filter(pk=response.data['id']).exists())


class EssayLabSearchTests(EssayLabTestCase):
    def test_search_matches_the_essay_text(self):
        self.make_essay(title='Bread', content='The kitchen smelled of cardamom every Friday.')
        self.make_essay(title='Robots', content='Soldering my first circuit board.')
        response = self.client.get(f'{BASE}/essays/', {'q': 'cardamom'})
        self.assertEqual([item['title'] for item in response.data], ['Bread'])


class EssayLabCacheOutageTests(EssayLabTestCase):
    def test_autosave_and_depth_check_fail_open_when_redis_is_down(self):
        essay = self.make_essay()
        broken = {'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': 'redis://127.0.0.1:1/0',
            'OPTIONS': {'socket_connect_timeout': 0.2, 'socket_timeout': 0.2},
        }}
        with override_settings(CACHES=broken), self.assertLogs('naseeb.cache', level='WARNING'):
            saved = self.autosave(essay, make_doc('Still saving during an outage.'), base_seq=0, save_id='outage-1')
            checked = self.client.post(f'{BASE}/essays/{essay.pk}/depth-check/', {'base_seq': 1}, format='json')
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        self.assertEqual(checked.status_code, status.HTTP_200_OK, checked.data)


class LegacyEssayApiTests(EssayLabTestCase):
    NEW_FIELDS = {
        'essay_type', 'folder', 'word_limit', 'doc', 'save_seq', 'last_client_save_id', 'word_count',
        'preview', 'last_cursor', 'last_edited_at', 'trashed_at', 'page_size', 'tabs', 'tab',
    }

    def make_essay(self, student=None, **fields):
        # These tests are about staff access, which needs a shared essay.
        fields.setdefault('shared_with_counselor', True)
        return super().make_essay(student, **fields)

    def test_trashed_essays_leave_counselor_counts_and_school_view(self):
        essay = self.make_essay(status=Essay.Status.NEEDS_REVISION)
        self.client.post(f'{BASE}/essays/{essay.pk}/trash/')
        self.client.force_authenticate(self.counselor)
        stats = self.client.get('/api/dashboard/stats/')
        self.assertEqual(stats.status_code, status.HTTP_200_OK, stats.data)
        self.assertEqual(stats.data['essays_need_revision'], 0)
        self.assertEqual(self.client.get(f'/api/essays/{essay.pk}/').status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.organization)
        visibility = self.client.get(f'/api/students/{self.student.pk}/data-visibility/')
        self.assertEqual(visibility.status_code, status.HTTP_200_OK, visibility.data)
        self.assertEqual(visibility.data['essays'], [])

    def test_legacy_patch_clears_doc_and_bumps_seq(self):
        essay = self.make_essay()
        self.autosave(essay, make_doc('Rich text'), base_seq=0, save_id='1')
        self.client.force_authenticate(self.counselor)
        response = self.client.patch(f'/api/essays/{essay.pk}/', {'content': 'Counselor fixed a typo here.'},
                                     format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        essay.refresh_from_db()
        self.assertIsNone(self.tab_of(essay).doc)
        self.assertEqual(self.tab_of(essay).save_seq, 2)
        self.assertEqual(essay.word_count, 5)
        self.assertEqual(essay.preview, 'Counselor fixed a typo here.')
        self.assertEqual(essay.version, 2)
        # The student's in-flight autosave against the old seq now conflicts.
        self.client.force_authenticate(self.student_user)
        response = self.autosave(essay, make_doc('Stale'), base_seq=1, save_id='2')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['doc'], make_doc('Counselor fixed a typo here.'))

    def test_legacy_patch_without_text_change_keeps_doc(self):
        essay = self.make_essay()
        self.autosave(essay, make_doc('Rich text'), base_seq=0, save_id='1')
        self.client.force_authenticate(self.counselor)
        self.client.patch(f'/api/essays/{essay.pk}/', {'content': 'Rich text', 'counselor_comment': 'Nice'},
                          format='json')
        essay.refresh_from_db()
        self.assertEqual(self.tab_of(essay).doc, make_doc('Rich text'))
        self.assertEqual(self.tab_of(essay).save_seq, 1)
        self.assertEqual(essay.counselor_comment, 'Nice')
        self.assertEqual(essay.version, 2)

    def test_counselor_and_organisation_responses_have_no_new_fields(self):
        essay = self.make_essay()
        for user in (self.counselor, self.organization, self.student_user):
            self.client.force_authenticate(user)
            with self.subTest(role=user.role):
                listing = self.client.get('/api/essays/')
                self.assertEqual(listing.status_code, status.HTTP_200_OK)
                rows = listing.data['results'] if isinstance(listing.data, dict) else listing.data
                self.assertEqual(len(rows), 1)
                self.assertFalse(self.NEW_FIELDS & set(rows[0]))
                detail = self.client.get(f'/api/essays/{essay.pk}/').data
                self.assertFalse(self.NEW_FIELDS & set(detail))
                self.assertIn('university_name', detail)
        self.client.force_authenticate(self.counselor)
        detail = self.client.get(f'/api/essays/{essay.pk}/').data
        for field in ('content', 'counselor_comment', 'revisions', 'version', 'student_name'):
            self.assertIn(field, detail)

    def test_legacy_write_ignores_new_fields(self):
        essay = self.make_essay()
        self.client.patch(f'/api/essays/{essay.pk}/', {'save_seq': 50, 'doc': {'type': 'doc'},
                                                       'trashed_at': '2020-01-01T00:00:00Z'}, format='json')
        essay.refresh_from_db()
        self.assertEqual(self.tab_of(essay).save_seq, 0)
        self.assertIsNone(self.tab_of(essay).doc)
        self.assertIsNone(essay.trashed_at)

    def test_student_cannot_set_counselor_comment_or_approve(self):
        essay = self.make_essay()
        response = self.client.patch(f'/api/essays/{essay.pk}/', {'counselor_comment': 'Perfect, approved!'},
                                     format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        essay.refresh_from_db()
        self.assertEqual(essay.counselor_comment, '')
        response = self.client.patch(f'/api/essays/{essay.pk}/', {'status': 'approved'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post('/api/essays/', {
            'student': self.student.pk, 'title': 'New', 'prompt': 'P', 'counselor_comment': 'fake',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Essay.objects.get(pk=response.data['id']).counselor_comment, '')

    def test_application_must_belong_to_the_essays_student(self):
        university = University.objects.create(name='Essay U', country='Testland')
        own = Application.objects.create(student=self.student, university=university, program='CS')
        foreign = Application.objects.create(student=self.other_student, university=university, program='CS')
        essay = self.make_essay()
        response = self.client.patch(f'/api/essays/{essay.pk}/', {'application': foreign.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post('/api/essays/', {
            'student': self.student.pk, 'title': 'New', 'prompt': 'P', 'application': foreign.pk,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.patch(f'/api/essays/{essay.pk}/', {'application': own.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Counselors are held to the same rule.
        self.client.force_authenticate(self.counselor)
        response = self.client.patch(f'/api/essays/{essay.pk}/', {'application': foreign.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_legacy_create_derives_word_count(self):
        response = self.client.post('/api/essays/', {
            'student': self.student.pk, 'title': 'New', 'prompt': '', 'content': 'Three small words',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        essay = Essay.objects.get(pk=response.data['id'])
        self.assertEqual(essay.word_count, 3)
        self.assertEqual(essay.preview, 'Three small words')


class StatementCountMixin:
    """Query budgets. Transaction control (BEGIN/SAVEPOINT/COMMIT) isn't a round trip that matters
    here and differs between SQLite and the test wrapper, so only real statements are counted."""

    TRANSACTION_CONTROL = ('BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'RELEASE SAVEPOINT', 'ROLLBACK TO SAVEPOINT')

    @contextmanager
    def assertNumQueries(self, expected):
        with CaptureQueriesContext(connection) as captured:
            yield
        statements = [
            query['sql'] for query in captured.captured_queries
            if not query['sql'].upper().startswith(self.TRANSACTION_CONTROL)
        ]
        self.assertEqual(len(statements), expected, '\n'.join(statements))


class EssayLabQueryBudgetTests(StatementCountMixin, EssayLabTestCase):
    def test_list_is_one_query(self):
        folder = EssayFolder.objects.create(student=self.student, name='F')
        for index in range(15):
            self.make_essay(title=f'Essay {index}', folder=folder if index % 2 else None)
        with self.assertNumQueries(1):
            response = self.client.get(f'{BASE}/essays/')
        self.assertEqual(len(response.data), 15)

    def test_autosave_budget(self):
        essay = self.make_essay()
        tab = self.tab_of(essay)
        url = f'{BASE}/essays/{essay.pk}/autosave/'
        # A normal save: lock the essay, lock the tab, checkpoint probe, update the tab,
        # read the tabs' text, update the essay's derived text. The same for any number of tabs.
        # The first save also writes an automatic checkpoint and prunes: two more.
        with self.assertNumQueries(8):
            response = self.client.put(url, {'doc': make_doc('One'), 'base_seq': 0, 'client_save_id': 'a',
                                             'tab': tab.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with self.assertNumQueries(6):
            self.client.put(url, {'doc': make_doc('One two'), 'base_seq': 1, 'client_save_id': 'b', 'tab': tab.pk},
                            format='json')
        for index in range(20):
            EssayTab.objects.create(essay=essay, title=f'More {index}', position=index + 1, content='Other text.')
        with self.assertNumQueries(6):
            response = self.client.put(url, {'doc': make_doc('One two 3'), 'base_seq': 2, 'client_save_id': 'b2',
                                             'tab': tab.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        # Formatting only (same text): the essay's text isn't re-derived.
        bold = {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [
            {'type': 'text', 'text': 'One two 3', 'marks': [{'type': 'bold'}]}]}]}
        with self.assertNumQueries(5):
            self.client.put(url, {'doc': bold, 'base_seq': 3, 'client_save_id': 'b3', 'tab': tab.pk}, format='json')
        # An idempotent retry: only the locks.
        with self.assertNumQueries(2):
            self.client.put(url, {'doc': bold, 'base_seq': 3, 'client_save_id': 'b3', 'tab': tab.pk}, format='json')
        # At the checkpoint cap the prune is still one DELETE.
        doc = make_doc('x')
        EssayCheckpoint.objects.bulk_create(
            [EssayCheckpoint(essay=essay, tab=tab, doc=doc, content='x', reason='auto')
             for _ in range(CHECKPOINT_CAP - 1)]
        )
        EssayCheckpoint.objects.filter(essay=essay).update(created_at=timezone.now() - timedelta(minutes=30))
        with self.assertNumQueries(8):
            self.client.put(url, {'doc': make_doc('One two three'), 'base_seq': 4, 'client_save_id': 'c',
                                  'tab': tab.pk}, format='json')
        self.assertEqual(EssayCheckpoint.objects.filter(essay=essay).count(), CHECKPOINT_CAP)

    def test_delta_autosave_budget(self):
        essay = self.make_essay()
        self.client.put(f'{BASE}/essays/{essay.pk}/autosave/',
                        {'doc': make_doc('One'), 'base_seq': 0, 'client_save_id': 'a'}, format='json')
        # Same as a full save (the tab lock now reads the doc).
        with self.assertNumQueries(6):
            response = self.client.put(f'{BASE}/essays/{essay.pk}/autosave/', {
                'ops': [{'at': 1, 'delete': 0, 'insert': [paragraph('Two')]}],
                'doc_hash': doc_hash(make_doc('One', 'Two')), 'base_seq': 1, 'client_save_id': 'b',
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        # A resync is answered from the locked rows alone.
        with self.assertNumQueries(2):
            response = self.client.put(f'{BASE}/essays/{essay.pk}/autosave/', {
                'ops': [], 'doc_hash': '0' * 64, 'base_seq': 2, 'client_save_id': 'c',
            }, format='json')
        self.assertEqual(response.data['code'], 'resync')
        # Nothing changed: only the locks.
        with self.assertNumQueries(2):
            self.client.put(f'{BASE}/essays/{essay.pk}/autosave/', {
                'ops': [], 'doc_hash': doc_hash(make_doc('One', 'Two')), 'base_seq': 2, 'client_save_id': 'd',
            }, format='json')
