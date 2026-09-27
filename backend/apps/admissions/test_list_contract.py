"""The shared list contract: pagination modes, search, filters and ordering."""
import base64
import json
from datetime import date, timedelta
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.admissions.listing import ListQueryMixin
from apps.admissions.models import Application, Document, Essay, StudentProfile, SupportTicket, Task, University
from apps.admissions.urls import router as admissions_router
from apps.users.models import User
from apps.users.urls import router as users_router
from core.pagination import ListPagination

from .test_audit_base import AuditBaseMixin


def walk(client, url):
    """Follow ``next`` links from ``url``; return (ids, pages)."""
    ids, pages = [], 0
    while url:
        response = client.get(url)
        assert response.status_code == 200, response.data
        pages += 1
        ids.extend(row['id'] for row in response.data['results'])
        url = response.data['next']
    return ids, pages


class ListContractMixin(AuditBaseMixin):
    def add_tasks(self, student, count, *, start=0, due=None):
        base = due or date(2027, 1, 1)
        return Task.objects.bulk_create([
            Task(student=student, title=f'Task {start + index:04d}', due_date=base + timedelta(days=(start + index) % 7))
            for index in range(count)
        ])

    def add_students(self, school, counselor, count, *, prefix='Student'):
        users = User.objects.bulk_create([
            User(
                username=f'{prefix.lower()}-{school.pk}-{index}', email=f'{prefix.lower()}-{school.pk}-{index}@example.com',
                first_name=f'{prefix}{index:05d}', last_name='Test', role=User.Role.STUDENT, school=school,
            )
            for index in range(count)
        ])
        return StudentProfile.objects.bulk_create([
            StudentProfile(user=user, school=school, school_name=school.name, assigned_counselor=counselor)
            for user in users
        ])


