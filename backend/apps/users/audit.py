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
