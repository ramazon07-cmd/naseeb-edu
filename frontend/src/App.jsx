import { Children, Fragment, createContext, isValidElement, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useContext } from 'react';
import { createPortal } from 'react-dom';
import {
  Activity, ArrowLeft, Award, BookOpen, Bot, Building2, CheckCircle2,
  CalendarClock, CalendarDays, Check, ChevronRight, ClipboardCheck, Clock3, Compass,
  ContactRound, DollarSign, Download, ExternalLink, Eye, FileText, Filter, Fingerprint, Flag, FolderKanban, Globe2, GraduationCap, Heart, LayoutDashboard,
  Inbox, LibraryBig, LifeBuoy, ListChecks, LogOut, MapPin, Menu, MessageCircle, MessageSquareText, Moon, MoreHorizontal,
  PackageOpen, Pencil, PenLine, Plus, RefreshCw, School, Search, Send, ShieldAlert, ShieldCheck,
  ShoppingCart, Sparkles, Square, Sun, Target, Trash2, UserRound, Users, UsersRound, WifiOff, X } from
'lucide-react';
import { api } from './api';
import {
  LANGUAGE_OPTIONS,
  formatCurrencyLocale,
  formatDateLocale,
  formatNumberLocale,
  formatPercentLocale,
  getLanguage,
  locale,
  setLanguage,
  t,
  tx } from
'./i18n';

const LABELS = {
  admin: 'Admin', counselor: 'School Counselor', teacher: 'Teacher', organization: 'Organization School', student: 'Student',
  parent: 'Parent', mother: 'Mother', father: 'Father', guardian: 'Guardian',
  todo: 'To do', in_progress: 'In progress', submitted: 'Submitted', approved: 'Approved', late: 'Late',
  low: 'Low', medium: 'Medium', high: 'High', urgent: 'Urgent', researching: 'Researching',
  shortlisted: 'Shortlisted', applying: 'Applying', accepted: 'Accepted', rejected: 'Rejected',
  waitlisted: 'Waitlisted', dream: 'Dream', target: 'Target', safety: 'Safety', required: 'Required',
  uploaded: 'Uploaded', reviewing: 'Reviewing', draft: 'Draft', needs_revision: 'Needs revision',
  requested: 'Requested', drafting: 'Drafting', extracurricular: 'Extracurricular', volunteering: 'Volunteering',
  leadership: 'Leadership', club: 'Club', competition: 'Competition', community: 'Community service',
  school: 'School', regional: 'Regional', national: 'National', international: 'International',
  project: 'Project', research: 'Research', olympiad: 'Olympiad', startup: 'Startup', sport: 'Sport', art: 'Art',
  planned: 'Planned', completed: 'Completed', active: 'Active', pending: 'Pending', confirmed: 'Confirmed',
  cancelled: 'Cancelled', direct: 'Direct', group: 'Group', discussion: 'Discussion', question: 'Q&A', update: 'Update',
  public: 'Public', private: 'Private', urban: 'Urban', suburban: 'Suburban', rural: 'Rural',
  four_year: '4-year', two_year: '2-year', merit: 'Merit', need_based: 'Need-based', athletic: 'Athletic',
  full_ride: 'Full ride', full: 'Full funding', partial: 'Partial funding', fixed: 'Fixed amount',
  onsite: 'On-site', online: 'Online', hybrid: 'Hybrid', reach: 'Reach', strong_option: 'Strong option',
  academic: 'Academic', preferences: 'Preferences', financial: 'Financial', profile_strength: 'Profile strength',
  harassment: 'Harassment or bullying', unsafe: 'Unsafe content', privacy: 'Privacy concern', misinformation: 'Misinformation',
  open: 'Open', closed: 'Closed', technical: 'Technical', account: 'Account', application: 'Application', billing: 'Billing', other: 'Other',
  resolved: 'Resolved', dismissed: 'Dismissed', none: 'No action', content_removed: 'Content removed',
  muted_24h: 'Muted 24 hours', muted_7d: 'Muted 7 days'
};

const label = (value) => t(LABELS[value] || value || '—');
const fullName = (user) => user?.full_name || [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.username || 'User';
const initials = (name) => String(name || 'U').split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase();
const dateText = (value) => formatDateLocale(value);
const dateTimeText = (value) => formatDateLocale(value, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
const isCounselor = (user) => ['admin', 'counselor'].includes(user?.role);
const isTaskManager = (user) => ['admin', 'counselor', 'teacher'].includes(user?.role);
const SHOW_DEMO_ACCOUNTS = import.meta.env.DEV && import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === 'true';
const PERSONALITY_QUIZ_URL = (import.meta.env.VITE_PERSONALITY_QUIZ_URL || '').trim();
// Set VITE_SCHOOL_CONTACT_URL to a real enquiry destination (form, mailto: or
// messenger link). Until it is set the school-enquiry CTA is not rendered —
// a landing page must not ship a primary action that goes nowhere.
const SCHOOL_CONTACT_URL = (import.meta.env.VITE_SCHOOL_CONTACT_URL || '').trim();
const ownStudent = (data) => data.students?.[0];
const studentName = (data, id) => fullName(data.students?.find((student) => student.id === Number(id))?.user_detail);
const THEME_KEY = 'naseeb-edu-theme';
const TARGET_COUNTRIES_MAX_LENGTH = 255;
const PERSONALITY_RATING_OPTIONS = [1, 2, 3, 4, 5];
const SCREEN_TIME_QUEUE_KEY = 'naseeb-screen-time-pending-v1';
const formatDuration = (seconds = 0) => {
  const totalMinutes = Math.round(Number(seconds) / 60);
  if (totalMinutes < 1) return `< ${formatNumberLocale(1)} ${t("min")}`;
  if (totalMinutes < 60) return `${formatNumberLocale(totalMinutes)} ${t("min")}`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${formatNumberLocale(hours)} ${t("h")}${minutes ? ` ${formatNumberLocale(minutes)} ${t("min")}` : ''}`;
};
const localDateKey = () => {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
};
const BRAND_LOGOS = {
  light: '/brand/naseeb-light-256.jpg',
  dark: '/brand/naseeb-dark-256.png'
};

const PageTitleContext = createContext('');

function pageFromLocation() {
  const raw = window.location.hash.replace(/^#\/?/, '').split(/[/?]/)[0];
  return raw && PAGE_META[raw] ? raw : 'dashboard';
}

function pageHash(page) {
  return `#/${page}`;
}

function writePageLocation(page, navigationContext = null, replace = false) {
  const url = new URL(window.location.href);
  url.hash = `/${page}`;
  const state = { ...(window.history.state || {}), page, navigationContext };
  window.history[replace ? 'replaceState' : 'pushState'](state, '', url);
}

function publicPageFromLocation() {
  return window.location.hash.replace(/^#\/?/, '').split(/[/?]/)[0] === 'login' ? 'login' : 'landing';
}

function writePublicLocation(publicPage, replace = false) {
  const url = new URL(window.location.href);
  url.hash = publicPage === 'login' ? '/login' : '';
  window.history[replace ? 'replaceState' : 'pushState']({ publicPage }, '', url);
}

function brandLogoFor(theme) {
  return BRAND_LOGOS[theme] || BRAND_LOGOS.light;
}

function normalizeCountries(value) {
  const seen = new Set();
  return String(value || '').
  split(',').
  map((country) => country.trim()).
  filter((country) => {
    const key = country.toLocaleLowerCase('en');
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).
  join(', ');
}

function initialTheme() {
  try {
    const saved = window.localStorage.getItem(THEME_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {






    // Storage can be unavailable in strict privacy modes; the OS preference still works.
  }return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';}function BrandLogo({ className = '' }) {return <span className={`brand-logo ${className}`} role="img" aria-label={t("Naseeb Edu")} />;}

function BrandLockup({ theme }) {
  return <div className="brand-lockup"><BrandLogo theme={theme} /><div><b>{t("Naseeb Edu")}</b><small>{t('Education Counseling Platform')}</small></div></div>;
}

function LanguageSelector({ language, onChange, compact = false }) {
  return <label className={`language-selector ${compact ? 'compact' : ''}`} aria-label={t('Language')}><Globe2 size={15} /><select value={language} onChange={(event) => onChange(event.target.value)}>{LANGUAGE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{compact ? option.short : option.label}</option>)}</select></label>;
}

function AppBootLoader({ message = 'Preparing your workspace…' }) {
  return <main className="app-boot" role="status" aria-label={message}><div className="app-boot-card"><div className="app-boot-mark" aria-hidden="true">{t("N")}</div><div className="app-boot-copy"><b>{t("Naseeb Edu")}</b><span>{message}</span></div><div className="app-boot-line" aria-hidden="true" /></div></main>;
}

function BootstrapError({ message, onRetry, onSignOut }) {
  return <main className="app-boot"><section className="bootstrap-error" role="alert"><WifiOff size={30} /><span className="eyebrow">{t("CONNECTION INTERRUPTED")}</span><h1>{t("We could not open your workspace.")}</h1><p>{message}</p><div><button type="button" className="button primary" onClick={onRetry}><RefreshCw size={16} /> {t("Retry")}</button><button type="button" className="button quiet" onClick={onSignOut}>{t("Return to sign in")}</button></div></section></main>;
}

function ThemeToggle({ theme, onToggle }) {
  const isDark = theme === 'dark';
  return <button type="button" className="icon-button theme-toggle" onClick={onToggle} title={isDark ? t("Light mode") : t("Dark mode")} aria-label={isDark ? t("Switch to light mode") : t("Switch to dark mode")} aria-pressed={isDark}>{isDark ? <Sun size={18} /> : <Moon size={18} />}</button>;
}

const PAGE_META = {
  dashboard: { label: 'Dashboard', icon: LayoutDashboard, description: 'A complete view of the application journey' },
  schools: { label: 'Schools', icon: Building2, description: 'Schools and organization accounts' },
  students: { label: 'Students', icon: Users, description: 'Student profiles and progress' },
  profile: { label: 'My profile', icon: UserRound, description: 'Your personal application profile' },
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
  roadmap: { label: 'Roadmap', icon: Compass, description: 'Level-linked missions, milestones, and reflections' },
  community: { label: 'Community', icon: Users, description: 'Student discussions, questions, and shared experience' },
  bookings: { label: 'Meetings', icon: CalendarClock, description: 'Schedule and manage meetings' },
  messages: { label: 'Messages', icon: MessageCircle, description: 'Direct, Group, Community, and Discussion messages' },
  program_usage: { label: 'Program Usage', icon: ListChecks, description: 'Services, mentors, and usage balance' },
  programs: { label: 'Programs', icon: Globe2, description: 'National and international opportunity catalog' },
  resource_index: { label: 'Resource Index', icon: LibraryBig, description: 'All tools and resources for students' },
  essay_lab: { label: 'Essay Lab', icon: PenLine, description: 'Essay drafts, feedback, and revision history' },
  college_search: { label: 'College Search', icon: School, description: 'Find, compare, and shortlist universities' },
  store: { label: 'Naseeb Store', icon: ShoppingCart, description: 'Additional education and application services' },
  contacts: { label: 'Contacts', icon: ContactRound, description: 'Contact your counselor and school coordinator' },
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

function navigationFor(user) {
  if (user?.role === 'parent') return ['dashboard', 'parent_progress', 'parent_tasks', 'parent_applications', 'parent_documents', 'parent_meetings'];
  if (user?.role === 'admin') return ['admin_dashboard', 'admin_schools', 'admin_counselors', 'admin_students', 'counselor_roadmap', 'admin_audit', 'support'];
  if (isCounselor(user)) return ['dashboard', 'schools', 'students', 'counselor_roadmap', 'academics', 'portfolio', 'activities', 'recommendations', 'tasks', 'roadmap', 'program_usage', 'applications', 'documents', 'certificates', 'essays', 'bookings', 'messages', 'screen_time', 'support'];
  if (user?.role === 'teacher') return ['dashboard', 'students', 'tasks', 'roadmap', 'bookings', 'messages', 'screen_time'];
  if (user?.role === 'organization') return ['dashboard', 'students', 'bookings', 'messages', 'screen_time', 'support'];
  return ['dashboard', 'student_center', 'roadmap', 'community', 'bookings', 'messages', 'program_usage', 'programs', 'resource_index', 'essay_lab', 'applications', 'college_search', 'store', 'contacts', 'screen_time', 'support'];
}

const EMPTY_DATA = {
  schools: [], students: [], universities: [], tasks: [], applications: [], documents: [], essays: [],
  achievements: [], researches: [], projects: [], internships: [], activities: [], honors: [],
  recommendations: [], roadmapMissions: [], communityPosts: [],
  bookings: [], studentMessages: [], messageChannels: [], programServices: [], scholarships: [], opportunityPrograms: [], resourceLibrary: [], storeItems: [], team: [], supportTickets: [],
  accounts: [], counselorRoadmapTemplates: [], counselorRoadmaps: [], adminAuditEvents: [],
  parentPortal: { children: [], pending_invitations: [], privacy: { hidden: [], read_only: true } }
};

const GLOBAL_SEARCH_RESOURCES = {
  schools: 'schools', students: 'students', tasks: 'tasks', applications: 'applications', documents: 'documents',
  essays: 'essays', achievements: 'activities', researches: 'academics', projects: 'portfolio', internships: 'portfolio',
  activities: 'activities', honors: 'activities', recommendations: 'recommendations', roadmapMissions: 'roadmap',
  communityPosts: 'community', bookings: 'bookings', messageChannels: 'messages', programServices: 'program_usage',
  universities: 'college_search', scholarships: 'college_search', opportunityPrograms: 'programs',
  resourceLibrary: 'resource_index', storeItems: 'store', team: 'contacts', supportTickets: 'support',
  accounts: 'admin_counselors', counselorRoadmaps: 'counselor_roadmap', adminAuditEvents: 'admin_audit'
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

function globalSearchResults(user, data, query) {
  const term = query.trim().toLocaleLowerCase(locale());
  if (!term) return [];
  const navigation = navigationFor(user);
  const allowedPages = new Set(navigation);
  const pageResults = navigation.flatMap((destination) => {
    const meta = PAGE_META[destination];
    const haystack = `${t(meta.label)} ${t(meta.description)} ${meta.label} ${meta.description}`.toLocaleLowerCase(locale());
    return haystack.includes(term) ? [{ id: `page-${destination}`, kind: 'page', destination, title: t(meta.label), subtitle: t(meta.description) }] : [];
  });
  const recordResults = Object.entries(GLOBAL_SEARCH_RESOURCES).flatMap(([resource, destination]) => {
    if (!allowedPages.has(destination)) return [];
    const records = Array.isArray(data[resource]) ? data[resource] : [];
    return records.flatMap((item, index) => {
      const title = globalSearchTitle(resource, item);
      if (!title) return [];
      const haystack = `${title} ${JSON.stringify(item)}`.toLocaleLowerCase(locale());
      if (!haystack.includes(term)) return [];
      return [{
        id: `${resource}-${item.id ?? index}`,
        kind: 'record',
        destination,
        title: String(title),
        subtitle: t(PAGE_META[destination].label),
        filterQuery: String(title)
      }];
    });
  });
  return [...pageResults, ...recordResults].slice(0, 10);
}

const RESOURCE_FIELDS = {
  researches: [
  ['title', 'Research title', 'text', true], ['field', 'Field'], ['role', 'Role'],
  ['summary', 'Summary', 'textarea', true], ['outcome', 'Outcome'], ['start_date', 'Start date', 'date'],
  ['end_date', 'End date', 'date'], ['link', 'Link', 'url'], ['google_docs_url', 'Google Docs URL', 'url']],

  projects: [
  ['title', 'Project title', 'text', true], ['role', 'Role'], ['technologies', 'Technologies'],
  ['description', 'Description', 'textarea', true], ['impact', 'Measurable impact'], ['date', 'Date', 'date'], ['link', 'Link', 'url'],
  ['google_docs_url', 'Google Docs URL', 'url']],

  internships: [
  ['organization', 'Organization', 'text', true], ['position', 'Position', 'text', true], ['supervisor', 'Supervisor'],
  ['description', 'Responsibilities and results', 'textarea'], ['start_date', 'Start date', 'date'], ['end_date', 'End date', 'date'],
  ['is_current', 'Current internship', 'checkbox'], ['google_docs_url', 'Google Docs URL', 'url']],

  activities: [
  ['name', 'Activity name', 'text', true], ['activity_type', 'Type', 'select', true, ['extracurricular', 'volunteering', 'leadership', 'club', 'competition', 'community', 'other']],
  ['role', 'Role'], ['description', 'Description', 'textarea'], ['impact', 'Impact'],
  ['hours_per_week', 'Hours per week', 'number'], ['weeks_per_year', 'Weeks per year', 'number'],
  ['start_date', 'Start date', 'date'], ['end_date', 'End date', 'date'],
  ['google_docs_url', 'Google Docs URL', 'url']],

  honors: [
  ['title', 'Honor title', 'text', true], ['issuer', 'Issuer'], ['level', 'Level', 'select', true, ['school', 'regional', 'national', 'international']],
  ['award_date', 'Award date', 'date'], ['description', 'Description', 'textarea'], ['proof_file', 'Proof file', 'file'],
  ['google_docs_url', 'Google Docs URL', 'url']],

  achievements: [
  ['title', 'Achievement title', 'text', true], ['category', 'Category', 'select', true, ['project', 'startup', 'olympiad', 'volunteering', 'leadership', 'research', 'sport', 'art', 'other']],
  ['date', 'Date', 'date'], ['impact', 'Impact'], ['description', 'Description', 'textarea', true],
  ['proof_file', 'Proof file', 'file']],

  recommendations: [
  ['recommender_name', 'Recommender name', 'text', true], ['recommender_title', 'Position'], ['recommender_email', 'Email', 'email'],
  ['relationship', 'Relationship'], ['status', 'Status', 'select', true, ['requested', 'drafting', 'submitted', 'approved']],
  ['deadline', 'Deadline', 'date'], ['notes', 'Notes', 'textarea'], ['google_docs_url', 'Google Docs URL', 'url']],

  tasks: [
  ['title', 'Task title', 'text', true], ['description', 'Description', 'textarea'], ['due_date', 'Due date', 'date', true],
  ['priority', 'Priority', 'select', true, ['low', 'medium', 'high', 'urgent']],
  ['status', 'Status', 'select', true, ['todo', 'in_progress', 'submitted', 'late']],
  ['student_response', 'Student response', 'textarea'], ['submission_url', 'Submission or Google Docs URL', 'url'],
  ['submission_file', 'Submission file', 'file']],

  applications: [
  ['university', 'University', 'university', true], ['program', 'Program', 'text', true],
  ['tier', 'Tier', 'select', true, ['dream', 'target', 'safety']],
  ['status', 'Status', 'select', true, ['researching', 'shortlisted', 'applying', 'submitted', 'accepted', 'rejected', 'waitlisted']],
  ['deadline', 'Deadline', 'date'], ['scholarship_deadline', 'Scholarship deadline', 'date'], ['application_portal_url', 'Portal URL', 'url'], ['notes', 'Notes', 'textarea']],

  essays: [
  ['application', 'Application', 'application'], ['title', 'Essay title', 'text', true], ['prompt', 'Prompt', 'textarea', true],
  ['content', 'Draft content', 'textarea'], ['status', 'Status', 'select', true, ['draft', 'reviewing', 'needs_revision', 'approved']],
  ['google_docs_url', 'Google Docs URL', 'url'], ['counselor_comment', 'Counselor comment', 'textarea']]

};

function Landing({ onLogin, theme, toggleTheme, language, changeLanguage }) {
  const pageRef = useRef(null);
  const path = [
  { title: 'Set the direction', description: 'Turn a student’s goals into a focused university and scholarship strategy.' },
  { title: 'Build the profile', description: 'Academics, activities, honors and documents collected in one verified profile.' },
  { title: 'Prepare applications', description: 'Tasks, essays, recommendations and deadlines, each with a clear owner.' },
  { title: 'Make the decision', description: 'Compare offers, funding and fit, then commit to the right final choice.' }];

  const capabilities = [
  { icon: Compass, title: 'Roadmap', description: 'Level-linked missions a teacher or counselor approves, so progress is earned rather than claimed.', note: 'Staff approved' },
  { icon: GraduationCap, title: 'College Search', description: 'Universities ranked against the student’s real GPA, SAT, IELTS, budget and scholarship needs.', note: 'Profile driven' },
  { icon: PenLine, title: 'Essay Lab', description: 'Drafts, revision history and counselor feedback stay with the application they belong to.', note: 'Versioned' },
  { icon: FileText, title: 'Documents', description: 'Transcripts, certificates and evidence stream through authenticated links, never public URLs.', note: 'Private storage' },
  { icon: MessageSquareText, title: 'Messaging', description: 'Direct, group and school channels, with moderation and reporting built in.', note: 'Moderated' },
  { icon: ClipboardCheck, title: 'Student 360', description: 'One reviewable view per student for staff — with private notes and drafts deliberately excluded.', note: 'Audited' }];

  // Verifiable platform facts only. Outcome metrics belong here once real data
  // exists — add a row rather than replacing these; nothing here may be estimated.
  const ledger = [
  { figure: 6, label: 'Roles', description: 'Admin, counselor, teacher, school, student and parent — each with its own data scope.' },
  { figure: 3, label: 'Languages', description: 'Uzbek, Russian and English across the whole product, not just the marketing page.' },
  { figure: 0, label: 'Public sign-ups', description: 'Accounts are issued by a school or counselor. Nobody can register their way into student data.' }];


  // Every line below maps to shipped behaviour: personality_university_fit(),
  // college_ai_advice() and review_essay(). No capability is described that the
  // backend does not already implement.
  const asks = [
  { title: '“Why is this university a fit for me?”', description: 'It scores the match against your assessed interests and names the traits behind the number, instead of returning a ranking you cannot question.' },
  { title: '“Is my essay ready to send?”', description: 'It reviews the draft against a rubric, quotes the lines that weaken it, and lists what is already working.' },
  { title: '“What should I be doing about my list?”', description: 'It answers using your own profile — grades, tests, budget and target countries — not a generic admissions FAQ.' }];

  const governance = [
  { title: 'Approved, not asserted', description: 'Progress counts only once a teacher or counselor has approved the evidence behind it. Nobody marks their own work complete.' },
  { title: 'Scoped by role', description: 'A counselor sees the students assigned to them, a school sees its own, and a parent sees only the sections consent allows.' },
  { title: 'Private by default', description: 'Messages, counselor notes, essay drafts and task submissions stay out of staff overviews unless policy puts them there.' }];


  useEffect(() => {
    const page = pageRef.current;
    if (!page) return undefined;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const paths = [...page.querySelectorAll('.landing-path-list')];
    const steps = [...page.querySelectorAll('.landing-path-list li')];
    const groups = reduced ? [] : [...page.querySelectorAll('[data-reveal]')];
    if (!reduced) page.classList.add('is-animated');
    let frame = 0;

    // One rAF-throttled pass for every scroll-linked behaviour on the page:
    // nav state, section reveals and step emphasis. Adding a listener per
    // effect is what makes pages like this feel expensive.
    const update = () => {
      frame = 0;
      const y = window.scrollY;
      const viewport = window.innerHeight;
      page.classList.toggle('is-scrolled', y > 8);
      page.classList.toggle('is-compact', y > viewport * 0.6);

      // Reveals run both ways: returning to the top replays them.
      for (const group of groups) group.classList.toggle('is-in', group.getBoundingClientRect().top < viewport * 0.88);
      for (const path of paths) path.classList.toggle('is-in', path.getBoundingClientRect().top < viewport * 0.92);
      // Emphasise the step nearest the reading line rather than all of them.
      if (steps.length) {
        let nearest = 0;
        let best = Infinity;
        steps.forEach((step, index) => {
          const distance = Math.abs(step.getBoundingClientRect().top - viewport * 0.38);
          if (distance < best) {best = distance;nearest = index;}
        });
        steps.forEach((step, index) => step.classList.toggle('is-active', index === nearest));
      }
    };
    // Resize matters as much as scroll: rotating a phone or growing the window
    // changes which band sits under the bar without firing a scroll event.
    const onChange = () => {if (!frame) frame = window.requestAnimationFrame(update);};
    update();
    window.addEventListener('scroll', onChange, { passive: true });
    window.addEventListener('resize', onChange, { passive: true });
    return () => {
      window.removeEventListener('scroll', onChange);
      window.removeEventListener('resize', onChange);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  return <div className="landing-page" id="landing-top" ref={pageRef}>
    <a className="landing-skip" href="#landing-main">{t('Skip to content')}</a>
    <header className="landing-nav">
      <div className="lp-shell">
        <a href="#landing-top" className="landing-brand" aria-label={t('Naseeb Edu home')}><BrandLockup theme={theme} /></a>
        <nav aria-label={t('Landing navigation')}>
          <a href="#journey">{t('Journey')}</a>
          <a href="#platform">{t('Platform')}</a>
          <a href="#trust">{t('Trust')}</a>
        </nav>
        <div className="landing-nav-actions">
          <LanguageSelector language={language} onChange={changeLanguage} compact />
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
          <button type="button" className="landing-login-button" onClick={onLogin}>{t('Sign in')}</button>
        </div>
      </div>
    </header>

    <main id="landing-main">
      <section className="landing-hero">
        <div className="lp-shell landing-hero-grid">
          <div className="landing-hero-copy">
            <p className="lp-eyebrow">{t('For schools, counselors and students in Uzbekistan')}</p>
            <h1><span>{t('The application')}</span>{' '}<span>{t('is a long year.')}</span>{' '}<em>{t('Hold it together.')}</em></h1>
            <p className="landing-hero-lede">{t('One workspace where a school, a counselor and a student run an international university application together — from the first goal to the final offer.')}</p>
            <div className="landing-hero-actions">
              <a className="landing-primary-cta" href="#journey">{t('See how it works')} <ChevronRight size={17} /></a>
              {SCHOOL_CONTACT_URL ?
              <a className="landing-text-cta" href={SCHOOL_CONTACT_URL}>{t('Bring Naseeb Edu to your school')} <ChevronRight size={15} /></a> :
              <button type="button" className="landing-text-cta" onClick={onLogin}>{t('Sign in')} <ChevronRight size={15} /></button>}
            </div>
            <p className="landing-access-note"><Fingerprint size={15} /> {t('Students receive a temporary login from their school or counselor. There is no public sign-up.')}</p>
          </div>
          <figure className="landing-hero-media">
            <img src="/landing/naseeb-counseling-hero.jpg" alt={t('A student and counselor planning a university application together.')} width="1600" height="853" decoding="async" />
          </figure>
        </div>
        <div className="landing-rail">
          <div className="lp-shell">
            {ledger.map((item) =>
            <article key={item.label}>
                <b>{formatNumberLocale(item.figure)}</b>
                <span>{t(item.label)}</span>
                <small>{t(item.description)}</small>
              </article>
            )}
          </div>
        </div>
      </section>

      <section className="landing-band landing-journey" id="journey">
        <div className="lp-shell">
          <div className="landing-section-head" data-reveal>
            <h2>{t('Four steps, in order.')}</h2>
            <p>{t('Each step unlocks the next only after a counselor approves the work behind it.')}</p>
            {/* A real Level 1 mission in a real state. Title, category, status
                vocabulary and the 75 XP award all come from services.py.
                Ordered after the list on mobile: the example follows what it illustrates. */}
            <figure className="landing-specimen">
              <figcaption>{t('Step 3')} · {t('Applications')}</figcaption>
              <p>{t('Build a balanced university shortlist')}</p>
              <div>
                <span className="landing-specimen-status">{t('Submitted for approval')}</span>
                <b>{tx`+${formatNumberLocale(75)} XP`}</b>
              </div>
              <small>{t('The next step stays locked until a counselor approves this one. XP counts toward the student’s level.')}</small>
            </figure>
          </div>
          <ol className="landing-path-list">
            {path.map((step) => <li key={step.title}><h3>{t(step.title)}</h3><p>{t(step.description)}</p></li>)}
          </ol>
        </div>
      </section>

      <section className="landing-band landing-platform" id="platform">
        <div className="lp-shell">
          <div className="landing-section-head" data-reveal>
            <h2>{t('What the workspace actually does.')}</h2>
            <p>{t('Six connected surfaces, not six separate tools.')}</p>
          </div>
          <div className="landing-register">
            {capabilities.map(({ icon: Icon, title, description, note }) =>
            <article className="landing-capability" key={title}>
                <Icon size={19} aria-hidden="true" />
                <h3>{t(title)}</h3>
                <p>{t(description)}</p>
                <span className="landing-capability-note">{t(note)}</span>
              </article>
            )}
          </div>
        </div>
      </section>

      <section className="landing-band landing-invert landing-trust" id="trust">
        <div className="lp-shell">
          <div className="landing-trust-head" data-reveal>
            <h2>{t('Trust is a structure, not a promise.')}</h2>
            <p>{t('A record here means something because the platform decides who may write it, who must approve it, and who is allowed to read it.')}</p>
          </div>
          <dl className="landing-ledger">
            {governance.map((item) =>
            <div key={item.title}>
                <dt>{t(item.title)}</dt>
                <dd>{t(item.description)}</dd>
              </div>
            )}
          </dl>
        </div>
      </section>

      <section className="landing-band landing-ai">
        <div className="lp-shell">
          <div className="landing-ai-head" data-reveal="mask">
            <p className="lp-eyebrow">{t('Naseeb AI')}</p>
            <h2>{t('Ask the question you would ask a counselor at midnight.')}</h2>
          </div>
          <div className="landing-ai-asks">
            {asks.map((item) =>
            <article key={item.title}>
                <p className="landing-ai-ask">{t(item.title)}</p>
                <p className="landing-ai-answer">{t(item.description)}</p>
              </article>
            )}
          </div>
          <p className="landing-ai-limit"><ShieldCheck size={15} /> {t('It reads only what your role already permits, and it never rewrites your work or acts for you.')}</p>
        </div>
      </section>
    </main>

    <footer className="landing-footer">
      <div className="lp-shell">
        <small>© {new Date().getFullYear()} Naseeb Edu</small>
        <a className="landing-footer-mark" href="#landing-top" aria-label={t('Back to top')} title={t('Back to top')}>
          <BrandLockup theme={theme} />
        </a>
        <div className="landing-footer-controls">
          <LanguageSelector language={language} onChange={changeLanguage} />
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
          {SCHOOL_CONTACT_URL && <a className="landing-footer-contact" href={SCHOOL_CONTACT_URL}>{t('Contact')}</a>}
        </div>
      </div>
    </footer>
  </div>;
}

function Login({ onLogin, onBack, theme, toggleTheme, language, changeLanguage }) {
  const [form, setForm] = useState(SHOW_DEMO_ACCOUNTS ?
  { username: 'counselor', password: 'admin12345' } :
  { username: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      await api.login(form.username, form.password);
      await onLogin();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return <main className="login-page">
    <section className="login-copy">
      <button type="button" className="login-return" onClick={onBack}><ArrowLeft size={17} /> {t('Home')}</button>
      <div className="login-copy-content">
        <BrandLogo theme={theme} className="login-emblem" />
        <span className="eyebrow">{t("NASEEB EDU / EDUCATION PLATFORM")}</span>
        <h1>{t('Every opportunity.')}<br />{t('One trusted path.')}</h1>
        <p>{t('A professional counseling platform connecting students in Uzbekistan with global education opportunities.')}</p>
        <span className="brand-tagline">{t('Bridging Uzbekistan to the World Through Education')}</span>
      </div>
    </section>
    <section className="login-form-panel" aria-label={t('Sign in')}>
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand-row"><BrandLockup theme={theme} /><div className="login-preferences"><LanguageSelector language={language} onChange={changeLanguage} compact /><ThemeToggle theme={theme} onToggle={toggleTheme} /></div></div>
        <div><h2>{t('Sign in')}</h2><p>{t('Enter your username and password.')}</p></div>
        <Field label={t('Username')}><input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} autoComplete="username" required /></Field>
        <Field label={t('Password')}><input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="current-password" required /></Field>
        {error && <div className="alert error">{error}</div>}
        <button className="button primary full" disabled={loading} aria-busy={loading}>{loading ? t("Signing in…") : t("Sign in")}<ChevronRight size={18} /></button>
        {SHOW_DEMO_ACCOUNTS && <div className="demo-hint">{t("Demo: counselor / admin12345")}</div>}
      </form>
    </section>
  </main>;
}

function ForcedPasswordChange({ user, onChanged, onSignOut, theme, toggleTheme, language, changeLanguage }) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    if (password !== confirmPassword) {setError(t('Passwords do not match.'));return;}
    setSaving(true);setError('');
    try {const result = await api.changePassword(password, confirmPassword);await onChanged(result.user);}
    catch (requestError) {setError(requestError.message);} finally
    {setSaving(false);}
  }
  return <main className="password-change-page"><section className="password-change-card"><header><BrandLockup theme={theme} /><div className="password-change-preferences"><LanguageSelector language={language} onChange={changeLanguage} compact /><ThemeToggle theme={theme} onToggle={toggleTheme} /></div></header><div className="password-change-intro"><span className="password-change-icon"><Fingerprint size={24} /></span><span className="eyebrow">{t('Temporary login')}</span><h1>{t('Change temporary password')}</h1><p>{t('Create a permanent password before opening your cabinet.')}</p></div><form className="form-grid" onSubmit={submit}><Field label={t('New password')} hint={t('Use at least 12 characters with upper/lowercase letters and a number.')}><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength="12" autoComplete="new-password" required /></Field><Field label={t('Confirm password')}><input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} minLength="12" autoComplete="new-password" required /></Field>{error && <div className="alert error form-wide">{error}</div>}<div className="password-change-warning form-wide"><ShieldAlert size={17} /><p>{t('Your temporary password has already been consumed. If you leave now, an administrator must reissue it.')}</p></div><div className="form-actions form-wide"><button type="button" className="button quiet" onClick={onSignOut}>{t('Sign out')}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving securely…") : t("Save new password")}</button></div></form><footer>{fullName(user)} · {user.school_name || label(user.role)}</footer></section></main>;
}

const PAGE_RESOURCE_KEYS = {
  dashboard: ['dashboard', 'students', 'tasks', 'applications', 'essays', 'achievements', 'honors', 'bookings', 'team', 'parentPortal'],
  schools: ['schools'], students: ['students'], profile: ['students'], academics: ['students', 'researches'],
  portfolio: ['projects', 'internships'], activities: ['activities', 'honors', 'achievements'],
  recommendations: ['recommendations'], tasks: ['tasks', 'students'],
  roadmap: ['roadmapMissions', 'tasks', 'students'], applications: ['applications', 'universities', 'students'],
  documents: ['documents'], certificates: ['documents'], essays: ['essays'],
  student_center: ['students', 'researches', 'projects', 'internships', 'activities', 'honors', 'achievements', 'recommendations', 'documents'],
  community: ['communityPosts'], bookings: ['bookings'], messages: ['messageChannels'], program_usage: ['programServices', 'students'],
  programs: ['opportunityPrograms', 'scholarships'], resource_index: ['resourceLibrary'], essay_lab: ['essays'],
  college_search: ['students', 'universities', 'applications'], store: ['storeItems'], contacts: ['team'], support: ['supportTickets'],
  screen_time: [],
  parent_progress: ['parentPortal'], parent_tasks: ['parentPortal'], parent_applications: ['parentPortal'],
  parent_documents: ['parentPortal'], parent_meetings: ['parentPortal']
};

function Field({ label: title, children, error = '', hint = '' }) {
  return <label className={`field ${error ? 'is-error' : ''}`.trim()}><span>{title}</span>{children}{error ? <small className="field-error">{error}</small> : hint ? <small className="field-hint">{hint}</small> : null}</label>;
}

function CheckboxControl({ children, className = '', ...props }) {
  return <label className={`checkbox-card ${className}`.trim()}>
    <input type="checkbox" {...props} />
    <span className="checkbox-indicator" aria-hidden="true"><Check size={14} strokeWidth={3} /></span>
    <span>{children}</span>
  </label>;
}

function ChoiceCards({ name, label: groupLabel, value, onChange, options }) {
  function handleKeyDown(event, index) {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const direction = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1;
    const nextIndex = (index + direction + options.length) % options.length;
    onChange(options[nextIndex].value);
    event.currentTarget.closest('.choice-card-group')?.querySelectorAll('input')[nextIndex]?.focus();
  }
  return <div className="choice-card-group" role="radiogroup" aria-label={groupLabel} style={{ '--choice-columns': options.length }}>
    {options.map((option, index) => {
      const OptionIcon = option.icon || Target;
      return <label className="choice-card" key={option.value}>
        <input type="radio" name={name} value={option.value} checked={value === option.value} onChange={() => onChange(option.value)} onKeyDown={(event) => handleKeyDown(event, index)} />
        <OptionIcon aria-hidden="true" />
        <span className="choice-card-copy"><b>{t(option.label)}</b><small>{t(option.description)}</small></span>
        <CheckCircle2 className="choice-card-check" size={19} aria-hidden="true" />
      </label>;
    })}
  </div>;
}

function Badge({ children, tone = '' }) {
  const normalized = String(children || '').toLowerCase().replaceAll(' ', '-');
  return <span className={`badge ${tone || normalized}`}>{label(children)}</span>;
}

function Modal({ title, onClose, children }) {
  const modalRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    const modal = modalRef.current;
    const focusable = () => [...(modal?.querySelectorAll('button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])') || [])];
    (modal?.querySelector('[data-autofocus]') || focusable()[0])?.focus();
    function handleKeyDown(event) {
      if (event.key === 'Escape') {event.preventDefault();onCloseRef.current();return;}
      if (event.key !== 'Tab') return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {event.preventDefault();last.focus();} else
      if (!event.shiftKey && document.activeElement === last) {event.preventDefault();first.focus();}
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => {document.removeEventListener('keydown', handleKeyDown);previous?.focus?.();};
  }, []);
  return <div className="modal-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
    <section ref={modalRef} className="modal" role="dialog" aria-modal="true" aria-label={t(title)} tabIndex="-1">
      <header><div><span className="eyebrow">{t("NASEEB EDU")}</span><h2>{t(title)}</h2></div><button className="icon-button" onClick={onClose} aria-label={t('Close')}><X /></button></header>
      {children}
    </section>
  </div>;
}

function ActionDialog({ request, onResolve }) {
  const [value, setValue] = useState(request.initialValue || '');
  const isPrompt = request.type === 'prompt';
  const valid = !isPrompt || !request.required || value.trim();
  function submit(event) {
    event.preventDefault();
    if (!valid) return;
    onResolve(isPrompt ? value.trim() : true);
  }
  return <Modal title={request.title} onClose={() => onResolve(isPrompt ? null : false)}><form className="action-dialog" onSubmit={submit}>
    {request.description && <p>{request.description}</p>}
    {isPrompt && <Field label={request.inputLabel || t("Details")}><textarea data-autofocus value={value} onChange={(event) => setValue(event.target.value)} rows={4} required={request.required} /></Field>}
    <div className="form-actions"><button type="button" className="button quiet" onClick={() => onResolve(isPrompt ? null : false)}>{t("Cancel")}</button><button className={`button ${request.tone === 'danger' ? 'danger' : 'primary'}`} disabled={!valid}>{request.confirmLabel || t("Confirm")}</button></div>
  </form></Modal>;
}

function useActionDialog() {
  const [request, setRequest] = useState(null);
  const open = useCallback((config) => new Promise((resolve) => setRequest({ ...config, resolve })), []);
  const confirm = useCallback((config) => open({ type: 'confirm', ...config }), [open]);
  const prompt = useCallback((config) => open({ type: 'prompt', required: true, ...config }), [open]);
  const resolve = useCallback((value) => {
    if (!request) return;
    request.resolve(value);
    setRequest(null);
  }, [request]);
  return { confirm, prompt, dialog: request ? <ActionDialog request={request} onResolve={resolve} /> : null };
}

function Empty({ text = 'No information available yet.' }) {
  return <div className="empty"><span aria-hidden="true"><Inbox size={20} /></span><p>{t(text)}</p></div>;
}

function PageSkeleton() {
  return <div className="page-skeleton" role="status" aria-label={t("Loading page data")}>
    <div className="skeleton-stat-grid">{[0, 1, 2, 3].map((item) => <span className="skeleton-block" key={item} />)}</div>
    <div className="skeleton-panel"><span className="skeleton-line title" />{[0, 1, 2, 3].map((item) => <span className="skeleton-line" key={item} />)}</div>
    <span className="sr-only">{t("Loading page data…")}</span>
  </div>;
}

function ChannelListSkeleton({ count = 4 }) {
  return <div className="channel-skeleton" role="status" aria-label={t("Loading conversations")}>{Array.from({ length: count }, (_, index) => <span key={index}><i /><b /><small /></span>)}</div>;
}

function MessageListSkeleton() {
  return <div className="message-skeleton" role="status" aria-label={t("Loading messages")}>{[58, 74, 46, 66].map((width, index) => <span className={index % 2 ? "mine" : ''} style={{ '--skeleton-width': `${width}%` }} key={`${width}-${index}`}><i /><b /><small /></span>)}</div>;
}

function StaffStatsSkeleton() {
  return <div className="staff-stats-skeleton" role="status" aria-label={t("Loading messaging overview")}>{Array.from({ length: 5 }, (_, index) => <span key={index}><i /><b /></span>)}</div>;
}

function InlineLoadError({ message, onRetry }) {
  return <div className="inline-load-error" role="alert"><WifiOff size={20} /><p>{message}</p><button type="button" className="button quiet small" onClick={onRetry}><RefreshCw size={14} /> {t("Retry")}</button></div>;
}

function PageDataBoundary({ page, data, stats, loading, resourceStatus, retry, children }) {
  const keys = PAGE_RESOURCE_KEYS[page] || [page];
  const tracked = keys.filter((key) => resourceStatus[key]);
  const loadingKeys = tracked.filter((key) => resourceStatus[key].status === 'loading');
  const failedKeys = tracked.filter((key) => resourceStatus[key].status === 'error');
  const hasVisibleData = keys.some((key) => key === 'dashboard' ? Boolean(stats) : Boolean(data[key]?.length));
  const initialLoading = (loadingKeys.length > 0 || loading && tracked.length === 0) && !hasVisibleData;

  if (initialLoading) return <PageSkeleton />;
  return <>
    {failedKeys.length > 0 && <div className="data-state error" role="alert"><X size={18} /><div><b>{t("Some information could not be loaded")}</b><p>{failedKeys.slice(0, 2).map((key) => resourceStatus[key].error).join(' · ')}</p>{hasVisibleData && <small>{t("Available information remains visible while you retry.")}</small>}</div><button type="button" className="button quiet small" onClick={() => retry(failedKeys)}><RefreshCw size={14} /> {t("Retry")}</button></div>}
    {loadingKeys.length > 0 && hasVisibleData && <div className="data-state refreshing" role="status"><RefreshCw className="spin" size={16} /><span>{t("Refreshing this page. Current information remains available.")}</span></div>}
    {children}
  </>;
}

function ScreenTimeTracker({ page }) {
  const activeSeconds = useRef(0);
  const lastInteraction = useRef(Date.now());
  const sending = useRef(false);
  const queued = useRef(null);

  useEffect(() => {
    const markInteraction = () => {lastInteraction.current = Date.now();};
    const events = ['pointerdown', 'keydown', 'scroll', 'touchstart'];
    events.forEach((eventName) => window.addEventListener(eventName, markInteraction, { passive: true }));

    const persistAndSend = async () => {
      const seconds = activeSeconds.current;
      activeSeconds.current = 0;
      if (!queued.current) {
        try {queued.current = JSON.parse(localStorage.getItem(SCREEN_TIME_QUEUE_KEY) || '[]');} catch {queued.current = [];}
      }
      let queue = queued.current;
      if (seconds > 0) {
        const date = localDateKey();
        const existing = queue.find((entry) => entry.date === date && entry.page === page);
        if (existing) existing.seconds += seconds;else
        queue.push({ date, page, seconds });
        try {localStorage.setItem(SCREEN_TIME_QUEUE_KEY, JSON.stringify(queue));} catch {/* Memory queue remains available in strict privacy modes. */}
      }
      if (!navigator.onLine || sending.current || !queue.length) return;
      sending.current = true;
      const batch = queue.slice(0, 50).map((entry) => ({ ...entry, seconds: Math.min(300, entry.seconds) }));
      try {
        await api.trackScreenTime(batch);
        batch.forEach((sent) => {
          const current = queue.find((entry) => entry.date === sent.date && entry.page === sent.page);
          if (current) current.seconds -= sent.seconds;
        });
        queue = queue.filter((entry) => entry.seconds > 0);
        queued.current = queue;
        try {
          if (queue.length) localStorage.setItem(SCREEN_TIME_QUEUE_KEY, JSON.stringify(queue));else
          localStorage.removeItem(SCREEN_TIME_QUEUE_KEY);
        } catch {/* The in-memory queue still holds any remaining aggregate. */}
      } catch {






        // Aggregate seconds stay queued locally and retry when the connection returns.
      } finally {sending.current = false;}};const tick = window.setInterval(() => {if (document.visibilityState === 'visible' && Date.now() - lastInteraction.current < 60_000) activeSeconds.current += 1;
      }, 1_000);
    const flush = window.setInterval(persistAndSend, 30_000);
    const onVisibility = () => {if (document.visibilityState === 'hidden') persistAndSend();};
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('online', persistAndSend);
    persistAndSend();
    return () => {
      window.clearInterval(tick);
      window.clearInterval(flush);
      events.forEach((eventName) => window.removeEventListener(eventName, markInteraction));
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('online', persistAndSend);
      persistAndSend();
    };
  }, [page]);
  return null;
}

function AssistantCenter({ user, onOpenScreenTime }) {
  const welcome = useMemo(() => ({
    id: `welcome-${user.id}`,
    role: 'assistant',
    local: true,
    content: user.role === 'counselor' ?
    'I can help you review workload patterns, prepare check-in plans, and improve counseling workflows without exposing student identities.' :
    'I can help you plan tasks, understand your roadmap, and prepare application work. I cannot change your account data.'
  }), [user.id, user.role]);
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([welcome]);
  const [input, setInput] = useState('');
  const [status, setStatus] = useState('ready');
  const [error, setError] = useState('');
  const abortRef = useRef(null);
  const inputRef = useRef(null);
  const listRef = useRef(null);
  const busy = status === 'submitted' || status === 'streaming';

  useEffect(() => setMessages([welcome]), [welcome]);
  useEffect(() => {
    if (!open) return undefined;
    function closeOnEscape(event) {if (event.key === 'Escape') setOpen(false);}
    document.addEventListener('keydown', closeOnEscape);
    window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: status === 'streaming' ? 'auto' : 'smooth' });
  }, [messages, open, status]);

  function clearConversation() {
    abortRef.current?.abort();
    setMessages([welcome]);
    setInput('');
    setError('');
    setStatus('ready');
  }

  async function sendMessage(value = input) {
    const content = value.trim();
    if (!content || busy) return;
    const stamp = Date.now();
    const userMessage = { id: `user-${stamp}`, role: 'user', content };
    const assistantId = `assistant-${stamp}`;
    const outbound = [...messages.filter((message) => !message.local && message.content), userMessage].
    slice(-12).
    map(({ role, content: text }) => ({ role, content: text }));
    setMessages((current) => [...current, userMessage, { id: assistantId, role: 'assistant', content: '' }]);
    setInput('');
    setError('');
    setStatus('submitted');
    const controller = new AbortController();
    abortRef.current = controller;
    let received = '';
    try {
      const response = await api.streamAssistant(outbound, controller.signal);
      if (!response.body) throw new Error('Streaming is not supported by this browser.');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value: chunk } = await reader.read();
        if (done) break;
        received += decoder.decode(chunk, { stream: true });
        setStatus('streaming');
        setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, content: received } : message));
      }
      received += decoder.decode();
      if (!received.trim()) throw new Error('The assistant returned an empty response.');
      setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, content: received } : message));
      setStatus('ready');
    } catch (requestError) {
      if (requestError?.name === 'AbortError') {
        if (!received) setMessages((current) => current.filter((message) => message.id !== assistantId));
        setStatus('ready');
      } else {
        setMessages((current) => current.filter((message) => message.id !== assistantId));
        setError(requestError?.status === 429 ? t("You have reached the assistant limit. Please try again later.") : t("The assistant could not respond. Check your connection and try again."));
        setStatus('error');
      }
    } finally {
      abortRef.current = null;
    }
  }

  const suggestions = user.role === 'counselor' ?
  ['Plan today’s student check-ins', 'How should I review overdue work?', 'Create a privacy-safe meeting agenda'] :
  ['What should I work on today?', 'Break my next roadmap mission into steps', 'Help me plan an application essay'];

  return <div className={`assistant-center ${open ? 'open' : ''}`}>
    {open && <section className="assistant-drawer" role="dialog" aria-label={t("Naseeb AI assistant")}>
      <header><div className="assistant-title"><span className="assistant-mark"><Bot size={18} /></span><div><span className="eyebrow">{t("READ-ONLY GUIDANCE")}</span><h2>{t("Naseeb AI")}</h2></div></div><div className="assistant-header-actions"><button type="button" className="icon-button" onClick={clearConversation} aria-label={t("Clear conversation")} title={t("Clear conversation")}><Trash2 size={16} /></button><button type="button" className="icon-button" onClick={() => setOpen(false)} aria-label={t("Close assistant")}><X size={18} /></button></div></header>
      <div className="assistant-safety"><ShieldCheck size={15} /><span>{t("Role-scoped context only. Do not share contact, passport, password, or payment details.")}</span></div>
      <div ref={listRef} className="assistant-messages" aria-live="polite" aria-busy={busy}>
        {messages.map((message) => <article className={`assistant-message ${message.role}`} key={message.id}><span>{message.role === 'assistant' ? <Sparkles size={14} /> : initials(fullName(user))}</span><div><b>{message.role === 'assistant' ? t("Naseeb AI") : t("You")}</b><p>{message.content || <span className="assistant-typing" aria-label={t("Assistant is thinking")}><i /><i /><i /></span>}</p></div></article>)}
        {status === 'submitted' && <span className="sr-only">{t("Assistant is preparing a response.")}</span>}
        {error && <div className="assistant-error" role="alert"><WifiOff size={15} /><span>{error}</span></div>}
      </div>
      {messages.length === 1 && <div className="assistant-suggestions" aria-label={t("Suggested questions")}>{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => sendMessage(suggestion)}>{suggestion}<ChevronRight size={14} /></button>)}</div>}
      <form className="assistant-compose" onSubmit={(event) => {event.preventDefault();sendMessage();}}>
        <textarea ref={inputRef} value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => {if (event.key === 'Enter' && !event.shiftKey) {event.preventDefault();sendMessage();}}} maxLength="2000" rows="2" placeholder={t("Ask about tasks, roadmap, essays…")} disabled={busy} aria-label={t("Message Naseeb AI")} />
        <button type={busy ? "button" : "submit"} className="assistant-send" onClick={busy ? () => abortRef.current?.abort() : undefined} disabled={!busy && !input.trim()} aria-label={busy ? t("Stop response") : t("Send message")}>{busy ? <Square size={16} fill="currentColor" /> : <Send size={17} />}</button>
        <small>{t("AI can make mistakes. Verify important deadlines with your counselor. History is kept only while this page is open.")}</small>
      </form>
    </section>}
    <div className="assistant-launchers"><button type="button" className="screen-time-launcher" onClick={onOpenScreenTime} aria-label={t("Open screen time")}><Clock3 size={19} /><span>{t("Time")}</span></button><button type="button" className="assistant-launcher" onClick={() => setOpen((current) => !current)} aria-label={t("Open Naseeb AI assistant")} aria-expanded={open}><Sparkles size={22} /><span>{t("AI")}</span></button></div>
  </div>;
}

