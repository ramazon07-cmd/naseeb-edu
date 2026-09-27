"""Shared upload validation."""
import warnings

from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler
from django.http import JsonResponse
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

IMAGE_FORMATS = {'PNG', 'JPEG', 'WEBP'}


def verify_image(upload, *, allowed_formats=IMAGE_FORMATS):
    """Open the image with Pillow (content, not extension) and reject bombs."""
    try:
        with warnings.catch_warnings():
            # Pillow only *warns* between MAX_IMAGE_PIXELS and 2x that; treat as fatal.
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(upload) as image:
                image_format = image.format
                image.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise serializers.ValidationError('This image is too large to process.')
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise serializers.ValidationError('This file is not a valid image.')
    finally:
        upload.seek(0)
    if allowed_formats and image_format not in allowed_formats:
        raise serializers.ValidationError('Use a PNG, JPEG or WebP image.')
    return upload


def validate_image_upload(upload, *, max_bytes):
    if upload.size == 0:
        raise serializers.ValidationError('The selected file is empty.')
    if upload.size > max_bytes:
        raise serializers.ValidationError(f'The image must be {max_bytes // (1024 * 1024)} MB or smaller.')
    return verify_image(upload)


class UploadTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_code = 'upload_too_large'

    def __init__(self, limit):
        super().__init__(f'File is larger than the {max(1, limit // (1024 * 1024))} MB limit.')


def limit_upload_size(request, max_bytes):
    """Lower the per-file cap for this request; call before the body is parsed."""
    getattr(request, '_request', request).upload_size_limit = max_bytes


class FileSizeLimitUploadHandler(FileUploadHandler):
    """Abort a multipart upload as soon as one file passes its size limit.

    Content-Length caps the whole body; this caps each file while it is still
    arriving, so an oversized file is never fully read or written anywhere.
    Views with a smaller limit set it through ``limit_upload_size``.
    """

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.received = 0
        self.limit = getattr(self.request, 'upload_size_limit', None) or settings.DOCUMENT_MAX_UPLOAD_SIZE

    def receive_data_chunk(self, raw_data, start):
        self.received += len(raw_data)
        if self.received > self.limit:
            raise UploadTooLarge(self.limit)
        return raw_data

    def file_complete(self, file_size):
        return None


class RequestSizeLimitMiddleware:
    """Refuse oversized bodies from Content-Length before Django reads them.

    Upload validators only run after the whole body has been received; this
    stops a client from making the server buffer arbitrarily large requests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            length = int(request.META.get('CONTENT_LENGTH') or 0)
        except ValueError:
            length = 0
        if length > settings.MAX_REQUEST_BODY_SIZE:
            limit_mb = settings.MAX_REQUEST_BODY_SIZE // (1024 * 1024)
            return JsonResponse({'detail': f'Request body exceeds the {limit_mb} MB limit.'}, status=413)
        return self.get_response(request)

    def process_exception(self, request, exception):
        # DRF views answer UploadTooLarge themselves; this covers plain Django
        # views such as the admin.
        if isinstance(exception, UploadTooLarge):
            return JsonResponse({'detail': str(exception.detail)}, status=exception.status_code)
        return None
