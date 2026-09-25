// Public-page styles first, in their original cascade position (before the
// dashboard and onboarding sheets and before styles.css in main.jsx).
import './landing.css';
import './mind-section.css';
import { Activity, Award, Bell, ChevronsLeft, ChevronsRight, BookOpen, Building2, CalendarClock, ChevronRight, ClipboardCheck, Clock3, Compass, Download, FileText, Fingerprint, FolderKanban, Globe2, GraduationCap, LayoutDashboard, LifeBuoy, Lock, LogOut, Menu, MessageCircle, MessageSquareText, PenLine, RefreshCw, School, Search, ShieldAlert, ShieldCheck, ShoppingCart, Target, UserRound, Users, UsersRound, WifiOff, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ScreenTimeShortcut } from './CompactDashboard';
import { api } from './api';
import { AssistantCenter } from './components/AssistantCenter';
import { ScreenTimeTracker, flushActiveScreenTime } from './components/ScreenTimeTracker';
import { AppBootLoader, BootstrapError, BrandLockup, LanguageSelector, ThemeToggle } from './components/brand';
import { ProfileCard, StudentAvatar } from './components/records';
import { LazyBoundary, PageSkeleton } from './components/states';
import { lazyWithRetry } from './lib/retryableLazy';
import { pageLoadState } from './lib/pageLoadState';
import { Empty, Modal } from './components/ui';
import { NotificationPanel } from './components/NotificationPanel';
import { formatNumberLocale, getLanguage, locale, setLanguage, siteTitle, t, tp, tx } from './i18n';
import { exportNodePdf } from './lib/exportPdf';
import { fullName, initials, label, ownStudent } from './lib/labels';
import { isCounselor, isPlatformAdmin, isTaskManager } from './lib/roles';
import { LANDING_PATH, LOGIN_PATH, buildPath, canOpenPage, isPageLocked, loginPath, navigationFor, openablePage, parsePath, publicPageFor, resolveRoute, safeNextPath } from './lib/routes';
import { buildIndex, mergeSearchResults, remoteSearchEntries, searchIndex, searchText } from './lib/searchIndex';
import { usesPagedLists } from './lib/workspaceResources';
import { useRemoteSearch } from './hooks/useRemoteSearch';
import { useSupportCounts } from './hooks/useSupportCounts';
import { useNotificationBell } from './hooks/useNotificationBell';
import { invalidatePagedLists } from './hooks/usePagedList';
import { bellTotal } from './lib/notifications';
import { ForcedPasswordChange, Login } from './pages/Login';
import { clearUserSessionStorage, clearUserStorage, dropLegacySharedKeys } from './userStorage';
import { useTheme } from './hooks/useTheme';
import { useOnlineStatus } from './hooks/useOnlineStatus';
import { useToast } from './hooks/useToast';
import { RELOAD_CHANGED, useWorkspaceData } from './hooks/useWorkspaceData';
// Onboarding styles stay in the main stylesheet (after dashboard.css) so the
// lazy onboarding chunk does not reorder the cascade.
import './student-onboarding.css';

// Route-level code splitting: landing visitors do not download the assessment
// banks, and signed-in users do not download the landing page.
const LandingPage = lazyWithRetry(() => import('./LandingPage'));
const StudentOnboarding = lazyWithRetry(() => import('./StudentOnboarding'));
const ProfileAssessmentPage = lazyWithRetry(() => import('./pages/ProfileAssessmentPage'));
// Workspace pages are chunks of their own, loaded on first visit (PageRouter
// renders inside a Suspense boundary), so landing visitors never download them.
const lazyNamed = (load, name) => lazyWithRetry(() => load().then((module) => ({ default: module[name] })));
const EssayLab = lazyWithRetry(() => import('./essayLab/EssayLab.jsx'));
const AdminAuditPage = lazyNamed(() => import('./pages/AdminPages'), 'AdminAuditPage');
const AdminControlDashboard = lazyNamed(() => import('./pages/AdminPages'), 'AdminControlDashboard');
const AdminCounselorsPage = lazyNamed(() => import('./pages/AdminPages'), 'AdminCounselorsPage');
const CounselorRoadmapPage = lazyNamed(() => import('./pages/AdminPages'), 'CounselorRoadmapPage');
const ApplicationsPortalPage = lazyNamed(() => import('./pages/ApplicationsPortalPage'), 'ApplicationsPortalPage');
const BookingsPage = lazyNamed(() => import('./pages/BookingsPage'), 'BookingsPage');
const CollegeSearchPage = lazyNamed(() => import('./pages/CollegeSearchPage'), 'CollegeSearchPage');
const Dashboard = lazyNamed(() => import('./pages/DashboardPage'), 'Dashboard');
const DocumentsPage = lazyNamed(() => import('./pages/DocumentsPage'), 'DocumentsPage');
const MessagesPage = lazyNamed(() => import('./pages/MessagesPage'), 'MessagesPage');
const ParentPortalPage = lazyNamed(() => import('./pages/ParentPortalPage'), 'ParentPortalPage');
const ProgramsPage = lazyNamed(() => import('./pages/ProgramsPage'), 'ProgramsPage');
const ResourceSection = lazyNamed(() => import('./pages/ResourceSection'), 'ResourceSection');
const RoadmapPage = lazyNamed(() => import('./pages/RoadmapPage'), 'RoadmapPage');
const SchoolsPage = lazyNamed(() => import('./pages/SchoolsPage'), 'SchoolsPage');
const ScreenTimePage = lazyNamed(() => import('./pages/ScreenTimePage'), 'ScreenTimePage');
const StorePage = lazyNamed(() => import('./pages/StorePage'), 'StorePage');
const StudentCenterPage = lazyNamed(() => import('./pages/StudentCenterPage'), 'StudentCenterPage');
const StudentsPage = lazyNamed(() => import('./pages/StudentsPage'), 'StudentsPage');
const SupportPage = lazyNamed(() => import('./pages/SupportPage'), 'SupportPage');

