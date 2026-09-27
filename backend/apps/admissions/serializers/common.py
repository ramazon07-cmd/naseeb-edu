"""Admissions API serializers — common."""
from rest_framework import serializers
from django.conf import settings
from django.urls import reverse
from pathlib import Path
from urllib.parse import urlparse
import mimetypes
import re
import unicodedata
import zipfile
import codecs
from apps.users.uploads import verify_image
from core.storage import delete_file_on_commit
from ..models import StudentProfile
from ..scoping import scope_students


def google_docs_document_id(value):
    if not value:
        return None
    parsed = urlparse(str(value))
    if parsed.scheme != 'https' or parsed.hostname != 'docs.google.com':
        return None
    parts = [part for part in parsed.path.split('/') if part]
    if not parts or parts[0] != 'document':
        return None
    for index, part in enumerate(parts[:-1]):
        if part == 'd' and parts[index + 1]:
            return parts[index + 1]
    return None


def validate_google_docs_url(value):
    if value and not google_docs_document_id(value):
        raise serializers.ValidationError('Use a valid https://docs.google.com/document/... link.')
    return value


def google_docs_preview_url(value):
    document_id = google_docs_document_id(value)
    return f'https://docs.google.com/document/d/{document_id}/preview' if document_id else None


# Explicit types for extensions the platform's mimetypes table may not know,
# so stored metadata does not depend on the server's OS.
UPLOAD_CONTENT_TYPES = {
    '.pdf': 'application/pdf',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.heic': 'image/heic',
}
HEIF_BRANDS = {b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis', b'mif1', b'msf1'}
# Control characters, path separators and bidi overrides: a name like
# "cv\u202efdp.exe" would otherwise display as a different extension.
_UNSAFE_NAME_CHARS = re.compile(r'[\x00-\x1f\x7f/\\\u200e\u200f\u202a-\u202e\u2066-\u2069]')
MAX_FILE_NAME_LENGTH = 255
# Types a browser renders safely inline; everything else is served as an attachment.
INLINE_FILE_EXTENSIONS = frozenset({'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.txt', '.csv'})


def is_previewable(name):
    return Path(name or '').suffix.lower() in INLINE_FILE_EXTENSIONS


def clean_upload_name(name, fallback='file'):
    """The display name kept for an upload; the stored key is always a UUID."""
    raw = unicodedata.normalize('NFC', str(name or '')).replace('\\', '/').rsplit('/', 1)[-1]
    cleaned = ' '.join(_UNSAFE_NAME_CHARS.sub('', raw).split()).strip(' .')
    stem, dot, suffix = cleaned.rpartition('.')
    if not dot:
        stem, suffix = cleaned, ''
    suffix = f'.{suffix}'[:16] if suffix else ''
    stem = stem.strip(' .') or fallback
    return stem[:MAX_FILE_NAME_LENGTH - len(suffix)] + suffix


def uploaded_file_details(upload, fallback='file'):
    """(display name, content type, size) stored beside a private upload."""
    name = clean_upload_name(upload.name, fallback)
    extension = Path(name).suffix.lower()
    content_type = UPLOAD_CONTENT_TYPES.get(extension) or mimetypes.guess_type(name)[0] or 'application/octet-stream'
    return name, content_type[:120], upload.size


def validate_private_upload(upload):
    """Validate private documents and evidence using one production-safe policy."""
    extension = Path(clean_upload_name(upload.name)).suffix.lower()
    allowed = set(settings.DOCUMENT_ALLOWED_EXTENSIONS)
    if extension not in allowed:
        raise serializers.ValidationError(
            f'Unsupported file type. Allowed: {", ".join(sorted(allowed))}.'
        )
    if upload.size > settings.DOCUMENT_MAX_UPLOAD_SIZE:
        limit_mb = settings.DOCUMENT_MAX_UPLOAD_SIZE // (1024 * 1024)
        raise serializers.ValidationError(f'File is larger than the {limit_mb} MB limit.')
    if upload.size == 0:
        raise serializers.ValidationError('The selected file is empty.')

    try:
        head = upload.read(min(upload.size, 4096))
        upload.seek(0)
        if extension == '.pdf' and not head.startswith(b'%PDF-'):
            raise serializers.ValidationError('This file is not a valid PDF.')
        if extension in {'.png', '.jpg', '.jpeg', '.webp'}:
            verify_image(upload)
        if extension == '.heic' and not (head[4:8] == b'ftyp' and head[8:12] in HEIF_BRANDS):
            raise serializers.ValidationError('This file is not a valid HEIC image.')
        if extension in {'.doc', '.xls', '.ppt'} and not head.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
            raise serializers.ValidationError('This legacy Office file is invalid.')
        if extension == '.rtf' and not head.lstrip().startswith(b'{\\rtf'):
            raise serializers.ValidationError('This file is not a valid RTF document.')
        if extension in {'.txt', '.csv'}:
            if b'\x00' in head:
                raise serializers.ValidationError('Text documents cannot contain binary data.')
            codecs.getincrementaldecoder('utf-8-sig')().decode(head, final=False)
        if extension in {'.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp'}:
            with zipfile.ZipFile(upload) as archive:
                names = archive.namelist()
                required_prefix = {
                    '.docx': 'word/', '.xlsx': 'xl/', '.pptx': 'ppt/',
                    '.odt': 'content.xml', '.ods': 'content.xml', '.odp': 'content.xml',
                }[extension]
                if not any(name == required_prefix or name.startswith(required_prefix) for name in names):
                    raise serializers.ValidationError('The Office document structure is invalid.')
            upload.seek(0)
    except UnicodeDecodeError:
        upload.seek(0)
        raise serializers.ValidationError('Text documents must use UTF-8 encoding.')
    except zipfile.BadZipFile:
        upload.seek(0)
        raise serializers.ValidationError('The Office document is damaged or invalid.')
    return upload


UNAVAILABLE_STUDENT = 'Select one of your students.'
UNAVAILABLE_STUDENT_RECORD = 'Select a record of one of your students.'


def _is_student_owned(model):
    return any(
        field.name == 'student' and field.is_relation and field.related_model is StudentProfile
        for field in model._meta.concrete_fields
    )


def scope_related_field(field, queryset, message):
    """Resolve ``field`` only inside ``queryset``.

    Another tenant's id then fails exactly like an id that does not exist, so
    a body id can neither attach nor reveal a row the caller cannot see.
    """
    field.queryset = queryset
    field.error_messages = {**field.error_messages, 'does_not_exist': message, 'incorrect_type': message}


class StudentRecordSerializerMixin:
    """Keep every student, and every student-owned record, a client names in scope.

    Writable links to StudentProfile, or to a model owned by a student (an
    essay's application, a mission's prerequisite), are looked up through the
    canonical scope in ``scoping.py``, the same one the list endpoints use.
    """

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        for field in fields.values():
            queryset = getattr(field, 'queryset', None)
            if field.read_only or queryset is None:
                continue
            if queryset.model is StudentProfile:
                scope_related_field(field, scope_students(queryset, user), UNAVAILABLE_STUDENT)
            elif _is_student_owned(queryset.model):
                scope_related_field(
                    field, scope_students(queryset, user, via='student'), UNAVAILABLE_STUDENT_RECORD,
                )
        return fields


class VerifiedStudentRecordMixin(StudentRecordSerializerMixin):
    def validate_verified(self, value):
        request = self.context.get('request')
        if request and not request.user.is_counselor_like:
            current = getattr(self.instance, 'verified', False)
            if value != current:
                raise serializers.ValidationError('Only a counselor can verify records.')
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        instance = self.instance
        if request and not request.user.is_counselor_like and instance is not None and instance.verified:
            # The badge vouches for what the counselor checked; edited content
            # goes back for review.
            if any(value != getattr(instance, key, None) for key, value in attrs.items() if key != 'verified'):
                attrs['verified'] = False
        return attrs


class GoogleDocsModelSerializer(serializers.ModelSerializer):
    """Expose one validated Google Docs link and its embeddable preview URL."""

    google_docs_preview_url = serializers.SerializerMethodField()

    def validate_google_docs_url(self, value):
        return validate_google_docs_url(value)

    def get_google_docs_preview_url(self, obj):
        return google_docs_preview_url(obj.google_docs_url)


def validate_gpa_on_scale(gpa, scale):
    if gpa is not None and scale and gpa > scale:
        raise serializers.ValidationError({'gpa': f'GPA cannot exceed its {scale} scale.'})


class PrivateEvidenceSerializerMixin:
    evidence_resource = ''

    def validate_proof_file(self, upload):
        if upload is None:
            return None
        return validate_private_upload(upload)

    def get_has_proof_file(self, obj) -> bool:
        return bool(obj.proof_file)

    def get_proof_file_previewable(self, obj) -> bool:
        return bool(obj.proof_file) and is_previewable(obj.proof_file_name or obj.proof_file.name)

    def _proof_file_url(self, obj, download=False):
        if not obj.proof_file:
            return None
        request = self.context.get('request')
        path = reverse(f'{self.evidence_resource}-proof-file', kwargs={'pk': obj.pk})
        if download:
            path += '?download=1'
        return request.build_absolute_uri(path) if request else path

    def get_proof_file_preview_url(self, obj) -> str | None:
        return self._proof_file_url(obj) if self.get_proof_file_previewable(obj) else None

    def get_proof_file_download_url(self, obj) -> str | None:
        return self._proof_file_url(obj, download=True)

    def get_proof_resource(self, obj) -> str:
        return self.evidence_resource

    @staticmethod
    def _proof_metadata(upload):
        name, content_type, size = uploaded_file_details(upload, 'evidence')
        return {'proof_file_name': name, 'proof_file_content_type': content_type, 'proof_file_size': size}

    def create(self, validated_data):
        upload = validated_data.get('proof_file')
        if upload:
            validated_data.update(self._proof_metadata(upload))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        proof_supplied = 'proof_file' in validated_data
        upload = validated_data.get('proof_file')
        old_name = instance.proof_file.name if proof_supplied and instance.proof_file else ''
        old_storage = instance.proof_file.storage if old_name else None
        if upload:
            validated_data.update(self._proof_metadata(upload))
        elif proof_supplied:
            validated_data.update({
                'proof_file_name': '',
                'proof_file_content_type': '',
                'proof_file_size': 0,
            })
        updated = super().update(instance, validated_data)
        updated_name = updated.proof_file.name if updated.proof_file else ''
        if old_name and old_name != updated_name:
            delete_file_on_commit(old_storage, old_name)
        return updated
