"""Global header search: top matches per type, scoped exactly like the list endpoints."""
from datetime import date

from rest_framework.test import APITestCase

from apps.admissions.models import Application, SupportTicket, Task, University

from .test_list_contract import ListContractMixin


class GlobalSearchTests(ListContractMixin, APITestCase):
    URL = '/api/search/?q='

    def setUp(self):
        super().setUp()
        for user, last in ((self.student_user, 'Karimov'), (self.student_b_user, 'Aliyev')):
            user.first_name, user.last_name = 'Nodira', last
            user.save()
        Task.objects.create(student=self.student, title='Nodira essay draft', due_date=date(2027, 1, 1))
        Task.objects.create(student=self.student_b, title='Nodira visa', due_date=date(2027, 1, 1))
        university = University.objects.create(name='Nodira Institute', country='UZ')
        Application.objects.create(student=self.student, university=university, program='Law')
        Application.objects.create(student=self.student_b, university=university, program='Law')
        SupportTicket.objects.create(requester=self.counselor_b, category='technical', subject='Nodira login', message='m')

    def search(self, user, query='nodira'):
        self.client.force_authenticate(user)
        response = self.client.get(self.URL + query)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['results']

    def titles(self, results, key):
        return sorted(item['title'] for item in results.get(key, []))

    def test_counselor_sees_only_their_school(self):
        results = self.search(self.counselor)
        self.assertEqual(self.titles(results, 'students'), ['Nodira Karimov'])
        self.assertEqual(self.titles(results, 'tasks'), ['Nodira essay draft'])
        self.assertEqual(len(results['applications']), 1)
        self.assertNotIn('supportTickets', results)
        self.assertNotIn('accounts', results)

    def test_other_school_counselor_sees_only_theirs(self):
        results = self.search(self.counselor_b)
        self.assertEqual(self.titles(results, 'students'), ['Nodira Aliyev'])
        self.assertEqual(self.titles(results, 'tasks'), ['Nodira visa'])
        self.assertEqual(self.titles(results, 'supportTickets'), ['Nodira login'])

    def test_school_roles(self):
        organization = self.search(self.organization)
        self.assertEqual(self.titles(organization, 'students'), ['Nodira Karimov'])
        self.assertEqual(self.titles(organization, 'tasks'), ['Nodira essay draft'])
        teacher = self.search(self.teacher)
        self.assertEqual(self.titles(teacher, 'students'), ['Nodira Karimov'])
        self.assertEqual(self.titles(teacher, 'tasks'), ['Nodira essay draft'])
        self.assertNotIn('applications', teacher)

    def test_student_and_parent(self):
        student = self.search(self.student_user)
        self.assertEqual(self.titles(student, 'tasks'), ['Nodira essay draft'])
        self.assertEqual(self.titles(student, 'students'), ['Nodira Karimov'])
        self.assertEqual(self.search(self.parent), {})

    def test_admin_sees_every_school_and_accounts(self):
        results = self.search(self.admin)
        self.assertEqual(self.titles(results, 'students'), ['Nodira Aliyev', 'Nodira Karimov'])
        self.assertEqual(self.titles(results, 'tasks'), ['Nodira essay draft', 'Nodira visa'])
        self.assertEqual(self.titles(results, 'accounts'), ['Nodira Aliyev', 'Nodira Karimov'])
        self.assertEqual(self.titles(results, 'supportTickets'), ['Nodira login'])

    def test_short_and_long_queries(self):
        self.assertEqual(self.search(self.admin, 'n'), {})
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.URL + 'x' * 101).status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.URL + 'nodira').status_code, 401)

    def test_results_are_capped_and_query_count_is_constant(self):
        self.client.force_authenticate(self.admin)
        few, _ = self.get_counted(self.URL + 'nodira')
        for index in range(12):
            Task.objects.create(student=self.student, title=f'Nodira extra {index}', due_date=date(2027, 1, 1))
        self.add_students(self.school_a, self.counselor, 12, prefix='Nodira')
        many, response = self.get_counted(self.URL + 'nodira')
        self.assertEqual(few, many)
        self.assertLessEqual(many, 12)
        self.assertEqual(len(response.data['results']['tasks']), 5)
        self.assertEqual(len(response.data['results']['students']), 5)

    def test_only_the_roles_search_types_are_queried(self):
        from unittest import mock

        from apps.admissions.views import search

        expected = {
            self.admin: (11, 11), self.counselor: (9, 9), self.organization: (9, 9), self.student_user: (9, 9),
            self.teacher: (4, 4), self.parent: (0, 0),
        }
        for user, (views_built, queries) in expected.items():
            with self.subTest(role=user.role):
                self.client.force_authenticate(user)
                with mock.patch.object(search, 'scoped_list_queryset', wraps=search.scoped_list_queryset) as built:
                    count, _ = self.get_counted(self.URL + 'nodira')
                self.assertEqual((built.call_count, count), (views_built, queries))
                if not user.is_product_admin:
                    basenames = {call.args[1] for call in built.call_args_list}
                    self.assertFalse(basenames & {'schools', 'accounts'})
