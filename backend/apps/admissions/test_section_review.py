"""Counselor review of the Student Center profile sections."""
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.users.models import User
from .models import Notification, ParentStudentLink, ProfileSectionReview, School, StudentProfile
from .section_review import SECTION_KEYS

ONBOARDING = '/api/students/onboarding/'
Status = ProfileSectionReview.Status


def review_url(profile):
    return f'/api/students/{profile.pk}/section-review/'


class SectionReviewTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Review school', code='review-test')
        self.counselor = User.objects.create_user(username='review-counselor', email='review-counselor@example.com', role='counselor', school=self.school)
        self.student = User.objects.create_user(username='review-student', email='review-student@example.com', role='student', school=self.school)
        self.profile = StudentProfile.objects.create(user=self.student, school=self.school, assigned_counselor=self.counselor)
        self.client.force_authenticate(self.student)
        payload = dict(
            first_name='Aziza', last_name='Karimova', gender='Female', grade='11', graduation_year=2027,
            school_name='Review school', country='Uzbekistan', city='Tashkent', gpa_scale='5', gpa=4.6,
            ielts_status='planning', sat_status='not_taken', target_countries='US', interests=['Science'],
            honors=[], activities=[],
        )
        response = self.client.post(ONBOARDING, payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def review(self, user, section='academics', status=Status.APPROVED, note='', profile=None):
        self.client.force_authenticate(user)
        return self.client.post(review_url(profile or self.profile), {'section': section, 'status': status, 'note': note}, format='json')

    def reviews(self):
        self.client.force_authenticate(self.student)
        return self.client.get(ONBOARDING).data['section_reviews']

    def test_every_section_starts_not_reviewed(self):
        reviews = self.reviews()
        self.assertEqual(list(reviews), SECTION_KEYS)
        self.assertTrue(all(item == {'status': 'not_reviewed', 'note': '', 'reviewed_at': None} for item in reviews.values()))

    def test_assigned_counselor_sets_status_and_note_and_student_is_notified(self):
        response = self.review(self.counselor, 'tests', Status.CHANGES_REQUESTED, 'Add your IELTS date.')
        self.assertEqual(response.status_code, 200, response.data)
        reviews = self.reviews()
        self.assertEqual((reviews['tests']['status'], reviews['tests']['note']), ('changes_requested', 'Add your IELTS date.'))
        self.assertIsNotNone(reviews['tests']['reviewed_at'])
        notice = Notification.objects.get(student=self.profile)
        self.assertEqual((notice.kind, notice.title, notice.message, notice.target_id), (
            Notification.Kind.PROFILE_REVIEW, 'Profile section needs changes', 'Add your IELTS date.', SECTION_KEYS.index('tests') + 1,
        ))
        # The same status again (a note edit) is not a new notice; a new status is.
        self.assertEqual(self.review(self.counselor, 'tests', Status.CHANGES_REQUESTED, 'And the scores.').status_code, 200)
        self.assertEqual(Notification.objects.filter(student=self.profile).count(), 1)
        self.assertEqual(self.review(self.counselor, 'tests', Status.APPROVED).status_code, 200)
        self.assertEqual(Notification.objects.filter(student=self.profile).first().title, 'Profile section approved')
        self.assertEqual(self.client.get('/api/notifications/').status_code, 200)

    def test_school_admin_and_product_admin_may_review(self):
        organization = User.objects.create_user(username='review-org', email='review-org@example.com', role='organization', school=self.school)
        admin = User.objects.create_user(username='review-admin', email='review-admin@example.com', role='admin')
        self.assertEqual(self.review(organization).status_code, 200)
        self.assertEqual(self.review(admin, status=Status.CHANGES_REQUESTED).status_code, 200)

    def test_others_cannot_review(self):
        other_school = School.objects.create(name='Other review school', code='review-other')
        other_counselor = User.objects.create_user(username='review-other-counselor', email='review-oc@example.com', role='counselor', school=other_school)
        unassigned = User.objects.create_user(username='review-unassigned', email='review-un@example.com', role='counselor', school=self.school)
        teacher = User.objects.create_user(username='review-teacher', email='review-teacher@example.com', role='teacher', school=self.school)
        other_org = User.objects.create_user(username='review-other-org', email='review-other-org@example.com', role='organization', school=other_school)
        parent = User.objects.create_user(username='review-parent', email='review-parent@example.com', role='parent')
        ParentStudentLink.objects.create(parent=parent, student=self.profile, status=ParentStudentLink.Status.ACTIVE)
        other_student = User.objects.create_user(username='review-other-student', email='review-os@example.com', role='student', school=self.school)
        StudentProfile.objects.create(user=other_student, school=self.school)
        for user in (other_counselor, unassigned, teacher, other_org, parent, other_student, self.student):
            response = self.review(user)
            self.assertIn(response.status_code, (403, 404), user.username)
        self.assertFalse(ProfileSectionReview.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_invalid_input_is_rejected(self):
        self.assertEqual(self.review(self.counselor, section='photo').status_code, 400)
        self.assertEqual(self.review(self.counselor, status='done').status_code, 400)
        self.assertEqual(self.review(self.counselor, note='x' * 2001).status_code, 400)

    def test_editing_a_reviewed_section_sends_it_back_for_review(self):
        self.review(self.counselor, 'academics', Status.APPROVED)
        self.review(self.counselor, 'goal', Status.CHANGES_REQUESTED, 'Pick more countries.')
        self.review(self.counselor, 'personal', Status.APPROVED)
        self.client.force_authenticate(self.student)
        response = self.client.patch(ONBOARDING, {'city': 'Samarkand', 'target_countries': 'US, UK'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        reviews = response.data['profile']['section_reviews']
        self.assertEqual(reviews['academics']['status'], 'waiting')
        self.assertEqual(reviews['goal']['status'], 'waiting')
        self.assertEqual(reviews['personal']['status'], 'approved', 'an untouched section keeps its review')
        self.assertEqual(reviews['honors']['status'], 'not_reviewed')

    def test_first_edit_of_an_unreviewed_section_asks_for_review(self):
        self.client.force_authenticate(self.student)
        response = self.client.patch(ONBOARDING, {'honors': [dict(role='Captain', project='Robotics', description='Led it.', recognition='National')]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['profile']['section_reviews']['honors']['status'], 'waiting')
        self.assertEqual(ProfileSectionReview.objects.get(student=self.profile).section, 'honors')

    def test_saving_unchanged_answers_keeps_the_review(self):
        self.review(self.counselor, 'academics', Status.APPROVED)
        self.client.force_authenticate(self.student)
        response = self.client.patch(ONBOARDING, {'city': 'Tashkent', 'gpa': 4.6, 'gpa_scale': '5'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['profile']['section_reviews']['academics']['status'], 'approved')

    def test_student_list_serves_reviews_without_a_query_per_student(self):
        self.review(self.counselor, 'academics', Status.APPROVED)
        for i in range(3):
            user = User.objects.create_user(username=f'review-many-{i}', email=f'review-many-{i}@example.com', role='student', school=self.school)
            profile = StudentProfile.objects.create(user=user, school=self.school, assigned_counselor=self.counselor)
            ProfileSectionReview.objects.create(student=profile, section='tests', status=Status.WAITING)
        self.client.force_authenticate(self.counselor)
        with CaptureQueriesContext(connection) as few:
            response = self.client.get('/api/students/')
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 4)
        self.assertEqual(sum(1 for row in rows if row['section_reviews']['tests']['status'] == 'waiting'), 3)
        for i in range(3, 8):
            user = User.objects.create_user(username=f'review-many-{i}', email=f'review-many-{i}@example.com', role='student', school=self.school)
            profile = StudentProfile.objects.create(user=user, school=self.school, assigned_counselor=self.counselor)
            ProfileSectionReview.objects.create(student=profile, section='tests', status=Status.WAITING)
        with CaptureQueriesContext(connection) as many:
            self.client.get('/api/students/')
        self.assertEqual(len(many), len(few), [q['sql'] for q in many])

    def test_own_profile_read_query_count(self):
        self.review(self.counselor, 'academics', Status.APPROVED)
        self.client.force_authenticate(self.student)
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(ONBOARDING).status_code, 200)
        self.assertEqual(sum('admissions_profilesectionreview' in q['sql'] for q in queries), 1)


class SeedDemoSectionReviewTests(APITestCase):
    def test_seed_marks_one_section_approved_and_one_needing_changes(self):
        call_command('seed_demo', verbosity=0)
        call_command('seed_demo', verbosity=0)
        reviews = ProfileSectionReview.objects.filter(student__user__username='ramazon')
        self.assertEqual({review.section: review.status for review in reviews}, {'academics': 'approved', 'tests': 'changes_requested'})
        self.assertTrue(reviews.get(section='tests').note)
