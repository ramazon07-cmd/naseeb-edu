"""Writing streak for the digest."""
from collections import defaultdict
from datetime import timedelta

from apps.admissions.essay_lab.streak import current_streak
from apps.admissions.models import EssayWritingDay

# Only the run ending today matters, so a year of history is enough; longer streaks show as this many days.
STREAK_WINDOW_DAYS = 400


def essay_activity_for(user_ids, today):
    """{user id: current streak length} on the Tashkent date ``today``, from one query.

    Words per day are deliberately not exposed, and the digest shows the streak only for students
    without private essays: EssayWritingDay cannot tell shared essays from private ones.
    """
    user_ids = list(user_ids)
    if not user_ids:
        return {}
    fire_days = defaultdict(set)
    rows = EssayWritingDay.objects.filter(
        user_id__in=user_ids, goal_met=True, date__gte=today - timedelta(days=STREAK_WINDOW_DAYS),
    ).values_list('user_id', 'date')
    for user_id, day in rows:
        fire_days[user_id].add(day)
    return {user_id: current_streak(fire_days[user_id], today) for user_id in user_ids}