class KeysetPaginationTests(ListContractMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.counselor)

    def test_page_number_shape_is_unchanged(self):
        self.add_tasks(self.student, 30)
        response = self.client.get('/api/tasks/?page_size=10')
        self.assertEqual(set(response.data), {'count', 'next', 'previous', 'results'})
        self.assertEqual(response.data['count'], 30)
        self.assertEqual(len(response.data['results']), 10)

    def test_cursor_walk_returns_every_row_once_in_order(self):
        self.add_tasks(self.student, 57)
        ids, pages = walk(self.client, '/api/tasks/?cursor=&page_size=10')
        expected = list(Task.objects.filter(student=self.student).order_by('due_date', 'id').values_list('id', flat=True))
        self.assertEqual(ids, expected)
        self.assertEqual(pages, 6)

    def test_cursor_response_has_no_count(self):
        self.add_tasks(self.student, 12)
        with CaptureQueriesContext(connection) as context:
            response = self.client.get('/api/tasks/?cursor=&page_size=5')
        self.assertEqual(set(response.data), {'results', 'next', 'has_more'})
        self.assertTrue(response.data['has_more'])
        self.assertFalse(any('COUNT(' in query['sql'].upper() for query in context.captured_queries))

    def test_last_page_has_no_next(self):
        self.add_tasks(self.student, 5)
        response = self.client.get('/api/tasks/?cursor=&page_size=5')
        self.assertIsNone(response.data['next'])
        self.assertFalse(response.data['has_more'])

    def test_inserts_during_a_walk_cause_no_duplicates_or_skips(self):
        originals = {task.id for task in self.add_tasks(self.student, 40)}
        for ordering in ('-created', 'due', '-updated'):
            with self.subTest(ordering=ordering):
                seen = []
                url = f'/api/tasks/?cursor=&page_size=7&ordering={ordering}'
                inserted = False
                while url:
                    response = self.client.get(url)
                    seen.extend(row['id'] for row in response.data['results'])
                    url = response.data['next']
                    if not inserted:
                        # New rows land before, inside and after the cursor position.
                        self.add_tasks(self.student, 9, start=500)
                        inserted = True
                self.assertEqual(len(seen), len(set(seen)), 'duplicate rows')
                self.assertTrue(originals <= set(seen), 'skipped rows')

    def test_ties_are_broken_by_id(self):
        # Same due date for every row: only the id keeps the order total.
        Task.objects.bulk_create([Task(student=self.student, title='Same', due_date=date(2027, 5, 5)) for _ in range(23)])
        ids, _ = walk(self.client, '/api/tasks/?cursor=&page_size=4')
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), 23)

    def test_descending_datetime_cursor(self):
        tickets = [
            SupportTicket.objects.create(requester=self.counselor, category='technical', subject=f'S{index}', message='m')
            for index in range(9)
        ]
        ids, _ = walk(self.client, '/api/support-tickets/?cursor=&page_size=2')
        self.assertEqual(ids, [ticket.id for ticket in reversed(tickets)])

    def test_bad_cursors_are_400(self):
        self.add_tasks(self.student, 6)
        good = self.client.get('/api/tasks/?cursor=&page_size=2').data['next']
        cursor = good.split('cursor=')[1].split('&')[0]
        other_ordering = f'/api/tasks/?cursor={cursor}&ordering=-created'

        def forged(values, ordering='due_date,id'):
            payload = json.dumps({'o': ordering, 'v': values}).encode()
            return base64.urlsafe_b64encode(payload).decode().rstrip('=')

        for url in (
            '/api/tasks/?cursor=not-base64!!',
            '/api/tasks/?cursor=' + base64.urlsafe_b64encode(b'[1,2]').decode(),
            other_ordering,
            '/api/tasks/?cursor=' + forged(['2027-01-01']),
            '/api/tasks/?cursor=' + forged(['not-a-date', 5]),
            '/api/tasks/?cursor=' + forged([{'a': 1}, 5]),
            '/api/tasks/?cursor=' + forged(['2027-01-01', 2 ** 70]),
            '/api/tasks/?cursor=' + forged(['2027-01-01', True]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 400)

    def test_cursor_pages_cost_the_same_at_any_depth(self):
        self.add_tasks(self.student, 60)
        first, response = self.get_counted('/api/tasks/?cursor=&page_size=10')
        url = response.data['next']
        for _ in range(3):
            url = self.client.get(url).data['next']
        deep, _ = self.get_counted(url)
        self.assertEqual(first, deep)
        with CaptureQueriesContext(connection) as context:
            self.client.get(url)
        self.assertFalse(any('OFFSET' in query['sql'].upper() for query in context.captured_queries))

    def test_every_list_endpoint_accepts_a_cursor(self):
        self.client.force_authenticate(self.admin)
        routes = [
            (prefix, viewset) for prefix, viewset, _ in admissions_router.registry
        ] + [(f'users/{prefix}', viewset) for prefix, viewset, _ in users_router.registry]
        for prefix, viewset in routes:
            if viewset.pagination_class is not ListPagination:
                continue
            with self.subTest(route=prefix):
                response = self.client.get(f'/api/{prefix}/?cursor=&page_size=2')
                if response.status_code == 200 and isinstance(response.data, dict) and 'results' in response.data:
                    self.assertIn('has_more', response.data)


class BoundedCountTests(ListContractMixin, APITestCase):
    def test_small_counts_are_exact_and_uncached(self):
        self.client.force_authenticate(self.counselor)
        self.add_tasks(self.student, 3)
        self.assertEqual(self.client.get('/api/tasks/').data['count'], 3)
        self.add_tasks(self.student, 2, start=10)
        self.assertEqual(self.client.get('/api/tasks/').data['count'], 5)

    def test_large_counts_run_once_per_minute_per_scope(self):
        self.add_tasks(self.student, 12)
        self.add_tasks(self.student_b, 8)
        with mock.patch('core.pagination.EXACT_COUNT_LIMIT', 5):
            self.client.force_authenticate(self.admin)
            cold, response = self.get_counted('/api/tasks/')
            self.assertEqual(response.data['count'], 20)
            warm, response = self.get_counted('/api/tasks/')
            self.assertEqual(response.data['count'], 20)
            self.assertEqual(warm, cold - 1)
            # Another tenant's scope is a different cache entry.
            self.client.force_authenticate(self.counselor)
            self.assertEqual(self.client.get('/api/tasks/').data['count'], 12)


class SearchFilterOrderingTests(ListContractMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.student_user.first_name, self.student_user.last_name = 'Zafar', 'Karimov'
        self.student_user.save()
        self.student_b_user.first_name, self.student_b_user.last_name = 'Zafar', 'Aliyev'
        self.student_b_user.save()

    def names(self, response):
        return sorted(row['user_detail']['full_name'] for row in self.results(response))

    def test_student_search_matches_every_term(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.names(self.client.get('/api/students/?search=zafar')), ['Zafar Aliyev', 'Zafar Karimov'])
        self.assertEqual(self.names(self.client.get('/api/students/?search=zafar%20kari')), ['Zafar Karimov'])
        self.assertEqual(self.names(self.client.get('/api/students/?search=base-student-b')), ['Zafar Aliyev'])

    def test_search_never_widens_the_scope(self):
        for user in (self.counselor, self.organization, self.teacher):
            with self.subTest(role=user.role):
                self.client.force_authenticate(user)
                self.assertEqual(self.names(self.client.get('/api/students/?search=zafar')), ['Zafar Karimov'])
                self.assertEqual(
                    self.results(self.client.get(f'/api/students/?school={self.school_b.id}')), [],
                )

    def test_student_filters(self):
        self.client.force_authenticate(self.admin)
        rows = self.results(self.client.get(f'/api/students/?school={self.school_b.id}'))
        self.assertEqual([row['id'] for row in rows], [self.student_b.id])
        rows = self.results(self.client.get(f'/api/students/?counselor={self.counselor.id}'))
        self.assertEqual([row['id'] for row in rows], [self.student.id])
        self.assertEqual(self.results(self.client.get('/api/students/?unassigned=true')), [])

    def test_task_search_matches_title_or_student_name(self):
        Task.objects.create(student=self.student, title='Write essay', due_date=date(2027, 1, 1))
        Task.objects.create(student=self.student_b, title='Visit campus', due_date=date(2027, 1, 2))
        self.client.force_authenticate(self.admin)
        titles = lambda url: sorted(row['title'] for row in self.results(self.client.get(url)))  # noqa: E731
        self.assertEqual(titles('/api/tasks/?search=essay'), ['Write essay'])
        self.assertEqual(titles('/api/tasks/?search=aliyev'), ['Visit campus'])
        self.assertEqual(titles('/api/tasks/?search=zafar'), ['Visit campus', 'Write essay'])
        self.assertEqual(titles('/api/tasks/?search=zafar%20campus'), ['Visit campus'])

    def test_date_range_and_choice_filters(self):
        Task.objects.create(student=self.student, title='Early', due_date=date(2027, 1, 1), status='submitted')
        Task.objects.create(student=self.student, title='Late', due_date=date(2027, 3, 1))
        self.client.force_authenticate(self.counselor)
        titles = lambda url: [row['title'] for row in self.results(self.client.get(url))]  # noqa: E731
        self.assertEqual(titles('/api/tasks/?due_from=2027-02-01'), ['Late'])
        self.assertEqual(titles('/api/tasks/?due_to=2027-01-01'), ['Early'])
        self.assertEqual(titles('/api/tasks/?status=submitted'), ['Early'])
        today = date.today().isoformat()
        self.assertEqual(len(titles(f'/api/tasks/?created_from={today}&created_to={today}')), 2)
        self.assertEqual(titles('/api/tasks/?created_to=2000-01-01'), [])

    def test_ordering_whitelist(self):
        first = Task.objects.create(student=self.student, title='A', due_date=date(2027, 1, 1))
        second = Task.objects.create(student=self.student, title='B', due_date=date(2026, 1, 1))
        self.client.force_authenticate(self.counselor)
        ids = lambda url: [row['id'] for row in self.results(self.client.get(url))]  # noqa: E731
        self.assertEqual(ids('/api/tasks/?ordering=-created'), [second.id, first.id])
        self.assertEqual(ids('/api/tasks/?ordering=due'), [second.id, first.id])
        self.assertEqual(ids('/api/tasks/?ordering=-due'), [first.id, second.id])

    def test_invalid_parameters_are_400(self):
        self.client.force_authenticate(self.admin)
        for url in (
            '/api/tasks/?status=bogus',
            '/api/tasks/?priority=bogus',
            '/api/tasks/?ordering=title',
            '/api/tasks/?due_from=yesterday',
            '/api/tasks/?due_to=2027-02-31',
            '/api/tasks/?student=abc',
            '/api/tasks/?self_assigned=maybe',
            '/api/students/?grade=13',
            '/api/students/?search=' + 'x' * 101,
            '/api/applications/?deadline_from=2027-13-01',
            '/api/users/accounts/?role=wizard',
            '/api/schools/?is_active=yes',
            '/api/support-tickets/?status=bogus',
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 400)

    def test_keyset_orderings_use_non_null_columns(self):
        views = [viewset for _, viewset, _ in admissions_router.registry + users_router.registry]
        for viewset in views:
            if not issubclass(viewset, ListQueryMixin):
                continue
            model = (viewset.queryset if viewset.queryset is not None else viewset.serializer_class.Meta).model
            for name, terms in viewset.ordering_options.items():
                self.assertIn(terms[-1].lstrip('-'), {'id', 'pk'}, f'{viewset.__name__}.{name}')
                for term in terms:
                    current = model
                    for part in term.lstrip('-').split('__'):
                        field = current._meta.get_field(part)
                        self.assertFalse(field.null, f'{viewset.__name__}.{name}: {term} is nullable')
                        current = field.related_model or current
            if viewset.default_cursor_ordering:
                self.assertIn(viewset.default_cursor_ordering, viewset.ordering_options)


class ListQueryCountTests(ListContractMixin, APITestCase):
    """Cursor pages cost the same whatever the table size."""

    def assert_constant(self, user, url, grow):
        self.client.force_authenticate(user)
        grow(10)
        few, _ = self.get_counted(url)
        grow(20)
        many, response = self.get_counted(url)
        self.assertEqual(few, many, url)
        return many, response

    def test_student_and_record_lists(self):
        university = University.objects.create(name='Count U', country='USA')
        serial = iter(range(10_000))

        def grow(count):
            for profile in self.add_students(self.school_a, self.counselor, count, prefix=f'Grow{next(serial)}'):
                Task.objects.create(student=profile, title='T', due_date=date(2027, 1, 1))
                Application.objects.create(student=profile, university=university, program='CS')
                Document.objects.create(student=profile, title='Passport')
                Essay.objects.create(student=profile, title='Why us')

        for url in (
            '/api/students/?cursor=&page_size=20',
            '/api/students/?cursor=&page_size=20&search=grow',
            '/api/tasks/?cursor=&page_size=20',
            '/api/applications/?cursor=&page_size=20',
            '/api/documents/?cursor=&page_size=20',
            '/api/essays/?cursor=&page_size=20',
        ):
            for user in (self.admin, self.counselor, self.organization):
                with self.subTest(url=url, role=user.role):
                    queries, _ = self.assert_constant(user, url, grow)
                    self.assertLessEqual(queries, 8)


class LargeRosterFirstPageTests(ListContractMixin, APITestCase):
    """A 5,000-student school renders its first screen with a fixed number of LIMITed queries."""

    def test_first_page_of_5000_students(self):
        self.add_students(self.school_a, self.counselor, 50, prefix='Small')
        self.client.force_authenticate(self.organization)
        small, _ = self.get_counted('/api/students/?cursor=&page_size=50')
        self.add_students(self.school_a, self.counselor, 4950, prefix='Big')
        with CaptureQueriesContext(connection) as context:
            response = self.client.get('/api/students/?cursor=&page_size=50')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 50)
        self.assertTrue(response.data['has_more'])
        self.assertEqual(len(context.captured_queries), small)
        profile_table = StudentProfile._meta.db_table
        for query in context.captured_queries:
            sql = query['sql']
            if sql.startswith('SELECT') and f'FROM "{profile_table}"' in sql and 'IN (' not in sql:
                self.assertIn('LIMIT', sql.upper(), sql)
        search, response = self.get_counted('/api/students/?cursor=&page_size=50&search=big0001')
        self.assertEqual(search, small)
        self.assertEqual(len(response.data['results']), 10)


class AssignmentCandidateTests(ListContractMixin, APITestCase):
    def test_candidates_are_searched_on_the_server_and_capped(self):
        from apps.admissions.views.students import ASSIGNMENT_CANDIDATE_LIMIT

        self.add_students(self.school_a, None, ASSIGNMENT_CANDIDATE_LIMIT + 5, prefix='Pool')
        self.client.force_authenticate(self.counselor)
        response = self.client.get('/api/students/assignment-candidates/')
        self.assertEqual(len(response.data), ASSIGNMENT_CANDIDATE_LIMIT)
        names = [row['user_detail']['full_name'] for row in response.data]
        self.assertEqual(names, sorted(names))
        found = self.client.get('/api/students/assignment-candidates/?search=pool00007')
        self.assertEqual([row['user_detail']['full_name'] for row in found.data], ['Pool00007 Test'])