// Kept equal to CHALLENGES.length by tests/codeSplitting.test.mjs, so the
// navigation does not pull the question banks into the main bundle.
export const ASSESSMENT_CHALLENGE_COUNT = 4;

const SIDEBAR_KEY = 'naseeb-edu-sidebar';

const readLocation = () => ({ pathname: window.location.pathname, search: window.location.search, hash: window.location.hash });

// Export belongs to the page, not to every panel on it. These are the pages
// whose content is a record people print; student_center keeps its own button
// because it prints the Overview tab rather than whatever tab is open.
const PDF_EXPORT_PAGES = new Set([
  'student_center',
  'students', 'admin_students', 'academics', 'portfolio', 'activities', 'recommendations',
  'tasks', 'roadmap', 'applications', 'documents', 'certificates', 'essays',
]);

const PAGE_META = {
  dashboard: { label: 'Dashboard', icon: LayoutDashboard, description: 'A complete view of the application journey' },
  schools: { label: 'Schools', icon: Building2, description: 'Schools and organization accounts' },
  students: { label: 'Students', icon: Users, description: 'Student profiles and progress' },
  academics: { label: 'Academics', icon: BookOpen, description: 'Academic results and research' },
  portfolio: { label: 'Portfolio', icon: FolderKanban, description: 'Projects and internship experience' },
  activities: { label: 'Activities', icon: Activity, description: 'Activities, honors, and achievements' },
  recommendations: { label: 'Recommendations', icon: MessageSquareText, description: 'Recommendation letter progress' },
  tasks: { label: 'Tasks', icon: ClipboardCheck, description: 'Assignments and deadline tracking' },
  applications: { label: 'Applications', icon: Target, description: 'University application pipeline' },
  documents: { label: 'Documents', icon: FileText, description: 'Documents, uploads, and review' },
  certificates: { label: 'Certificates', icon: Award, description: 'Certificates and supporting files' },
  essays: { label: 'Essays', icon: GraduationCap, description: 'Essay drafts and revision history' },
  student_center: { label: 'Student Center', icon: UsersRound, description: 'Academic profile, portfolio, activities, and documents' },
  find_personality: { label: 'Profile Assessment', icon: Fingerprint, description: `${ASSESSMENT_CHALLENGE_COUNT} challenges that reveal your best-fit study directions` },
  roadmap: { label: 'Roadmap', icon: Compass, description: 'Level-linked missions, milestones, and reflections' },
  bookings: { label: 'Meetings', icon: CalendarClock, description: 'Schedule and manage meetings' },
  messages: { label: 'Messages', icon: MessageCircle, description: 'Private, group, and discussion messages' },
  programs: { label: 'Programs', icon: Globe2, description: 'National and international opportunity catalog' },
  essay_lab: { label: 'Essay Lab', icon: PenLine, description: 'Essay drafts, feedback, and revision history' },
  college_search: { label: 'College Search', icon: School, description: 'Find, compare, and shortlist universities' },
  store: { label: 'Naseeb Store', icon: ShoppingCart, description: 'Additional education and application services' },
  support: { label: 'Support', icon: LifeBuoy, description: 'Contact support and track your requests' },
  screen_time: { label: 'Screen Time', icon: Clock3, description: 'Active learning time without idle minutes' },
  parent_progress: { label: 'Progress', icon: Activity, description: 'Academic profile and application journey' },
  parent_tasks: { label: 'Tasks', icon: ClipboardCheck, description: 'Assigned work and upcoming deadlines' },
  parent_applications: { label: 'Applications', icon: Target, description: 'University application status' },
  parent_documents: { label: 'Documents', icon: FileText, description: 'Document checklist and review status' },
  parent_meetings: { label: 'Meetings', icon: CalendarClock, description: 'Upcoming and completed counselor meetings' },
  admin_dashboard: { label: 'Admin Control', icon: ShieldCheck, description: 'Platform provisioning and operational overview' },
  admin_schools: { label: 'Schools', icon: Building2, description: 'Create and manage organization workspaces' },
  admin_counselors: { label: 'Counselors', icon: UserRound, description: 'Provision, transfer, and deactivate counselors' },
  admin_students: { label: 'Student 360', icon: Users, description: 'Open every permitted student profile' },
  counselor_roadmap: { label: 'Counselor Roadmap', icon: Compass, description: 'Professional and school-management milestones' },
  admin_audit: { label: 'Audit Log', icon: ShieldAlert, description: 'Review product administration actions' }
};

const GLOBAL_SEARCH_RESOURCES = {
  schools: 'schools', students: 'students', tasks: 'tasks', applications: 'applications', documents: 'documents',
  essays: 'essays', achievements: 'activities', researches: 'academics', projects: 'portfolio', internships: 'portfolio',
  activities: 'activities', honors: 'activities', recommendations: 'recommendations', roadmapMissions: 'roadmap',
  bookings: 'bookings', messageChannels: 'messages', programServices: 'dashboard',
  universities: 'college_search', scholarships: 'college_search', opportunityPrograms: 'programs',
  storeItems: 'store', team: 'dashboard', supportTickets: 'support',
  accounts: 'admin_counselors', counselorRoadmaps: 'counselor_roadmap'
};

