"""Essay collaboration: block ids, ops v2 merges, comments and suggestions, access and notifications."""

import copy
import json
from contextlib import contextmanager
from pathlib import Path

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User
from .essay_lab.access import resolve_access
from .essay_lab.collab import insert_text, mark_ids, mark_range, resolve_suggestions
from .essay_lab.doc import (
    BlockConflict, apply_ops_v2, block_hash, doc_hash, doc_stats, ensure_bids, validate_doc,
)
from .models import (
    Essay, EssayCheckpoint, EssayComment, EssayCommentThread, EssaySuggestion, EssayTab, EssayTabEdit, Notification,
    ParentStudentLink,
)
from .test_audit_base import AuditBaseMixin

FIXTURES = Path(__file__).parent / 'essay_lab' / 'fixtures' / 'doc_delta_cases.json'
LAB = '/api/essay-lab/essays'
REVIEW = '/api/essay-lab/review/essays'
SECRET = 'Grandmother bread secret'


def para(bid, text, marks=None):
    node = {'type': 'text', 'text': text}
    if marks:
        node['marks'] = marks
    return {'type': 'paragraph', 'attrs': {'bid': bid}, 'content': [node]}


def doc(*blocks):
    return {'type': 'doc', 'content': list(blocks)}


BASE_DOC = doc(para('p1', 'My grandmother never wasted bread.'), para('p2', 'I learned patience.'),
               para('p3', 'The radio came back to life.'))


class FixtureParityTests(APITestCase):
    """The shared cases the frontend runs too (tests/essayLabCollab.test.mjs)."""

    fixtures_data = json.loads(FIXTURES.read_text())

    def test_bid_cases(self):
        for case in self.fixtures_data['bid_cases']:
            with self.subTest(case['name']):
                self.assertEqual(ensure_bids(case['input']), case['output'])

    def test_v2_cases(self):
        for case in self.fixtures_data['v2_cases']:
            with self.subTest(case['name']):
                base = validate_doc(case['base'])
                result = apply_ops_v2(base['content'], case['ops_v2'])
                self.assertEqual(doc_hash({'type': 'doc', 'content': result}), case['doc_hash'])

    def test_merge_cases(self):
        for case in self.fixtures_data['merge_cases']:
            with self.subTest(case['name']):
                stored = validate_doc(case['stored'])['content']
                if 'conflicts' in case:
                    with self.assertRaises(BlockConflict) as caught:
                        apply_ops_v2(stored, case['ops_v2'])
                    self.assertEqual(caught.exception.bids, case['conflicts'])
                else:
                    self.assertEqual(apply_ops_v2(stored, case['ops_v2']), case['merged']['content'])


class DocOperationTests(APITestCase):
    def test_marks_split_text_and_sort_after_formatting(self):
        block = {'type': 'paragraph', 'attrs': {'bid': 'a'}, 'content': [
            {'type': 'text', 'text': 'Bold ', 'marks': [{'type': 'bold'}]}, {'type': 'text', 'text': 'plain words'},
        ]}
        marked, quote = mark_range(block, 2, 10, {'type': 'comment', 'attrs': {'id': 4}})
        self.assertEqual(quote, 'ld plain')
        self.assertEqual([node['text'] for node in marked['content']], ['Bo', 'ld ', 'plain', ' words'])
        self.assertEqual(marked['content'][1]['marks'], [{'type': 'bold'}, {'type': 'comment', 'attrs': {'id': 4}}])
        self.assertEqual(block['content'][0]['text'], 'Bold ', 'the input is not changed')
        self.assertEqual(validate_doc(doc(marked))['content'][0], marked)

    def test_offsets_count_utf16_units_like_the_editor(self):
        block = para('a', 'A😀b')
        marked, quote = mark_range(block, 3, 4, {'type': 'comment', 'attrs': {'id': 1}})
        self.assertEqual(quote, 'b')
        with self.assertRaises(Exception):
            mark_range(block, 2, 4, {'type': 'comment', 'attrs': {'id': 1}})

    def test_suggestions_are_left_out_until_accepted(self):
        block, _ = mark_range(para('a', 'I learned slowly that.'), 10, 17, {'type': 'suggestDelete', 'attrs': {'id': 1}})
        block = insert_text(block, 17, 'quickly ', {'type': 'suggestInsert', 'attrs': {'id': 1}})
        suggested = validate_doc(doc(block))
        self.assertEqual(doc_stats(suggested).content, 'I learned slowly that.')
        accepted = resolve_suggestions(suggested, {1: True})
        rejected = resolve_suggestions(suggested, {1: False})
        self.assertEqual(doc_stats(accepted).content, 'I learned quickly that.')
        self.assertEqual(accepted['content'][0]['content'], [{'type': 'text', 'text': 'I learned quickly that.'}],
                         'neighbouring text with the same marks is joined, as the editor does')
        self.assertEqual(rejected['content'][0]['content'], [{'type': 'text', 'text': 'I learned slowly that.'}])


