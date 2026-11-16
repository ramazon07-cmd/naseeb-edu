"""Send the current card (with buttons) for every open, upcoming meeting, to the staff member and the student.

For meetings whose earlier Telegram messages went out as plain text. Each card is queued once per
meeting state, so running the command again sends nothing new.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.admissions.models import Booking
from apps.telegram_bot.meeting_cards import _state_header, buttons_for, staff_card, student_card
from apps.telegram_bot.models import StudentTelegram, TelegramLink, TelegramOutbox


class Command(BaseCommand):
    help = 'Queue a fresh Telegram card with buttons for every open upcoming meeting.'

    def add_arguments(self, parser):
        parser.add_argument('--participant', type=int, help='Only meetings with this staff user id.')
        parser.add_argument('--dry-run', action='store_true', help='Count what would be sent, send nothing.')

    def handle(self, *args, participant=None, dry_run=False, **options):
        bookings = Booking.objects.filter(
            status__in=Booking.OPEN_STATUSES, starts_at__gt=timezone.now(), participant__isnull=False,
        ).select_related('student__user', 'participant').order_by('starts_at')
        if participant:
            bookings = bookings.filter(participant_id=participant)
        staff_links = {link.user_id: link for link in TelegramLink.objects.filter(is_active=True)}
        student_links = {link.user_id: link for link in StudentTelegram.objects.filter(is_active=True)}
        sent = {'staff': 0, 'student': 0}
        for booking in bookings:
            targets = (
                ('staff', staff_links.get(booking.participant_id), staff_card),
                ('student', student_links.get(booking.student.user_id), student_card),
            )
            for viewer, link, render in targets:
                if link is None:
                    continue
                key = f'resend:{booking.pk}:{booking.status}:{int(booking.starts_at.timestamp())}:{viewer}'
                if TelegramOutbox.objects.filter(key=key).exists():
                    continue
                if not dry_run:
                    TelegramOutbox.objects.create(
                        key=key, chat_id=link.chat_id, booking=booking,
                        text=render(booking, link.language, _state_header(booking, viewer)),
                        buttons=buttons_for(booking, viewer, link.language),
                    )
                sent[viewer] += 1
        verb = 'would send' if dry_run else 'queued'
        self.stdout.write(f"{verb}: {sent['staff']} staff cards, {sent['student']} student cards")
