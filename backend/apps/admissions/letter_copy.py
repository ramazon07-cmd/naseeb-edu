"""Copy check for recommendation letters (no AI): how much of this letter the same author wrote before.

Letters are compared as sets of word 5-gram shingles after the student's name, the school and other private
details are replaced (letter_coach.anonymize), so a letter about another student with the same sentences still
matches. The score is containment: the share of THIS letter's shingles found in another letter. It is shown to
the author only, as a percent and the other letter's date; the other letter's text is never returned.
"""
import re

from .essay_lab import coach

SHINGLE_WORDS = 5
MIN_PERCENT = 30
MAX_OTHERS = 100
_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


def shingles(text, size=SHINGLE_WORDS):
    words = _WORD.findall(coach.fold(text).replace('’', "'"))
    return {' '.join(words[index:index + size]) for index in range(len(words) - size + 1)}


def containment(mine, other):
    """Share (0-1) of `mine` that also occurs in `other`."""
    return len(mine & other) / len(mine) if mine else 0.0


def best_match(mine, others):
    """others: (date, shingle set) pairs -> {'percent', 'date'} of the closest one at or above 30%, or None."""
    best = None
    for date, theirs in others:
        score = containment(mine, theirs)
        if best is None or score > best[0]:
            best = (score, date)
    if best is None or round(best[0] * 100) < MIN_PERCENT:
        return None
    return {'percent': round(best[0] * 100), 'date': best[1].isoformat()}


def copy_match(letter, queryset, anonymize):
    """The match of `letter.body` with the same author's other letters in `queryset`, or None.

    "Same author" is the recommender name (case and spacing ignored). `anonymize(text, student)` hides names.
    """
    name = coach.normalize(letter.recommender_name).lower()
    if not name:
        return None
    candidates = (
        queryset.exclude(pk=letter.pk).exclude(body='').filter(recommender_name__iexact=letter.recommender_name.strip())
        .select_related('student__user', 'student__school').order_by('-created_at', '-id')[:MAX_OTHERS]
    )
    mine = shingles(anonymize(letter.body, letter.student))
    if not mine:
        return None
    others = [
        (other.created_at.date(), shingles(anonymize(other.body, other.student)))
        for other in candidates if coach.normalize(other.recommender_name).lower() == name
    ]
    return best_match(mine, others)