function globalSearchTitle(resource, item) {
  if (resource === 'students') return fullName(item.user_detail);
  if (resource === 'schools') return item.name;
  if (resource === 'applications') return item.university_name || item.program;
  if (resource === 'documents') return item.title || item.file_name;
  if (resource === 'bookings') return item.topic;
  if (resource === 'messageChannels') return item.name || item.title;
  if (resource === 'programServices') return item.name;
  if (resource === 'universities') return item.name;
  if (resource === 'team') return item.name;
  return item.title || item.name || item.organization || item.recommender_name || item.subject || item.program || item.category;
}

// Built once per (user, data, language) instead of JSON.stringify-ing every
// record on every keystroke; typing only filters the prepared haystacks.
function buildGlobalSearchIndex(user, data) {
  const navigation = navigationFor(user).filter((page) => !isPageLocked(page, user));
  const allowedPages = new Set(navigation);
  const pages = navigation.map((destination) => {
    const meta = PAGE_META[destination];
    return { id: `page-${destination}`, kind: 'page', destination, title: t(meta.label), subtitle: t(meta.description), text: `${t(meta.label)} ${t(meta.description)} ${meta.label} ${meta.description}` };
  });
  const records = Object.entries(GLOBAL_SEARCH_RESOURCES).flatMap(([resource, destination]) => {
    if (!allowedPages.has(destination)) return [];
    const items = Array.isArray(data[resource]) ? data[resource] : [];
    return items.flatMap((item, index) => {
      const title = globalSearchTitle(resource, item);
      if (!title) return [];
      return [{ id: `${resource}-${item.id ?? index}`, kind: 'record', destination, title: String(title), subtitle: t(PAGE_META[destination].label), filterQuery: String(title), text: `${title} ${searchText(item)}` }];
    });
  });
  return buildIndex([...pages, ...records], (entry) => entry.text, locale());
}

function globalSearchResults(index, query) {
  return searchIndex(index, query, locale(), 10).map(({ text: _text, ...result }) => result);
}

// Server search result type -> the page that lists it, when this user has it.
function remoteSearchDestinations(user) {
  const allowed = new Set(navigationFor(user));
  const admin = isPlatformAdmin(user);
  const pick = (page) => allowed.has(page) ? page : null;
  return {
    students: pick(admin ? 'admin_students' : 'students'), tasks: pick('tasks'),
    applications: pick('applications'), documents: pick('documents'), essays: pick('essays'), recommendations: pick('recommendations'),
    roadmapMissions: pick('roadmap'), bookings: pick('bookings'), schools: pick(admin ? 'admin_schools' : 'schools'),
    accounts: pick('admin_counselors'), supportTickets: pick('support'),
  };
}

const PAGE_RESOURCE_KEYS = {
  dashboard: ['dashboard', 'students', 'tasks', 'applications', 'essays', 'achievements', 'honors', 'bookings', 'team', 'programServices', 'parentPortal'],
  schools: ['schools'], students: ['students'], academics: ['students', 'researches'],
  portfolio: ['projects', 'internships'], activities: ['activities', 'honors', 'achievements'],
  recommendations: ['recommendations'], tasks: ['tasks', 'students'],
  roadmap: ['roadmapMissions', 'tasks', 'students'], applications: ['applications', 'universities', 'students'],
  documents: ['documents'], certificates: ['documents'], essays: ['essays'],
  student_center: ['students', 'researches', 'projects', 'internships', 'activities', 'honors', 'achievements', 'recommendations', 'documents'],
  bookings: ['bookings'], messages: ['messageChannels'],
  programs: ['opportunityPrograms', 'scholarships'], essay_lab: [],
  college_search: ['students', 'universities', 'applications'], store: ['storeItems'], support: ['supportTickets'],
  screen_time: [],
  parent_progress: ['parentPortal'], parent_tasks: ['parentPortal'], parent_applications: ['parentPortal'],
  parent_documents: ['parentPortal'], parent_meetings: ['parentPortal']
};

function PageDataBoundary({ page, data, stats, loading, resourceStatus, retry, children }) {
  const keys = PAGE_RESOURCE_KEYS[page] || [page];
  const { loadingKeys, failedKeys, hasVisibleData, initialLoading } = pageLoadState({ keys, data, stats, loading, resourceStatus });

  if (initialLoading) return <PageSkeleton />;
  return <>
    {failedKeys.length > 0 && <div className="data-state error" role="alert"><X size={18} /><div><b>{t("Some information could not be loaded")}</b><p>{failedKeys.slice(0, 2).map((key) => resourceStatus[key].error).join(' · ')}</p>{hasVisibleData && <small>{t("Available information remains visible while you retry.")}</small>}</div><button type="button" className="button quiet small" onClick={() => retry(failedKeys)}><RefreshCw size={14} /> {t("Retry")}</button></div>}
    {loadingKeys.length > 0 && hasVisibleData && <div className="data-state refreshing" role="status"><RefreshCw className="spin" size={16} /><span>{t("Refreshing this page. Current information remains available.")}</span></div>}
    {children}
  </>;
}

