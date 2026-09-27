// Product staff: an admin-role account or a Django superuser, whatever its role.
export const isPlatformAdmin = (user) => Boolean(user && (user.is_superuser || user.role === 'admin'));

const STAFF_TIER_RANK = { support: 1, ops: 2, superadmin: 3 };

// Product staff tier check; accounts from before tiers existed have full access.
export const hasStaffTier = (user, tier) => isPlatformAdmin(user)
  && (STAFF_TIER_RANK[user.staff_tier || 'superadmin'] || 0) >= STAFF_TIER_RANK[tier];

// Creating and changing schools, plans and counselor accounts needs the ops tier.
export const canManageWorkspaces = (user) => hasStaffTier(user, 'ops');

export const isCounselor = (user) => isPlatformAdmin(user) || user?.role === 'counselor';

export const isTaskManager = (user) => isCounselor(user) || user?.role === 'teacher';

// The role whose workspace the user gets; platform admins always get the admin one.
export const workspaceRole = (user) => (isPlatformAdmin(user) ? 'admin' : user?.role);
