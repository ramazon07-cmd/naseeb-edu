"""Cache of the dashboard progress summary, dropped on every relevant write.

The summary is keyed by student scope and by versions that change whenever a
row feeding it is saved or deleted, so an approval, an assignment or a
deactivation shows on the dashboard at once.

Each school has its own version: a write in one school leaves every other
school's cached summaries alone. Product admins see every school, so their
summary also follows an "all schools" version that every write bumps. A write
whose school cannot be told (a bulk change, a row without a school) bumps the
epoch, which every key includes: everything is recomputed once.

A version changes on the write and again after its transaction commits: a
reader that ran in between cached the old rows under a version nobody asks
for any more. The timeout only bounds bulk writes that skip signals.
"""
import time

from django.db import transaction
from django.db.models.signals import post_delete, post_init, post_save

from apps.users.cache_safety import cache_get, cache_get_many, cache_set, cache_set_many
from apps.users.throttles import hashed

from .progress import summarize_progress
from .scoping import student_scope_key, tenant_school_id

EPOCH_KEY = 'dashboard-progress:epoch'
ALL_KEY = 'dashboard-progress:all'
CACHE_SECONDS = 60
# A user row matters only for scope: active flag, school or role.
USER_SCOPE_FIELDS = frozenset({'is_active', 'school', 'school_id', 'role'})
# Stands for "school unknown": the epoch is bumped instead of one school.
EVERY_SCHOOL = None


def school_key(school_id):
    return f'dashboard-progress:school:{school_id}'


def _keys_for(school_ids):
    if EVERY_SCHOOL in school_ids:
        return [EPOCH_KEY]
    return [ALL_KEY, *(school_key(pk) for pk in sorted(school_ids))]


def _bump(school_ids=frozenset({EVERY_SCHOOL})):
    stamp = time.time_ns()
    cache_set_many(dict.fromkeys(_keys_for(set(school_ids)), stamp), None)


def _flush_pending():
    connection = transaction.get_connection()
    pending, connection.progress_cache_pending = getattr(connection, 'progress_cache_pending', set()), set()
    if pending:
        _bump(pending)


def invalidate_progress_summary(*school_ids):
    """Drop the cached summaries of these schools (of every school when none is given)."""
    ids = set(school_ids) or {EVERY_SCHOOL}
    _bump(ids)
    connection = transaction.get_connection()
    if not connection.in_atomic_block:
        return
    # One commit hook per transaction, carrying every school touched in it: a cascade
    # delete fires this for every row.
    if not any(entry[1] is _flush_pending for entry in connection.run_on_commit):
        # A rolled-back transaction leaves its set behind with no hook to clear it.
        connection.progress_cache_pending = set()
        transaction.on_commit(_flush_pending)
    connection.progress_cache_pending |= ids


def _student_school(instance):
    """The school of a row's student, read without a query when the student is loaded."""
    from .models import StudentProfile

    field = type(instance).student
    if field.is_cached(instance):
        return instance.student.school_id if instance.student else EVERY_SCHOOL
    found = StudentProfile.objects.filter(pk=instance.student_id).values_list('school_id', flat=True).first()
    return found or EVERY_SCHOOL


def _schools_of(instance):
    from apps.users.models import User

    from .models import School, StudentProfile

    if isinstance(instance, School):
        return {instance.pk}
    if isinstance(instance, StudentProfile):
        return {instance.school_id or EVERY_SCHOOL}
    if isinstance(instance, User):
        schools = {instance.school_id} if instance.school_id else set()
        if instance.role == User.Role.STUDENT:
            schools |= set(StudentProfile.objects.filter(user_id=instance.pk).values_list('school_id', flat=True))
        return {school or EVERY_SCHOOL for school in schools} or {EVERY_SCHOOL}
    return {_student_school(instance)}


def _remember_loaded_school(sender, instance, **kwargs):
    # A row moving between schools changes both. The school it was loaded with is kept
    # (no query: read from the row as loaded; a deferred school stays unknown).
    instance._progress_loaded_school = instance.__dict__.get('school_id')


def _changed(instance):
    schools = _schools_of(instance)
    loaded = getattr(instance, '_progress_loaded_school', None)
    if loaded:
        schools.add(loaded)
    invalidate_progress_summary(*schools)
    if hasattr(instance, '_progress_loaded_school'):
        instance._progress_loaded_school = instance.__dict__.get('school_id')


def _on_row_change(sender, instance, update_fields=None, **kwargs):
    _changed(instance)


def _on_user_change(sender, instance, update_fields=None, created=False, **kwargs):
    if created or update_fields is None or USER_SCOPE_FIELDS & set(update_fields):
        _changed(instance)


def connect():
    from apps.users.models import User

    from .models import Application, Document, RecommendationLetter, RoadmapMission, School, StudentProfile, Task

    for model in (Application, Document, RecommendationLetter, RoadmapMission, School, StudentProfile, Task):
        uid = f'progress-cache-{model._meta.label_lower}'
        post_save.connect(_on_row_change, sender=model, dispatch_uid=f'{uid}-save')
        post_delete.connect(_on_row_change, sender=model, dispatch_uid=f'{uid}-delete')
    for model in (StudentProfile, User):
        post_init.connect(_remember_loaded_school, sender=model, dispatch_uid=f'progress-cache-{model._meta.label_lower}-loaded')
    post_save.connect(_on_user_change, sender=User, dispatch_uid='progress-cache-user-save')
    post_delete.connect(_on_row_change, sender=User, dispatch_uid='progress-cache-user-delete')


def _versions(user, scope):
    keys = [EPOCH_KEY, ALL_KEY if scope == 'all' else school_key(tenant_school_id(user))]
    found = cache_get_many(keys)
    if found is None:  # cache down: nothing is cached anyway
        return None
    missing = {key: time.time_ns() for key in keys if key not in found}
    if missing:
        # Start a version the first time it is asked for, so a later bump really changes it.
        cache_set_many(missing, None)
        found.update(missing)
    return ':'.join(str(found[key]) for key in keys)


def cached_progress_summary(user, students):
    scope = student_scope_key(user)
    if scope is None:
        return summarize_progress(students)
    versions = _versions(user, scope)
    if versions is None:
        return summarize_progress(students)
    key = f'dashboard-progress:v3:{versions}:{hashed(scope)}'
    summary = cache_get(key)
    if summary is None:
        summary = summarize_progress(students)
        cache_set(key, summary, CACHE_SECONDS)
    return dict(summary)
