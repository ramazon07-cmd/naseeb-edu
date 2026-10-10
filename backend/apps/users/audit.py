"""Product audit trail writers: one INSERT per event, never a lookup."""
from contextlib import contextmanager
from contextvars import ContextVar

from .models import ProductAuditEvent

_recording = ContextVar('audit_recording', default=None)


@contextmanager
def recorded_actions():
    """Collect the actions audited inside the block (by any service it calls)."""
    actions = []
    token = _recording.set(actions)
    try:
        yield actions
    finally:
        _recording.reset(token)


def _school_id(target, school):
    if school is not None:
        return getattr(school, 'pk', school)
    from apps.admissions.models import School

    if isinstance(target, School):
        return target.pk
    # A loaded instance already carries school_id; reading it costs no query.
    return getattr(target, 'school_id', None)


def build_event(*, actor, action, target, metadata=None, school=None):
    return ProductAuditEvent(
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        action=action,
        target_type=target._meta.label_lower,
        target_id=str(target.pk or ''),
        target_label=str(target)[:255],
        metadata=metadata or {},
        school_id=_school_id(target, school),
    )


def audit_product_action(*, actor, action, target, metadata=None, school=None):
    event = build_event(actor=actor, action=action, target=target, metadata=metadata, school=school)
    event.save(force_insert=True)
    recording = _recording.get()
    if recording is not None:
        recording.append(action)
    return event


AUDIT_VALUE_MAX = 200


def audit_value(value):
    """A JSON-safe, bounded form of a field value for audit metadata."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    value = getattr(value, 'pk', value)
    if value is None or isinstance(value, (int, float)):
        return value
    text = value.isoformat() if hasattr(value, 'isoformat') else str(value)
    return text[:AUDIT_VALUE_MAX]


def field_changes(instance, data):
    """``{field: {'from', 'to'}}`` for the concrete fields ``data`` changes on ``instance``.

    Call it before saving; nested and many-to-many values are left out.
    """
    from django.core.exceptions import FieldDoesNotExist

    changes = {}
    for name, value in data.items():
        try:
            field = instance._meta.get_field(name)
        except FieldDoesNotExist:
            continue
        if not field.concrete or field.many_to_many:
            continue
        before = audit_value(getattr(instance, field.attname))
        after = audit_value(value)
        if before != after:
            changes[name] = {'from': before, 'to': after}
    return changes


class ProductAuditAdminMixin:
    """Django-admin edits of product data write the same audit rows as the API.

    ``audit_prefix`` names the record (``'plan'`` -> ``plan.created``,
    ``plan.updated``, ``plan.deleted``). The admin wraps each save and delete
    in a transaction, so the row and the change commit together.
    """

    audit_prefix = ''
    audit_update_verb = 'updated'

    def _audit(self, request, obj, verb, **metadata):
        audit_product_action(
            actor=request.user, action=f'{self.audit_prefix}.{verb}', target=obj,
            metadata={'source': 'django_admin', **metadata},
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            self._audit(request, obj, 'created')
            return
        changes = {
            name: {'from': audit_value(form.initial.get(name)), 'to': audit_value(form.cleaned_data.get(name))}
            for name in form.changed_data
        }
        self._audit(request, obj, self.audit_update_verb, changes=changes)

    def delete_model(self, request, obj):
        self._audit(request, obj, 'deleted')
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self._audit(request, obj, 'deleted')
        super().delete_queryset(request, queryset)


def audit_many(events):
    """Write several built events in one statement."""
    return ProductAuditEvent.objects.bulk_create(events) if events else []


def audit_staff_read(request, target, action, **metadata):
    """Record a product-staff read of one person's data; no-op for other roles."""
    user = request.user
    if not getattr(user, 'is_product_admin', False):
        return None
    return audit_product_action(
        actor=user,
        action=action,
        target=target,
        metadata={'staff_tier': user.staff_tier, **metadata},
    )
