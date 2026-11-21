"""A university's QS rank in each subject, as the College Search rows and the university page show it.

Ranks are read in the database: College Search annotates each row with the selected subject's rank (one
correlated subquery on the (university, subject, year) index) so filtering and sorting by it stay in SQL,
and the university page loads all of one university's ranks with one prefetch. Only the newest year
loaded is used.
"""
from django.db.models import CharField, FloatField, IntegerField, Max, OuterRef, Prefetch, Subquery, Value

from .models import UniversitySubjectRank
from .subjects import AREAS, SUBJECTS, subjects_for_major

LATEST_ATTR = 'latest_subject_ranks'


def latest_year():
    return UniversitySubjectRank.objects.aggregate(year=Max('year'))['year']


def with_subject_rank(queryset, code, year):
    """``queryset`` with ``subject_rank``, ``subject_rank_label`` and ``subject_score`` of the subject in ``year`` (NULL when unranked)."""
    if year is None:
        return queryset.annotate(
            subject_rank=Value(None, output_field=IntegerField()),
            subject_rank_label=Value(None, output_field=CharField()),
            subject_score=Value(None, output_field=FloatField()),
        )
    rows = UniversitySubjectRank.objects.filter(university=OuterRef('pk'), subject_code=code, year=year).order_by()
    return queryset.annotate(
        subject_rank=Subquery(rows.values('rank')[:1]),
        subject_rank_label=Subquery(rows.values('rank_label')[:1]),
        subject_score=Subquery(rows.values('score')[:1]),
    )


def subject_rank_row(university, code, year):
    """The annotated rank of one university, or None when it is not ranked in the subject."""
    if getattr(university, 'subject_rank', None) is None:
        return None
    return {
        'code': code, 'rank': university.subject_rank, 'label': university.subject_rank_label or '',
        'score': university.subject_score, 'year': year,
    }


def prefetch_subject_ranks(year):
    return Prefetch('subject_ranks', queryset=UniversitySubjectRank.objects.filter(year=year), to_attr=LATEST_ATTR)


def major_subject_codes(user):
    """The QS subject codes of a student's target major; [] for anyone without a student profile."""
    profile = getattr(user, 'student_profile', None)
    return subjects_for_major(profile.target_major) if profile else []


def university_subjects(university, year, major_codes):
    """The university's subject ranks: the student's own major subjects first (as ``mine``), then the other
    subjects best rank first, then the five broad areas. A list of plain dicts; empty when unranked."""
    mine = {code: index for index, code in enumerate(major_codes)}
    items = []
    for row in getattr(university, LATEST_ATTR, []):
        if row.subject_code not in SUBJECTS:
            continue
        name, area = SUBJECTS[row.subject_code]
        items.append({
            'code': row.subject_code, 'name': name, 'area': area, 'is_area': row.subject_code in AREAS,
            'rank': row.rank, 'rank_label': row.rank_label, 'score': row.score, 'mine': row.subject_code in mine,
        })
    items.sort(key=lambda item: (
        0 if item['mine'] else 1,
        mine.get(item['code'], 0),
        item['is_area'],
        item['rank'],
        -(item['score'] if item['score'] is not None else -1),
        item['name'],
    ))
    return {'year': year, 'items': items}
