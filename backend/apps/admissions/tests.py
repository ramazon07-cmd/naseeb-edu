from datetime import date, timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User
from .models import (
    Achievement, Activity, Application, Booking, ChannelMembership, ChannelMessage, CommunityPost, Document, Essay, Honor,
    Internship, MeetingNote, LevelApproval, Notification, OpportunityProgram, ProgramService, Project, RecommendationLetter,
    Research, ResourceLibraryItem, MessageChannel, MessageReport, RoadmapMission, School, Scholarship, StoreItem,
    StudentMessage, StudentProfile, Task, University, XPTransaction,
)


class RoleIsolationTests(APITestCase):
    def setUp(self):
        self.school_a = School.objects.create(name='School A', code='school-a')
        self.school_b = School.objects.create(name='School B', code='school-b')

        self.counselor = User.objects.create_user(
            username='counselor-test',
            email='counselor-test@example.com',
            password='StrongPass123!',
            role=User.Role.COUNSELOR,
        )
        self.organization = User.objects.create_user(
            username='organization-a',
            email='organization-a@example.com',
            password='StrongPass123!',
            role=User.Role.ORGANIZATION,
            school=self.school_a,
        )
        self.teacher = User.objects.create_user(
            username='teacher-a',
            email='teacher-a@example.com',
            password='StrongPass123!',
            role=User.Role.TEACHER,
            school=self.school_a,
        )
        self.student_a_user = User.objects.create_user(
            username='student-a',
            email='student-a@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_a,
        )
        self.student_b_user = User.objects.create_user(
            username='student-b',
            email='student-b@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_b,
        )
        self.student_a = StudentProfile.objects.create(
            user=self.student_a_user,
            school=self.school_a,
            school_name=self.school_a.name,
            assigned_counselor=self.counselor,
        )
        self.student_b = StudentProfile.objects.create(
            user=self.student_b_user,
            school=self.school_b,
            school_name=self.school_b.name,
            assigned_counselor=self.counselor,
        )

    def results(self, response):
        return response.data.get('results', response.data)

    def test_public_registration_is_disabled(self):
        response = self.client.post(
            '/api/users/register/',
            {
                'username': 'public-user',
                'email': 'public-user@example.com',
                'password': 'VeryStrongPass123!',
                'role': User.Role.ADMIN,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(User.objects.filter(username='public-user').exists())

    def test_student_only_lists_own_profile(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.get('/api/students/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in self.results(response)], [self.student_a.id])

    def test_student_reads_only_own_tasks_certificates_essays_and_meetings(self):
        records = {
            'tasks': (
                Task.objects.create(student=self.student_a, title='My task', due_date=date(2027, 12, 1)),
                Task.objects.create(student=self.student_b, title='Other task', due_date=date(2027, 12, 1)),
            ),
            'documents': (
                Document.objects.create(student=self.student_a, title='My certificate', document_type=Document.Type.CERTIFICATE),
                Document.objects.create(student=self.student_b, title='Other certificate', document_type=Document.Type.CERTIFICATE),
            ),
            'essays': (
                Essay.objects.create(student=self.student_a, title='My essay', prompt='My prompt'),
                Essay.objects.create(student=self.student_b, title='Other essay', prompt='Other prompt'),
            ),
            'meetings': (
                MeetingNote.objects.create(student=self.student_a, counselor=self.counselor, title='My meeting', summary='My summary'),
                MeetingNote.objects.create(student=self.student_b, counselor=self.counselor, title='Other meeting', summary='Other summary'),
            ),
        }
        self.client.force_authenticate(self.student_a_user)
        for path, (own_record, _) in records.items():
            with self.subTest(path=path):
                response = self.client.get(f'/api/{path}/')
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual([item['id'] for item in self.results(response)], [own_record.id])

    def test_student_cannot_create_task_for_another_student(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(
            '/api/tasks/',
            {
                'student': self.student_b.id,
                'title': 'Forbidden cross-school task',
                'due_date': date(2027, 12, 1),
                'priority': Task.Priority.LOW,
                'status': Task.Status.TODO,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Task.objects.filter(title='Forbidden cross-school task').exists())

    def test_student_cannot_self_assign_task(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(
            '/api/tasks/',
            {
                'student': self.student_a.id,
                'title': 'Self-assigned task',
                'due_date': date(2027, 12, 1),
                'priority': Task.Priority.LOW,
                'status': Task.Status.TODO,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Task.objects.filter(title='Self-assigned task').exists())

    def test_student_can_only_update_task_progress_fields(self):
        task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.counselor,
            title='Counselor task',
            due_date=date(2027, 12, 1),
        )
        self.client.force_authenticate(self.student_a_user)
        progressed = self.client.patch(
            f'/api/tasks/{task.id}/',
            {'status': Task.Status.IN_PROGRESS},
            format='json',
        )
        self.assertEqual(progressed.status_code, status.HTTP_200_OK)
        tampered = self.client.patch(
            f'/api/tasks/{task.id}/',
            {'title': 'Student changed title', 'due_date': date(2030, 1, 1)},
            format='json',
        )
        self.assertEqual(tampered.status_code, status.HTTP_400_BAD_REQUEST)
        task.refresh_from_db()
        self.assertEqual(task.title, 'Counselor task')
        self.assertEqual(task.due_date, date(2027, 12, 1))

    def test_student_cannot_approve_own_task(self):
        task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.counselor,
            title='Counselor approval required',
            due_date=date(2027, 12, 1),
        )
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(f'/api/tasks/{task.id}/approve/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        task.refresh_from_db()
        self.assertNotEqual(task.status, Task.Status.APPROVED)

    def test_student_cannot_approve_own_document(self):
        document = Document.objects.create(
            student=self.student_a,
            title='Transcript',
            document_type=Document.Type.TRANSCRIPT,
            status=Document.Status.UPLOADED,
        )
        self.client.force_authenticate(self.student_a_user)
        response = self.client.patch(
            f'/api/documents/{document.id}/',
            {'status': Document.Status.APPROVED},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.UPLOADED)

    def test_organization_only_lists_its_school_students(self):
        self.client.force_authenticate(self.organization)
        response = self.client.get('/api/students/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in self.results(response)], [self.student_a.id])

    def test_organization_can_read_only_its_school_admissions_modules(self):
        own_task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.counselor,
            title='School A task',
            due_date=date(2027, 12, 1),
        )
        Task.objects.create(
            student=self.student_b,
            assigned_by=self.counselor,
            title='School B private task',
            due_date=date(2027, 12, 1),
        )
        self.client.force_authenticate(self.organization)
        for path in (
            'tasks', 'applications', 'documents', 'essays', 'achievements', 'meetings',
            'researches', 'projects', 'internships', 'activities', 'honors', 'recommendations',
        ):
            with self.subTest(path=path):
                response = self.client.get(f'/api/{path}/')
                self.assertEqual(response.status_code, status.HTTP_200_OK)
        tasks = self.results(self.client.get('/api/tasks/'))
        self.assertEqual([item['id'] for item in tasks], [own_task.id])

    def test_organization_cannot_write_student_admissions_records(self):
        self.client.force_authenticate(self.organization)
        response = self.client.post(
            '/api/tasks/',
            {
                'student': self.student_a.id,
                'title': 'Organization must not assign tasks',
                'due_date': date(2027, 12, 1),
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Task.objects.filter(title='Organization must not assign tasks').exists())

    def test_organization_quick_create_stays_in_own_school(self):
        self.client.force_authenticate(self.organization)
        response = self.client.post(
            '/api/students/quick-create/',
            {
                'name': 'New School Student',
                'email': 'new-school-student@example.com',
                'grade': '11',
                'password': 'NewStudentPass123!',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = StudentProfile.objects.get(id=response.data['id'])
        self.assertEqual(created.school, self.school_a)
        self.assertEqual(created.user.school, self.school_a)

    def test_quick_create_requires_a_strong_initial_password(self):
        self.client.force_authenticate(self.organization)
        missing = self.client.post(
            '/api/students/quick-create/',
            {'name': 'No Password Student', 'email': 'no-password@example.com'},
            format='json',
        )
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        weak = self.client.post(
            '/api/students/quick-create/',
            {'name': 'Weak Password Student', 'email': 'weak-password@example.com', 'password': '12345'},
            format='json',
        )
        self.assertEqual(weak.status_code, status.HTTP_400_BAD_REQUEST)

    def test_organization_can_only_read_its_school(self):
        self.client.force_authenticate(self.organization)
        response = self.client.get('/api/schools/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in self.results(response)], [self.school_a.id])
        denied = self.client.get(f'/api/schools/{self.school_b.id}/')
        self.assertEqual(denied.status_code, status.HTTP_404_NOT_FOUND)

    def test_counselor_sees_only_assigned_students_and_their_workspace(self):
        other_counselor = User.objects.create_user(
            username='other-counselor',
            email='other-counselor@example.com',
            password='StrongPass123!',
            role=User.Role.COUNSELOR,
        )
        other_user = User.objects.create_user(
            username='other-counselor-student',
            email='other-counselor-student@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_a,
        )
        other_student = StudentProfile.objects.create(
            user=other_user,
            school=self.school_a,
            school_name=self.school_a.name,
            assigned_counselor=other_counselor,
        )
        own_task = Task.objects.create(student=self.student_a, assigned_by=self.counselor, title='Assigned task', due_date=date(2027, 12, 1))
        Task.objects.create(student=other_student, assigned_by=other_counselor, title='Private task', due_date=date(2027, 12, 1))
        own_document = Document.objects.create(student=self.student_a, title='Assigned student file')
        Document.objects.create(student=other_student, title='Other counselor file')
        university = University.objects.create(name='Workspace University', country='Testland')
        own_application = Application.objects.create(student=self.student_a, university=university, program='Computer Science')
        other_university = University.objects.create(name='Private University', country='Testland')
        Application.objects.create(student=other_student, university=other_university, program='Economics')
        self.client.force_authenticate(self.counselor)
        response = self.client.get('/api/students/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({item['id'] for item in self.results(response)}, {self.student_a.id, self.student_b.id})
        self.assertEqual({item['id'] for item in self.results(self.client.get('/api/tasks/'))}, {own_task.id})
        self.assertEqual({item['id'] for item in self.results(self.client.get('/api/documents/'))}, {own_document.id})
        self.assertEqual({item['id'] for item in self.results(self.client.get('/api/applications/'))}, {own_application.id})
        blocked_assignment = self.client.post(
            '/api/tasks/',
            {'student': other_student.id, 'title': 'Cross-counselor task', 'due_date': '2027-12-02'},
            format='json',
        )
        self.assertEqual(blocked_assignment.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_task_response_and_google_docs_previews_are_visible_to_counselor(self):
        task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.counselor,
            title='Complete essay outline',
            description='Submit the outline and supporting link.',
            due_date=date(2027, 12, 1),
        )
        google_docs_url = 'https://docs.google.com/document/d/test-document-id/edit'
        self.client.force_authenticate(self.student_a_user)
        submitted = self.client.patch(
            f'/api/tasks/{task.id}/',
            {
                'status': Task.Status.SUBMITTED,
                'student_response': 'I completed the outline and explained my structure.',
                'submission_url': google_docs_url,
            },
            format='json',
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(submitted.data['submitted_at'])
        self.assertEqual(
            submitted.data['submission_preview_url'],
            'https://docs.google.com/document/d/test-document-id/preview',
        )

        document = self.client.post(
            '/api/documents/',
            {
                'student': self.student_a.id,
                'title': 'Google Docs planning file',
                'document_type': Document.Type.OTHER,
                'status': Document.Status.UPLOADED,
                'google_docs_url': google_docs_url,
            },
            format='json',
        )
        self.assertEqual(document.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            document.data['google_docs_preview_url'],
            'https://docs.google.com/document/d/test-document-id/preview',
        )
        essay = self.client.post(
            '/api/essays/',
            {
                'student': self.student_a.id,
                'title': 'Google Docs personal statement',
                'prompt': 'Describe your academic goals.',
                'google_docs_url': google_docs_url,
            },
            format='json',
        )
        self.assertEqual(essay.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            essay.data['google_docs_preview_url'],
            'https://docs.google.com/document/d/test-document-id/preview',
        )
        invalid_link = self.client.patch(
            f"/api/essays/{essay.data['id']}/",
            {'google_docs_url': 'https://example.com/not-google-docs'},
            format='json',
        )
        self.assertEqual(invalid_link.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.counselor)
        counselor_task = self.client.get(f'/api/tasks/{task.id}/')
        self.assertEqual(counselor_task.status_code, status.HTTP_200_OK)
        self.assertEqual(counselor_task.data['student_response'], 'I completed the outline and explained my structure.')
        self.assertEqual(self.client.get(f"/api/documents/{document.data['id']}/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f"/api/essays/{essay.data['id']}/").status_code, status.HTTP_200_OK)

    def test_shared_google_docs_support_for_student_records(self):
        google_docs_url = 'https://docs.google.com/document/d/shared-record-document/edit'
        expected_preview = 'https://docs.google.com/document/d/shared-record-document/preview'
        resources = {
            'researches': {
                'title': 'AI education research',
                'summary': 'Research summary.',
            },
            'projects': {
                'title': 'Admissions dashboard',
                'description': 'Project description.',
            },
            'internships': {
                'organization': 'Naseeb Edu',
                'position': 'Student intern',
            },
            'activities': {
                'name': 'University club',
                'activity_type': Activity.Type.CLUB,
            },
            'honors': {
                'title': 'Academic honor',
                'level': Honor.Level.SCHOOL,
            },
            'recommendations': {
                'recommender_name': 'Teacher Name',
                'status': RecommendationLetter.Status.REQUESTED,
            },
        }

        self.client.force_authenticate(self.student_a_user)
        created = {}
        for resource, payload in resources.items():
            with self.subTest(resource=resource):
                response = self.client.post(
                    f'/api/{resource}/',
                    {
                        **payload,
                        'student': self.student_a.id,
                        'google_docs_url': google_docs_url,
                    },
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                self.assertEqual(response.data['google_docs_url'], google_docs_url)
                self.assertEqual(response.data['google_docs_preview_url'], expected_preview)
                created[resource] = response.data['id']

        invalid = self.client.patch(
            f"/api/researches/{created['researches']}/",
            {'google_docs_url': 'https://example.com/not-google-docs'},
            format='json',
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.student_b_user)
        blocked = self.client.patch(
            f"/api/projects/{created['projects']}/",
            {'google_docs_url': google_docs_url},
            format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(self.counselor)
        for resource, record_id in created.items():
            with self.subTest(counselor_resource=resource):
                response = self.client.get(f'/api/{resource}/{record_id}/')
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data['google_docs_preview_url'], expected_preview)

    def test_student_can_create_own_project_but_not_verify_it(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(
            '/api/projects/',
            {
                'student': self.student_a.id,
                'title': 'Student portfolio project',
                'description': 'A real student-owned project.',
                'verified': True,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(
            '/api/projects/',
            {
                'student': self.student_a.id,
                'title': 'Student portfolio project',
                'description': 'A real student-owned project.',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Project.objects.get(id=response.data['id']).verified)

    def test_student_cannot_verify_own_achievement(self):
        achievement = Achievement.objects.create(
            student=self.student_a,
            title='Regional award',
            category=Achievement.Category.OLYMPIAD,
            description='A submitted achievement.',
        )
        self.client.force_authenticate(self.student_a_user)
        response = self.client.patch(
            f'/api/achievements/{achievement.id}/',
            {'verified': True},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        achievement.refresh_from_db()
        self.assertFalse(achievement.verified)

    def test_student_cannot_change_own_school_membership(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.patch(
            f'/api/users/accounts/{self.student_a_user.id}/',
            {'school': self.school_b.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.student_a_user.refresh_from_db()
        self.assertEqual(self.student_a_user.school, self.school_a)

    def test_student_cannot_create_project_for_another_student(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(
            '/api/projects/',
            {
                'student': self.student_b.id,
                'title': 'Cross student project',
                'description': 'Must be rejected.',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_organization_can_delete_own_student_and_user(self):
        self.client.force_authenticate(self.organization)
        user_id = self.student_a_user.id
        response = self.client.delete(f'/api/students/{self.student_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(id=user_id).exists())

    def test_counselor_can_create_organization_account(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.post(
            f'/api/schools/{self.school_b.id}/create-account/',
            {
                'username': 'school-b-admin',
                'email': 'school-b-admin@example.com',
                'password': 'OrgPass987!',
                'first_name': 'School B',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        account = User.objects.get(username='school-b-admin')
        self.assertEqual(account.role, User.Role.ORGANIZATION)
        self.assertEqual(account.school, self.school_b)

    def test_organization_cannot_create_another_organization_account(self):
        self.client.force_authenticate(self.organization)
        response = self.client.post(
            f'/api/schools/{self.school_a.id}/create-account/',
            {
                'username': 'forbidden-org',
                'email': 'forbidden-org@example.com',
                'password': 'OrgPass987!',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_application_status_history_is_recorded(self):
        university = University.objects.create(name='History University', country='Testland')
        self.client.force_authenticate(self.counselor)
        created = self.client.post(
            '/api/applications/',
            {
                'student': self.student_a.id,
                'university': university.id,
                'program': 'Computer Science',
                'status': Application.Status.RESEARCHING,
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        application_id = created.data['id']
        updated = self.client.patch(
            f'/api/applications/{application_id}/',
            {'status': Application.Status.SUBMITTED},
            format='json',
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(len(updated.data['status_history']), 2)

    def test_essay_revisions_are_versioned(self):
        self.client.force_authenticate(self.student_a_user)
        created = self.client.post(
            '/api/essays/',
            {
                'student': self.student_a.id,
                'title': 'Personal Statement',
                'prompt': 'Tell your story.',
                'content': 'First draft',
                'status': Essay.Status.DRAFT,
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        updated = self.client.patch(
            f"/api/essays/{created.data['id']}/",
            {'content': 'Second draft'},
            format='json',
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data['version'], 2)
        self.assertEqual(len(updated.data['revisions']), 2)

    def test_student_can_mark_own_notification_read(self):
        notification = Notification.objects.create(
            student=self.student_a,
            title='Deadline',
            message='A deadline is approaching.',
        )
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(f'/api/notifications/{notification.id}/read/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_student_can_only_submit_roadmap_mission_with_reflection(self):
        other = RoadmapMission.objects.create(student=self.student_b, title='Private mission')
        own = RoadmapMission.objects.create(
            student=self.student_a,
            assigned_by=self.teacher,
            title='Teacher mission',
        )
        self.client.force_authenticate(self.student_a_user)
        created = self.client.post(
            '/api/roadmap-missions/',
            {
                'title': 'My application mission',
                'category': 'Applications',
                'status': RoadmapMission.Status.IN_PROGRESS,
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_403_FORBIDDEN)
        selected_status = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {
                'status': RoadmapMission.Status.IN_PROGRESS,
                'reflection': 'I started the assigned milestones.',
            },
            format='json',
        )
        self.assertEqual(selected_status.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Students cannot choose a mission status', str(selected_status.data))
        missing_reflection = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {'status': RoadmapMission.Status.SUBMITTED},
            format='json',
        )
        self.assertEqual(missing_reflection.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Add a reflection', str(missing_reflection.data))
        submitted = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {
                'status': RoadmapMission.Status.SUBMITTED,
                'reflection': 'I completed the assigned milestones.',
            },
            format='json',
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        own.refresh_from_db()
        self.assertEqual(own.status, RoadmapMission.Status.SUBMITTED)
        manual_progress = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {'progress_percent': 50},
            format='json',
        )
        self.assertEqual(manual_progress.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Manual mission progress has been removed', str(manual_progress.data))
        resubmitted = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {
                'status': RoadmapMission.Status.SUBMITTED,
                'reflection': 'Changed after submission.',
            },
            format='json',
        )
        self.assertEqual(resubmitted.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already submitted', str(resubmitted.data))
        tampered = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {'title': 'Student changed title'},
            format='json',
        )
        self.assertEqual(tampered.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.client.patch(
                f'/api/roadmap-missions/{own.id}/',
                {'status': RoadmapMission.Status.COMPLETED},
                format='json',
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.delete(f'/api/roadmap-missions/{own.id}/').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        listed = self.results(self.client.get('/api/roadmap-missions/'))
        self.assertEqual([item['id'] for item in listed], [own.id])
        self.assertFalse(any(item['id'] == other.id for item in listed))

    def test_teacher_controls_tasks_and_roadmap_only_within_own_school(self):
        self.client.force_authenticate(self.teacher)
        students = self.results(self.client.get('/api/students/'))
        self.assertEqual([item['id'] for item in students], [self.student_a.id])

        task = self.client.post(
            '/api/tasks/',
            {
                'student': self.student_a.id,
                'title': 'Teacher task',
                'due_date': date(2027, 12, 1),
                'status': Task.Status.TODO,
            },
            format='json',
        )
        self.assertEqual(task.status_code, status.HTTP_201_CREATED)
        self.assertEqual(task.data['assigned_by'], self.teacher.id)

        mission = self.client.post(
            '/api/roadmap-missions/',
            {
                'student': self.student_a.id,
                'title': 'Teacher roadmap mission',
                'status': RoadmapMission.Status.PLANNED,
            },
            format='json',
        )
        self.assertEqual(mission.status_code, status.HTTP_201_CREATED)
        self.assertEqual(mission.data['assigned_by'], self.teacher.id)

        cross_school_task = self.client.post(
            '/api/tasks/',
            {
                'student': self.student_b.id,
                'title': 'Forbidden teacher task',
                'due_date': date(2027, 12, 1),
            },
            format='json',
        )
        self.assertEqual(cross_school_task.status_code, status.HTTP_400_BAD_REQUEST)
        cross_school_mission = self.client.post(
            '/api/roadmap-missions/',
            {'student': self.student_b.id, 'title': 'Forbidden teacher mission'},
            format='json',
        )
        self.assertEqual(cross_school_mission.status_code, status.HTTP_400_BAD_REQUEST)

    def test_staff_can_extend_level_one_without_duplicates_and_students_follow_order(self):
        self.client.force_authenticate(self.teacher)
        extended = self.client.post(
            '/api/roadmap-missions/extend-level-one/',
            {'student': self.student_a.id},
            format='json',
        )
        self.assertEqual(extended.status_code, status.HTTP_200_OK)
        self.assertEqual(extended.data['created_count'], 8)
        self.assertEqual(extended.data['total_count'], 8)
        self.assertEqual(
            [item['sequence'] for item in extended.data['missions']],
            list(range(1, 9)),
        )
        self.assertIsNone(extended.data['missions'][0]['prerequisite'])
        self.assertEqual(
            extended.data['missions'][1]['prerequisite'],
            extended.data['missions'][0]['id'],
        )

        repeated = self.client.post(
            '/api/roadmap-missions/extend-level-one/',
            {'student': self.student_a.id},
            format='json',
        )
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated.data['created_count'], 0)
        self.assertEqual(RoadmapMission.objects.filter(student=self.student_a, level=1).count(), 8)

        outside_scope = self.client.post(
            '/api/roadmap-missions/extend-level-one/',
            {'student': self.student_b.id},
            format='json',
        )
        self.assertEqual(outside_scope.status_code, status.HTTP_403_FORBIDDEN)

        first, second = RoadmapMission.objects.filter(student=self.student_a).order_by('sequence')[:2]
        self.client.force_authenticate(self.student_a_user)
        locked = self.client.patch(
            f'/api/roadmap-missions/{second.id}/',
            {
                'status': RoadmapMission.Status.SUBMITTED,
                'reflection': 'I completed the second mission.',
            },
            format='json',
        )
        self.assertEqual(locked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('previous Level 1 mission', str(locked.data))

        student_extend = self.client.post(
            '/api/roadmap-missions/extend-level-one/',
            {'student': self.student_a.id},
            format='json',
        )
        self.assertEqual(student_extend.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_or_counselor_approval_is_required_for_submitted_work(self):
        task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.teacher,
            title='Submitted task',
            due_date=date(2027, 12, 1),
            status=Task.Status.SUBMITTED,
        )
        mission = RoadmapMission.objects.create(
            student=self.student_a,
            assigned_by=self.teacher,
            title='Submitted mission',
            status=RoadmapMission.Status.SUBMITTED,
        )
        self.client.force_authenticate(self.teacher)
        approved_task = self.client.post(f'/api/tasks/{task.id}/approve/', {}, format='json')
        approved_mission = self.client.post(f'/api/roadmap-missions/{mission.id}/approve/', {}, format='json')
        self.assertEqual(approved_task.status_code, status.HTTP_200_OK)
        self.assertEqual(approved_task.data['status'], Task.Status.APPROVED)
        self.assertEqual(approved_mission.status_code, status.HTTP_200_OK)
        self.assertEqual(approved_mission.data['status'], RoadmapMission.Status.COMPLETED)
        self.assertNotIn('progress_percent', approved_mission.data)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.xp_total, 125)
        self.assertEqual(self.student_a.level, 1)
        self.assertEqual(self.student_a.eligible_level, 2)
        self.assertTrue(self.student_a.level_up_pending)
        self.assertEqual(XPTransaction.objects.filter(student=self.student_a).count(), 2)

        repeated_task = self.client.post(f'/api/tasks/{task.id}/approve/', {}, format='json')
        repeated_mission = self.client.post(f'/api/roadmap-missions/{mission.id}/approve/', {}, format='json')
        self.assertEqual(repeated_task.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated_task.data['xp_awarded'], 0)
        self.assertEqual(repeated_mission.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated_mission.data['xp_awarded'], 0)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.xp_total, 125)

        self.client.force_authenticate(self.student_a_user)
        student_approval = self.client.post(f'/api/students/{self.student_a.id}/approve-level/', {}, format='json')
        self.assertEqual(student_approval.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.teacher)
        level_approval = self.client.post(f'/api/students/{self.student_a.id}/approve-level/', {}, format='json')
        self.assertEqual(level_approval.status_code, status.HTTP_200_OK)
        self.assertEqual(level_approval.data['level'], 2)
        self.assertFalse(level_approval.data['level_up_pending'])
        self.assertEqual(LevelApproval.objects.get(student=self.student_a).approved_by, self.teacher)

    def test_approved_status_cannot_bypass_xp_ledger(self):
        task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.teacher,
            title='Approval action required',
            due_date=date(2027, 12, 1),
            status=Task.Status.SUBMITTED,
        )
        mission = RoadmapMission.objects.create(
            student=self.student_a,
            assigned_by=self.teacher,
            title='Roadmap approval action required',
            status=RoadmapMission.Status.SUBMITTED,
        )
        self.client.force_authenticate(self.teacher)
        direct_task = self.client.patch(
            f'/api/tasks/{task.id}/',
            {'status': Task.Status.APPROVED},
            format='json',
        )
        direct_mission = self.client.patch(
            f'/api/roadmap-missions/{mission.id}/',
            {'status': RoadmapMission.Status.COMPLETED},
            format='json',
        )
        self.assertEqual(direct_task.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(direct_mission.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(XPTransaction.objects.exists())

    def test_student_community_can_post_and_toggle_like(self):
        self.client.force_authenticate(self.student_a_user)
        created = self.client.post(
            '/api/community-posts/',
            {'title': 'Application tip', 'body': 'Use a weekly checklist.', 'post_type': 'discussion'},
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.student_b_user)
        liked = self.client.post(f"/api/community-posts/{created.data['id']}/like/", {}, format='json')
        self.assertEqual(liked.status_code, status.HTTP_200_OK)
        self.assertTrue(liked.data['liked_by_me'])
        self.assertEqual(liked.data['likes_count'], 1)
        unliked = self.client.post(f"/api/community-posts/{created.data['id']}/like/", {}, format='json')
        self.assertEqual(unliked.status_code, status.HTTP_200_OK)
        self.assertFalse(unliked.data['liked_by_me'])
        self.assertEqual(unliked.data['likes_count'], 0)
        self.assertEqual(CommunityPost.objects.get(pk=created.data['id']).liked_by.count(), 0)

    def test_student_booking_and_message_use_assigned_counselor(self):
        self.client.force_authenticate(self.student_a_user)
        booking = self.client.post(
            '/api/bookings/',
            {
                'topic': 'Essay review',
                'starts_at': '2027-11-20T09:00:00Z',
                'duration_minutes': 45,
                'status': Booking.Status.REQUESTED,
            },
            format='json',
        )
        self.assertEqual(booking.status_code, status.HTTP_201_CREATED)
        self.assertEqual(booking.data['student'], self.student_a.id)
        self.assertEqual(booking.data['counselor'], self.counselor.id)

        message = self.client.post('/api/student-messages/', {'body': 'Could you review my outline?'}, format='json')
        self.assertEqual(message.status_code, status.HTTP_201_CREATED)
        self.assertEqual(message.data['sender'], self.student_a_user.id)
        self.assertEqual(message.data['recipient'], self.counselor.id)

        self.client.force_authenticate(self.counselor)
        counselor_messages = self.results(self.client.get('/api/student-messages/'))
        self.assertEqual([item['id'] for item in counselor_messages], [message.data['id']])
        reply = self.client.post(
            '/api/student-messages/',
            {'student': self.student_a.id, 'body': 'Your outline is ready for review.'},
            format='json',
        )
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED)
        self.assertEqual(reply.data['sender'], self.counselor.id)
        self.assertEqual(reply.data['recipient'], self.student_a_user.id)

        counselor_bookings = self.results(self.client.get('/api/bookings/'))
        self.assertEqual([item['id'] for item in counselor_bookings], [booking.data['id']])
        confirmed = self.client.patch(
            f"/api/bookings/{booking.data['id']}/",
            {'status': Booking.Status.CONFIRMED},
            format='json',
        )
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)

    def test_direct_channel_is_unique_and_private_to_its_members(self):
        self.client.force_authenticate(self.student_a_user)
        first = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        second = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['id'], second.data['id'])
        channel = MessageChannel.objects.get(id=first.data['id'])
        self.assertEqual(channel.kind, MessageChannel.Kind.DIRECT)
        self.assertEqual(channel.memberships.count(), 2)
        exposed = self.client.patch(
            f'/api/message-channels/{channel.id}/',
            {'is_public': True},
            format='json',
        )
        self.assertEqual(exposed.status_code, status.HTTP_400_BAD_REQUEST)

        sent = self.client.post(
            '/api/channel-messages/',
            {'channel': channel.id, 'body': 'Private direct message.'},
            format='json',
        )
        self.assertEqual(sent.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.student_b_user)
        listed = self.results(self.client.get('/api/message-channels/?kind=direct'))
        self.assertEqual(listed, [])
        messages = self.results(self.client.get(f'/api/channel-messages/?channel={channel.id}'))
        self.assertEqual(messages, [])

    def test_counselor_messaging_contacts_are_limited_to_assigned_students_and_school_staff(self):
        outsider = User.objects.create_user(
            username='unrelated-student',
            email='unrelated-student@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_b,
        )
        self.client.force_authenticate(self.counselor)
        contacts = self.client.get('/api/message-channels/contacts/')
        self.assertEqual(contacts.status_code, status.HTTP_200_OK)
        contact_ids = {item['id'] for item in contacts.data}
        self.assertTrue({self.student_a_user.id, self.student_b_user.id, self.organization.id, self.teacher.id}.issubset(contact_ids))
        self.assertNotIn(outsider.id, contact_ids)

    def test_school_messaging_interface_supports_counselor_contact_overview_and_member_management(self):
        self.client.force_authenticate(self.organization)
        contacts = self.client.get('/api/message-channels/contacts/')
        self.assertEqual(contacts.status_code, status.HTTP_200_OK)
        contact_ids = {item['id'] for item in contacts.data}
        self.assertTrue({self.student_a_user.id, self.teacher.id, self.counselor.id}.issubset(contact_ids))
        self.assertNotIn(self.student_b_user.id, contact_ids)

        direct = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        self.assertEqual(direct.status_code, status.HTTP_201_CREATED)
        group = self.client.post(
            '/api/message-channels/',
            {
                'kind': MessageChannel.Kind.GROUP,
                'name': 'School A staff and students',
                'members': [self.student_a_user.id, self.counselor.id, self.student_b_user.id],
            },
            format='json',
        )
        self.assertEqual(group.status_code, status.HTTP_201_CREATED)
        channel = MessageChannel.objects.get(id=group.data['id'])
        self.assertTrue(channel.memberships.filter(user=self.student_a_user).exists())
        self.assertTrue(channel.memberships.filter(user=self.counselor).exists())
        self.assertFalse(channel.memberships.filter(user=self.student_b_user).exists())

        members = self.client.get(f'/api/message-channels/{channel.id}/members/')
        self.assertEqual(members.status_code, status.HTTP_200_OK)
        removed = self.client.delete(
            f'/api/message-channels/{channel.id}/members/',
            {'user': self.student_a_user.id},
            format='json',
        )
        self.assertEqual(removed.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(channel.memberships.filter(user=self.student_a_user).exists())

        overview = self.client.get('/api/message-channels/overview/')
        self.assertEqual(overview.status_code, status.HTTP_200_OK)
        self.assertEqual(overview.data['channel_counts'][MessageChannel.Kind.DIRECT], 1)
        self.assertEqual(overview.data['channel_counts'][MessageChannel.Kind.GROUP], 1)
        self.assertEqual(overview.data['students_total'], 1)

    def test_teacher_group_is_school_scoped_and_tracks_unread(self):
        self.client.force_authenticate(self.teacher)
        created = self.client.post(
            '/api/message-channels/',
            {
                'kind': MessageChannel.Kind.GROUP,
                'name': 'School A application group',
                'members': [self.student_a_user.id, self.student_b_user.id],
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        channel = MessageChannel.objects.get(id=created.data['id'])
        self.assertEqual(channel.school, self.school_a)
        self.assertTrue(channel.memberships.filter(user=self.student_a_user).exists())
        self.assertFalse(channel.memberships.filter(user=self.student_b_user).exists())
        message = self.client.post(
            '/api/channel-messages/',
            {'channel': channel.id, 'body': 'Group deadline update.'},
            format='json',
        )
        self.assertEqual(message.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.student_a_user)
        group = self.results(self.client.get('/api/message-channels/?kind=group'))[0]
        self.assertEqual(group['unread_count'], 1)
        marked = self.client.post(f'/api/message-channels/{channel.id}/mark-read/', {}, format='json')
        self.assertEqual(marked.status_code, status.HTTP_200_OK)
        group = self.results(self.client.get('/api/message-channels/?kind=group'))[0]
        self.assertEqual(group['unread_count'], 0)

        self.client.force_authenticate(self.student_b_user)
        self.assertEqual(self.results(self.client.get('/api/message-channels/?kind=group')), [])

    def test_community_requires_join_before_posting(self):
        self.client.force_authenticate(self.teacher)
        created = self.client.post(
            '/api/message-channels/',
            {'kind': MessageChannel.Kind.COMMUNITY, 'name': 'School A Community'},
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        channel_id = created.data['id']

        self.client.force_authenticate(self.student_a_user)
        community = self.results(self.client.get('/api/message-channels/?kind=community'))[0]
        self.assertFalse(community['is_member'])
        blocked = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'Posting before joining.'},
            format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        joined = self.client.post(f'/api/message-channels/{channel_id}/join/', {}, format='json')
        self.assertEqual(joined.status_code, status.HTTP_201_CREATED)
        posted = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'Hello community.'},
            format='json',
        )
        self.assertEqual(posted.status_code, status.HTTP_201_CREATED)

    def test_discussion_supports_anonymous_threads_and_accepted_answer(self):
        self.client.force_authenticate(self.student_a_user)
        discussion = self.client.post(
            '/api/message-channels/',
            {'kind': MessageChannel.Kind.DISCUSSION, 'name': 'How should I structure my essay?'},
            format='json',
        )
        self.assertEqual(discussion.status_code, status.HTTP_201_CREATED)
        channel_id = discussion.data['id']
        question = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'I need a clear outline.', 'is_anonymous': True},
            format='json',
        )
        self.assertEqual(question.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.organization)
        joined = self.client.post(f'/api/message-channels/{channel_id}/join/', {}, format='json')
        self.assertIn(joined.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})
        visible_question = self.results(self.client.get(f'/api/channel-messages/?channel={channel_id}'))[0]
        self.assertIsNone(visible_question['sender_id'])
        self.assertEqual(visible_question['sender_name'], 'Anonymous')
        reply = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'parent': question.data['id'], 'body': 'Start with one concrete moment.'},
            format='json',
        )
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.student_a_user)
        root_answer = self.client.post(f"/api/channel-messages/{question.data['id']}/accept/", {}, format='json')
        self.assertEqual(root_answer.status_code, status.HTTP_400_BAD_REQUEST)
        accepted = self.client.post(f"/api/channel-messages/{reply.data['id']}/accept/", {}, format='json')
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        self.assertTrue(accepted.data['is_accepted_answer'])
        self.assertEqual(ChannelMessage.objects.filter(channel_id=channel_id, is_accepted_answer=True).count(), 1)

    def test_anonymous_author_stays_hidden_and_student_can_report_once(self):
        classmate = User.objects.create_user(
            username='student-a-classmate',
            email='student-a-classmate@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_a,
        )
        StudentProfile.objects.create(user=classmate, school=self.school_a, school_name=self.school_a.name)
        self.client.force_authenticate(self.student_a_user)
        discussion = self.client.post(
            '/api/message-channels/',
            {'kind': MessageChannel.Kind.DISCUSSION, 'name': 'Private identity discussion'},
            format='json',
        )
        channel_id = discussion.data['id']
        own_message = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'My own question.'},
            format='json',
        )

        self.client.force_authenticate(classmate)
        self.client.post(f'/api/message-channels/{channel_id}/join/', {}, format='json')
        anonymous_message = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'Anonymous classmate reply.', 'is_anonymous': True},
            format='json',
        )
        self.assertEqual(anonymous_message.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.student_a_user)
        listed = self.results(self.client.get(f'/api/channel-messages/?channel={channel_id}'))
        visible = next(item for item in listed if item['id'] == anonymous_message.data['id'])
        self.assertIsNone(visible['sender_id'])
        self.assertEqual(visible['sender_name'], 'Anonymous')
        reported = self.client.post(
            f"/api/channel-messages/{anonymous_message.data['id']}/report/",
            {'reason': MessageReport.Reason.HARASSMENT, 'details': 'Please review this message.'},
            format='json',
        )
        self.assertEqual(reported.status_code, status.HTTP_201_CREATED)
        duplicate = self.client.post(
            f"/api/channel-messages/{anonymous_message.data['id']}/report/",
            {'reason': MessageReport.Reason.SPAM},
            format='json',
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        own_report = self.client.post(
            f"/api/channel-messages/{own_message.data['id']}/report/",
            {'reason': MessageReport.Reason.OTHER},
            format='json',
        )
        self.assertEqual(own_report.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.get('/api/message-reports/').status_code, status.HTTP_403_FORBIDDEN)

    def test_school_moderator_queue_reveals_identity_only_there_and_removes_content(self):
        classmate = User.objects.create_user(
            username='reported-classmate',
            email='reported-classmate@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_a,
        )
        StudentProfile.objects.create(user=classmate, school=self.school_a, school_name=self.school_a.name)
        self.client.force_authenticate(self.student_a_user)
        discussion = self.client.post(
            '/api/message-channels/',
            {'kind': MessageChannel.Kind.DISCUSSION, 'name': 'Moderated school discussion'},
            format='json',
        )
        channel_id = discussion.data['id']
        self.client.force_authenticate(classmate)
        self.client.post(f'/api/message-channels/{channel_id}/join/', {}, format='json')
        message = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'Message for moderation.', 'is_anonymous': True},
            format='json',
        )
        self.client.force_authenticate(self.student_a_user)
        report = self.client.post(
            f"/api/channel-messages/{message.data['id']}/report/",
            {'reason': MessageReport.Reason.PRIVACY},
            format='json',
        )

        unrelated_school = User.objects.create_user(
            username='organization-b',
            email='organization-b@example.com',
            password='StrongPass123!',
            role=User.Role.ORGANIZATION,
            school=self.school_b,
        )
        self.client.force_authenticate(unrelated_school)
        self.assertEqual(self.results(self.client.get('/api/message-reports/?status=pending')), [])

        self.client.force_authenticate(self.organization)
        feed_message = next(
            item for item in self.results(self.client.get(f'/api/channel-messages/?channel={channel_id}'))
            if item['id'] == message.data['id']
        )
        self.assertIsNone(feed_message['sender_id'])
        queue = self.results(self.client.get('/api/message-reports/?status=pending'))
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]['sender_id'], classmate.id)
        self.assertEqual(queue[0]['reporter'], self.student_a_user.id)
        resolved = self.client.post(
            f"/api/message-reports/{report.data['id']}/resolve/",
            {'action': MessageReport.Action.CONTENT_REMOVED, 'moderator_note': 'Removed after review.'},
            format='json',
        )
        self.assertEqual(resolved.status_code, status.HTTP_200_OK)
        self.assertEqual(resolved.data['status'], MessageReport.Status.RESOLVED)
        self.assertEqual(resolved.data['action'], MessageReport.Action.CONTENT_REMOVED)
        self.assertIsNotNone(resolved.data['message_deleted_at'])

    def test_moderator_mute_blocks_new_channel_messages(self):
        reporter = User.objects.create_user(
            username='same-school-reporter',
            email='same-school-reporter@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_a,
        )
        StudentProfile.objects.create(user=reporter, school=self.school_a, school_name=self.school_a.name)
        self.client.force_authenticate(self.teacher)
        community = self.client.post(
            '/api/message-channels/',
            {'kind': MessageChannel.Kind.COMMUNITY, 'name': 'School moderation community'},
            format='json',
        )
        channel_id = community.data['id']
        for member in [self.student_a_user, reporter]:
            self.client.force_authenticate(member)
            self.client.post(f'/api/message-channels/{channel_id}/join/', {}, format='json')
        self.client.force_authenticate(self.student_a_user)
        message = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'A reported community message.'},
            format='json',
        )
        self.client.force_authenticate(reporter)
        report = self.client.post(
            f"/api/channel-messages/{message.data['id']}/report/",
            {'reason': MessageReport.Reason.SPAM},
            format='json',
        )
        self.client.force_authenticate(self.teacher)
        muted = self.client.post(
            f"/api/message-reports/{report.data['id']}/resolve/",
            {'action': MessageReport.Action.MUTED_24H},
            format='json',
        )
        self.assertEqual(muted.status_code, status.HTTP_200_OK)
        membership = ChannelMembership.objects.get(channel_id=channel_id, user=self.student_a_user)
        self.assertGreater(membership.muted_until, timezone.now() + timedelta(hours=23))
        self.client.force_authenticate(self.student_a_user)
        blocked = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'This should be blocked while muted.'},
            format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_reads_program_resources_store_and_team(self):
        ProgramService.objects.create(student=self.student_a, name='Admissions strategy', unlimited=True)
        ProgramService.objects.create(student=self.student_b, name='Private service', unlimited=True)
        ResourceLibraryItem.objects.create(title='Essay Lab', category='Essays')
        StoreItem.objects.create(title='University Match', category='Planning')
        self.client.force_authenticate(self.student_a_user)

        services = self.results(self.client.get('/api/program-services/'))
        self.assertEqual([item['name'] for item in services], ['Admissions strategy'])
        self.assertEqual(len(self.results(self.client.get('/api/resource-library/'))), 1)
        self.assertEqual(len(self.results(self.client.get('/api/store-items/'))), 1)
        team = self.client.get('/api/student-team/')
        self.assertEqual(team.status_code, status.HTTP_200_OK)
        self.assertEqual(team.data[0]['id'], self.counselor.id)

    def test_non_student_roles_cannot_open_student_only_portal_endpoints(self):
        for account in (self.counselor, self.organization):
            self.client.force_authenticate(account)
            paths = ('community-posts', 'program-services') if account == self.counselor else ('roadmap-missions', 'community-posts', 'program-services')
            for path in paths:
                with self.subTest(role=account.role, path=path):
                    self.assertEqual(self.client.get(f'/api/{path}/').status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.organization)
        for path in ('bookings', 'student-messages'):
            with self.subTest(role=self.organization.role, path=path):
                self.assertEqual(self.client.get(f'/api/{path}/').status_code, status.HTTP_403_FORBIDDEN)

    def test_student_can_shortlist_own_university_but_not_record_decision(self):
        university = University.objects.create(name='Student Choice University', country='Testland')
        self.client.force_authenticate(self.student_a_user)
        created = self.client.post(
            '/api/applications/',
            {
                'student': self.student_a.id,
                'university': university.id,
                'program': 'Computer Science',
                'tier': 'target',
                'status': Application.Status.SHORTLISTED,
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        denied = self.client.patch(
            f"/api/applications/{created.data['id']}/",
            {'status': Application.Status.ACCEPTED},
            format='json',
        )
        self.assertEqual(denied.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_reads_active_scholarship_and_program_catalogs(self):
        active_scholarship = Scholarship.objects.create(
            title='Active Scholarship', provider='Naseeb', scholarship_type=Scholarship.Type.MERIT,
            funding_level=Scholarship.FundingLevel.FULL, scope=Scholarship.Scope.INTERNATIONAL,
        )
        Scholarship.objects.create(
            title='Hidden Scholarship', provider='Naseeb', scholarship_type=Scholarship.Type.NEED_BASED,
            scope=Scholarship.Scope.NATIONAL, is_active=False,
        )
        national_program = OpportunityProgram.objects.create(
            title='National Program', provider='Naseeb', program_type=OpportunityProgram.ProgramType.NATIONAL,
            category='Research',
        )
        international_program = OpportunityProgram.objects.create(
            title='International Program', provider='Naseeb', program_type=OpportunityProgram.ProgramType.INTERNATIONAL,
            category='Leadership',
        )
        OpportunityProgram.objects.create(
            title='Hidden Program', provider='Naseeb', program_type=OpportunityProgram.ProgramType.NATIONAL,
            category='Camp', is_active=False,
        )
        self.client.force_authenticate(self.student_a_user)
        scholarships = self.results(self.client.get('/api/scholarships/'))
        programs = self.results(self.client.get('/api/opportunity-programs/'))
        self.assertEqual([item['id'] for item in scholarships], [active_scholarship.id])
        self.assertEqual({item['id'] for item in programs}, {national_program.id, international_program.id})
        self.assertEqual({item['program_type'] for item in programs}, {'national', 'international'})

    def test_university_api_exposes_niche_style_aid_fields(self):
        University.objects.create(
            name='Aid University', country='Testland', acceptance_rate='42.50', sat_min=1200, sat_max=1400,
            net_price_usd=18000, average_aid_usd=12000, offers_merit_aid=True,
            offers_international_aid=True, test_optional=True,
        )
        self.client.force_authenticate(self.student_a_user)
        result = self.results(self.client.get('/api/universities/'))[0]
        self.assertEqual(result['acceptance_rate'], '42.50')
        self.assertEqual(result['net_price_usd'], 18000)
        self.assertTrue(result['offers_international_aid'])
        self.assertTrue(result['test_optional'])

    def test_college_research_asks_only_for_missing_profile_data(self):
        self.student_a.gpa = '4.80'
        self.student_a.save(update_fields=['gpa', 'updated_at'])
        self.client.force_authenticate(self.student_a_user)

        response = self.client.get('/api/college-research/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['ready'])
        self.assertNotIn('gpa', response.data['missing_fields'])
        self.assertIn('sat_score', response.data['missing_fields'])
        self.assertIn('target_major', response.data['missing_fields'])
        self.assertEqual(
            {question['field'] for question in response.data['questions']},
            set(response.data['missing_fields']),
        )

    def test_student_can_complete_profile_and_receive_ranked_college_research(self):
        university = University.objects.create(
            name='Profile Match University', country='United States', city='Boston', ranking=12,
            acceptance_rate='34.00', sat_min=1350, sat_max=1500, net_price_usd=18000,
            average_aid_usd=24000, offers_merit_aid=True, offers_international_aid=True,
            popular_majors='Computer Science, Data Science',
        )
        self.client.force_authenticate(self.student_a_user)

        response = self.client.post(
            '/api/college-research/',
            {
                'gpa': '4.70',
                'sat_score': 1450,
                'ielts_score': '7.5',
                'target_major': 'Computer Science',
                'target_countries': 'United States, Canada',
                'budget_usd': 22000,
                'scholarship_needed': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['ready'])
        self.assertEqual(response.data['recommendations'][0]['university']['id'], university.id)
        self.assertGreaterEqual(response.data['recommendations'][0]['match_score'], 65)
        self.assertIn(response.data['recommendations'][0]['admission_band'], {'reach', 'target', 'strong_option'})
        self.assertIn('academic', response.data['recommendations'][0]['score_breakdown'])
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.sat_score, 1450)
        self.assertEqual(self.student_a.target_major, 'Computer Science')

    def test_non_student_cannot_use_college_research(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.get('/api/college-research/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_task_roadmap_and_journey_progress_are_computed(self):
        Task.objects.create(student=self.student_a, title='Working task', due_date=date(2027, 12, 1), status=Task.Status.IN_PROGRESS)
        Task.objects.create(student=self.student_a, title='Approved task', due_date=date(2027, 12, 1), status=Task.Status.APPROVED)
        RoadmapMission.objects.create(student=self.student_a, title='Planned mission', status=RoadmapMission.Status.PLANNED)
        RoadmapMission.objects.create(student=self.student_a, title='Done mission', status=RoadmapMission.Status.COMPLETED)
        self.assertEqual(self.student_a.task_progress_percent, 70)
        self.assertEqual(self.student_a.roadmap_progress_percent, 50)
        self.assertEqual(self.student_a.journey_progress_percent, 60)
        self.client.force_authenticate(self.student_a_user)
        profile = self.results(self.client.get('/api/students/'))[0]
        self.assertEqual(profile['task_progress_percent'], 70)
        self.assertEqual(profile['roadmap_progress_percent'], 50)
        self.assertEqual(profile['journey_progress_percent'], 60)
        self.assertEqual(profile['task_status_counts']['approved'], 1)
        self.assertEqual(profile['roadmap_status_counts']['completed'], 1)

    def test_dashboard_exposes_progress_and_risk_summary(self):
        Task.objects.create(student=self.student_a, title='Late task', due_date=date(2025, 1, 1), status=Task.Status.LATE)
        RoadmapMission.objects.create(student=self.student_a, title='Current mission', status=RoadmapMission.Status.IN_PROGRESS)
        self.client.force_authenticate(self.counselor)
        response = self.client.get('/api/dashboard/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('average_task_progress', response.data)
        self.assertIn('average_roadmap_progress', response.data)
        self.assertIn('average_journey_progress', response.data)
        self.assertEqual(response.data['students_at_risk'], 1)
