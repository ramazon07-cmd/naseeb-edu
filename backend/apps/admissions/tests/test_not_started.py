"""A brand-new student is "not started", never "on track": the Students list status,
the pill counts, the row flag and Home's student progress."""
from datetime import timedelta

from django.utils import timezone

from apps.users.models import TemporaryCredential, User

from ..counselor_summary import not_started_ids, progress_bucket
from ..models import Activity, Document, Essay, RoadmapMission, ScreenTimeDaily, StudentProfile, Task
from .base import RoleIsolationBase
from .test_counselor_home import HOME_URL


class NotStartedTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.client.force_authenticate(self.counselor)

    def add_student(self, first, signed_in=False, school=None):
        school = school or self.school_a
        number = User.objects.count()
        user = User.objects.create_user(
            username=f'{first}-{number}'.lower(), email=f'{first}{number}@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=school, first_name=first, last_login=timezone.now() if signed_in else None,
        )
        return StudentProfile.objects.create(user=user, school=school, assigned_counselor=self.counselor)

    def names(self, **params):
        response = self.client.get('/api/students/', {'page_size': 100, **params})
        self.assertEqual(response.status_code, 200, response.data)
        return sorted(row['user_detail']['first_name'] for row in self.results(response))

    def test_a_brand_new_student_is_not_started_and_not_on_track(self):
        self.add_student('Neo')
        self.assertIn('Neo', self.names(status='not_started'))
        self.assertNotIn('Neo', self.names(status='on_track'))
        self.assertNotIn('Neo', self.names(status='need_you'))

    def test_the_row_carries_the_flag(self):
        fresh = self.add_student('Fresh')
        used = self.add_student('Used', signed_in=True)
        rows = {row['user_detail']['first_name']: row for row in self.results(self.client.get('/api/students/', {'page_size': 100}))}
        self.assertIs(rows['Fresh']['not_started'], True)
        self.assertIs(rows['Used']['not_started'], False)
        self.assertEqual(not_started_ids([fresh.pk, used.pk]), {fresh.pk})
        detail = self.client.get(f'/api/students/{fresh.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertIs(detail.data['not_started'], True)

    def test_signing_in_with_no_work_is_on_track(self):
        self.add_student('Back', signed_in=True)
        self.assertIn('Back', self.names(status='on_track'))
        self.assertNotIn('Back', self.names(status='not_started'))

    def test_each_sign_of_life_ends_not_started(self):
        seen = self.add_student('Seen')
        ScreenTimeDaily.objects.create(user=seen.user, date=self.today, page='dashboard', active_seconds=30)
        temp = self.add_student('Temp')
        TemporaryCredential.objects.create(user=temp.user, issued_by=self.counselor, status=TemporaryCredential.Status.USED,
                                           expires_at=timezone.now() + timedelta(days=1))
        issued = self.add_student('Issued')
        TemporaryCredential.objects.create(user=issued.user, issued_by=self.counselor, expires_at=timezone.now() + timedelta(days=1))
        work = {
            'Task': lambda p: Task.objects.create(student=p, title='T', due_date=self.today + timedelta(days=5)),
            'Mission': lambda p: RoadmapMission.objects.create(student=p, title='M'),
            'Essay': lambda p: Essay.objects.create(student=p, title='E'),
            'Activity': lambda p: Activity.objects.create(student=p, name='A', activity_type='club'),
            'Doc': lambda p: Document.objects.create(student=p, title='D', status=Document.Status.UPLOADED),
        }
        for first, make in work.items():
            make(self.add_student(first))
        listed = set(self.names(status='not_started'))
        self.assertIn('Issued', listed)
        self.assertFalse(listed & {'Seen', 'Temp', *work})

    def test_never_signed_in_with_late_work_stays_late(self):
        late = self.add_student('Lata')
        Task.objects.create(student=late, title='Late', due_date=self.today - timedelta(days=2), status=Task.Status.TODO)
        self.assertIn('Lata', self.names(status='late'))
        self.assertNotIn('Lata', self.names(status='not_started'))

    def test_summary_counts_add_up_and_follow_the_filters(self):
        self.add_student('One')
        self.add_student('Two')
        self.add_student('Back', signed_in=True)
        counts = self.client.get('/api/students/summary/').data['counts']
        expected = not_started_ids(StudentProfile.objects.filter(assigned_counselor=self.counselor).values_list('pk', flat=True))
        self.assertGreaterEqual(len(expected), 2)
        self.assertEqual(counts['not_started'], len(expected))
        self.assertEqual(counts['on_track'] + counts['not_started'], counts['all'])
        narrowed = self.client.get('/api/students/summary/', {'search': 'One'}).data['counts']
        self.assertEqual((narrowed['all'], narrowed['not_started'], narrowed['on_track']), (1, 1, 0))

    def test_an_assistant_sees_not_started_only_for_their_students(self):
        mine = self.add_student('Mine')
        self.add_student('Others')
        assistant = User.objects.create_user(
            username='assist-ns', email='assist-ns@example.com', password='StrongPass123!',
            role=User.Role.ASSISTANT, school=self.school_a, supervising_counselor=self.counselor,
        )
        StudentProfile.objects.filter(pk=mine.pk).update(assigned_assistant=assistant)
        self.client.force_authenticate(assistant)
        self.assertEqual(self.names(status='not_started'), ['Mine'])

    def test_the_bucket_never_hides_late_work(self):
        self.assertEqual(progress_bucket(0, 0, 0, True), 'not_started')
        self.assertEqual(progress_bucket(0, 0, 0, False), 'on_track')
        self.assertEqual(progress_bucket(0, 0, 2, True), 'behind')
        self.assertEqual(progress_bucket(0, 0, 3, True), 'needs_attention')
        self.assertEqual(progress_bucket(0, 50, 0, True), 'needs_attention')

    def test_home_progress_counts_the_bucket(self):
        self.add_student('Fresh')
        self.add_student('Back', signed_in=True)
        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200)
        progress = response.data['home']['progress']
        buckets = progress['buckets']
        self.assertEqual(sum(buckets.values()), progress['total'])
        self.assertGreaterEqual(buckets['not_started'], 1)
