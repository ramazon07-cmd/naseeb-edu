// Path <-> page mapping for the signed-in workspace (History API routing).
// Framework-free so the mapping and the role guards are unit tested.
import { isCounselor, isPlatformAdmin } from './roles.js';

// Product-admin pages live under /platform: /admin/ is Django's admin site.
export const PAGE_PATHS = {
  dashboard: '/dashboard',
  schools: '/schools',
  students: '/students',
  academics: '/academics',
  portfolio: '/portfolio',
  activities: '/activities',
  recommendations: '/recommendations',
  tasks: '/tasks',
  applications: '/applications',
  documents: '/documents',
  certificates: '/certificates',
  essays: '/essays',
  student_center: '/student-center',
  find_personality: '/profile-assessment',
  roadmap: '/roadmap',
  bookings: '/meetings',
  messages: '/messages',
  programs: '/programs',
  essay_lab: '/essay-lab',
  college_search: '/college-search',
  store: '/store',
  support: '/support',
  screen_time: '/screen-time',
  parent_progress: '/family/progress',
  parent_tasks: '/family/tasks',
  parent_applications: '/family/applications',
  parent_documents: '/family/documents',
  parent_meetings: '/family/meetings',
  admin_dashboard: '/platform',
  admin_schools: '/platform/schools',
  admin_counselors: '/platform/counselors',
  admin_students: '/platform/students',
  counselor_roadmap: '/counselor-roadmap',
  admin_audit: '/platform/audit',
};

const PATH_PAGES = new Map(Object.entries(PAGE_PATHS).map(([page, path]) => [path, page]));
// The old full-form profile editor: its answers are edited in the Student Center now.
const PATH_ALIASES = new Map([['/profile', 'student_center']]);

export const LOGIN_PATH = '/login';
export const LANDING_PATH = '/';

export const STUDENT_CENTER_TABS = ['overview', 'academics', 'portfolio', 'activities', 'documents'];
// Students see path/tasks, staff missions/tasks/timeline/reflections; the bare
// /roadmap path opens the role's first tab, so no tab is the default here.
export const ROADMAP_TABS = ['path', 'missions', 'tasks', 'timeline', 'reflections'];
// /messages/counselor opens the student's earlier counselor messages.
export const MESSAGES_TABS = ['counselor'];
const DEFAULT_TAB = { student_center: 'overview' };
const ROADMAP_ROLE_TABS = { student: ['path', 'tasks'], staff: ['missions', 'tasks', 'timeline', 'reflections'] };
// Student Center cards that open in edit mode from a link (?edit=goal).
export const STUDENT_CENTER_EDIT_SECTIONS = ['personal', 'academics', 'tests', 'goal', 'honors', 'activities'];

// The roadmap tab to show: the requested one when this role has it, else the role's first.
export function roadmapTab(tab, manager) {
  const tabs = ROADMAP_ROLE_TABS[manager ? 'staff' : 'student'];
  return tabs.includes(tab) ? tab : tabs[0];
}
const TAB_PAGES = { student_center: STUDENT_CENTER_TABS, roadmap: ROADMAP_TABS, messages: MESSAGES_TABS };

// Record pages: /essay-lab/essays/42, /students/15, /platform/students/15,
// /messages/9 (open that chat).
const RECORD_ROUTES = {
  essay_lab: { segment: 'essays', param: 'essayId' },
  students: { segment: '', param: 'studentId' },
  admin_students: { segment: '', param: 'studentId' },
  messages: { segment: '', param: 'channelId' },
};

const ID_PATTERN = /^[1-9]\d{0,9}$/;

function normalizePath(pathname) {
  const path = String(pathname || '/').replace(/\/{2,}/g, '/');
  return path.length > 1 ? path.replace(/\/+$/, '') : path;
}

// '/essay-lab/essays/42' -> { page: 'essay_lab', params: { essayId: 42 } };
// null for anything that is not a workspace page.
export function parsePath(pathname) {
  const path = normalizePath(pathname);
  if (PATH_PAGES.has(path)) return { page: PATH_PAGES.get(path), params: {} };
  if (PATH_ALIASES.has(path)) return { page: PATH_ALIASES.get(path), params: {} };
  const cut = path.lastIndexOf('/');
  const base = path.slice(0, cut);
  const last = path.slice(cut + 1);
  // Base paths are unique across both kinds, so at most one branch matches.
  for (const [page, tabs] of Object.entries(TAB_PAGES)) {
    // The default tab has no segment of its own; its explicit path is still
    // accepted and canonicalised to the bare page path.
    if (PAGE_PATHS[page] === base && tabs.includes(last)) return { page, params: last === DEFAULT_TAB[page] ? {} : { tab: last } };
  }
  if (!ID_PATTERN.test(last)) return null;
  for (const [page, { segment, param }] of Object.entries(RECORD_ROUTES)) {
    const expected = segment ? `${PAGE_PATHS[page]}/${segment}` : PAGE_PATHS[page];
    if (expected === base) return { page, params: { [param]: Number(last) } };
  }
  return null;
}

