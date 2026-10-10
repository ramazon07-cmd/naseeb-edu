// Product staff: an admin-role account or a Django superuser, whatever its role.
export const isPlatformAdmin = (user) => Boolean(user && (user.is_superuser || user.role === 'admin'));

const STAFF_TIER_RANK = { support: 1, ops: 2, superadmin: 3 };

// Product staff tier check; accounts from before tiers existed have full access.
export const hasStaffTier = (user, tier) => isPlatformAdmin(user)
  && (STAFF_TIER_RANK[user.staff_tier || 'superadmin'] || 0) >= STAFF_TIER_RANK[tier];

// Creating and changing schools, plans and counselor accounts needs the ops tier.
export const canManageWorkspaces = (user) => hasStaffTier(user, 'ops');

// Writes no lower tier's route list allows: roadmap templates and reviews, level approvals, staff accounts.
export const isSuperAdmin = (user) => hasStaffTier(user, 'superadmin');

export const isCounselor = (user) => isPlatformAdmin(user) || user?.role === 'counselor';

// Staff the student CV endpoint lets in (CounselorOrOwnerPermission): counselors
// and product admins, and the teachers and organization account of the school.
export const canDownloadCv = (user) => isCounselor(user) || ['teacher', 'organization'].includes(user?.role);

export const isTaskManager = (user) => isCounselor(user) || user?.role === 'teacher';

// The role whose workspace the user gets; platform admins always get the admin one.
export const workspaceRole = (user) => (isPlatformAdmin(user) ? 'admin' : user?.role);