function AppShell({ user, data, stats, page, setPage, query, setQuery, loading, error, refresh, retryResources, resourceStatus, isOnline, notify, logout, theme, toggleTheme, language, changeLanguage, children }) {
  const [utility, setUtility] = useState(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileMenuRef = useRef(null);
  useEffect(() => {
    function shortcut(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {event.preventDefault();setUtility('search');}
      if (event.key === 'Escape') setProfileOpen(false);
    }
    function outside(event) {if (!profileMenuRef.current?.contains(event.target)) setProfileOpen(false);}
    document.addEventListener('keydown', shortcut);document.addEventListener('pointerdown', outside);
    return () => {document.removeEventListener('keydown', shortcut);document.removeEventListener('pointerdown', outside);};
  }, []);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try {return localStorage.getItem(SIDEBAR_KEY) === 'collapsed';} catch {return false;}
  });
  const [searchOpen, setSearchOpen] = useState(false);
  const [activeSearchIndex, setActiveSearchIndex] = useState(0);
  const searchRef = useRef(null);
  const navigation = navigationFor(user).filter((item) => !['support', 'screen_time'].includes(item));
  const meta = PAGE_META[page];
  // eslint-disable-next-line react-hooks/exhaustive-deps -- language changes the translated labels
  const searchIndexData = useMemo(() => buildGlobalSearchIndex(user, data), [user, data, language]);
  // Staff lists are paged, so records beyond what is loaded come from the server.
  const remoteSearch = useRemoteSearch(query, usesPagedLists(user));
  const searchResults = useMemo(() => mergeSearchResults(
    globalSearchResults(searchIndexData, query),
    remoteSearchEntries(remoteSearch.results, remoteSearchDestinations(user)).map((entry) => ({ ...entry, subtitle: entry.subtitle || t(PAGE_META[entry.destination].label) })),
  ), [searchIndexData, query, remoteSearch.results, user]);
  const adminSupport = useSupportCounts(isPlatformAdmin(user), stats);
  const supportBadge = isPlatformAdmin(user) ?
  adminSupport.open + adminSupport.inProgress :
  data.supportTickets.filter((ticket) => ticket.has_unread_response).length;
  // Students get server-side notices; staff keep the unread-chat dot.
  const studentBell = user.role === 'student';
  const bell = useNotificationBell(studentBell);
  const bellCount = studentBell ? bellTotal(bell.summary) : data.messageChannels.filter((item) => item.unread_count > 0).length;
  const bellLabel = bellCount > 0 ? tx`Notifications, ${bellCount > 99 ? '99+' : formatNumberLocale(bellCount)} unread` : t('Notifications');
  function openNotifications() {
    // Opening the bell always shows the newest notices, never a cached page.
    invalidatePagedLists(['notifications']);
    bell.refresh();
    setUtility('notifications');
  }
  function openFromNotification(nextPage, params) {
    setUtility(null);setMobileOpen(false);
    setPage(nextPage, params);
  }
  useEffect(() => {
    setActiveSearchIndex(0);
  }, [query]);
  useEffect(() => {
    const closeSearch = (event) => {
      if (!searchRef.current?.contains(event.target)) setSearchOpen(false);
    };
    document.addEventListener('pointerdown', closeSearch);
    return () => document.removeEventListener('pointerdown', closeSearch);
  }, []);
  function toggleSidebar() {
    setCollapsed((current) => {
      const next = !current;
      try {localStorage.setItem(SIDEBAR_KEY, next ? 'collapsed' : 'expanded');} catch {/* Collapse is a per-browser convenience only. */}
      return next;
    });
  }
  function openSearchResult(result) {
    if (!result) return;
    setUtility(null);setMobileOpen(false);
    setPage(result.destination);
    setQuery(result.kind === 'record' ? result.filterQuery : '');
    setSearchOpen(false);
  }
  function handleSearchKeyDown(event) {
    if (event.key === 'Escape') {
      setSearchOpen(false);
      setQuery('');
      event.currentTarget.blur();
      return;
    }
    if (!searchResults.length) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setSearchOpen(true);
      setActiveSearchIndex((current) => (current + 1) % searchResults.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setSearchOpen(true);
      setActiveSearchIndex((current) => (current - 1 + searchResults.length) % searchResults.length);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      openSearchResult(searchResults[activeSearchIndex]);
    }
  }
  const collapseLabel = collapsed ? t("Expand navigation") : t("Collapse navigation");
  return <div className={`app-shell ${collapsed ? 'nav-collapsed' : ''}`.trim()}>
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
      <div className="sidebar-top">
        <BrandLockup theme={theme} subtitle={false} />
        <button className="icon-button sidebar-collapse desktop-only" onClick={toggleSidebar} title={collapseLabel} aria-label={collapseLabel} aria-expanded={!collapsed}>{collapsed ? <ChevronsRight size={19} /> : <ChevronsLeft size={19} />}</button>
        <button className="icon-button mobile-only" onClick={() => setMobileOpen(false)} aria-label={t("Close navigation")}><X /></button>
      </div>
      <div className="sidebar-utilities"><button onClick={openNotifications} title={bellLabel} aria-label={bellLabel}><Bell size={20} /><span>{t('Notifications')}</span>{bellCount > 0 && <i className="sidebar-unread-dot" />}</button></div>
      <nav aria-label={t('Main navigation')}>{navigation.map((item) => {
          const ItemIcon = PAGE_META[item].icon;
          const itemLabel = t(PAGE_META[item].label);
          // A locked page stays visible but cannot be opened or focused.
          if (isPageLocked(item, user)) return <button key={item} type="button" className="nav-locked" disabled aria-disabled="true" title={t('Coming soon')} aria-label={`${itemLabel} — ${t('Coming soon')}`}><ItemIcon size={18} aria-hidden="true" /><span>{itemLabel}</span><Lock size={13} className="nav-lock-icon" aria-hidden="true" /></button>;
          return <button key={item} className={page === item ? "active" : ''} title={collapsed ? itemLabel : undefined} onClick={() => {setPage(item);setQuery('');setSearchOpen(false);setMobileOpen(false);}} aria-label={itemLabel}><ItemIcon size={18} /><span>{itemLabel}</span>{item === 'support' && supportBadge > 0 && <span className="nav-badge">{supportBadge > 99 ? '99+' : supportBadge}</span>}</button>;
        })}</nav>

      <div className="sidebar-account" ref={profileMenuRef}><button className="sidebar-account-trigger" aria-expanded={profileOpen} aria-label={t('Account menu')} title={t('Account menu')} onClick={() => setProfileOpen(!profileOpen)}>{user.role === 'student' ? <StudentAvatar student={ownStudent(data)} /> : <span className="avatar">{initials(fullName(user))}</span>}<span className="sidebar-account-copy"><b>{user.first_name || fullName(user)}</b><small>{label(user.role)}</small></span><ChevronRight size={17} className={profileOpen ? 'rotated' : ''} /></button>{profileOpen && <div className="sidebar-account-menu">{user.role === 'student' && <button onClick={() => {setPage('student_center');setProfileOpen(false);setMobileOpen(false);}}><UserRound size={17} />{t('My profile')}</button>}{navigationFor(user).includes('support') && <button onClick={() => {setPage('support');setQuery('');setProfileOpen(false);setMobileOpen(false);}}><LifeBuoy size={17} />{t('Support')}{supportBadge > 0 && <b>{supportBadge}</b>}</button>}<button onClick={logout}><LogOut size={17} />{t('Logout')}</button></div>}</div>
    </aside>
    <main className={`workspace ${page === 'messages' ? 'workspace-messages' : ''} ${page === 'dashboard' && user.role === 'student' ? 'workspace-dashboard' : ''}`}>
      <header className="top-header">
        <button className="icon-button mobile-only" onClick={() => setMobileOpen(true)} aria-label={t("Open navigation")}><Menu /></button>
        <div className="page-heading"><h1>{t(meta.label)}</h1><p>{t(meta.description)}</p></div>
        <div className="header-actions">
          {page !== 'essay_lab' && <div className="global-search" ref={searchRef}>
            <div className={`search ${searchOpen && query.trim() ? 'is-open' : ''}`}><Search size={17} /><input role="combobox" aria-autocomplete="list" aria-controls="global-search-results" aria-expanded={searchOpen && Boolean(query.trim())} aria-activedescendant={searchResults[activeSearchIndex]?.id} aria-label={t("Search pages and records")} placeholder={t("Search pages and records…")} value={query} onFocus={() => setSearchOpen(true)} onChange={(event) => {setQuery(event.target.value);setSearchOpen(true);}} onKeyDown={handleSearchKeyDown} />{query && <button type="button" className="search-clear" onClick={() => {setQuery('');setSearchOpen(false);}} aria-label={t("Clear search")}><X size={14} /></button>}</div>
            {searchOpen && query.trim() && <div className="search-results" id="global-search-results" role="listbox" aria-label={t("Search results")}>
              {searchResults.map((result, index) => {
                const ResultIcon = PAGE_META[result.destination].icon;
                return <button type="button" id={result.id} role="option" aria-selected={index === activeSearchIndex} className={index === activeSearchIndex ? 'active' : ''} key={result.id} onMouseEnter={() => setActiveSearchIndex(index)} onMouseDown={(event) => event.preventDefault()} onClick={() => openSearchResult(result)}><span className="search-result-icon"><ResultIcon size={16} /></span><span><b>{result.title}</b><small>{result.kind === 'page' ? t("Page") : result.subtitle}</small></span><ChevronRight size={15} /></button>;
              })}
              {!searchResults.length && (remoteSearch.loading ? <div className="search-empty" role="status"><Search size={18} /><span>{t("Searching…")}</span></div> : <div className="search-empty"><Search size={18} /><span>{tx`No results for “${query.trim()}”`}</span></div>)}
              {searchResults.length > 0 && <footer><span>{tp('{n} result|{n} results', searchResults.length, { n: searchResults.length })}</span><small>{t("Use ↑↓ and Enter")}</small></footer>}
            </div>}
          </div>}
          <LanguageSelector language={language} onChange={changeLanguage} compact />
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
          {PDF_EXPORT_PAGES.has(page) && <button className="icon-button" onClick={() => exportNodePdf(document.querySelector('.page-content'))} title={t("Export PDF")} aria-label={t("Export PDF")}><Download size={19} /></button>}
        </div>
      </header>
      {user.workspace?.read_only && <div className="data-state workspace-read-only" role="status"><ShieldAlert size={18} /><div><b>{t('This workspace is read-only')}</b><p>{t('You can view everything, but changes are paused until an administrator renews the workspace subscription.')}</p></div></div>}
      {!isOnline && <div className="data-state offline" role="status"><WifiOff size={18} /><div><b>{t('You are offline')}</b><p>{t('Current information remains available. Reconnect before saving changes.')}</p></div></div>}
      {error && <div className="alert error workspace-alert">{error}</div>}
      <div className="page-content">{['dashboard', 'admin_dashboard'].includes(page) && user.role !== 'student' && canOpenPage('screen_time', user) && <ScreenTimeShortcut userId={user.id} setPage={setPage} />}<PageDataBoundary {...{ page, data, stats, loading, resourceStatus }} retry={retryResources}>{children}</PageDataBoundary></div>
    </main>
    {utility && <Modal title={t(utility === 'search' ? 'Search' : 'Notifications')} onClose={() => {setUtility(null);setQuery('');}}>{utility === 'search' ? <div className="sidebar-utility-panel"><label className="search"><Search size={18} /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t('Search pages and records…')} aria-label={t('Search pages and records')} onKeyDown={handleSearchKeyDown} /></label><div className="sidebar-search-results">{(query.trim() ? searchResults : navigation.map((destination) => ({id:destination,destination,title:t(PAGE_META[destination].label),kind:'page'}))).map((result) => <button key={result.id} onClick={() => openSearchResult(result)}><span>{result.title}</span><ChevronRight size={16} /></button>)}{query.trim() && !searchResults.length && <Empty text={t('No information available yet.')} />}</div></div> : <NotificationPanel user={user} data={data} summary={bell.summary} onOpen={openFromNotification} notify={notify} />}</Modal>}
    <ScreenTimeTracker page={page} userId={user.id} />
    {['counselor', 'student'].includes(user.role) && <AssistantCenter user={user} onOpenScreenTime={() => setPage('screen_time')} />}
  </div>;
}

