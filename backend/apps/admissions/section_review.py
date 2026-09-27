"""Counselor review of the Student Center profile sections.

Each section of a student's profile answers (the cards the student edits one
at a time) carries a review state. Saving a change to a section sends it back
to "waiting for review"; the assigned counselor approves it or asks for changes.
"""
from django.utils import timezone

from .exam_scores import EXAM_KEYS
from .models import Notification, ProfileSectionReview

Section = ProfileSectionReview.Section
Status = ProfileSectionReview.Status

# The answers each section edits, as current_answers() names them. Mirrors
# PROFILE_SECTIONS in frontend/src/lib/profileSections.js.
SECTION_FIELDS = {
    Section.PERSONAL: frozenset({
        'first_name', 'middle_name', 'last_name', 'gender', 'grade', 'graduation_year', 'first_generation',
        'family_income', 'residency_status', 'guardian_name', 'guardian_relation', 'guardian_contact',
    }),
    Section.ACADEMICS: frozenset({'school_name', 'country', 'state', 'city', 'class_size', 'class_rank', 'gpa_scale', 'gpa'}),
    Section.TESTS: frozenset({*EXAM_KEYS, 'subjects'}),
    Section.GOAL: frozenset({'target_countries', 'interests', 'program_strengths', 'personal_story'}),
    Section.HONORS: frozenset({'honors'}),
    Section.ACTIVITIES: frozenset({'activities'}),
}
SECTION_KEYS = [choice.value for choice in Section]

NOTIFICATION_TITLES = {
    Status.APPROVED: 'Profile section approved',
    Status.CHANGES_REQUESTED: 'Profile section needs changes',
}


def changed_sections(before, after):
    """Sections with at least one answer that differs between two current_answers() snapshots."""
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    return [section for section, fields in SECTION_FIELDS.items() if fields & changed]


def mark_waiting(profile, sections):
    """Send edited sections back to the counselor, in one query."""
    if not sections:
        return
    now = timezone.now()
    ProfileSectionReview.objects.bulk_create(
        [ProfileSectionReview(student=profile, section=section, status=Status.WAITING, created_at=now, updated_at=now) for section in sections],
        update_conflicts=True, unique_fields=['student', 'section'], update_fields=['status', 'updated_at'],
    )


def reviews_payload(profile):
    """{section: {status, note, reviewed_at}} for every section; reads prefetched rows when present."""
    stored = {review.section: review for review in profile.section_reviews.all()}
    payload = {}
    for section in SECTION_KEYS:
        review = stored.get(section)
        payload[section] = {
            'status': review.status if review else Status.NOT_REVIEWED,
            'note': review.note if review else '',
            'reviewed_at': review.reviewed_at.isoformat() if review and review.reviewed_at else None,
        }
    return payload


def set_review(profile, section, status, note, reviewer):
    """Store a counselor's decision; tells the student when the status changed. Returns the review."""
    review, _ = ProfileSectionReview.objects.select_for_update().get_or_create(student=profile, section=section)
    status_changed = review.status != status
    review.status = status
    review.note = note
    review.reviewed_by = reviewer
    review.reviewed_at = timezone.now()
    review.save()
    title = NOTIFICATION_TITLES.get(status)
    if status_changed and title:
        Notification.objects.create(
            student=profile, title=title, message=note, kind=Notification.Kind.PROFILE_REVIEW,
            # The section's position (1-based) so the client can name it in the reader's language.
            target_id=SECTION_KEYS.index(section) + 1,
        )
    return review
