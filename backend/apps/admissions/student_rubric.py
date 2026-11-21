"""The student's rubric: academics, activities and essays, each 0-10.

Scored once per profile, like an IELTS band per skill, then matched against every
university with fixed rules (admission_chance.py). Academics and activities come
from what the student entered (grades, tests, honor levels, roles, years); no AI.
Essays are the student's latest scored personal statement check from the Essay Lab
(0-100 divided by 10); no new AI call is made here. Without a scored check the
essays score is None: "not checked yet", unknown, not zero.

Recommendation letters are never part of a student's score, and writing language is never scored.

The weights are starting values from the research (SFFA v. Harvard ratings, counselor
activity tiers); they are meant to be tuned against recorded outcomes.
"""
from datetime import date

from .models import Achievement, Essay, EssayDepthCheck, Honor

# Honor level -> how far the recognition reaches (Harvard extracurricular 1 is national or beyond).
HONOR_LEVELS = {
    Honor.Level.INTERNATIONAL: 1.0, Honor.Level.NATIONAL: 0.8, Honor.Level.REGIONAL: 0.6, Honor.Level.SCHOOL: 0.3,
}
# Activities have no level field: taken as school or community reach until a counselor or AI says more.
ACTIVITY_LEVEL = 0.5
RESEARCH_LEVEL = 0.6
INTERNSHIP_LEVEL = 0.55
PROJECT_LEVEL = 0.5
ACHIEVEMENT_LEVELS = {
    Achievement.Category.OLYMPIAD: 0.6, Achievement.Category.STARTUP: 0.6, Achievement.Category.RESEARCH: 0.6,
}
ACHIEVEMENT_LEVEL = 0.45
# A title is easy to claim, so it adds only a little: duration and verification count more.
# Role words, strongest first, with the bonus they add to the base role value.
ROLE_BASE = 0.55
ROLE_BONUSES = (
    (0.10, ('founder', 'co-founder', 'cofounder', 'asoschi', 'основател')),
    (0.07, ('president', 'captain', 'head', 'chair', 'editor', 'lead', 'leader', 'rais', 'sardor', 'капитан', 'президент', 'руководител')),
    (0.04, ('organizer', 'organiser', 'coordinator', 'manager', 'author', 'tashkilotchi', 'организатор', 'координатор')),
)
# Unverified evidence counts for little more than half.
UNVERIFIED = 0.6
# Weights of the strongest three items: one standout counts most (a "spike").
TOP_WEIGHTS = (0.7, 0.2, 0.1)
OLYMPIAD_WORDS = ('olymp', 'олимп')
OLYMPIAD_BONUS = {Honor.Level.INTERNATIONAL: 1.0, Honor.Level.NATIONAL: 0.5, Honor.Level.REGIONAL: 0.25}
# Without a standardized test, academics stay at most 8: grades alone cannot show the top band.
NO_TEST_CAP = 8


def clamp(value, low=0.0, high=10.0):
    return max(low, min(high, value))


def role_weight(text):
    text = (text or '').lower()
    return ROLE_BASE + next((bonus for bonus, words in ROLE_BONUSES if any(word in text for word in words)), 0)


def duration_weight(start, end, today=None):
    if not start:
        return 0.5
    years = ((end or today or date.today()) - start).days / 365
    return 1.0 if years >= 1.5 else 0.8 if years >= 0.5 else 0.5


def academics_score(ctx, honors):
    """Grades and tests on 0-10, plus up to 1 for olympiad results."""
    grades = clamp((ctx['gpa'] / ctx['gpa_scale'] - 0.6) / 0.4 * 10)
    tests = []
    if ctx['sat'] is not None:
        tests.append(clamp((ctx['sat'] - 900) / 700 * 10))
    if ctx['act'] is not None:
        tests.append(clamp((ctx['act'] - 17) / 19 * 10))
    score = 0.5 * grades + 0.5 * max(tests) if tests else min(grades, NO_TEST_CAP)
    olympiad = max((
        OLYMPIAD_BONUS.get(honor.level, 0) for honor in honors
        if any(word in f'{honor.title} {honor.description}'.lower() for word in OLYMPIAD_WORDS)
    ), default=0)
    return round(clamp(score + olympiad), 1)


def activity_items(profile, honors, today=None):
    """Each piece of evidence as a 0-1 value: reach x role x how long, much less while unverified."""
    def value(level, role, start=None, end=None, verified=True, timed=False):
        item = level * role * (duration_weight(start, end, today) if timed else 1.0)
        return min(1.0, item * (1 if verified else UNVERIFIED))

    items = []
    for honor in honors:
        items.append(value(HONOR_LEVELS.get(honor.level, 0.3), 1.0))
    for activity in profile.activities.all():
        role = role_weight(activity.role)
        if (activity.hours_per_week or 0) >= 5:
            role = min(1.0, role * 1.1)
        level = ACTIVITY_LEVEL * (1.15 if activity.impact.strip() else 1)  # a stated result
        items.append(value(level, role, activity.start_date, activity.end_date, activity.verified, timed=True))
    for research in profile.researches.all():
        level = RESEARCH_LEVEL * (1.15 if research.outcome else 1)
        items.append(value(level, role_weight(research.role), research.start_date, research.end_date, research.verified, timed=True))
    for internship in profile.internships.all():
        end = None if internship.is_current else internship.end_date
        items.append(value(INTERNSHIP_LEVEL, 0.65, internship.start_date, end, internship.verified, timed=True))
    for project in profile.projects.all():
        level = PROJECT_LEVEL * (1.1 if project.impact else 1)
        items.append(value(level, role_weight(project.role), verified=project.verified))
    for achievement in profile.achievements.all():
        level = ACHIEVEMENT_LEVELS.get(achievement.category, ACHIEVEMENT_LEVEL) * (1.1 if achievement.impact else 1)
        items.append(value(level, 1.0, verified=achievement.verified))
    return sorted(items, reverse=True)


def activities_score(items):
    return round(clamp(10 * sum(weight * item for weight, item in zip(TOP_WEIGHTS, items))), 1)


def essays_score(profile):
    """The latest scored personal statement check, 0-100 as 0-10; None while no check is scored.

    No AI call: the Essay Lab already scored it (EssayDepthCheck.overall, null for unscored checks).
    """
    overall = EssayDepthCheck.objects.filter(
        essay__student=profile, essay__essay_type=Essay.EssayType.PERSONAL_STATEMENT, essay__trashed_at__isnull=True,
        overall__isnull=False,
    ).order_by('-created_at', '-id').values_list('overall', flat=True).first()
    return None if overall is None else round(clamp(overall / 10), 1)


def rubric(profile, ctx):
    """The three scores, 0-10 (essays None when no personal statement check is scored yet)."""
    honors = list(profile.honors.all())
    return {
        'academics': academics_score(ctx, honors),
        'activities': activities_score(activity_items(profile, honors)),
        'essays': essays_score(profile),
    }