function AppShell({ user, data, stats, page, setPage, query, setQuery, loading, error, refresh, retryResources, resourceStatus, isOnline, logout, theme, toggleTheme, language, changeLanguage, children }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [activeSearchIndex, setActiveSearchIndex] = useState(0);
  const searchRef = useRef(null);
  const navigation = navigationFor(user);
  const meta = PAGE_META[page];
  const searchResults = useMemo(() => globalSearchResults(user, data, query), [user, data, query, language]);
  const supportBadge = user.role === 'admin' ?
  data.supportTickets.filter((ticket) => ['open', 'in_progress'].includes(ticket.status)).length :
  data.supportTickets.filter((ticket) => ticket.has_unread_response).length;
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
  function openSearchResult(result) {
    if (!result) return;
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
  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
      <div className="sidebar-top">
        <BrandLockup theme={theme} />
        <button className="icon-button mobile-only" onClick={() => setMobileOpen(false)} aria-label={t("Close navigation")}><X /></button>
      </div>
      <nav>{navigation.map((item) => {
          const ItemIcon = PAGE_META[item].icon;
          const itemLabel = t(PAGE_META[item].label);
          return <button key={item} className={page === item ? "active" : ''} onClick={() => {setPage(item);setQuery('');setSearchOpen(false);setMobileOpen(false);}} aria-label={itemLabel}><ItemIcon size={18} /><span>{itemLabel}</span>{item === 'support' && supportBadge > 0 && <span className="nav-badge">{supportBadge > 99 ? '99+' : supportBadge}</span>}</button>;
        })}</nav>
      <div className="sidebar-profile"><span className="avatar">{initials(fullName(user))}</span><div><b>{fullName(user)}</b><small>{label(user.role)}</small></div><button className="icon-button" onClick={logout} title={t('Logout')} aria-label={t('Logout')}><LogOut size={18} /></button></div>
    </aside>
    <main className="workspace">
      <header className="top-header">
        <button className="icon-button mobile-only" onClick={() => setMobileOpen(true)} aria-label={t("Open navigation")}><Menu /></button>
        <div className="page-heading"><span className="eyebrow">{t("CURRENT WORKSPACE")}</span><h1>{t(meta.label)}</h1><p>{t(meta.description)}</p></div>
        <div className="header-actions">
          <div className="global-search" ref={searchRef}>
            <div className={`search ${searchOpen && query.trim() ? 'is-open' : ''}`}><Search size={17} /><input role="combobox" aria-autocomplete="list" aria-controls="global-search-results" aria-expanded={searchOpen && Boolean(query.trim())} aria-activedescendant={searchResults[activeSearchIndex]?.id} aria-label={t("Search pages and records")} placeholder={t("Search pages and records…")} value={query} onFocus={() => setSearchOpen(true)} onChange={(event) => {setQuery(event.target.value);setSearchOpen(true);}} onKeyDown={handleSearchKeyDown} />{query && <button type="button" className="search-clear" onClick={() => {setQuery('');setSearchOpen(false);}} aria-label={t("Clear search")}><X size={14} /></button>}</div>
            {searchOpen && query.trim() && <div className="search-results" id="global-search-results" role="listbox" aria-label={t("Search results")}>
              {searchResults.map((result, index) => {
                const ResultIcon = PAGE_META[result.destination].icon;
                return <button type="button" id={result.id} role="option" aria-selected={index === activeSearchIndex} className={index === activeSearchIndex ? 'active' : ''} key={result.id} onMouseEnter={() => setActiveSearchIndex(index)} onMouseDown={(event) => event.preventDefault()} onClick={() => openSearchResult(result)}><span className="search-result-icon"><ResultIcon size={16} /></span><span><b>{result.title}</b><small>{result.kind === 'page' ? t("Page") : result.subtitle}</small></span><ChevronRight size={15} /></button>;
              })}
              {!searchResults.length && <div className="search-empty"><Search size={18} /><span>{tx`No results for “${query.trim()}”`}</span></div>}
              {searchResults.length > 0 && <footer><span>{tx`${searchResults.length} results`}</span><small>{t("Use ↑↓ and Enter")}</small></footer>}
            </div>}
          </div>
          <LanguageSelector language={language} onChange={changeLanguage} compact />
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
          <button className="icon-button" onClick={refresh} disabled={loading} aria-busy={loading} title={t('Refresh')}><RefreshCw className={loading ? "spin" : ''} size={19} /></button>
        </div>
      </header>
      {!isOnline && <div className="data-state offline" role="status"><WifiOff size={18} /><div><b>{t('You are offline')}</b><p>{t('Current information remains available. Reconnect before saving changes.')}</p></div></div>}
      {error && <div className="alert error workspace-alert">{error}</div>}
      <div className="page-content"><PageTitleContext.Provider value={t(meta.label)}><PageDataBoundary {...{ page, data, stats, loading, resourceStatus }} retry={retryResources}>{children}</PageDataBoundary></PageTitleContext.Provider></div>
    </main>
    <ScreenTimeTracker page={page} />
    {['counselor', 'student'].includes(user.role) && <AssistantCenter user={user} onOpenScreenTime={() => setPage('screen_time')} />}
  </div>;
}

function Dashboard({ user, data, stats, setPage }) {
  const student = ownStudent(data);
  if (user.role === 'organization') return <>
    <div className="stat-grid"><Stat label={t("School students")} value={formatNumberLocale(stats?.students_total ?? data.students.length)} note={t("Only students from your school")} /><Stat label={t("Task progress")} value={formatPercentLocale(stats?.average_task_progress ?? 0)} note={t("Weighted completion")} /><Stat label={t("Roadmap progress")} value={formatPercentLocale(stats?.average_roadmap_progress ?? 0)} note={t("Mission completion")} /><Stat label={t("Need attention")} value={formatNumberLocale(stats?.students_at_risk ?? 0)} note={t("Late task or mission")} tone="danger" /></div>
    <Panel title={t("Student progress")} action={<button className="button primary" onClick={() => setPage('students')}>{t("Student profiles")} <ChevronRight size={17} /></button>}><StudentTable data={data} readOnly /></Panel>
  </>;
  if (user.role === 'student') return <StudentDashboard user={user} data={data} stats={stats} setPage={setPage} />;
  return <>
    <div className="stat-grid"><Stat label={t("Students")} value={formatNumberLocale(stats?.students_total ?? data.students.length)} /><Stat label={t("Task progress")} value={formatPercentLocale(stats?.average_task_progress ?? 0)} /><Stat label={t("Roadmap progress")} value={formatPercentLocale(stats?.average_roadmap_progress ?? 0)} /><Stat label={t("Need attention")} value={formatNumberLocale(stats?.students_at_risk ?? stats?.tasks_late ?? 0)} tone="danger" /></div>
    <div className="split-grid wide-left"><Panel title={t("Student progress")} action={<button className="button quiet" onClick={() => setPage('students')}>{t("View all")} <ChevronRight size={16} /></button>}><StudentTable data={data} readOnly /></Panel><Panel title={t("Deadline radar")}>{data.tasks.slice(0, 6).map((task) => <Record key={task.id} title={task.title} meta={`${studentName(data, task.student)} • ${dateText(task.due_date)}`} badge={task.status} />)}{!data.tasks.length && <Empty />}</Panel></div>
  </>;
}

function StudentDashboard({ user, data, setPage }) {
  const student = ownStudent(data);
  const pendingTasks = data.tasks.filter((item) => item.status !== 'approved');
  const nextBooking = [...data.bookings].filter((item) => new Date(item.starts_at) >= new Date() && !['rejected', 'completed'].includes(item.status)).sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at))[0];
  const completed = data.tasks.filter((item) => item.status === 'approved').length;
  const achievementTotal = data.achievements.length + data.honors.length;
  return <div className="section-stack student-portal">
    <section className="student-welcome">
      <div><span className="eyebrow">{t("WELCOME BACK")}</span><h2>{fullName(user)}</h2><p>{t("Complete today’s priorities and strengthen your application profile.")}</p><div className="welcome-actions"><button className="button light" onClick={() => setPage('roadmap')}><Compass size={17} /> {t("Open roadmap")}</button><button className="button ghost-light" onClick={() => setPage('college_search')}><Search size={17} /> {t("Find universities")}</button></div></div>
      <div className="readiness-ring" style={{ '--progress': `${student?.journey_progress_percent || 0}%` }}><strong>{formatPercentLocale(student?.journey_progress_percent || 0)}</strong><span>{t("Journey progress")}</span></div>
    </section>
    <div className="student-dashboard-overview">
      <div className="student-dashboard-progress"><JourneyProgress student={student} /><LevelProgress student={student} /></div>
      <DashboardDiscoveryCards setPage={setPage} />
    </div>
    <div className="stat-grid"><Stat label={t("Active tasks")} value={pendingTasks.length} note={tx`${completed} completed`} /><Stat label={t("Applications")} value={data.applications.length} note={tx`${data.applications.filter((item) => item.status === 'submitted').length} submitted`} /><Stat label={t("Essays")} value={data.essays.length} note={tx`${data.essays.filter((item) => item.status === 'approved').length} approved`} /><Stat label={t("Achievements")} value={achievementTotal} note={t("Honors included")} /></div>
    <div className="student-dashboard-grid">
      <div className="student-dashboard-column">
        <Panel title={t("Next priorities")} action={<button className="button quiet small" onClick={() => setPage('roadmap')}>{t("View roadmap")} <ChevronRight size={14} /></button>}><div className="record-list">{pendingTasks.slice(0, 4).map((task) => <Record key={task.id} title={task.title} meta={`${dateText(task.due_date)} • ${label(task.priority)}`} badge={task.status} />)}{!pendingTasks.length && <Empty text={t("All tasks are complete.")} />}</div></Panel>
        <Panel title={t("Upcoming session")} action={<button className="button quiet small" onClick={() => setPage('bookings')}>{t("Meetings")}</button>}>{nextBooking ? <div className="booking-highlight"><span><CalendarClock size={22} /></span><div><b>{nextBooking.topic}</b><small>{dateTimeText(nextBooking.starts_at)} • {nextBooking.duration_minutes} {t("min")}</small><p>{nextBooking.participant_name || t("Meeting participant")} · {label(nextBooking.participant_role)}</p></div><Badge>{nextBooking.status}</Badge></div> : <Empty text={t("No upcoming sessions.")} />}</Panel>
      </div>
      <div className="student-dashboard-column">
        <Panel title={t("Student Center quick access")}><div className="quick-grid">{[
            ['Profile & academics', 'student_center', BookOpen], ['Essay Lab', 'essay_lab', PenLine], ['Applications', 'applications', Target], ['Resources', 'resource_index', LibraryBig]].
            map(([title, page, Icon]) => <button key={page} onClick={() => setPage(page)}><span><Icon size={19} /></span><b>{t(title)}</b><ChevronRight size={15} /></button>)}</div></Panel>
        <Panel title={t("My Naseeb team")} action={<button className="button quiet small" onClick={() => setPage('contacts')}>{t("All contacts")}</button>}><div className="team-mini-list">{data.team.slice(0, 3).map((member) => <div key={`${member.kind}-${member.id}`}><span className="avatar">{initials(member.name)}</span><div><b>{member.name}</b><small>{member.role}</small></div><button className="icon-button" onClick={() => setPage('messages', { context: { action: 'message', memberId: member.id, memberName: member.name } })} aria-label={tx`Message ${member.name}`}><MessageCircle size={16} /></button></div>)}{!data.team.length && <Empty text={t("No team members have been assigned yet.")} />}</div></Panel>
      </div>
    </div>
  </div>;
}

function DashboardDiscoveryCards({ setPage }) {
  const personalityAction = PERSONALITY_QUIZ_URL ?
  <a href={PERSONALITY_QUIZ_URL} target="_blank" rel="noreferrer">{t("Start assessment")} <ExternalLink size={15} /></a> :
  <button type="button" disabled title={t("Add VITE_PERSONALITY_QUIZ_URL to enable this assessment")}>{t("Link coming soon")}</button>;
  return <section className="dashboard-discovery-rail" aria-label={t("Student discovery tools")}>
    <article className="dashboard-discovery-card personality">
      <Fingerprint className="discovery-card-art" size={118} strokeWidth={1.35} />
      <div><span>{t("SELF DISCOVERY")}</span><h3>{t("Personality & Interests")}</h3><p>{t("Identify your strengths, interests, and future study direction.")}</p>{personalityAction}</div>
    </article>
    <article className="dashboard-discovery-card university">
      <GraduationCap className="discovery-card-art" size={122} strokeWidth={1.35} />
      <div><span>{t("COLLEGE RESEARCH")}</span><h3>{t("University Match")}</h3><p>{t("Find universities that match your academic profile and goals.")}</p><button type="button" onClick={() => setPage('college_search')}>{t("Explore matches")} <ChevronRight size={16} /></button></div>
    </article>
  </section>;
}

function JourneyProgress({ student }) {
  const rows = [
  ['Tasks', student?.task_progress_percent || 0, tx`${student?.task_status_counts?.approved || 0} approved`],
  ['Roadmap', student?.roadmap_progress_percent || 0, tx`${student?.roadmap_status_counts?.completed || 0} completed`],
  ['Overall journey', student?.journey_progress_percent || 0, student?.is_at_risk ? t('A deadline needs your attention') : t('Progress is on track')]];

  return <section className="journey-progress"><div><span className="eyebrow">{t("LIVE PROGRESS")}</span><h3>{t("Tasks and roadmap progress")}</h3><p>{t("Every update is added to your overall progress automatically.")}</p></div><div className="journey-progress-bars">{rows.map(([title, value, note]) => <div key={title}><header><b>{t(title)}</b><strong>{formatPercentLocale(value)}</strong></header><div className="progress"><span style={{ width: `${value}%` }} /></div><small>{note}</small></div>)}</div></section>;
}

function LevelProgress({ student }) {
  if (!student) return null;
  return <section className="journey-progress"><div><span className="eyebrow">{t("XP & LEVEL")}</span><h3>{t("Level")} {formatNumberLocale(student.level ?? 1)}</h3><p>{student.level_up_pending ? tx`Teacher or counselor approval is pending for Level ${student.eligible_level}.` : tx`Next level: ${student.next_level_xp ?? 0} XP`}</p></div><div className="journey-progress-bars"><div><header><b>{formatNumberLocale(student.xp_total ?? 0)} {t("XP")}</b><strong>{formatPercentLocale(student.xp_progress_percent ?? 0)}</strong></header><div className="progress"><span style={{ width: `${student.xp_progress_percent ?? 0}%` }} /></div><small>{student.level_up_pending ? t("XP threshold reached — your level changes only after approval.") : tx`${Math.max(0, (student.next_level_xp ?? 0) - (student.xp_total ?? 0))} XP remaining`}</small></div></div></section>;
}

function Stat({ label: title, value, note, tone = '' }) {
  return <article className={`stat-card ${tone}`}><span>{t(title)}</span><strong>{value}</strong>{note && <small>{t(note)}</small>}</article>;
}

function ActionMenu({ children, label: menuLabel = 'More actions' }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const rect = triggerRef.current?.getBoundingClientRect();
    const width = 200;
    setPosition({ top: (rect?.bottom || 0) + 6, left: Math.max(12, Math.min((rect?.right || width) - width, window.innerWidth - width - 12)) });
    function closeOnOutside(event) {
      if (!triggerRef.current?.contains(event.target) && !menuRef.current?.contains(event.target)) setOpen(false);
    }
    function closeOnEscape(event) {if (event.key === 'Escape') {setOpen(false);triggerRef.current?.focus();}}
    const closeOnViewportChange = () => setOpen(false);
    document.addEventListener('pointerdown', closeOnOutside);
    document.addEventListener('keydown', closeOnEscape);
    window.addEventListener('resize', closeOnViewportChange);
    window.addEventListener('scroll', closeOnViewportChange, true);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutside);
      document.removeEventListener('keydown', closeOnEscape);
      window.removeEventListener('resize', closeOnViewportChange);
      window.removeEventListener('scroll', closeOnViewportChange, true);
    };
  }, [open]);
  return <div className="action-menu"><button ref={triggerRef} type="button" className="icon-button" aria-label={t(menuLabel)} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((current) => !current)}><MoreHorizontal size={17} /></button>{open && createPortal(<div ref={menuRef} className="action-menu-popover" role="menu" style={position} onClick={() => setOpen(false)}>{children}</div>, document.body)}</div>;
}

function Panel({ title, action, children, className = '' }) {
  const pageTitle = useContext(PageTitleContext);
  const translatedTitle = t(title);
  const duplicatesPageTitle = Boolean(pageTitle && translatedTitle === pageTitle);
  const showHeader = !duplicatesPageTitle || action;
  return <section className={`panel ${duplicatesPageTitle ? 'contextual-panel' : ''} ${className}`}>{showHeader && <header className={duplicatesPageTitle ? 'actions-only' : ''}><h2 className={duplicatesPageTitle ? 'sr-only' : ''}>{translatedTitle}</h2>{action}</header>}<div className="panel-body">{children}</div></section>;
}

function flattenActions(children) {
  const items = [];
  Children.toArray(children).forEach((child) => {
    if (!child) return;
    if (isValidElement(child) && child.type === Fragment) flattenActions(child.props.children).forEach((item) => items.push(item));else
    items.push(child);
  });
  return items;
}

function Record({ title, meta, description, badge, actions, primaryAction, overflowActions }) {
  const actionItems = flattenActions(actions);
  const resolvedPrimary = primaryAction || actionItems[0] || null;
  const resolvedOverflow = overflowActions || (actionItems.length > 1 ? actionItems.slice(1) : null);
  return <article className="record"><div className="record-main"><div><b>{title}</b>{meta && <small>{meta}</small>}</div>{badge && <Badge>{badge}</Badge>}</div>{description && <p>{description}</p>}{(resolvedPrimary || resolvedOverflow) && <div className="record-actions">{resolvedPrimary}{resolvedOverflow && <ActionMenu>{resolvedOverflow}</ActionMenu>}</div>}</article>;
}

function GoogleDocsPreview({ previewUrl, title }) {
  const [frameState, setFrameState] = useState('loading');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setFrameState('loading');
    const timer = window.setTimeout(() => setFrameState((current) => current === 'loading' ? 'slow' : current), 12_000);
    return () => window.clearTimeout(timer);
  }, [previewUrl, attempt]);
  if (!previewUrl) return null;
  return <div className="google-doc-preview"><div><FileText size={18} /><span><b>{t("Google Docs preview")}</b><small>{t("The document must allow Viewer access or “Anyone with the link” for the preview to load.")}</small></span></div><section className="embedded-preview-frame">
    {frameState !== 'ready' && <div className={`embedded-preview-state ${frameState}`} role="status"><div className="document-skeleton"><span /><span /><span /><span /></div>{frameState === 'slow' && <div className="embedded-preview-slow"><Clock3 size={20} /><b>{t("The preview is taking longer than expected.")}</b><p>{t("Your connection may be slow. You can retry without closing this record.")}</p><button type="button" className="button quiet small" onClick={() => setAttempt((current) => current + 1)}><RefreshCw size={14} /> {t("Retry preview")}</button></div>}</div>}
    <iframe key={`${previewUrl}-${attempt}`} className={frameState === 'ready' ? "is-ready" : ''} src={previewUrl} title={tx`${title} Google Docs preview`} loading="lazy" referrerPolicy="no-referrer" onLoad={() => setFrameState('ready')} onError={() => setFrameState('slow')} />
  </section></div>;
}

function googleDocsTitle(item) {
  return item.title || item.name || item.organization || item.recommender_name || 'Google Docs record';
}

function GoogleDocsActions({ item, onPreview }) {
  if (!item?.google_docs_url) return null;
  if (item.google_docs_preview_url && onPreview) return <button type="button" className="button quiet small" onClick={onPreview}><Eye size={14} /> {t("Preview")}</button>;
  return <a className="button quiet small" href={item.google_docs_url} target="_blank" rel="noreferrer">{t("Open in Google Docs")} <ExternalLink size={14} /></a>;
}

function GoogleDocsRecordModal({ item, onClose }) {
  const title = googleDocsTitle(item);
  return <Modal title={title} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><span>{t("Google Docs attachment")}</span><GoogleDocsActions item={item} /></div><GoogleDocsPreview previewUrl={item.google_docs_preview_url} title={title} /></div></Modal>;
}

