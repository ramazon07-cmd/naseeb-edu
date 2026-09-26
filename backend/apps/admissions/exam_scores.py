"""IELTS and SAT score rules shared by the model, onboarding and the migration.

The frontend mirrors these in ``frontend/src/lib/testScores.js``.
"""
from decimal import ROUND_FLOOR, Decimal

IELTS_SECTIONS = ('ielts_listening', 'ielts_reading', 'ielts_writing', 'ielts_speaking')
SAT_DETAIL_FIELDS = ('sat_reading', 'sat_math', 'sat_superscore', 'sat_superscore_reading', 'sat_superscore_math')
IELTS_FIELDS = ('ielts_status', 'ielts_score', *IELTS_SECTIONS, 'ielts_test_date', 'ielts_attempts')
SAT_FIELDS = ('sat_status', 'sat_score', *SAT_DETAIL_FIELDS, 'sat_test_date', 'sat_attempts')
EXAM_KEYS = frozenset((*IELTS_FIELDS, *SAT_FIELDS))
MAX_ATTEMPTS = 20


def ielts_overall(sections):
    """Official band rounding: the mean goes to the nearest half band, .25 and .75 round up."""
    if len(sections) != 4 or any(value is None for value in sections):
        return None
    mean = sum(Decimal(str(value)) for value in sections) / 4
    return ((mean * 2) + Decimal('0.5')).to_integral_value(rounding=ROUND_FLOOR) / 2


def sat_sent_total(reading, math, superscore=None, best_reading=None, best_math=None):
    """The total a student sends: the superscore when they send one, otherwise one test day."""
    if superscore and best_reading and best_math:
        return best_reading + best_math
    if reading and math:
        return reading + math
    return None


def reconcile(profile):
    """Keep the headline scores and their detail consistent.

    ``ielts_score`` and ``sat_score`` can also be written on their own (profile
    edit, college research). Section detail that no longer adds up to the
    headline is dropped rather than shown next to a different total. A cleared
    headline means there is no result any more: status and detail are reset.
    """
    if profile.ielts_score is None:
        if profile.ielts_status == 'taken':
            _clear(profile, IELTS_FIELDS)
    else:
        profile.ielts_status = 'taken'
        overall = ielts_overall([getattr(profile, name) for name in IELTS_SECTIONS])
        if overall is not None and overall != Decimal(str(profile.ielts_score)):
            for name in IELTS_SECTIONS:
                setattr(profile, name, None)
    if profile.sat_score is None:
        if profile.sat_status == 'taken':
            _clear(profile, SAT_FIELDS)
    else:
        profile.sat_status = 'taken'
        expected = sat_sent_total(
            profile.sat_reading, profile.sat_math, profile.sat_superscore,
            profile.sat_superscore_reading, profile.sat_superscore_math,
        )
        if expected is not None and expected != profile.sat_score:
            for name in SAT_DETAIL_FIELDS:
                setattr(profile, name, None)


def _clear(profile, fields):
    status, *details = fields
    setattr(profile, status, 'not_taken')
    for name in details:
        setattr(profile, name, None)
