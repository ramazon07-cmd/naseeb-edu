"""Shared cache for the read-only catalogue lists.

Universities, scholarships and opportunity programmes are the same for every
signed-in user, and api.list() loads all of them on every sign-in. Their list
pages are cached after authentication and permission checks have run. Any
save or delete of a catalogue row changes the version in the cache key, so
edits made through the API or the admin show up at once; the timeout covers
bulk writes that skip model signals.
"""
import time

from django.db.models.signals import post_delete, post_save
from rest_framework.response import Response

from apps.users.cache_safety import cache_get, cache_set

VERSION_KEY = 'catalog:version'
CACHE_SECONDS = 300


def bump_version(**kwargs):
    cache_set(VERSION_KEY, time.time_ns(), None)


def connect():
    from .models import OpportunityProgram, Scholarship, University, UniversityProgram

    for model in (University, UniversityProgram, Scholarship, OpportunityProgram):
        uid = f'catalog-cache-{model._meta.label_lower}'
        post_save.connect(bump_version, sender=model, dispatch_uid=f'{uid}-save')
        post_delete.connect(bump_version, sender=model, dispatch_uid=f'{uid}-delete')


class CachedCatalogListMixin:
    """Cache ``list`` responses; the rows must not depend on who is asking."""

    def list(self, request, *args, **kwargs):
        version = cache_get(VERSION_KEY, 0)
        # The absolute URL keeps page, page_size and the host of the next link.
        key = f'catalog:{self.basename}:{version}:{request.build_absolute_uri()}'
        data = cache_get(key)
        if data is None:
            data = super().list(request, *args, **kwargs).data
            cache_set(key, data, CACHE_SECONDS)
        return Response(data)