function EssayAIReviewPanel({ essay }) {
  const [review, setReview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    api.essayAIReview(essay.id).then((result) => {if (active) setReview(result);}).catch((requestError) => {if (active && requestError.status !== 404) setError(requestError.message);}).finally(() => {if (active) setLoading(false);});
    return () => {active = false;};
  }, [essay.id, essay.version]);
  async function runReview() {
    setRunning(true);setError('');
    try {setReview(await api.essayAIReview(essay.id, true));} catch (requestError) {setError(requestError.message);} finally {setRunning(false);}
  }
  const result = review?.result;
  return <section className="essay-ai-review"><header><div><span className="detail-label">{t("Naseeb AI essay checker")}</span><h3>{t("Feedback without rewriting your voice")}</h3><p>{t("The checker reviews the saved draft. It never changes your essay automatically.")}</p></div><button type="button" className="button primary small" onClick={runReview} disabled={running || loading || String(essay.content || '').trim().length < 80} aria-busy={running}>{running ? <><RefreshCw className="spin" size={15} /> {t("Checking…")}</> : <><Sparkles size={15} /> {review ? t("Check again") : t("Check essay")}</>}</button></header>{String(essay.content || '').trim().length < 80 && <div className="essay-ai-notice"><ShieldAlert size={16} /><span>{t("Add at least 80 characters to the saved draft before using the checker. Google Docs content is not imported automatically.")}</span></div>}{error && <div className="essay-ai-notice error"><X size={16} /><span>{error}</span></div>}{loading && <div className="essay-ai-loading"><span /><span /><span /></div>}{result && <div className="essay-ai-result"><div className="essay-ai-score"><strong>{formatNumberLocale(result.overall_score)}</strong><span>/ 100</span><small>{formatNumberLocale(result.word_count)} {t("words")}</small></div><div className="essay-ai-summary"><p>{result.summary}</p><small>{result.disclaimer}</small></div><div className="essay-ai-rubric">{result.rubric?.map((item) => <article key={item.key}><div><b>{item.label}</b><span>{formatNumberLocale(item.score)}/10</span></div><div className="progress"><i style={{ width: `${Number(item.score) * 10}%` }} /></div><p>{item.feedback}</p></article>)}</div>{result.strengths?.length > 0 && <div className="essay-ai-list strengths"><h4>{t("Strengths")}</h4><ul>{result.strengths.map((item) => <li key={item}><CheckCircle2 size={14} /> {item}</li>)}</ul></div>}{result.issues?.length > 0 && <div className="essay-ai-issues"><h4>{t("Priority improvements")}</h4>{result.issues.map((item, index) => <article key={`${item.problem}-${index}`}>{item.excerpt && <blockquote>“{item.excerpt}”</blockquote>}<b>{item.problem}</b><p>{item.suggestion}</p></article>)}</div>}{result.next_steps?.length > 0 && <div className="essay-ai-list"><h4>{t("Next revision steps")}</h4><ol>{result.next_steps.map((item) => <li key={item}>{item}</li>)}</ol></div>}<small className="essay-ai-meta">{t("Reviewed draft version")} {review.essay_version} · {dateText(review.created_at)} · {review.mode === 'gateway' ? t("Naseeb AI") : t("Local guidance fallback")}</small></div>}</section>;
}

function EssayDetailModal({ essay, onClose, user = null }) {
  const canUseAI = ['student', 'counselor'].includes(user?.role);
  return <Modal title={essay.title} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><div><Badge>{essay.status}</Badge><span>{t("Version")} {essay.version} · {essay.university_name || t("General essay")}</span></div><GoogleDocsActions item={essay} /></div><section><span className="detail-label">{t("Essay prompt")}</span><p>{essay.prompt}</p></section>{essay.google_docs_preview_url ? <GoogleDocsPreview previewUrl={essay.google_docs_preview_url} title={essay.title} /> : <section><span className="detail-label">{t("Current draft")}</span><div className="essay-content-preview">{essay.content || t("No draft content has been added yet.")}</div></section>}{canUseAI && <EssayAIReviewPanel essay={essay} />}{essay.counselor_comment && <section className="counselor-feedback"><span className="detail-label">{t("Counselor feedback")}</span><p>{essay.counselor_comment}</p></section>}{essay.revisions?.length > 0 && <section><span className="detail-label">{t("Revision history")}</span><div className="revision-chips">{essay.revisions.map((revision) => <span key={revision.id}>{t("v")}{revision.version} · {label(revision.status)} · {dateText(revision.created_at)}</span>)}</div></section>}</div></Modal>;
}

function TaskSubmissionModal({ task, onClose }) {
  return <Modal title={tx`Task response · ${task.title}`} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><div><Badge>{task.status}</Badge><span>{task.submitted_at ? tx`Submitted ${dateTimeText(task.submitted_at)}` : t("Not submitted yet")}</span></div><div className="detail-actions">{task.submission_file && <a className="button quiet" href={task.submission_file} target="_blank" rel="noreferrer">{t("Open file")} <ExternalLink size={15} /></a>}{task.submission_url && <a className="button primary" href={task.submission_url} target="_blank" rel="noreferrer">{t("Open submission")} <ExternalLink size={15} /></a>}</div></div><section><span className="detail-label">{t("Assigned task")}</span><p>{task.description || t("No additional instructions.")}</p></section><section><span className="detail-label">{t("Student response")}</span><div className="essay-content-preview">{task.student_response || t("The student has not submitted a written response yet.")}</div></section><GoogleDocsPreview previewUrl={task.submission_preview_url} title={task.title} /></div></Modal>;
}

const formatFileSize = (bytes = 0) => {
  if (!bytes) return '—';
  if (bytes < 1024 * 1024) return `${formatNumberLocale(Math.max(1, Math.round(bytes / 1024)))} KB`;
  return `${formatNumberLocale(bytes / (1024 * 1024), { maximumFractionDigits: 1 })} MB`;
};

async function downloadDocumentFile(doc, notify) {
  try {
    const result = await api.downloadDocument(doc.id);
    const url = URL.createObjectURL(result.blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = doc.file_name || result.fileName || 'document';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
  } catch (error) {
    notify?.(error.message, 'error');
  }
}

async function downloadEvidenceFile(item, notify) {
  try {
    const result = await api.downloadEvidence(item.proof_resource, item.id);
    const url = URL.createObjectURL(result.blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = item.proof_file_name || result.fileName || 'evidence';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
  } catch (error) {
    notify?.(error.message, 'error');
  }
}

function DocumentFilePreview({ doc, evidenceResource = '' }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ loading: true, url: '', contentType: '', error: '' });
  useEffect(() => {
    let active = true;
    let objectUrl = '';
    setState({ loading: true, url: '', contentType: '', error: '' });
    const request = evidenceResource ? api.evidenceFile(evidenceResource, doc.id) : api.documentFile(doc.id);
    request.then((result) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(result.blob);
      setState({ loading: false, url: objectUrl, contentType: result.contentType, error: '' });
    }).catch((error) => {
      if (active) setState({ loading: false, url: '', contentType: '', error: error.message });
    });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [doc.id, evidenceResource, attempt]);

  if (state.loading) return <div className="secure-document-state" role="status"><div className="document-skeleton"><span /><span /><span /><span /></div><p>{t("Secure preview is loading…")}</p></div>;
  if (state.error) return <div className="secure-document-state error" role="alert"><ShieldAlert size={24} /><b>{t("Preview could not be loaded")}</b><p>{state.error}</p><button className="button quiet small" onClick={() => setAttempt((value) => value + 1)}><RefreshCw size={14} /> {t("Retry")}</button></div>;
  if (state.contentType.startsWith('image/')) return <div className="secure-document-preview image"><img src={state.url} alt={doc.title} /></div>;
  return <div className="secure-document-preview"><iframe src={state.url} title={tx`${doc.title} preview`} /></div>;
}

function EvidencePreviewModal({ item, onClose, notify }) {
  return <Modal title={tx`Evidence · ${visibilityItemTitle(item)}`} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><div><ShieldCheck size={16} /><span>{item.proof_file_name} · {formatFileSize(item.proof_file_size)}</span></div><button className="button quiet" onClick={() => downloadEvidenceFile(item, notify)}><Download size={15} /> {t("Download")}</button></div>{item.proof_file_previewable ? <DocumentFilePreview doc={{ ...item, title: visibilityItemTitle(item) }} evidenceResource={item.proof_resource} /> : <Empty text={t("This evidence file is stored securely. Download it to open it in the appropriate application.")} />}</div></Modal>;
}

function DocumentPreviewModal({ document: doc, onClose, notify }) {
  return <Modal title={doc.title} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><div><Badge>{doc.status}</Badge><span>{label(doc.document_type)}{doc.has_file && ` · ${doc.file_name || t("Document")} · ${formatFileSize(doc.file_size)}`}</span></div><div className="detail-actions">{doc.has_file && <button className="button quiet" onClick={() => downloadDocumentFile(doc, notify)}><Download size={15} /> {t("Download")}</button>}<GoogleDocsActions item={doc} /></div></div>{doc.counselor_comment && <section><span className="detail-label">{t("Counselor comment")}</span><p>{doc.counselor_comment}</p></section>}{doc.google_docs_preview_url ? <GoogleDocsPreview previewUrl={doc.google_docs_preview_url} title={doc.title} /> : doc.has_file && doc.file_previewable ? <DocumentFilePreview doc={doc} /> : doc.has_file ? <Empty text={t("This Office document is stored securely. Download it to open it in the appropriate application.")} /> : <Empty text={t("No file or Google Docs link has been added for preview.")} />}</div></Modal>;
}

function ProfileCard({ student }) {
  if (!student) return <Panel title={t("Profile")}><Empty text={t("Student profile not found.")} /></Panel>;
  return <Panel title={t("Profile overview")} className="profile-card"><div className="profile-identity"><span className="avatar large">{initials(fullName(student.user_detail))}</span><div><h3>{fullName(student.user_detail)}</h3><p>{student.user_detail?.email}</p></div></div><div className="detail-grid"><Detail label={t("School")} value={student.school_name} /><Detail label={t("Grade")} value={student.grade === 'gap' ? t("Gap year") : tx`Grade ${student.grade}`} /><Detail label={t("Counselor")} value={student.counselor_name} /><Detail label={t("Major")} value={student.target_major} /><Detail label={t("GPA")} value={student.gpa} /><Detail label={t("IELTS")} value={student.ielts_score} /><Detail label={t("SAT")} value={student.sat_score} /><Detail label={t("Countries")} value={student.target_countries} /><Detail label={t("Scholarship")} value={student.scholarship_needed ? t("Needed") : t("Not needed")} /></div></Panel>;
}

function Detail({ label: title, value }) {
  return <div className="detail"><span>{t(title)}</span><b>{value || '—'}</b></div>;
}

function StudentTable({ data, onView, onEdit, onDelete, onApproveLevel, readOnly = false, query = '' }) {
  const rows = data.students.filter((student) => fullName(student.user_detail).toLowerCase().includes(query.toLowerCase()));
  if (!rows.length) return <Empty text={t("No students found.")} />;
  const hasActions = Boolean(onView || onApproveLevel || !readOnly && (onEdit || onDelete));
  return <div className="table-wrap"><table><thead><tr><th>{t("Student")}</th><th>{t("School")}</th><th>{t("Target")}</th><th>{t("Scores")}</th><th>{t("XP / Level")}</th><th>{t("Task / Roadmap / Overall")}</th>{hasActions && <th />}</tr></thead><tbody>{rows.map((student) => <tr key={student.id} className={onView ? "clickable-row" : ''} onDoubleClick={() => onView?.(student)}><td><div className="person"><span className="avatar">{initials(fullName(student.user_detail))}</span><div><b>{fullName(student.user_detail)}</b><small>{student.user_detail?.email}</small>{student.is_at_risk && <span className="risk-note">{t("Needs attention")}</span>}</div></div></td><td>{student.school_name || '—'}</td><td className="student-target-cell"><b>{student.target_major || '—'}</b><small>{student.target_countries || '—'}</small></td><td>{t("GPA")} {student.gpa || '—'}<small>{t("IELTS")} {student.ielts_score || '—'} {t("• SAT")} {student.sat_score || '—'}</small></td><td><b>{t("Level")} {formatNumberLocale(student.level ?? 1)}</b><small>{formatNumberLocale(student.xp_total ?? 0)} {t("XP")}</small>{student.level_up_pending && <span className="risk-note">{t("Level")} {formatNumberLocale(student.eligible_level)} {t("pending")}</span>}</td><td><div className="student-progress-stack">{[['Task', student.task_progress_percent], ['Roadmap', student.roadmap_progress_percent], ['Overall', student.journey_progress_percent]].map(([title, value]) => <div key={title}><span>{t(title)}</span><div className="progress"><i style={{ width: `${value || 0}%` }} /></div><b>{formatPercentLocale(value || 0)}</b></div>)}</div></td>{hasActions && <td><div className="row-actions">{onApproveLevel && student.level_up_pending && <button className="button quiet small" onClick={() => onApproveLevel(student)}><CheckCircle2 size={15} /> {t("Approve level")}</button>}{onView && <button className="icon-button" onClick={() => onView(student)} title={t("Full profile")}><Eye size={16} /></button>}{!readOnly && onEdit && <button className="icon-button" onClick={() => onEdit(student)} title={t("Edit")}><Pencil size={16} /></button>}{!readOnly && onDelete && <button className="icon-button danger" onClick={() => onDelete(student)} title={t("Delete")}><Trash2 size={16} /></button>}</div></td>}</tr>)}</tbody></table></div>;
}

const STUDENT_RESOURCE_GROUPS = [
['Research', 'researches'], ['Projects', 'projects'], ['Internships', 'internships'],
['Activities', 'activities'], ['Honors', 'honors'], ['Achievements', 'achievements'],
['Recommendation letters', 'recommendations'], ['Meetings', 'bookings']];


function studentItems(data, resource, studentId) {
  return (data[resource] || []).filter((item) => Number(item.student) === Number(studentId));
}

function StudentOverviewList({ title, resource, items, data }) {
  const [viewingGoogleDoc, setViewingGoogleDoc] = useState(null);
  return <><Panel title={title}><div className="record-list">{items.map((item) => <RecordRow key={item.id} resource={resource} item={item} data={data} actions={<GoogleDocsActions item={item} onPreview={() => setViewingGoogleDoc(item)} />} />)}{!items.length && <Empty />}</div></Panel>{viewingGoogleDoc && <GoogleDocsRecordModal item={viewingGoogleDoc} onClose={() => setViewingGoogleDoc(null)} />}</>;
}

function StudentTaskList({ items, onView }) {
  return <Panel title={t("Assigned tasks & responses")}><div className="record-list">{items.map((task) => <Record key={task.id} title={task.title} meta={`${dateText(task.due_date)} · ${label(task.priority)}${task.submitted_at ? ` · Submitted ${dateText(task.submitted_at)}` : ''}`} description={task.student_response || task.description} badge={task.status} actions={<button className="button quiet small" onClick={() => onView(task)}><Eye size={14} /> {t("View response")}</button>} />)}{!items.length && <Empty text={t("No assigned tasks found.")} />}</div></Panel>;
}

function StudentCollegeList({ items }) {
  return <Panel title={t("College list")}><div className="record-list">{items.map((application) => <Record key={application.id} title={application.university_detail?.name || t("University")} meta={`${application.program} · ${label(application.tier)} · Deadline ${dateText(application.deadline)}`} description={application.notes} badge={application.status} actions={application.application_portal_url && <a className="button quiet small" href={application.application_portal_url} target="_blank" rel="noreferrer">{t("Application portal")} <ExternalLink size={14} /></a>} />)}{!items.length && <Empty text={t("The student has not added any universities to the college list yet.")} />}</div></Panel>;
}

function StudentEssayList({ items, onView }) {
  return <Panel title={t("Essays & Google Docs")}><div className="record-list">{items.map((essay) => <Record key={essay.id} title={essay.title} meta={`Version ${essay.version} · ${essay.university_name || 'General essay'}`} description={essay.counselor_comment || essay.prompt} badge={essay.status} actions={<><button className="button quiet small" onClick={() => onView(essay)}><Eye size={14} /> {t("Essay details")}</button><GoogleDocsActions item={essay} /></>} />)}{!items.length && <Empty text={t("No essays found.")} />}</div></Panel>;
}

function StudentDocumentList({ title, items, onPreview, notify }) {
  return <Panel title={title}><div className="record-list">{items.map((doc) => <Record key={doc.id} title={doc.title} meta={`${label(doc.document_type)}${doc.has_file ? ` · ${doc.file_name || 'File'} · ${formatFileSize(doc.file_size)}` : ''}`} description={doc.counselor_comment} badge={doc.status} actions={<>{(doc.google_docs_preview_url || doc.has_file && doc.file_previewable) && <button className="button quiet small" onClick={() => onPreview(doc)}><Eye size={14} /> {t("Preview")}</button>}{doc.has_file && <button className="button quiet small" onClick={() => downloadDocumentFile(doc, notify)}><Download size={14} /> {t("Download")}</button>}<GoogleDocsActions item={doc} /></>} />)}{!items.length && <Empty />}</div></Panel>;
}

