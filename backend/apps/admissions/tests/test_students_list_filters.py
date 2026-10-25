"""GET /api/students/: the Students page's status, level, grade and country filters,
its late/progress orderings and GET /api/students/summary/ (pill counts)."""
from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.users.models import User

from ..models import Achievement, Document, RoadmapMission, StudentProfile, Task
from .base import RoleIsolationBase


class StudentListFilterTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.past = timezone.localdate() - timedelta(days=3)
        self.client.force_authenticate(self.counselor)
        # student_a ("Zed") is signed in today: on track, not quiet.
        self.student_a_user.first_name = 'Zed'
        self.student_a_user.last_login = timezone.now()
        self.student_a_user.save()

    def add_student(self, first, school=None, counselor=None, **profile):
        school = school or self.school_a
        number = User.objects.count()
        user = User.objects.create_user(
            username=f'{first}-{number}'.lower(), email=f'{first}{number}@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=school, first_name=first, last_login=timezone.now(),
        )
        return StudentProfile.objects.create(user=user, school=school, assigned_counselor=counselor or self.counselor, **profile)

    def late_task(self, student, n=1):
        for index in range(n):
            Task.objects.create(student=student, title=f'Late {index}', due_date=self.past, status=Task.Status.TODO)

    def missions(self, student, done, total):
        for index in range(total):
            status = RoadmapMission.Status.COMPLETED if index < done else RoadmapMission.Status.PLANNED
            RoadmapMission.objects.create(student=student, title=f'M{index}', status=status)

    def names(self, params, user=None):
        if user:
            self.client.force_authenticate(user)
        response = self.client.get('/api/students/', {'page_size': 100, **params})
        self.assertEqual(response.status_code, 200, response.data)
        return [row['user_detail']['first_name'] for row in self.results(response)]

    def test_status_filters(self):
        late = self.add_student('Lata')
        self.late_task(late)
        mission = self.add_student('Mila')
        RoadmapMission.objects.create(student=mission, title='M', status=RoadmapMission.Status.IN_PROGRESS, due_date=self.past)
        missing = self.add_student('Doc')
        Document.objects.create(student=missing, title='Passport', status=Document.Status.REQUIRED)
        quiet = self.add_student('Quin')
        User.objects.filter(pk=quiet.user_id).update(last_login=timezone.now() - timedelta(days=20))
        review = self.add_student('Rev')
        Achievement.objects.create(student=review, title='Olympiad')
        never = self.add_student('Neve')
        User.objects.filter(pk=never.user_id).update(last_login=None)

        self.assertEqual(sorted(self.names({'status': 'late'})), ['Lata', 'Mila'])
        self.assertEqual(self.names({'status': 'missing_documents'}), ['Doc'])
        self.assertEqual(sorted(self.names({'status': 'need_you'})), ['Doc', 'Lata', 'Mila'])
        self.assertEqual(self.names({'status': 'quiet'}), ['Quin'])
        # Work to review or a quiet spell is not "on track"; never signing in is not quiet.
        self.assertEqual(sorted(self.names({'status': 'on_track'})), ['Neve', 'Zed'])
        self.assertEqual(self.client.get('/api/students/', {'status': 'asleep'}).status_code, 400)

    def test_level_grade_and_country_filters(self):
        self.add_student('Uma', level=3, grade='11', target_countries='UK, US')
        self.add_student('Usa', level=1, grade='11', target_countries='US')
        self.add_student('Hon', level=3, grade='9', target_countries='Hong Kong, China, Canada')
        self.add_student('Tur', level=2, grade='10', target_countries='Turkey, UK')

        self.assertEqual(sorted(self.names({'level': 3})), ['Hon', 'Uma'])
        self.assertEqual(sorted(self.names({'grade': '11'})), ['Uma', 'Usa'])
        self.assertEqual(sorted(self.names({'country': 'US'})), ['Uma', 'Usa'])
        self.assertEqual(sorted(self.names({'country': 'UK'})), ['Tur', 'Uma'])
        self.assertEqual(self.names({'country': 'China'}), ['Hon'])
        self.assertEqual(self.names({'country': 'UK', 'level': 2}), ['Tur'])
        self.assertEqual(self.names({'country': 'Mars'}), [])
        self.assertEqual(self.client.get('/api/students/', {'country': 'US,UK'}).status_code, 400)
        self.assertEqual(self.client.get('/api/students/', {'grade': '13'}).status_code, 400)

    def test_a_student_without_a_class_is_listed_but_matches_no_class_filter(self):
        self.add_student('Uma', grade='11')
        self.add_student('Nia')  # a new login: the class is empty until the student picks it
        self.assertIn('Nia', self.names({}))
        self.assertEqual(self.names({'grade': '11'}), ['Uma'])
        self.assertNotIn('Nia', self.names({'grade': 'gap'}))
        # An empty value means "no class filter", not "no class".
        self.assertIn('Nia', self.names({'grade': ''}))

    def test_country_filter_reads_older_spellings(self):
        # Profiles saved before onboarding's list: "USA", no space after the comma, other countries.
        self.add_student('Old', target_countries='Singapore,Hong Kong,USA')
        self.add_student('Spaced', target_countries='usa , Germany')
        self.add_student('Long', target_countries='United States')
        self.add_student('Russ', target_countries='Russia')
        self.assertEqual(sorted(self.names({'country': 'US'})), ['Long', 'Old', 'Spaced'])
        self.assertEqual(self.names({'country': 'Hong Kong'}), ['Old'])
        self.assertEqual(self.names({'country': 'Germany'}), ['Spaced'])
        self.assertEqual(self.names({'country': 'Singapore'}), ['Old'])
        self.assertEqual(self.names({'country': 'Rus'}), [])
        countries = self.client.get('/api/students/summary/').data['countries']
        # Onboarding's countries first, in its spelling; the rest by name.
        self.assertEqual(countries, ['US', 'Hong Kong', 'Germany', 'Russia', 'Singapore'])

    def test_late_ordering(self):
        two = self.add_student('Two')
        self.late_task(two, 2)
        three = self.add_student('Three')
        self.late_task(three, 1)
        RoadmapMission.objects.create(student=three, title='M', status=RoadmapMission.Status.PLANNED, due_date=self.past)
        RoadmapMission.objects.create(student=three, title='N', status=RoadmapMission.Status.IN_PROGRESS, due_date=self.past)
        self.add_student('Amy')
        self.assertEqual(self.names({'ordering': 'late'}), ['Three', 'Two', 'Amy', 'Zed'])

    def test_progress_ordering(self):
        half = self.add_student('Half')
        self.missions(half, 1, 2)
        third = self.add_student('Third')
        self.missions(third, 1, 3)
        full = self.add_student('Full')
        self.missions(full, 2, 2)
        # No missions is 0%; ties go to the one with more late work, then name.
        empty_late = self.add_student('Yan')
        self.late_task(empty_late)
        response = self.client.get('/api/students/', {'ordering': 'progress', 'page_size': 100})
        rows = self.results(response)
        self.assertEqual([row['user_detail']['first_name'] for row in rows], ['Yan', 'Zed', 'Third', 'Half', 'Full'])
        # The order is the roadmap % the rows show.
        self.assertEqual([row['roadmap_progress_percent'] for row in rows], [0, 0, 33, 50, 100])

    def test_name_ordering_and_page_numbers(self):
        for first in ('Cid', 'Abe', 'Bea'):
            self.add_student(first)
        response = self.client.get('/api/students/', {'ordering': 'name', 'page_size': 2, 'page': 2})
        self.assertEqual(response.data['count'], 4)
        self.assertEqual([row['user_detail']['first_name'] for row in response.data['results']], ['Cid', 'Zed'])

    def test_cursor_pages_follow_new_orderings(self):
        for index in range(7):
            student = self.add_student(f'S{index}')
            self.late_task(student, index % 3)
            self.missions(student, index % 2, 2)
        for ordering in ('late', 'progress'):
            expected = self.names({'ordering': ordering})
            seen, cursor = [], ''
            while True:
                response = self.client.get('/api/students/', {'ordering': ordering, 'cursor': cursor, 'page_size': 3})
                self.assertEqual(response.status_code, 200)
                seen += [row['user_detail']['first_name'] for row in response.data['results']]
                if not response.data['has_more']:
                    break
                cursor = response.data['next'].split('cursor=')[1].split('&')[0]
            self.assertEqual(seen, expected)

    def test_a_document_marked_uploaded_with_nothing_attached_is_missing_not_to_review(self):
        empty = self.add_student('Empty')
        Document.objects.create(student=empty, title='Passport', status=Document.Status.UPLOADED)
        linked = self.add_student('Linked')
        Document.objects.create(student=linked, title='Passport', status=Document.Status.REVIEWING,
                                google_docs_url='https://docs.google.com/document/d/x')
        self.assertEqual(self.names({'status': 'missing_documents'}), ['Empty'])
        self.assertEqual(self.names({'status': 'need_you'}), ['Empty'])
        self.assertEqual(sorted(self.names({'status': 'on_track'})), ['Zed'])
        counts = self.client.get('/api/students/summary/').data['counts']
        self.assertEqual((counts['missing_documents'], counts['need_you']), (1, 1))
        rows = {row['user_detail']['first_name']: row for row in self.results(self.client.get('/api/students/', {'page_size': 100}))}
        self.assertEqual((rows['Empty']['documents_missing'], rows['Empty']['missing_document_title']), (1, 'Passport'))
        self.assertEqual(rows['Empty']['to_review_total'], 0)
        self.assertEqual((rows['Linked']['documents_missing'], rows['Linked']['to_review_total']), (0, 1))

    def test_summary_counts_every_status_and_follows_filters(self):
        late = self.add_student('Lata', level=2, target_countries='US')
        self.late_task(late)
        Document.objects.create(student=late, title='Passport', status=Document.Status.REQUIRED)
        missing = self.add_student('Doc', level=2)
        Document.objects.create(student=missing, title='Passport', status=Document.Status.REQUIRED)
        quiet = self.add_student('Quin', level=4)
        User.objects.filter(pk=quiet.user_id).update(last_login=timezone.now() - timedelta(days=30))
        response = self.client.get('/api/students/summary/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['counts'], {
            'all': 4, 'need_you': 2, 'late': 1, 'missing_documents': 2, 'quiet': 1, 'on_track': 1,
        })
        self.assertEqual(response.data['levels'], [1, 2, 4])
        self.assertEqual(response.data['countries'], ['US'])
        # Filters and search narrow the counts; ?status= never does (each pill is a status).
        counts = self.client.get('/api/students/summary/', {'level': 2, 'status': 'quiet'}).data['counts']
        self.assertEqual((counts['all'], counts['need_you'], counts['late']), (2, 2, 1))
        self.assertEqual(self.client.get('/api/students/summary/', {'search': 'lata'}).data['counts']['all'], 1)
        self.assertEqual(self.client.get('/api/students/summary/', {'country': 'US'}).data['counts']['all'], 1)

    def test_filters_and_summary_never_cross_schools(self):
        other = self.add_student('Other', school=self.school_b, counselor=self.counselor_b, level=7, target_countries='US')
        self.late_task(other, 3)
        Document.objects.create(student=other, title='Visa', status=Document.Status.REQUIRED)
        self.late_task(self.student_b)
        for user in (self.counselor, self.organization):
            for params in ({'status': 'late'}, {'status': 'need_you'}, {'status': 'missing_documents'}, {'level': 7},
                           {'country': 'US'}, {'ordering': 'late'}, {'ordering': 'progress'}):
                self.assertNotIn('Other', self.names(params, user))
            summary = self.client.get('/api/students/summary/').data
            self.assertEqual(summary['counts']['late'], 0)
            self.assertEqual(summary['counts']['missing_documents'], 0)
            self.assertNotIn(7, summary['levels'])
            self.assertNotIn('US', summary['countries'])
        # Another counselor of the same school sees none of this counselor's students.
        colleague = User.objects.create_user(username='colleague', email='colleague@example.com', password='StrongPass123!', role=User.Role.COUNSELOR, school=self.school_a)
        self.late_task(self.student_a)
        self.assertEqual(self.names({'status': 'late'}, colleague), [])
        self.client.force_authenticate(colleague)
        self.assertEqual(self.client.get('/api/students/summary/').data['counts']['all'], 0)

    def query_counts(self, n):
        StudentProfile.objects.filter(assigned_counselor=self.counselor).exclude(pk=self.student_a.pk).delete()
        for index in range(n):
            student = self.add_student(f'Q{index}', level=1 + index % 3, target_countries='US')
            self.late_task(student, index % 2)
            self.missions(student, index % 2, 2)
            Document.objects.create(student=student, title='D', status=Document.Status.REQUIRED)
        counts = []
        for params in (
            {'ordering': 'late'}, {'ordering': 'progress'}, {'ordering': 'name'},
            {'ordering': 'late', 'cursor': ''}, {'ordering': 'progress', 'cursor': ''},
            {'status': 'need_you'}, {'status': 'on_track'}, {'status': 'quiet'}, {'status': 'late'},
            {'status': 'missing_documents', 'country': 'US', 'level': 1, 'grade': '10'},
        ):
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get('/api/students/', {'page_size': 100, **params})
            self.assertEqual(response.status_code, 200)
            counts.append(len(queries))
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get('/api/students/summary/').status_code, 200)
        counts.append(len(queries))
        return counts

    def test_query_count_is_constant(self):
        self.assertEqual(self.query_counts(5), self.query_counts(60))
