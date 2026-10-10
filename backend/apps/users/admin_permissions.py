"""Product-staff permission tiers.

support    reads everything product admins can read, resets credentials,
           views the audit log and opens audited support views.
ops        support + workspace, plan and account provisioning.
superadmin everything, including staff tiers and admin roles.
"""
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

from .localization import localized_message
from .models import User


TIER_RANK = {
    User.AdminTier.SUPPORT: 1,
    User.AdminTier.OPS: 2,
    User.AdminTier.SUPERADMIN: 3,
}

# Product admins pass the broad counselor-level checks everywhere, so lower
# tiers are limited centrally: a write is allowed only on these routes.
SUPPORT_WRITE_ROUTES = frozenset({
    'accounts-temporary-credential',
    'accounts-support-view',
    'accounts-change-password',
    # The signed-in staff member's own account and activity, never anyone else's.
    'accounts-account-email',
    'accounts-dashboard-layout',
    'screen-time-track',
    # Answering a ticket (status and reply) is the support tier's job; the
    # requester's subject, message and category are read-only for all staff.
    'support-tickets-detail',
})
OPS_WRITE_ROUTES = SUPPORT_WRITE_ROUTES | frozenset({
    'schools-list',
    'schools-detail',
    'schools-create-account',
    'accounts-list',
    'accounts-detail',
    'accounts-create-counselor',
    'accounts-create-individual-counselor',
    'accounts-transfer-school',
    'accounts-deactivate',
    'students-quick-create',
    'students-assign-counselor',
    # Edit and deactivate (DELETE) a student from Student 360.
    'students-detail',
    'workspace-subscriptions-detail',
    # The admin catalogue editor (apps/admissions/views/catalog.py).
    'catalog-universities-list',
    'catalog-universities-detail',
    'catalog-programs-list',
    'catalog-programs-detail',
    'catalog-scholarships-list',
    'catalog-scholarships-detail',
    'catalog-opportunity-programs-list',
    'catalog-opportunity-programs-detail',
})
WRITE_ROUTES = {
    User.AdminTier.SUPPORT: SUPPORT_WRITE_ROUTES,
    User.AdminTier.OPS: OPS_WRITE_ROUTES,
}


def has_tier(user, tier):
    if not (user and user.is_authenticated and user.is_product_admin):
        return False
    return TIER_RANK.get(user.staff_tier, 0) >= TIER_RANK[tier]


def staff_tier_denied(request):
    return PermissionDenied({
        'detail': localized_message('staff_tier_forbidden', request),
        'code': 'staff_tier_forbidden',
    })


def enforce_staff_write_scope(request, user):
    """Reject a write outside the routes the caller's staff tier may use."""
    if not user.is_product_admin:
        return
    allowed = WRITE_ROUTES.get(user.staff_tier)
    if allowed is None:
        return
    match = getattr(request, 'resolver_match', None)
    if match is not None and match.url_name in allowed:
        return
    raise staff_tier_denied(request)


class StaffTierPermission(permissions.BasePermission):
    tier = User.AdminTier.SUPERADMIN

    def has_permission(self, request, view):
        return has_tier(request.user, self.tier)


class IsSupportStaff(StaffTierPermission):
    tier = User.AdminTier.SUPPORT


class IsOpsStaff(StaffTierPermission):
    tier = User.AdminTier.OPS


class IsSuperAdmin(StaffTierPermission):
    tier = User.AdminTier.SUPERADMIN


class SupportReadOpsWrite(permissions.BasePermission):
    """Support staff read; ops staff and above write."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return has_tier(request.user, User.AdminTier.SUPPORT)
        return has_tier(request.user, User.AdminTier.OPS)


class SupportReadSuperadminWrite(permissions.BasePermission):
    """Support staff read; only super admins write (plans and other platform settings)."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return has_tier(request.user, User.AdminTier.SUPPORT)
        return has_tier(request.user, User.AdminTier.SUPERADMIN)
