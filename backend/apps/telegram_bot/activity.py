"""Essay writing activity (words typed today, writing streak) for the digest.

The writing-streak data is not part of this branch yet, so this adapter reports
``available=False`` and no per-user numbers. When the streak feature lands, only
``essay_activity_for`` changes; the digest and the bot already handle both cases.
"""
from dataclasses import dataclass, field


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
    """Activity for the given student user ids on the Tashkent date ``today``."""
    return ActivityResult(available=False)
