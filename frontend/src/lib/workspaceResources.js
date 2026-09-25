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

// The dashboard stats endpoint is loaded for everyone except parents.
export const loadsDashboardStats = (user) => workspaceRole(user) !== 'parent';
