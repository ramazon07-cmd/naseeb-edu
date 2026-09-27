"""Role isolation: accounts, profiles, photos and workspace provisioning."""
import io
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from apps.users.models import User
from ..models import School, StudentProfile
from .base import RoleIsolationBase


class AccountRoleIsolationTests(RoleIsolationBase):
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
        # The endpoint is gone for everyone (accounts are provisioned by staff).
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.student_a_user)
        authenticated = self.client.post(
            '/api/users/register/',
            {'username': 'public-user', 'email': 'public-user@example.com', 'password': 'VeryStrongPass123!'},
            format='json',
        )
        self.assertEqual(authenticated.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(User.objects.filter(username='public-user').exists())

    def test_student_only_lists_own_profile(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.get('/api/students/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in self.results(response)], [self.student_a.id])

    def test_student_can_update_academic_and_goal_profile_details(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.patch(
            f'/api/students/{self.student_a.id}/',
            {
                'grade': '11',
                'gpa': '4.50',
                'ielts_score': '7.5',
                'sat_score': 1420,
                'target_major': 'Computer Science',
                'target_countries': 'United States, Canada',
                'budget_usd': 30000,
                'scholarship_needed': True,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.grade, '11')
        self.assertEqual(str(self.student_a.gpa), '4.50')
        self.assertEqual(str(self.student_a.ielts_score), '7.5')
        self.assertEqual(self.student_a.sat_score, 1420)
        self.assertEqual(self.student_a.target_major, 'Computer Science')
        self.assertEqual(self.student_a.target_countries, 'United States, Canada')

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

    def test_organization_cannot_delete_own_student(self):
        self.client.force_authenticate(self.organization)
        user_id = self.student_a_user.id
        response = self.client.delete(f'/api/students/{self.student_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(User.objects.filter(id=user_id, is_active=True).exists())

    def test_counselor_cannot_create_account_for_another_school(self):
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
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(User.objects.filter(username='school-b-admin').exists())

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

    def test_only_the_student_can_change_their_own_profile_photo(self):
        """Photos are private uploads: the owner writes, the scope decides who reads."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from PIL import Image

        buffer = io.BytesIO()
        Image.new('RGB', (4, 4), 'white').save(buffer, format='PNG')
        # A real image: photos are now content-checked, not just by extension.
        png = SimpleUploadedFile('face.png', buffer.getvalue(), content_type='image/png')
        self.client.force_authenticate(self.student_b_user)
        stranger = self.client.post(
            f'/api/students/{self.student_a.id}/photo/',
            {'photo': png},
            format='multipart',
        )
        self.assertIn(stranger.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

        self.client.force_authenticate(self.student_a_user)
        missing = self.client.get(f'/api/students/{self.student_a.id}/photo/')
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)

        wrong_type = self.client.post(
            f'/api/students/{self.student_a.id}/photo/',
            {'photo': SimpleUploadedFile('notes.txt', b'hello', content_type='text/plain')},
            format='multipart',
        )
        self.assertEqual(wrong_type.status_code, status.HTTP_400_BAD_REQUEST)

        png.seek(0)
        saved = self.client.post(
            f'/api/students/{self.student_a.id}/photo/',
            {'photo': png},
            format='multipart',
        )
        self.assertEqual(saved.status_code, status.HTTP_200_OK)
        self.assertTrue(saved.data['has_photo'])
        self.assertNotIn('photo', saved.data, 'The private file must never be serialized as a URL.')
        self.student_a.refresh_from_db()
        self.assertTrue(self.student_a.photo)
        served = self.client.get(f'/api/students/{self.student_a.id}/photo/')
        self.assertEqual(served.status_code, status.HTTP_200_OK)
        # Unversioned URLs must revalidate; ?v=<photo_version> is cacheable.
        self.assertEqual(served['Cache-Control'], 'private, no-cache')
        # Consume (not close()) the stream: the test client's wrapper closes it without
        # firing close_old_connections, which would drop the PostgreSQL test connection.
        b''.join(served.streaming_content)
        self.student_a.photo.delete(save=True)

    def test_counselor_account_requires_school_and_is_scoped_to_it(self):
        admin_user = User.objects.create_user(
            username='school-link-admin',
            email='school-link-admin@example.com',
            password='StrongPass123!',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(admin_user)
        missing_school = self.client.post(
            '/api/users/accounts/',
            {
                'username': 'no-school-counselor',
                'email': 'no-school-counselor@example.com',
                'role': User.Role.COUNSELOR,
            },
            format='json',
        )
        self.assertEqual(missing_school.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('school', missing_school.data)
        created = self.client.post(
            '/api/users/accounts/',
            {
                'username': 'school-a-counselor',
                'email': 'school-a-counselor@example.com',
                'role': User.Role.COUNSELOR,
                'school': self.school_a.id,
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(created.data['school'], self.school_a.id)

        self.client.force_authenticate(self.counselor)
        schools = self.results(self.client.get('/api/schools/'))
        self.assertEqual([school['id'] for school in schools], [self.school_a.id])
        users = self.results(self.client.get('/api/users/accounts/'))
        self.assertTrue(all(item['school'] == self.school_a.id for item in users))

    def test_unassigned_new_student_can_load_every_dashboard_resource(self):
        new_user = User.objects.create_user(
            username='new-admin-student',
            email='new-admin-student@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
        )
        StudentProfile.objects.create(user=new_user, level=0, xp_total=0)
        self.client.force_authenticate(new_user)

        paths = (
            'dashboard/stats', 'students', 'tasks', 'applications', 'documents', 'essays',
            'achievements', 'researches', 'projects', 'internships', 'activities', 'honors',
            'recommendations', 'notifications', 'universities', 'roadmap-missions',
            'bookings', 'message-channels', 'program-services',
            'scholarships', 'opportunity-programs', 'store-items',
            'student-team',
        )
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(f'/api/{path}/')
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_non_student_roles_cannot_open_student_only_portal_endpoints(self):
        self.client.force_authenticate(self.organization)
        self.assertEqual(self.client.get('/api/roadmap-missions/').status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.post('/api/roadmap-missions/', {}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.get('/api/bookings/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get('/api/student-messages/').status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_creates_individual_counselor_with_unique_private_workspace(self):
        admin_user = User.objects.create_user(
            username='workspace-admin', email='workspace-admin@example.com',
            password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.client.force_authenticate(admin_user)
        response = self.client.post(
            '/api/users/accounts/create-individual-counselor/',
            {
                'username': 'independent-counselor',
                'email': 'independent@example.com',
                'password': 'StrongPass123!',
                'first_name': 'Aziza',
                'last_name': 'Karimova',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        counselor = User.objects.get(username='independent-counselor')
        workspace = counselor.school
        self.assertEqual(workspace.workspace_type, School.WorkspaceType.INDIVIDUAL)
        self.assertEqual(workspace.owner_counselor, counselor)
        self.assertTrue(workspace.code.startswith('individual-independent-counselor'))
        self.assertEqual(response.data['school_workspace_type'], School.WorkspaceType.INDIVIDUAL)

        self.client.force_authenticate(self.counselor)
        forbidden = self.client.post(
            '/api/users/accounts/create-individual-counselor/',
            {
                'username': 'forbidden-counselor', 'email': 'forbidden@example.com',
                'password': 'StrongPass123!', 'first_name': 'No',
            },
            format='json',
        )
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

    def test_individual_counselor_transfer_requires_students_to_match_target_school(self):
        admin_user = User.objects.create_user(
            username='transfer-admin', email='transfer-admin@example.com',
            password='StrongPass123!', role=User.Role.ADMIN,
        )
        workspace = School.objects.create(
            name='Private counselor workspace', code='private-counselor',
            workspace_type=School.WorkspaceType.INDIVIDUAL,
        )
        counselor = User.objects.create_user(
            username='transfer-counselor', email='transfer-counselor@example.com',
            password='StrongPass123!', role=User.Role.COUNSELOR, school=workspace,
        )
        workspace.owner_counselor = counselor
        workspace.save(update_fields=['owner_counselor'])
        private_student_user = User.objects.create_user(
            username='private-student', email='private-student@example.com',
            password='StrongPass123!', role=User.Role.STUDENT, school=workspace,
        )
        private_profile = StudentProfile.objects.create(
            user=private_student_user, school=workspace, school_name=workspace.name,
            assigned_counselor=counselor,
        )
        self.client.force_authenticate(admin_user)
        blocked = self.client.post(
            f'/api/users/accounts/{counselor.id}/transfer-school/',
            {'school': self.school_a.id}, format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_409_CONFLICT)
        private_profile.assigned_counselor = None
        private_profile.save(update_fields=['assigned_counselor'])
        transferred = self.client.post(
            f'/api/users/accounts/{counselor.id}/transfer-school/',
            {'school': self.school_a.id}, format='json',
        )
        self.assertEqual(transferred.status_code, status.HTTP_200_OK)
        counselor.refresh_from_db()
        workspace.refresh_from_db()
        self.assertEqual(counselor.school, self.school_a)
        self.assertFalse(workspace.is_active)
