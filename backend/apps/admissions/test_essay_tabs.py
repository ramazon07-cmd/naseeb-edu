"""Essay Lab document tabs: the tabs API, per-tab saving/history/Coach, and the derived essay text."""

from unittest import mock

from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory, TransactionTestCase
from rest_framework import status

from apps.users.models import User

from .essay_lab import coach
from .essay_lab import views as essay_lab_views
from .essay_lab.doc import doc_from_text, doc_hash
from .essay_lab.tabs import MAX_TABS
from .models import Essay, EssayCheckpoint, EssayDepthCheck, EssayTab
from .test_essay_lab import BASE, EssayLabTestCase, StatementCountMixin, make_doc


class TabTestCase(EssayLabTestCase):
    def setUp(self):
        super().setUp()
        self.essay = self.make_essay(content='First tab text.')
        self.first = self.tab_of(self.essay)

    def url(self, suffix=''):
        return f'{BASE}/essays/{self.essay.pk}/{suffix}'

    def add_tab(self, **body):
        response = self.client.post(self.url('tabs/'), body, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data['tab']

    def save_tab(self, tab_id, doc, base_seq=0, save_id=None):
        return self.client.put(self.url('autosave/'), {
            'doc': doc, 'base_seq': base_seq, 'client_save_id': save_id or f'save-{tab_id}-{base_seq}', 'tab': tab_id,
        }, format='json')


class TabManagementTests(TabTestCase):
    def test_add_tabs_and_sub_tabs_in_order(self):
        second = self.add_tab(title='UniList')
        self.assertEqual((second['title'], second['parent'], second['position']), ('UniList', None, 1))
        self.assertEqual(second['doc'], {'type': 'doc', 'content': [{'type': 'paragraph'}]})
        untitled = self.add_tab()
        self.assertEqual(untitled['title'], 'Tab 3')
        response = self.client.post(self.url('tabs/'), {'title': 'Autobiography', 'parent': self.first.pk},
                                    format='json')
        child = response.data['tab']
        self.assertEqual(child['parent'], self.first.pk)
        # Reading order: every parent followed by its sub-tabs.
        self.assertEqual([tab['id'] for tab in response.data['tabs']],
                         [self.first.pk, child['id'], second['id'], untitled['id']])

    def test_sub_tabs_are_one_level_deep_and_parents_must_be_in_the_document(self):
        child = self.add_tab(parent=self.first.pk)
        response = self.client.post(self.url('tabs/'), {'parent': child['id']}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (400, 'nesting_limit'))
        foreign = self.make_essay(student=self.other_student)
        foreign_tab = self.tab_of(foreign)
        response = self.client.post(self.url('tabs/'), {'parent': foreign_tab.pk}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (400, 'invalid_tab'))
        mine = self.make_essay(title='Another of mine')
        response = self.client.post(self.url('tabs/'), {'parent': self.tab_of(mine).pk}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (400, 'invalid_tab'))

    def test_tab_cap(self):
        EssayTab.objects.bulk_create([
            EssayTab(essay=self.essay, title=f'T{index}', position=index + 1) for index in range(MAX_TABS - 1)
        ])
        response = self.client.post(self.url('tabs/'), {}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (409, 'too_many_tabs'))
        response = self.client.post(self.url(f'tabs/{self.first.pk}/duplicate/'), format='json')
        self.assertEqual((response.status_code, response.data['code']), (409, 'too_many_tabs'))

    def test_title_limits(self):
        response = self.client.post(self.url('tabs/'), {'title': 'x' * 101}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.patch(self.url(f'tabs/{self.first.pk}/'), {'title': ''}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rename_updates_the_derived_text(self):
        second = self.add_tab(title='Notes')
        self.save_tab(second['id'], make_doc('Some notes.'))
        response = self.client.patch(self.url(f'tabs/{second["id"]}/'), {'title': 'Ideas'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['title'], 'Ideas')
        self.essay.refresh_from_db()
        self.assertEqual(self.essay.content, 'Tab 1\n\nFirst tab text.\n\nIdeas\n\nSome notes.')

    def test_delete_takes_sub_tabs_and_keeps_the_last_tab(self):
        child = self.add_tab(parent=self.first.pk, title='Child')
        second = self.add_tab(title='Second')
        self.save_tab(child['id'], make_doc('Child text.'))
        response = self.client.delete(self.url(f'tabs/{self.first.pk}/'))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual([tab['id'] for tab in response.data['tabs']], [second['id']])
        self.assertFalse(EssayTab.objects.filter(pk__in=[self.first.pk, child['id']]).exists())
        self.assertFalse(EssayCheckpoint.objects.filter(tab_id=child['id']).exists())
        response = self.client.delete(self.url(f'tabs/{second["id"]}/'))
        self.assertEqual((response.status_code, response.data['code']), (409, 'last_tab'))
        self.essay.refresh_from_db()
        self.assertEqual((self.essay.content, self.essay.word_count), ('', 0))

    def test_duplicate_copies_the_tab_and_its_sub_tabs_right_after_it(self):
        child = self.add_tab(parent=self.first.pk, title='Child')
        second = self.add_tab(title='Second')
        self.save_tab(child['id'], make_doc('Child text.'))
        response = self.client.post(self.url(f'tabs/{self.first.pk}/duplicate/'), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        copy = response.data['tab']
        self.assertEqual(copy['title'], 'Tab 1 (copy)')
        self.assertEqual(copy['doc'], doc_from_text('First tab text.'))
        titles = [(tab['title'], tab['parent']) for tab in response.data['tabs']]
        self.assertEqual(titles, [
            ('Tab 1', None), ('Child', self.first.pk), ('Tab 1 (copy)', None), ('Child', copy['id']),
            ('Second', None),
        ])
        copied_child = EssayTab.objects.get(parent_id=copy['id'])
        self.assertEqual((copied_child.content, copied_child.save_seq), ('Child text.', 0))
        self.assertEqual(EssayTab.objects.get(pk=second['id']).position, 2)

    def test_reorder_siblings(self):
        second = self.add_tab(title='Second')
        third = self.add_tab(title='Third')
        response = self.client.put(self.url('tabs/order/'), {'parent': None,
                                                             'ids': [third['id'], self.first.pk, second['id']]},
                                   format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual([tab['title'] for tab in response.data['tabs']], ['Third', 'Tab 1', 'Second'])
        self.essay.refresh_from_db()
        self.assertTrue(self.essay.content.startswith('Third\n\nTab 1\n\nFirst tab text.'))
        for ids in ([third['id'], self.first.pk], [third['id'], self.first.pk, second['id'], second['id']], []):
            response = self.client.put(self.url('tabs/order/'), {'parent': None, 'ids': ids}, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_students_tabs_are_404(self):
        foreign = self.make_essay(student=self.other_student, title='Theirs')
        tab = self.tab_of(foreign)
        for method, url, body in (
            ('get', f'{BASE}/essays/{foreign.pk}/tabs/{tab.pk}/', None),
            ('patch', f'{BASE}/essays/{foreign.pk}/tabs/{tab.pk}/', {'title': 'Mine'}),
            ('delete', f'{BASE}/essays/{foreign.pk}/tabs/{tab.pk}/', None),
            ('post', f'{BASE}/essays/{foreign.pk}/tabs/', {}),
            ('post', f'{BASE}/essays/{foreign.pk}/tabs/{tab.pk}/duplicate/', None),
            # Someone else's tab id under my own essay.
            ('get', self.url(f'tabs/{tab.pk}/'), None),
            ('patch', self.url(f'tabs/{tab.pk}/'), {'title': 'Mine'}),
            ('delete', self.url(f'tabs/{tab.pk}/'), None),
            ('put', self.url('autosave/'), {'doc': make_doc('x'), 'base_seq': 0, 'client_save_id': 'x', 'tab': tab.pk}),
            ('get', self.url(f'checkpoints/?tab={tab.pk}'), None),
            ('post', self.url('depth-check/'), {'base_seq': 0, 'tab': tab.pk}),
        ):
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)
        tab.refresh_from_db()
        self.assertEqual((tab.title, tab.content), ('Tab 1', foreign.content))


class TabTextTests(TabTestCase):
    def test_one_tab_reads_exactly_like_before(self):
        self.save_tab(self.first.pk, make_doc('Just one tab.'))
        self.essay.refresh_from_db()
        self.assertEqual((self.essay.content, self.essay.word_count, self.essay.preview),
                         ('Just one tab.', 3, 'Just one tab.'))

    def test_several_tabs_derive_titled_text_in_reading_order(self):
        second = self.add_tab(title='UniList')
        child = self.add_tab(title='Reach', parent=self.first.pk)
        self.save_tab(second['id'], make_doc('MIT and NUS.'))
        self.save_tab(child['id'], make_doc('Stanford.'))
        self.essay.refresh_from_db()
        self.assertEqual(self.essay.content,
                         'Tab 1\n\nFirst tab text.\n\nReach\n\nStanford.\n\nUniList\n\nMIT and NUS.')
        self.assertEqual(self.essay.word_count, 3 + 1 + 3)
        self.assertEqual(self.essay.preview, 'First tab text. Stanford. MIT and NUS.')
        # The counselor-facing legacy API and the library search read the combined text.
        self.assertEqual([item['id'] for item in self.client.get(f'{BASE}/essays/', {'q': 'Stanford'}).data],
                         [self.essay.pk])

    def titled_document(self):
        second = self.add_tab(title='Many title words here')
        self.save_tab(second['id'], make_doc('MIT and NUS.'))
        self.essay.refresh_from_db()
        self.assertEqual((self.essay.word_count, self.essay.preview), (6, 'First tab text. MIT and NUS.'))
        return self.essay

    def assert_tab_counts(self, essay):
        essay.refresh_from_db()
        self.assertEqual((essay.word_count, essay.preview), (6, 'First tab text. MIT and NUS.'))

    def test_duplicating_keeps_the_counts_of_the_tabs_not_their_titles(self):
        self.titled_document()
        response = self.client.post(self.url('duplicate/'), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        copy = Essay.objects.get(pk=response.data['id'])
        self.assert_tab_counts(copy)
        self.assertEqual(copy.content, Essay.objects.get(pk=self.essay.pk).content)

    def test_saves_that_leave_the_text_alone_keep_the_tab_counts(self):
        essay = self.titled_document()
        essay.shared_with_counselor = True
        essay.save()  # admin and other full saves
        self.assert_tab_counts(essay)
        self.client.force_authenticate(self.counselor)
        response = self.client.patch(f'/api/essays/{essay.pk}/', {'status': Essay.Status.NEEDS_REVISION},
                                     format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assert_tab_counts(essay)
        detail = self.client.get(f'/api/essays/{essay.pk}/').data
        response = self.client.put(f'/api/essays/{essay.pk}/', {
            key: detail[key] for key in ('student', 'title', 'prompt', 'content', 'status')
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assert_tab_counts(essay)

    def test_admin_cannot_edit_the_derived_text_of_a_document(self):
        essay = self.titled_document()
        request = RequestFactory().get('/admin/')
        request.user = User.objects.create_superuser('lab-root', 'lab-root@example.com', 'StrongPass123!')
        essay_admin = admin.site._registry[Essay]
        fields = essay_admin.get_form(request, essay).base_fields
        self.assertFalse({'content', 'word_count', 'preview'} & fields.keys())
        # A new essay has no tabs yet: its text is typed here and becomes the first tab.
        fields = essay_admin.get_form(request, None).base_fields
        self.assertIn('content', fields)
        self.assertFalse({'word_count', 'preview'} & fields.keys())

    def test_a_plain_text_save_still_counts_the_text(self):
        essay = Essay.objects.create(student=self.student, title='Seeded', prompt='', content='One two three.')
        self.assertEqual((essay.word_count, essay.preview), (3, 'One two three.'))
        essay = Essay.objects.get(pk=essay.pk)
        essay.content = 'Now four words here.'
        essay.save()
        essay.refresh_from_db()
        self.assertEqual((essay.word_count, essay.preview), (4, 'Now four words here.'))

    def test_counts_per_tab(self):
        response = self.save_tab(self.first.pk, {'type': 'doc', 'content': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Two words'}, {'type': 'hardBreak'},
                                              {'type': 'text', 'text': 'and three'}]},
        ]})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data['word_count'], response.data['char_count'],
                          response.data['char_count_no_spaces']), (4, 18, 16))
        tab = self.tab_of(self.essay)
        self.assertEqual((tab.word_count, tab.char_count, tab.char_count_no_spaces), (4, 18, 16))


class TabSavingTests(TabTestCase):
    def test_each_tab_saves_on_its_own_sequence(self):
        second = self.add_tab(title='Second')
        self.assertEqual(self.save_tab(self.first.pk, make_doc('A')).data['save_seq'], 1)
        # The other tab's seq is independent: no conflict.
        response = self.save_tab(second['id'], make_doc('B'))
        self.assertEqual((response.status_code, response.data['save_seq'], response.data['tab']),
                         (200, 1, second['id']))
        stale = self.save_tab(second['id'], make_doc('C'), base_seq=0, save_id='stale')
        self.assertEqual((stale.status_code, stale.data['code'], stale.data['tab']), (409, 'conflict', second['id']))
        self.assertEqual(stale.data['doc'], make_doc('B'))

    def test_a_document_with_several_tabs_needs_the_tab_id(self):
        self.add_tab()
        response = self.client.put(self.url('autosave/'), {'doc': make_doc('x'), 'base_seq': 0,
                                                           'client_save_id': 'no-tab'}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (400, 'tab_required'))

    def test_delta_saves_per_tab(self):
        second = self.add_tab(title='Second')
        self.save_tab(second['id'], make_doc('One.'))
        result = make_doc('One.', 'Two.')
        response = self.client.put(self.url('autosave/'), {
            'ops': [{'at': 1, 'delete': 0, 'insert': [make_doc('Two.')['content'][0]]}],
            'doc_hash': doc_hash(result), 'base_seq': 1, 'client_save_id': 'delta', 'tab': second['id'],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(EssayTab.objects.get(pk=second['id']).doc, result)
        self.assertEqual(self.tab_of(self.essay).doc, None)

    def test_history_is_per_tab_and_restores_into_its_tab(self):
        second = self.add_tab(title='Second')
        self.save_tab(second['id'], make_doc('Second v1'))
        self.save_tab(self.first.pk, make_doc('First v1'))
        listing = self.client.get(self.url(f'checkpoints/?tab={second["id"]}')).data
        self.assertEqual([item['tab'] for item in listing], [second['id']])
        checkpoint_id = listing[0]['id']
        self.save_tab(second['id'], make_doc('Second v2'), base_seq=1)
        response = self.client.post(self.url(f'checkpoints/{checkpoint_id}/restore/'), {'base_seq': 2},
                                    format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data['id'], response.data['doc']), (second['id'], make_doc('Second v1')))
        self.assertEqual(self.tab_of(self.essay).content, 'First v1')
        manual = self.client.post(self.url('checkpoints/'), {'tab': self.first.pk, 'label': 'Mine'}, format='json')
        self.assertEqual((manual.status_code, manual.data['tab']), (201, self.first.pk))

    def test_coach_checks_the_open_tab(self):
        second = self.add_tab(title='Second')
        self.save_tab(second['id'], make_doc('I learned a lot about myself in that summer.'))
        response = self.client.post(self.url('depth-check/'), {'base_seq': 1, 'tab': second['id']}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['tab'], second['id'])
        check = EssayDepthCheck.objects.get()
        self.assertEqual(check.tab_id, second['id'])
        self.assertEqual(EssayCheckpoint.objects.get(reason='depth_check').tab_id, second['id'])
        latest = self.client.get(self.url(f'depth-check/latest/?tab={self.first.pk}'))
        self.assertEqual(latest.status_code, status.HTTP_204_NO_CONTENT)
        latest = self.client.get(self.url(f'depth-check/latest/?tab={second["id"]}'))
        self.assertEqual(latest.data['id'], check.pk)


    def test_a_tab_deleted_during_the_coach_check_is_a_404(self):
        second = self.add_tab(title='Second')
        self.save_tab(second['id'], make_doc('I learned a lot about myself in that summer.'))
        run_local_check = coach.run_local_check

        def delete_tab_meanwhile(essay, text):
            EssayTab.objects.filter(pk=second['id']).delete()
            return run_local_check(essay, text)

        with mock.patch.object(coach, 'run_local_check', side_effect=delete_tab_meanwhile):
            response = self.client.post(self.url('depth-check/'), {'base_seq': 1, 'tab': second['id']},
                                        format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)
        self.assertFalse(EssayDepthCheck.objects.exists())
        self.assertFalse(EssayCheckpoint.objects.filter(reason='depth_check').exists())


class TabLoadingTests(TabTestCase):
    def test_detail_returns_every_tabs_metadata_and_only_the_open_tabs_doc(self):
        second = self.add_tab(title='Second')
        self.save_tab(second['id'], make_doc('Second text'))
        data = self.client.get(self.url()).data
        self.assertEqual([tab['title'] for tab in data['tabs']], ['Tab 1', 'Second'])
        self.assertNotIn('doc', data['tabs'][0])
        self.assertEqual(data['tab']['id'], self.first.pk)
        data = self.client.get(self.url(), {'tab': second['id']}).data
        self.assertEqual(data['tab']['doc'], make_doc('Second text'))
        # A tab deleted elsewhere opens the first tab instead of failing.
        data = self.client.get(self.url(), {'tab': 999999}).data
        self.assertEqual(data['tab']['id'], self.first.pk)
        opened = self.client.get(self.url(f'tabs/{second["id"]}/')).data
        self.assertEqual((opened['doc'], opened['save_seq']), (make_doc('Second text'), 1))

    def test_a_tab_deleted_while_opening_opens_another_tab(self):
        second = self.add_tab(title='Second')
        list_tabs = essay_lab_views._tab_metas
        calls = []

        def delete_after_listing(essay_id):
            metas = list_tabs(essay_id)
            if not calls:
                EssayTab.objects.filter(pk=second['id']).delete()
            calls.append(essay_id)
            return metas

        with mock.patch.object(essay_lab_views, '_tab_metas', side_effect=delete_after_listing):
            response = self.client.get(self.url(), {'tab': second['id']})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data['tab']['id'], [tab['id'] for tab in response.data['tabs']]),
                         (self.first.pk, [self.first.pk]))

    def test_an_essay_made_elsewhere_gets_its_first_tab_on_open(self):
        essay = Essay.objects.create(student=self.student, title='Seeded', prompt='', content='Seeded text.')
        data = self.client.get(f'{BASE}/essays/{essay.pk}/').data
        self.assertEqual((data['tab']['title'], data['tab']['doc']), ('Tab 1', doc_from_text('Seeded text.')))
        self.assertEqual(EssayTab.objects.filter(essay=essay).count(), 1)
        self.client.get(f'{BASE}/essays/{essay.pk}/')
        self.assertEqual(EssayTab.objects.filter(essay=essay).count(), 1)

    def test_duplicating_a_document_copies_every_tab(self):
        child = self.add_tab(parent=self.first.pk, title='Child')
        self.save_tab(child['id'], make_doc('Child text.'))
        response = self.client.post(self.url('duplicate/'), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual([(tab['title'], tab['parent'] is None) for tab in response.data['tabs']],
                         [('Tab 1', True), ('Child', False)])
        copy = Essay.objects.get(pk=response.data['id'])
        self.assertEqual(copy.content, self.essay.__class__.objects.get(pk=self.essay.pk).content)

    def test_page_setup_is_stored_per_document(self):
        response = self.client.patch(self.url(), {'page_size': 'letter'}, format='json')
        self.assertEqual((response.status_code, response.data['page_size']), (200, 'letter'))
        response = self.client.patch(self.url(), {'page_size': 'a3'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TabQueryBudgetTests(StatementCountMixin, TabTestCase):
    def test_opening_a_document_is_three_queries_whatever_its_size(self):
        big = make_doc(*[f'Paragraph {index} ' * 40 for index in range(40)])
        EssayTab.objects.bulk_create([
            EssayTab(essay=self.essay, title=f'T{index}', position=index + 1, doc=big, content='x')
            for index in range(30)
        ])
        with self.assertNumQueries(3):  # essay, tabs' metadata, the open tab
            response = self.client.get(self.url())
        self.assertEqual(len(response.data['tabs']), 31)
        # The other tabs' docs are never read: the response stays small.
        self.assertLess(len(response.content), 20_000)
        with self.assertNumQueries(2):  # essay, the tab
            self.client.get(self.url(f'tabs/{self.first.pk}/'))


class LegacyApiWithTabsTests(TabTestCase):
    def make_essay(self, student=None, **fields):
        # Counselor edits need an essay the student shared.
        fields.setdefault('shared_with_counselor', True)
        return super().make_essay(student, **fields)

    def test_plain_text_edits_replace_a_one_tab_document(self):
        self.save_tab(self.first.pk, make_doc('Rich text'))
        self.client.force_authenticate(self.counselor)
        response = self.client.patch(f'/api/essays/{self.essay.pk}/', {'content': 'Counselor fixed it.'},
                                     format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        tab = self.tab_of(self.essay)
        self.assertEqual((tab.doc, tab.content, tab.save_seq, tab.word_count), (None, 'Counselor fixed it.', 2, 3))

    def test_plain_text_edits_are_refused_for_a_document_with_tabs(self):
        self.add_tab(title='Second')
        self.client.force_authenticate(self.counselor)
        response = self.client.patch(f'/api/essays/{self.essay.pk}/', {'content': 'Overwrite everything.'},
                                     format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(EssayTab.objects.filter(essay=self.essay).count(), 2)
        # Comments still work.
        response = self.client.patch(f'/api/essays/{self.essay.pk}/', {'counselor_comment': 'Lovely.'},
                                     format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_legacy_create_makes_the_first_tab(self):
        response = self.client.post('/api/essays/', {
            'student': self.student.pk, 'title': 'New', 'prompt': '', 'content': 'Three small words',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        tab = EssayTab.objects.get(essay_id=response.data['id'])
        self.assertEqual((tab.title, tab.content, tab.word_count), ('Tab 1', 'Three small words', 3))


class TabMigrationTests(TransactionTestCase):
    migrate_from = [('admissions', '0051_files_activity_proof_file')]
    migrate_to = [('admissions', '0053_tabs_essay_tabs_required')]

    def tearDown(self):
        from django.db.migrations.executor import MigrationExecutor

        # Leave the schema at the latest migration for the tests that follow.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        cache.clear()

    def test_every_essay_becomes_one_tab_and_back(self):
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old = executor.loader.project_state(self.migrate_from).apps
        School, User = old.get_model('admissions', 'School'), old.get_model('users', 'User')
        Profile, OldEssay = old.get_model('admissions', 'StudentProfile'), old.get_model('admissions', 'Essay')
        Checkpoint = old.get_model('admissions', 'EssayCheckpoint')
        school = School.objects.create(name='Tabs school', code='tabs-school')
        student = Profile.objects.create(
            user=User.objects.create(username='tabs-student', email='tabs@example.com', role='student', school=school),
            school=school,
        )
        rich = OldEssay.objects.create(student=student, title='Rich', prompt='', content='Hello world.',
                                       doc=make_doc('Hello world.'), save_seq=7, word_count=2, last_cursor=4)
        plain = OldEssay.objects.create(student=student, title='Plain', prompt='', content='Old text only.',
                                        word_count=3)
        Checkpoint.objects.create(essay=rich, doc=make_doc('Hello'), content='Hello', word_count=1)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        new = executor.loader.project_state(self.migrate_to).apps
        Tab = new.get_model('admissions', 'EssayTab')
        rich_tab = Tab.objects.get(essay_id=rich.pk)
        self.assertEqual((rich_tab.title, rich_tab.doc, rich_tab.content, rich_tab.save_seq, rich_tab.last_cursor,
                          rich_tab.word_count, rich_tab.char_count, rich_tab.char_count_no_spaces),
                         ('Tab 1', make_doc('Hello world.'), 'Hello world.', 7, 4, 2, 12, 11))
        plain_tab = Tab.objects.get(essay_id=plain.pk)
        self.assertEqual((plain_tab.doc, plain_tab.content), (None, 'Old text only.'))
        self.assertEqual(new.get_model('admissions', 'EssayCheckpoint').objects.get().tab_id, rich_tab.pk)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_from)
        back = executor.loader.project_state(self.migrate_from).apps.get_model('admissions', 'Essay').objects.get(
            pk=rich.pk)
        self.assertEqual((back.doc, back.save_seq, back.last_cursor), (make_doc('Hello world.'), 7, 4))
