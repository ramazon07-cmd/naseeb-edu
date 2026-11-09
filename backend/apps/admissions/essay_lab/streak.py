"""Writing streak: what a save adds to the student's day, and the streak read from those days.

A day is a Tashkent calendar day (`timezone.localdate`). Words are tracked as a
per-day running net of the text the student has on the page (deleting takes it
back, never below 0) and its peak; "words today" is the peak, so typing and
deleting in a loop cannot add up. What one save may add is capped by how long
the tab has been idle since its previous save, so a pasted block earns about
what typing could have produced. Writing time is the screen-time tracker's
`essay_lab` seconds, added to the day by the track endpoint on the server's
calendar. `goal_met` is kept by the two writes (words and seconds); reading the
streak never writes and never recomputes it.

Raw SQL here: the words upsert (`record_words`) and the seconds upsert
(`record_essay_seconds`), both `INSERT ... ON CONFLICT (user_id, date) DO UPDATE`
with CASE expressions, valid on PostgreSQL and SQLite.
"""

import logging
import math
import re
import time
from datetime import date, timedelta

from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from ..models import EssayWritingDay
from .doc import block_id, doc_stats

logger = logging.getLogger(__name__)

GOAL_WORDS = 100
GOAL_MINUTES = 10
GOAL_SECONDS = GOAL_MINUTES * 60
MIN_WORDS_WITH_MINUTES = 25
# What a save may add: seconds since the tab's previous save times TYPING_WORDS_PER_SECOND
# (90 words a minute), at most MAX_SAVE_CREDIT, with no minimum, so back-to-back saves earn
# nothing extra. This is a rate limit, not a paste detector: the daily 100 words need at
# least ~67 s of wall-clock time however they arrive. The default applies when there is no
# earlier save to measure from.
TYPING_WORDS_PER_SECOND = 1.5
MAX_SAVE_CREDIT = 60
DEFAULT_SAVE_CREDIT = 30
SECONDS_REPORT_SLACK = 10
SECONDS_FIRST_REPORT = 30
SECONDS_LOCK_TTL = 5
SECONDS_LOCK_TRIES = 4
SECONDS_LOCK_WAIT = 0.02
SECONDS_LAST_REPORT_TTL = 3600
# record_essay_seconds credits a batch dated up to this many days back to its own date.
SECONDS_BACKDATE_DAYS = 7
SCREEN_TIME_PAGE = 'essay_lab'

FIRE = 'fire'
EMBER = 'ember'
MONTH_RE = re.compile(r'^(\d{4})-(\d{2})$')


def save_credit_cap(previous_save_at, now):
    if previous_save_at is None:
        return DEFAULT_SAVE_CREDIT
    idle = (now - previous_save_at).total_seconds()
    if idle < 0:
        return DEFAULT_SAVE_CREDIT
    return min(MAX_SAVE_CREDIT, math.ceil(idle * TYPING_WORDS_PER_SECOND))


def goal_met(words, seconds):
    return words >= GOAL_WORDS or (seconds >= GOAL_SECONDS and words >= MIN_WORDS_WITH_MINUTES)


def record_words(user, words_before, words_after, now, previous_save_at=None):
    """Fold one save's change in the tab's word count into the student's day.

    One upsert, race-safe: net = max(0, net + delta), peak = max(peak, net) and goal_met,
    all computed by the database. Never raises: a failure here must not fail the save.
    """
    delta = words_after - words_before
    if not delta:
        return
    delta = min(delta, save_credit_cap(previous_save_at, now))
    try:
        table = connection.ops.quote_name(EssayWritingDay._meta.db_table)
        net = f'(CASE WHEN {table}.words_net + %s < 0 THEN 0 ELSE {table}.words_net + %s END)'
        peak = f'(CASE WHEN {net} > {table}.words_peak THEN {net} ELSE {table}.words_peak END)'
        met = (
            f'CASE WHEN {table}.goal_met OR {peak} >= %s'
            f' OR ({table}.active_seconds >= %s AND {peak} >= %s) THEN %s ELSE %s END'
        )
        net_params = [delta, delta]
        peak_params = net_params * 2
        first = max(delta, 0)
        params = [
            user.pk, timezone.localdate(now), first, first, 0, goal_met(first, 0),
            *net_params,
            *peak_params,
            *peak_params, GOAL_WORDS, GOAL_SECONDS, *peak_params, MIN_WORDS_WITH_MINUTES, True, False,
        ]
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO {table} (user_id, date, words_net, words_peak, active_seconds, goal_met)'
                ' VALUES (%s, %s, %s, %s, %s, %s)'
                ' ON CONFLICT (user_id, date) DO UPDATE SET'
                f' words_net = {net}, words_peak = {peak}, goal_met = {met}',
                params,
            )
    except Exception:
        logger.exception('Could not record the writing day for user %s', user.pk)


def _block_words(block):
    return doc_stats({'type': 'doc', 'content': [block]}).word_count


def own_words_delta(stored_doc, ops):
    """Net words the student's own ops v2 add, measured against the blocks they touch.

    Used when the save was merged into a newer version: the document-wide count then also
    holds words other people added since, which are not the student's writing.
    """
    try:
        stored = {block_id(block): block for block in stored_doc.get('content') or []}
        delta = 0
        for op in ops:
            if 'ins' in op:
                delta += _block_words(op['ins'])
            elif 'del' in op:
                if op['del'] in stored:
                    delta -= _block_words(stored[op['del']])
            elif op['set'] in stored:
                delta += _block_words(op['block']) - _block_words(stored[op['set']])
        return delta
    except Exception:
        logger.exception('Could not measure the words a merged save added')
        return 0


