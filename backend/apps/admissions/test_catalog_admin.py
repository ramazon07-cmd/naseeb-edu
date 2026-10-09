"""The admin catalogue editor (/api/catalog/...): who reads, who writes, and what a write may not break."""
from rest_framework.test import APITestCase

from apps.admissions.models import Application, OpportunityProgram, Scholarship, University, UniversityProgram
from apps.admissions.test_audit_base import AuditBaseMixin
from apps.users.models import ProductAuditEvent, User

UNIVERSITIES = '/api/catalog/universities/'
PROGRAMS = '/api/catalog/programs/'
SCHOLARSHIPS = '/api/catalog/scholarships/'
OPPORTUNITIES = '/api/catalog/opportunity-programs/'


class CatalogAdminTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.ops = self.make_user('base-ops', User.Role.ADMIN, None, admin_tier=User.AdminTier.OPS)
        self.support = self.make_user('base-support', User.Role.ADMIN, None, admin_tier=User.AdminTier.SUPPORT)
        self.university = University.objects.create(name='Lakeside University', country='Canada', city='Toronto')
        self.scholarship = Scholarship.objects.create(title='Global Merit Award', provider='Lakeside', scholarship_type='merit')
        self.program = OpportunityProgram.objects.create(
            title='Summer Research Lab', provider='Lakeside', program_type='international', category='Research', source_key='lab-1',
        )

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def test_every_product_admin_reads_the_whole_catalogue_hidden_rows_too(self):
        Scholarship.objects.create(title='Retired Award', provider='Old Fund', scholarship_type='merit', is_active=False)
        response = self.as_user(self.support).get(SCHOLARSHIPS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['title'] for row in self.results(response)}, {'Global Merit Award', 'Retired Award'})
        hidden = self.as_user(self.support).get(f'{SCHOLARSHIPS}?is_active=false')
        self.assertEqual([row['title'] for row in self.results(hidden)], ['Retired Award'])

    def test_support_staff_and_other_roles_cannot_write(self):
        payload = {'name': 'New University', 'country': 'Japan'}
        self.assertEqual(self.as_user(self.support).post(UNIVERSITIES, payload, format='json').status_code, 403)
        for user in (self.counselor, self.teacher, self.organization, self.student_user, self.parent):
            client = self.as_user(user)
            self.assertEqual(client.get(UNIVERSITIES).status_code, 403, user.username)
            self.assertEqual(client.post(UNIVERSITIES, payload, format='json').status_code, 403, user.username)
            self.assertEqual(client.patch(f'{SCHOLARSHIPS}{self.scholarship.id}/', {'is_active': False}, format='json').status_code, 403)
        self.assertFalse(University.objects.filter(name='New University').exists())
        self.scholarship.refresh_from_db()
        self.assertTrue(self.scholarship.is_active)

    def test_ops_staff_create_and_edit_and_every_write_is_audited(self):
        client = self.as_user(self.ops)
        created = client.post(UNIVERSITIES, {'name': 'Harbor Institute', 'country': 'USA', 'net_price_usd': 0, 'sat_min': 1200, 'sat_max': 1400}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['market'], 'us')
        edited = client.patch(f"{UNIVERSITIES}{created.data['id']}/", {'city': 'Boston'}, format='json')
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual(edited.data['applications_count'], 0)
        actions = list(ProductAuditEvent.objects.filter(actor=self.ops).values_list('action', flat=True).order_by('id'))
        self.assertEqual(actions, ['university.created', 'university.updated'])
        # The public, cached catalogue shows the edit at once.
        public = self.as_user(self.student_user).get('/api/universities/')
        self.assertIn('Boston', {row['city'] for row in self.results(public)})

    def test_numbers_must_be_plausible(self):
        client = self.as_user(self.ops)
        reversed_range = client.patch(f'{UNIVERSITIES}{self.university.id}/', {'sat_min': 1500, 'sat_max': 1300}, format='json')
        self.assertEqual(reversed_range.status_code, 400)
        self.assertIn('sat_max', reversed_range.data)
        # Only one end changes: the stored other end still counts.
        University.objects.filter(pk=self.university.pk).update(act_max=30)
        self.assertEqual(client.patch(f'{UNIVERSITIES}{self.university.id}/', {'act_min': 33}, format='json').status_code, 400)
        self.assertEqual(client.patch(f'{UNIVERSITIES}{self.university.id}/', {'acceptance_rate': 120}, format='json').status_code, 400)
        self.assertEqual(client.post(UNIVERSITIES, {'name': 'Lakeside University', 'country': 'Canada'}, format='json').status_code, 400)

    def test_a_university_in_use_is_never_deleted(self):
        client = self.as_user(self.ops)
        Application.objects.create(student=self.student, university=self.university, program='Biology')
        self.assertEqual(client.delete(f'{UNIVERSITIES}{self.university.id}/').status_code, 400)
        linked = University.objects.create(name='Linked College', country='Canada')
        Scholarship.objects.create(title='Linked Award', provider='Linked', scholarship_type='merit', university=linked)
        self.assertEqual(client.delete(f'{UNIVERSITIES}{linked.id}/').status_code, 400)
        self.assertEqual(University.objects.filter(pk__in=[self.university.pk, linked.pk]).count(), 2)

        unused = University.objects.create(name='Typo Universty', country='Canada')
        self.assertEqual(client.delete(f'{UNIVERSITIES}{unused.id}/').status_code, 204)
        self.assertFalse(University.objects.filter(pk=unused.pk).exists())
        self.assertTrue(ProductAuditEvent.objects.filter(action='university.deleted', target_id=str(unused.pk)).exists())

    def test_programs_belong_to_a_university_and_are_unique_there(self):
        client = self.as_user(self.ops)
        payload = {'university': self.university.id, 'name': 'BSc Biology', 'canonical_major': 'Biology'}
        created = client.post(PROGRAMS, payload, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['university_name'], 'Lakeside University')
        self.assertEqual(client.post(PROGRAMS, payload, format='json').status_code, 400)
        other = University.objects.create(name='Other University', country='Canada')
        UniversityProgram.objects.create(university=other, name='BA History', canonical_major='History')
        mine = client.get(f'{PROGRAMS}?university={self.university.id}')
        self.assertEqual([row['name'] for row in self.results(mine)], ['BSc Biology'])
        self.assertEqual(client.delete(f"{PROGRAMS}{created.data['id']}/").status_code, 204)

    def test_scholarships_and_opportunity_programs_are_hidden_never_deleted(self):
        client = self.as_user(self.ops)
        self.assertEqual(client.delete(f'{SCHOLARSHIPS}{self.scholarship.id}/').status_code, 405)
        self.assertEqual(client.delete(f'{OPPORTUNITIES}{self.program.id}/').status_code, 405)
        hidden = client.patch(f'{SCHOLARSHIPS}{self.scholarship.id}/', {'is_active': False}, format='json')
        self.assertEqual(hidden.status_code, 200, hidden.data)
        public = self.as_user(self.student_user).get('/api/scholarships/')
        self.assertNotIn(self.scholarship.id, {row['id'] for row in self.results(public)})

    def test_the_importer_key_of_an_opportunity_program_is_read_only(self):
        response = self.as_user(self.ops).patch(
            f'{OPPORTUNITIES}{self.program.id}/', {'source_key': 'hijacked', 'deadline_text': 'Every March'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.program.refresh_from_db()
        self.assertEqual((self.program.source_key, self.program.deadline_text), ('lab-1', 'Every March'))

    def test_search_narrows_each_list(self):
        University.objects.create(name='Mountain College', country='Switzerland', city='Zurich')
        response = self.as_user(self.support).get(f'{UNIVERSITIES}?search=zurich')
        self.assertEqual([row['name'] for row in self.results(response)], ['Mountain College'])

    def test_country_edit_clears_a_market_that_no_longer_applies(self):
        response = self.as_user(self.ops).patch(
            f'{UNIVERSITIES}{self.university.id}/', {'country': 'Japan'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['market'], '')
        self.university.refresh_from_db()
        self.assertEqual(self.university.market, '')

    def test_university_deletion_does_not_silently_delete_its_programs(self):
        program = UniversityProgram.objects.create(university=self.university, name='Biology', canonical_major='Biology')
        client = self.as_user(self.ops)
        detail = client.get(f'{UNIVERSITIES}{self.university.id}/')
        self.assertEqual(detail.data['programs_count'], 1)
        self.assertEqual(detail.data['scholarships_count'], 0)
        self.assertEqual(client.delete(f'{UNIVERSITIES}{self.university.id}/').status_code, 400)
        self.assertTrue(UniversityProgram.objects.filter(pk=program.pk).exists())

    def test_opportunity_dates_cannot_be_reversed_even_on_partial_edit(self):
        client = self.as_user(self.ops)
        url = f'{OPPORTUNITIES}{self.program.id}/'
        response = client.patch(url, {'start_date': '2027-06-01', 'end_date': '2027-05-01'}, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('end_date', response.data)
        self.assertEqual(client.patch(url, {'start_date': '2027-06-01', 'end_date': '2027-07-01'}, format='json').status_code, 200)
        self.assertEqual(client.patch(url, {'end_date': '2027-05-01'}, format='json').status_code, 400)
