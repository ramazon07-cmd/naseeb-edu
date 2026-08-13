from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import (
    CounselorRoadmap,
    CounselorRoadmapMission,
    School,
    StudentProfile,
    XPTransaction,
)
from apps.users.models import ProductAuditEvent


User = get_user_model()


class AdminControlTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Control School', code='control-school')
        self.admin = User.objects.create_user(
            username='product-admin', email='product-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN
        )

    def create_counselor(self, index, school=None, active=True):
        return User.objects.create_user(
            username=f'counselor-{index}',
            email=f'counselor-{index}@example.com',
            password='StrongPass123!',
            role=User.Role.COUNSELOR,
            school=school or self.school,
            is_active=active,
        )

    def test_is_staff_does_not_grant_product_admin_access(self):
        staff_teacher = User.objects.create_user(
            username='staff-teacher', email='staff-teacher@example.com', password='StrongPass123!',
            role=User.Role.TEACHER, school=self.school, is_staff=True,
        )
        self.client.force_authenticate(staff_teacher)
        users_response = self.client.get('/api/users/accounts/')
        audit_response = self.client.get('/api/users/audit-events/')
        self.assertEqual(users_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(users_response.data['results']), 1)
        self.assertEqual(audit_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_counselor_cannot_deactivate_a_peer_counselor(self):
        first = self.create_counselor(1)
        second = self.create_counselor(2)
        self.client.force_authenticate(first)
        response = self.client.patch(
            f'/api/users/accounts/{second.id}/', {'is_active': False}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        second.refresh_from_db()
        self.assertTrue(second.is_active)

    def test_school_crud_is_admin_only_and_delete_is_soft(self):
        counselor = self.create_counselor(1)
        payload = {'name': 'Provisioned School', 'code': 'provisioned-school', 'is_active': True}
        self.client.force_authenticate(counselor)
        denied = self.client.post('/api/schools/', payload, format='json')
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin)
        created = self.client.post('/api/schools/', payload, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        school_id = created.data['id']
        updated = self.client.patch(f'/api/schools/{school_id}/', {'contact_phone': '+998901234567'}, format='json')
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        deactivated = self.client.delete(f'/api/schools/{school_id}/')
        self.assertEqual(deactivated.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(School.objects.get(pk=school_id).is_active)
        self.assertTrue(ProductAuditEvent.objects.filter(action='school.deactivated', target_id=str(school_id)).exists())

    def test_fourth_active_school_counselor_is_rejected_and_deactivation_releases_slot(self):
        counselors = [self.create_counselor(index) for index in range(3)]
        self.client.force_authenticate(self.admin)
        payload = {
            'username': 'fourth', 'email': 'fourth@example.com', 'first_name': 'Fourth',
            'password': 'StrongPass123!', 'school': self.school.id,
        }
        rejected = self.client.post('/api/users/accounts/create-counselor/', payload, format='json')
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('at most 3', str(rejected.data))

        deactivated = self.client.post(f'/api/users/accounts/{counselors[0].id}/deactivate/')
        self.assertEqual(deactivated.status_code, status.HTTP_200_OK)
        created = self.client.post('/api/users/accounts/create-counselor/', payload, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.filter(school=self.school, role=User.Role.COUNSELOR, is_active=True).count(), 3)

    def test_individual_counselor_workspace_is_exempt(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/users/accounts/create-individual-counselor/', {
            'username': 'independent', 'email': 'independent@example.com', 'first_name': 'Indira',
            'password': 'StrongPass123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['school_workspace_type'], School.WorkspaceType.INDIVIDUAL)

    def test_counselor_roadmap_completion_is_separate_from_student_xp(self):
        counselor = self.create_counselor(1)
        student_user = User.objects.create_user(
            username='student-roadmap', email='student-roadmap@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school,
        )
        StudentProfile.objects.create(user=student_user, school=self.school, assigned_counselor=counselor)
        self.client.force_authenticate(self.admin)
        template_response = self.client.post('/api/counselor-roadmap-templates/', {
            'name': 'School launch', 'description': 'Core onboarding', 'kind': 'school_management',
            'missions': [{'title': 'Review student safeguarding', 'sequence': 1, 'due_days': 3, 'is_required': True}],
        }, format='json')
        self.assertEqual(template_response.status_code, status.HTTP_201_CREATED)
        assigned = self.client.post('/api/counselor-roadmaps/', {
            'counselor': counselor.id, 'template': template_response.data['id'], 'title': '',
        }, format='json')
        self.assertEqual(assigned.status_code, status.HTTP_201_CREATED)
        roadmap_id = assigned.data['id']
        mission_id = assigned.data['missions'][0]['id']

        self.client.force_authenticate(counselor)
        submitted = self.client.post(f'/api/counselor-roadmaps/{roadmap_id}/submit-mission/', {
            'mission': mission_id, 'counselor_note': 'Safeguarding workflow reviewed.',
        }, format='json')
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertEqual(submitted.data['missions'][0]['status'], CounselorRoadmapMission.Status.SUBMITTED)
        self.assertEqual(submitted.data['missions'][0]['counselor_note'], 'Safeguarding workflow reviewed.')

        self.client.force_authenticate(self.admin)
        approved = self.client.post(f'/api/counselor-roadmaps/{roadmap_id}/review-mission/', {
            'mission': mission_id, 'decision': 'approve',
        }, format='json')
        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        self.assertEqual(approved.data['status'], CounselorRoadmap.Status.COMPLETED)
        self.assertEqual(approved.data['progress_percent'], 100)
        self.assertEqual(approved.data['missions'][0]['status'], CounselorRoadmapMission.Status.APPROVED)
        self.assertEqual(
            approved.data['missions'][0]['approved_by_name'],
            self.admin.get_full_name() or self.admin.username,
        )
        self.assertEqual(XPTransaction.objects.count(), 0)
        self.assertEqual(CounselorRoadmapMission.objects.get(pk=mission_id).status, CounselorRoadmapMission.Status.APPROVED)

    def test_counselor_can_select_an_active_template_and_start_own_roadmap(self):
        counselor = self.create_counselor(1)
        other_counselor = self.create_counselor(2)
        self.client.force_authenticate(self.admin)
        template_response = self.client.post('/api/counselor-roadmap-templates/', {
            'name': 'Professional foundations',
            'description': 'Counselor onboarding milestones',
            'kind': 'professional_onboarding',
            'missions': [
                {'title': 'Set advising standards', 'sequence': 1, 'due_days': 7, 'is_required': True},
            ],
        }, format='json')
        self.assertEqual(template_response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(counselor)
        templates = self.client.get('/api/counselor-roadmap-templates/')
        self.assertEqual(templates.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in templates.data['results']], [template_response.data['id']])

        started = self.client.post('/api/counselor-roadmaps/', {
            'counselor': other_counselor.id,
            'template': template_response.data['id'],
            'title': 'My professional plan',
        }, format='json')
        self.assertEqual(started.status_code, status.HTTP_201_CREATED)
        roadmap = CounselorRoadmap.objects.get(pk=started.data['id'])
        self.assertEqual(roadmap.counselor, counselor)
        self.assertEqual(roadmap.school, counselor.school)
        self.assertEqual(roadmap.assigned_by, counselor)

        duplicate = self.client.post('/api/counselor-roadmaps/', {
            'template': template_response.data['id'],
        }, format='json')
        self.assertEqual(duplicate.status_code, status.HTTP_409_CONFLICT)

        custom = self.client.post('/api/counselor-roadmaps/', {
            'title': 'My school management plan',
            'kind': 'school_management',
            'missions': [
                {'title': 'Audit the school onboarding flow'},
                {'title': 'Publish the monthly counselor report'},
            ],
        }, format='json')
        self.assertEqual(custom.status_code, status.HTTP_201_CREATED)
        custom_roadmap = CounselorRoadmap.objects.get(pk=custom.data['id'])
        self.assertIsNone(custom_roadmap.template)
        self.assertEqual(custom_roadmap.counselor, counselor)
        self.assertEqual(list(custom_roadmap.missions.values_list('sequence', flat=True)), [1, 2])

        denied_template_create = self.client.post('/api/counselor-roadmap-templates/', {
            'name': 'Unauthorized template',
            'kind': 'school_management',
            'missions': [{'title': 'Not allowed', 'sequence': 1, 'due_days': 1}],
        }, format='json')
        self.assertEqual(denied_template_create.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_360_access_is_audited(self):
        student_user = User.objects.create_user(
            username='student-360', email='student-360@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school,
        )
        profile = StudentProfile.objects.create(user=student_user, school=self.school)
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/students/{profile.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(ProductAuditEvent.objects.filter(action='student_360.viewed', target_id=str(profile.id)).exists())
