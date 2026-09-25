"""Cache of the dashboard progress summary, dropped on every relevant write.

The summary is keyed by student scope and by a version that changes whenever
a row feeding it is saved or deleted, so an approval, an assignment or a
deactivation shows on the dashboard at once. The version changes on the
write and again after its transaction commits: a reader that ran in between
cached the old rows under a version nobody asks for any more. The timeout
only bounds bulk writes that skip signals.
"""
import time

from django.db import transaction
from django.db.models.signals import post_delete, post_save

from apps.users.cache_safety import cache_get, cache_set
from apps.users.throttles import hashed

from .progress import summarize_progress
from .scoping import student_scope_key

VERSION_KEY = 'dashboard-progress:version'
CACHE_SECONDS = 60
# A user row matters only for scope: active flag, school or role.
USER_SCOPE_FIELDS = frozenset({'is_active', 'school', 'school_id', 'role'})


def _bump():
    cache_set(VERSION_KEY, time.time_ns(), None)


def invalidate_progress_summary():
    _bump()
    connection = transaction.get_connection()
    # One commit hook per transaction: a cascade delete fires this for every row.
    if connection.in_atomic_block and not any(entry[1] is _bump for entry in connection.run_on_commit):
        transaction.on_commit(_bump)


def _on_row_change(sender, update_fields=None, **kwargs):
    invalidate_progress_summary()


def _on_user_change(sender, update_fields=None, created=False, **kwargs):
    if created or update_fields is None or USER_SCOPE_FIELDS & set(update_fields):
        invalidate_progress_summary()


def connect():
    from apps.users.models import User

    from .models import Application, Document, RecommendationLetter, RoadmapMission, School, StudentProfile, Task

    for model in (Application, Document, RecommendationLetter, RoadmapMission, School, StudentProfile, Task):
        uid = f'progress-cache-{model._meta.label_lower}'
        post_save.connect(_on_row_change, sender=model, dispatch_uid=f'{uid}-save')
        post_delete.connect(_on_row_change, sender=model, dispatch_uid=f'{uid}-delete')
    post_save.connect(_on_user_change, sender=User, dispatch_uid='progress-cache-user-save')
    post_delete.connect(_on_row_change, sender=User, dispatch_uid='progress-cache-user-delete')


def cached_progress_summary(user, students):
    scope = student_scope_key(user)
    if scope is None:
        return summarize_progress(students)
    key = f'dashboard-progress:v2:{cache_get(VERSION_KEY, 0)}:{hashed(scope)}'
    summary = cache_get(key)
    if summary is None:
        summary = summarize_progress(students)
        cache_set(key, summary, CACHE_SECONDS)
    return dict(summary)
