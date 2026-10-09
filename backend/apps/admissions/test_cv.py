"""The student CV: GET /api/students/me/cv/ and /api/students/{id}/cv/."""
import datetime
import json

from rest_framework.test import APITestCase

from apps.users.models import User
from .models import (
    Achievement, Activity, Application, Essay, Honor, Internship, ParentStudentLink, Project, Research, School,
    StudentProfile, Task, University,
)

ME = '/api/students/me/cv/'
ONBOARDING = '/api/students/onboarding/'

PRIVATE_VALUES = (
    'Under $10,000', 'Gulnora Guardian', '+998900000001', 'INTERNAL-NOTE', 'COUNSELOR-COMMENT', 'Citizen of Mars',
    'ESSAY-BODY', 'TASK-TITLE', 'Dream University', 'SUPERVISOR-NAME', 'https://docs.google.com/document/d/private',
    'Male', 'Not sure', 'MY PERSONAL STORY',
)


class CvTestBase(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='CV school', code='cv-school')
        self.other_school = School.objects.create(name='Other school', code='cv-other')
        self.counselor = User.objects.create_user(username='cv-counselor', email='cv-counselor@example.com', role='counselor', school=self.school)
        self.other_counselor = User.objects.create_user(username='cv-counselor-2', email='cv-c2@example.com', role='counselor', school=self.school)
        self.foreign_counselor = User.objects.create_user(username='cv-counselor-b', email='cv-cb@example.com', role='counselor', school=self.other_school)
        self.teacher = User.objects.create_user(username='cv-teacher', email='cv-teacher@example.com', role='teacher', school=self.school)
        self.parent = User.objects.create_user(username='cv-parent', email='cv-parent@example.com', role='parent')
        self.user = User.objects.create_user(
            username='cv-student', email='cv-student@example.com', role='student', school=self.school,
            first_name='Sardor', last_name='Fictional', phone='+998 90 000 00 00',
        )
        self.profile = StudentProfile.objects.create(user=self.user, school=self.school, assigned_counselor=self.counselor)
        self.other_user = User.objects.create_user(username='cv-student-2', email='cv-s2@example.com', role='student', school=self.school)
        self.other_profile = StudentProfile.objects.create(user=self.other_user, school=self.school, assigned_counselor=self.counselor)
        ParentStudentLink.objects.create(parent=self.parent, student=self.profile, status=ParentStudentLink.Status.ACTIVE)
        self.client.force_authenticate(self.user)
        self.onboard()

    def onboard(self, **extra):
        payload = dict(
            first_name='Sardor', middle_name='Testovich', last_name='Fictional', gender='Male', grade='11', graduation_year=2027,
            first_generation='Not sure', family_income='Under $10,000', residency_status='Citizen of Mars',
            guardian_name='Gulnora Guardian', guardian_relation='mother', guardian_contact='+998900000001',
            school_name='Example Lyceum No. 1', country='Uzbekistan', city='Namangan', class_size=200, class_rank=6,
            gpa_scale='5', gpa=4.85, ielts_status='taken', ielts_score=7.5, ielts_test_date='2025-05-10',
            sat_status='taken', sat_reading=700, sat_math=780, sat_test_date='2025-03-08',
            subjects=[dict(type='AP', subject='Calculus BC', score=5)],
            certificates=[dict(type='toefl', score='104'), dict(type='other', name='CS50x Certificate', score='Pass')],
            target_countries='US, UK', interests=['Computer Technologies', 'Engineering'], personal_story='MY PERSONAL STORY',
            linkedin_url='linkedin.com/in/sardor-example', website_url='',
            languages=[dict(name='Uzbek', level='Native'), dict(name='English', level='Fluent'), dict(name='english', level='Basic')],
            skills=['Python', ' python ', 'Public speaking', ''], hobbies=['Chess', 'Football'],
            honors=[
                dict(role='Gold medal', project='Regional Math Olympiad', description='Top score.', grade='10', recognition='State/Regional'),
                dict(role='Finalist', project='Hackathon Tashkent', description='Built an app.', grade='11', recognition='National'),
            ],
            activities=[
                dict(type='Club', position='Founder', organization='Debate Society', description='Weekly debates.', grades='9, 10, 11', hours=3, weeks=30),
                dict(type='Competition', position='Participant', organization='Regional Math Olympiad', description='Same olympiad.', grades='10', hours=5, weeks=10),
                dict(type='Internship', position='Intern', organization='Startup Hub', description='Summer work.', grades='10', hours=20, weeks=8),
            ],
        )
        payload.update(extra)
        response = self.client.post(ONBOARDING, payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()

    def add_records(self):
        p = self.profile
        Internship.objects.create(
            student=p, organization='Example Bank', position='Data Intern', location='Tashkent, Uzbekistan',
            description='- Cleaned data\n\n• Built a dashboard', start_date=datetime.date(2024, 6, 1), end_date=datetime.date(2024, 12, 1),
            supervisor='SUPERVISOR-NAME', google_docs_url='https://docs.google.com/document/d/private',
        )
        Internship.objects.create(student=p, organization='Startup Hub', position='Intern', start_date=datetime.date(2025, 1, 1), is_current=True)
        Research.objects.create(
            student=p, title='Air quality study', field='Environmental science', role='Lead author', summary='Measured PM2.5.',
            outcome='Published in a school journal', start_date=datetime.date(2023, 1, 1), end_date=datetime.date(2023, 5, 1),
        )
        Project.objects.create(student=p, title='Homework bot', role='Developer', description='A Telegram bot.', technologies='Python', date=datetime.date(2024, 2, 1), link='https://example.com/bot')
        Activity.objects.create(student=p, name='Debate Society', role='President', location='Namangan', description='Led 20 members.', start_date=datetime.date(2022, 9, 1), hours_per_week=3)
        Activity.objects.create(student=p, name='Red Crescent volunteering', role='Volunteer', start_date=datetime.date(2021, 9, 1), end_date=datetime.date(2022, 6, 1))
        Honor.objects.create(student=p, title='Regional Math Olympiad - Gold medal', issuer='Regional Education Department', level='regional', award_date=datetime.date(2024, 3, 1))
        Achievement.objects.create(student=p, title='Regional Math Olympiad - Gold medal', category='olympiad', description='Duplicate of the honor.', counselor_comment='COUNSELOR-COMMENT', date=datetime.date(2024, 3, 1))
        Achievement.objects.create(student=p, title='Best school startup', category='startup', description='Won the pitch day.', counselor_comment='COUNSELOR-COMMENT', date=datetime.date(2025, 4, 1))
        p.notes = 'INTERNAL-NOTE'
        p.budget_usd = 12345
        p.save()
        Task.objects.create(student=p, title='TASK-TITLE', due_date=datetime.date(2025, 1, 1))
        Essay.objects.create(student=p, title='Essay', content='ESSAY-BODY', counselor_comment='COUNSELOR-COMMENT')
        university = University.objects.create(name='Dream University', country='US')
        Application.objects.create(student=p, university=university, program='CS', notes='INTERNAL-NOTE')


class StudentCvContentTests(CvTestBase):
    def test_only_whitelisted_fields_leave_the_server(self):
        self.add_records()
        response = self.client.get(ME)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        body = json.dumps(response.data)
        for value in PRIVATE_VALUES:
            self.assertNotIn(value, body)
        self.assertNotIn('12345', body)
        self.assertEqual(set(response.data), {'header', 'sections', 'additional'})
        self.assertEqual(set(response.data['header']), {'name', 'email', 'phone', 'location', 'links'})
        entry_keys = {'organization', 'location', 'title', 'note', 'link', 'start', 'end', 'current', 'date', 'date_text', 'bullets'}
        for section in response.data['sections']:
            self.assertEqual(set(section), {'key', 'entries'})
            for entry in section['entries']:
                self.assertEqual(set(entry), entry_keys)

    def test_header_education_and_additional_information(self):
        data = self.client.get(ME).data
        self.assertEqual(data['header'], {
            'name': 'Sardor Testovich Fictional', 'email': 'cv-student@example.com', 'phone': '+998 90 000 00 00',
            'location': 'Namangan, Uzbekistan', 'links': ['https://linkedin.com/in/sardor-example'],
        })
        education = data['sections'][0]
        self.assertEqual(education['key'], 'education')
        school = education['entries'][0]
        self.assertEqual((school['organization'], school['location'], school['date_text']), ('Example Lyceum No. 1', 'Namangan, Uzbekistan', 'Class of 2027'))
        self.assertEqual(school['note'], 'Intended fields of study: Computer Technologies, Engineering')
        self.assertEqual(school['bullets'], ['GPA: 4.85/5.0', 'Class rank: 6 of 200 (Top 3%)', 'AP: Calculus BC (5)'])
        self.assertEqual(data['additional'], [
            {'key': 'languages', 'value': 'Uzbek (Native), English (Fluent)'},
            {'key': 'test_scores', 'value': 'SAT 1480 (Reading and Writing 700, Math 780), IELTS 7.5, TOEFL iBT 104, CS50x Certificate Pass'},
            {'key': 'skills', 'value': 'Python, Public speaking'},
            {'key': 'interests', 'value': 'Chess, Football'},
        ])

    def test_records_win_over_onboarding_answers_and_duplicates_print_once(self):
        self.add_records()
        sections = {section['key']: section['entries'] for section in self.client.get(ME).data['sections']}
        names = lambda key: [entry['organization'] for entry in sections[key]]
        # The onboarding "Startup Hub" internship and "Debate Society" club are covered by records.
        self.assertEqual(names('experience'), ['Startup Hub', 'Example Bank', 'Homework bot', 'Air quality study'])
        self.assertEqual(names('leadership'), ['Debate Society', 'Red Crescent volunteering'])
        # The olympiad is an Honor, an Achievement, an onboarding honor and an onboarding activity: printed once.
        self.assertEqual(names('honors'), ['Best school startup', 'Regional Math Olympiad - Gold medal', 'Hackathon Tashkent'])
        bank = sections['experience'][1]
        self.assertEqual((bank['location'], bank['title'], bank['start'], bank['end'], bank['current']), ('Tashkent, Uzbekistan', 'Data Intern', '2024-06-01', '2024-12-01', False))
        self.assertEqual(bank['bullets'], ['Cleaned data', 'Built a dashboard'])
        self.assertTrue(sections['experience'][0]['current'])
        self.assertTrue(sections['leadership'][0]['current'])
        self.assertEqual(sections['experience'][2]['link'], 'https://example.com/bot')
        self.assertEqual(sections['experience'][3]['bullets'], ['Measured PM2.5.', 'Outcome: Published in a school journal'])
        honor = sections['honors'][1]
        self.assertEqual((honor['location'], honor['title'], honor['date']), ('Regional', 'Regional Education Department', '2024-03-01'))

    def test_onboarding_answers_fill_in_without_records(self):
        sections = {section['key']: section['entries'] for section in self.client.get(ME).data['sections']}
        self.assertEqual([e['organization'] for e in sections['experience']], ['Startup Hub'])
        self.assertEqual([e['organization'] for e in sections['leadership']], ['Debate Society'])
        debate = sections['leadership'][0]
        self.assertEqual((debate['title'], debate['date_text']), ('Founder', 'Grades 9, 10, 11'))
        self.assertEqual(debate['bullets'], ['Weekly debates.', '3 hours/week, 30 weeks/year'])
        # Onboarding honors: the olympiad activity repeats an onboarding honor and is dropped.
        self.assertEqual([e['organization'] for e in sections['honors']], ['Hackathon Tashkent', 'Regional Math Olympiad'])
        self.assertEqual(sections['honors'][0]['date_text'], 'Grade 11')

    def test_empty_sections_are_omitted(self):
        self.profile.application_profile = {}
        self.profile.school_name = ''
        self.profile.sat_status = self.profile.ielts_status = 'not_taken'
        self.profile.sat_score = self.profile.sat_reading = self.profile.sat_math = self.profile.ielts_score = None
        self.profile.save()
        data = self.client.get(ME).data
        self.assertEqual(data['sections'], [])
        self.assertEqual(data['additional'], [])
        Honor.objects.create(student=self.profile, title='Only honor', level='school')
        data = self.client.get(ME).data
        self.assertEqual([section['key'] for section in data['sections']], ['honors'])

    def test_undated_entries_come_last(self):
        Activity.objects.create(student=self.profile, name='Undated club')
        Activity.objects.create(student=self.profile, name='Old club', start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 6, 1))
        Activity.objects.create(student=self.profile, name='Newer club', start_date=datetime.date(2021, 1, 1), end_date=datetime.date(2022, 6, 1))
        sections = {section['key']: section['entries'] for section in self.client.get(ME).data['sections']}
        self.assertEqual([e['organization'] for e in sections['leadership']], ['Newer club', 'Old club', 'Debate Society', 'Undated club'])