def _take_lock(lock_key):
    # The lock is held for two cache calls, so a short wait makes a lost race (second tab) rare.
    for attempt in range(SECONDS_LOCK_TRIES):
        if cache.add(lock_key, 1, SECONDS_LOCK_TTL):
            return True
        time.sleep(SECONDS_LOCK_WAIT * (attempt + 1))
    return False


def clamp_essay_seconds(user, entries, now):
    """Credit at most the wall-clock time since this user's previous Essay Lab report.

    The tracker reports every 30 s, so honest clients never exceed the elapsed time; one
    inflated batch cannot add more than that. Reads of the last report are serialized by a
    short cache lock, retried for a moment: a request that still loses the race is credited
    nothing, and so is one that cannot reach the cache at all. With no recent report, credit
    a first half minute. Whatever date the client names, the seconds belong to the server's
    today, so past days cannot be topped up afterwards. Other pages pass through untouched.
    """
    essay = {key: seconds for key, seconds in entries.items() if key[1] == SCREEN_TIME_PAGE}
    if not essay:
        return entries
    today = timezone.localdate(now)
    cache_key = f'essay-seconds-last:{user.pk}'
    lock_key = f'essay-seconds-lock:{user.pk}'
    allowed = 0
    try:
        if _take_lock(lock_key):
            try:
                last = cache.get(cache_key)
                cache.set(cache_key, now.timestamp(), SECONDS_LAST_REPORT_TTL)
            finally:
                cache.delete(lock_key)
            if last is None:
                allowed = SECONDS_FIRST_REPORT
            else:
                allowed = max(0, int(now.timestamp() - last)) + SECONDS_REPORT_SLACK
    except Exception:
        logger.warning('Essay Lab seconds are not credited: the cache is unavailable')
    clamped = {key: seconds for key, seconds in entries.items() if key[1] != SCREEN_TIME_PAGE}
    credit = min(sum(essay.values()), allowed)
    if credit:
        clamped[(today, SCREEN_TIME_PAGE)] = credit
    return clamped


def record_essay_seconds(user, entries, today):
    """Add a screen-time batch's `essay_lab` seconds to the student's days, in one upsert.

    `entries` is {(date, page): seconds}, credited to that date (a future date counts as
    today; dates older than SECONDS_BACKDATE_DAYS are dropped). The screen-time request
    passes it clamp_essay_seconds' output, which already dates everything to the server's today.
    Does nothing when the batch has no Essay Lab entry. Never raises: the request must not fail because of it.
    """
    by_day = {}
    for (client_date, page), seconds in entries.items():
        if page != SCREEN_TIME_PAGE:
            continue
        day = min(client_date, today)
        if day < today - timedelta(days=SECONDS_BACKDATE_DAYS):
            continue
        by_day[day] = by_day.get(day, 0) + seconds
    if not by_day:
        return
    try:
        table = connection.ops.quote_name(EssayWritingDay._meta.db_table)
        total = f'{table}.active_seconds + EXCLUDED.active_seconds'
        rows = [(user.pk, day, seconds) for day, seconds in by_day.items()]
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO {table} (user_id, date, words_net, words_peak, active_seconds, goal_met) VALUES '
                + ', '.join(['(%s, %s, 0, 0, %s, %s)'] * len(rows))
                + ' ON CONFLICT (user_id, date) DO UPDATE SET'
                f' active_seconds = {total},'
                f' goal_met = CASE WHEN {table}.goal_met OR ({total} >= %s AND {table}.words_peak >= %s)'
                ' THEN %s ELSE %s END',
                [value for row in rows for value in (*row, False)] + [GOAL_SECONDS, MIN_WORDS_WITH_MINUTES, True, False],
            )
    except Exception:
        logger.exception('Could not record Essay Lab time for user %s', user.pk)


def parse_month(value, today):
    """First day of the requested month, or None when it is malformed or after the current month."""
    match = MONTH_RE.match(value or '')
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12 or year < 1:
        return None
    first = date(year, month, 1)
    return first if first <= today.replace(day=1) else None


def streak_numbers(fire_days, today):
    """(current, best) from the set of fire dates.

    Today without a fire day yet does not break the streak: counting starts at yesterday.
    """
    cursor = today if today in fire_days else today - timedelta(days=1)
    current = 0
    while cursor in fire_days:
        current += 1
        cursor -= timedelta(days=1)
    best = run = 0
    previous = None
    for day in sorted(fire_days):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    return current, best


def build_streak(user, first_of_month):
    """The /streak/ payload from two read-only queries.

    One for the requested month's days plus today's (the progress line), one for the
    dates that met the goal, from which the current and best streaks are counted.
    """
    today = timezone.localdate()
    next_month = (first_of_month + timedelta(days=32)).replace(day=1)
    rows = EssayWritingDay.objects.filter(user=user).filter(
        Q(date__gte=first_of_month, date__lt=next_month) | Q(date=today)
    ).values_list('date', 'words_peak', 'active_seconds', 'goal_met')
    fire_days = set(
        EssayWritingDay.objects.filter(user=user, goal_met=True).order_by('date').values_list('date', flat=True)
    )
    month_days = {}
    words_today = seconds_today = 0
    for day, words, seconds, met in rows:
        if day == today:
            words_today, seconds_today = words, seconds
        if first_of_month <= day < next_month:
            if met:
                month_days[day.isoformat()] = FIRE
            elif words or seconds:
                month_days[day.isoformat()] = EMBER
    current, best = streak_numbers(fire_days, today)
    return {
        'today': today.isoformat(),
        'current': current,
        'best': best,
        'progress': {
            'words': words_today,
            'minutes': seconds_today // 60,
            'goal_met': today in fire_days,
        },
        'goal': {'words': GOAL_WORDS, 'minutes': GOAL_MINUTES},
        'month': first_of_month.strftime('%Y-%m'),
        'days': month_days,
    }
