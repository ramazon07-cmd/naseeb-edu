import { workspaceRole } from './roles.js';

// Which API collections each role keeps in memory, as [dataKey, endpoint, query?].
//
// Only collections with a per-user bound are loaded up front: a student's or
// parent's own records, catalogues, the admin's counselor roster (three per
// school), roadmap templates, a staff member's own meetings, channels and
// tickets. Staff-wide collections (students, tasks, applications, documents,
// essays, portfolio records, roadmap missions, accounts, audit events, all
// support tickets) grow with the number of students and are fetched a page at
// a time by the page that shows them (hooks/usePagedList).
const STUDENT_RESOURCES = ['students', 'tasks', 'applications', 'documents', 'essays', 'achievements', 'researches', 'projects', 'internships', 'activities', 'honors', 'recommendations'].map((key) => [key, key]);
const PORTAL_RESOURCES = [
  ['roadmapMissions', 'roadmap-missions'], ['bookings', 'bookings'],
  ['messageChannels', 'message-channels'], ['programServices', 'program-services'],
  ['scholarships', 'scholarships'], ['opportunityPrograms', 'opportunity-programs'],
  ['storeItems', 'store-items'], ['team', 'student-team'], ['supportTickets', 'support-tickets'],
];
const ROADMAP_ADMIN = [['counselorRoadmapTemplates', 'counselor-roadmap-templates'], ['counselorRoadmaps', 'counselor-roadmaps']];
const ADMIN_RESOURCES = [['schools', 'schools'], ['accounts', 'users/accounts', '?role=counselor'], ...ROADMAP_ADMIN];
const COUNSELOR_RESOURCES = [['schools', 'schools'], ['universities', 'universities'], ...ROADMAP_ADMIN, ['programServices', 'program-services'], ['bookings', 'bookings'], ['messageChannels', 'message-channels'], ['supportTickets', 'support-tickets']];

export function resourcesFor(user) {
  switch (workspaceRole(user)) {
    case 'parent': return [['parentPortal', 'parent-portal']];
    case 'organization': return [['bookings', 'bookings'], ['messageChannels', 'message-channels'], ['supportTickets', 'support-tickets']];
    case 'teacher': return [['bookings', 'bookings'], ['messageChannels', 'message-channels']];
    case 'admin': return ADMIN_RESOURCES;
    case 'counselor': return COUNSELOR_RESOURCES;
    default: return [...STUDENT_RESOURCES, ['universities', 'universities'], ...PORTAL_RESOURCES];
  }
}

// Staff roles read the large collections through server-paged lists.
export const usesPagedLists = (user) => Boolean(user) && !['student', 'parent'].includes(workspaceRole(user));

// Endpoints a staff role reads through paged lists: a save to one of them
// refreshes those lists (and stats) instead of reloading the workspace.
export const PAGED_ENDPOINTS = ['students', 'tasks', 'applications', 'documents', 'essays', 'achievements', 'researches', 'projects', 'internships', 'activities', 'honors', 'recommendations', 'roadmap-missions', 'users/accounts', 'users/audit-events', 'support-tickets', 'schools', 'meetings'];

// Paged lists that show data written through another endpoint: a school
// card carries its workspace plan, status and seat usage.
const PAGED_DEPENDENTS = { 'users/workspace-subscriptions': ['schools'] };

// The paged lists to refetch after these writes. Any record save can change
// student progress shown in student lists.
export function pagedListsAfter(written) {
  if (!written.length) return [];
  return [...new Set([...written, ...written.flatMap((endpoint) => PAGED_DEPENDENTS[endpoint] || []), 'students'])];
}

// Nothing loads until the password is changed or, for students, onboarding
// is done; product staff never go through onboarding, whatever their role.
export const waitsBeforeLoading = (user) => !user || Boolean(user.must_change_password)
  || (workspaceRole(user) === 'student' && !user.student_profile_complete);

// The dashboard stats endpoint is loaded for everyone except parents and
// students: the student dashboard reads its numbers from the student record.
export const loadsDashboardStats = (user) => !['parent', 'student'].includes(workspaceRole(user));

// Students load their collections page by page: sign-in fetches only what the
// dashboard shows, and every other page fetches its own collections the first
// time it opens (then keeps them like before). Other roles load everything at
// sign-in, as they always have.
export const loadsLazily = (user) => workspaceRole(user) === 'student';

// Collections every student page needs: the own student record (avatar,
// progress) and the support tickets behind the sidebar's unread badge (the
// API has no unread-count endpoint for tickets yet).
export const STUDENT_SHELL_KEYS = ['students', 'supportTickets'];

// The workspace collections each student page renders.
export const STUDENT_PAGE_KEYS = {
  dashboard: ['tasks', 'bookings', 'essays', 'team', 'programServices'],
  student_center: ['tasks', 'applications', 'essays', 'documents', 'researches', 'projects', 'internships', 'activities', 'honors', 'achievements', 'recommendations'],
  find_personality: [],
  roadmap: ['roadmapMissions', 'tasks'],
  bookings: ['bookings'],
  messages: ['messageChannels'],
  programs: ['opportunityPrograms'],
  essay_lab: [],
  applications: ['applications', 'universities'],
  college_search: ['universities', 'applications', 'scholarships'],
  store: ['storeItems'],
  screen_time: [],
  support: ['supportTickets'],
};

// Keys a student page renders (and waits for): the own student record plus
// the page's collections. The shell's support tickets only feed a badge.
export function studentPageKeys(page) {
  return [...new Set(['students', ...(STUDENT_PAGE_KEYS[page] || [])])];
}

// Keys to fetch when a student opens a page: the wanted collections of this
// role that were never requested before. Other roles loaded everything.
export function missingKeys(user, wanted, requested) {
  if (!loadsLazily(user)) return [];
  const available = new Set(resourcesFor(user).map(([key]) => key));
  return [...new Set(wanted)].filter((key) => available.has(key) && !requested.has(key));
}

/**
 * Keys a student's loadData call refetches. `requestedKeys` is the caller's
 * explicit list, or null for "everything" (a refresh, or a save the reload
 * plan could not map); `requested` holds the keys fetched so far. Collections
 * that were never opened stay unloaded: their page fetches them fresh.
 */
export function lazyReloadKeys(requestedKeys, requested, { explicit = false } = {}) {
  if (!requestedKeys) return [...new Set([...STUDENT_SHELL_KEYS, ...requested])];
  if (explicit) return [...new Set(requestedKeys)];
  return [...new Set(requestedKeys)].filter((key) => requested.has(key));
}

/**
 * The [key, endpoint] pairs one workspace load fetches ('dashboard' = stats).
 * `planned`: explicit keys, a reload plan's keys (`changed`), or null for all.
 * `requested`: keys this session already fetched (lazy students only).
 */
export function selectWorkspaceLoad(user, planned, requested = new Set(), { changed = false } = {}) {
  const lazyKeys = loadsLazily(user) ? lazyReloadKeys(planned, requested, { explicit: !changed }) : null;
  const wanted = lazyKeys ? new Set(lazyKeys) : planned ? new Set(planned) : null;
  return [...(loadsDashboardStats(user) ? [['dashboard']] : []), ...resourcesFor(user)]
    .filter(([key]) => !wanted || wanted.has(key));
}