function ParentInviteModal({ student, onClose, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    const payload = {
      student: student.id,
      email: values.get('email'),
      first_name: values.get('first_name'),
      last_name: values.get('last_name'),
      relationship: values.get('relationship'),
      can_view_applications: values.get('can_view_applications') === 'on',
      can_view_documents: values.get('can_view_documents') === 'on',
      can_view_meetings: values.get('can_view_meetings') === 'on'
    };
    if (values.get('password')) payload.password = values.get('password');
    try {
      const result = await api.inviteParent(payload);
      notify(tx`Parent invitation created. Login username: ${result.username}`);
      onClose();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={tx`Invite parent · ${fullName(student.user_detail)}`} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Parent first name")}><input name="first_name" /></Field><Field label={t("Parent last name")}><input name="last_name" /></Field><Field label={t("Parent email")}><input name="email" type="email" required /></Field><Field label={t("Relationship")}><select name="relationship" defaultValue="guardian"><option value="mother">{t("Mother")}</option><option value="father">{t("Father")}</option><option value="guardian">{t("Guardian")}</option><option value="other">{t("Other")}</option></select></Field><Field label={t("Temporary password")} hint={t("Required only when this email does not already have a parent account.")}><input name="password" type="password" minLength="12" autoComplete="new-password" /></Field><div className="parent-permission-fields form-wide"><span>{t("Shared read-only sections")}</span><CheckboxControl name="can_view_applications" defaultChecked>{t("Applications")}</CheckboxControl><CheckboxControl name="can_view_documents" defaultChecked>{t("Document status")}</CheckboxControl><CheckboxControl name="can_view_meetings" defaultChecked>{t("Meetings")}</CheckboxControl></div><p className="form-note form-wide"><Fingerprint size={16} /> {t("The invitation starts as pending. No child data is shown until the parent signs in and accepts it. Essays, messages, counselor notes, responses, files, and credentials are never included.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Creating invitation…") : t("Invite parent")}</button></div></form></Modal>;
}

function TemporaryCredentialModal({ account, onClose, notify }) {
  const [result, setResult] = useState(null);
  const [saving, setSaving] = useState(false);

  async function issue() {
    setSaving(true);
    try {
      setResult(await api.issueTemporaryCredential(account.id));
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function copyPassword() {
    if (!result?.temporary_password) return;
    try {
      await navigator.clipboard.writeText(result.temporary_password);
      notify(t('Copied'));
    } catch {
      notify(t('Copy password'), 'error');
    }
  }

  return <Modal title={`${t('Reset login')} · ${fullName(account)}`} onClose={onClose}>
    <div className="credential-modal">
      <div className="credential-account"><Fingerprint size={21} /><div><b>{account.username}</b><small>{account.email || label(account.role)}</small></div></div>
      {!result ? <>
        <p>{t('This revokes existing sessions and any previous temporary password.')}</p>
        <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t('Cancel')}</button><button type="button" className="button primary" onClick={issue} disabled={saving} aria-busy={saving}><Fingerprint size={16} />{t('Generate temporary password')}</button></div>
      </> : <>
        <p className="credential-delivery"><ShieldAlert size={17} />{t('The password is shown once. Send it through an approved secure channel.')}</p>
        <div className="credential-secret"><span>{t('Generated password')}</span><code>{result.temporary_password}</code><button type="button" className="button quiet" onClick={copyPassword}><ClipboardCheck size={16} />{t('Copy password')}</button></div>
        <small>{t('expires')}: {dateTimeText(result.credential?.expires_at)}</small>
        <div className="form-actions"><button type="button" className="button primary" onClick={onClose}>{t('Close')}</button></div>
      </>}
    </div>
  </Modal>;
}

function StudentOverview({ student, data, onBack, user, notify }) {
  const [selectedTask, setSelectedTask] = useState(null);
  const [selectedEssay, setSelectedEssay] = useState(null);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [parentInviteOpen, setParentInviteOpen] = useState(false);
  const [credentialOpen, setCredentialOpen] = useState(false);
  if (!student) return <Empty text={t("Student profile not found.")} />;
  const documents = studentItems(data, 'documents', student.id);
  const certificates = documents.filter((item) => item.document_type === 'certificate');
  const regularDocuments = documents.filter((item) => item.document_type !== 'certificate');
  const tasks = studentItems(data, 'tasks', student.id);
  const applications = studentItems(data, 'applications', student.id);
  const essays = studentItems(data, 'essays', student.id);

  return <div className="section-stack student-overview">
    <section className="student-overview-hero">
      <div className="student-overview-title">{onBack && <button className="button quiet student-overview-back" onClick={onBack}>{t("← Students")}</button>}<div className="profile-identity"><span className="avatar large">{initials(fullName(student.user_detail))}</span><div><span className="eyebrow">{t("STUDENT 360° PROFILE")}</span><h2>{fullName(student.user_detail)}</h2><p>{student.user_detail?.email} • {student.school_name || t("No school assigned")}</p></div></div></div>
      <div className="student-overview-actions">{['admin', 'counselor', 'organization'].includes(user?.role) && <button className="button quiet" onClick={() => setCredentialOpen(true)}><Fingerprint size={16} /> {t('Reset login')}</button>}{['admin', 'counselor'].includes(user?.role) && <button className="button quiet" onClick={() => setParentInviteOpen(true)}><UsersRound size={16} /> {t("Invite parent")}</button>}</div>
      <div className="overview-progress"><strong>{formatPercentLocale(student.progress_percent || 0)}</strong><span>{t("Application readiness")}</span><div className="progress wide"><span style={{ width: `${student.progress_percent || 0}%` }} /></div></div>
    </section>
    <div className="stat-grid"><Stat label={t("Level")} value={student.level ?? 1} note={student.level_up_pending ? tx`Level ${student.eligible_level} approval pending` : t("Teacher approved")} /><Stat label={t("XP")} value={student.xp_total ?? 0} note={tx`Next: ${student.next_level_xp ?? 0} XP`} /><Stat label={t("Assigned tasks")} value={tasks.length} /><Stat label={t("Applications")} value={applications.length} /></div>
    <LevelProgress student={student} />
    <div className="split-grid wide-left"><ProfileCard student={student} /><Panel title={t("Contact & planning")}><div className="detail-grid"><Detail label={t("Phone")} value={student.user_detail?.phone} /><Detail label={t("Parent contact")} value={student.parent_contact} /><Detail label={t("Budget USD")} value={student.budget_usd} /><Detail label={t("Target countries")} value={student.target_countries} /><Detail label={t("Scholarship")} value={student.scholarship_needed ? "Needed" : "Not needed"} /><Detail label={t("Counselor")} value={student.counselor_name} /></div>{student.notes && <div className="student-notes"><span>{t("Internal notes")}</span><p>{student.notes}</p></div>}</Panel></div>
    <div className="overview-grid student-workspace-grid"><StudentTaskList items={tasks} onView={setSelectedTask} /><StudentCollegeList items={applications} /><StudentEssayList items={essays} onView={setSelectedEssay} /><StudentDocumentList title={t("Documents")} items={regularDocuments} onPreview={setSelectedDocument} notify={notify} /></div>
    <div className="overview-grid">
      {STUDENT_RESOURCE_GROUPS.map(([title, resource]) => <StudentOverviewList key={resource} title={title} resource={resource} items={studentItems(data, resource, student.id)} data={data} />)}
      <StudentDocumentList title={t("Certificates")} items={certificates} onPreview={setSelectedDocument} notify={notify} />
    </div>
    {selectedTask && <TaskSubmissionModal task={selectedTask} onClose={() => setSelectedTask(null)} />}
    {selectedEssay && <EssayDetailModal essay={selectedEssay} onClose={() => setSelectedEssay(null)} />}
    {selectedDocument && <DocumentPreviewModal document={selectedDocument} onClose={() => setSelectedDocument(null)} notify={notify} />}
    {parentInviteOpen && <ParentInviteModal student={student} onClose={() => setParentInviteOpen(false)} notify={notify} />}
    {credentialOpen && <TemporaryCredentialModal account={student.user_detail} onClose={() => setCredentialOpen(false)} notify={notify} />}
  </div>;
}

function visibilityItemTitle(item) {
  return item.title || item.name || item.organization || item.university_name || item.recommender_name || item.topic || t("Record");
}

const VISIBILITY_POLICY_LABELS = {
  identity_and_contact: 'Identity & contact', academic_profile: 'Academic profile', progress_and_xp: 'Progress & XP',
  task_metadata_and_status: 'Task metadata & status', roadmap_metadata_and_status: 'Roadmap metadata & status',
  application_metadata_and_status: 'Application metadata & status', document_metadata_and_secure_file: 'Document metadata & secure file',
  essay_metadata_and_status: 'Essay metadata & status', recommendation_metadata_and_status: 'Recommendation metadata & status',
  portfolio_and_activities: 'Portfolio & activities', meeting_schedule_and_status: 'Meeting schedule & status', program_usage: 'Program usage',
  private_messages: 'Private messages', message_moderation_reports: 'Moderation reports', credentials_and_password_state: 'Credentials & password state',
  internal_counselor_notes: 'Internal counselor notes', meeting_notes: 'Meeting notes', application_portal_credentials: 'Application portal credentials',
  essay_draft_content_and_feedback: 'Essay draft content & feedback', recommendation_files_and_private_notes: 'Recommendation files & private notes',
  task_submission_content: 'Task submission content', roadmap_reflections: 'Roadmap reflections', screen_time_detail: 'Screen time detail', support_tickets: 'Support tickets',
};

function visibilityPolicyLabel(item) {
  return t(VISIBILITY_POLICY_LABELS[item] || item.replaceAll('_', ' '));
}

function VisibilitySection({ title, items = [], onDocument, onEvidence }) {
  return <Panel title={title}><div className="visibility-records">{items.slice(0, 8).map((item) => <article key={`${item.proof_resource || 'record'}-${item.id}`}><div><b>{visibilityItemTitle(item)}</b><small>{label(item.status || item.category || item.document_type || item.activity_type || item.level || '')}</small></div><div className="panel-actions">{onDocument && (item.has_file || item.google_docs_preview_url) && <button className="button quiet" onClick={() => onDocument(item)}><Eye size={15} /> {t("Preview")}</button>}{onEvidence && item.has_proof_file && <button className="button quiet" onClick={() => onEvidence(item)}><ShieldCheck size={15} /> {t("Evidence")}</button>}</div></article>)}{!items.length && <Empty />}</div></Panel>;
}

function SchoolStudent360({ visibility, student, loading, error, onBack, user, notify }) {
  const [credentialOpen, setCredentialOpen] = useState(false);
  const [document, setDocument] = useState(null);
  const [evidence, setEvidence] = useState(null);
  if (loading) return <PageSkeleton />;
  if (error) return <div className="section-stack"><button className="button quiet back-button" onClick={onBack}>{t("← Students")}</button><div className="alert error">{error}</div></div>;
  if (!visibility) return <Empty text={t("Student visibility data is unavailable.")} />;
  const profile = visibility.student;
  const identity = profile.user || student.user_detail;
  const included = visibility.policy?.included || [];
  const excluded = visibility.policy?.excluded || [];
  const portfolio = [...visibility.achievements, ...visibility.researches, ...visibility.projects, ...visibility.internships, ...visibility.activities, ...visibility.honors];
  return <div className="section-stack school-student-360"><section className="student-overview-hero"><div className="student-overview-title"><button className="button quiet" onClick={onBack}>{t("← Students")}</button><div className="profile-identity"><span className="avatar large">{initials(fullName(identity))}</span><div><span className="eyebrow">{t("PRIVACY-SAFE STUDENT 360")}</span><h2>{fullName(identity)}</h2><p>{identity.email} • {profile.school_name}</p></div></div><button className="button quiet" onClick={() => setCredentialOpen(true)}><Fingerprint size={16} /> {t("Reset login")}</button></div><div className="overview-progress"><strong>{formatPercentLocale(profile.journey_progress_percent || 0)}</strong><span>{t("Application journey")}</span><div className="progress wide"><span style={{ width: `${profile.journey_progress_percent || 0}%` }} /></div></div></section><section className="visibility-policy"><div><ShieldCheck size={22} /><div><span className="eyebrow">{t("DATA VISIBILITY POLICY")}</span><h3>{visibility.policy.access_scope === 'global' ? t("Global admin scope") : t("Own-school scope")}</h3><p>{t("Admissions data is read-only here. Sensitive communication, credentials, and internal notes require a separate authorized workflow.")}</p></div></div><Badge tone="success">{t("Read only")}</Badge><details><summary>{t("What is visible")}</summary><div className="visibility-tags included">{included.map((item) => <span key={item}>{visibilityPolicyLabel(item)}</span>)}</div></details><details><summary>{t("What is protected")}</summary><div className="visibility-tags protected">{excluded.map((item) => <span key={item}>{visibilityPolicyLabel(item)}</span>)}</div></details></section><div className="stat-grid"><Stat label={t("Level")} value={profile.level} note={tx`${profile.xp_total} XP`} /><Stat label={t("Tasks")} value={visibility.tasks.length} note={formatPercentLocale(profile.task_progress_percent || 0)} /><Stat label={t("Roadmap")} value={visibility.roadmap.length} note={formatPercentLocale(profile.roadmap_progress_percent || 0)} /><Stat label={t("Applications")} value={visibility.applications.length} note={t("Metadata and status")}/></div><div className="split-grid"><Panel title={t("Academic & planning")}><div className="detail-grid"><Detail label={t("Grade")} value={profile.grade} /><Detail label={t("GPA")} value={profile.gpa} /><Detail label={t("IELTS")} value={profile.ielts_score} /><Detail label={t("SAT")} value={profile.sat_score} /><Detail label={t("Target major")} value={profile.target_major} /><Detail label={t("Target countries")} value={profile.target_countries} /><Detail label={t("Parent contact")} value={profile.parent_contact} /><Detail label={t("Counselor")} value={profile.counselor_name} /></div></Panel><VisibilitySection title={t("Meetings")} items={visibility.meetings} /></div><div className="overview-grid"><VisibilitySection title={t("Tasks")} items={visibility.tasks} /><VisibilitySection title={t("Roadmap")} items={visibility.roadmap} /><VisibilitySection title={t("Applications")} items={visibility.applications} /><VisibilitySection title={t("Documents")} items={visibility.documents} onDocument={setDocument} /><VisibilitySection title={t("Essays")} items={visibility.essays} /><VisibilitySection title={t("Recommendations")} items={visibility.recommendations} /><VisibilitySection title={t("Portfolio & activities")} items={portfolio} onEvidence={setEvidence} /><VisibilitySection title={t("Program Usage")} items={visibility.program_usage} /></div>{credentialOpen && <TemporaryCredentialModal account={{ ...identity, role: 'student' }} onClose={() => setCredentialOpen(false)} notify={notify} />}{document && <DocumentPreviewModal document={document} onClose={() => setDocument(null)} notify={notify} />}{evidence && <EvidencePreviewModal item={evidence} onClose={() => setEvidence(null)} notify={notify} />}</div>;
}

function StudentAssignmentModal({ user, data, onClose, onSaved, notify }) {
  const admin = user.role === 'admin';
  const counselors = (data.accounts || []).filter((account) => account.role === 'counselor' && account.is_active && account.school);
  const [counselorId, setCounselorId] = useState(admin ? '' : String(user.id));
  const [candidates, setCandidates] = useState([]);
  const [selected, setSelected] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(!admin);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (admin && !counselorId) {
      setCandidates([]);
      setSelected([]);
      setLoading(false);
      return () => {cancelled = true;};
    }
    setLoading(true);
    setError('');
    setSelected([]);
    api.studentAssignmentCandidates(admin ? counselorId : null).
    then((items) => {if (!cancelled) setCandidates(items || []);}).
    catch((requestError) => {if (!cancelled) setError(requestError.message);}).
    finally(() => {if (!cancelled) setLoading(false);});
    return () => {cancelled = true;};
  }, [admin, counselorId]);

  const visible = candidates.filter((student) => {
    const haystack = `${fullName(student.user_detail)} ${student.user_detail?.email || ''}`.toLowerCase();
    return haystack.includes(search.trim().toLowerCase());
  });
  const target = admin ? counselors.find((account) => String(account.id) === String(counselorId)) : user;
  const targetRoleLabel = label(target?.role || user.role);
  const toggle = (studentId) => setSelected((current) => current.includes(studentId) ? current.filter((id) => id !== studentId) : [...current, studentId]);

  async function submit(event) {
    event.preventDefault();
    if (!selected.length) {setError(t("Select at least one student."));return;}
    setSaving(true);
    setError('');
    try {
      await api.assignCounselorStudents({ counselor: Number(counselorId), students: selected });
      notify(t("Students connected."));
      onSaved();
    } catch (requestError) {setError(requestError.message);} finally {setSaving(false);}
  }

  return <Modal title={admin ? t("Assign counselor") : t("Connect students")} onClose={onClose}><form className="student-assignment-form" onSubmit={submit}>
    {admin && <Field label={t("Counselor")}><select value={counselorId} onChange={(event) => setCounselorId(event.target.value)} required><option value="">{t("Select a counselor")}</option>{counselors.map((account) => <option key={account.id} value={account.id}>{fullName(account)} · {account.school_name}</option>)}</select></Field>}
    <p className="form-note form-wide"><ShieldCheck size={16} />{admin ? t("Admins can reassign students only to an active counselor from the same school.") : t("You can connect only unassigned students from your own school.")}</p>
    {target && <div className="assignment-target form-wide"><span className="avatar">{initials(fullName(target))}</span><div><b>{fullName(target)}</b><small>{target.school_name || targetRoleLabel}</small></div><Badge>{`${formatNumberLocale(candidates.length)} ${t("available")}`}</Badge></div>}
    {(counselorId || !admin) && <fieldset className="member-picker assignment-picker form-wide"><legend>{formatNumberLocale(selected.length)} {t("selected")}</legend><div className="assignment-tools"><label className="member-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("Search students")} /></label><div className="audience-shortcuts"><button type="button" onClick={() => setSelected(visible.map((student) => student.id))}>{t("Select all")}</button><button type="button" onClick={() => setSelected([])}>{t("Clear")}</button></div></div><div className="assignment-candidate-list">{visible.map((student) => <CheckboxControl key={student.id} checked={selected.includes(student.id)} onChange={() => toggle(student.id)}><span className="assignment-candidate-copy"><b>{fullName(student.user_detail)}</b><small>{student.user_detail?.email || '—'} · {t("Grade")} {student.grade}</small></span><Badge>{student.counselor_name ? t("Reassign") : t("Unassigned")}</Badge></CheckboxControl>)}</div>{loading && <small>{t("Loading students…")}</small>}{!loading && !visible.length && <small>{admin && !counselorId ? t("Select a counselor first.") : t("No students are available for assignment in this school.")}</small>}</fieldset>}
    {error && <div className="alert error form-wide">{error}</div>}
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || loading || !selected.length} aria-busy={saving}>{saving ? t("Connecting…") : t("Connect selected students")}</button></div>
  </form></Modal>;
}

function StudentsPage({ user, data, query, reload, notify }) {
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(false);
  const [assignmentOpen, setAssignmentOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [visibility, setVisibility] = useState(null);
  const [visibilityLoading, setVisibilityLoading] = useState(false);
  const [visibilityError, setVisibilityError] = useState('');
  const { confirm, dialog } = useActionDialog();

  async function openStudent(student) {
    setSelected(student);
    setVisibility(null);
    setVisibilityError('');
    if (!['admin', 'organization'].includes(user.role)) return;
    setVisibilityLoading(true);
    try {setVisibility(await api.studentDataVisibility(student.id));} catch (error) {setVisibilityError(error.message);} finally {setVisibilityLoading(false);}
  }

  async function remove(student) {
    if (!await confirm({ title: t("Delete student profile"), description: tx`Delete ${fullName(student.user_detail)}’s profile? This action cannot be undone.`, confirmLabel: t("Delete profile"), tone: 'danger' })) return;
    try {await api.remove('students', student.id);notify(t("Student deleted."));reload();} catch (err) {notify(err.message, 'error');}
  }

  async function approveLevel(student) {
    try {
      const result = await api.approveStudentLevel(student.id);
      notify(tx`Level ${result.level} approved.`);
      reload();
    } catch (err) {notify(err.message, 'error');}
  }

  if (selected && ['admin', 'organization'].includes(user.role)) return <SchoolStudent360 visibility={visibility} student={selected} loading={visibilityLoading} error={visibilityError} onBack={() => setSelected(null)} user={user} notify={notify} />;
  if (selected) return <StudentOverview student={data.students.find((item) => item.id === selected.id) || selected} data={data} onBack={() => setSelected(null)} user={user} notify={notify} />;

  const actions = user.role !== 'teacher' && <div className="panel-actions">{['admin', 'counselor'].includes(user.role) && <button className="button quiet" onClick={() => setAssignmentOpen(true)}><UsersRound size={17} /> {user.role === 'admin' ? t("Assign counselor") : t("Connect students")}</button>}<button className="button primary" onClick={() => {setEditing(null);setOpen(true);}}><Plus size={17} /> {t("Add student")}</button></div>;
  return <>
    <Panel title={t("Students")} action={actions}><StudentTable data={data} query={query} onView={openStudent} onApproveLevel={isTaskManager(user) ? approveLevel : undefined} onEdit={user.role !== 'teacher' ? (student) => {setEditing(student);setOpen(true);} : undefined} onDelete={user.role !== 'teacher' ? remove : undefined} /></Panel>
    {open && <StudentForm user={user} data={data} student={editing} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}
    {assignmentOpen && <StudentAssignmentModal user={user} data={data} onClose={() => setAssignmentOpen(false)} onSaved={() => {setAssignmentOpen(false);reload();}} notify={notify} />}
    {dialog}
  </>;
}

function StudentForm({ user, data, student, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [form, setForm] = useState({
    name: fullName(student?.user_detail) === 'User' ? '' : fullName(student?.user_detail), email: student?.user_detail?.email || '',
    password: '',
    grade: student?.grade || '11', target_major: student?.target_major || '', target_countries: student?.target_countries || '',
    gpa: student?.gpa || '', ielts_score: student?.ielts_score || '', sat_score: student?.sat_score || '',
    budget_usd: student?.budget_usd || '', parent_contact: student?.parent_contact || '', notes: student?.notes || '',
    scholarship_needed: student?.scholarship_needed ?? true, school: student?.school || user.school || ''
  });
  function update(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
    if (fieldErrors[name]) setFieldErrors((current) => ({ ...current, [name]: '' }));
  }
  async function submit(event) {
    event.preventDefault();
    const targetCountries = normalizeCountries(form.target_countries);
    if (!targetCountries) {
      setFieldErrors({ target_countries: 'Add at least one target country.' });
      return;
    }
    if (targetCountries.length > TARGET_COUNTRIES_MAX_LENGTH) {
      setFieldErrors({ target_countries: `Use ${TARGET_COUNTRIES_MAX_LENGTH} characters or fewer.` });
      return;
    }
    setForm((current) => ({ ...current, target_countries: targetCountries }));
    setFieldErrors({});
    setSaving(true);
    try {
      const profilePayload = { grade: form.grade, target_major: form.target_major, target_countries: targetCountries, gpa: form.gpa || null, ielts_score: form.ielts_score || null, sat_score: form.sat_score || null, budget_usd: form.budget_usd || null, parent_contact: form.parent_contact, scholarship_needed: form.scholarship_needed, school: Number(form.school) };
      const createPayload = { name: form.name, email: form.email, password: form.password, grade: form.grade, major: form.target_major, countries: targetCountries, gpa: form.gpa, ielts: form.ielts_score, sat: form.sat_score, budget_usd: form.budget_usd, parent_contact: form.parent_contact, scholarship_needed: form.scholarship_needed, school: form.school };
      if (user.role !== 'organization') {
        profilePayload.notes = form.notes;
        createPayload.notes = form.notes;
      }
      if (student) await api.update('students', student.id, profilePayload);else
      await api.quickCreateStudent(createPayload);
      notify(student ? t("Student updated.") : t("Student created."));onSaved();
    } catch (err) {
      const countryErrors = err.details?.target_countries || err.details?.countries;
      if (countryErrors) setFieldErrors({ target_countries: Array.isArray(countryErrors) ? countryErrors.join(' ') : String(countryErrors) });else
      notify(err.message, 'error');
    } finally {setSaving(false);}
  }
  return <Modal title={student ? t("Edit student") : t("Add student")} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <Field label={t("Full name")}><input value={form.name} onChange={(e) => update('name', e.target.value)} disabled={Boolean(student)} required /></Field>
    <Field label={t("Email")}><input type="email" value={form.email} onChange={(e) => update('email', e.target.value)} disabled={Boolean(student)} /></Field>
    {!student && <Field label={t('Temporary password')} hint={t('The password is shown once. Send it through an approved secure channel.')}><input type="password" value={form.password} onChange={(e) => update('password', e.target.value)} minLength="12" autoComplete="new-password" required /></Field>}
    <Field label={t("Grade")}><select value={form.grade} onChange={(e) => update('grade', e.target.value)}>{['8', '9', '10', '11', 'gap'].map((item) => <option key={item} value={item}>{item === 'gap' ? t("Gap year") : tx`Grade ${item}`}</option>)}</select></Field>
    {isCounselor(user) && <Field label={t("School")}><select value={form.school} onChange={(e) => update('school', e.target.value)} required><option value="">{t("Select school")}</option>{data.schools.map((school) => <option key={school.id} value={school.id}>{school.name}</option>)}</select></Field>}
    <Field label={t("Target major")}><input value={form.target_major} onChange={(e) => update('target_major', e.target.value)} required /></Field>
    <Field label={t("Target countries")} error={fieldErrors.target_countries} hint={tx`${form.target_countries.length}/${TARGET_COUNTRIES_MAX_LENGTH} characters · separate countries with commas`}><input value={form.target_countries} onChange={(e) => update('target_countries', e.target.value)} onBlur={() => update('target_countries', normalizeCountries(form.target_countries))} maxLength={TARGET_COUNTRIES_MAX_LENGTH} aria-invalid={Boolean(fieldErrors.target_countries)} required /></Field>
    <Field label={t("GPA")}><input type="number" step=".01" value={form.gpa} onChange={(e) => update('gpa', e.target.value)} /></Field>
    <Field label={t("IELTS")}><input type="number" step=".5" value={form.ielts_score} onChange={(e) => update('ielts_score', e.target.value)} /></Field>
    <Field label={t("SAT")}><input type="number" value={form.sat_score} onChange={(e) => update('sat_score', e.target.value)} /></Field>
    <Field label={t("Annual budget USD")}><input type="number" value={form.budget_usd} onChange={(e) => update('budget_usd', e.target.value)} /></Field>
    <Field label={t("Parent contact")}><input value={form.parent_contact} onChange={(e) => update('parent_contact', e.target.value)} /></Field>
    {user.role !== 'organization' && <Field label={t("Notes")}><textarea value={form.notes} onChange={(e) => update('notes', e.target.value)} /></Field>}
    <CheckboxControl className="form-wide" checked={form.scholarship_needed} onChange={(e) => update('scholarship_needed', e.target.checked)}>{t("Scholarship needed")}</CheckboxControl>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : t("Save student")}</button></div>
  </form></Modal>;
}

function SchoolsPage({ user, data, reload, notify }) {
  const [open, setOpen] = useState('');
  const [editingSchool, setEditingSchool] = useState(null);
  const [transferTarget, setTransferTarget] = useState(null);
  const [credentialTarget, setCredentialTarget] = useState(null);
  const { confirm, dialog } = useActionDialog();
  async function remove(school) {
    if (!await confirm({ title: t("Deactivate school"), description: tx`Deactivate ${school.name}? Organization access will stop until the school is reactivated.`, confirmLabel: t("Deactivate"), tone: 'danger' })) return;
    try {await api.remove('schools', school.id);notify(t("School deactivated."));reload();} catch (err) {notify(err.message, 'error');}
  }
  const isAdmin = user.role === 'admin';
  const actions = isAdmin && <div className="panel-actions"><button className="button quiet" onClick={() => setOpen('counselor')}><UserRound size={17} /> {t("Individual counselor")}</button><button className="button primary" onClick={() => setOpen('school')}><Plus size={17} /> {t("Add school")}</button></div>;
  return <>
    <Panel title={t("Schools & counselor workspaces")} action={actions}><div className="card-grid">{data.schools.map((school) => <article className={`school-card ${school.workspace_type === 'individual' ? 'individual' : ''}`} key={school.id}>
      <div className="school-number">{school.workspace_type === 'individual' ? <UserRound size={22} /> : String(school.id).padStart(2, '0')}</div>
      <div><div className="school-card-title"><h3>{school.name}</h3><Badge>{school.workspace_type === 'individual' ? t("Individual workspace") : t("School")}</Badge></div><p>{school.workspace_type === 'individual' ? tx`Owner: ${school.owner_counselor_name || t("Not assigned")}` : `${school.contact_email || t("No email")} • ${school.contact_phone || t("No phone")}`}</p><span>{school.students_count || 0} {t("students")}{school.organization_account_username ? ` · ${school.organization_account_username}` : ''}</span></div>
      {isAdmin && <div className="school-card-actions">
        {school.workspace_type !== 'individual' && <button className="icon-button" onClick={() => setEditingSchool(school)} aria-label={tx`Edit ${school.name}`}><Pencil size={16} /></button>}
        {school.workspace_type === 'individual' && school.owner_counselor && <button className="icon-button" onClick={() => setTransferTarget(school)} aria-label={tx`Transfer ${school.owner_counselor_name}`} title={t("Transfer to school")}><Building2 size={16} /></button>}
        {school.organization_account_id && <button className="icon-button" onClick={() => setCredentialTarget({ id: school.organization_account_id, username: school.organization_account_username, full_name: school.name, role: 'organization' })} aria-label={`${t('Reset login')} · ${school.name}`} title={t('Reset login')}><Fingerprint size={16} /></button>}
        {school.workspace_type !== 'individual' && school.is_active && <button className="icon-button danger" onClick={() => remove(school)} aria-label={tx`Deactivate ${school.name}`}><Trash2 size={16} /></button>}
      </div>}
    </article>)}{!data.schools.length && <Empty />}</div></Panel>
    {open === 'school' && <SchoolForm onClose={() => setOpen('')} onSaved={() => {setOpen('');reload();}} notify={notify} />}
    {editingSchool && <SchoolForm school={editingSchool} onClose={() => setEditingSchool(null)} onSaved={() => {setEditingSchool(null);reload();}} notify={notify} />}
    {open === 'counselor' && <IndividualCounselorForm onClose={() => setOpen('')} onSaved={() => {setOpen('');reload();}} notify={notify} />}
    {transferTarget && <CounselorTransferForm workspace={transferTarget} schools={data.schools.filter((school) => school.workspace_type === 'school' && school.is_active)} onClose={() => setTransferTarget(null)} onSaved={() => {setTransferTarget(null);reload();}} notify={notify} />}
    {credentialTarget && <TemporaryCredentialModal account={credentialTarget} onClose={() => setCredentialTarget(null)} notify={notify} />}
    {dialog}
  </>;
}

function CounselorTransferForm({ workspace, schools, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    try {
      const school = Number(new FormData(event.currentTarget).get('school'));
      await api.transferCounselor(workspace.owner_counselor, school);
      notify(t("Counselor transferred. The private workspace is now inactive."));
      onSaved();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={tx`Transfer ${workspace.owner_counselor_name}`} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Organization school")}><select name="school" required defaultValue=""><option value="" disabled>{t("Select a school")}</option>{schools.map((school) => <option key={school.id} value={school.id}>{school.name}</option>)}</select></Field><p className="form-note form-wide"><ShieldAlert size={16} /> {t("Every student assigned to this counselor must already belong to the selected school. The transfer is blocked otherwise.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || !schools.length}>{saving ? t("Transferring…") : t("Transfer counselor")}</button></div></form></Modal>;
}

function IndividualCounselorForm({ onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.createIndividualCounselor(Object.fromEntries(values.entries()));
      notify(t("Individual counselor and private workspace created."));
      onSaved();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={t("Add individual counselor")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("First name")}><input name="first_name" required /></Field><Field label={t("Last name")}><input name="last_name" /></Field><Field label={t("Username")}><input name="username" autoComplete="off" required /></Field><Field label={t("Email")}><input name="email" type="email" required /></Field><Field label={t("Phone")}><input name="phone" /></Field><Field label={t("Position")}><input name="position" placeholder={t("Independent counselor")} /></Field><Field label={t("Temporary password")}><input name="password" type="password" minLength="8" autoComplete="new-password" required /></Field><p className="form-note form-wide"><ShieldCheck size={16} /> {t("A clearly labeled private workspace is created automatically. An admin can later transfer this counselor to an organization school after their students are reassigned.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Creating…") : t("Create counselor")}</button></div></form></Modal>;
}

function SchoolForm({ school = null, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);
    try {
      const payload = { name: values.get('name'), code: values.get('code'), contact_email: values.get('contact_email'), contact_phone: values.get('contact_phone'), is_active: true };
      if (school) {await api.update('schools', school.id, payload);notify(t("School updated."));} else {const createdSchool = await api.create('schools', payload);await api.createSchoolAccount(createdSchool.id, { username: values.get('username'), email: values.get('account_email'), password: values.get('password'), first_name: values.get('name'), last_name: 'Organization' });notify(t("School and organization account created."));}onSaved();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={school ? t("Edit school") : t("Add organization school")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("School name")}><input name="name" defaultValue={school?.name || ''} required /></Field><Field label={t("Unique code")}><input name="code" defaultValue={school?.code || ''} required /></Field><Field label={t("Contact email")}><input name="contact_email" type="email" defaultValue={school?.contact_email || ''} /></Field><Field label={t("Contact phone")}><input name="contact_phone" defaultValue={school?.contact_phone || ''} /></Field>{!school && <><Field label={t("Login username")}><input name="username" required /></Field><Field label={t("Login email")}><input name="account_email" type="email" required /></Field><Field label={t('Temporary password')} hint={t('The password is shown once. Send it through an approved secure channel.')}><input name="password" type="password" minLength="12" autoComplete="new-password" required /></Field></>}<div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t('Cancel')}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : school ? t("Save") : t("Create school")}</button></div></form></Modal>;
}

function ResourceSection({ title, resource, data, user, query, reload, notify, canCreate = true, defaultStudentId = null }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [viewingEssay, setViewingEssay] = useState(null);
  const [viewingTask, setViewingTask] = useState(null);
  const [viewingGoogleDoc, setViewingGoogleDoc] = useState(null);
  const [viewingEvidence, setViewingEvidence] = useState(null);
  const { confirm, dialog } = useActionDialog();
  const records = data[resource] || [];
  const filtered = records.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  const staffControlled = resource === 'tasks';
  const allowCreate = canCreate && (staffControlled ? isTaskManager(user) || user.role === 'student' : isCounselor(user) || user.role === 'student');
  const allowEdit = staffControlled ? isTaskManager(user) || user.role === 'student' : allowCreate;

  async function approve(item) {
    try {
      const result = await api.approveTask(item.id);
      notify(result.xp_awarded ? tx`Task approved. +${result.xp_awarded} XP` : t("Self-task approved. No XP awarded."));
      reload();
    } catch (err) {notify(err.message, 'error');}
  }

  async function remove(item) {
    if (!await confirm({ title: t("Delete record"), description: t("Delete this record? This action cannot be undone."), confirmLabel: t("Delete"), tone: 'danger' })) return;
    try {await api.remove(resource, item.id);notify(t("Record deleted."));reload();} catch (err) {notify(err.message, 'error');}
  }
  return <>{dialog}<Panel title={title} action={allowCreate && <button className="button quiet" onClick={() => {setEditing(null);setOpen(true);}}><Plus size={16} /> {staffControlled ? user.role === 'student' ? t("Create self-task") : t("Assign task") : t("Add")}</button>}><div className="record-list">{filtered.map((item) => {
          const lockedAfterApproval = item.status === 'approved';
          const allowDelete = !staffControlled ? allowCreate : isTaskManager(user) || user.role === 'student' && item.is_self_assigned;
          return <RecordRow key={item.id} resource={resource} item={item} data={data} actions={<>{resource === 'tasks' && <button className="button quiet small" onClick={() => setViewingTask(item)}><Eye size={14} /> {t("Response")}</button>}{resource === 'essays' && <button className="button quiet small" onClick={() => setViewingEssay(item)}><Eye size={14} /> {t("Details")}</button>}{item.has_proof_file && <><button className="button quiet small" onClick={() => setViewingEvidence(item)}><Eye size={14} /> {t("Evidence")}</button><button className="button quiet small" onClick={() => downloadEvidenceFile(item, notify)}><Download size={14} /> {t("Download")}</button></>}{resource !== 'essays' && <GoogleDocsActions item={item} onPreview={() => setViewingGoogleDoc(item)} />}{isTaskManager(user) && staffControlled && item.status === 'submitted' && <button className="button quiet small" onClick={() => approve(item)}><CheckCircle2 size={15} /> {t("Approve")}</button>}{allowEdit && !lockedAfterApproval && <button className="button quiet small" onClick={() => {setEditing(item);setOpen(true);}} aria-label={tx`Edit ${title}`}><Pencil size={15} /> {t("Edit")}</button>}{allowDelete && <button className="button quiet small danger" onClick={() => remove(item)} aria-label={tx`Delete ${title}`}><Trash2 size={15} /> {t("Delete")}</button>}</>} />;
        })}{!filtered.length && <Empty />}</div></Panel>{open && <ResourceForm resource={resource} item={editing} data={data} user={user} defaultStudentId={defaultStudentId} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}{viewingEssay && <EssayDetailModal essay={viewingEssay} user={user} onClose={() => setViewingEssay(null)} />}{viewingTask && <TaskSubmissionModal task={viewingTask} onClose={() => setViewingTask(null)} />}{viewingGoogleDoc && <GoogleDocsRecordModal item={viewingGoogleDoc} onClose={() => setViewingGoogleDoc(null)} />}{viewingEvidence && <EvidencePreviewModal item={viewingEvidence} onClose={() => setViewingEvidence(null)} notify={notify} />}</>;
}

function RecordRow({ resource, item, data, actions }) {
  const student = studentName(data, item.student);
  const map = {
    researches: [item.title, `${student} • ${item.field || 'Research'} • ${item.role || '—'}`, item.summary, item.verified ? 'approved' : 'reviewing'],
    projects: [item.title, `${student} • ${item.role || 'Project'} • ${item.technologies || '—'}`, item.description, item.verified ? 'approved' : 'reviewing'],
    internships: [`${item.position} — ${item.organization}`, `${student} • ${dateText(item.start_date)} — ${item.is_current ? 'Current' : dateText(item.end_date)}`, item.description, item.verified ? 'approved' : 'reviewing'],
    activities: [item.name, `${student} • ${label(item.activity_type)} • ${item.role || '—'}`, item.impact || item.description, item.verified ? 'approved' : 'reviewing'],
    honors: [item.title, `${student} • ${item.issuer || '—'} • ${label(item.level)}`, item.description, item.verified ? 'approved' : 'reviewing'],
    achievements: [item.title, `${student} • ${label(item.category)} • ${dateText(item.date)}`, item.impact || item.description, item.verified ? 'approved' : 'reviewing'],
    recommendations: [item.recommender_name, `${student} • ${item.recommender_title || '—'} • ${item.relationship || '—'}`, `Deadline: ${dateText(item.deadline)}`, item.status],
    tasks: [item.title, `${student} • ${dateText(item.due_date)} • ${label(item.priority)}${item.is_self_assigned ? ' • Self-task · no XP' : ''}${item.submitted_at ? ` • Submitted ${dateText(item.submitted_at)}` : ''}`, item.student_response || item.description, item.status],
    applications: [item.university_detail?.name || 'University', `${student} • ${item.program} • ${label(item.tier)}`, `Deadline: ${dateText(item.deadline)}`, item.status],
    essays: [item.title, `${student} • Version ${item.version} • ${item.university_name || 'General'}`, item.counselor_comment || item.prompt, item.status],
    bookings: [item.topic, `${student} • ${dateTimeText(item.starts_at)} • ${item.participant_name || 'Meeting participant'}`, item.notes, item.status]
  };
  const [title, meta, description, badge] = map[resource] || ['Record', student, '', null];
  return <Record title={title} meta={meta} description={description} badge={badge} actions={actions} />;
}

function ResourceForm({ resource, item, data, user, defaultStudentId = null, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const allFields = RESOURCE_FIELDS[resource] || [];
  const fields = resource === 'tasks' && user.role === 'student' ?
  allFields.filter(([name]) =>
  !item ?
  ['title', 'description', 'due_date', 'priority'].includes(name) :
  item.is_self_assigned || ['status', 'student_response', 'submission_url', 'submission_file'].includes(name)
  ) :
  allFields;
  async function submit(event) {
    event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);
    const usesFileUpload = fields.some(([name,, type]) => type === 'file' && values.get(name)?.size);
    const payload = usesFileUpload ? new FormData() : {};
    for (const [name,, type] of fields) {
      const raw = values.get(name);
      if (type === 'file') {
        if (raw?.size && payload instanceof FormData) payload.append(name, raw);
        continue;
      }
      const nullable = ['date', 'number', 'university', 'application'].includes(type);
      const normalized = type === 'checkbox' ? raw === 'on' : raw === '' && nullable ? null : raw;
      if (payload instanceof FormData) payload.append(name, normalized ?? '');else
      payload[name] = normalized;
    }
    if (!item) {
      const studentId = isTaskManager(user) ? Number(values.get('student')) : ownStudent(data)?.id;
      if (payload instanceof FormData) payload.append('student', studentId);else
      payload.student = studentId;
    }
    try {
      if (item) await api.update(resource, item.id, payload);else
      await api.create(resource, payload);
      notify(item ? t("Record updated.") : t("Record created."));onSaved();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  const selfTask = resource === 'tasks' && user.role === 'student';
  return <Modal title={selfTask ? item ? t("Edit self-task") : t("Create self-task") : `${item ? t("Edit") : t("Add")} ${resource}`} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    {!item && isTaskManager(user) && <Field label={t("Student")} hint={t("Only students connected to your account are listed.")}><select name="student" required defaultValue={defaultStudentId || ''}><option value="" disabled>{t("Select student")}</option>{data.students.map((student) => <option key={student.id} value={student.id}>{fullName(student.user_detail)}</option>)}</select></Field>}
    {selfTask && <div className="form-wide self-task-note"><Sparkles size={18} /><div><b>{t("Personal development task")}</b><p>{t("This task is for your own planning and never awards XP.")}</p></div></div>}
    {fields.map(([name, title, type = 'text', required = false, choices = []]) => <DynamicField key={name} name={name} labelText={title} type={type} required={required} choices={choices} value={item?.[name]} data={data} user={user} />)}
    {fields.some(([name]) => name === 'google_docs_url') && <div className="form-wide google-doc-sharing-hint"><ShieldCheck size={16} /><span>{t("Set Google Docs sharing to Viewer or “Anyone with the link” to enable the preview.")}</span></div>}
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : t("Save")}</button></div>
  </form></Modal>;
}

function DynamicField({ name, labelText, type, required, choices, value, data, user }) {
  if (name === 'status' && !isTaskManager(user)) choices = choices.filter((choice) => !['approved', 'late', 'rejected', 'waitlisted', 'accepted', 'needs_revision', 'completed'].includes(choice));
  if (type === 'textarea') return <Field label={t(labelText)}><textarea name={name} defaultValue={value || ''} required={required} /></Field>;
  if (type === 'select') return <Field label={t(labelText)}><select name={name} defaultValue={value || choices[0]} required={required}>{choices.map((choice) => <option key={choice} value={choice}>{label(choice)}</option>)}</select></Field>;
  if (type === 'checkbox') return <CheckboxControl className="form-wide" name={name} defaultChecked={Boolean(value)}>{t(labelText)}</CheckboxControl>;
  if (type === 'file') return <Field label={t(labelText)}><input name={name} type="file" accept=".pdf,.doc,.docx,.png,.jpg,.jpeg" /></Field>;
  if (type === 'university') return <Field label={t(labelText)}><select name={name} defaultValue={value || ''} required={required}><option value="">{t('Select university')}</option>{data.universities.map((uni) => <option key={uni.id} value={uni.id}>{uni.name} — {uni.country}</option>)}</select></Field>;
  if (type === 'application') return <Field label={t(labelText)}><select name={name} defaultValue={value || ''}><option value="">{t('General essay')}</option>{data.applications.map((app) => <option key={app.id} value={app.id}>{app.university_detail?.name} — {studentName(data, app.student)}</option>)}</select></Field>;
  return <Field label={t(labelText)}><input name={name} type={type} defaultValue={value ?? ''} required={required} /></Field>;
}

function DocumentsPage({ user, data, query, reload, notify, typeFilter = '', title = 'Documents' }) {
  const [open, setOpen] = useState(false);
  const [previewing, setPreviewing] = useState(null);
  const docs = data.documents.filter((item) => (!typeFilter || item.document_type === typeFilter) && JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  async function approve(doc) {try {await api.update('documents', doc.id, { status: 'approved' });notify(t("Document approved."));reload();} catch (err) {notify(err.message, 'error');}}
  return <><Panel title={title} action={<button className="button primary" onClick={() => setOpen(true)}><Plus size={16} /> {typeFilter === 'certificate' ? t("Upload certificate") : t("Upload document")}</button>}><div className="record-list">{docs.map((doc) => <Record key={doc.id} title={doc.title} meta={`${studentName(data, doc.student)} • ${label(doc.document_type)}${doc.has_file ? ` • ${doc.file_name || 'File'} • ${formatFileSize(doc.file_size)}` : ''}`} description={doc.counselor_comment} badge={doc.status} actions={<>{(doc.google_docs_preview_url || doc.has_file && doc.file_previewable) && <button className="button quiet small" onClick={() => setPreviewing(doc)}><Eye size={14} /> {t("Preview")}</button>}{doc.has_file && <button className="button quiet small" onClick={() => downloadDocumentFile(doc, notify)}><Download size={14} /> {t("Download")}</button>}<GoogleDocsActions item={doc} />{isCounselor(user) && doc.status !== 'approved' && <button className="button quiet small" onClick={() => approve(doc)}><CheckCircle2 size={15} /> {t("Approve")}</button>}</>} />)}{!docs.length && <Empty />}</div></Panel>{open && <DocumentForm user={user} data={data} defaultType={typeFilter} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}{previewing && <DocumentPreviewModal document={previewing} onClose={() => setPreviewing(null)} notify={notify} />}</>;
}

function DocumentForm({ user, data, defaultType = '', onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  async function submit(event) {
    event.preventDefault();const values = new FormData(event.currentTarget);const payload = new FormData();
    const file = values.get('file');
    const status = values.get('status') || 'uploaded';
    if (status !== 'required' && !file?.size && !values.get('google_docs_url')) {
      notify(t("Select a file or add a Google Docs link."), 'error');
      return;
    }
    setSaving(true);
    payload.append('student', isCounselor(user) ? values.get('student') : ownStudent(data)?.id);
    for (const name of ['title', 'document_type', 'status', 'google_docs_url']) payload.append(name, values.get(name) || '');
    if (file?.size) payload.append('file', file);
    try {await api.uploadDocument(payload);notify(status === 'required' ? t("Document requirement created.") : t("Document uploaded securely."));onSaved();} catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  const acceptedFiles = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.rtf,.odt,.ods,.odp,.png,.jpg,.jpeg,.webp,.heic';
  return <Modal title={defaultType === 'certificate' ? t("Upload certificate") : t("Upload document")} onClose={onClose}><form className="form-grid" onSubmit={submit}>{isCounselor(user) && <Field label={t("Student")}><select name="student" required>{data.students.map((student) => <option value={student.id} key={student.id}>{fullName(student.user_detail)}</option>)}</select></Field>}<Field label={t("Title")}><input name="title" required /></Field><Field label={t("Type")}><select name="document_type" defaultValue={defaultType || 'passport'} disabled={Boolean(defaultType)}>{['passport', 'transcript', 'ielts', 'sat', 'cv', 'recommendation', 'essay', 'certificate', 'other'].map((item) => <option key={item} value={item}>{label(item)}</option>)}</select>{defaultType && <input type="hidden" name="document_type" value={defaultType} />}</Field>{isCounselor(user) ? <Field label={t("Status")}><select name="status" defaultValue="uploaded">{['required', 'uploaded', 'reviewing', 'approved', 'rejected'].map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></Field> : <input type="hidden" name="status" value="uploaded" />}<Field label={t("File")} hint={t("PDF, Office, OpenDocument, text or image · maximum 25 MB")}><input name="file" type="file" accept={acceptedFiles} onChange={(event) => setSelectedFile(event.target.files?.[0] || null)} /></Field>{selectedFile && <div className="selected-document-file"><FileText size={18} /><span><b>{selectedFile.name}</b><small>{formatFileSize(selectedFile.size)}</small></span><CheckCircle2 size={17} /></div>}<Field label={t("Google Docs URL")} hint={t("Optional alternative to an uploaded file")}><input name="google_docs_url" type="url" placeholder={t("https://docs.google.com/document/d/.../edit")} /></Field><div className="form-wide google-doc-sharing-hint"><ShieldCheck size={16} /><span>{t("Files are private and opened through an authenticated connection. For Google Docs preview, enable Viewer access.")}</span></div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Uploading securely…") : t("Upload")}</button></div></form></Modal>;
}

function PortalTabs({ items, active, onChange }) {
  function handleKeyDown(event, index) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length;
    onChange(items[nextIndex][0]);
    event.currentTarget.parentElement?.querySelectorAll('[role="tab"]')[nextIndex]?.focus();
  }
  return <div className="portal-tabs" role="tablist">{items.map(([key, title], index) => <button type="button" role="tab" aria-selected={active === key} tabIndex={active === key ? 0 : -1} key={key} className={active === key ? "active" : ''} onClick={() => onChange(key)} onKeyDown={(event) => handleKeyDown(event, index)}>{t(title)}</button>)}</div>;
}

function StudentCenterPage({ user, data, query, reload, notify }) {
  const [tab, setTab] = useState('overview');
  return <div className="section-stack student-portal">
    <PortalTabs active={tab} onChange={setTab} items={[["overview", "Overview"], ["academics", "Academics"], ["portfolio", "Portfolio"], ["activities", "Activities & honors"], ["documents", "Documents"]]} />
    {tab === 'overview' && <StudentOverview student={ownStudent(data)} data={data} />}
    {tab === 'academics' && <div className="section-stack"><ProfileCard student={ownStudent(data)} /><ResourceSection title={t("Research & academic work")} resource="researches" {...{ user, data, query, reload, notify }} /></div>}
    {tab === 'portfolio' && <div className="split-grid"><ResourceSection title={t("Projects")} resource="projects" {...{ user, data, query, reload, notify }} /><ResourceSection title={t("Internships")} resource="internships" {...{ user, data, query, reload, notify }} /></div>}
    {tab === 'activities' && <div className="section-stack"><div className="split-grid"><ResourceSection title={t("Activities")} resource="activities" {...{ user, data, query, reload, notify }} /><ResourceSection title={t("Honors")} resource="honors" {...{ user, data, query, reload, notify }} /></div><div className="split-grid"><ResourceSection title={t("Achievements")} resource="achievements" {...{ user, data, query, reload, notify }} /><ResourceSection title={t("Recommendation letters")} resource="recommendations" {...{ user, data, query, reload, notify }} /></div></div>}
    {tab === 'documents' && <DocumentsPage {...{ user, data, query, reload, notify }} />}
  </div>;
}

function StudentWorkspaceSelector({ students, value, onChange, metrics = [] }) {
  const selected = students.find((student) => String(student.id) === String(value));
  return <section className="student-workspace-selector">
    <div className="student-workspace-identity"><span className="student-workspace-avatar">{selected ? initials(fullName(selected.user_detail)) : <UsersRound size={20} />}</span><div><span className="eyebrow">{t("STUDENT WORKSPACE")}</span><h3>{selected ? fullName(selected.user_detail) : t("All assigned students")}</h3><p>{selected ? tx`${selected.school_name || selected.school?.name || t("School")} · Grade ${selected.grade || '—'}` : tx`${students.length} students connected to your account`}</p></div></div>
    <div className="student-workspace-metrics">{metrics.map(([metricLabel, value]) => <span key={metricLabel}><strong>{value}</strong><small>{metricLabel}</small></span>)}</div>
    <Field label={t("Choose student")} hint={t("Assignments and lists follow this selection.")}><select value={value} onChange={(event) => onChange(event.target.value)}><option value="all">{t("All assigned students")}</option>{students.map((student) => <option key={student.id} value={student.id}>{fullName(student.user_detail)}</option>)}</select></Field>
  </section>;
}

function MissionForm({ mission, user, data, defaultStudentId = null, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const manager = isTaskManager(user);
  const studentSubmitted = !manager && mission?.status === 'submitted';
  async function submit(event) {
    event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);
    const payload = manager ?
    { title: values.get('title'), category: values.get('category'), description: values.get('description'), due_date: values.get('due_date') || null, status: values.get('status') } :
    { status: 'submitted', reflection: values.get('reflection') };
    if (manager && !mission) payload.student = Number(values.get('student'));
    try {mission ? await api.update('roadmap-missions', mission.id, payload) : await api.create('roadmap-missions', payload);notify(manager ? mission ? t("Mission updated.") : t("Mission created.") : t("Mission submitted for approval."));onSaved();} catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  const statuses = ['planned', 'in_progress', 'submitted'];
  return <Modal title={manager ? mission ? t("Edit roadmap mission") : t("Assign roadmap mission") : studentSubmitted ? t("Mission submitted") : t("Submit roadmap mission")} onClose={onClose}><form className="form-grid" onSubmit={submit}>{manager && !mission && <Field label={t("Student")} hint={t("The currently selected student is preselected.")}><select name="student" required defaultValue={defaultStudentId || ''}><option value="" disabled>{t("Select student")}</option>{data.students.map((student) => <option key={student.id} value={student.id}>{fullName(student.user_detail)}</option>)}</select></Field>}{manager && <><Field label={t("Mission title")}><input name="title" defaultValue={mission?.title || ''} required /></Field><Field label={t("Category")}><input name="category" defaultValue={mission?.category || ''} placeholder={t("Applications, Essays...")} /></Field><Field label={t("Due date")}><input name="due_date" type="date" defaultValue={mission?.due_date || ''} /></Field><Field label={t("Status")}><select name="status" defaultValue={mission?.status || 'planned'}>{statuses.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></Field></>}{!manager && <div className={`form-wide mission-submit-status ${studentSubmitted ? 'submitted' : 'planned'}`}>{studentSubmitted ? <Clock3 size={21} /> : <Sparkles size={21} />}<div><b>{studentSubmitted ? t("Submitted") : t("Planned mission")}</b><p>{studentSubmitted ? t("Your work is awaiting teacher or counselor approval.") : t("Complete the mission, write your reflection, then submit it for approval.")}</p></div></div>}{manager ? <Field label={t("Description")}><textarea name="description" defaultValue={mission?.description || ''} /></Field> : <Field label={t("Reflection")}><textarea name="reflection" defaultValue={mission?.reflection || ''} placeholder={t("What did you learn while completing this mission?")} required readOnly={studentSubmitted} /></Field>}<div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{studentSubmitted ? t("Close") : t("Cancel")}</button>{!studentSubmitted && <button className="button primary" disabled={saving} aria-busy={saving}>{saving ? manager ? t("Saving…") : t("Submitting…") : manager ? t("Save") : t("Submit mission")}</button>}</div></form></Modal>;
}

function LevelOneSetupModal({ data, defaultStudentId = null, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      const result = await api.extendLevelOneRoadmap(Number(values.get('student')));
      notify(result.created_count ? tx`${result.created_count} Level 1 missions added.` : t("Level 1 is already up to date."));
      onSaved();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("Extend Level 1 roadmap")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Student")}><select name="student" required defaultValue={defaultStudentId || ''}><option value="" disabled>{t("Select student")}</option>{data.students.map((student) => <option key={student.id} value={student.id}>{fullName(student.user_detail)}</option>)}</select></Field><div className="form-wide roadmap-setup-note"><Sparkles size={19} /><div><b>{t("8-step Level 1 path")}</b><p>{t("Missing missions will be added in the correct order. Existing statuses, reflections and approvals stay unchanged.")}</p></div></div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || !data.students.length} aria-busy={saving}>{saving ? t("Extending…") : t("Extend Level 1")}</button></div></form></Modal>;
}

function StudentRoadmapPath({ student, missions, onOpen }) {
  const level = student?.level ?? 1;
  const levelMissions = missions.
  filter((item) => (item.level || 1) === level).
  sort((a, b) => (a.sequence || 1) - (b.sequence || 1));
  const missionById = new Map(levelMissions.map((item) => [item.id, item]));
  const completed = levelMissions.filter((item) => item.status === 'completed').length;
  const activeIndex = levelMissions.findIndex((item) => item.status !== 'completed');
  const currentIndex = activeIndex === -1 ? Math.max(0, levelMissions.length - 1) : activeIndex;
  const nextLevel = student?.level_up_pending ? student.eligible_level : Math.min(50, level + 1);
  const isLocked = (item) => item.prerequisite && missionById.get(item.prerequisite)?.status !== 'completed';
  function missionState(item, index) {
    if (item.status === 'completed') return 'complete';
    if (item.status === 'submitted') return 'approval';
    if (isLocked(item)) return 'locked';
    if (item.status === 'in_progress' || index === currentIndex) return 'current';
    return 'upcoming';
  }
  return <section className="level-roadmap-shell">
    <header className="level-roadmap-summary">
      <div><span className="eyebrow">{t("LEVEL")} {level} {t("· MISSION")} {Math.min(completed + 1, Math.max(1, levelMissions.length))} {t("OF")} {Math.max(1, levelMissions.length)}</span><h2>{levelMissions[currentIndex]?.title || t("Your next milestone")}</h2><p>{student?.level_up_pending ? tx`You have earned enough XP for Level ${student.eligible_level}. Teacher or counselor approval is pending.` : t("Complete each mission in order, submit your reflection, and earn XP after staff approval.")}</p></div>
      <div className="roadmap-level-score"><span><Award size={18} /> {t("Level")} {level}</span><strong>{student?.xp_total || 0} {t("XP")}</strong><small>{student?.level_up_pending ? t("Level approval pending") : tx`${Math.max(0, (student?.next_level_xp || 0) - (student?.xp_total || 0))} XP to next level`}</small></div>
    </header>
    <div className="roadmap-path-stats"><span><CheckCircle2 size={17} /><b>{completed}</b> {t("approved missions")}</span><span><Sparkles size={17} /><b>{t("75 XP")}</b> {t("per approved mission")}</span><span><Target size={17} /><b>{t("Level")} {nextLevel}</b> {t("next checkpoint")}</span></div>
    <div className="roadmap-xp-track"><span style={{ width: `${student?.xp_progress_percent || 0}%` }} /><b>{formatPercentLocale(student?.xp_progress_percent || 0)}</b></div>
    {levelMissions.length ? <div className="level-roadmap-path">{levelMissions.map((item, index) => {
        const state = missionState(item, index);
        const NodeIcon = state === 'complete' ? Check : state === 'approval' ? Clock3 : item.status === 'planned' ? Sparkles : state === 'current' ? BookOpen : state === 'locked' ? ShieldCheck : Sparkles;
        return <article className={`roadmap-path-row ${state}`} style={{ '--path-offset': `${[0, -78, 0, 78][index % 4]}px` }} key={item.id}>
        <button type="button" className="roadmap-node" onClick={() => onOpen(item)} disabled={state === 'complete' || state === 'locked'} aria-label={`${item.title}, ${state === 'locked' ? t("locked") : label(item.status)}`}><NodeIcon size={30} strokeWidth={2.7} /></button>
        <div className="roadmap-node-card"><span>{t("Step")} {item.sequence || index + 1} · {item.category || t("Roadmap")}</span>{item.status === 'planned' && <div className="mission-status-chip"><Sparkles size={12} /> {t("Planned")}</div>}<h3>{item.title}</h3><p>{state === 'complete' ? t("Approved · XP awarded") : state === 'approval' ? t("Submitted · awaiting staff approval") : state === 'locked' ? t("Locked · complete the previous mission first") : item.status === 'planned' ? t("Complete the task and submit when ready") : state === 'current' ? t("Continue the mission and submit when ready") : tx`Upcoming · due ${dateText(item.due_date)}`}</p></div>
      </article>;
      })}<div className="roadmap-checkpoint"><span><Award size={26} /></span><div><small>{t("NEXT CHECKPOINT")}</small><h3>{t("Level")} {nextLevel}</h3><p>{student?.level_up_pending ? t("Ready for staff approval") : tx`${student?.next_level_xp || 0} total XP required`}</p></div></div></div> : <Empty text={t("Your counselor has not assigned any roadmap missions yet.")} />}
  </section>;
}

function roadmapMissionState(item, missions) {
  if (item.status === 'completed') return 'completed';
  if (item.status === 'submitted') return 'submitted';
  const prerequisite = item.prerequisite ?
  missions.find((candidate) => candidate.id === item.prerequisite) :
  null;
  if (prerequisite && prerequisite.status !== 'completed') return 'locked';
  const siblings = missions.
  filter((candidate) => candidate.student === item.student && (candidate.level || 1) === (item.level || 1)).
  sort((a, b) => (a.sequence || 1) - (b.sequence || 1));
  const firstActionable = siblings.find((candidate) => {
    if (['completed', 'submitted'].includes(candidate.status)) return false;
    const required = candidate.prerequisite ?
    missions.find((mission) => mission.id === candidate.prerequisite) :
    null;
    return !required || required.status === 'completed';
  });
  if (item.status === 'in_progress' || firstActionable?.id === item.id) return 'current';
  return 'upcoming';
}

const MISSION_STATE_COPY = {
  current: ['Current', 'Ready to continue'],
  locked: ['Locked', 'Complete the prerequisite first'],
  submitted: ['Submitted', 'Awaiting staff approval'],
  completed: ['Completed', 'Approved and XP awarded'],
  upcoming: ['Upcoming', 'Queued in your roadmap']
};

function MissionList({ user, data, query, onOpen, onApprove, onRemove }) {
  const manager = isTaskManager(user);
  const [filter, setFilter] = useState('all');
  const [sort, setSort] = useState('sequence');
  const missions = data.roadmapMissions.map((item) => ({
    ...item,
    displayState: roadmapMissionState(item, data.roadmapMissions)
  }));
  const normalizedQuery = query.trim().toLowerCase();
  const visible = missions.
  filter((item) => filter === 'all' || item.displayState === filter).
  filter((item) => !normalizedQuery || JSON.stringify(item).toLowerCase().includes(normalizedQuery)).
  sort((a, b) => {
    if (sort === 'deadline') return String(a.due_date || '9999').localeCompare(String(b.due_date || '9999'));
    if (sort === 'status') return a.displayState.localeCompare(b.displayState);
    return (a.level || 1) - (b.level || 1) || (a.sequence || 1) - (b.sequence || 1);
  });
  const nextMission = !manager ? missions.find((item) => item.displayState === 'current') : null;

  return <div className="mission-list-shell">
    {nextMission && <section className="next-mission-callout"><div><span className="eyebrow">{t("NEXT MISSION")}</span><h3>{nextMission.title}</h3><p>{nextMission.description || t("Continue this mission and submit a reflection when you are ready.")}</p></div><div><span><CalendarDays size={15} /> {nextMission.due_date ? dateText(nextMission.due_date) : t("No deadline")}</span><span><Sparkles size={15} /> {nextMission.xp_reward || 75} {t("XP after approval")}</span><button className="button primary" onClick={() => onOpen(nextMission)}>{t("Continue mission")} <ChevronRight size={16} /></button></div></section>}
    <div className="mission-list-toolbar"><PortalTabs active={filter} onChange={setFilter} items={[["all", "All"], ["current", "Current"], ["locked", "Locked"], ["submitted", "Submitted"], ["completed", "Completed"], ["upcoming", "Upcoming"]]} /><label><Filter size={15} /><span>{t("Sort")}</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option value="sequence">{t("Roadmap order")}</option><option value="deadline">{t("Deadline")}</option><option value="status">{t("Status")}</option></select></label></div>
    <div className="mission-grid">{visible.map((item) => {
        const [stateLabel, stateDescription] = MISSION_STATE_COPY[item.displayState];
        const canOpen = item.displayState !== 'locked';
        return <article className={`mission-card mission-${item.displayState}`} key={item.id}>
        <div className="mission-top"><span>{t("Level")} {item.level || 1} {t("· Step")} {item.sequence || 1} · {item.category || t("Roadmap")}</span><Badge tone={item.displayState}>{stateLabel}</Badge></div>
        <h3>{item.title}</h3><p>{item.description || t("No description provided.")}</p>
        {manager && <small className="mission-owner">{item.student_name} {t("· Assigned by")} {item.assigned_by_name || t("staff")}</small>}
        <div className="mission-details"><span><CalendarDays size={14} /><b>{t("Deadline")}</b>{item.due_date ? dateText(item.due_date) : t("No deadline")}</span><span><Sparkles size={14} /><b>{t("Reward")}</b>{item.xp_reward || 75} {t("XP")}</span><span><ShieldCheck size={14} /><b>{t("Prerequisite")}</b>{item.prerequisite_title || (item.prerequisite_sequence ? tx`Step ${item.prerequisite_sequence}` : t("None"))}</span><span><MessageSquareText size={14} /><b>{t("Reflection")}</b>{item.reflection ? t("Added") : t("Not written")}</span></div>
        <div className="mission-approval"><span className={`mission-state-dot ${item.displayState}`} /> <b>{t(stateLabel)}</b><small>{t(stateDescription)}</small></div>
        <footer><small>{item.reflection ? `${item.reflection.slice(0, 72)}${item.reflection.length > 72 ? '…' : ''}` : t("Reflection will appear here after submission.")}</small><div>{manager && item.status === 'submitted' && <button className="button quiet small" onClick={() => onApprove(item)}><CheckCircle2 size={15} /> {t("Approve")}</button>}{canOpen && item.status !== 'completed' && <button className="button quiet small" onClick={() => onOpen(item)}>{!manager && item.status === 'submitted' ? <Eye size={15} /> : <Pencil size={15} />} {!manager && item.status === 'submitted' ? t("View") : manager ? t("Edit") : t("Open")}</button>}{manager && <button className="icon-button danger" onClick={() => onRemove(item)} aria-label={tx`Delete ${item.title}`}><Trash2 size={15} /></button>}</div></footer>
      </article>;
      })}{!visible.length && <Empty text={data.roadmapMissions.length ? t("No missions match this filter.") : t("No missions have been assigned yet.")} />}</div>
  </div>;
}

function RoadmapPage({ user, data, query, reload, notify }) {
  const manager = isTaskManager(user);
  const [tab, setTab] = useState(manager ? 'missions' : 'path');
  const [selectedStudentId, setSelectedStudentId] = useState(() => manager && data.students[0] ? String(data.students[0].id) : 'all');
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(false);
  const [setupOpen, setSetupOpen] = useState(false);
  const { confirm, dialog } = useActionDialog();
  const student = ownStudent(data);
  useEffect(() => {
    if (!manager || !data.students.length) return;
    if (selectedStudentId !== 'all' && !data.students.some((item) => String(item.id) === selectedStudentId)) {
      setSelectedStudentId(String(data.students[0].id));
    }
  }, [data.students, manager, selectedStudentId]);
  const selectedStudentNumericId = selectedStudentId === 'all' ? null : Number(selectedStudentId);
  const scopedData = manager && selectedStudentNumericId ?
  {
    ...data,
    tasks: data.tasks.filter((item) => item.student === selectedStudentNumericId),
    roadmapMissions: data.roadmapMissions.filter((item) => item.student === selectedStudentNumericId)
  } :
  data;
  const selectedStudent = data.students.find((item) => item.id === selectedStudentNumericId);
  const workspaceTitle = selectedStudent ? fullName(selectedStudent.user_detail) : manager ? 'All students' : 'My';
  async function remove(item) {if (!await confirm({ title: t("Delete mission"), description: tx`Delete ${item.title}? This action cannot be undone.`, confirmLabel: t("Delete"), tone: 'danger' })) return;try {await api.remove('roadmap-missions', item.id);notify(t("Mission deleted."));reload();} catch (err) {notify(err.message, 'error');}}
  async function approve(item) {try {const result = await api.approveRoadmapMission(item.id);notify(tx`Roadmap mission approved. +${result.xp_awarded || 0} XP`);reload();} catch (err) {notify(err.message, 'error');}}
  const timeline = [
  ...scopedData.tasks.map((item) => ({ id: `task-${item.id}`, title: item.title, date: item.due_date, status: item.status, kind: 'Task' })),
  ...scopedData.roadmapMissions.map((item) => ({ id: `mission-${item.id}`, title: item.title, date: item.due_date, status: item.status, kind: 'Mission' }))].
  filter((item) => item.date).sort((a, b) => new Date(a.date) - new Date(b.date));
  return <div className="section-stack student-portal">
    <section className="portal-hero roadmap-hero"><div><span className="eyebrow">{t("YOUR APPLICATION PLAN")}</span><h2>{t("Roadmap")}</h2><p>{manager ? t("Assign missions, review student submissions, and approve the work that earns XP.") : t("Follow your visual learning path, submit reflections, and level up after teacher or counselor approval.")}</p></div>{manager && <div className="roadmap-hero-actions"><button className="button light" onClick={() => setSetupOpen(true)}><Sparkles size={17} /> {t("Extend Level 1")}</button><button className="button light" onClick={() => {setEditing(null);setOpen(true);}}><Plus size={17} /> {t("Assign mission")}</button></div>}</section>
    {manager && <StudentWorkspaceSelector students={data.students} value={selectedStudentId} onChange={setSelectedStudentId} metrics={[["Missions", scopedData.roadmapMissions.length], ["Tasks", scopedData.tasks.length], ["Awaiting approval", scopedData.roadmapMissions.filter((item) => item.status === 'submitted').length + scopedData.tasks.filter((item) => item.status === 'submitted').length]]} />}
    <PortalTabs active={tab} onChange={setTab} items={manager ? [["missions", "Mission list"], ["tasks", "Task list"], ["timeline", "Timeline view"], ["reflections", "Reflection view"]] : [["path", "Level path"], ["tasks", "Task list"], ["missions", "Mission list"], ["reflections", "Reflections"]]} />
    {tab === 'path' && !manager && <StudentRoadmapPath student={student} missions={data.roadmapMissions} onOpen={(item) => {setEditing(item);setOpen(true);}} />}
    {tab === 'tasks' && <ResourceSection title={tx`${workspaceTitle} tasks`} resource="tasks" data={scopedData} user={user} query={query} reload={reload} notify={notify} defaultStudentId={selectedStudentNumericId} />}
    {tab === 'missions' && <MissionList user={user} data={scopedData} query={query} onOpen={(item) => {setEditing(item);setOpen(true);}} onApprove={approve} onRemove={remove} />}
    {tab === 'timeline' && <Panel title={tx`${workspaceTitle} application timeline`}><div className="timeline-list">{timeline.map((item) => <div key={item.id}><span className="timeline-dot" /><time>{dateText(item.date)}</time><div><b>{item.title}</b><small>{item.kind}</small></div><Badge>{item.status}</Badge></div>)}{!timeline.length && <Empty text={t("No dated tasks or missions for this student.")} />}</div></Panel>}
    {tab === 'reflections' && <div className="reflection-grid">{scopedData.roadmapMissions.map((item) => <article key={item.id}><Sparkles size={20} /><div><span>{item.category || t("Mission")}</span><h3>{item.title}</h3>{manager && <small>{item.student_name}</small>}<p>{item.reflection || t("No reflection has been written for this mission yet.")}</p></div>{!manager && item.status !== 'completed' && <button className="button quiet small" onClick={() => {setEditing(item);setOpen(true);}}>{item.status === 'submitted' ? t("View submission") : t("Write reflection")}</button>}</article>)}{!scopedData.roadmapMissions.length && <Empty text={t("No roadmap reflections for this student.")} />}</div>}
    {open && <MissionForm mission={editing} user={user} data={data} defaultStudentId={selectedStudentNumericId} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}
    {setupOpen && <LevelOneSetupModal data={data} defaultStudentId={selectedStudentNumericId} onClose={() => setSetupOpen(false)} onSaved={() => {setSetupOpen(false);reload();}} notify={notify} />}
    {dialog}
  </div>;
}

function CommunityPostForm({ onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);try {await api.create('community-posts', { title: values.get('title'), body: values.get('body'), post_type: values.get('post_type') });notify(t("Post published."));onSaved();} catch (err) {notify(err.message, 'error');} finally {setSaving(false);}}
  return <Modal title={t("Create a community post")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Type")}><select name="post_type">{['discussion', 'question', 'update'].map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></Field><Field label={t("Title")}><input name="title" required /></Field><Field label={t("Post")}><textarea name="body" required /></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Publishing…") : t("Publish")}</button></div></form></Modal>;
}

function CommunityPage({ data, reload, notify }) {
  const [filter, setFilter] = useState('all');
  const [open, setOpen] = useState(false);
  const [communityPosts, setCommunityPosts] = useState(data.communityPosts);
  const [likingIds, setLikingIds] = useState([]);
  useEffect(() => setCommunityPosts(data.communityPosts), [data.communityPosts]);
  const posts = communityPosts.filter((item) => filter === 'all' || item.post_type === filter);
  async function like(item) {
    if (likingIds.includes(item.id)) return;
    const optimistic = { ...item, liked_by_me: !item.liked_by_me, likes_count: Math.max(0, item.likes_count + (item.liked_by_me ? -1 : 1)) };
    setLikingIds((ids) => [...ids, item.id]);
    setCommunityPosts((items) => items.map((post) => post.id === item.id ? optimistic : post));
    try {
      const saved = await api.likeCommunityPost(item.id);
      setCommunityPosts((items) => items.map((post) => post.id === item.id ? saved : post));
    } catch (err) {
      setCommunityPosts((items) => items.map((post) => post.id === item.id ? item : post));
      notify(err.message, 'error');
    } finally {
      setLikingIds((ids) => ids.filter((id) => id !== item.id));
    }
  }
  return <div className="section-stack student-portal"><section className="portal-hero community-hero"><div><span className="eyebrow">{t("NASEEB COMMUNITY")}</span><h2>{t("Learn together. Grow together.")}</h2><p>{t("Ask questions, share useful resources, and learn from the application experience of other students.")}</p></div><button className="button light" onClick={() => setOpen(true)}><Plus size={17} /> {t("Create a post")}</button></section><div className="community-layout"><div><PortalTabs active={filter} onChange={setFilter} items={[["all", "All posts"], ["discussion", "Discussion"], ["question", "Q&A"], ["update", "Updates"]]} /><div className="community-feed">{posts.map((post) => {const liking = likingIds.includes(post.id);return <article className="community-card" key={post.id}><header><span className="avatar">{post.author_initials}</span><div><b>{post.author_name || t("Student")}</b><small>{dateTimeText(post.created_at)} • {label(post.post_type)}</small></div></header><h3>{post.title}</h3><p>{post.body}</p><footer><button className={post.liked_by_me ? "liked" : ''} onClick={() => like(post)} disabled={liking} aria-pressed={post.liked_by_me} aria-label={`${post.liked_by_me ? t("Unlike") : t("Like")} ${post.title}`} title={post.liked_by_me ? t("Remove your like") : t("Like this post")}><Heart size={17} fill={post.liked_by_me ? "currentColor" : "none"} /><span>{post.liked_by_me ? t("Liked") : t("Like")}</span><b>{post.likes_count}</b></button></footer></article>;})}{!posts.length && <Empty text={t("No posts in this section yet.")} />}</div></div><aside><Panel title={t("How likes work")}><p className="community-like-help"><Heart size={16} /> {t("Tap Like to support a useful post. Tap it again to remove your like. Each student counts once.")}</p></Panel><Panel title={t("Community guidelines")}><ul className="guide-list"><li>{t("Keep every conversation useful and respectful.")}</li><li>{t("Do not share passwords or confidential documents.")}</li><li>{t("Check your sources and ask clear questions.")}</li></ul></Panel></aside></div>{open && <CommunityPostForm onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}</div>;
}

function BookingForm({ onClose, onSaved, notify, initialParticipantId = null, initialTopic = '' }) {
  const [participants, setParticipants] = useState([]);
  const [loadingParticipants, setLoadingParticipants] = useState(true);
  const [saving, setSaving] = useState(false);
  const [participantId, setParticipantId] = useState(initialParticipantId ? String(initialParticipantId) : '');
  useEffect(() => {
    let active = true;
    api.bookingParticipants().
    then((items) => active && setParticipants(items || [])).
    catch((err) => notify(err.message, 'error')).
    finally(() => active && setLoadingParticipants(false));
    return () => {active = false;};
  }, [notify]);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.create('bookings', {
        participant: Number(values.get('participant')),
        topic: values.get('topic'),
        starts_at: new Date(values.get('starts_at')).toISOString(),
        duration_minutes: Number(values.get('duration_minutes')),
        notes: values.get('notes')
      });
      notify(t("Meeting request sent for approval."));
      onSaved();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("Request a meeting")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Meet with")}><select name="participant" required value={participantId} onChange={(event) => setParticipantId(event.target.value)} disabled={loadingParticipants}><option value="" disabled>{loadingParticipants ? t("Loading available staff…") : t("Select counselor, teacher, or school representative")}</option>{participants.map((participant) => <option key={participant.id} value={participant.id}>{fullName(participant)} · {label(participant.role)}{participant.position ? ` · ${participant.position}` : ''}</option>)}</select></Field><Field label={t("Topic")}><input name="topic" required defaultValue={initialTopic} placeholder={t("Essay review, university list...")} /></Field><Field label={t("Date & time")}><input name="starts_at" type="datetime-local" required /></Field><Field label={t("Duration")}><select name="duration_minutes" defaultValue="45"><option value="30">{t("30 min")}</option><option value="45">{t("45 min")}</option><option value="60">{t("60 min")}</option></select></Field><Field label={t("Notes")}><textarea name="notes" /></Field>{!loadingParticipants && !participants.length && <div className="form-wide booking-participant-warning"><ShieldAlert size={18} /><span>{t("No counselor, teacher, or school representative is available for your account.")}</span></div>}<div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || loadingParticipants || !participants.length} aria-busy={saving}>{saving ? t("Requesting…") : t("Request meeting")}</button></div></form></Modal>;
}

function BookingsPage({ user, data, reload, notify, navigationContext }) {
  const staff = user.role !== 'student';
  const [tab, setTab] = useState(staff ? 'pending' : 'upcoming');
  const [open, setOpen] = useState(false);
  const [savingId, setSavingId] = useState(null);
  const handledIntentRef = useRef(null);
  useEffect(() => {
    const intentKey = navigationContext?.action === 'book' && navigationContext.memberId ? `${navigationContext.memberId}-${navigationContext.serviceTitle || ''}` : null;
    if (!intentKey || handledIntentRef.current === intentKey || staff) return;
    handledIntentRef.current = intentKey;
    setOpen(true);
  }, [navigationContext, staff]);
  const now = new Date();
  const tabs = staff ?
  [['pending', 'Pending approval'], ['upcoming', 'Approved'], ['history', 'History']] :
  [['upcoming', 'Upcoming'], ['history', 'History']];
  const items = data.bookings.filter((item) => {
    const future = new Date(item.starts_at) >= now;
    if (tab === 'pending') return item.status === 'pending';
    if (tab === 'upcoming') return future && (staff ? item.status === 'approved' : ['pending', 'approved'].includes(item.status));
    return !future || ['rejected', 'completed'].includes(item.status);
  });
  async function transition(item, action) {
    setSavingId(item.id);
    try {
      const methods = { approve: api.approveBooking, reject: api.rejectBooking, complete: api.completeBooking };
      await methods[action](item.id);
      notify(tx`Meeting ${label(action === 'approve' ? 'approved' : action === 'reject' ? 'rejected' : 'completed')}.`);
      reload();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSavingId(null);
    }
  }
  return <div className="section-stack student-portal"><div className="portal-toolbar"><PortalTabs active={tab} onChange={setTab} items={tabs} />{!staff && <button className="button primary" onClick={() => setOpen(true)}><Plus size={17} /> {t("Request meeting")}</button>}</div><div className="booking-grid">{items.map((item) => <article className="booking-card" key={item.id}><div className="booking-date"><strong>{new Date(item.starts_at).getDate()}</strong><span>{new Intl.DateTimeFormat(locale(), { month: 'short' }).format(new Date(item.starts_at))}</span></div><div><h3>{item.topic}</h3>{staff && <span className="booking-student"><UserRound size={14} /> {item.student_name}</span>}<p><Clock3 size={15} /> {dateTimeText(item.starts_at)} • {item.duration_minutes} {t("min")}</p><small>{t("With")} {item.participant_name || t("Meeting participant")} · {label(item.participant_role)}</small>{item.notes && <p>{item.notes}</p>}</div><div><Badge>{item.status}</Badge>{staff && item.status === 'pending' && <div className="booking-actions"><button className="button primary small" disabled={savingId === item.id} onClick={() => transition(item, 'approve')}><Check size={14} /> {t("Approve")}</button><button className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'reject')}><X size={14} /> {t("Reject")}</button></div>}{staff && item.status === 'approved' && <button className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'complete')}><CheckCircle2 size={14} /> {t("Mark completed")}</button>}</div></article>)}{!items.length && <Empty text={tab === 'pending' ? t("No meetings need approval.") : tab === 'upcoming' ? t("No upcoming meetings.") : t("No meeting history yet.")} />}</div>{open && <BookingForm initialParticipantId={navigationContext?.memberId} initialTopic={navigationContext?.serviceTitle ? tx`Discuss ${navigationContext.serviceTitle}` : ''} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}</div>;
}

function MessageChannelForm({ kind, user, onClose, onSaved, notify }) {
  const [contacts, setContacts] = useState([]);
  const [selectedMembers, setSelectedMembers] = useState([]);
  const [memberSearch, setMemberSearch] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    api.messageContacts().then((items) => active && setContacts(items || [])).catch((err) => notify(err.message, 'error'));
    return () => {active = false;};
  }, []);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      const channel = kind === 'direct' ?
      await api.openDirectChannel(Number(values.get('contact'))) :
      await api.create('message-channels', {
        kind,
        name: values.get('name')?.trim(),
        description: values.get('description')?.trim(),
        members: selectedMembers
      });
      notify(kind === 'direct' ? t("Direct conversation opened.") : tx`${label(kind)} created.`);
      onSaved(channel);
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  const staffInterface = ['counselor', 'organization'].includes(user.role);
  const normalizedSearch = memberSearch.trim().toLowerCase();
  const visibleContacts = contacts.filter((contact) => !normalizedSearch || `${fullName(contact)} ${contact.role} ${contact.school_name || ''}`.toLowerCase().includes(normalizedSearch));
  function chooseAudience(audience) {
    if (audience === 'clear') {setSelectedMembers([]);return;}
    const matches = contacts.filter((contact) => audience === 'all' || (audience === 'students' ? contact.role === 'student' : contact.role !== 'student'));
    setSelectedMembers(matches.map((contact) => contact.id));
  }
  function toggleMember(contactId) {
    setSelectedMembers((current) => current.includes(contactId) ? current.filter((id) => id !== contactId) : [...current, contactId]);
  }

  const title = kind === 'direct' ? 'Start a direct conversation' : kind === 'discussion' ? 'Start a discussion' : `Create a ${kind}`;
  return <Modal title={title} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    {kind === 'direct' ?
      <Field label={user.role === 'counselor' ? t("Assigned student or school contact") : user.role === 'organization' ? t("Student, teacher or counselor") : t("Contact")}><select name="contact" required defaultValue=""><option value="" disabled>{t("Select a person")}</option>{contacts.map((contact) => <option key={contact.id} value={contact.id}>{fullName(contact)} · {label(contact.role)}{contact.school_name ? ` · ${contact.school_name}` : ''}</option>)}</select></Field> :
      <><Field label={kind === 'discussion' ? t("Question or topic") : t("Channel name")}><input name="name" required maxLength="160" /></Field><Field label={t("Description")}><textarea name="description" maxLength="2000" /></Field></>}
    {['group', 'community'].includes(kind) && <fieldset className="form-wide member-picker"><legend>{t("Initial members ·")} {selectedMembers.length} {t("selected")}</legend><p>{t("Add contacts now. People can also join a public Community later.")}</p>{staffInterface && <div className="audience-shortcuts"><button type="button" onClick={() => chooseAudience('students')}>{user.role === 'counselor' ? t("Assigned students") : t("School students")}</button><button type="button" onClick={() => chooseAudience('staff')}>{t("School staff")}</button><button type="button" onClick={() => chooseAudience('all')}>{t("All contacts")}</button><button type="button" onClick={() => chooseAudience('clear')}>{t("Clear")}</button></div>}<label className="member-search"><Search size={15} /><input value={memberSearch} onChange={(event) => setMemberSearch(event.target.value)} placeholder={t("Search contacts")} /></label><div>{visibleContacts.map((contact) => <CheckboxControl key={contact.id} name="members" value={contact.id} checked={selectedMembers.includes(contact.id)} onChange={() => toggleMember(contact.id)}>{fullName(contact)} · {label(contact.role)}{contact.school_name ? ` · ${contact.school_name}` : ''}</CheckboxControl>)}</div>{!visibleContacts.length && <small>{t("No matching contacts.")}</small>}</fieldset>}
    {kind === 'discussion' && <div className="alert warning form-wide">{t("Discussions are public. A user must join before posting.")}</div>}
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || kind === 'direct' && !contacts.length} aria-busy={saving}>{saving ? t("Saving…") : t("Continue")}</button></div>
  </form></Modal>;
}

function ChannelMembersModal({ channel, user, onClose, onChanged, notify }) {
  const [members, setMembers] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [selectedUser, setSelectedUser] = useState('');
  const [selectedRole, setSelectedRole] = useState('member');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [memberItems, contactItems] = await Promise.all([api.channelMembers(channel.id), api.messageContacts()]);
      setMembers(memberItems || []);
      setContacts(contactItems || []);
    } catch (err) {notify(err.message, 'error');}
  }, [channel.id, notify]);

  useEffect(() => {load();}, [load]);
  const memberIds = new Set(members.map((membership) => membership.user));
  const available = contacts.filter((contact) => !memberIds.has(contact.id));

  async function addMember(event) {
    event.preventDefault();
    if (!selectedUser) return;
    setSaving(true);
    try {
      await api.addChannelMember(channel.id, Number(selectedUser), selectedRole);
      setSelectedUser('');
      await load();
      await onChanged();
      notify(t("Channel member added."));
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }

  async function changeRole(membership, role) {
    setSaving(true);
    try {
      await api.addChannelMember(channel.id, membership.user, role);
      await load();
      notify(tx`Member role changed to ${role}.`);
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }

  async function removeMember(membership) {
    setSaving(true);
    try {
      await api.removeChannelMember(channel.id, membership.user);
      await load();
      await onChanged();
      notify(t("Channel member removed."));
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }

  return <Modal title={tx`Manage ${channel.display_name}`} onClose={onClose}><div className="member-manager"><form onSubmit={addMember}><Field label={t("Add a contact")}><select value={selectedUser} onChange={(event) => setSelectedUser(event.target.value)} required><option value="">{t("Select a contact")}</option>{available.map((contact) => <option key={contact.id} value={contact.id}>{fullName(contact)} · {label(contact.role)}</option>)}</select></Field><Field label={t("Channel role")}><select value={selectedRole} onChange={(event) => setSelectedRole(event.target.value)}><option value="member">{t("Member")}</option><option value="moderator">{t("Moderator")}</option></select></Field><button className="button primary" disabled={saving || !selectedUser}><Plus size={16} /> {t("Add")}</button></form><div className="member-manager-list">{members.map((membership) => <article key={membership.id}><span className="avatar">{initials(fullName(membership.user_detail))}</span><div><b>{fullName(membership.user_detail)}</b><small>{label(membership.user_detail?.role)}{membership.user_detail?.school_name ? ` · ${membership.user_detail.school_name}` : ''}</small></div><Badge>{membership.role}</Badge>{membership.role !== 'owner' && membership.user !== user.id && <div>{membership.role === 'member' ? <button type="button" className="button quiet small" disabled={saving} onClick={() => changeRole(membership, 'moderator')}>{t("Make moderator")}</button> : <button type="button" className="button quiet small" disabled={saving} onClick={() => changeRole(membership, 'member')}>{t("Make member")}</button>}<button type="button" className="icon-button danger" disabled={saving} onClick={() => removeMember(membership)} aria-label={tx`Remove ${fullName(membership.user_detail)}`}><Trash2 size={15} /></button></div>}</article>)}</div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Done")}</button></div></div></Modal>;
}

function ReportMessageModal({ message, onClose, onReported, notify }) {
  const [reason, setReason] = useState('spam');
  const [details, setDetails] = useState('');
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    try {
      await api.reportChannelMessage(message.id, { reason, details: details.trim() });
      notify(t("Report submitted. Moderators will review it confidentially."));
      onReported();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }

  return <Modal title={t("Report this message")} onClose={onClose}><form className="form-grid report-message-form" onSubmit={submit}><div className="report-privacy-note form-wide"><ShieldCheck size={19} /><div><b>{t("Your report is confidential")}</b><p>{t("Only trusted school moderators can see who submitted the report. Other users and the message author cannot see your identity.")}</p></div></div><Field label={t("Reason")}><select value={reason} onChange={(event) => setReason(event.target.value)}><option value="spam">{t("Spam")}</option><option value="harassment">{t("Harassment or bullying")}</option><option value="unsafe">{t("Unsafe content")}</option><option value="privacy">{t("Privacy concern")}</option><option value="misinformation">{t("Misinformation")}</option><option value="other">{t("Other")}</option></select></Field><Field label={t("Additional details (optional)")}><textarea value={details} onChange={(event) => setDetails(event.target.value)} maxLength="2000" rows="4" placeholder={t("Briefly explain the issue to the moderator.")} /></Field><div className="reported-message-preview form-wide"><small>{t("Reported message")}</small><p>{message.body}</p></div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}><Flag size={16} /> {saving ? t("Sending…") : t("Submit report")}</button></div></form></Modal>;
}

function ModerationQueueModal({ onClose, onChanged, notify }) {
  const [statusFilter, setStatusFilter] = useState('pending');
  const [reports, setReports] = useState([]);
  const [notes, setNotes] = useState({});
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);

  const load = useCallback(async (statusValue = statusFilter) => {
    setLoading(true);
    try {setReports((await api.messageReports(statusValue)) || []);}
    catch (err) {notify(err.message, 'error');} finally
    {setLoading(false);}
  }, [statusFilter, notify]);

  useEffect(() => {load(statusFilter);}, [statusFilter]);

  async function moderate(report, mode, action = 'none') {
    setSavingId(report.id);
    try {
      if (mode === 'review') await api.reviewMessageReport(report.id);else
      if (mode === 'dismiss') await api.dismissMessageReport(report.id, { moderator_note: notes[report.id] || '' });else
      await api.resolveMessageReport(report.id, { action, moderator_note: notes[report.id] || '' });
      notify(mode === 'review' ? t("Report moved to review.") : mode === 'dismiss' ? t("Report dismissed.") : t("Moderation action applied."));
      await load(statusFilter);
      await onChanged();
    } catch (err) {notify(err.message, 'error');} finally {setSavingId(null);}
  }

  const openStatuses = ['pending', 'reviewing'];
  return <Modal title={t("Anonymous moderation queue")} onClose={onClose}><div className="moderation-queue"><PortalTabs active={statusFilter} onChange={setStatusFilter} items={[["pending", "Pending"], ["reviewing", "Reviewing"], ["resolved", "Resolved"], ["dismissed", "Dismissed"]]} /><div className="moderation-list">{loading && <ChannelListSkeleton count={3} />}{!loading && reports.map((report) => <article className="moderation-card" key={report.id}><header><div><Badge>{report.reason}</Badge>{report.message_is_anonymous && <span className="anonymous-report-badge"><ShieldAlert size={13} /> {t("Anonymous post")}</span>}</div><time>{dateTimeText(report.created_at)}</time></header><blockquote>{report.message_body}</blockquote><div className="moderation-identities"><span>{t("Author")} <b>{report.sender_name}</b></span><span>{t("Reporter")} <b>{report.reporter_name}</b></span><span>{t("Channel")} <b>{report.channel_name}</b></span></div>{report.details && <p className="report-details"><b>{t("Report details:")}</b> {report.details}</p>}{openStatuses.includes(report.status) ? <><Field label={t("Moderator note")}><textarea value={notes[report.id] || ''} onChange={(event) => setNotes((current) => ({ ...current, [report.id]: event.target.value }))} maxLength="2000" rows="2" /></Field><footer>{report.status === 'pending' && <button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'review')}>{t("Start review")}</button>}<button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'dismiss')}>{t("Dismiss")}</button><button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'resolve', 'none')}>{t("Resolve only")}</button><button className="button danger small" disabled={savingId === report.id} onClick={() => moderate(report, 'resolve', 'content_removed')}>{t("Remove content")}</button><button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'resolve', 'muted_24h')}>{t("Mute 24h")}</button><button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'resolve', 'muted_7d')}>{t("Mute 7d")}</button></footer></> : <div className="moderation-result"><Badge>{report.status}</Badge><span>{label(report.action)}{report.reviewed_by_name ? ` · ${report.reviewed_by_name}` : ''}</span>{report.moderator_note && <p>{report.moderator_note}</p>}</div>}</article>)}{!loading && !reports.length && <Empty text={t("No reports with this status.")} />}</div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Done")}</button></div></div></Modal>;
}