class CollabTestCase(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        ParentStudentLink.objects.create(parent=self.parent, student=self.student,
                                         status=ParentStudentLink.Status.ACTIVE, consented_at=timezone.now())
        self.essay = Essay.objects.create(student=self.student, title=SECRET, prompt='Why?', content='x',
                                          shared_with_counselor=True, shared_at=timezone.now())
        self.tab = EssayTab.objects.create(essay=self.essay, title='Tab 1', position=0, doc=copy.deepcopy(BASE_DOC))
        stats = doc_stats(BASE_DOC)
        EssayTab.objects.filter(pk=self.tab.pk).update(content=stats.content, word_count=stats.word_count)
        self.tab.refresh_from_db()

    def as_user(self, user):
        self.client.force_authenticate(user)

    def comment(self, user=None, bid='p2', start=10, end=18, body='Say more about this.'):
        self.as_user(user or self.counselor)
        return self.client.post(f'{REVIEW}/{self.essay.pk}/threads/',
                                {'tab': self.tab.pk, 'bid': bid, 'start': start, 'end': end, 'body': body}, format='json')

    def suggest(self, items, user=None):
        self.as_user(user or self.counselor)
        return self.client.post(f'{REVIEW}/{self.essay.pk}/suggestions/', {'tab': self.tab.pk, 'items': items},
                                format='json')

    def stored(self):
        self.tab.refresh_from_db()
        return self.tab.doc

    def autosave_v2(self, ops, base_seq, save_id, doc_hash_value='0' * 64):
        self.as_user(self.student_user)
        return self.client.put(f'{LAB}/{self.essay.pk}/autosave/', {
            'ops_v2': ops, 'doc_hash': doc_hash_value, 'base_seq': base_seq, 'client_save_id': save_id,
            'tab': self.tab.pk,
        }, format='json')


class AccessTests(CollabTestCase):
    def test_resolve_access_matrix(self):
        essay = Essay.objects.select_related('student__user', 'student__school').get(pk=self.essay.pk)
        self.assertEqual(resolve_access(self.student_user, essay), {'view', 'comment', 'suggest', 'edit', 'decide'})
        self.assertEqual(resolve_access(self.counselor, essay), {'view', 'comment', 'suggest'})
        self.assertEqual(resolve_access(self.admin, essay), {'view'})
        for user in (self.counselor_peer, self.counselor_b, self.teacher, self.organization, self.parent,
                     self.student_b_user):
            self.assertEqual(resolve_access(user, essay), set(), user.username)
        essay.counselor_access = Essay.CounselorAccess.COMMENT
        self.assertEqual(resolve_access(self.counselor, essay), {'view', 'comment'})
        essay.shared_with_counselor = False
        self.assertEqual(resolve_access(self.counselor, essay), set())
        self.assertEqual(resolve_access(self.student_user, essay), {'view', 'comment', 'suggest', 'edit', 'decide'})

    def test_every_staff_endpoint_is_404_for_everyone_but_the_assigned_counselor(self):
        thread = self.comment().data
        outsiders = (self.counselor_peer, self.counselor_b, self.teacher, self.organization, self.parent,
                     self.student_b_user, self.student_user)
        requests = [
            ('get', f'{REVIEW}/{self.essay.pk}/', None),
            ('get', f'{REVIEW}/{self.essay.pk}/changes/?tab={self.tab.pk}', None),
            ('post', f'{REVIEW}/{self.essay.pk}/threads/', {'tab': self.tab.pk, 'bid': 'p1', 'start': 0, 'end': 2, 'body': 'x'}),
            ('post', f'{REVIEW}/{self.essay.pk}/threads/{thread["id"]}/reply/', {'body': 'x'}),
            ('post', f'{REVIEW}/{self.essay.pk}/threads/{thread["id"]}/resolve/', None),
            ('post', f'{REVIEW}/{self.essay.pk}/threads/{thread["id"]}/reopen/', None),
            ('post', f'{REVIEW}/{self.essay.pk}/suggestions/', {'tab': self.tab.pk, 'items': [{'bid': 'p1', 'start': 0, 'end': 2}]}),
        ]
        for user in outsiders:
            self.as_user(user)
            for method, url, body in requests:
                response = getattr(self.client, method)(url, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, f'{user.username} {method} {url}')
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'{REVIEW}/{self.essay.pk}/').status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admins_read_only_and_audited(self):
        self.as_user(self.admin)
        response = self.client.get(f'{REVIEW}/{self.essay.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['capabilities'], ['view'])
        self.assertEqual(self.comment(self.admin).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.suggest([{'bid': 'p1', 'start': 0, 'end': 2}], self.admin).status_code,
                         status.HTTP_403_FORBIDDEN)
        from apps.users.models import ProductAuditEvent
        self.assertTrue(ProductAuditEvent.objects.filter(action='essay.review_read').exists())

    def test_comment_only_access_cannot_suggest(self):
        Essay.objects.filter(pk=self.essay.pk).update(counselor_access=Essay.CounselorAccess.COMMENT)
        self.assertEqual(self.comment().status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.suggest([{'bid': 'p1', 'start': 0, 'end': 2}]).status_code, status.HTTP_403_FORBIDDEN)

    def test_unshared_or_trashed_essays_are_hidden_but_feedback_is_kept(self):
        thread = self.comment().data
        self.as_user(self.student_user)
        self.client.post(f'{LAB}/{self.essay.pk}/unshare/')
        self.as_user(self.counselor)
        self.assertEqual(self.client.get(f'{REVIEW}/{self.essay.pk}/').status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.comment().status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(EssayCommentThread.objects.filter(pk=thread['id']).exists())
        # The student still sees it; after a new share the counselor does too.
        self.as_user(self.student_user)
        changes = self.client.get(f'{LAB}/{self.essay.pk}/changes/', {'tab': self.tab.pk})
        self.assertEqual([item['id'] for item in changes.data['threads']], [thread['id']])
        self.client.post(f'{LAB}/{self.essay.pk}/share/')
        self.as_user(self.counselor)
        response = self.client.get(f'{REVIEW}/{self.essay.pk}/')
        self.assertEqual([item['id'] for item in response.data['threads']], [thread['id']])
        Essay.objects.filter(pk=self.essay.pk).update(trashed_at=timezone.now())
        self.assertEqual(self.client.get(f'{REVIEW}/{self.essay.pk}/').status_code, status.HTTP_404_NOT_FOUND)

    def test_students_cannot_touch_other_students_threads(self):
        thread = self.comment().data
        self.as_user(self.student_b_user)
        for path in ('reply/', 'resolve/', 'reopen/'):
            response = self.client.post(f'{LAB}/{self.essay.pk}/threads/{thread["id"]}/{path}', {'body': 'x'}, format='json')
            self.assertIn(response.status_code, {status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN})
        self.assertEqual(self.client.get(f'{LAB}/{self.essay.pk}/changes/', {'tab': self.tab.pk}).status_code,
                         status.HTTP_404_NOT_FOUND)
        for user in (self.counselor, self.parent):
            self.as_user(user)
            self.assertIn(self.client.get(f'{LAB}/{self.essay.pk}/changes/', {'tab': self.tab.pk}).status_code,
                          {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND})


class CommentTests(CollabTestCase):
    def test_counselor_comment_marks_the_words_and_tells_the_student(self):
        response = self.comment()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        thread = EssayCommentThread.objects.get(pk=response.data['id'])
        self.assertEqual(thread.quote, 'patience')
        stored = self.stored()
        self.assertEqual(stored['content'][1]['content'][1],
                         {'type': 'text', 'text': 'patience', 'marks': [{'type': 'comment', 'attrs': {'id': thread.pk}}]})
        self.assertEqual(self.tab.save_seq, 1)
        self.assertEqual(self.tab.content, doc_stats(BASE_DOC).content, 'a comment never changes the text')
        notice = Notification.objects.get(recipient__isnull=True, kind=Notification.Kind.ESSAY)
        self.assertEqual((notice.title, notice.target_id), ('New feedback on your essay', self.essay.pk))
        self.assertNotIn('patience', notice.message)
        self.assertNotIn(SECRET, notice.message)
        checkpoint = EssayCheckpoint.objects.get(kind=EssayCheckpoint.Kind.COMMENT)
        self.assertEqual(checkpoint.author, self.counselor)
        self.assertTrue(EssayTabEdit.objects.filter(kind='comment', author=self.counselor).exists())

    def test_legacy_docs_get_their_ids_on_the_first_comment(self):
        EssayTab.objects.filter(pk=self.tab.pk).update(doc={'type': 'doc', 'content': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Old text without ids.'}]}]})
        response = self.comment(bid='n0', start=0, end=3)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(self.stored()['content'][0]['attrs'], {'bid': 'n0'})

    def test_bad_ranges_are_refused_and_nothing_is_written(self):
        for body in ({'bid': 'zz'}, {'start': 5, 'end': 500}, {'start': 3, 'end': 3}):
            response = self.comment(**body)
            self.assertIn(response.status_code, {status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT}, body)
        self.assertEqual(EssayCommentThread.objects.count(), 0)
        self.assertEqual(self.stored(), BASE_DOC)

    def test_student_replies_resolves_and_reopens_and_the_counselor_is_told(self):
        thread = self.comment().data
        self.as_user(self.student_user)
        reply = self.client.post(f'{LAB}/{self.essay.pk}/threads/{thread["id"]}/reply/', {'body': 'I will.'}, format='json')
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED)
        self.assertEqual([comment['body'] for comment in reply.data['comments']], ['Say more about this.', 'I will.'])
        self.assertTrue(reply.data['comments'][1]['by_me'])
        resolved = self.client.post(f'{LAB}/{self.essay.pk}/threads/{thread["id"]}/resolve/')
        self.assertEqual(resolved.data['status'], 'resolved')
        self.client.post(f'{LAB}/{self.essay.pk}/threads/{thread["id"]}/resolve/')  # idempotent: one notice
        reopened = self.client.post(f'{LAB}/{self.essay.pk}/threads/{thread["id"]}/reopen/')
        self.assertEqual(reopened.data['status'], 'open')
        titles = list(Notification.objects.filter(recipient=self.counselor).order_by('id').values_list('title', flat=True))
        self.assertEqual(titles, ['New reply to your comment', 'Comment resolved'])

    def test_counselor_replies_and_resolves(self):
        thread = self.comment().data
        self.as_user(self.counselor)
        reply = self.client.post(f'{REVIEW}/{self.essay.pk}/threads/{thread["id"]}/reply/', {'body': 'Also this.'},
                                 format='json')
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.client.post(f'{REVIEW}/{self.essay.pk}/threads/{thread["id"]}/resolve/').data['status'],
                         'resolved')


class SuggestionTests(CollabTestCase):
    def make_two(self):
        response = self.suggest([
            {'bid': 'p1', 'start': 3, 'end': 14, 'text': 'nana'},  # "grandmother" -> "nana"
            {'bid': 'p3', 'start': 28, 'end': 28, 'text': ' again'},
        ])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data['suggestions']

    def decide(self, decisions):
        self.as_user(self.student_user)
        return self.client.post(f'{LAB}/{self.essay.pk}/suggestions/decide/', {'tab': self.tab.pk, 'decisions': decisions},
                                format='json')

    def test_suggestions_do_not_change_the_text_until_accepted(self):
        first, second = self.make_two()
        self.assertEqual((first['delete_text'], first['insert_text']), ('grandmother', 'nana'))
        self.tab.refresh_from_db()
        self.assertEqual(self.tab.content, doc_stats(BASE_DOC).content)
        self.assertEqual(Notification.objects.get(recipient__isnull=True).message,
                         f'{self.counselor.get_full_name() or self.counselor.username} suggested 2 edits to your essay.')
        response = self.decide([{'id': first['id'], 'accept': True}, {'id': second['id'], 'accept': False}])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.tab.refresh_from_db()
        self.assertEqual(self.tab.content, 'My nana never wasted bread.\n\nI learned patience.\n\nThe radio came back to life.')
        self.assertEqual(response.data['doc'], self.tab.doc)
        self.assertEqual(set(EssaySuggestion.objects.values_list('status', flat=True)), {'accepted', 'rejected'})
        # The counselor hears how it went; the student's own feed doesn't show that notice.
        notice = Notification.objects.get(recipient=self.counselor)
        self.assertEqual(notice.title, 'Suggestions reviewed')
        self.assertIn('accepted 1 suggestion and rejected 1 suggestion', notice.message)
        self.as_user(self.student_user)
        titles = [row['title'] for row in self.client.get('/api/notifications/').data['results']]
        self.assertNotIn('Suggestions reviewed', titles)
        self.assertEqual(self.client.get('/api/notifications/summary/').data['unread'], 1)
        # History names both people.
        history = self.client.get(f'{LAB}/{self.essay.pk}/checkpoints/', {'tab': self.tab.pk}).data
        lines = {(item['kind'], item['author_name'], item['by_me'], json.dumps(item['detail'], sort_keys=True)) for item in history}
        name = self.counselor.get_full_name() or self.counselor.username
        student_name = self.student_user.get_full_name() or self.student_user.username
        self.assertIn(('suggest', name, False, '{"suggestions": 2}'), lines)
        self.assertIn(('decision', student_name, True, '{"accepted": 1, "rejected": 1}'), lines)

    def test_decisions_are_all_or_nothing(self):
        first, second = self.make_two()
        before = self.stored()
        seq = self.tab.save_seq
        for decisions, code in (
            ([{'id': first['id'], 'accept': True}, {'id': 999999, 'accept': True}], status.HTTP_404_NOT_FOUND),
            ([{'id': first['id'], 'accept': True}, {'id': first['id'], 'accept': False}], status.HTTP_400_BAD_REQUEST),
        ):
            self.assertEqual(self.decide(decisions).status_code, code)
            self.assertEqual((self.stored(), self.tab.save_seq), (before, seq))
            self.assertEqual(EssaySuggestion.objects.filter(status='pending').count(), 2)
        self.assertEqual(self.decide([{'id': first['id'], 'accept': True}]).status_code, status.HTTP_200_OK)
        again = self.decide([{'id': second['id'], 'accept': True}, {'id': first['id'], 'accept': False}])
        self.assertEqual(again.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(EssaySuggestion.objects.get(pk=second['id']).status, 'pending')

    def test_overlapping_suggestions_are_refused(self):
        response = self.suggest([{'bid': 'p1', 'start': 0, 'end': 5}, {'bid': 'p1', 'start': 3, 'end': 8}])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(EssaySuggestion.objects.count(), 0)

    def test_other_students_cannot_decide(self):
        first, _second = self.make_two()
        self.as_user(self.student_b_user)
        response = self.client.post(f'{LAB}/{self.essay.pk}/suggestions/decide/',
                                    {'tab': self.tab.pk, 'decisions': [{'id': first['id'], 'accept': True}]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class StatementCounter:
    TRANSACTION_CONTROL = ('BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'RELEASE SAVEPOINT', 'ROLLBACK TO SAVEPOINT')

    @contextmanager
    def assertStatements(self, expected, at_most=False):
        with CaptureQueriesContext(connection) as captured:
            yield
        statements = [query['sql'] for query in captured.captured_queries
                      if not query['sql'].upper().startswith(self.TRANSACTION_CONTROL)]
        if at_most:
            self.assertLessEqual(len(statements), expected, '\n'.join(statements))
        else:
            self.assertEqual(len(statements), expected, '\n'.join(statements))


class MergeAutosaveTests(StatementCounter, CollabTestCase):
    def test_strict_v2_save_and_budget(self):
        stored = ensure_bids(self.stored())
        new_block = para('p2', 'I learned patience slowly.')
        result = {'type': 'doc', 'content': [stored['content'][0], new_block, stored['content'][2]]}
        with self.assertStatements(9, at_most=True):
            response = self.autosave_v2([{'set': 'p2', 'base': block_hash(stored['content'][1]), 'block': new_block}], 0,
                                        'v2-a', doc_hash(result))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['doc_hash'], doc_hash(result))
        self.assertNotIn('merged', response.data)
        self.assertEqual(self.stored(), result)

    def test_edits_to_different_paragraphs_merge(self):
        self.comment(bid='p3', start=4, end=9)  # the counselor changes p3 (seq 1)
        new_block = para('p1', 'My grandmother never wasted a crumb.')
        response = self.autosave_v2([{'set': 'p1', 'base': block_hash(BASE_DOC['content'][0]), 'block': new_block}], 0, 'm1')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['merged'])
        merged = self.stored()
        self.assertEqual(response.data['doc'], merged)
        self.assertEqual(merged['content'][0], new_block)
        self.assertEqual(merged['content'][2]['content'][1]['marks'][0]['type'], 'comment', 'the comment is kept')
        self.assertEqual(self.tab.save_seq, 2)
        self.assertIsNone(self.tab.last_editor_id)
        self.assertTrue(EssayTabEdit.objects.filter(kind='edit', author=self.student_user).exists(),
                        'the student starting to edit after the counselor is in the edit log')

    def test_the_same_paragraph_is_a_block_conflict_and_nothing_is_saved(self):
        self.comment(bid='p2')
        before = self.stored()
        new_block = para('p2', 'I learned nothing.')
        response = self.autosave_v2([{'set': 'p2', 'base': block_hash(BASE_DOC['content'][1]), 'block': new_block}], 0, 'c1')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual((response.data['code'], response.data['bids']), ('block_conflict', ['p2']))
        self.assertEqual(response.data['doc'], before)
        self.assertEqual(self.stored(), before)

    def test_v1_clients_still_need_the_latest_version(self):
        self.comment()
        self.as_user(self.student_user)
        response = self.client.put(f'{LAB}/{self.essay.pk}/autosave/', {
            'doc': BASE_DOC, 'base_seq': 0, 'client_save_id': 'old', 'tab': self.tab.pk}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (status.HTTP_409_CONFLICT, 'conflict'))
        latest = self.stored()
        ops = [{'at': 0, 'delete': 1, 'insert': [para('p1', 'Changed.')]}]
        result = {'type': 'doc', 'content': [para('p1', 'Changed.'), *latest['content'][1:]]}
        response = self.client.put(f'{LAB}/{self.essay.pk}/autosave/', {
            'ops': ops, 'doc_hash': doc_hash(result), 'base_seq': 1, 'client_save_id': 'v1', 'tab': self.tab.pk,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_poll_answers_304_in_one_query(self):
        self.as_user(self.student_user)
        url = f'{LAB}/{self.essay.pk}/changes/'
        first = self.client.get(url, {'tab': self.tab.pk, 'since': 0})
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertNotIn('doc', first.data, 'the client already has this version')
        etag = first['ETag']
        with self.assertStatements(1):
            again = self.client.get(url, {'tab': self.tab.pk, 'since': 0}, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(again.status_code, status.HTTP_304_NOT_MODIFIED)
        self.comment()
        self.as_user(self.student_user)
        changed = self.client.get(url, {'tab': self.tab.pk, 'since': 0}, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.assertEqual(changed.data['save_seq'], 1)
        self.assertEqual(len(changed.data['threads']), 1)
        self.assertEqual(changed.data['doc'], self.stored())
        self.assertTrue(changed.data['others_active'], 'the counselor just had the essay open')


class NotificationAudienceTests(CollabTestCase):
    def test_share_notice_goes_to_the_counselor_only(self):
        Essay.objects.filter(pk=self.essay.pk).update(shared_with_counselor=False)
        self.as_user(self.student_user)
        response = self.client.post(f'{LAB}/{self.essay.pk}/share/', {'access': 'comment'}, format='json')
        self.assertEqual(response.data['counselor_access'], 'comment')
        notice = Notification.objects.get(title='Essay shared with counselor')
        self.assertEqual(notice.recipient, self.counselor)
        self.assertEqual(self.client.get('/api/notifications/').data['results'], [])
        self.as_user(self.counselor)
        self.assertEqual([row['id'] for row in self.client.get('/api/notifications/').data['results']], [notice.pk])
        self.as_user(self.counselor_peer)
        self.assertEqual(self.client.get('/api/notifications/').data['results'], [])
        # Sharing again with another choice only changes the choice.
        self.as_user(self.student_user)
        self.client.post(f'{LAB}/{self.essay.pk}/share/', {'access': 'suggest'}, format='json')
        self.essay.refresh_from_db()
        self.assertEqual(self.essay.counselor_access, 'suggest')
        self.assertEqual(Notification.objects.filter(title='Essay shared with counselor').count(), 1)

    def test_student_notices_still_reach_student_and_counselor(self):
        notice = Notification.objects.create(student=self.student, title='Deadline alert', message='Soon.')
        for user in (self.student_user, self.counselor):
            self.as_user(user)
            self.assertIn(notice.pk, [row['id'] for row in self.client.get('/api/notifications/').data['results']])
        self.as_user(self.student_user)
        self.assertEqual(self.client.post(f'/api/notifications/{notice.pk}/read/').status_code, status.HTTP_200_OK)
        staff_notice = Notification.objects.create(student=self.student, recipient=self.counselor, title='x', message='y')
        self.assertEqual(self.client.post(f'/api/notifications/{staff_notice.pk}/read/').status_code,
                         status.HTTP_404_NOT_FOUND)
        self.client.post('/api/notifications/read-all/')
        staff_notice.refresh_from_db()
        self.assertFalse(staff_notice.is_read, 'read-all only touches the student’s own notices')


class SeedDemoFeedbackTests(APITestCase):
    def test_demo_feedback_is_seeded_once_and_decidable(self):
        from io import StringIO

        from django.core.management import call_command
        from django.test import override_settings

        with override_settings(DEMO_ACCOUNTS_ENABLED=True):
            call_command('seed_demo', stdout=StringIO())
            call_command('seed_demo', stdout=StringIO())
        essay = Essay.objects.get(title='Why I rebuild radios', student__user__username='ramazon')
        self.assertTrue(essay.shared_with_counselor)
        self.assertEqual(EssayCommentThread.objects.filter(essay=essay).count(), 1)
        self.assertEqual(EssaySuggestion.objects.filter(essay=essay, status='pending').count(), 2)
        tab = EssayTab.objects.get(essay=essay)
        self.assertEqual(tab.doc, validate_doc(tab.doc))
        self.assertNotIn('rescued', tab.content)
        student = User.objects.get(username='ramazon')
        self.client.force_authenticate(student)
        ids = list(EssaySuggestion.objects.filter(essay=essay).values_list('id', flat=True))
        response = self.client.post(f'{LAB}/{essay.pk}/suggestions/decide/',
                                    {'tab': tab.pk, 'decisions': [{'id': pk, 'accept': True} for pk in ids]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        tab.refresh_from_db()
        self.assertIn('She called it respect. Every evening', tab.content)
        self.assertIn('I rescued the school radio', tab.content)


class FeedbackLifecycleTests(CollabTestCase):
    """Copies, restored versions, history pruning and who hears about the student's answers."""

    def make_two(self):
        response = self.suggest([
            {'bid': 'p1', 'start': 3, 'end': 14, 'text': 'nana'},
            {'bid': 'p3', 'start': 28, 'end': 28, 'text': ' again'},
        ])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data['suggestions']

    def decide(self, decisions):
        self.as_user(self.student_user)
        return self.client.post(f'{LAB}/{self.essay.pk}/suggestions/decide/', {'tab': self.tab.pk, 'decisions': decisions},
                                format='json')

    def feedback_marks(self, value):
        return mark_ids(value, 'comment') | mark_ids(value, 'suggestInsert') | mark_ids(value, 'suggestDelete')

    def test_duplicates_start_without_feedback(self):
        self.comment()
        self.make_two()
        self.as_user(self.student_user)
        response = self.client.post(f'{LAB}/{self.essay.pk}/tabs/{self.tab.pk}/duplicate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        copy_tab = EssayTab.objects.get(pk=response.data['tab']['id'])
        self.assertEqual(self.feedback_marks(copy_tab.doc), set())
        self.assertEqual(doc_stats(copy_tab.doc).content, doc_stats(BASE_DOC).content,
                         'pending insertions go, the words proposed for deletion stay')
        response = self.client.post(f'{LAB}/{self.essay.pk}/duplicate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        for tab in EssayTab.objects.filter(essay_id=response.data['id']):
            self.assertEqual(self.feedback_marks(tab.doc), set())
        self.assertNotEqual(self.feedback_marks(self.stored()), set(), 'the original keeps its feedback')

    def test_restoring_a_version_applies_decisions_made_since(self):
        thread = self.comment().data
        first, second = self.make_two()
        with_feedback = EssayCheckpoint.objects.filter(tab=self.tab).order_by('-id').first()
        self.assertEqual(self.decide([{'id': first['id'], 'accept': True}, {'id': second['id'], 'accept': False}]).status_code,
                         status.HTTP_200_OK)
        EssayCommentThread.objects.filter(pk=thread['id']).delete()
        self.tab.refresh_from_db()
        self.as_user(self.student_user)
        response = self.client.post(f'{LAB}/{self.essay.pk}/checkpoints/{with_feedback.pk}/restore/',
                                    {'base_seq': self.tab.save_seq}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        restored = self.stored()
        self.assertEqual(self.feedback_marks(restored), set())
        self.assertIn('My nana never wasted bread.', doc_stats(restored).content)
        self.assertNotIn('again', doc_stats(restored).content)

    def test_restoring_keeps_feedback_that_is_still_open(self):
        first, _second = self.make_two()
        with_feedback = EssayCheckpoint.objects.filter(tab=self.tab).order_by('-id').first()
        self.tab.refresh_from_db()
        self.as_user(self.student_user)
        response = self.client.post(f'{LAB}/{self.essay.pk}/checkpoints/{with_feedback.pk}/restore/',
                                    {'base_seq': self.tab.save_seq}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn(first['id'], mark_ids(self.stored(), 'suggestInsert'))
        self.assertEqual(self.decide([{'id': first['id'], 'accept': True}]).status_code, status.HTTP_200_OK)

    def test_feedback_versions_are_pruned_before_the_students_own(self):
        from .essay_lab.writes import CHECKPOINT_CAP, prune_checkpoints
        own = EssayCheckpoint.objects.create(essay=self.essay, tab=self.tab, doc=BASE_DOC, content='x',
                                             reason=EssayCheckpoint.Reason.AUTO)
        EssayCheckpoint.objects.bulk_create([
            EssayCheckpoint(essay=self.essay, tab=self.tab, doc=BASE_DOC, content='x', reason=EssayCheckpoint.Reason.AUTO,
                            kind=EssayCheckpoint.Kind.COMMENT, author=self.counselor)
            for _ in range(CHECKPOINT_CAP)
        ])
        prune_checkpoints(self.essay.pk)
        self.assertTrue(EssayCheckpoint.objects.filter(pk=own.pk).exists())
        self.assertEqual(EssayCheckpoint.objects.filter(essay=self.essay).count(), CHECKPOINT_CAP)

    def test_counselors_who_lost_access_hear_nothing(self):
        thread = self.comment().data
        self.as_user(self.student_user)
        self.client.post(f'{LAB}/{self.essay.pk}/unshare/')
        before = Notification.objects.filter(recipient=self.counselor).count()
        response = self.client.post(f'{LAB}/{self.essay.pk}/threads/{thread["id"]}/reply/', {'body': 'Thanks!'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.client.post(f'{LAB}/{self.essay.pk}/threads/{thread["id"]}/resolve/')
        self.assertEqual(Notification.objects.filter(recipient=self.counselor).count(), before)
        self.client.post(f'{LAB}/{self.essay.pk}/share/', {}, format='json')
        self.client.post(f'{LAB}/{self.essay.pk}/threads/{thread["id"]}/reopen/')
        self.client.post(f'{LAB}/{self.essay.pk}/threads/{thread["id"]}/reply/', {'body': 'One more'}, format='json')
        self.assertEqual(Notification.objects.filter(recipient=self.counselor, title='New reply to your comment').count(), 1)
