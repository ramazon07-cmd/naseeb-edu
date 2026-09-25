"""Role isolation: support tickets."""
from rest_framework import status
from apps.users.models import User
from ..models import SupportTicket
from .base import RoleIsolationBase


class SupportRoleIsolationTests(RoleIsolationBase):
    def test_support_requesters_create_and_only_list_own_tickets(self):
        other_ticket = SupportTicket.objects.create(
            requester=self.student_b_user,
            category=SupportTicket.Category.TECHNICAL,
            subject='Other student ticket',
            message='Private issue from another requester.',
        )
        self.client.force_authenticate(self.student_a_user)
        created = self.client.post(
            '/api/support-tickets/',
            {
                'category': SupportTicket.Category.APPLICATION,
                'subject': 'Application portal issue',
                'message': 'I cannot open my application checklist.',
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        ticket = SupportTicket.objects.get(id=created.data['id'])
        self.assertEqual(ticket.requester, self.student_a_user)
        self.assertEqual(ticket.status, SupportTicket.Status.OPEN)

        listed = self.results(self.client.get('/api/support-tickets/'))
        self.assertEqual([item['id'] for item in listed], [ticket.id])
        self.assertNotEqual(ticket.id, other_ticket.id)

    def test_support_requester_cannot_spoof_admin_response_or_update_ticket(self):
        self.client.force_authenticate(self.student_a_user)
        spoofed = self.client.post(
            '/api/support-tickets/',
            {
                'category': SupportTicket.Category.ACCOUNT,
                'subject': 'Spoofed response',
                'message': 'Please help.',
                'status': SupportTicket.Status.RESOLVED,
                'admin_response': 'Fake admin response',
            },
            format='json',
        )
        self.assertEqual(spoofed.status_code, status.HTTP_400_BAD_REQUEST)

        ticket = SupportTicket.objects.create(
            requester=self.student_a_user,
            category=SupportTicket.Category.ACCOUNT,
            subject='Account help',
            message='Please help with my account.',
        )
        updated = self.client.patch(
            f'/api/support-tickets/{ticket.id}/',
            {'status': SupportTicket.Status.RESOLVED, 'admin_response': 'Not allowed'},
            format='json',
        )
        self.assertEqual(updated.status_code, status.HTTP_403_FORBIDDEN)

    def test_counselor_staff_flag_does_not_grant_global_support_access(self):
        self.counselor.is_staff = True
        self.counselor.save(update_fields=['is_staff'])
        own_ticket = SupportTicket.objects.create(
            requester=self.counselor,
            category=SupportTicket.Category.OTHER,
            subject='Counselor support request',
            message='I need workflow assistance.',
        )
        SupportTicket.objects.create(
            requester=self.student_a_user,
            category=SupportTicket.Category.TECHNICAL,
            subject='Student-only ticket',
            message='Private student issue.',
        )
        self.client.force_authenticate(self.counselor)
        listed = self.results(self.client.get('/api/support-tickets/'))
        self.assertEqual([item['id'] for item in listed], [own_ticket.id])

    def test_admin_reads_all_tickets_and_response_uses_in_page_unread_state(self):
        admin_user = User.objects.create_user(
            username='product-admin',
            email='product-admin@example.com',
            password='StrongPass123!',
            role=User.Role.ADMIN,
        )
        student_ticket = SupportTicket.objects.create(
            requester=self.student_a_user,
            category=SupportTicket.Category.TECHNICAL,
            subject='Login page issue',
            message='The page is not loading correctly.',
        )
        SupportTicket.objects.create(
            requester=self.organization,
            category=SupportTicket.Category.BILLING,
            subject='School service question',
            message='Please clarify the service balance.',
        )

        self.client.force_authenticate(admin_user)
        listed = self.results(self.client.get('/api/support-tickets/'))
        self.assertEqual(len(listed), 2)
        response = self.client.patch(
            f'/api/support-tickets/{student_ticket.id}/',
            {
                'status': SupportTicket.Status.RESOLVED,
                'admin_response': 'Please clear the browser cache and sign in again.',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['has_unread_response'])
        self.assertEqual(response.data['responded_by'], admin_user.id)

        self.client.force_authenticate(self.student_a_user)
        own_ticket = self.client.get(f'/api/support-tickets/{student_ticket.id}/')
        self.assertTrue(own_ticket.data['has_unread_response'])
        viewed = self.client.post(f'/api/support-tickets/{student_ticket.id}/mark-viewed/', {}, format='json')
        self.assertEqual(viewed.status_code, status.HTTP_200_OK)
        self.assertFalse(viewed.data['has_unread_response'])

    def test_teacher_cannot_access_support_ticket_mvp(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(
            self.client.get('/api/support-tickets/').status_code,
            status.HTTP_403_FORBIDDEN,
        )