function PageRouter({ page, params, user, data, stats, query, reload, notify, setPage, search, navigate }) {
  const [directChannel, setDirectChannel] = useState(null);
  const openingDirect = useRef(false);
  useEffect(() => {if (page !== 'messages') setDirectChannel(null);}, [page]);
  async function onDirect(userId) {
    if (openingDirect.current) return;
    openingDirect.current = true;
    try {
      const channel = await api.openDirectChannel(userId);
      setDirectChannel(channel);
      setPage('messages');
    } catch (err) {notify(err.message, 'error');}
    finally {openingDirect.current = false;}
  }
  if (user.role === 'parent') return <ParentPortalPage {...{ page, user, data, reload, notify }} />;
  if (isPlatformAdmin(user) && page === 'admin_dashboard') return <AdminControlDashboard data={data} stats={stats} setPage={setPage} />;
  if (isPlatformAdmin(user) && page === 'admin_schools') return <SchoolsPage user={user} data={data} query={query} reload={reload} notify={notify} />;
  if (isPlatformAdmin(user) && page === 'admin_counselors') return <AdminCounselorsPage user={user} data={data} query={query} reload={reload} notify={notify} />;
  if (isPlatformAdmin(user) && page === 'admin_students') return <StudentsPage user={user} data={data} query={query} reload={reload} notify={notify} studentId={params.studentId} onStudent={(studentId) => setPage(page, { studentId })} />;
  if (isCounselor(user) && page === 'counselor_roadmap') return <CounselorRoadmapPage user={user} data={data} reload={reload} notify={notify} />;
  if (isPlatformAdmin(user) && page === 'admin_audit') return <AdminAuditPage data={data} query={query} />;
  if (page === 'dashboard') return <Dashboard {...{ user, data, stats, reload, notify, setPage, onDirect }} />;
  if (user.role === 'student' && page === 'student_center') {
    const editSection = new URLSearchParams(search).get('edit');
    return <StudentCenterPage {...{ user, data, query, reload, notify, setPage }} tab={params.tab} onTab={(tab) => setPage(page, { tab })} editSection={editSection}
      onEditDone={() => { if (editSection) navigate(buildPath({ page, params }), { replace: true }); }} />;
  }
  if (isTaskManager(user) && page === 'roadmap') return <RoadmapPage {...{ user, data, query, reload, notify }} />;
  if (user.role === 'student' && page === 'roadmap') return <RoadmapPage {...{ user, data, query, reload, notify }} tab={params.tab} onTab={(tab) => setPage(page, { tab })} />;
  if (user.role === 'student' && page === 'find_personality') return <ProfileAssessmentPage user={user} notify={notify} data={data} reload={reload} />;
  if (page === 'bookings') return <BookingsPage {...{ user, data, reload, notify }} />;
  if (page === 'messages') return <MessagesPage {...{ user, data, notify }} initialChannel={directChannel} channelId={params.channelId} openInbox={params.tab === 'counselor'} onChannelOpened={() => navigate(buildPath({ page: 'messages' }), { replace: true })} />;
  if (page === 'support') return <SupportPage {...{ user, data, query, reload, notify }} />;
  if (page === 'screen_time') return <ScreenTimePage user={user} pageLabel={(key) => PAGE_META[key] ? t(PAGE_META[key].label) : ''} />;
  if (user.role === 'student' && page === 'programs') return <ProgramsPage {...{ data, query, search, navigate }} />;
  if (user.role === 'student' && page === 'essay_lab') return <EssayLab user={user} notify={notify} essayId={params.essayId} onEssay={(essayId) => setPage(page, { essayId })} />;
  if (user.role === 'student' && page === 'applications') return <ApplicationsPortalPage {...{ user, data, query, reload, notify, setPage }} />;
  if (user.role === 'student' && page === 'college_search') return <CollegeSearchPage {...{ data, query, reload, notify }} />;
  if (user.role === 'student' && page === 'store') return <StorePage {...{ data, query, setPage }} />;
  if (page === 'schools') return <SchoolsPage user={user} data={data} query={query} reload={reload} notify={notify} />;
  if (page === 'students') return <StudentsPage user={user} data={data} query={query} reload={reload} notify={notify} studentId={params.studentId} onStudent={(studentId) => setPage(page, { studentId })} />;
  if (page === 'academics') return <div className="section-stack">{user.role === 'student' && <ProfileCard student={ownStudent(data)} />}<ResourceSection title={t("Research")} resource="researches" {...{ user, data, query, reload, notify }} /></div>;
  if (page === 'portfolio') return <div className="split-grid"><ResourceSection title={t("Projects")} resource="projects" {...{ user, data, query, reload, notify }} /><ResourceSection title={t("Internships")} resource="internships" {...{ user, data, query, reload, notify }} /></div>;
  if (page === 'activities') return <div className="section-stack"><div className="split-grid"><ResourceSection title={t("Activities")} resource="activities" {...{ user, data, query, reload, notify }} /><ResourceSection title={t("Honors")} resource="honors" {...{ user, data, query, reload, notify }} /></div><ResourceSection title={t("Achievements")} resource="achievements" {...{ user, data, query, reload, notify }} /></div>;
  if (page === 'recommendations') return <ResourceSection title={t("Recommendation letters")} resource="recommendations" {...{ user, data, query, reload, notify }} />;
  if (page === 'documents') return <DocumentsPage {...{ user, data, query, reload, notify }} />;
  if (page === 'certificates') return <DocumentsPage typeFilter="certificate" title={t("Certificates")} {...{ user, data, query, reload, notify }} />;
  const titleMap = { tasks: 'Tasks', applications: 'University applications', essays: 'Essays' };
  return <ResourceSection title={titleMap[page] || label(page)} resource={page} {...{ user, data, query, reload, notify }} />;
}

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const [language, setLanguageState] = useState(getLanguage);
  const [location, setLocation] = useState(readLocation);
  const [user, setUser] = useState(null);
  const [query, setQuery] = useState('');
  const isOnline = useOnlineStatus();
  const [toast, notify] = useToast();
  const [bootstrapping, setBootstrapping] = useState(() => api.hasSession());
  const [bootstrapError, setBootstrapError] = useState('');
  const bootstrapAttempted = useRef(false);
  const [signOutPrompt, setSignOutPrompt] = useState(false);
  const signingOut = useRef(false);
  const handleUnauthorized = useCallback(() => {api.logout();setUser(null);}, []);
  const { data, stats, loading, error, resourceStatus, loadData, reset: resetWorkspace } = useWorkspaceData(user, handleUnauthorized);

  const changeLanguage = useCallback((nextLanguage) => setLanguageState(setLanguage(nextLanguage)), []);

  // The URL is the source of truth for where the user is: a refresh, a
  // reopened tab, a bookmark or back/forward lands on the same page.
  const navigate = useCallback((to, { replace = false } = {}) => {
    if (to !== `${window.location.pathname}${window.location.search}${window.location.hash}`) window.history[replace ? 'replaceState' : 'pushState'](null, '', to);
    setLocation(readLocation());
  }, []);

  useEffect(() => {
    const handleNavigation = () => setLocation(readLocation());
    window.addEventListener('popstate', handleNavigation);
    return () => window.removeEventListener('popstate', handleNavigation);
  }, []);

  const showPublicPage = useCallback((nextPage, replace = false) => {
    navigate(nextPage === 'login' ? LOGIN_PATH : LANDING_PATH, { replace });
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, [navigate]);

  const publicPage = publicPageFor(location.pathname, location.hash);
  const requestedRoute = useMemo(() => parsePath(location.pathname), [location.pathname]);
  const route = useMemo(() => resolveRoute(requestedRoute, user), [requestedRoute, user]);
  const page = route.page;
  // Opening a page the role cannot see does nothing: pushing its path would
  // only be replaced by the home page, leaving a Back entry that bounces.
  const setPage = useCallback((nextPage, params = {}) => {
    const target = openablePage(nextPage, user);
    if (target) navigate(buildPath({ page: target, params }));
  }, [navigate, user]);
  const inWorkspace = Boolean(user) && !user.must_change_password && !(user.role === 'student' && !isPlatformAdmin(user) && !user.student_profile_complete);

  const loadUser = useCallback(async () => {
    const current = await api.me();
    setUser(current);
    return current;
  }, []);

  const bootstrapSession = useCallback(async () => {
    if (!api.hasSession()) {setBootstrapping(false);return;}
    setBootstrapping(true);
    setBootstrapError('');
    try {
      const current = await loadUser();
      setBootstrapping(false);
      if (!current.must_change_password) await loadData(current);
    } catch (err) {
      if (err.status === 401) {
        api.logout();
        setUser(null);
      } else {
        setBootstrapError(err.message || t("Unable to connect to the server. Check your connection and retry."));
      }
      setBootstrapping(false);
    }
  }, [loadUser, loadData]);

  useEffect(() => {
    if (bootstrapAttempted.current) return;
    bootstrapAttempted.current = true;
    dropLegacySharedKeys(() => window.localStorage);
    bootstrapSession();
  }, []);

  // Signed out on a workspace link: sign in first, then come back to it.
  useEffect(() => {
    if (user || bootstrapping || bootstrapError || publicPage) return;
    navigate(loginPath(`${location.pathname}${location.search}`), { replace: true });
  }, [user, bootstrapping, bootstrapError, publicPage, location, navigate]);

  // Signed in: show the requested page, or the role's home page for sign-in,
  // unknown and forbidden paths. Waits until onboarding is done so a deep
  // link survives it.
  useEffect(() => {
    if (!inWorkspace) return;
    if (publicPage === 'login') {
      const next = safeNextPath(new URLSearchParams(location.search).get('next'));
      if (next) {navigate(next, { replace: true });return;}
    }
    const canonical = buildPath(route);
    if (canonical !== location.pathname) navigate(`${canonical}${requestedRoute?.page === route.page ? location.search : ''}`, { replace: true });
  }, [inWorkspace, publicPage, route, requestedRoute, location, navigate]);

  useEffect(() => {
    document.title = inWorkspace && PAGE_META[page] ? `${t(PAGE_META[page].label)} · Naseeb Edu` : siteTitle();
  }, [inWorkspace, page, language]);

  async function afterLogin() {
    const current = await loadUser();
    if (!current.must_change_password) await loadData(current);
  }
  async function afterPasswordChanged(current) {
    setUser(current);
    await loadData(current);
  }
  async function logout() {
    // Upload this user's queued screen time and open essays while the session
    // is still valid (up to a few seconds), then remove everything stored for
    // them on this device. A second click while this runs does nothing.
    if (signingOut.current) return;
    signingOut.current = true;
    notify(t('Saving your work before signing out…'));
    try {
      const screenTime = flushActiveScreenTime ? Promise.race([flushActiveScreenTime().catch(() => {}), new Promise((resolve) => window.setTimeout(resolve, 3000))]) : null;
      const [, essaysSynced] = await Promise.all([screenTime, api.syncBeforeSignOut(user?.id)]);
      if (!essaysSynced) {setSignOutPrompt(true);return;}
      finishSignOut();
    } finally {
      signingOut.current = false;
    }
  }
  // keepDrafts ("Sign in again"): end the session but keep this user's unsynced
  // Essay Lab drafts on the device, and go straight to the sign-in form.
  function finishSignOut({ keepDrafts = false } = {}) {
    const signedOut = user?.id;
    setSignOutPrompt(false);
    resetWorkspace();
    api.signOut(signedOut, { keepDrafts });clearUserStorage(() => window.localStorage, signedOut);clearUserSessionStorage(() => window.sessionStorage, signedOut);setUser(null);setBootstrapError('');showPublicPage(keepDrafts ? 'login' : 'landing', true);}
  const retryResources = useCallback((keys) => loadData(user, keys), [loadData, user]);

  if (bootstrapping) return <AppBootLoader message="Checking your secure session…" />;
  if (bootstrapError && !user) return <BootstrapError message={bootstrapError} onRetry={bootstrapSession} onSignOut={logout} />;
  if (!user) return publicPage !== 'landing' ?
  <Login onLogin={afterLogin} onBack={() => showPublicPage('landing')} theme={theme} toggleTheme={toggleTheme} language={language} changeLanguage={changeLanguage} /> :
  <LazyBoundary fallback={<AppBootLoader />}><LandingPage onLogin={() => showPublicPage('login')} theme={theme} toggleTheme={toggleTheme} language={language} changeLanguage={changeLanguage} /></LazyBoundary>;
  if (user.must_change_password) return <ForcedPasswordChange user={user} onChanged={afterPasswordChanged} onSignOut={logout} theme={theme} toggleTheme={toggleTheme} language={language} changeLanguage={changeLanguage} />;
  if (user.role === 'student' && !isPlatformAdmin(user) && !user.student_profile_complete) return <LazyBoundary fallback={<AppBootLoader />}><StudentOnboarding userId={user.id} onSaved={afterPasswordChanged} onSignOut={logout} /></LazyBoundary>;
  return <>
    <AppShell {...{ user, data, stats, page, setPage, query, setQuery, loading, error, resourceStatus, retryResources, isOnline, refresh: () => loadData(user), notify, logout, theme, toggleTheme, language, changeLanguage }}>
      <LazyBoundary resetKey={page} fallback={<PageSkeleton />}><PageRouter {...{ page, params: route.params, user, data, stats, query, reload: () => loadData(user, RELOAD_CHANGED), notify, setPage, search: location.search, navigate }} /></LazyBoundary>
    </AppShell>
    {signOutPrompt && <Modal title="Sign out?" backdropClassName="is-above-editor" onClose={() => setSignOutPrompt(false)}>
      <div className="sign-out-prompt" role="alert">
        <p>{t("You have writing that isn't saved to your account yet. Sign in again to save it, or sign out and delete it from this device.")}</p>
        <div className="form-actions"><button type="button" className="button danger" onClick={() => finishSignOut()}>{t('Sign out anyway')}</button><button type="button" className="button primary" onClick={() => finishSignOut({ keepDrafts: true })}>{t('Sign in again')}</button></div>
      </div>
    </Modal>}
    {toast && <div className={`toast ${toast.type}`}>{toast.type === 'success' ? <ShieldCheck size={18} /> : <X size={18} />}{toast.message}</div>}
  </>;
}