function MessagesPage({ user, data, notify, navigationContext }) {
  const [tab, setTab] = useState('direct');
  const [channels, setChannels] = useState(data.messageChannels || []);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [body, setBody] = useState('');
  const [anonymous, setAnonymous] = useState(false);
  const [replyTo, setReplyTo] = useState(null);
  const [search, setSearch] = useState('');
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [channelError, setChannelError] = useState('');
  const [messageError, setMessageError] = useState('');
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [membersOpen, setMembersOpen] = useState(false);
  const [reportingMessage, setReportingMessage] = useState(null);
  const [moderationOpen, setModerationOpen] = useState(false);
  const [overview, setOverview] = useState(null);
  const [overviewError, setOverviewError] = useState('');
  const handledIntentRef = useRef(null);

  const visibleChannels = channels.filter((channel) => channel.kind === tab);
  const activeChannel = visibleChannels.find((channel) => channel.id === activeId) || visibleChannels[0] || null;
  const staffInterface = ['counselor', 'organization'].includes(user.role);
  const moderationEnabled = isTaskManager(user) || user.role === 'organization';
  const canCreate = tab === 'direct' || tab === 'discussion' || isTaskManager(user) || user.role === 'organization';
  const canAccept = activeChannel?.kind === 'discussion' && (isTaskManager(user) || ['owner', 'moderator'].includes(activeChannel?.my_role));
  const canManageMembers = activeChannel?.kind !== 'direct' && activeChannel?.is_member && (isTaskManager(user) || user.role === 'organization' || ['owner', 'moderator'].includes(activeChannel?.my_role));

  const refreshOverview = useCallback(async () => {
    if (!moderationEnabled && !staffInterface) return null;
    setOverviewError('');
    try {
      const nextOverview = await api.messagingOverview();
      setOverview(nextOverview);
      return nextOverview;
    } catch (err) {
      notify(err.message, 'error');
      setOverviewError(err.message);
      return null;
    }
  }, [moderationEnabled, staffInterface, notify]);

  const refreshChannels = useCallback(async (kind = tab, term = search, preferredId = activeId) => {
    setLoadingChannels(true);
    setChannelError('');
    try {
      const items = await api.messageChannels(kind, term);
      setChannels(items || []);
      setActiveId((current) => {
        if (items.some((item) => item.id === preferredId)) return preferredId;
        if (items.some((item) => item.id === current)) return current;
        return items[0]?.id || null;
      });
      return items || [];
    } catch (err) {
      notify(err.message, 'error');
      setChannelError(err.message);
      return [];
    } finally {
      setLoadingChannels(false);
    }
  }, [tab, search, activeId, notify]);

  const loadMessages = useCallback(async (channel) => {
    if (!channel?.is_member) {setMessages([]);setMessageError('');return;}
    setLoadingMessages(true);
    setMessageError('');
    try {
      const items = await api.channelMessages(channel.id);
      setMessages([...(items || [])].reverse());
      await api.markChannelRead(channel.id);
      setChannels((current) => current.map((item) => item.id === channel.id ? { ...item, unread_count: 0 } : item));
    } catch (err) {
      notify(err.message, 'error');
      setMessageError(err.message);
    } finally {
      setLoadingMessages(false);
    }
  }, [notify]);

  useEffect(() => {
    const timer = window.setTimeout(() => refreshChannels(tab, search, null), 220);
    return () => window.clearTimeout(timer);
  }, [tab, search]);

  useEffect(() => {refreshOverview();}, [refreshOverview]);

  useEffect(() => {
    const intentKey = navigationContext?.action === 'message' && navigationContext.memberId ? `${navigationContext.memberId}-${navigationContext.serviceTitle || ''}` : null;
    if (!intentKey || handledIntentRef.current === intentKey) return;
    handledIntentRef.current = intentKey;
    setTab('direct');
    setSearch('');
    if (navigationContext.serviceTitle) setBody(tx`I’m interested in ${navigationContext.serviceTitle}. Could you tell me more about it?`);
    api.openDirectChannel(Number(navigationContext.memberId)).then(channelSaved).catch((err) => notify(err.message, 'error'));
  }, [navigationContext, notify]);

  useEffect(() => {
    setReplyTo(null);
    setAnonymous(false);
    loadMessages(activeChannel);
  }, [activeChannel?.id, activeChannel?.is_member]);

  async function send(event) {
    event.preventDefault();
    if (!activeChannel || !body.trim()) return;
    setSaving(true);
    try {
      await api.create('channel-messages', {
        channel: activeChannel.id,
        body: body.trim(),
        is_anonymous: anonymous,
        ...(replyTo ? { parent: replyTo.id } : {})
      });
      setBody('');
      setReplyTo(null);
      await loadMessages(activeChannel);
      await refreshChannels(tab, search, activeChannel.id);
      await refreshOverview();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function join() {
    try {
      await api.joinChannel(activeChannel.id);
      const items = await refreshChannels(tab, search, activeChannel.id);
      const joined = items.find((item) => item.id === activeChannel.id);
      if (joined) await loadMessages(joined);
      await refreshOverview();
      notify(t("You joined the channel."));
    } catch (err) {notify(err.message, 'error');}
  }

  async function leave() {
    try {
      await api.leaveChannel(activeChannel.id);
      setMessages([]);
      await refreshChannels(tab, search, null);
      await refreshOverview();
      notify(t("You left the channel."));
    } catch (err) {notify(err.message, 'error');}
  }

  async function accept(message) {
    try {
      const accepted = await api.acceptChannelMessage(message.id);
      setMessages((current) => current.map((item) => ({ ...item, is_accepted_answer: item.id === accepted.id })));
      notify(t("Reply marked as the accepted answer."));
    } catch (err) {notify(err.message, 'error');}
  }

  async function channelSaved(channel) {
    setOpen(false);
    setTab(channel.kind);
    setSearch('');
    const items = await refreshChannels(channel.kind, '', channel.id);
    if (!items.some((item) => item.id === channel.id)) setChannels((current) => [channel, ...current]);
    setActiveId(channel.id);
    await refreshOverview();
  }

  return <div className={`messaging-page section-stack ${user.role === 'student' ? 'student-portal' : ''}`}>
    {staffInterface && <section className="staff-messaging-overview"><div className="staff-messaging-copy"><span><MessageCircle size={22} /></span><div><small>{user.role === 'counselor' ? t("COUNSELOR INBOX") : t("SCHOOL COMMUNICATIONS")}</small><h2>{user.role === 'counselor' ? t("Student and school conversations") : t("Keep your school connected")}</h2><p>{user.role === 'counselor' ? t("Message assigned students, coordinate with school staff and moderate shared channels.") : t("Contact your students, teachers and assigned counselors from one secure inbox.")}</p></div></div>{overview ? <div className="staff-messaging-stats"><div><strong>{overview.unread_total || 0}</strong><span>{t("Unread")}</span></div><div><strong>{overview.students_total || 0}</strong><span>{user.role === 'counselor' ? t("Assigned students") : t("School students")}</span></div><div><strong>{overview.channel_counts?.direct || 0}</strong><span>{t("Direct chats")}</span></div><div><strong>{(overview.channel_counts?.group || 0) + (overview.channel_counts?.community || 0)}</strong><span>{t("Managed spaces")}</span></div><div className={overview.pending_reports ? "attention" : ''}><strong>{overview.pending_reports || 0}</strong><span>{t("Open reports")}</span></div></div> : overviewError ? <InlineLoadError message={overviewError} onRetry={refreshOverview} /> : <StaffStatsSkeleton />}<div className="staff-messaging-actions"><button className="button primary" onClick={() => {setTab('direct');setActiveId(null);setOpen(true);}}><MessageCircle size={16} /> {t("Message a student")}</button><button className="button quiet" onClick={() => {setTab('group');setActiveId(null);setOpen(true);}}><UsersRound size={16} /> {t("Create group")}</button><button className="button quiet" onClick={() => setModerationOpen(true)}><ShieldAlert size={16} /> {t("Moderation queue")}{overview?.pending_reports ? ` · ${overview.pending_reports}` : ''}</button></div></section>}
    <div className="portal-toolbar messaging-toolbar"><PortalTabs active={tab} onChange={(next) => {setTab(next);setActiveId(null);}} items={[["direct", "Direct"], ["group", "Group"], ["community", "Community"], ["discussion", "Discussions"]]} /><div className="messaging-toolbar-actions">{moderationEnabled && !staffInterface && <button className="button quiet" onClick={() => setModerationOpen(true)}><ShieldAlert size={17} /> {t("Moderation")}{overview?.pending_reports ? ` · ${overview.pending_reports}` : ''}</button>}{canCreate && <button className="button primary" onClick={() => setOpen(true)}><Plus size={17} /> {tab === 'direct' ? t("New message") : tab === 'discussion' ? t("New discussion") : t("New channel")}</button>}</div></div>
    <div className="messages-shell">
      <aside className="channel-sidebar"><label className="channel-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={tx`Search ${tab}`} aria-label={tx`Search ${tab} channels`} /></label><div className="channel-list" aria-busy={loadingChannels}>{loadingChannels ? <ChannelListSkeleton /> : channelError ? <InlineLoadError message={channelError} onRetry={() => refreshChannels(tab, search, activeId)} /> : <>{visibleChannels.map((channel) => <button type="button" key={channel.id} className={`channel-item ${activeChannel?.id === channel.id ? 'active' : ''}`} onClick={() => setActiveId(channel.id)}><span className="avatar">{initials(channel.display_name)}</span><span><b>{channel.display_name}</b><small>{channel.last_message?.body || channel.description || tx`${channel.members_count} members`}</small></span>{channel.unread_count > 0 && <strong aria-label={tx`${channel.unread_count} unread`}>{channel.unread_count > 99 ? '99+' : channel.unread_count}</strong>}</button>)}{!visibleChannels.length && <Empty text={t("No channels found in this section.")} />}</>}</div></aside>
      {activeChannel ? <section className="message-thread"><header><div><b>{activeChannel.display_name}</b><small>{label(activeChannel.kind)}{activeChannel.school_name ? ` · ${activeChannel.school_name}` : ''} · {activeChannel.members_count} {t("members")}</small></div><div className="channel-actions">{canManageMembers && <button className="button quiet small" onClick={() => setMembersOpen(true)}><UsersRound size={15} /> {t("Manage members")}</button>}{activeChannel.is_public && !activeChannel.is_member && <button className="button primary small" onClick={join}>{t("Join")}</button>}{activeChannel.is_member && activeChannel.kind !== 'direct' && activeChannel.my_role !== 'owner' && <button className="button quiet small" onClick={leave}>{t("Leave")}</button>}<Badge>{activeChannel.kind}</Badge></div></header>
        {activeChannel.is_member ? <><div className="message-list" aria-busy={loadingMessages}>{loadingMessages ? <MessageListSkeleton /> : messageError ? <InlineLoadError message={messageError} onRetry={() => loadMessages(activeChannel)} /> : <>{messages.map((message) => {const mine = message.sender_id === user.id;return <article key={message.id} className={`message-bubble ${mine ? 'mine' : ''} ${message.parent ? 'reply' : ''} ${message.is_accepted_answer ? 'accepted' : ''}`}>{message.parent_preview && <button type="button" className="parent-preview" onClick={() => document.getElementById(`message-${message.parent}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}>{t("Reply to:")} {message.parent_preview.body}</button>}<div id={`message-${message.id}`}><b>{message.sender_name}{message.is_anonymous ? t("· Anonymous") : ''}</b>{message.is_accepted_answer && <span className="accepted-label"><CheckCircle2 size={13} /> {t("Accepted answer")}</span>}</div><p>{message.deleted_at ? t("Message deleted") : message.body}</p><footer><time>{dateTimeText(message.created_at)}{message.is_edited ? t("· edited") : ''}</time>{!message.deleted_at && <button type="button" onClick={() => setReplyTo(message)}>{t("Reply")}</button>}{!mine && !message.deleted_at && <button type="button" disabled={message.is_reported_by_me} onClick={() => setReportingMessage(message)}><Flag size={11} /> {message.is_reported_by_me ? t("Reported") : t("Report")}</button>}{canAccept && message.parent && !message.deleted_at && !message.is_accepted_answer && <button type="button" onClick={() => accept(message)}>{t("Accept answer")}</button>}</footer></article>;})}{!messages.length && <Empty text={t("Start the conversation with the first message.")} />}</>}</div><form className="message-compose" onSubmit={send}><div>{replyTo && <div className="replying-to"><span>{t("Replying to")} <b>{replyTo.sender_name}</b></span><button type="button" className="icon-button" onClick={() => setReplyTo(null)} aria-label={t("Cancel reply")}><X size={15} /></button></div>}<textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder={t("Write a message…")} rows="2" />{['community', 'discussion'].includes(activeChannel.kind) && <CheckboxControl className="compact anonymous-toggle" checked={anonymous} onChange={(event) => setAnonymous(event.target.checked)}>{t("Post anonymously")}</CheckboxControl>}</div><button className="button primary" disabled={saving || !body.trim()} aria-busy={saving}><Send size={17} /> {saving ? t("Sending…") : t("Send")}</button></form></> : <div className="message-join-state"><UsersRound size={42} /><h3>{activeChannel.display_name}</h3><p>{activeChannel.description || t("Join this channel to read and send messages.")}</p><button className="button primary" onClick={join}>{t("Join channel")}</button></div>}
      </section> : <section className="message-empty-state"><MessageCircle size={44} /><h3>{t("Select a conversation")}</h3><p>{t("Select a channel or start a new conversation.")}</p></section>}
    </div>
    {open && <MessageChannelForm kind={tab} user={user} onClose={() => setOpen(false)} onSaved={channelSaved} notify={notify} />}
    {membersOpen && activeChannel && <ChannelMembersModal channel={activeChannel} user={user} onClose={() => setMembersOpen(false)} onChanged={async () => {await refreshChannels(tab, search, activeChannel.id);await refreshOverview();}} notify={notify} />}
    {reportingMessage && <ReportMessageModal message={reportingMessage} onClose={() => setReportingMessage(null)} onReported={async () => {setMessages((current) => current.map((item) => item.id === reportingMessage.id ? { ...item, is_reported_by_me: true } : item));setReportingMessage(null);await refreshOverview();}} notify={notify} />}
    {moderationOpen && moderationEnabled && <ModerationQueueModal onClose={() => setModerationOpen(false)} onChanged={refreshOverview} notify={notify} />}
  </div>;
}

function ProgramServiceForm({ service, user, data, defaultStudentId = null, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [unlimited, setUnlimited] = useState(Boolean(service?.unlimited));
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    const payload = {
      student: service?.student || Number(values.get('student')),
      name: values.get('name'),
      category: values.get('category'),
      status: values.get('status'),
      unlimited,
      total_hours: unlimited ? null : Number(values.get('total_hours')),
      used_hours: Number(values.get('used_hours') || 0),
      mentor: user.role === 'counselor' ? user.id : service?.mentor || null
    };
    try {
      if (service) await api.update('program-services', service.id, payload);else
      await api.create('program-services', payload);
      notify(service ? t("Program service updated.") : t("Program service assigned."));
      onSaved();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={service ? t("Edit program service") : t("Assign program service")} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <Field label={t("Student")} hint={t("The currently selected student is preselected.")}><select name="student" defaultValue={service?.student || defaultStudentId || ''} required disabled={Boolean(service)}><option value="" disabled>{t("Select student")}</option>{data.students.map((student) => <option value={student.id} key={student.id}>{fullName(student.user_detail)}</option>)}</select></Field>
    <Field label={t("Service name")}><input name="name" defaultValue={service?.name || ''} required /></Field>
    <Field label={t("Category")}><input name="category" defaultValue={service?.category || ''} placeholder={t("Essay, mentorship, admissions…")} /></Field>
    <Field label={t("Status")}><select name="status" defaultValue={service?.status || 'active'}>{['active', 'pending', 'completed'].map((status) => <option value={status} key={status}>{label(status)}</option>)}</select></Field>
    <Field label={t("Allocated hours")}><input name="total_hours" type="number" min="0.5" step="0.5" defaultValue={service?.total_hours || ''} required={!unlimited} disabled={unlimited} /></Field>
    <Field label={t("Used hours")}><input name="used_hours" type="number" min="0" step="0.5" defaultValue={service?.used_hours || 0} /></Field>
    <CheckboxControl className="form-wide" checked={unlimited} onChange={(event) => setUnlimited(event.target.checked)}>{t("Unlimited service access")}</CheckboxControl>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{saving ? t("Saving…") : t("Save service")}</button></div>
  </form></Modal>;
}

function ProgramUsagePage({ user, data, reload, notify }) {
  const manager = isCounselor(user);
  const [selectedStudentId, setSelectedStudentId] = useState(() => manager && data.students[0] ? String(data.students[0].id) : 'all');
  const [status, setStatus] = useState('all');
  const [category, setCategory] = useState('all');
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(false);
  const { confirm, dialog } = useActionDialog();
  useEffect(() => {
    if (!manager || !data.students.length) return;
    if (selectedStudentId !== 'all' && !data.students.some((item) => String(item.id) === selectedStudentId)) {
      setSelectedStudentId(String(data.students[0].id));
    }
  }, [data.students, manager, selectedStudentId]);
  const selectedStudentNumericId = selectedStudentId === 'all' ? null : Number(selectedStudentId);
  const scopedServices = manager && selectedStudentNumericId ?
  data.programServices.filter((item) => item.student === selectedStudentNumericId) :
  data.programServices;
  const categories = [...new Set(scopedServices.map((item) => item.category).filter(Boolean))].sort();
  const visible = scopedServices.filter((item) => (status === 'all' || item.status === status) && (category === 'all' || item.category === category));
  const finite = scopedServices.filter((item) => !item.unlimited);
  const total = finite.reduce((sum, item) => sum + Number(item.total_hours || 0), 0);
  const used = finite.reduce((sum, item) => sum + Number(item.used_hours || 0), 0);
  const remaining = Math.max(total - used, 0);
  async function remove(service) {
    if (!await confirm({ title: t("Remove service"), description: tx`Remove ${service.name} from this student’s program?`, confirmLabel: t("Remove"), tone: 'danger' })) return;
    try {await api.remove('program-services', service.id);notify(t("Program service removed."));reload();} catch (err) {notify(err.message, 'error');}
  }
  return <div className="section-stack student-portal program-usage-page">
    <section className="portal-hero usage-hero"><div><span className="eyebrow">{manager ? t("STUDENT SERVICE MANAGEMENT") : t("YOUR NASEEB PROGRAM")}</span><h2>{manager ? t("Program services") : t("Program usage")}</h2><p>{manager ? t("Assign services and keep each student’s usage balance accurate.") : t("See your allocated services, mentor status, and remaining hours.")}</p></div>{manager ? <button className="button light" onClick={() => {setEditing(null);setOpen(true);}}><Plus size={17} /> {t("Assign service")}</button> : <ListChecks size={58} />}</section>
    {manager && <StudentWorkspaceSelector students={data.students} value={selectedStudentId} onChange={(value) => {setSelectedStudentId(value);setStatus('all');setCategory('all');}} metrics={[["Services", scopedServices.length], ["Active", scopedServices.filter((item) => item.status === 'active').length], ["Mentor pending", scopedServices.filter((item) => !item.mentor_name).length]]} />}
    <div className="usage-summary"><article><span>{t("Total allocated")}</span><strong>{formatNumberLocale(total, { maximumFractionDigits: 1 })} {t("h")}</strong><small>{t("Finite services")}</small></article><article><span>{t("Hours used")}</span><strong>{formatNumberLocale(used, { maximumFractionDigits: 1 })} {t("h")}</strong><small>{total ? tx`${Math.round(used / total * 100)}% of allocation` : t("No finite allocation")}</small></article><article><span>{t("Remaining")}</span><strong>{formatNumberLocale(remaining, { maximumFractionDigits: 1 })} {t("h")}</strong><small>{t("Across active services")}</small></article><article><span>{t("Unlimited")}</span><strong>{formatNumberLocale(scopedServices.filter((item) => item.unlimited).length)}</strong><small>{t("Services without hour limits")}</small></article></div>
    <div className="usage-toolbar"><div><Filter size={16} /><b>{t("Filter services")}</b></div><label>{t("Status")}<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">{t("All statuses")}</option>{['active', 'pending', 'completed'].map((item) => <option value={item} key={item}>{label(item)}</option>)}</select></label><label>{t("Category")}<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="all">{t("All categories")}</option>{categories.map((item) => <option value={item} key={item}>{item}</option>)}</select></label><small>{visible.length} {t("service")}{visible.length === 1 ? '' : t("s")}</small></div>
    <div className="service-list">{visible.map((service) => {
        const serviceTotal = Number(service.total_hours || 0);
        const serviceUsed = Number(service.used_hours || 0);
        const percent = serviceTotal ? Math.min(100, serviceUsed / serviceTotal * 100) : 0;
        return <article className={`service-card service-${service.status}`} key={service.id}><header><div><span>{service.category || t("Education support")}</span><h3>{service.name}</h3>{manager && <p>{service.student_name || t("Student")}</p>}</div><Badge>{service.status}</Badge></header><div className="service-balance"><div><strong>{service.unlimited ? '∞' : tx`${service.remaining_hours ?? 0}h`}</strong><span>{service.unlimited ? t("Unlimited access") : t("Remaining")}</span></div><div><strong>{serviceUsed}{t("h")}</strong><span>{t("Used")}</span></div><div><strong>{service.unlimited ? t("No limit") : tx`${serviceTotal}h`}</strong><span>{t("Allocated")}</span></div></div><div className={`service-bar ${service.unlimited ? 'unlimited' : ''}`} aria-label={service.unlimited ? t("Unlimited service access") : tx`${Math.round(percent)} percent used`}><span style={{ width: `${service.unlimited ? 100 : percent}%` }} /></div><div className="service-meta"><span><UserRound size={14} /> {service.mentor_name || t("Mentor pending")}</span><span>{service.mentor_name ? label(service.mentor_role || t("counselor")) : t("Assignment needed")}</span></div>{manager && <footer><button className="button quiet small" onClick={() => {setEditing(service);setOpen(true);}}><Pencil size={14} /> {t("Edit")}</button><button className="icon-button danger" onClick={() => remove(service)} aria-label={tx`Remove ${service.name}`}><Trash2 size={15} /></button></footer>}</article>;
      })}{!visible.length && <Empty text={scopedServices.length ? t("No services match these filters.") : manager ? t("No services assigned to this student yet.") : t("No program services have been assigned yet.")} />}</div>
    {open && <ProgramServiceForm service={editing} user={user} data={data} defaultStudentId={selectedStudentNumericId} notify={notify} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} />}
    {dialog}
  </div>;
}

function ResourceIndexPage({ data, query, setPage }) {
  const filtered = data.resourceLibrary.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  const groups = Object.groupBy ? Object.groupBy(filtered, (item) => item.category) : filtered.reduce((acc, item) => ({ ...acc, [item.category]: [...(acc[item.category] || []), item] }), {});
  function open(item) {if (item.destination && PAGE_META[item.destination]) setPage(item.destination);else if (item.external_url) window.open(item.external_url, '_blank', 'noopener,noreferrer');}
  return <div className="section-stack student-portal"><label className="resource-search"><Search size={20} /><input value={query} readOnly placeholder={t("Use the search field in the top header")} /><span>{filtered.length} {t("resources")}</span></label>{Object.entries(groups).map(([category, items], index) => <section className="resource-group" key={category} style={{ '--group-index': index }}><header><span><LibraryBig size={20} /></span><div><h2>{category}</h2><p>{items.length} {t("student resources")}</p></div></header><div>{items.map((item) => <button key={item.id} onClick={() => open(item)}><span>{String(item.sort_order + 1).padStart(2, '0')}</span><div><b>{item.title}</b><small>{item.description}</small></div><ChevronRight size={18} /></button>)}</div></section>)}{!filtered.length && <Empty text={t("No resources found.")} />}</div>;
}

function EssayLabPage({ user, data, query, reload, notify }) {
  const approved = data.essays.filter((item) => item.status === 'approved').length;
  const active = data.essays.filter((item) => item.status !== 'approved').length;
  return <div className="section-stack student-portal"><section className="portal-hero essay-hero"><div><span className="eyebrow">{t("NASEEB ESSAY LAB")}</span><h2>{t("Ideas into impact.")}</h2><p>{t("Manage drafts, revisions, and counselor feedback in one place.")}</p></div><div className="essay-progress"><div><strong>{data.essays.length}</strong><span>{t("Total")}</span></div><div><strong>{active}</strong><span>{t("Active")}</span></div><div><strong>{approved}</strong><span>{t("Approved")}</span></div></div></section><ResourceSection title={t("Active essays & supplements")} resource="essays" {...{ user, data, query, reload, notify }} /></div>;
}

function ApplicationsPortalPage({ user, data, query, reload, notify, setPage }) {
  const submitted = data.applications.filter((item) => ['submitted', 'accepted'].includes(item.status)).length;
  return <div className="section-stack student-portal"><section className="portal-hero application-hero"><div><span className="eyebrow">{t("APPLICATION TRACKER")}</span><h2>{t("Manage every application.")}</h2><p>{t("Track your university list, statuses, deadlines, and scholarship information.")}</p></div><button className="button light" onClick={() => setPage('college_search')}><Search size={17} /> {t("Add a university")}</button></section><div className="stat-grid"><Stat label={t("Universities")} value={data.applications.length} /><Stat label={t("Submitted")} value={submitted} /><Stat label={t("In progress")} value={data.applications.filter((item) => ['shortlisted', 'applying'].includes(item.status)).length} /><Stat label={t("Decisions")} value={data.applications.filter((item) => ['accepted', 'rejected', 'waitlisted'].includes(item.status)).length} /></div><ResourceSection title={t("My university list")} resource="applications" {...{ user, data, query, reload, notify }} /></div>;
}

const money = (value) => formatCurrencyLocale(value);

function universityFit(university, student) {
  if (!student) return { score: 0, label: 'Profile needed' };
  let score = 20;
  const targets = String(student.target_countries || '').toLowerCase();
  if (targets.includes(String(university.country || '').toLowerCase())) score += 25;
  if (!university.sat_min || Number(student.sat_score || 0) >= Number(university.sat_min)) score += 25;
  if (!university.net_price_usd || !student.budget_usd || Number(university.net_price_usd) <= Number(student.budget_usd)) score += 15;
  if (!student.scholarship_needed || university.offers_international_aid || university.offers_merit_aid) score += 15;
  const bounded = Math.min(score, 100);
  return { score: bounded, label: bounded >= 80 ? 'Strong fit' : bounded >= 60 ? 'Good fit' : 'Explore' };
}

function scholarshipRequirements(item) {
  return [
  item.requires_transcript && 'Transcript', item.requires_essay && 'Essay',
  item.requires_recommendation && 'Recommendation', item.requires_financial_documents && 'Financial documents',
  item.requires_cv && 'CV', item.requires_portfolio && 'Portfolio'].
  filter(Boolean);
}

function eligibleScholarship(item, student) {
  if (!student) return false;
  if (item.min_gpa && Number(student.gpa || 0) < Number(item.min_gpa)) return false;
  if (item.min_ielts && Number(student.ielts_score || 0) < Number(item.min_ielts)) return false;
  if (item.min_sat && Number(student.sat_score || 0) < Number(item.min_sat)) return false;
  return !item.eligible_grades || String(item.eligible_grades).split(',').map((value) => value.trim()).includes(String(student.grade));
}

function CollegeSearchPage({ data, query, reload, notify }) {
  const [tab, setTab] = useState('universities');
  const [country, setCountry] = useState('all');
  const [institutionType, setInstitutionType] = useState('all');
  const [maxPrice, setMaxPrice] = useState('all');
  const [minimumAcceptance, setMinimumAcceptance] = useState('0');
  const [aid, setAid] = useState('all');
  const [testOptional, setTestOptional] = useState(false);
  const [scoreMatch, setScoreMatch] = useState(false);
  const [scholarshipType, setScholarshipType] = useState('all');
  const [funding, setFunding] = useState('all');
  const [scope, setScope] = useState('all');
  const [eligibleOnly, setEligibleOnly] = useState(false);
  const [research, setResearch] = useState(null);
  const [researchLoading, setResearchLoading] = useState(true);
  const [researchSaving, setResearchSaving] = useState(false);
  const [personalitySaving, setPersonalitySaving] = useState(false);
  const [personalityEditor, setPersonalityEditor] = useState(null);
  const [researchError, setResearchError] = useState('');
  const student = ownStudent(data);
  const researchMap = new Map((research?.recommendations || []).map((item) => [item.university.id, item]));
  const countries = [...new Set(data.universities.map((item) => item.country))].sort();
  const added = new Set(data.applications.map((item) => item.university));

  useEffect(() => {
    let active = true;
    setResearchLoading(true);
    api.collegeResearch().then((result) => {if (active) {setResearch(result);setResearchError('');}}).catch((error) => {if (active) setResearchError(error.message);}).finally(() => {if (active) setResearchLoading(false);});
    return () => {active = false;};
  }, []);

  async function refreshResearch() {
    setResearchLoading(true);setResearchError('');
    try {setResearch(await api.collegeResearch());} catch (error) {setResearchError(error.message);} finally {setResearchLoading(false);}
  }

  async function completeResearchProfile(payload) {
    setResearchSaving(true);setResearchError('');
    try {
      const result = await api.updateCollegeResearchProfile(payload);
      setResearch(result);
      notify(t("Profile details saved and college research updated."));
      reload();
    } catch (error) {setResearchError(error.message);} finally {setResearchSaving(false);}
  }
  async function completePersonalityAssessment(answers) {
    setPersonalitySaving(true);setResearchError('');
    try {
      await api.submitPersonalityAssessment(answers);
      setPersonalityEditor(null);
      await refreshResearch();
      notify(t("Personality profile saved and university matches updated."));
    } catch (error) {setResearchError(error.message);} finally {setPersonalitySaving(false);}
  }
  async function editPersonalityAssessment() {
    setResearchError('');
    try {setPersonalityEditor(await api.personalityAssessment());} catch (error) {setResearchError(error.message);}
  }
  const items = data.universities.filter((item) => {
    const aidMatch = aid === 'all' || aid === 'need' && item.offers_need_based_aid || aid === 'merit' && item.offers_merit_aid || aid === 'international' && item.offers_international_aid || aid === 'full_need' && item.meets_full_need;
    return (country === 'all' || item.country === country) && (
    institutionType === 'all' || item.institution_type === institutionType) && (
    maxPrice === 'all' || Number(item.net_price_usd || Infinity) <= Number(maxPrice)) &&
    Number(item.acceptance_rate || 0) >= Number(minimumAcceptance) && (
    !testOptional || item.test_optional) && (
    !scoreMatch || !item.sat_min || Number(student?.sat_score || 0) >= Number(item.sat_min)) &&
    aidMatch && JSON.stringify(item).toLowerCase().includes(query.toLowerCase());
  }).sort((a, b) => (researchMap.get(b.id)?.match_score ?? universityFit(b, student).score) - (researchMap.get(a.id)?.match_score ?? universityFit(a, student).score));
  const scholarships = data.scholarships.filter((item) => (scholarshipType === 'all' || item.scholarship_type === scholarshipType) && (
  funding === 'all' || item.funding_level === funding) && (scope === 'all' || item.scope === scope) && (
  !eligibleOnly || eligibleScholarship(item, student)) && JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  async function shortlist(university) {try {await api.create('applications', { student: student?.id, university: university.id, program: student?.target_major || 'Undeclared', tier: 'target', status: 'shortlisted', deadline: university.application_deadline, scholarship_deadline: university.scholarship_deadline });notify(tx`${university.name} added to your shortlist.`);reload();} catch (err) {notify(err.message, 'error');}}
  return <div className="section-stack student-portal">
    <section className="college-banner"><div><span className="eyebrow">{t("NASEEB COLLEGE & AID FINDER")}</span><h2>{t("Universities, scholarships & aid")}</h2><p>{t("Filter profile-matched options by price, acceptance, testing, and financial aid.")}</p></div><School size={80} /></section>
    <div className="finder-tabs"><PortalTabs active={tab} onChange={setTab} items={[["universities", "Universities"], ["scholarships", "Scholarships & Aid"], ["aid", "What you need"]]} /></div>
    {tab === 'universities' && researchLoading && <div className="college-research-state"><RefreshCw className="spin" size={22} /><div><b>{t("Analyzing your profile")}</b><p>{t("Checking SAT, GPA, IELTS, major, budget, and portfolio evidence.")}</p></div></div>}
    {tab === 'universities' && researchError && <div className="college-research-state error"><X size={22} /><div><b>{t("Research yuklanmadi")}</b><p>{researchError}</p></div><button className="button quiet small" onClick={refreshResearch}>{t("Retry")}</button></div>}
    {tab === 'universities' && !researchLoading && research && !research.ready && research.missing_fields?.length > 0 && <CollegeProfileQuestions research={research} saving={researchSaving} onComplete={completeResearchProfile} />}
    {tab === 'universities' && !researchLoading && research && !research.ready && !research.missing_fields?.length && !research.personality?.ready && <PersonalityAssessmentCard personality={research.personality} saving={personalitySaving} onComplete={completePersonalityAssessment} />}
    {tab === 'universities' && !researchLoading && personalityEditor && <PersonalityAssessmentCard personality={personalityEditor} saving={personalitySaving} onComplete={completePersonalityAssessment} onCancel={() => setPersonalityEditor(null)} />}
    {tab === 'universities' && !researchLoading && research?.ready && !personalityEditor && <><CollegeResearchOverview research={research} onRefresh={refreshResearch} onEditPersonality={editPersonalityAssessment} /><CollegeAIAdvisor /><div className="finder-layout">
      <aside className="filter-panel"><header><Filter size={18} /><b>{t("University filters")}</b></header><label>{t("Country")}<select value={country} onChange={(event) => setCountry(event.target.value)}><option value="all">{t("All countries")}</option>{countries.map((item) => <option key={item}>{item}</option>)}</select></label><label>{t("Institution type")}<select value={institutionType} onChange={(event) => setInstitutionType(event.target.value)}><option value="all">{t("Public & private")}</option><option value="public">{t("Public")}</option><option value="private">{t("Private")}</option></select></label><label>{t("Maximum net price")}<select value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)}><option value="all">{t("Any price")}</option><option value="15000">{t("Up to $15,000")}</option><option value="25000">{t("Up to $25,000")}</option><option value="40000">{t("Up to $40,000")}</option></select></label><label>{t("Minimum acceptance")}<select value={minimumAcceptance} onChange={(event) => setMinimumAcceptance(event.target.value)}><option value="0">{t("Any rate")}</option><option value="10">10%+</option><option value="25">25%+</option><option value="50">50%+</option></select></label><label>{t("Aid type")}<select value={aid} onChange={(event) => setAid(event.target.value)}><option value="all">{t("Any aid")}</option><option value="need">{t("Need-based")}</option><option value="merit">{t("Merit")}</option><option value="international">{t("International aid")}</option><option value="full_need">{t("Meets full need")}</option></select></label><CheckboxControl className="compact" checked={testOptional} onChange={(event) => setTestOptional(event.target.checked)}>{t("Test optional only")}</CheckboxControl><CheckboxControl className="compact" checked={scoreMatch} onChange={(event) => setScoreMatch(event.target.checked)}>{t("My SAT matches")}</CheckboxControl></aside>
      <section className="finder-results"><header><div><span className="eyebrow">{t("PROFILE-BASED RESEARCH")}</span><h3>{formatNumberLocale(items.length)} {t("universities found")}</h3></div><small>{t("The match score is not an admission probability; it measures profile, preference, and affordability fit.")}</small></header><div className="university-results">{items.map((uni) => {const result = researchMap.get(uni.id);const fit = result ? { score: result.match_score, label: result.match_label } : universityFit(uni, student);return <article className="university-card" key={uni.id}><header><span className="rank">#{uni.ranking ? formatNumberLocale(uni.ranking) : '—'}</span><div><h3>{uni.name}</h3><p><MapPin size={14} /> {uni.city}, {uni.country} · {label(uni.institution_type)}</p></div><div className="university-fit"><span className="fit-badge">{formatPercentLocale(fit.score)} {label(fit.label)}</span>{result && <Badge>{result.admission_band}</Badge>}</div></header><div className="university-metrics"><div><span>{t("Acceptance")}</span><b>{uni.acceptance_rate ? formatPercentLocale(uni.acceptance_rate) : '—'}</b></div><div><span>{t("Net price")}</span><b>{money(uni.net_price_usd)}</b></div><div><span>{t("Average aid")}</span><b>{money(uni.average_aid_usd)}</b></div><div><span>{t("SAT range")}</span><b>{uni.sat_min ? `${formatNumberLocale(uni.sat_min)}–${uni.sat_max ? formatNumberLocale(uni.sat_max) : '—'}` : t("Optional/—")}</b></div></div>{result && <div className="research-breakdown">{Object.entries(result.score_breakdown).map(([name, value]) => <div key={name}><span>{label(name)}</span><div className="progress"><i style={{ width: `${Math.min(100, Number(value) * (name === 'academic' ? 2 : name === 'preferences' ? 4.5 : name === 'financial' ? 5 : 10))}%` }} /></div><b>{formatNumberLocale(value)}</b></div>)}</div>}<div className="aid-badges">{uni.offers_need_based_aid && <span>{t("Need-based")}</span>}{uni.offers_merit_aid && <span>{t("Merit")}</span>}{uni.offers_international_aid && <span>{t("International aid")}</span>}{uni.meets_full_need && <span>{t("Meets full need")}</span>}{uni.test_optional && <span>{t("Test optional")}</span>}</div>{result && <details className="research-details"><summary>{t("Why this result?")}</summary><div><ul>{result.reasons.map((reason) => <li key={reason}><CheckCircle2 size={13} /> {reason}</li>)}</ul>{result.gaps.length > 0 && <ul className="gaps">{result.gaps.map((gap) => <li key={gap}><Clock3 size={13} /> {gap}</li>)}</ul>}</div></details>}<footer><div><span>{t("Application:")} {dateText(uni.application_deadline)}</span><span>{t("Aid:")} {dateText(uni.scholarship_deadline)}</span></div>{added.has(uni.id) ? <span className="added"><Check size={17} /> {t("Shortlisted")}</span> : <button className="button primary small" onClick={() => shortlist(uni)}><Plus size={16} /> {t("Shortlist")}</button>}</footer></article>;})}{!items.length && <Empty text={t("No universities match these filters.")} />}</div></section>
    </div></>}
    {tab === 'scholarships' && <div className="finder-layout"><aside className="filter-panel"><header><DollarSign size={18} /><b>{t("Scholarship filters")}</b></header><label>{t("Scholarship type")}<select value={scholarshipType} onChange={(event) => setScholarshipType(event.target.value)}><option value="all">{t("All types")}</option><option value="merit">{t("Merit")}</option><option value="need_based">{t("Need-based")}</option><option value="leadership">{t("Leadership")}</option><option value="research">{t("Research")}</option><option value="full_ride">{t("Full ride")}</option></select></label><label>{t("Funding")}<select value={funding} onChange={(event) => setFunding(event.target.value)}><option value="all">{t("Any funding")}</option><option value="full">{t("Full funding")}</option><option value="partial">{t("Partial")}</option><option value="fixed">{t("Fixed amount")}</option></select></label><label>{t("Scope")}<select value={scope} onChange={(event) => setScope(event.target.value)}><option value="all">{t("National & International")}</option><option value="national">{t("National")}</option><option value="international">{t("International")}</option></select></label><CheckboxControl className="compact" checked={eligibleOnly} onChange={(event) => setEligibleOnly(event.target.checked)}>{t("Eligible for my profile")}</CheckboxControl></aside><section className="finder-results"><header><div><span className="eyebrow">{t("FUNDING OPTIONS")}</span><h3>{scholarships.length} {t("scholarships found")}</h3></div><small>{t("Eligibility is not a final decision; always verify the official requirements.")}</small></header><div className="scholarship-grid">{scholarships.map((item) => {const eligible = eligibleScholarship(item, student);return <article className="scholarship-card" key={item.id}><header><div><span>{label(item.scholarship_type)}</span><h3>{item.title}</h3><p>{item.provider}{item.university_name ? ` · ${item.university_name}` : ''}</p></div><Badge>{item.scope}</Badge></header><strong>{item.funding_level === 'fixed' ? money(item.amount_usd) : label(item.funding_level)}</strong><p>{item.coverage}</p><div className="eligibility-row"><span className={eligible ? "eligible" : "review"}>{eligible ? t("Profile match") : t("Review requirements")}</span><span>{t("Deadline")} {dateText(item.deadline)}</span></div><div className="score-requirements">{item.min_gpa && <span>{t("GPA")} {item.min_gpa}+</span>}{item.min_ielts && <span>{t("IELTS")} {item.min_ielts}+</span>}{item.min_sat && <span>{t("SAT")} {item.min_sat}+</span>}</div><div className="requirement-tags">{scholarshipRequirements(item).map((requirement) => <span key={requirement}>{requirement}</span>)}</div>{item.application_url && <a className="button quiet small" href={item.application_url} target="_blank" rel="noreferrer">{t("Application info")} <ExternalLink size={14} /></a>}</article>;})}{!scholarships.length && <Empty text={t("No matching scholarships found.")} />}</div></section></div>}
    {tab === 'aid' && <AidChecklist data={data} student={student} />}
  </div>;
}

function CollegeProfileQuestions({ research, saving, onComplete }) {
  const [answers, setAnswers] = useState(() => Object.fromEntries(research.questions.map((question) => [question.field, research.profile_snapshot?.[question.field] ?? ''])));
  function submit(event) {
    event.preventDefault();
    onComplete(answers);
  }
  return <section className="college-profile-questions"><div className="research-question-copy"><span><Sparkles size={20} /></span><div><span className="eyebrow">{t("PROFILE DATA REQUIRED")}</span><h2>{t("A few details are missing from your research profile")}</h2><p>{t("Your answers will be saved to your student profile and used to rank universities for you.")}</p></div></div><form onSubmit={submit}><div className="research-question-grid">{research.questions.map((question) => <label key={question.field}><span>{question.label}</span><input type={question.type} min={question.min} max={question.max} step={question.step || (question.type === 'number' ? '1' : undefined)} placeholder={question.placeholder} value={answers[question.field] ?? ''} onChange={(event) => setAnswers((current) => ({ ...current, [question.field]: event.target.value }))} required /></label>)}</div><footer><small>{research.questions.length} {t("answers required")}</small><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? <><RefreshCw className="spin" size={16} /> {t("Researching…")}</> : <><Search size={16} /> {t("Save & research")}</>}</button></footer></form></section>;
}

function PersonalityAssessmentCard({ personality, saving, onComplete, onCancel = null }) {
  const [answers, setAnswers] = useState(personality.answers || {});
  const questions = personality.questions || [];
  const complete = questions.every((question) => Number(answers[question.id]) >= 1);
  function submit(event) {event.preventDefault();if (complete) onComplete(answers);}
  return <section className="personality-assessment"><header><span className="personality-mark"><Sparkles size={22} /></span><div><span className="eyebrow">{t("NASEEB AI PERSONALITY FIT")}</span><h2>{t("How do you naturally learn and work?")}</h2><p>{t("Rate each statement from 1 to 5. Naseeb AI combines this education-interest profile with your academic data; it is not a psychological diagnosis.")}</p></div></header><form onSubmit={submit}><div className="personality-scale-key"><span>1 · {t("Not like me")}</span><span>5 · {t("Very much like me")}</span></div><div className="personality-questions">{questions.map((question, index) => <fieldset key={question.id}><legend><span>{formatNumberLocale(index + 1)}</span>{question.text}</legend><div>{PERSONALITY_RATING_OPTIONS.map((value) => <label key={value} className={Number(answers[question.id]) === value ? 'selected' : ''}><input type="radio" name={question.id} value={value} checked={Number(answers[question.id]) === value} onChange={() => setAnswers((current) => ({ ...current, [question.id]: value }))} required /><span>{value}</span></label>)}</div></fieldset>)}</div><footer><small>{Object.keys(answers).length}/{questions.length} {t("answered")}</small><div className="personality-assessment-actions">{onCancel && <button type="button" className="button quiet" onClick={onCancel} disabled={saving}>{t("Cancel")}</button>}<button className="button primary" disabled={!complete || saving} aria-busy={saving}>{saving ? <><RefreshCw className="spin" size={16} /> {t("Analyzing…")}</> : <><Sparkles size={16} /> {t("Save personality profile")}</>}</button></div></footer></form></section>;
}

function CollegeResearchOverview({ research, onRefresh, onEditPersonality }) {
  const profile = research.profile_snapshot || {};
  const evidence = Object.values(profile.evidence || {}).reduce((total, value) => total + Number(value || 0), 0);
  const personality = research.personality || profile.personality || {};
  const traits = (personality.top_traits || []).map((trait) => personality.trait_labels?.[trait] || trait).join(' · ');
  return <section className="college-research-overview"><div><span className="research-status-icon"><CheckCircle2 size={21} /></span><div><span className="eyebrow">{t("NASEEB AI MATCH READY")}</span><h3>{t("Academic and personality fit calculated")}</h3><p>{research.methodology}</p></div></div><div className="research-profile-chips"><span>{t("SAT")} <b>{profile.sat_score}</b></span><span>{t("GPA")} <b>{profile.gpa}</b></span><span>{t("IELTS")} <b>{profile.ielts_score}</b></span><span>{t("Major")} <b>{profile.target_major}</b></span><span>{t("Budget")} <b>{money(profile.budget_usd)}</b></span><span>{t("Evidence")} <b>{evidence}</b></span><span>{t("Personality fit")} <b>{traits || '—'}</b></span></div><div className="research-overview-actions"><button className="button quiet small" onClick={onEditPersonality}><Pencil size={14} /> {t("Update personality profile")}</button><button className="button quiet small" onClick={onRefresh}><RefreshCw size={15} /> {t("Refresh")}</button></div></section>;
}

function CollegeAIAdvisor() {
  const suggestions = [
    t("Which 3 universities fit me best and why?"),
    t("Which options are closest to my budget?"),
    t("Where do I have the strongest scholarship fit?"),
  ];
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function askAI(value = question) {
    const cleanQuestion = String(value || '').trim();
    if (cleanQuestion.length < 3 || loading) return;
    setQuestion(cleanQuestion);
    setLoading(true);
    setError('');
    try {setAnswer(await api.collegeAIAdvice(cleanQuestion));} catch (requestError) {setError(requestError.message);} finally {setLoading(false);}
  }

  function submit(event) {event.preventDefault();askAI();}
  return <section className="college-ai-advisor" aria-labelledby="college-ai-title"><header><span><Bot size={23} /></span><div><h3 id="college-ai-title">{t("Ask Naseeb AI about your universities")}</h3><p>{t("Naseeb AI reads your saved profile and top five matches, then gives a short answer based only on this catalog.")}</p></div></header><div className="college-ai-suggestions" aria-label={t("Suggested questions")}>{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => askAI(suggestion)} disabled={loading}>{suggestion}</button>)}</div><form onSubmit={submit}><label htmlFor="college-ai-question">{t("Your question")}</label><div><textarea id="college-ai-question" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={400} rows={2} placeholder={t("Example: Which universities match my budget and Computer Science goal?")} /><button type="submit" className="button primary" disabled={loading || question.trim().length < 3} aria-busy={loading}>{loading ? <><RefreshCw className="spin" size={16} /> {t("Thinking…")}</> : <><Send size={16} /> {t("Ask AI")}</>}</button></div><small>{formatNumberLocale(question.length)}/400 · {t("Short answer, top five matches only")}</small></form>{error && <div className="college-ai-error" role="alert"><ShieldAlert size={16} /><span>{error}</span></div>}{loading && <div className="college-ai-answer loading" role="status" aria-label={t("Naseeb AI is analyzing your matches")}><span /><span /><span /></div>}{answer?.result && !loading && <div className="college-ai-answer" aria-live="polite"><div className="college-ai-answer-copy"><Sparkles size={17} /><p>{answer.result.answer}</p></div>{answer.result.universities?.length > 0 && <div className="college-ai-options">{answer.result.universities.map((university) => <article key={university.name}><header><b>{university.name}</b><span>{formatPercentLocale(university.match_score)}</span></header><p>{university.reason}</p>{university.caution && <small>{university.caution}</small>}</article>)}</div>}<footer><small>{answer.result.disclaimer}</small><span>{answer.mode === 'gateway' ? t("Naseeb AI") : t("Local guidance fallback")}</span></footer></div>}</section>;
}

function AidChecklist({ data, student }) {
  const shortlisted = data.applications.map((item) => data.universities.find((uni) => uni.id === item.university)).filter(Boolean);
  const needsCss = shortlisted.some((uni) => uni.css_profile_required);
  const needsFafsa = shortlisted.some((uni) => uni.fafsa_required);
  const checklist = [
  ['Academic transcript', 'Official grades and school records', true],
  ['Family financial documents', 'Income, tax or employer statements requested by the institution', student?.scholarship_needed],
  ['Bank or sponsor statement', 'Proof of available funds for international study', true],
  ['Scholarship essays', 'Motivation, impact and financial-need responses', true],
  ['Recommendation letters', 'Teacher or counselor recommendations where requested', true],
  ['CSS Profile', 'Only for shortlisted universities that require it', needsCss],
  ['FAFSA', 'Only where eligibility and university requirements apply', needsFafsa]];

  return <div className="aid-checklist"><section className="aid-intro"><div><span className="eyebrow">{t("AID PREPARATION")}</span><h2>{t("Prepare for financial aid")}</h2><p>{t("Core documents based on your shortlist and profile. Verify final requirements on each university’s official financial aid page.")}</p></div><div className="aid-profile-summary"><Detail label={t("Budget")} value={money(student?.budget_usd)} /><Detail label={t("Scholarship")} value={student?.scholarship_needed ? t("Needed") : t("Optional")} /><Detail label={t("Shortlisted")} value={data.applications.length} /></div></section><div className="checklist-cards">{checklist.map(([title, description, needed]) => <article key={title} className={needed ? "needed" : ''}><span>{needed ? <CheckCircle2 size={20} /> : <Clock3 size={20} />}</span><div><h3>{t(title)}</h3><p>{t(description)}</p></div><Badge>{needed ? t("Prepare") : t("If required")}</Badge></article>)}</div></div>;
}

function ProgramsPage({ data, query }) {
  const [type, setType] = useState('national');
  const [category, setCategory] = useState('all');
  const [delivery, setDelivery] = useState('all');
  const [aidOnly, setAidOnly] = useState(false);
  const nationalCount = data.opportunityPrograms.filter((item) => item.program_type === 'national').length;
  const internationalCount = data.opportunityPrograms.filter((item) => item.program_type === 'international').length;
  const categories = [...new Set(data.opportunityPrograms.filter((item) => item.program_type === type).map((item) => item.category))].sort();
  const programs = data.opportunityPrograms.filter((item) => item.program_type === type && (category === 'all' || item.category === category) && (delivery === 'all' || item.delivery_mode === delivery) && (!aidOnly || item.scholarship_available) && JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  return <div className="section-stack student-portal"><section className="programs-hero"><div><span className="eyebrow">{t("PROFILE-BUILDING OPPORTUNITIES")}</span><h2>{t("National & International Programs")}</h2><p>{t("Find research, leadership, competition, and summer programs in one catalog.")}</p></div><Globe2 size={76} /></section><ChoiceCards name="program-type" label={t("Program type")} value={type} onChange={(nextType) => {setType(nextType);setCategory('all');}} options={[{ value: 'national', label: `National (${nationalCount})`, description: 'Opportunities within Uzbekistan', icon: MapPin }, { value: 'international', label: `International (${internationalCount})`, description: 'Global and overseas opportunities', icon: Globe2 }]} /><div className="program-filters"><label>{t("Category")}<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="all">{t("All categories")}</option>{categories.map((item) => <option key={item}>{item}</option>)}</select></label><label>{t("Delivery")}<select value={delivery} onChange={(event) => setDelivery(event.target.value)}><option value="all">{t("All formats")}</option><option value="onsite">{t("On-site")}</option><option value="online">{t("Online")}</option><option value="hybrid">{t("Hybrid")}</option></select></label><CheckboxControl className="compact" checked={aidOnly} onChange={(event) => setAidOnly(event.target.checked)}>{t("Scholarship available")}</CheckboxControl><span>{programs.length} {t("programs")}</span></div><div className="program-grid">{programs.map((item) => <article className="program-card" key={item.id}><header><span>{item.category}</span><Badge>{item.program_type}</Badge></header><h3>{item.title}</h3><p className="provider">{item.provider}</p><p>{item.description}</p><div className="program-meta"><span><MapPin size={15} /> {[item.city, item.country].filter(Boolean).join(', ')}</span><span><CalendarDays size={15} /> {t("Deadline")} {dateText(item.deadline)}</span><span><DollarSign size={15} /> {Number(item.fee_usd) === 0 ? t("Free") : money(item.fee_usd)}</span><span><UsersRound size={15} /> {t("Grades")} {item.eligible_grades || t("Open")}</span></div>{item.scholarship_available && <div className="program-aid"><Sparkles size={16} /><span><b>{t("Financial aid available")}</b>{item.aid_details}</span></div>}<details><summary>{t("Requirements")}</summary><p>{item.requirements || t("See official application page.")}</p></details>{item.application_url && <a className="button primary small" href={item.application_url} target="_blank" rel="noreferrer">{t("View program")} <ExternalLink size={14} /></a>}</article>)}{!programs.length && <Empty text={t("No programs match these filters.")} />}</div></div>;
}

function StorePage({ data, query, setPage }) {
  const items = data.storeItems.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  return <div className="section-stack student-portal"><section className="store-hero"><div><span className="eyebrow">{t("NASEEB EDU SERVICES")}</span><h2>{t("Unlock your next step.")}</h2><p>{t("Explore education and counseling services that support your application journey.")}</p><button className="button light" onClick={() => setPage('contacts')}>{t("Talk to your team")} <ChevronRight size={17} /></button></div><PackageOpen size={104} /></section><div className="store-grid">{items.map((item) => <article key={item.id} className={item.is_featured ? "featured" : ''}><span>{item.category}</span><h3>{item.title}</h3><p>{item.description}</p><footer><b>{item.price_label || t("Ask your counselor")}</b><button className="button quiet small" onClick={() => setPage('contacts', { context: { serviceId: item.id, serviceTitle: item.title } })}>{t("Ask about this service")}</button></footer></article>)}{!items.length && <Empty />}</div></div>;
}

const SUPPORT_CATEGORIES = ['technical', 'account', 'academic', 'application', 'billing', 'other'];
const SUPPORT_STATUSES = ['open', 'in_progress', 'resolved', 'closed'];

function SupportTicketForm({ onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.create('support-tickets', {
        category: values.get('category'),
        subject: String(values.get('subject') || '').trim(),
        message: String(values.get('message') || '').trim()
      });
      notify(t("Support request sent."));
      onSaved();
    } catch (error) {
      notify(error.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("New support request")} onClose={onClose}><form className="form-grid support-form" onSubmit={submit}>
    <Field label={t("Category")}><select name="category" defaultValue="technical" required>{SUPPORT_CATEGORIES.map((category) => <option key={category} value={category}>{label(category)}</option>)}</select></Field>
    <Field label={t("Subject")}><input name="subject" maxLength="180" placeholder={t("Briefly describe the issue")} required /></Field>
    <Field label={t("Message")}><textarea name="message" maxLength="5000" rows="7" placeholder={t("What happened, where did it happen, and what did you expect?")} required /></Field>
    <div className="support-privacy-note form-wide"><ShieldCheck size={18} /><span>{t("Do not include passwords, payment details, passport numbers, or other sensitive credentials.")}</span></div>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Sending…") : <><Send size={16} /> {t("Send request")}</>}</button></div>
  </form></Modal>;
}

function SupportResponseModal({ ticket, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.update('support-tickets', ticket.id, {
        status: values.get('status'),
        admin_response: String(values.get('admin_response') || '').trim()
      });
      notify(t("Support response saved."));
      onSaved();
    } catch (error) {
      notify(error.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("Respond to support request")} onClose={onClose}><form className="form-grid support-form" onSubmit={submit}>
    <div className="support-request-preview form-wide"><span><Badge>{ticket.category}</Badge><Badge>{ticket.status}</Badge></span><h3>{ticket.subject}</h3><p>{ticket.message}</p><small>{ticket.requester_name} · {label(ticket.requester_role)} · {dateTimeText(ticket.created_at)}</small></div>
    <Field label={t("Status")}><select name="status" defaultValue={ticket.status}>{SUPPORT_STATUSES.map((status) => <option key={status} value={status}>{label(status)}</option>)}</select></Field>
    <Field label={t("Admin response")}><textarea name="admin_response" defaultValue={ticket.admin_response} maxLength="5000" rows="7" placeholder={t("Write a clear resolution or next step.")} required /></Field>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : <><Send size={16} /> {t("Save response")}</>}</button></div>
  </form></Modal>;
}

function SupportTicketDetail({ ticket, user, onClose, onRespond }) {
  const admin = user.role === 'admin';
  return <Modal title={ticket.subject} onClose={onClose}><div className="support-ticket-detail">
    <header><div><Badge>{ticket.category}</Badge><Badge>{ticket.status}</Badge>{ticket.has_unread_response && !admin && <Badge tone="unread">{t("New response")}</Badge>}</div><small>{t("Created")} {dateTimeText(ticket.created_at)} {t("· Updated")} {dateTimeText(ticket.updated_at)}</small></header>
    {admin && <div className="support-requester"><span className="avatar">{initials(ticket.requester_name)}</span><div><b>{ticket.requester_name}</b><small>{label(ticket.requester_role)}</small></div></div>}
    <section><span className="eyebrow">{t("REQUEST")}</span><p>{ticket.message}</p></section>
    <section className={`support-response ${ticket.admin_response ? 'answered' : ''}`}><span className="eyebrow">{t("SUPPORT RESPONSE")}</span>{ticket.admin_response ? <><p>{ticket.admin_response}</p><small>{ticket.responded_by_name || t("Naseeb Edu Support")} · {dateTimeText(ticket.responded_at)}</small></> : <p className="muted-copy">{t("Support has not responded yet. Return to this page later; a badge will appear in the Support menu when a response is ready.")}</p>}</section>
    <footer><button className="button quiet" onClick={onClose}>{t("Close")}</button>{admin && <button className="button primary" onClick={onRespond}><MessageSquareText size={16} /> {t("Respond")}</button>}</footer>
  </div></Modal>;
}

function SupportPage({ user, data, query, reload, notify }) {
  const [tab, setTab] = useState('all');
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState(null);
  const [responding, setResponding] = useState(null);
  const admin = user.role === 'admin';
  const search = query.trim().toLowerCase();
  const tickets = data.supportTickets.filter((ticket) => (tab === 'all' || ticket.status === tab) && (!search || JSON.stringify(ticket).toLowerCase().includes(search)));
  const activeCount = data.supportTickets.filter((ticket) => ['open', 'in_progress'].includes(ticket.status)).length;
  const unreadCount = data.supportTickets.filter((ticket) => ticket.has_unread_response).length;

  async function openTicket(ticket) {
    setSelected(ticket);
    if (!admin && ticket.has_unread_response) {
      try {
        await api.markSupportViewed(ticket.id);
        setSelected((current) => current?.id === ticket.id ? { ...current, has_unread_response: false, requester_viewed_at: new Date().toISOString() } : current);
        await reload();
      } catch (error) {
        notify(error.message, 'error');
      }
    }
  }

  function saved() {
    setCreating(false);
    setResponding(null);
    setSelected(null);
    reload();
  }

  return <div className="section-stack support-page">
    <section className="support-hero"><div><span className="eyebrow">{t("NASEEB EDU SUPPORT")}</span><h2>{admin ? t("Support requests") : t("Ask the Naseeb team")}</h2><p>{admin ? t("Review requests from students, schools, and counselors in one focused queue.") : t("Tell us what you need, track its progress here, and return when the Naseeb team replies.")}</p></div>{!admin && <button className="button primary" onClick={() => setCreating(true)}><Plus size={17} /> {t("New request")}</button>}</section>
    <div className="support-summary"><article><span>{admin ? t("All requests") : t("My requests")}</span><strong>{data.supportTickets.length}</strong></article><article><span>{t("Active")}</span><strong>{activeCount}</strong></article><article><span>{admin ? t("Resolved") : t("New responses")}</span><strong>{admin ? data.supportTickets.filter((ticket) => ticket.status === 'resolved').length : unreadCount}</strong></article></div>
    <section className="support-list"><div className="support-toolbar"><PortalTabs active={tab} onChange={setTab} items={[["all", "All"], ["open", "Open"], ["in_progress", "In progress"], ["resolved", "Resolved"], ["closed", "Closed"]]} /><small>{tickets.length} {tickets.length === 1 ? t("request") : t("requests")}</small></div>
      <div className="support-ticket-grid">{tickets.map((ticket) => <article className={`support-ticket-card ${ticket.has_unread_response && !admin ? 'has-new-response' : ''}`} key={ticket.id}><div className="support-ticket-copy"><header><div><Badge>{ticket.category}</Badge><Badge>{ticket.status}</Badge>{ticket.has_unread_response && !admin && <Badge tone="unread">{t("New response")}</Badge>}</div><time>{dateText(ticket.updated_at)}</time></header><h3>{ticket.subject}</h3><p>{ticket.message}</p>{admin && <div className="support-requester compact"><span className="avatar">{initials(ticket.requester_name)}</span><div><b>{ticket.requester_name}</b><small>{label(ticket.requester_role)}</small></div></div>}</div><footer><small>{ticket.admin_response ? tx`Answered by ${ticket.responded_by_name || t("Support")}` : t("Awaiting support response")}</small><div><button className="button quiet small" onClick={() => openTicket(ticket)}><Eye size={14} /> {ticket.has_unread_response && !admin ? t("Read response") : t("View")}</button>{admin && <button className="button primary small" onClick={() => setResponding(ticket)}><MessageSquareText size={14} /> {t("Respond")}</button>}</div></footer></article>)}{!tickets.length && <Empty text={data.supportTickets.length ? t("No requests match this filter.") : admin ? t("No support requests have been submitted.") : t("You have not sent a support request yet.")} />}</div>
    </section>
    {creating && <SupportTicketForm onClose={() => setCreating(false)} onSaved={saved} notify={notify} />}
    {selected && <SupportTicketDetail ticket={selected} user={user} onClose={() => setSelected(null)} onRespond={() => {setResponding(selected);setSelected(null);}} />}
    {responding && <SupportResponseModal ticket={responding} onClose={() => setResponding(null)} onSaved={saved} notify={notify} />}
  </div>;
}

const PARENT_CHILD_KEY = 'naseeb-parent-selected-child-v1';

function ParentChildSwitcher({ children, selectedId, onChange }) {
  if (children.length <= 1) return children[0] ? <div className="parent-single-child"><span className="avatar">{initials(children[0].profile.name)}</span><div><b>{children[0].profile.name}</b><small>{children[0].profile.school}</small></div></div> : null;
  return <label className="parent-child-switcher"><span>{t("Viewing child")}</span><select value={selectedId} onChange={(event) => onChange(Number(event.target.value))}>{children.map((child) => <option key={child.profile.id} value={child.profile.id}>{child.profile.name} · {child.profile.school}</option>)}</select></label>;
}

function ParentPortalPage({ page, data, reload, notify }) {
  const portal = data.parentPortal || EMPTY_DATA.parentPortal;
  const children = portal.children || [];
  const [preferredId, setPreferredId] = useState(() => {
    try {return Number(localStorage.getItem(PARENT_CHILD_KEY)) || null;} catch {return null;}
  });
  const child = children.find((item) => item.profile.id === preferredId) || children[0];
  const { confirm, dialog } = useActionDialog();

  function chooseChild(id) {
    setPreferredId(id);
    try {localStorage.setItem(PARENT_CHILD_KEY, String(id));} catch {/* Selection remains available for this session. */}
  }
  async function acceptInvite(invitation) {
    try {await api.acceptParentInvite(invitation.id);notify(tx`${invitation.student_name} is now connected.`);reload();} catch (err) {notify(err.message, 'error');}
  }
  async function revokeAccess() {
    if (!child || !await confirm({ title: t("Disconnect family access"), description: tx`Disconnect parent access to ${child.profile.name}? The counselor must invite this account again to restore access.`, confirmLabel: t("Disconnect"), tone: 'danger' })) return;
    try {await api.revokeParentLink(child.link_id);notify(t("Parent access disconnected."));reload();} catch (err) {notify(err.message, 'error');}
  }

  const invitations = portal.pending_invitations || [];
  if (!child) return <div className="parent-empty-workspace"><section><UsersRound size={42} /><span className="eyebrow">{t("PARENT WORKSPACE")}</span><h2>{t("Your family workspace is ready")}</h2><p>{t("A child appears here only after you accept an invitation from their assigned counselor or Naseeb Edu admin.")}</p></section>{invitations.map((invitation) => <article key={invitation.id}><div><b>{invitation.student_name}</b><small>{invitation.relationship_display} {t("invitation ·")} {dateText(invitation.invited_at)}</small></div><button className="button primary" onClick={() => acceptInvite(invitation)}><Check size={16} /> {t("Accept invitation")}</button></article>)}{!invitations.length && <div className="screen-time-privacy"><ShieldCheck size={18} /><p>{t("No pending invitation. Ask the student’s assigned counselor to invite your parent account.")}</p></div>}</div>;

  const profile = child.profile;
  const openTasks = child.tasks.filter((item) => item.status !== 'approved');
  const activeApplications = child.applications.filter((item) => !['accepted', 'rejected'].includes(item.status));
  const upcomingMeetings = child.meetings.filter((item) => new Date(item.starts_at) >= new Date() && !['rejected', 'completed'].includes(item.status));
  const header = <section className="parent-family-hero"><div><span className="eyebrow">{t("FAMILY VIEW · READ ONLY")}</span><h2>{profile.name}</h2><p>{profile.school} · {profile.grade === 'gap' ? t("Gap year") : tx`Grade ${profile.grade}`} {t("· Counselor:")} {profile.counselor_name || t("Not assigned")}</p></div><ParentChildSwitcher children={children} selectedId={profile.id} onChange={chooseChild} /></section>;
  const invitationsPanel = invitations.length > 0 && <section className="parent-invitations"><div><b>{t("New child invitation")}</b><p>{t("Accepting grants the exact read-only sections selected by the counselor.")}</p></div>{invitations.map((invitation) => <button key={invitation.id} className="button primary" onClick={() => acceptInvite(invitation)}><Check size={16} /> {t("Accept")} {invitation.student_name}</button>)}</section>;

  let content;
  if (page === 'dashboard') content = <>
    <div className="stat-grid parent-stat-grid"><Stat label={t("Journey progress")} value={formatPercentLocale(profile.journey_progress_percent)} note={t("Tasks + roadmap")} /><Stat label={t("Open tasks")} value={formatNumberLocale(openTasks.length)} note={openTasks.filter((item) => item.is_overdue).length ? t("Deadline needs attention") : t("No overdue work")} /><Stat label={t("Active applications")} value={formatNumberLocale(activeApplications.length)} note={child.permissions.applications ? t("Permission granted") : t("Not shared")} /><Stat label={t("Upcoming meetings")} value={formatNumberLocale(upcomingMeetings.length)} note={child.permissions.meetings ? t("Permission granted") : t("Not shared")} /></div>
    <div className="split-grid wide-left"><Panel title={t("Next priorities")}><div className="record-list">{openTasks.slice(0, 5).map((task) => <Record key={task.id} title={task.title} meta={`${dateText(task.due_date)} · ${label(task.priority)}`} badge={task.status} />)}{!openTasks.length && <Empty text={t("No open tasks for this child.")} />}</div></Panel><Panel title={t("Family access")}><div className="parent-access-list">{[['Progress & tasks', true], ['Applications', child.permissions.applications], ['Documents', child.permissions.documents], ['Meetings', child.permissions.meetings]].map(([title, allowed]) => <div key={title}><span>{t(title)}</span><b className={allowed ? "allowed" : ''}>{allowed ? t("Visible") : t("Hidden")}</b></div>)}</div><button className="button quiet small parent-revoke" onClick={revokeAccess}>{t("Disconnect access")}</button></Panel></div>
  </>;else
  if (page === 'parent_progress') content = <><div className="stat-grid parent-stat-grid"><Stat label={t("Level")} value={formatNumberLocale(profile.level)} note={tx`${profile.xp_total} XP earned`} /><Stat label={t("Task progress")} value={formatPercentLocale(profile.task_progress_percent)} /><Stat label={t("Roadmap progress")} value={formatPercentLocale(profile.roadmap_progress_percent)} /><Stat label={t("Overall journey")} value={formatPercentLocale(profile.journey_progress_percent)} /></div><div className="split-grid"><Panel title={t("Academic snapshot")}><div className="detail-grid"><Detail label={t("GPA")} value={profile.gpa} /><Detail label={t("IELTS")} value={profile.ielts_score} /><Detail label={t("SAT")} value={profile.sat_score} /><Detail label={t("Target major")} value={profile.target_major} /><Detail label={t("Target countries")} value={profile.target_countries} /><Detail label={t("Next level")} value={`${formatNumberLocale(profile.next_level_xp)} XP`} /></div></Panel><Panel title={t("Progress by area")}><div className="parent-progress-list">{[['Tasks', profile.task_progress_percent], ['Roadmap', profile.roadmap_progress_percent], ['Journey', profile.journey_progress_percent]].map(([title, value]) => <div key={title}><span><b>{t(title)}</b><small>{formatPercentLocale(value)}</small></span><div className="progress wide"><i style={{ width: `${value}%` }} /></div></div>)}</div></Panel></div></>;else
  if (page === 'parent_tasks') content = <Panel title={t("Assigned tasks")}><div className="parent-record-grid">{child.tasks.map((task) => <article key={task.id}><div><Badge>{task.status}</Badge>{task.is_self_assigned && <small>{t("Self-task · no XP")}</small>}</div><h3>{task.title}</h3><p>{dateText(task.due_date)} · {label(task.priority)} {t("priority")}</p>{task.is_overdue && <span className="risk-note">{t("Deadline passed")}</span>}</article>)}{!child.tasks.length && <Empty text={t("No assigned tasks yet.")} />}</div></Panel>;else
  if (page === 'parent_applications') content = child.permissions.applications ? <Panel title={t("University applications")}><div className="parent-record-grid">{child.applications.map((application) => <article key={application.id}><div><Badge>{application.status}</Badge><small>{label(application.tier)}</small></div><h3>{application.university}</h3><p>{application.program} · {application.country}</p><span>{t("Deadline")} {dateText(application.deadline)}</span></article>)}{!child.applications.length && <Empty text={t("No university applications have been added.")} />}</div></Panel> : <ParentHiddenSection title={t("Applications")} />;else
  if (page === 'parent_documents') content = child.permissions.documents ? <Panel title={t("Document checklist")}><div className="parent-record-grid">{child.documents.map((doc) => <article key={doc.id}><div><Badge>{doc.status}</Badge><small>{label(doc.document_type)}</small></div><h3>{doc.title}</h3><p>{t("Updated")} {dateText(doc.updated_at)}</p></article>)}{!child.documents.length && <Empty text={t("No document checklist items yet.")} />}</div></Panel> : <ParentHiddenSection title={t("Documents")} />;else
  content = child.permissions.meetings ? <Panel title={t("Counselor meetings")}><div className="parent-record-grid">{child.meetings.map((meeting) => <article key={meeting.id}><div><Badge>{meeting.status}</Badge><small>{meeting.duration_minutes} {t("min")}</small></div><h3>{meeting.topic}</h3><p>{dateTimeText(meeting.starts_at)}</p><span>{meeting.participant_name || t("Staff member")} · {label(meeting.participant_role)}</span></article>)}{!child.meetings.length && <Empty text={t("No meetings are visible yet.")} />}</div></Panel> : <ParentHiddenSection title={t("Meetings")} />;

  return <div className="section-stack parent-portal">{dialog}{header}{invitationsPanel}{content}<div className="screen-time-privacy"><ShieldCheck size={18} /><p><b>{t("Private by default.")}</b> {t("This cabinet never shows essays, messages, counselor notes, task responses, document files, passwords, or application portal credentials. All shared information is read-only.")}</p></div></div>;
}

function ParentHiddenSection({ title }) {
  return <section className="parent-hidden-section"><Fingerprint size={36} /><h2>{title} {t("are not shared")}</h2><p>{t("The counselor did not enable this section for the current parent-child connection.")}</p></section>;
}

function ScreenTimePage({ user }) {
  const [days, setDays] = useState(7);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {setSummary(await api.screenTimeSummary(days));} catch (err) {setError(err.message);} finally {setLoading(false);}
  }, [days]);
  useEffect(() => {load();}, [load]);

  if (loading && !summary) return <PageSkeleton />;
  if (error && !summary) return <InlineLoadError message={error} onRetry={load} />;
  const own = summary?.own || { today_seconds: 0, period_seconds: 0, daily: [], pages: [] };
  const dailyByDate = Object.fromEntries(own.daily.map((row) => [row.date, row.seconds]));
  const dates = Array.from({ length: days }, (_, offset) => {
    const date = new Date();
    date.setDate(date.getDate() - (days - offset - 1));
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 10);
  });
  const daily = dates.map((date) => ({ date, seconds: dailyByDate[date] || 0 }));
  const maxSeconds = Math.max(1, ...daily.map((row) => row.seconds));
  const isStaff = ['admin', 'counselor', 'teacher', 'organization'].includes(user.role);
  return <div className="section-stack screen-time-page">
    <section className="screen-time-intro"><div><span className="eyebrow">{t("ACTIVE LEARNING ONLY")}</span><h2>{t("Time that reflects real work")}</h2><p>{t("Time counts only while this tab is visible and you have interacted in the last minute. Idle and background time are excluded.")}</p></div><label className="period-select">{t("Period")}<select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value="7">{t("Last 7 days")}</option><option value="14">{t("Last 14 days")}</option><option value="30">{t("Last 30 days")}</option></select></label></section>
    {error && <div className="alert error">{error}</div>}
    <div className="stat-grid screen-time-stats"><Stat label={t("Today")} value={formatDuration(own.today_seconds)} note={t("Active tab time")} /><Stat label={tx`${days}-day total`} value={formatDuration(own.period_seconds)} note={t("Idle time excluded")} /><Stat label={t("Daily average")} value={formatDuration(own.period_seconds / days)} note={tx`Timezone: ${summary?.timezone || t("Asia/Tashkent")}`} /></div>
    <div className="split-grid wide-left"><Panel title={t("Daily activity")}><div className="time-chart" aria-label={t("Daily active time chart")}>{daily.map((row) => <div className="time-bar" key={row.date} title={`${dateText(row.date)}: ${formatDuration(row.seconds)}`}><span><i style={{ height: `${Math.max(row.seconds ? 8 : 2, row.seconds / maxSeconds * 100)}%` }} /></span><small>{new Date(`${row.date}T12:00:00`).toLocaleDateString(locale(), { weekday: 'short' })}</small></div>)}</div></Panel><Panel title={t("Pages")}><div className="page-time-list">{own.pages.slice(0, 8).map((row) => <div key={row.page}><span>{PAGE_META[row.page] ? t(PAGE_META[row.page].label) : label(row.page.replaceAll('_', ' '))}</span><b>{formatDuration(row.seconds)}</b></div>)}{!own.pages.length && <Empty text={t("Your active time will appear after the first 30-second sync.")} />}</div></Panel></div>
    {isStaff && <Panel title={t("Student activity")} action={<span className="privacy-chip"><ShieldCheck size={14} /> {t("Aggregate view")}</span>}><div className="time-team-list">{summary?.team?.map((student) => <article key={student.student}><div><span className="avatar">{initials(student.name)}</span><div><b>{student.name}</b><small>{student.school}</small></div></div><span><small>{t("Today")}</small><b>{formatDuration(student.today_seconds)}</b></span><span><small>{days} {t("days")}</small><b>{formatDuration(student.period_seconds)}</b></span></article>)}{!summary?.team?.length && <Empty text={t("No permitted student activity is available yet.")} />}</div></Panel>}
    <div className="screen-time-privacy"><ShieldCheck size={18} /><p><b>{t("Privacy by design.")}</b> {t("We store only aggregate seconds by user, day, and app page—never clicks, typed text, or browsing content. Offline totals retry for up to 7 days. Aggregate rows are retained for")} {summary?.retention_days || 365} {t("days.")}</p></div>
  </div>;
}

function ContactsPage({ data, setPage, navigationContext }) {
  const serviceTitle = navigationContext?.serviceTitle || '';
  const contactContext = (member, action) => ({ context: { action, memberId: member.id, memberName: member.name, serviceId: navigationContext?.serviceId, serviceTitle } });
  return <div className="section-stack student-portal"><section className="portal-hero contacts-hero"><div><span className="eyebrow">{t("YOUR SUPPORT NETWORK")}</span><h2>{t("My Naseeb Team")}</h2><p>{t("Quickly connect with your counselor and school coordinator.")}</p></div><ContactRound size={64} /></section>{serviceTitle && <section className="contact-intent-banner"><PackageOpen size={22} /><div><span>{t("Selected service")}</span><b>{serviceTitle}</b><p>{t("Choose a team member. Your message or meeting request will keep this service as context.")}</p></div></section>}<div className="contact-grid">{data.team.map((member) => <article key={`${member.kind}-${member.id}`}><span className="avatar large">{initials(member.name)}</span><div><span>{member.kind === 'counselor' ? t("Primary counselor") : t("School coordinator")}</span><h3>{member.name}</h3><p>{member.role}</p><small>{member.email || t("Email not provided")}</small><small>{member.phone || t("Phone not provided")}</small></div><footer><button className="button primary" onClick={() => setPage('messages', contactContext(member, 'message'))}><MessageCircle size={16} /> {serviceTitle ? t("Ask by message") : t("Message")}</button>{member.kind === 'counselor' && <button className="button quiet" onClick={() => setPage('bookings', contactContext(member, 'book'))}><CalendarClock size={16} /> {serviceTitle ? t("Discuss in a meeting") : t("Book")}</button>}</footer></article>)}{!data.team.length && <Empty text={t("No team members have been assigned yet.")} />}</div></div>;
}

function AdminControlDashboard({ data, setPage }) {
  const counselors = data.accounts.filter((account) => account.role === 'counselor');
  const activeCounselors = counselors.filter((account) => account.is_active);
  const pendingReviews = data.counselorRoadmaps.flatMap((roadmap) => roadmap.missions || []).filter((mission) => mission.status === 'submitted').length;
  return <div className="section-stack"><div className="stat-grid"><Stat label={t("Schools")} value={data.schools.filter((school) => school.workspace_type === 'school' && school.is_active).length} note={t("Active organization workspaces")} /><Stat label={t("Counselors")} value={activeCounselors.length} note={tx`${counselors.length - activeCounselors.length} inactive`} /><Stat label={t("Students")} value={data.students.length} note={t("Available in Student 360")} /><Stat label={t("Roadmap reviews")} value={pendingReviews} note={t("Submitted counselor missions")} /></div><Panel title={t("Platform administration")}><div className="quick-grid"><button onClick={() => setPage('admin_schools')}><Building2 /><span><b>{t("Manage schools")}</b><small>{t("Provision organization accounts")}</small></span></button><button onClick={() => setPage('admin_counselors')}><UserRound /><span><b>{t("Manage counselors")}</b><small>{t("Create, transfer, or deactivate")}</small></span></button><button onClick={() => setPage('counselor_roadmap')}><Compass /><span><b>{t("Review roadmaps")}</b><small>{t("Approve submitted milestones")}</small></span></button><button onClick={() => setPage('admin_audit')}><ShieldAlert /><span><b>{t("Open audit log")}</b><small>{t("Trace administration actions")}</small></span></button></div></Panel></div>;
}

function AdminCounselorsPage({ data, query, reload, notify }) {
  const [open, setOpen] = useState(false);
  const [transfer, setTransfer] = useState(null);
  const [editing, setEditing] = useState(null);
  const { confirm, dialog } = useActionDialog();
  const counselors = data.accounts.filter((account) => account.role === 'counselor' && JSON.stringify(account).toLowerCase().includes(query.toLowerCase()));
  async function deactivate(account) {
    if (!await confirm({ title: t("Deactivate counselor"), description: tx`Deactivate ${fullName(account)}? Their login will stop immediately.`, confirmLabel: t("Deactivate"), tone: 'danger' })) return;
    try {await api.deactivateAccount(account.id);notify(t("Counselor deactivated."));reload();} catch (error) {notify(error.message, 'error');}
  }
  return <>{dialog}<Panel title={t("Counselor provisioning")} action={<button className="button primary" onClick={() => setOpen(true)}><Plus size={16} /> {t("Add counselor")}</button>}><div className="record-list">{counselors.map((account) => <article className="record" key={account.id}><span className="avatar">{initials(fullName(account))}</span><div className="record-main"><h3>{fullName(account)}</h3><p>{account.email} · {account.school_name || t("No school")}</p><div className="record-meta"><Badge tone={account.is_active ? 'success' : 'danger'}>{account.is_active ? t("Active") : t("Inactive")}</Badge><span>{account.school_workspace_type === 'individual' ? t("Individual workspace") : t("Organization school")}</span></div></div><div className="record-actions"><button className="icon-button" onClick={() => setEditing(account)} title={t("Edit counselor")}><Pencil size={16} /></button>{account.is_active && account.school_workspace_type !== 'individual' && <button className="button quiet" onClick={() => setTransfer(account)}><Building2 size={15} /> {t("Transfer")}</button>}{account.is_active && <button className="icon-button danger" onClick={() => deactivate(account)} title={t("Deactivate counselor")}><Trash2 size={16} /></button>}</div></article>)}{!counselors.length && <Empty text={t("No counselors found.")} />}</div></Panel>{open && <CounselorProvisionForm schools={data.schools} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}{editing && <CounselorEditForm account={editing} onClose={() => setEditing(null)} onSaved={() => {setEditing(null);reload();}} notify={notify} />}{transfer && <AccountTransferForm account={transfer} schools={data.schools} onClose={() => setTransfer(null)} onSaved={() => {setTransfer(null);reload();}} notify={notify} />}</>;
}

function CounselorEditForm({ account, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);try {await api.update('users/accounts', account.id, { first_name: values.get('first_name'), last_name: values.get('last_name'), email: values.get('email'), phone: values.get('phone'), position: values.get('position'), is_active: values.get('is_active') === 'true' });notify(t("Counselor updated."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  return <Modal title={t("Edit counselor")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("First name")}><input name="first_name" defaultValue={account.first_name} required /></Field><Field label={t("Last name")}><input name="last_name" defaultValue={account.last_name} /></Field><Field label={t("Email")}><input name="email" type="email" defaultValue={account.email} required /></Field><Field label={t("Phone")}><input name="phone" defaultValue={account.phone} /></Field><Field label={t("Position")}><input name="position" defaultValue={account.position} /></Field><Field label={t("Status")}><select name="is_active" defaultValue={String(account.is_active)}><option value="true">{t("Active")}</option><option value="false">{t("Inactive")}</option></select></Field><p className="form-note form-wide">{t("Reactivation is blocked when the destination school already has three active counselors.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{saving ? t("Saving…") : t("Save")}</button></div></form></Modal>;
}

function CounselorProvisionForm({ schools, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();setSaving(true);try {const payload = Object.fromEntries(new FormData(event.currentTarget).entries());payload.school = Number(payload.school);await api.createCounselor(payload);notify(t("Counselor account created."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  const organizationSchools = schools.filter((school) => school.workspace_type === 'school' && school.is_active);
  return <Modal title={t("Add school counselor")} onClose={onClose}><form className="form-grid" onSubmit={submit} autoComplete="off"><Field label={t("First name")}><input name="first_name" required /></Field><Field label={t("Last name")}><input name="last_name" /></Field><Field label={t("Username")}><input name="username" autoComplete="off" required /></Field><Field label={t("Email")}><input name="email" type="email" autoComplete="off" required /></Field><Field label={t("Organization school")}><select name="school" required><option value="">{t("Select a school")}</option>{organizationSchools.map((school) => <option value={school.id} key={school.id}>{school.name}</option>)}</select></Field><Field label={t("Position")}><input name="position" /></Field><Field label={t("Temporary password")}><input name="password" type="password" minLength="12" autoComplete="new-password" required /></Field><p className="form-note form-wide"><ShieldCheck size={16} /> {t("Each organization school can have at most three active counselors.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{saving ? t("Creating…") : t("Create counselor")}</button></div></form></Modal>;
}

function AccountTransferForm({ account, schools, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();setSaving(true);try {await api.transferCounselor(account.id, Number(new FormData(event.currentTarget).get('school')));notify(t("Counselor transferred."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  return <Modal title={t("Transfer counselor")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Organization school")}><select name="school" required defaultValue=""><option value="" disabled>{t("Select a school")}</option>{schools.filter((school) => school.workspace_type === 'school' && school.is_active && school.id !== account.school).map((school) => <option key={school.id} value={school.id}>{school.name}</option>)}</select></Field><p className="form-note form-wide">{t("Transfer is blocked until assigned students belong to the destination school and a counselor slot is available.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{t("Transfer")}</button></div></form></Modal>;
}

function CounselorRoadmapPage({ user, data, reload, notify }) {
  const [templateOpen, setTemplateOpen] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [selfAssignOpen, setSelfAssignOpen] = useState(false);
  const { confirm, prompt, dialog } = useActionDialog();
  async function submitMission(roadmap, mission) {const note = await prompt({ title: t("Submit mission"), description: t("Add a completion note before sending this mission for review."), inputLabel: t("Completion note"), initialValue: mission.counselor_note || '', confirmLabel: t("Submit for review") });if (!note) return;try {await api.submitCounselorMission(roadmap.id, mission.id, note);notify(t("Mission submitted for review."));reload();} catch (error) {notify(error.message, 'error');}}
  async function review(roadmap, mission, decision) {let feedback = '';if (decision === 'request_changes') {feedback = await prompt({ title: t("Request changes"), description: t("Explain what the counselor needs to update."), inputLabel: t("Review feedback"), confirmLabel: t("Request changes") }) || '';if (!feedback) return;} else if (!await confirm({ title: t("Approve mission"), description: tx`Approve ${mission.title}?`, confirmLabel: t("Approve") })) return;try {await api.reviewCounselorMission(roadmap.id, mission.id, decision, feedback);notify(decision === 'approve' ? t("Mission approved.") : t("Changes requested."));reload();} catch (error) {notify(error.message, 'error');}}
  const templates = data.counselorRoadmapTemplates.filter((template) => template.is_active);
  const actions = user.role === 'admin' ? <div className="panel-actions"><button className="button quiet" onClick={() => setTemplateOpen(true)}><Plus size={16} /> {t("New template")}</button><button className="button primary" onClick={() => setAssignOpen(true)}><Compass size={16} /> {t("Assign roadmap")}</button></div> : <button className="button primary" onClick={() => setSelfAssignOpen(true)}><Compass size={16} /> {t("Start my roadmap")}</button>;
  const emptyText = user.role === 'counselor' ? t("Create your own roadmap or begin from an active template.") : t("No counselor roadmaps assigned yet.");
  return <>{dialog}<Panel title={user.role === 'admin' ? t("Counselor roadmap control") : t("My professional roadmap")} action={actions}><div className="record-list">{data.counselorRoadmaps.map((roadmap) => <article className="roadmap-admin-card" key={roadmap.id}><header><div><span className="eyebrow">{label(roadmap.kind)}</span><h3>{roadmap.title}</h3><p>{roadmap.counselor_name} · {roadmap.school_name}</p></div><div className="roadmap-progress"><b>{formatPercentLocale(roadmap.progress_percent)}</b><Badge tone={roadmap.status === 'completed' ? 'success' : ''}>{label(roadmap.status)}</Badge></div></header><div className="roadmap-admin-missions">{roadmap.missions.map((mission) => <div key={mission.id}><span className={`status-dot ${mission.status}`} /><div><b>{mission.sequence}. {mission.title}</b><small>{label(mission.status)} · {dateText(mission.due_date)}</small>{mission.counselor_note && <p>{mission.counselor_note}</p>}{mission.admin_feedback && <p className="form-note">{mission.admin_feedback}</p>}</div><div>{user.role === 'counselor' && mission.status !== 'approved' && <button className="button quiet" onClick={() => submitMission(roadmap, mission)}>{t("Submit")}</button>}{user.role === 'admin' && mission.status === 'submitted' && <><button className="button quiet" onClick={() => review(roadmap, mission, 'request_changes')}>{t("Request changes")}</button><button className="button primary" onClick={() => review(roadmap, mission, 'approve')}>{t("Approve")}</button></>}</div></div>)}</div></article>)}{!data.counselorRoadmaps.length && <Empty text={emptyText} />}</div></Panel>{templateOpen && <RoadmapTemplateForm onClose={() => setTemplateOpen(false)} onSaved={() => {setTemplateOpen(false);reload();}} notify={notify} />}{assignOpen && <RoadmapAssignForm data={data} onClose={() => setAssignOpen(false)} onSaved={() => {setAssignOpen(false);reload();}} notify={notify} />}{selfAssignOpen && <RoadmapSelfAssignForm templates={templates} onClose={() => setSelfAssignOpen(false)} onSaved={() => {setSelfAssignOpen(false);reload();}} notify={notify} />}</>;
}

function RoadmapSelfAssignForm({ templates, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [templateId, setTemplateId] = useState('');
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      const payload = templateId ? {
        template: Number(templateId),
        title: values.get('title'),
      } : {
        title: values.get('title'),
        kind: values.get('kind'),
        missions: String(values.get('missions')).split('\n').map((title) => title.trim()).filter(Boolean).map((title) => ({ title })),
      };
      await api.create('counselor-roadmaps', payload);
      notify(t("Roadmap started."));
      onSaved();
    } catch (error) {
      notify(error.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("Start my roadmap")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field className="form-wide" label={t("Roadmap source")}><select name="template" value={templateId} onChange={(event) => setTemplateId(event.target.value)}><option value="">{t("Create my own roadmap")}</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.name} · {label(template.kind)}</option>)}</select></Field><Field className="form-wide" label={templateId ? t("Custom title (optional)") : t("Roadmap title")}><input name="title" required={!templateId} /></Field>{!templateId && <><Field label={t("Roadmap type")}><select name="kind"><option value="professional_onboarding">{t("Professional onboarding")}</option><option value="school_management">{t("School management")}</option></select></Field><Field className="form-wide" label={t("Missions, one per line")}><textarea name="missions" rows="6" required /></Field></>}<p className="form-note form-wide"><Compass size={16} /> {t("You can start one active roadmap for each roadmap type.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{saving ? t("Starting…") : t("Start roadmap")}</button></div></form></Modal>;
}

function RoadmapTemplateForm({ onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);const missions = String(values.get('missions')).split('\n').map((title) => title.trim()).filter(Boolean).map((title, index) => ({ title, description: '', sequence: index + 1, due_days: (index + 1) * 7, is_required: true }));try {await api.create('counselor-roadmap-templates', { name: values.get('name'), description: values.get('description'), kind: values.get('kind'), is_active: true, missions });notify(t("Roadmap template created."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  return <Modal title={t("New counselor roadmap template")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Template name")}><input name="name" required /></Field><Field label={t("Roadmap type")}><select name="kind"><option value="professional_onboarding">{t("Professional onboarding")}</option><option value="school_management">{t("School management")}</option></select></Field><Field className="form-wide" label={t("Description")}><textarea name="description" /></Field><Field className="form-wide" label={t("Missions, one per line")}><textarea name="missions" required rows="6" /></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{t("Create template")}</button></div></form></Modal>;
}

function RoadmapAssignForm({ data, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);try {await api.create('counselor-roadmaps', { counselor: Number(values.get('counselor')), template: Number(values.get('template')), title: values.get('title') });notify(t("Roadmap assigned."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  return <Modal title={t("Assign counselor roadmap")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Counselor")}><select name="counselor" required><option value="">{t("Select a counselor")}</option>{data.accounts.filter((account) => account.role === 'counselor' && account.is_active).map((account) => <option key={account.id} value={account.id}>{fullName(account)} · {account.school_name}</option>)}</select></Field><Field label={t("Template")}><select name="template" required><option value="">{t("Select a template")}</option>{data.counselorRoadmapTemplates.filter((template) => template.is_active).map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}</select></Field><Field className="form-wide" label={t("Custom title (optional)")}><input name="title" /></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{t("Assign roadmap")}</button></div></form></Modal>;
}

function AdminAuditPage({ data, query }) {
  const events = data.adminAuditEvents.filter((event) => JSON.stringify(event).toLowerCase().includes(query.toLowerCase()));
  return <Panel title={t("Product administration audit")}><div className="record-list audit-list">{events.map((event) => <article className="record" key={event.id}><ShieldCheck size={20} /><div className="record-main"><h3>{event.action}</h3><p>{event.target_label || event.target_type}</p><div className="record-meta"><span>{event.actor_name || t("System")}</span><span>{dateTimeText(event.created_at)}</span></div></div></article>)}{!events.length && <Empty text={t("No audit events found.")} />}</div></Panel>;
}

function PageRouter({ page, user, data, stats, query, reload, notify, setPage, navigationContext }) {
  if (user.role === 'parent') return <ParentPortalPage {...{ page, data, reload, notify }} />;
  if (user.role === 'admin' && page === 'admin_dashboard') return <AdminControlDashboard data={data} setPage={setPage} />;
  if (user.role === 'admin' && page === 'admin_schools') return <SchoolsPage user={user} data={data} reload={reload} notify={notify} />;
  if (user.role === 'admin' && page === 'admin_counselors') return <AdminCounselorsPage data={data} query={query} reload={reload} notify={notify} />;
  if (user.role === 'admin' && page === 'admin_students') return <StudentsPage user={user} data={data} query={query} reload={reload} notify={notify} />;
  if (['admin', 'counselor'].includes(user.role) && page === 'counselor_roadmap') return <CounselorRoadmapPage user={user} data={data} reload={reload} notify={notify} />;
  if (user.role === 'admin' && page === 'admin_audit') return <AdminAuditPage data={data} query={query} />;
  if (page === 'dashboard') return <Dashboard user={user} data={data} stats={stats} setPage={setPage} />;
  if (user.role === 'student' && page === 'student_center') return <StudentCenterPage {...{ user, data, query, reload, notify }} />;
  if (isTaskManager(user) && page === 'roadmap') return <RoadmapPage {...{ user, data, query, reload, notify }} />;
  if (user.role === 'student' && page === 'roadmap') return <RoadmapPage {...{ user, data, query, reload, notify }} />;
  if (user.role === 'student' && page === 'community') return <CommunityPage {...{ data, reload, notify }} />;
  if (page === 'bookings') return <BookingsPage {...{ user, data, reload, notify, navigationContext }} />;
  if (page === 'messages') return <MessagesPage {...{ user, data, notify, navigationContext }} />;
  if (page === 'support') return <SupportPage {...{ user, data, query, reload, notify }} />;
  if (page === 'screen_time') return <ScreenTimePage user={user} />;
  if (['student', 'admin', 'counselor'].includes(user.role) && page === 'program_usage') return <ProgramUsagePage {...{ user, data, reload, notify }} />;
  if (user.role === 'student' && page === 'programs') return <ProgramsPage {...{ data, query }} />;
  if (user.role === 'student' && page === 'resource_index') return <ResourceIndexPage {...{ data, query, setPage }} />;
  if (user.role === 'student' && page === 'essay_lab') return <EssayLabPage {...{ user, data, query, reload, notify }} />;
  if (user.role === 'student' && page === 'applications') return <ApplicationsPortalPage {...{ user, data, query, reload, notify, setPage }} />;
  if (user.role === 'student' && page === 'college_search') return <CollegeSearchPage {...{ data, query, reload, notify }} />;
  if (user.role === 'student' && page === 'store') return <StorePage {...{ data, query, setPage }} />;
  if (user.role === 'student' && page === 'contacts') return <ContactsPage {...{ data, setPage, navigationContext }} />;
  if (page === 'schools') return <SchoolsPage user={user} data={data} reload={reload} notify={notify} />;
  if (page === 'students') return <StudentsPage user={user} data={data} query={query} reload={reload} notify={notify} />;
  if (page === 'profile') return <StudentOverview student={ownStudent(data)} data={data} />;
  if (page === 'academics') return <div className="section-stack">{user.role === 'student' && <ProfileCard student={ownStudent(data)} />}<ResourceSection title={t("Research")} resource="researches" {...{ user, data, query, reload, notify }} /></div>;
  if (page === 'portfolio') return <div className="split-grid"><ResourceSection title={t("Projects")} resource="projects" {...{ user, data, query, reload, notify }} /><ResourceSection title={t("Internships")} resource="internships" {...{ user, data, query, reload, notify }} /></div>;
  if (page === 'activities') return <div className="section-stack"><div className="split-grid"><ResourceSection title={t("Activities")} resource="activities" {...{ user, data, query, reload, notify }} /><ResourceSection title={t("Honors")} resource="honors" {...{ user, data, query, reload, notify }} /></div><ResourceSection title={t("Achievements")} resource="achievements" {...{ user, data, query, reload, notify }} /></div>;
  if (page === 'recommendations') return <ResourceSection title={t("Recommendation letters")} resource="recommendations" {...{ user, data, query, reload, notify }} />;
  if (page === 'documents') return <DocumentsPage {...{ user, data, query, reload, notify }} />;
  if (page === 'certificates') return <DocumentsPage typeFilter="certificate" title={t("Certificates")} {...{ user, data, query, reload, notify }} />;
  const titleMap = { tasks: t('Tasks'), applications: t('University applications'), essays: t('Essays') };
  return <ResourceSection title={titleMap[page] || label(page)} resource={page} {...{ user, data, query, reload, notify }} />;
}

export default function App() {
  const [theme, setTheme] = useState(initialTheme);
  const [language, setLanguageState] = useState(getLanguage);
  const [user, setUser] = useState(null);
  const [data, setData] = useState(EMPTY_DATA);
  const [stats, setStats] = useState(null);
  const [page, setPageState] = useState(pageFromLocation);
  const [publicPage, setPublicPage] = useState(publicPageFromLocation);
  const [navigationContext, setNavigationContext] = useState(() => window.history.state?.navigationContext || null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resourceStatus, setResourceStatus] = useState({});
  const [isOnline, setIsOnline] = useState(() => navigator.onLine);
  const [toast, setToast] = useState(null);
  const [bootstrapping, setBootstrapping] = useState(() => api.hasSession());
  const [bootstrapError, setBootstrapError] = useState('');
  const bootstrapAttempted = useRef(false);

  const setPage = useCallback((nextPage, options = {}) => {
    const nextContext = options.context || null;
    const replace = Boolean(options.replace);
    setPageState(nextPage);
    setNavigationContext(nextContext);
    if (window.location.hash !== pageHash(nextPage) || nextContext || replace) writePageLocation(nextPage, nextContext, replace);
  }, []);

  const setPublicLocation = useCallback((nextPage, options = {}) => {
    setPublicPage(nextPage);
    writePublicLocation(nextPage, Boolean(options.replace));
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, []);

  const notify = useCallback((message, type = 'success') => {
    setToast({ message, type });
    window.setTimeout(() => setToast(null), 3500);
  }, []);

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    try {window.localStorage.setItem(THEME_KEY, theme);} catch {/* Keep the active theme for this session. */}
    const favicon = document.querySelector('link[data-theme-icon]');
    if (favicon) favicon.href = brandLogoFor(theme);
    const themeColor = document.getElementById('theme-color');
    if (themeColor) themeColor.content = getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim();
  }, [theme]);

  const toggleTheme = useCallback(() => setTheme((current) => current === 'dark' ? 'light' : 'dark'), []);
  const changeLanguage = useCallback((nextLanguage) => setLanguageState(setLanguage(nextLanguage)), []);

  useEffect(() => {
    if (user && !window.location.hash) writePageLocation(page, navigationContext, true);
    function handleHistoryNavigation(event) {
      setPageState(pageFromLocation());
      setPublicPage(publicPageFromLocation());
      setNavigationContext(event.state?.navigationContext || null);
    }
    window.addEventListener('popstate', handleHistoryNavigation);
    return () => window.removeEventListener('popstate', handleHistoryNavigation);
  }, [user]);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const loadUser = useCallback(async () => {
    const current = await api.me();
    setUser(current);
    return current;
  }, []);

  const loadData = useCallback(async (activeUser = user, requestedKeys = null) => {
    if (!activeUser || activeUser.must_change_password) return;
    setLoading(true);setError('');
    try {
      const studentResources = ['students', 'tasks', 'applications', 'documents', 'essays', 'achievements', 'researches', 'projects', 'internships', 'activities', 'honors', 'recommendations'].map((key) => [key, key]);
      const portalResources = [
      ['roadmapMissions', 'roadmap-missions'], ['communityPosts', 'community-posts'], ['bookings', 'bookings'],
      ['messageChannels', 'message-channels'], ['programServices', 'program-services'],
      ['scholarships', 'scholarships'], ['opportunityPrograms', 'opportunity-programs'],
      ['resourceLibrary', 'resource-library'], ['storeItems', 'store-items'], ['team', 'student-team'], ['supportTickets', 'support-tickets']];

      const resources = activeUser.role === 'parent' ?
      [['parentPortal', 'parent-portal']] :
      activeUser.role === 'organization' ?
      [...studentResources, ['bookings', 'bookings'], ['messageChannels', 'message-channels'], ['supportTickets', 'support-tickets']] :
      activeUser.role === 'teacher' ?
      [['students', 'students'], ['tasks', 'tasks'], ['roadmapMissions', 'roadmap-missions'], ['bookings', 'bookings'], ['messageChannels', 'message-channels']] :
      [...studentResources, ['universities', 'universities'], ...(activeUser.role === 'admin' ? [['schools', 'schools'], ['accounts', 'users/accounts'], ['counselorRoadmapTemplates', 'counselor-roadmap-templates'], ['counselorRoadmaps', 'counselor-roadmaps'], ['adminAuditEvents', 'users/audit-events'], ['supportTickets', 'support-tickets']] : isCounselor(activeUser) ? [['schools', 'schools'], ['roadmapMissions', 'roadmap-missions'], ['counselorRoadmapTemplates', 'counselor-roadmap-templates'], ['counselorRoadmaps', 'counselor-roadmaps'], ['programServices', 'program-services'], ['bookings', 'bookings'], ['messageChannels', 'message-channels'], ['supportTickets', 'support-tickets']] : portalResources)];
      const requested = requestedKeys ? new Set(requestedKeys) : null;
      const requests = [
      ...(activeUser.role === 'parent' ? [] : [['dashboard', () => api.dashboard()]]),
      ...resources.map(([key, endpoint]) => [key, () => api.list(endpoint)])].
      filter(([key]) => !requested || requested.has(key));
      setResourceStatus((current) => {
        const next = { ...current };
        requests.forEach(([key]) => {next[key] = { status: 'loading', error: '' };});
        return next;
      });
      const settled = await Promise.allSettled(requests.map(([, request]) => request()));
      const successfulResources = {};
      const nextStatuses = {};
      let dashboardStats;
      let unauthorized = false;
      settled.forEach((result, index) => {
        const key = requests[index][0];
        if (result.status === 'fulfilled') {
          nextStatuses[key] = { status: 'success', error: '' };
          if (key === 'dashboard') dashboardStats = result.value;else
          successfulResources[key] = result.value || [];
        } else {
          unauthorized ||= result.reason?.status === 401;
          nextStatuses[key] = { status: 'error', error: result.reason?.message || 'Unable to load this section.' };
        }
      });
      if (unauthorized) {
        api.logout();
        setUser(null);
        return;
      }
      if (dashboardStats !== undefined) setStats(dashboardStats);
      if (Object.keys(successfulResources).length) {
        setData((current) => ({ ...current, ...successfulResources }));
      }
      setResourceStatus((current) => ({ ...current, ...nextStatuses }));
      if (settled.length > 0 && settled.every((result) => result.status === 'rejected')) {
        setError(t("No new information could be loaded. Check your connection and retry."));
      }
    } catch (err) {
      setError(err.message);
    } finally {setLoading(false);}
  }, [user]);

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
    bootstrapSession();
  }, []);

  useEffect(() => {
    if (!user) return;
    const locationPage = window.location.hash.replace(/^#\/?/, '').split(/[/?]/)[0];
    if (!PAGE_META[locationPage] || !navigationFor(user).includes(page)) setPage(user.role === 'admin' ? 'admin_dashboard' : 'dashboard', { replace: true });
  }, [user, page, setPage]);

  async function afterLogin() {
    const current = await loadUser();
    setPage(current.role === 'admin' ? 'admin_dashboard' : 'dashboard', { replace: true });
    if (!current.must_change_password) await loadData(current);
  }
  async function afterPasswordChanged(current) {
    setUser(current);
    await loadData(current);
  }
  function logout() {api.logout();setUser(null);setData(EMPTY_DATA);setStats(null);setResourceStatus({});setBootstrapError('');setPageState('dashboard');setNavigationContext(null);setPublicLocation('landing', { replace: true });}
  const retryResources = useCallback((keys) => loadData(user, keys), [loadData, user]);

  if (bootstrapping) return <AppBootLoader message="Checking your secure session…" />;
  if (bootstrapError && !user) return <BootstrapError message={bootstrapError} onRetry={bootstrapSession} onSignOut={logout} />;
  if (!user) return publicPage === 'login' ? <Login onLogin={afterLogin} onBack={() => setPublicLocation('landing')} theme={theme} toggleTheme={toggleTheme} language={language} changeLanguage={changeLanguage} /> : <Landing onLogin={() => setPublicLocation('login')} theme={theme} toggleTheme={toggleTheme} language={language} changeLanguage={changeLanguage} />;
  if (user.must_change_password) return <ForcedPasswordChange user={user} onChanged={afterPasswordChanged} onSignOut={logout} theme={theme} toggleTheme={toggleTheme} language={language} changeLanguage={changeLanguage} />;
  return <>
    <AppShell {...{ user, data, stats, page, setPage, query, setQuery, loading, error, resourceStatus, retryResources, isOnline, refresh: () => loadData(user), notify, logout, theme, toggleTheme, language, changeLanguage }}>
      <PageRouter {...{ page, user, data, stats, query, reload: () => loadData(user), notify, setPage, navigationContext }} />
    </AppShell>
    {toast && <div className={`toast ${toast.type}`}>{toast.type === 'success' ? <ShieldCheck size={18} /> : <X size={18} />}{toast.message}</div>}
  </>;
}