class StudentCvAccessTests(CvTestBase):
    def url(self, profile=None):
        return f'/api/students/{(profile or self.profile).id}/cv/'

    def test_student_reads_only_their_own(self):
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        self.assertEqual(self.client.get(self.url(self.other_profile)).status_code, 404)

    def test_assigned_counselor_and_school_staff(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['header']['name'], 'Sardor Testovich Fictional')
        self.assertEqual(self.client.get(ME).status_code, 403)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get(self.url()).status_code, 200)

    def test_other_counselors_and_parents_are_refused(self):
        for user in (self.other_counselor, self.foreign_counselor, self.parent):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(self.url()).status_code, 404, user.username)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get(ME).status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(ME).status_code, (401, 403))
        self.assertIn(self.client.get(self.url()).status_code, (401, 403))

    def test_only_get(self):
        self.assertIn(self.client.post(ME, {}).status_code, (403, 405))
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(self.url(), {}).status_code, 405)


class CvAnswerValidationTests(CvTestBase):
    def test_links_languages_skills_are_validated(self):
        bad = self.client.patch(ONBOARDING, {'linkedin_url': 'javascript:alert(1)'}, format='json')
        self.assertEqual(bad.status_code, 400)
        self.assertIn('linkedin_url', bad.data)
        bad = self.client.patch(ONBOARDING, {'languages': [{'name': 'Uzbek', 'level': 'Godlike'}]}, format='json')
        self.assertEqual(bad.status_code, 400)
        bad = self.client.patch(ONBOARDING, {'languages': [{'name': f'L{i}', 'level': 'Basic'} for i in range(11)]}, format='json')
        self.assertEqual(bad.status_code, 400)
        bad = self.client.patch(ONBOARDING, {'skills': ['x' * 61]}, format='json')
        self.assertEqual(bad.status_code, 400)
        ok = self.client.patch(ONBOARDING, {'website_url': 'https://example.com/me', 'skills': ['Go']}, format='json')
        self.assertEqual(ok.status_code, 200, ok.data)
        self.profile.refresh_from_db()
        answers = self.profile.application_profile
        self.assertEqual((answers['website_url'], answers['skills'], answers['languages'][0]['name']), ('https://example.com/me', ['Go'], 'Uzbek'))

    def test_editing_languages_sends_the_goal_section_back_for_review(self):
        self.client.patch(ONBOARDING, {'languages': [{'name': 'Russian', 'level': 'Advanced'}]}, format='json')
        self.assertEqual(self.profile.section_reviews.get(section='goal').status, 'waiting')
        self.client.patch(ONBOARDING, {'linkedin_url': 'https://linkedin.com/in/new'}, format='json')
        self.assertEqual(self.profile.section_reviews.get(section='personal').status, 'waiting')
