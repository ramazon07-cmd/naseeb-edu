"""End-to-end journeys through the public API, asserting every number.

Each test walks one real flow (assignment, tasks, roadmap, documents,
portfolio review, messaging, parent view, moving a student) and after every
step checks what each role sees: the student's own numbers, the counselor's
student list and dashboard, and the parent portal. Formulas: docs/metrics.md.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions.models import School
from apps.users.models import User

PASSWORD = 'Journey-Pass-2026!'


class JourneyBase(APITestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.school = School.objects.create(name='Journey Lyceum', code='journey-lyceum')
        self.other_school = School.objects.create(name='Other Lyceum', code='other-lyceum')
        self.admin = self.user('j-admin', User.Role.ADMIN, None)
        self.counselor = self.user('j-counselor', User.Role.COUNSELOR, self.school, first_name='Malika',
                                   last_name='Karimova')
        self.teacher = self.user('j-teacher', User.Role.TEACHER, self.school)
        self.organization = self.user('j-org', User.Role.ORGANIZATION, self.school, first_name='Lyceum',
                                      last_name='Office')
        self.student = self.create_student('Aziz Rahimov')
        self.student_user = User.objects.get(pk=self.student['user'])

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def user(username, role, school, **extra):
        return User.objects.create_user(username=username, email=f'{username}@example.com', password=None,
                                        role=role, school=school, **extra)

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self

    def call(self, method, url, data=None, expected=200):
        response = getattr(self.client, method)(url, data, format='json')
        self.assertEqual(response.status_code, expected, getattr(response, 'data', None))
        return response.data

    def get(self, url, expected=200):
        return self.call('get', url, expected=expected)

    def post(self, url, data=None, expected=200):
        return self.call('post', url, data or {}, expected)

    def patch(self, url, data, expected=200):
        return self.call('patch', url, data, expected)

    @staticmethod
    def rows(data):
        return data['results'] if isinstance(data, dict) and 'results' in data else data

    def create_student(self, name, school=None):
        self.as_user(self.admin)
        return self.post('/api/students/quick-create/', {
            'name': name, 'password': PASSWORD, 'school': (school or self.school).id,
        }, expected=201)

    def assign(self, student_id, counselor=None):
        self.as_user(counselor or self.counselor)
        return self.post('/api/students/assign-counselor/', {'students': [student_id]})

    def profile(self, user=None, student_id=None):
        self.as_user(user or self.counselor)
        return self.get(f'/api/students/{student_id or self.student["id"]}/')

    def dashboard(self, user=None):
        self.as_user(user or self.counselor)
        return self.get('/api/dashboard/stats/')

    def task(self, title, priority, due_in_days):
        self.as_user(self.counselor)
        return self.post('/api/tasks/', {
            'student': self.student['id'], 'title': title, 'priority': priority,
            'due_date': str(self.today + timedelta(days=due_in_days)),
        }, expected=201)

    def student_submits(self, task_id):
        self.as_user(self.student_user)
        return self.patch(f'/api/tasks/{task_id}/', {'status': 'submitted', 'student_response': 'Done, see draft.'})

    def approve(self, task_id, user=None):
        self.as_user(user or self.counselor)
        return self.post(f'/api/tasks/{task_id}/approve/')

    def assert_numbers(self, expected, user=None):
        profile = self.profile(user)
        self.assertEqual({key: profile[key] for key in expected}, expected)
        return profile


class AssignmentJourneyTests(JourneyBase):
    def test_counselor_and_student_see_each_other(self):
        self.assertEqual(self.dashboard()['students_total'], 0)
        self.as_user(self.counselor)
        candidates = self.get('/api/students/assignment-candidates/')
        self.assertEqual([row['id'] for row in candidates], [self.student['id']])

        self.assertEqual(self.assign(self.student['id'])['assigned_count'], 1)

        self.as_user(self.student_user)
        team = self.get('/api/student-team/')
        self.assertEqual([(m['kind'], m['name']) for m in team],
                         [('counselor', 'Malika Karimova'), ('school', 'Lyceum Office')])

        self.as_user(self.counselor)
        listed = self.rows(self.get('/api/students/'))
        self.assertEqual([(row['id'], row['school'], row['school_name'], row['counselor_name']) for row in listed],
                         [(self.student['id'], self.school.id, 'Journey Lyceum', 'Malika Karimova')])
        self.assertEqual(self.dashboard(), {
            **self.dashboard(), 'students_total': 1, 'students_at_risk': 0, 'average_progress': 0,
            'average_task_progress': 0, 'average_roadmap_progress': 0, 'average_journey_progress': 0,
        })
        # A second counselor of the school sees nobody; the organization sees the school.
        peer = self.user('j-peer', User.Role.COUNSELOR, self.school)
        self.assertEqual(self.dashboard(peer)['students_total'], 0)
        self.assertEqual(self.dashboard(self.organization)['students_total'], 1)


class TaskJourneyTests(JourneyBase):
    def setUp(self):
        super().setUp()
        self.assign(self.student['id'])

    def test_tasks_from_assignment_to_level_up(self):
        late = self.task('Finish activity list', 'high', -1)
        urgent = self.task('Book IELTS', 'urgent', 2)
        low = self.task('Tidy CV', 'low', 2)
        later = self.task('Draft essay', 'medium', 10)

        # Next priorities: earliest deadline first, then the most urgent.
        self.as_user(self.student_user)
        order = [row['id'] for row in self.rows(self.get('/api/tasks/'))]
        self.assertEqual(order, [late['id'], urgent['id'], low['id'], later['id']])

        self.assert_numbers({
            'task_status_counts': {'todo': 4, 'in_progress': 0, 'submitted': 0, 'approved': 0, 'late': 0},
            'task_progress_percent': 0, 'journey_progress_percent': 0, 'progress_percent': 0,
            'readiness_items_done': 0, 'readiness_items_total': 4, 'is_at_risk': True,
            'xp_total': 0, 'level': 1,
        })
        stats = self.dashboard()
        self.assertEqual((stats['tasks_total'], stats['tasks_late'], stats['tasks_due_week'],
                          stats['students_at_risk']), (4, 1, 2, 1))

        # Submitted work waits on the counselor: no longer late.
        submitted = self.student_submits(late['id'])
        self.assertEqual(submitted['status'], 'submitted')
        self.assertIsNotNone(submitted['submitted_at'])
        self.assertFalse(submitted['is_overdue'])
        self.assert_numbers({'task_progress_percent': 20, 'is_at_risk': False})  # 80 / 4
        stats = self.dashboard()
        self.assertEqual((stats['tasks_late'], stats['students_at_risk'], stats['average_task_progress']),
                         (0, 0, 20))

        approved = self.approve(late['id'])
        self.assertEqual(approved['xp_awarded'], 75)  # high priority
        self.assertEqual(approved['student_leveling']['xp_total'], 75)
        self.assert_numbers({
            'task_progress_percent': 25, 'progress_percent': 25, 'readiness_items_done': 1,
            'xp_total': 75, 'level': 1, 'eligible_level': 1, 'next_level_xp': 100,
            'xp_progress_percent': 75, 'level_up_pending': False,
        })
        # Approving twice awards nothing more.
        self.assertEqual(self.approve(late['id'])['xp_awarded'], 0)

        # Changes requested: the task goes back to the student.
        self.student_submits(urgent['id'])
        self.as_user(self.counselor)
        self.patch(f'/api/tasks/{urgent["id"]}/', {'status': 'in_progress'})
        self.assert_numbers({'task_progress_percent': 35})  # (100 + 40) / 4

        self.student_submits(urgent['id'])
        self.assertEqual(self.approve(urgent['id'], user=self.teacher)['xp_awarded'], 100)
        self.assert_numbers({
            'task_progress_percent': 50, 'progress_percent': 50, 'xp_total': 175, 'level': 1,
            'eligible_level': 2, 'level_up_pending': True, 'xp_progress_percent': 100,
        })

        # The student cannot undo an approval.
        self.as_user(self.student_user)
        self.patch(f'/api/tasks/{urgent["id"]}/', {'status': 'todo'}, expected=400)

        # Level approval by a teacher: Level 2 spans 100..300 XP.
        self.as_user(self.teacher)
        leveled = self.post(f'/api/students/{self.student["id"]}/approve-level/')
        self.assertEqual((leveled['level'], leveled['approved_from_level']), (2, 1))
        self.assert_numbers({
            'level': 2, 'eligible_level': 2, 'level_up_pending': False, 'next_level_xp': 300,
            'xp_progress_percent': 38,  # 75 of 200 = 37.5
        })
        self.as_user(self.teacher)
        self.post(f'/api/students/{self.student["id"]}/approve-level/', expected=400)

        # Late means owed and past due: the `late` status alone, before the date, is not at risk.
        self.as_user(self.counselor)
        self.patch(f'/api/tasks/{later["id"]}/', {'status': 'late'})
        self.assert_numbers({'is_at_risk': False, 'task_progress_percent': 50})
        self.assertEqual(self.dashboard()['students_at_risk'], 0)
        self.assertEqual(low['priority'], 'low')

    def test_self_tasks_count_but_never_earn_xp(self):
        self.as_user(self.student_user)
        own = self.post('/api/tasks/', {
            'student': self.student['id'], 'title': 'Read 20 pages', 'due_date': str(self.today),
        }, expected=201)
        self.student_submits(own['id'])
        self.assertEqual(self.approve(own['id'])['xp_awarded'], 0)
        self.assert_numbers({'task_progress_percent': 100, 'xp_total': 0})


class RoadmapJourneyTests(JourneyBase):
    def setUp(self):
        super().setUp()
        self.assign(self.student['id'])

    def test_missions_stars_and_journey(self):
        self.as_user(self.counselor)
        created = self.post('/api/roadmap-missions/extend-level-one/', {'student': self.student['id']})
        self.assertEqual((created['created_count'], created['total_count']), (8, 8))
        first, second = created['missions'][0], created['missions'][1]
        self.assertEqual((first['prerequisite_status'], second['prerequisite_status']), (None, 'planned'))
        self.assert_numbers({
            'roadmap_progress_percent': 0, 'roadmap_stars': 0, 'journey_progress_percent': 0,
            'roadmap_status_counts': {'planned': 8, 'in_progress': 0, 'submitted': 0, 'completed': 0},
        })

        self.as_user(self.student_user)
        self.patch(f'/api/roadmap-missions/{second["id"]}/', {'status': 'submitted', 'reflection': 'x'},
                   expected=400)
        self.patch(f'/api/roadmap-missions/{first["id"]}/', {'status': 'submitted'}, expected=400)
        submitted = self.patch(f'/api/roadmap-missions/{first["id"]}/',
                               {'status': 'submitted', 'reflection': 'My goals are clear.'})
        self.assertEqual(submitted['approval_status'], 'awaiting_approval')
        self.assert_numbers({'roadmap_progress_percent': 0, 'roadmap_stars': 0})

        self.as_user(self.counselor)
        approved = self.post(f'/api/roadmap-missions/{first["id"]}/approve/')
        self.assertEqual((approved['status'], approved['xp_awarded']), ('completed', 75))
        self.assert_numbers({
            'roadmap_progress_percent': 13, 'roadmap_stars': 1, 'journey_progress_percent': 13,
            'xp_total': 75,
        })
        missions = self.rows(self.get(f'/api/roadmap-missions/?student={self.student["id"]}&ordering=sequence'))
        self.assertEqual(missions[1]['prerequisite_status'], 'completed')
        self.assertEqual(self.dashboard()['average_roadmap_progress'], 13)

        # With tasks too, the journey is the mean of both.
        task = self.task('Shortlist', 'medium', 5)
        self.student_submits(task['id'])
        self.assert_numbers({'task_progress_percent': 80, 'journey_progress_percent': 47})  # (80 + 13) / 2
        self.assertEqual(self.dashboard()['average_journey_progress'], 47)


class DocumentJourneyTests(JourneyBase):
    def setUp(self):
        super().setUp()
        self.assign(self.student['id'])

    def readiness(self):
        profile = self.profile()
        return profile['progress_percent'], profile['readiness_items_done'], profile['readiness_items_total']

    def test_documents_and_letters_drive_readiness(self):
        self.as_user(self.counselor)
        document = self.post('/api/documents/', {
            'student': self.student['id'], 'title': 'Transcript', 'document_type': 'transcript',
        }, expected=201)
        self.assertEqual(document['status'], 'required')
        self.assertEqual(self.readiness(), (0, 0, 1))
        self.assertEqual(self.dashboard()['documents_pending_review'], 0)

        link = 'https://docs.google.com/document/d/transcript/edit'
        self.as_user(self.student_user)
        self.assertEqual(self.patch(f'/api/documents/{document["id"]}/', {'google_docs_url': link})['status'],
                         'uploaded')
        self.assertEqual(self.dashboard()['documents_pending_review'], 1)

        self.as_user(self.counselor)
        self.patch(f'/api/documents/{document["id"]}/', {'status': 'reviewing'})
        self.assertEqual((self.readiness(), self.dashboard()['documents_pending_review']), ((0, 0, 1), 1))
        self.as_user(self.counselor)
        self.patch(f'/api/documents/{document["id"]}/', {'status': 'rejected', 'counselor_comment': 'Unsigned'})
        self.assertEqual((self.readiness(), self.dashboard()['documents_pending_review']), ((0, 0, 1), 0))

        self.as_user(self.student_user)
        self.patch(f'/api/documents/{document["id"]}/', {'google_docs_url': link + '?v=2'})
        self.as_user(self.counselor)
        self.patch(f'/api/documents/{document["id"]}/', {'status': 'approved'})
        self.assertEqual(self.readiness(), (100, 1, 1))

        letter = self.post('/api/recommendations/', {
            'student': self.student['id'], 'recommender_name': 'Ms Yusupova',
        }, expected=201)
        self.assertEqual(self.readiness(), (50, 1, 2))
        self.as_user(self.student_user)
        self.patch(f'/api/recommendations/{letter["id"]}/', {'status': 'drafting'})
        self.assertEqual(self.readiness(), (50, 1, 2))
        self.as_user(self.student_user)
        self.patch(f'/api/recommendations/{letter["id"]}/', {'status': 'submitted'})
        self.assertEqual(self.readiness(), (100, 2, 2))
        self.assertEqual(self.dashboard()['average_progress'], 100)


class PortfolioReviewJourneyTests(JourneyBase):
    def setUp(self):
        super().setUp()
        self.assign(self.student['id'])

    def test_verification_states(self):
        payloads = {
            'activities': {'name': 'Debate club', 'activity_type': 'club'},
            'honors': {'title': 'Regional olympiad', 'level': 'regional'},
            'achievements': {'title': 'Tutoring app', 'category': 'project', 'description': 'Built for peers'},
        }
        for resource, payload in payloads.items():
            self.as_user(self.student_user)
            record = self.post(f'/api/{resource}/', {'student': self.student['id'], **payload}, expected=201)
            self.assertFalse(record['verified'], resource)
            self.patch(f'/api/{resource}/{record["id"]}/', {'verified': True}, expected=400)
            self.as_user(self.counselor)
            self.assertTrue(self.patch(f'/api/{resource}/{record["id"]}/', {'verified': True})['verified'])
            self.as_user(self.student_user)
            edited = self.patch(f'/api/{resource}/{record["id"]}/', {'description': 'Now with more detail'})
            self.assertFalse(edited['verified'], resource)


class MessagingJourneyTests(JourneyBase):
    def setUp(self):
        super().setUp()
        self.assign(self.student['id'])

    def unread(self, user):
        self.as_user(user)
        overview = self.get('/api/message-channels/overview/')
        channels = self.rows(self.get('/api/message-channels/?kind=direct'))
        return overview['unread_total'], [channel['unread_count'] for channel in channels]

    def test_direct_chat_both_ways_with_unread_counts(self):
        self.as_user(self.student_user)
        channel = self.post('/api/message-channels/direct/', {'user': self.counselor.id}, expected=201)
        for body in ('Hello!', 'Can we meet?'):
            self.post('/api/channel-messages/', {'channel': channel['id'], 'body': body}, expected=201)
        self.assertEqual(self.unread(self.student_user), (0, [0]))
        self.assertEqual(self.unread(self.counselor), (2, [2]))

        # The counselor opens the same chat from their side and replies.
        self.as_user(self.counselor)
        self.assertEqual(self.post('/api/message-channels/direct/', {'user': self.student_user.id})['id'],
                         channel['id'])
        self.post('/api/channel-messages/', {'channel': channel['id'], 'body': 'Yes, Friday.'}, expected=201)
        # Replying means the counselor has read the conversation.
        self.assertEqual(self.unread(self.counselor), (0, [0]))
        self.assertEqual(self.unread(self.student_user), (1, [1]))
        self.as_user(self.student_user)
        self.post(f'/api/message-channels/{channel["id"]}/mark-read/')
        self.assertEqual(self.unread(self.student_user), (0, [0]))


class ParentJourneyTests(JourneyBase):
    def setUp(self):
        super().setUp()
        self.assign(self.student['id'])

    def test_parent_sees_the_same_numbers(self):
        task = self.task('Book SAT', 'medium', -2)
        self.task('Draft essay', 'low', 4)
        self.student_submits(task['id'])
        self.approve(task['id'])
        self.as_user(self.counselor)
        self.post('/api/roadmap-missions/extend-level-one/', {'student': self.student['id']})
        self.task('Overdue call', 'high', -1)

        self.as_user(self.counselor)
        self.post('/api/parent-links/invite/', {
            'student': self.student['id'], 'email': 'j-parent@example.com', 'first_name': 'Dilnoza',
            'last_name': 'Rahimova', 'password': PASSWORD, 'relationship': 'mother',
        }, expected=201)
        parent = User.objects.get(email='j-parent@example.com')
        self.as_user(parent)
        link = self.rows(self.get('/api/parent-links/'))[0]
        self.post(f'/api/parent-links/{link["id"]}/accept/')

        portal = self.get('/api/parent-portal/')
        child = portal['children'][0]
        profile = self.profile()
        keys = ('level', 'xp_total', 'next_level_xp', 'task_progress_percent', 'roadmap_progress_percent',
                'journey_progress_percent', 'is_at_risk')
        self.assertEqual({key: child['profile'][key] for key in keys}, {key: profile[key] for key in keys})
        self.assertEqual(child['profile']['counselor_name'], 'Malika Karimova')
        self.assertEqual((child['profile']['task_progress_percent'], child['profile']['is_at_risk']), (33, True))
        self.assertEqual(sorted(item['is_overdue'] for item in child['tasks']), [False, False, True])


class MovingStudentsJourneyTests(JourneyBase):
    def setUp(self):
        super().setUp()
        self.assign(self.student['id'])
        self.second = self.create_student('Nodira Saidova')
        self.assign(self.second['id'])
        self.task('Overdue call', 'high', -1)

    def test_moved_and_deactivated_students_leave_the_counselor_numbers(self):
        stats = self.dashboard()
        self.assertEqual((stats['students_total'], stats['students_at_risk'], stats['tasks_total']), (2, 1, 1))

        self.as_user(self.admin)
        self.patch(f'/api/students/{self.student["id"]}/', {'school': self.other_school.id})
        stats = self.dashboard()
        self.assertEqual((stats['students_total'], stats['students_at_risk'], stats['tasks_total']), (1, 0, 0))
        self.as_user(self.counselor)
        self.assertEqual([row['id'] for row in self.rows(self.get('/api/students/'))], [self.second['id']])
        self.get(f'/api/students/{self.student["id"]}/', expected=404)
        self.as_user(self.student_user)
        self.assertEqual(self.get('/api/student-team/'), [])

        self.as_user(self.admin)
        self.call('delete', f'/api/students/{self.second["id"]}/', expected=204)
        self.assertEqual(self.dashboard()['students_total'], 0)
        self.as_user(self.counselor)
        self.assertEqual(self.rows(self.get('/api/students/')), [])
        self.assertEqual(self.dashboard(self.organization)['students_total'], 0)
