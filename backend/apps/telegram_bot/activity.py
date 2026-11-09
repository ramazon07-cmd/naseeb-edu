"""Essay writing activity (words typed today, writing streak) for the digest."""
from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Q

from apps.admissions.essay_lab.streak import streak_numbers
from apps.admissions.models import EssayWritingDay


@dataclass(frozen=True)
class EssayActivity:
    words_today: int | None = None
    streak_days: int | None = None


@dataclass(frozen=True)
class ActivityResult:
    by_user: dict = field(default_factory=dict)

    def for_user(self, user_id):
        return self.by_user.get(user_id, EssayActivity())


def essay_activity_for(user_ids, today):
    """Activity for the given student user ids on the Tashkent date ``today``, from one query."""
    user_ids = list(user_ids)
    if not user_ids:
        return ActivityResult()
    fire_days = defaultdict(set)
    words_today = {}
    rows = EssayWritingDay.objects.filter(user_id__in=user_ids).filter(
        Q(goal_met=True) | Q(date=today)
    ).values_list('user_id', 'date', 'words_peak', 'goal_met')
    for user_id, day, words, met in rows:
        if met:
            fire_days[user_id].add(day)
        if day == today:
            words_today[user_id] = words
    return ActivityResult({
        user_id: EssayActivity(
            words_today=words_today.get(user_id, 0),
            streak_days=streak_numbers(fire_days[user_id], today)[0],
        )
        for user_id in user_ids
    })
