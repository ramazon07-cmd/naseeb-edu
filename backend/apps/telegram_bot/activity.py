"""Essay writing activity (words typed today, writing streak) for the digest."""
from collections import defaultdict
from dataclasses import dataclass, field

from apps.admissions.essay_lab.streak import streak_numbers
from apps.admissions.models import EssayWritingDay


@dataclass(frozen=True)
class EssayActivity:
    words_today: int | None = None
    streak_days: int | None = None


@dataclass(frozen=True)
class ActivityResult:
    available: bool
    by_user: dict = field(default_factory=dict)

    def for_user(self, user_id):
        return self.by_user.get(user_id, EssayActivity())


def essay_activity_for(user_ids, today):
    """Activity for the given student user ids on the Tashkent date ``today``.

    Two queries for all students: the goal-met dates (for the streak) and today's words.
    """
    user_ids = list(user_ids)
    fire_days = defaultdict(set)
    words_today = {}
    rows = EssayWritingDay.objects.filter(user_id__in=user_ids).filter(
        goal_met=True
    ).values_list('user_id', 'date')
    for user_id, day in rows:
        fire_days[user_id].add(day)
    today_rows = EssayWritingDay.objects.filter(user_id__in=user_ids, date=today).values_list('user_id', 'words_peak')
    for user_id, words in today_rows:
        words_today[user_id] = words
    by_user = {
        user_id: EssayActivity(
            words_today=words_today.get(user_id, 0),
            streak_days=streak_numbers(fire_days[user_id], today)[0],
        )
        for user_id in user_ids
    }
    return ActivityResult(available=True, by_user=by_user)
