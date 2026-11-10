from datetime import timedelta
from unittest import mock

from django.core import mail, signing
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.users.google import STATE_SALT

from ..models import Booking, MeetingAvailability
from .base import RoleIsolationBase

GOOGLE = dict(GOOGLE_OAUTH_CLIENT_ID='client-id', GOOGLE_OAUTH_CLIENT_SECRET='secret', FRONTEND_URL='https://app.example.com')
MAIL = dict(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', FRONTEND_URL='https://app.example.com')


@override_settings(**GOOGLE)
class GoogleConnectTests(RoleIsolationBase):
    def state(self, user):
        return signing.dumps({'u': user.pk, 'pv': user.password_version}, salt=STATE_SALT)

    def callback(self, state, identity=('sub-1', 'student@gmail.com')):
        with mock.patch('apps.users.google.exchange_code', return_value=identity):
            return self.client.get('/api/users/google/callback/', {'code': 'c', 'state': state})

    def test_start_needs_a_signed_in_user_and_returns_a_google_url(self):
        self.assertEqual(self.client.post('/api/users/google/start/').status_code, 401)
        self.client.force_authenticate(self.student_a_user)
        url = self.client.post('/api/users/google/start/').data['url']
        self.assertTrue(url.startswith('https://accounts.google.com/'))
        self.assertIn('scope=openid+email', url)

    def test_callback_links_the_verified_email_to_the_user_who_started(self):
        response = self.callback(self.state(self.student_a_user))
        self.assertEqual(response['Location'], 'https://app.example.com/meetings?google=connected')
        self.student_a_user.refresh_from_db()
        self.assertEqual(self.student_a_user.google_email, 'student@gmail.com')
        self.client.force_authenticate(self.student_a_user)
        me = self.client.get('/api/users/accounts/me/').data
        self.assertEqual((me['google_email'], me['google_connect_enabled']), ('student@gmail.com', True))

    def test_callback_refuses_a_forged_or_stale_state_and_an_unverified_identity(self):
        forged = signing.dumps({'u': self.student_a_user.pk, 'pv': 1}, salt='other')
        stale = self.state(self.student_a_user)
        self.student_a_user.password_version += 1
        self.student_a_user.save(update_fields=['password_version'])
        for state, identity in ((forged, ('s', 'a@gmail.com')), (stale, ('s', 'a@gmail.com')), ('', ('s', 'a@gmail.com')),
                                (self.state(self.student_a_user), None)):
            response = self.callback(state, identity)
            self.assertEqual(response['Location'], 'https://app.example.com/meetings?google=failed')
        self.student_a_user.refresh_from_db()
        self.assertEqual(self.student_a_user.google_email, '')

    def test_google_email_cannot_be_set_through_the_profile(self):
        self.client.force_authenticate(self.student_a_user)
        self.client.patch('/api/users/accounts/me/', {'google_email': 'evil@example.com'}, format='json')
        self.student_a_user.refresh_from_db()
        self.assertEqual(self.student_a_user.google_email, '')

    def test_meetings_changes_need_a_connected_account_but_reads_do_not(self):
        start = (timezone.now() + timedelta(days=3)).replace(minute=0, second=0, microsecond=0)
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=start, duration_minutes=45)
        payload = {'participant': self.counselor.id, 'topic': 'Essay', 'starts_at': start.isoformat(),
                   'duration_minutes': 45, 'availability_slot': slot.id}
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.get('/api/bookings/').status_code, 200)
        self.assertEqual(self.client.post('/api/bookings/', payload, format='json').status_code, 403)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.put('/api/bookings/availability/weekly/', {'duration_minutes': 45, 'hours': {}}, format='json').status_code, 403)
        self.student_a_user.google_email = 'student@gmail.com'
        self.student_a_user.save(update_fields=['google_email'])
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.post('/api/bookings/', payload, format='json').status_code, 201)

    @override_settings(GOOGLE_OAUTH_CLIENT_ID='')
    def test_without_google_credentials_meetings_work_as_before(self):
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.post('/api/users/google/start/').status_code, 503)
        self.assertFalse(self.client.get('/api/users/accounts/me/').data['google_connect_enabled'])


@override_settings(**MAIL)
class MeetingEmailTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.student_a_user.google_email = 'student@gmail.com'
        self.student_a_user.save(update_fields=['google_email'])
        self.counselor.google_email = 'counselor@gmail.com'
        self.counselor.save(update_fields=['google_email'])
        self.start = (timezone.now() + timedelta(hours=5)).replace(second=0, microsecond=0)

    def test_request_and_confirmation_are_emailed_to_the_other_side(self):
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        self.client.force_authenticate(self.student_a_user)
        with self.captureOnCommitCallbacks(execute=True):
            booked = self.client.post('/api/bookings/', {
                'participant': self.counselor.id, 'topic': 'Essay review', 'starts_at': self.start.isoformat(),
                'duration_minutes': 45, 'availability_slot': slot.id,
            }, format='json', HTTP_ACCEPT_LANGUAGE='uz')
        self.assertEqual(booked.status_code, 201, booked.data)
        self.assertEqual([message.to for message in mail.outbox], [['counselor@gmail.com']])
        self.assertIn('Essay review', mail.outbox[0].body)
        self.assertIn('https://app.example.com/meetings', mail.outbox[0].body)
        self.client.force_authenticate(self.counselor)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/api/bookings/{booked.data['id']}/approve/")
        self.assertEqual(mail.outbox[-1].to, ['student@gmail.com'])

    def test_a_placeholder_address_gets_no_email(self):
        from ..meeting_mail import meeting_address
        self.student_a_user.google_email = ''
        self.student_a_user.email = 'x@students.naseeb.invalid'
        self.assertEqual(meeting_address(self.student_a_user), '')

    def test_reminder_goes_out_once_per_start_time(self):
        booking = Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Essay',
                                         starts_at=self.start, duration_minutes=45, status=Booking.Status.APPROVED)
        Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Later',
                               starts_at=self.start + timedelta(days=3), duration_minutes=45, status=Booking.Status.APPROVED)
        Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Pending',
                               starts_at=self.start + timedelta(hours=2), duration_minutes=45)
        call_command('send_meeting_reminders')
        call_command('send_meeting_reminders')
        self.assertEqual(sorted(message.to[0] for message in mail.outbox), ['counselor@gmail.com', 'student@gmail.com'])
        booking.starts_at += timedelta(hours=1)
        booking.save(update_fields=['starts_at'])
        call_command('send_meeting_reminders')
        self.assertEqual(len(mail.outbox), 4)
