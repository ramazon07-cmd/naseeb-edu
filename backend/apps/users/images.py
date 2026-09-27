"""Private profile images (student photos, account avatars).

Images are small and shown on many screens, so unlike documents they are
streamed through the API with a version in the URL: ``?v=<version>`` responses
are immutable for a day in the browser's private cache, and a changed image
gets a new version because every upload gets a new storage name.
"""
import hashlib
import mimetypes
from pathlib import Path

from django.http import FileResponse, Http404, HttpResponseNotModified
from django.urls import reverse
from rest_framework import serializers

VERSIONED_CACHE_CONTROL = 'private, max-age=86400, immutable'
UNVERSIONED_CACHE_CONTROL = 'private, no-cache'


def image_version(field_file):
    name = getattr(field_file, 'name', '') or ''
    return hashlib.sha256(name.encode()).hexdigest()[:16] if name else None


def versioned_url(request, path, field_file):
    version = image_version(field_file)
    if not version:
        return None
    url = f'{path}?v={version}'
    return request.build_absolute_uri(url) if request else url


def serve_private_image(request, field_file, *, missing_message):
    """Stream an authorised image; cache it only when the URL names its version."""
    version = image_version(field_file)
    if not version:
        raise Http404(missing_message)
    etag = f'"{version}"'
    cache_control = VERSIONED_CACHE_CONTROL if request.GET.get('v') == version else UNVERSIONED_CACHE_CONTROL
    if request.headers.get('If-None-Match') == etag:
        response = HttpResponseNotModified()
    else:
        try:
            stream = field_file.open('rb')
        except (FileNotFoundError, OSError):
            raise Http404(missing_message)
        name = Path(field_file.name).name
        response = FileResponse(stream, content_type=mimetypes.guess_type(name)[0] or 'image/jpeg')
        response['X-Content-Type-Options'] = 'nosniff'
    response['ETag'] = etag
    response['Cache-Control'] = cache_control
    response['Vary'] = 'Authorization'
    return response


class AvatarField(serializers.ImageField):
    """Accepts an image upload; reads back as the authorised, versioned avatar URL.

    The stored file's own URL is never exposed (on object storage it would be a
    bucket URL).
    """

    def to_representation(self, value):
        if not value:
            return None
        return versioned_url(
            self.context.get('request'),
            reverse('accounts-avatar', kwargs={'pk': value.instance.pk}),
            value,
        )
