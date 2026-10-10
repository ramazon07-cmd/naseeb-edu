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


# Every "what changed" in the audit log has one shape, written by audit_diff:
#   {field: {'from': old, 'to': new}}       for plain values (text cut at AUDIT_VALUE_MAX)
#   {field: {'changed_keys': [key, ...]}}   for JSON values: which keys changed, never their content
AUDIT_VALUE_MAX = 200
AUDIT_IGNORED_FIELDS = frozenset({'updated_at'})


def audit_value(value):
    """A JSON-safe, bounded form of a field value for audit metadata."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    value = getattr(value, 'pk', value)
    if value is None or isinstance(value, (int, float)):
        return value
    text = value.isoformat() if hasattr(value, 'isoformat') else str(value)
    return text if len(text) <= AUDIT_VALUE_MAX else f'{text[:AUDIT_VALUE_MAX]}…'


def _as_map(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return dict(enumerate(value))
    return {}


def audit_diff(before, after):
    """The audit shape above for every key of ``before`` whose value in ``after`` differs."""
    changes = {}
    for name, old in before.items():
        if name in AUDIT_IGNORED_FIELDS or name not in after:
            continue
        new = after[name]
        if isinstance(old, (dict, list)) or isinstance(new, (dict, list)):
            if old != new:
                old_map, new_map = _as_map(old), _as_map(new)
                keys = set(old_map) | set(new_map)
                changes[name] = {'changed_keys': sorted(str(key) for key in keys if old_map.get(key) != new_map.get(key))}
            continue
        if getattr(old, 'pk', old) != getattr(new, 'pk', new):
            changes[name] = {'from': audit_value(old), 'to': audit_value(new)}
    return changes


def audit_snapshot(instance, names=None):
    """``{field name: value}`` of ``instance``'s concrete fields (``names`` only, when given)."""
    return {
        field.name: getattr(instance, field.attname)
        for field in instance._meta.concrete_fields
        if names is None or field.name in names
    }


def field_changes(instance, data):
    """:func:`audit_diff` of the concrete fields ``data`` sets on ``instance``.

    Call it before saving; nested and many-to-many values are left out.
    """
    before = audit_snapshot(instance, set(data))
    return audit_diff(before, {name: data[name] for name in before})


# Account fields audited by name only: their values never go into the log.
ACCOUNT_VALUELESS_FIELDS = frozenset({'password', 'avatar'})
# Account changes with an audit action of their own (account.moved,
# account.deactivated / reactivated, staff.tier_changed).
ACCOUNT_OWN_ROW_FIELDS = frozenset({'school', 'is_active', 'admin_tier'})


def account_update_metadata(changes):
    """account.updated metadata: every changed field by name, values where safe to keep."""
    return {
        'fields': sorted(changes),
        'changes': {name: change for name, change in changes.items() if name not in ACCOUNT_VALUELESS_FIELDS},
    }


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
        changes = audit_diff(
            {name: form.initial.get(name) for name in form.changed_data},
            {name: form.cleaned_data.get(name) for name in form.changed_data},
        )
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
