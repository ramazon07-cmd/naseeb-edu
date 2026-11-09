from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.admissions.essay_lab.streak import MAX_SAVE_CREDIT as MAX_WORDS_PER_SAVE, goal_met
from apps.admissions.models import EssayCheckpoint, EssayWritingDay


def reconstruct_days(user_id, checkpoints):
    """{day: (net, peak)} of new text per Tashkent day, from a student's checkpoints in time order.

    A checkpoint is a sample of one tab's word count (at most one per 10 minutes while
    writing), so this follows the same net/peak rule as live saves but only sees the
    samples: peaks between samples are missed. A tab's first sample, samples made by
    feedback, and the first sample after a restore only set the baseline.
    """
    previous = {}
    after_restore = set()
    days = {}
    for tab_id, created_at, word_count, reason, kind, author_id in checkpoints:
        own = kind == EssayCheckpoint.Kind.EDIT and author_id in (None, user_id)
        before = previous.get(tab_id)
        if own and before is not None and tab_id not in after_restore:
            delta = min(word_count - before, MAX_WORDS_PER_SAVE)
            net, peak = days.get(timezone.localdate(created_at), (0, 0))
            net = max(0, net + delta)
            days[timezone.localdate(created_at)] = (net, max(peak, net))
        previous[tab_id] = word_count
        if reason == EssayCheckpoint.Reason.RESTORE:
            after_restore.add(tab_id)
        else:
            after_restore.discard(tab_id)
    return days


class Command(BaseCommand):
    help = (
        'Estimate past writing days for the Essay Lab streak from checkpoint word counts. '
        'Dry run unless --apply is given; never changes a day that already has a row.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=500, help='Students per batch.')
        parser.add_argument('--apply', action='store_true', help='Write the days (default: only report).')
        parser.add_argument('--since', help='Only days on or after this date (YYYY-MM-DD).')

    def handle(self, *args, apply=False, since=None, batch_size=500, **options):
        batch_size = max(1, batch_size)
        try:
            first_day = date.fromisoformat(since) if since else None
        except ValueError as error:
            raise CommandError('--since must be a date like 2026-09-01.') from error
        today = timezone.localdate()
        user_ids = sorted(set(
            EssayCheckpoint.objects.order_by().values_list('essay__student__user_id', flat=True).distinct()
        ))
        found = created = skipped = 0
        for start in range(0, len(user_ids), batch_size):
            chunk = user_ids[start:start + batch_size]
            checkpoints = {user_id: [] for user_id in chunk}
            rows = (
                EssayCheckpoint.objects.filter(essay__student__user_id__in=chunk)
                .order_by('created_at', 'id')
                .values_list('essay__student__user_id', 'tab_id', 'created_at', 'word_count', 'reason', 'kind',
                             'author_id')
            )
            for user_id, *sample in rows.iterator():
                checkpoints[user_id].append(sample)
            existing = {}
            for user_id, day in EssayWritingDay.objects.filter(user_id__in=chunk).values_list('user_id', 'date'):
                existing.setdefault(user_id, set()).add(day)
            new_rows = []
            for user_id, samples in checkpoints.items():
                for day, (net, peak) in reconstruct_days(user_id, samples).items():
                    if peak == 0 or day >= today or (first_day and day < first_day):
                        continue
                    found += 1
                    if day in existing.get(user_id, ()):
                        skipped += 1
                        continue
                    new_rows.append(EssayWritingDay(
                        user_id=user_id, date=day, words_net=net, words_peak=peak, goal_met=goal_met(peak, 0),
                    ))
            if apply and new_rows:
                before = EssayWritingDay.objects.filter(user_id__in=chunk).count()
                EssayWritingDay.objects.bulk_create(new_rows, ignore_conflicts=True)
                created += EssayWritingDay.objects.filter(user_id__in=chunk).count() - before
            elif not apply:
                created += len(new_rows)
        verb = 'Created' if apply else 'Would create'
        self.stdout.write(
            f'{verb} {created} writing days from {len(user_ids)} students '
            f'({found} reconstructed, {skipped} skipped because a day already has data).'
        )