export function buildPath({ page, params = {} } = {}) {
  const base = PAGE_PATHS[page];
  if (!base) return PAGE_PATHS.dashboard;
  const tabs = TAB_PAGES[page];
  // Every section card is on the overview tab.
  if (page === 'student_center' && STUDENT_CENTER_EDIT_SECTIONS.includes(params.edit)) return `${base}?edit=${params.edit}`;
  if (tabs && tabs.includes(params.tab) && params.tab !== DEFAULT_TAB[page]) return `${base}/${params.tab}`;
  const record = RECORD_ROUTES[page];
  const id = record ? params[record.param] : null;
  if (record && ID_PATTERN.test(String(id ?? ''))) return `${base}${record.segment ? `/${record.segment}` : ''}/${id}`;
  return base;
}

// Sidebar order per role.
export function navigationFor(user) {
  if (isPlatformAdmin(user)) return ['admin_dashboard', 'admin_schools', 'admin_counselors', 'admin_students', 'counselor_roadmap', 'admin_audit', 'support'];
  if (user?.role === 'parent') return ['dashboard', 'parent_progress', 'parent_tasks', 'parent_applications', 'parent_documents', 'parent_meetings'];
  if (isCounselor(user)) return ['dashboard', 'students', 'counselor_roadmap', 'academics', 'portfolio', 'activities', 'recommendations', 'tasks', 'roadmap', 'applications', 'documents', 'certificates', 'essays', 'bookings', 'messages', 'screen_time', 'support'];
  if (user?.role === 'teacher') return ['dashboard', 'students', 'tasks', 'roadmap', 'bookings', 'messages', 'screen_time'];
  if (user?.role === 'organization') return ['dashboard', 'students', 'bookings', 'messages', 'screen_time', 'support'];
  return ['dashboard', 'student_center', 'find_personality', 'roadmap', 'bookings', 'messages', 'programs', 'essay_lab', 'applications', 'college_search', 'store', 'screen_time', 'support'];
}

// Pages a role sees in its navigation but cannot open yet: the sidebar shows
// them locked ("Coming soon") and their paths fall back to the home page.
const LOCKED_PAGES = { student: ['store'] };

export function lockedPages(user) {
  if (!user || isPlatformAdmin(user)) return new Set();
  return new Set(LOCKED_PAGES[user.role] || []);
}

export const isPageLocked = (page, user) => lockedPages(user).has(page);

export function reachablePages(user) {
  if (!user) return new Set();
  const extra = user.role === 'parent' && !isPlatformAdmin(user) ? [] : ['screen_time'];
  const locked = lockedPages(user);
  return new Set([...navigationFor(user), ...extra].filter((page) => !locked.has(page)));
}

export const homePage = (user) => (isPlatformAdmin(user) ? 'admin_dashboard' : 'dashboard');

// A link shared from a staff workspace still opens for product admins, who
// have their own copy of these pages.
const ADMIN_ALIASES = { dashboard: 'admin_dashboard', students: 'admin_students', schools: 'admin_schools' };

// The page this user sees for a requested page: the page itself, its admin
// twin, or null when the role cannot open it.
export function openablePage(page, user) {
  if (!user) return null;
  const allowed = reachablePages(user);
  if (allowed.has(page)) return page;
  const alias = isPlatformAdmin(user) ? ADMIN_ALIASES[page] : null;
  return alias && allowed.has(alias) ? alias : null;
}

export const canOpenPage = (page, user) => openablePage(page, user) !== null;

// The page this user may see for a requested route: the route itself, its
// admin twin, or the role's home page for unknown and forbidden paths.
export function resolveRoute(route, user) {
  const page = route ? openablePage(route.page, user) : null;
  return page ? { page, params: route.params || {} } : { page: homePage(user), params: {} };
}

// Only same-site workspace paths are accepted as a post-login destination,
// so ?next= can never send someone to another site.
export function safeNextPath(next) {
  if (typeof next !== 'string' || !next.startsWith('/') || next.startsWith('//') || next.includes('\\')) return null;
  let url;
  try {
    url = new URL(next, 'http://naseeb.invalid');
  } catch {
    return null;
  }
  if (url.origin !== 'http://naseeb.invalid' || !parsePath(url.pathname)) return null;
  return `${normalizePath(url.pathname)}${url.search}`;
}

export function loginPath(next) {
  const target = safeNextPath(next);
  return target ? `${LOGIN_PATH}?next=${encodeURIComponent(target)}` : LOGIN_PATH;
}

// Public pages: '/login' (and the old '#/login' link) or the landing page.
export function publicPageFor(pathname, hash = '') {
  const path = normalizePath(pathname);
  if (path === LOGIN_PATH || (path === LANDING_PATH && hash === '#/login')) return 'login';
  if (path === LANDING_PATH) return 'landing';
  return null;
}

// Applies query updates to a search string, keeping keys it does not own
// (e.g. ?lang=). Empty values and defaults are removed so URLs stay short.
export function withQuery(search, updates, defaults = {}) {
  const params = new URLSearchParams(search || '');
  const asText = (value) => (value === true ? '1' : value === false ? '0' : value == null ? '' : String(value).trim());
  for (const [key, value] of Object.entries(updates)) {
    const text = asText(value);
    if (!text || text === asText(defaults[key])) params.delete(key);
    else params.set(key, text);
  }
  const text = params.toString();
  return text ? `?${text}` : '';
}
