"""Set a counselor's weekly meeting hours and notice, and invite students to meetings, in one safe re-runnable step.

Uses the code the API uses: MeetingSchedule + fill_schedule for the hours, create_staff_booking for the
invitations (pending until the student confirms, with the site notice, email and Telegram message).
Running it again changes nothing: a meeting of the same counselor, student and start is skipped.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.users.models import User

from ...meeting_service import create_staff_booking
from ...meetings import MAX_MIN_NOTICE_HOURS, MAX_REPEAT_DAYS, fill_schedule
from ...models import Booking, MeetingSchedule
from ...scoping import visible_students
from ...views.portal import BOOKING_STAFF_ROLES

DAYS = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}


def parse_zone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise CommandError(f'Unknown time zone "{name}".')


def parse_date(value, flag):
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise CommandError(f'{flag} must be YYYY-MM-DD.')


def parse_clock(value):
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise CommandError(f'"{value}" is not a HH:MM time.')


def parse_weekly(text):
    """'mon=09:00-12:00,tue=14:00-00:00' -> [(weekday, begin, end)]; an end of 00:00 is midnight."""
    ranges = []
    for part in filter(None, (piece.strip() for piece in text.split(','))):
        day, _, span = part.partition('=')
        begin, _, end = span.partition('-')
        if day.strip().lower() not in DAYS or not begin or not end:
            raise CommandError(f'"{part}" is not <day>=HH:MM-HH:MM (days: {", ".join(DAYS)}).')
        ranges.append((DAYS[day.strip().lower()], parse_clock(begin.strip()), parse_clock(end.strip())))
    if not ranges:
        raise CommandError('--weekly is empty.')
    return ranges


def to_server_hours(ranges, zone, reference):
    """The weekly ranges as the server's clock stores them ({"0": [["09:00", "12:00"]]}).

    Hours are kept on the server (Tashkent) clock; ranges given in another zone are converted on the
    first matching date at or after `reference`, and must stay on the same weekday there.
    """
    server = ZoneInfo(settings.TIME_ZONE)
    hours = {}
    for weekday, begin, end in ranges:
        day = reference + timedelta(days=(weekday - reference.weekday()) % 7)
        start_at = datetime.combine(day, begin, tzinfo=zone)
        end_at = datetime.combine(day, end, tzinfo=zone)
        if end <= begin:
            end_at += timedelta(days=1)  # 00:00 is midnight at the end of the day
        start_local, end_local = start_at.astimezone(server), end_at.astimezone(server)
        midnight = datetime.combine(start_local.date() + timedelta(days=1), time(0, 0), tzinfo=server)
        if start_local.weekday() != weekday or end_local > midnight:
            raise CommandError(
                f'{DAYS_NAMES[weekday]} {begin:%H:%M}-{end:%H:%M} {zone.key} does not fit inside one day on the '
                f'server clock ({settings.TIME_ZONE}). Give the hours in {settings.TIME_ZONE} instead.'
            )
        close = '00:00' if end_local == midnight else end_local.strftime('%H:%M')
        hours.setdefault(str(weekday), []).append([start_local.strftime('%H:%M'), close])
    for spans in hours.values():
        spans.sort()
    return hours


DAYS_NAMES = {number: name for name, number in DAYS.items()}


class Command(BaseCommand):
    help = 'Set a counselor\'s weekly meeting hours and minimum notice, and invite students to meetings (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--counselor', required=True, help='Username of the counselor (or other staff member).')
        parser.add_argument('--tz', default=settings.TIME_ZONE, help='IANA zone the --weekly hours are written in.')
        parser.add_argument('--weekly', help='Weekly hours: "mon=09:00-12:00,wed=14:00-00:00" (end 00:00 = midnight).')
        parser.add_argument('--from', dest='from_date', help='First day to generate slots for (YYYY-MM-DD).')
        parser.add_argument('--to', dest='to_date', help='Last day to generate slots for (YYYY-MM-DD).')
        parser.add_argument('--notice-hours', type=int, help=f'Students must book at least N hours ahead (0-{MAX_MIN_NOTICE_HOURS}).')
        parser.add_argument('--book', action='append', default=[], help='"<student username>|YYYY-MM-DD HH:MM|<minutes>|<topic>"; repeatable.')
        parser.add_argument('--book-tz', default=settings.TIME_ZONE, help='IANA zone of the --book times.')
        parser.add_argument('--dry-run', action='store_true', help='Do everything, check everything, save nothing, send nothing.')

    def handle(self, *args, **options):
        counselor = User.objects.filter(username=options['counselor']).first()
        if counselor is None or counselor.role not in BOOKING_STAFF_ROLES or not counselor.school_id:
            raise CommandError(f'"{options["counselor"]}" is not a staff member of a school.')
        zone, book_zone = parse_zone(options['tz']), parse_zone(options['book_tz'])
        notice = options['notice_hours']
        if notice is not None and not 0 <= notice <= MAX_MIN_NOTICE_HOURS:
            raise CommandError(f'--notice-hours must be between 0 and {MAX_MIN_NOTICE_HOURS}.')
        first = parse_date(options['from_date'], '--from') if options['from_date'] else None
        last = parse_date(options['to_date'], '--to') if options['to_date'] else None
        if (first and last and (last < first or (last - first).days >= MAX_REPEAT_DAYS)) or bool(first) != bool(last):
            raise CommandError('Give --from and --to together, with --to on or after --from and at most 12 weeks apart.')
        weekly = parse_weekly(options['weekly']) if options['weekly'] else None
        if weekly and not first:
            raise CommandError('--weekly needs --from and --to.')
        bookings = [self.parse_booking(raw, book_zone) for raw in options['book']]
        if weekly is None and notice is None and not bookings:
            raise CommandError('Nothing to do: give --weekly, --notice-hours or --book.')

        problems = []
        dry = options['dry_run']
        with transaction.atomic():
            User.objects.select_for_update().get(pk=counselor.pk)
            if weekly is not None or notice is not None:
                self.set_schedule(counselor, weekly, zone, first, last, notice)
            for student_username, start, minutes, topic in bookings:
                problem = self.book(counselor, student_username, start, minutes, topic)
                if problem:
                    problems.append(problem)
            if dry:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('Dry run: nothing was saved or sent.'))
        if problems:
            raise CommandError(f'{len(problems)} problem(s):\n' + '\n'.join(problems))

    @staticmethod
    def parse_booking(raw, zone):
        parts = [part.strip() for part in raw.split('|', 3)]
        if len(parts) != 4 or not all(parts):
            raise CommandError(f'--book "{raw}" must be "<student username>|YYYY-MM-DD HH:MM|<minutes>|<topic>".')
        try:
            start = datetime.strptime(parts[1], '%Y-%m-%d %H:%M').replace(tzinfo=zone)
            minutes = int(parts[2])
        except ValueError:
            raise CommandError(f'--book "{raw}": the time must be YYYY-MM-DD HH:MM and the length a number of minutes.')
        return parts[0], start, minutes, parts[3]

    def set_schedule(self, counselor, weekly, zone, first, last, notice):
        schedule = MeetingSchedule.objects.filter(participant=counselor).first() or MeetingSchedule(participant=counselor)
        if notice is not None:
            schedule.min_notice_hours = notice
        if weekly is None:
            schedule.save()
            self.stdout.write(f'Minimum notice for {counselor.username}: {schedule.min_notice_hours} hours.')
            return
        hours = to_server_hours(weekly, zone, first)
        schedule.hours = hours
        schedule.generated_until = None
        schedule.save()
        before = counselor.meeting_availability.count()
        fill_schedule(schedule, replace=True, first_day=first, until=last)
        added = counselor.meeting_availability.count() - before
        self.stdout.write(
            f'Weekly hours for {counselor.username} set ({settings.TIME_ZONE} clock): {hours}; '
            f'notice {schedule.min_notice_hours} h; {added} new slot(s) from {first} to {last}.'
        )

    def book(self, counselor, student_username, start, minutes, topic):
        """Invite one student; returns a problem text, or None when it was created or already exists."""
        label = f'{student_username} {timezone.localtime(start):%Y-%m-%d %H:%M}'
        profile = visible_students(counselor).filter(user__username=student_username).first()
        if profile is None:
            return f'{label}: "{student_username}" is not one of {counselor.username}\'s students (refused).'
        if Booking.objects.filter(participant=counselor, student=profile, starts_at=start).exists():
            self.stdout.write(f'Skipped (already booked): {label}')
            return None
        try:
            booking = create_staff_booking(counselor, profile, starts_at=start, duration_minutes=minutes, topic=topic)
        except ValidationError as error:
            return f'{label}: {error.detail}'
        slot = ' (took an open slot)' if booking.availability_slot_id else ''
        self.stdout.write(f'Invited (waiting for the student): {label}, {minutes} min, "{topic}"{slot}')
        return None
