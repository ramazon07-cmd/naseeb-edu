import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, Award, Bell, BookOpen, BriefcaseBusiness, Building2, CheckCircle2,
  CalendarClock, CalendarDays, Check, ChevronRight, ClipboardCheck, Clock3, Compass,
  ContactRound, DollarSign, ExternalLink, Eye, FileText, Filter, Fingerprint, Flag, FolderKanban, Globe2, GraduationCap, Heart, LayoutDashboard,
  LibraryBig, ListChecks, LogOut, MapPin, Menu, MessageCircle, MessageSquareText, Moon,
  PackageOpen, Pencil, PenLine, Plus, RefreshCw, School, Search, Send, ShieldAlert, ShieldCheck,
  ShoppingCart, Sparkles, Sun, Target, Trash2, UserRound, Users, UsersRound, X,
} from 'lucide-react'
import { api } from './api'

const LABELS = {
  admin: 'Admin', counselor: 'School Counselor', teacher: 'Teacher', organization: 'Organization School', student: 'Student',
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
  cancelled: 'Cancelled', discussion: 'Discussion', question: 'Q&A', update: 'Update',
  public: 'Public', private: 'Private', urban: 'Urban', suburban: 'Suburban', rural: 'Rural',
  four_year: '4-year', two_year: '2-year', merit: 'Merit', need_based: 'Need-based', athletic: 'Athletic',
  full_ride: 'Full ride', full: 'Full funding', partial: 'Partial funding', fixed: 'Fixed amount',
  onsite: 'On-site', online: 'Online', hybrid: 'Hybrid', reach: 'Reach', strong_option: 'Strong option',
  academic: 'Academic', preferences: 'Preferences', financial: 'Financial', profile_strength: 'Profile strength',
  harassment: 'Harassment or bullying', unsafe: 'Unsafe content', privacy: 'Privacy concern', misinformation: 'Misinformation',
  resolved: 'Resolved', dismissed: 'Dismissed', none: 'No action', content_removed: 'Content removed',
  muted_24h: 'Muted 24 hours', muted_7d: 'Muted 7 days',
}

const label = (value) => LABELS[value] || value || '—'
const fullName = (user) => user?.full_name || [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.username || 'User'
const initials = (name) => String(name || 'U').split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()
const dateText = (value) => value ? new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value)) : '—'
const dateTimeText = (value) => value ? new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '—'
const isCounselor = (user) => ['admin', 'counselor'].includes(user?.role)
const isTaskManager = (user) => ['admin', 'counselor', 'teacher'].includes(user?.role)
const SHOW_DEMO_ACCOUNTS = import.meta.env.DEV && import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === 'true'
const PERSONALITY_QUIZ_URL = (import.meta.env.VITE_PERSONALITY_QUIZ_URL || '').trim()
const ownStudent = (data) => data.students?.[0]
const studentName = (data, id) => fullName(data.students?.find((student) => student.id === Number(id))?.user_detail)
const THEME_KEY = 'naseeb-edu-theme'

function initialTheme() {
  const saved = window.localStorage.getItem(THEME_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function BrandLogo({ theme, className = '' }) {
  const source = theme === 'dark' ? '/brand/naseeb-dark.png' : '/brand/naseeb-light.jpg'
  return <img className={`brand-logo ${className}`} src={source} alt="Naseeb Edu" />
}

function BrandLockup({ theme }) {
  return <div className="brand-lockup"><BrandLogo theme={theme} /><div><b>Naseeb Edu</b><small>Education Counseling Platform</small></div></div>
}

function ThemeToggle({ theme, onToggle }) {
  const isDark = theme === 'dark'
  return <button type="button" className="icon-button theme-toggle" onClick={onToggle} title={isDark ? 'Light mode' : 'Dark mode'} aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'} aria-pressed={isDark}>{isDark ? <Sun size={18} /> : <Moon size={18} />}</button>
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
  meetings: { label: 'Meetings', icon: BriefcaseBusiness, description: 'Counselor meeting notes' },
  notifications: { label: 'Notifications', icon: Bell, description: 'Deadline and document alerts' },
  student_center: { label: 'Student Center', icon: UsersRound, description: 'Academic profile, portfolio, activities, and documents' },
  roadmap: { label: 'Roadmap', icon: Compass, description: 'Level-linked missions, milestones, and reflections' },
  community: { label: 'Community', icon: Users, description: 'Student discussions, questions, and shared experience' },
  bookings: { label: 'Bookings', icon: CalendarClock, description: 'Schedule meetings with your counselor' },
  messages: { label: 'Messages', icon: MessageCircle, description: 'Direct, Group, Community, and Discussion messages' },
  program_usage: { label: 'Program Usage', icon: ListChecks, description: 'Services, mentors, and usage balance' },
  programs: { label: 'Programs', icon: Globe2, description: 'National and international opportunity catalog' },
  resource_index: { label: 'Resource Index', icon: LibraryBig, description: 'All tools and resources for students' },
  essay_lab: { label: 'Essay Lab', icon: PenLine, description: 'Essay drafts, feedback, and revision history' },
  college_search: { label: 'College Search', icon: School, description: 'Find, compare, and shortlist universities' },
  store: { label: 'Naseeb Store', icon: ShoppingCart, description: 'Additional education and application services' },
  contacts: { label: 'Contacts', icon: ContactRound, description: 'Contact your counselor and school coordinator' },
}

function navigationFor(user) {
  if (isCounselor(user)) return ['dashboard', 'schools', 'students', 'academics', 'portfolio', 'activities', 'recommendations', 'tasks', 'roadmap', 'applications', 'documents', 'certificates', 'essays', 'meetings', 'messages']
  if (user?.role === 'teacher') return ['dashboard', 'students', 'tasks', 'roadmap', 'messages']
  if (user?.role === 'organization') return ['dashboard', 'students', 'messages']
  return ['dashboard', 'student_center', 'roadmap', 'community', 'bookings', 'messages', 'program_usage', 'programs', 'resource_index', 'essay_lab', 'applications', 'college_search', 'store', 'contacts']
}

const EMPTY_DATA = {
  schools: [], students: [], universities: [], tasks: [], applications: [], documents: [], essays: [],
  achievements: [], researches: [], projects: [], internships: [], activities: [], honors: [],
  recommendations: [], meetings: [], notifications: [], roadmapMissions: [], communityPosts: [],
  bookings: [], studentMessages: [], messageChannels: [], programServices: [], scholarships: [], opportunityPrograms: [], resourceLibrary: [], storeItems: [], team: [],
}

const RESOURCE_FIELDS = {
  researches: [
    ['title', 'Research title', 'text', true], ['field', 'Field'], ['role', 'Role'],
    ['summary', 'Summary', 'textarea', true], ['outcome', 'Outcome'], ['start_date', 'Start date', 'date'],
    ['end_date', 'End date', 'date'], ['link', 'Link', 'url'], ['google_docs_url', 'Google Docs URL', 'url'],
  ],
  projects: [
    ['title', 'Project title', 'text', true], ['role', 'Role'], ['technologies', 'Technologies'],
    ['description', 'Description', 'textarea', true], ['impact', 'Measurable impact'], ['date', 'Date', 'date'], ['link', 'Link', 'url'],
    ['google_docs_url', 'Google Docs URL', 'url'],
  ],
  internships: [
    ['organization', 'Organization', 'text', true], ['position', 'Position', 'text', true], ['supervisor', 'Supervisor'],
    ['description', 'Responsibilities and results', 'textarea'], ['start_date', 'Start date', 'date'], ['end_date', 'End date', 'date'],
    ['is_current', 'Current internship', 'checkbox'], ['google_docs_url', 'Google Docs URL', 'url'],
  ],
  activities: [
    ['name', 'Activity name', 'text', true], ['activity_type', 'Type', 'select', true, ['extracurricular', 'volunteering', 'leadership', 'club', 'competition', 'community', 'other']],
    ['role', 'Role'], ['description', 'Description', 'textarea'], ['impact', 'Impact'],
    ['hours_per_week', 'Hours per week', 'number'], ['weeks_per_year', 'Weeks per year', 'number'],
    ['google_docs_url', 'Google Docs URL', 'url'],
  ],
  honors: [
    ['title', 'Honor title', 'text', true], ['issuer', 'Issuer'], ['level', 'Level', 'select', true, ['school', 'regional', 'national', 'international']],
    ['award_date', 'Award date', 'date'], ['description', 'Description', 'textarea'], ['google_docs_url', 'Google Docs URL', 'url'],
  ],
  achievements: [
    ['title', 'Achievement title', 'text', true], ['category', 'Category', 'select', true, ['project', 'startup', 'olympiad', 'volunteering', 'leadership', 'research', 'sport', 'art', 'other']],
    ['date', 'Date', 'date'], ['impact', 'Impact'], ['description', 'Description', 'textarea', true],
  ],
  recommendations: [
    ['recommender_name', 'Recommender name', 'text', true], ['recommender_title', 'Position'], ['recommender_email', 'Email', 'email'],
    ['relationship', 'Relationship'], ['status', 'Status', 'select', true, ['requested', 'drafting', 'submitted', 'approved']],
    ['deadline', 'Deadline', 'date'], ['notes', 'Notes', 'textarea'], ['google_docs_url', 'Google Docs URL', 'url'],
  ],
  tasks: [
    ['title', 'Task title', 'text', true], ['description', 'Description', 'textarea'], ['due_date', 'Due date', 'date', true],
    ['priority', 'Priority', 'select', true, ['low', 'medium', 'high', 'urgent']],
    ['status', 'Status', 'select', true, ['todo', 'in_progress', 'submitted', 'late']],
    ['student_response', 'Student response', 'textarea'], ['submission_url', 'Submission or Google Docs URL', 'url'],
    ['submission_file', 'Submission file', 'file'],
  ],
  applications: [
    ['university', 'University', 'university', true], ['program', 'Program', 'text', true],
    ['tier', 'Tier', 'select', true, ['dream', 'target', 'safety']],
    ['status', 'Status', 'select', true, ['researching', 'shortlisted', 'applying', 'submitted', 'accepted', 'rejected', 'waitlisted']],
    ['deadline', 'Deadline', 'date'], ['scholarship_deadline', 'Scholarship deadline', 'date'], ['application_portal_url', 'Portal URL', 'url'], ['notes', 'Notes', 'textarea'],
  ],
  essays: [
    ['application', 'Application', 'application'], ['title', 'Essay title', 'text', true], ['prompt', 'Prompt', 'textarea', true],
    ['content', 'Draft content', 'textarea'], ['status', 'Status', 'select', true, ['draft', 'reviewing', 'needs_revision', 'approved']],
    ['google_docs_url', 'Google Docs URL', 'url'], ['counselor_comment', 'Counselor comment', 'textarea'],
  ],
  meetings: [
    ['title', 'Meeting title', 'text', true], ['meeting_date', 'Meeting date', 'date', true],
    ['summary', 'Summary', 'textarea', true], ['next_steps', 'Next steps', 'textarea'],
  ],
}

function Login({ onLogin, theme, toggleTheme }) {
  const [form, setForm] = useState(SHOW_DEMO_ACCOUNTS
    ? { username: 'counselor', password: 'admin12345' }
    : { username: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      await api.login(form.username, form.password)
      await onLogin()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return <main className="login-page">
    <section className="login-copy">
      <BrandLogo theme={theme} className="login-emblem" />
      <span className="eyebrow">NASEEB EDU / EDUCATION PLATFORM</span>
      <h1>Every opportunity.<br />One trusted path.</h1>
      <p>A professional counseling platform connecting students in Uzbekistan with global education opportunities.</p>
      <span className="brand-tagline">Bridging Uzbekistan to the World Through Education</span>
    </section>
    <form className="login-card" onSubmit={submit}>
      <div className="login-brand-row"><BrandLockup theme={theme} /><ThemeToggle theme={theme} onToggle={toggleTheme} /></div>
      <div><h2>Sign in</h2><p>Enter your username and password.</p></div>
      <Field label="Username"><input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} autoComplete="username" required /></Field>
      <Field label="Password"><input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="current-password" required /></Field>
      {error && <div className="alert error">{error}</div>}
      <button className="button primary full" disabled={loading} aria-busy={loading}>{loading ? 'Signing in…' : 'Sign in'}<ChevronRight size={18} /></button>
      {SHOW_DEMO_ACCOUNTS && <div className="demo-hint">Demo: counselor / admin12345</div>}
    </form>
  </main>
}

function Field({ label: title, children }) {
  return <label className="field"><span>{title}</span>{children}</label>
}

function CheckboxControl({ children, className = '', ...props }) {
  return <label className={`checkbox-card ${className}`.trim()}>
    <input type="checkbox" {...props} />
    <span className="checkbox-indicator" aria-hidden="true"><Check size={14} strokeWidth={3} /></span>
    <span>{children}</span>
  </label>
}

function ChoiceCards({ name, label: groupLabel, value, onChange, options }) {
  function handleKeyDown(event, index) {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
    event.preventDefault()
    const direction = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1
    const nextIndex = (index + direction + options.length) % options.length
    onChange(options[nextIndex].value)
    event.currentTarget.closest('.choice-card-group')?.querySelectorAll('input')[nextIndex]?.focus()
  }
  return <div className="choice-card-group" role="radiogroup" aria-label={groupLabel} style={{ '--choice-columns': options.length }}>
    {options.map((option, index) => {
      const OptionIcon = option.icon || Target
      return <label className="choice-card" key={option.value}>
        <input type="radio" name={name} value={option.value} checked={value === option.value} onChange={() => onChange(option.value)} onKeyDown={(event) => handleKeyDown(event, index)} />
        <OptionIcon aria-hidden="true" />
        <span className="choice-card-copy"><b>{option.label}</b><small>{option.description}</small></span>
        <CheckCircle2 className="choice-card-check" size={19} aria-hidden="true" />
      </label>
    })}
  </div>
}

function Badge({ children, tone = '' }) {
  const normalized = String(children || '').toLowerCase().replaceAll(' ', '-')
  return <span className={`badge ${tone || normalized}`}>{label(children)}</span>
}

function Modal({ title, onClose, children }) {
  const modalRef = useRef(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  useEffect(() => {
    const previous = document.activeElement
    const modal = modalRef.current
    const focusable = () => [...(modal?.querySelectorAll('button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])') || [])]
    focusable()[0]?.focus()
    function handleKeyDown(event) {
      if (event.key === 'Escape') { event.preventDefault(); onCloseRef.current(); return }
      if (event.key !== 'Tab') return
      const items = focusable()
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => { document.removeEventListener('keydown', handleKeyDown); previous?.focus?.() }
  }, [])
  return <div className="modal-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
    <section ref={modalRef} className="modal" role="dialog" aria-modal="true" aria-label={title} tabIndex="-1">
      <header><div><span className="eyebrow">NASEEB EDU</span><h2>{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close"><X /></button></header>
      {children}
    </section>
  </div>
}

function Empty({ text = 'No information available yet.' }) {
  return <div className="empty"><span>07</span><p>{text}</p></div>
}

function NotificationCenter({ data, refresh, notify }) {
  const [open, setOpen] = useState(false)
  const notifications = data.notifications || []
  const unread = notifications.filter((item) => !item.is_read).length
  useEffect(() => {
    if (!open) return undefined
    function closeOnEscape(event) { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [open])
  async function markRead(item) {
    try {
      await api.markNotificationRead(item.id)
      await refresh()
    } catch (err) { notify(err.message, 'error') }
  }
  return <div className={`notification-center ${open ? 'open' : ''}`}>
    {open && <section className="notification-drawer" aria-label="Notifications">
      <header><div><span className="eyebrow">UPDATES</span><h2>Notifications</h2></div><button type="button" className="icon-button" onClick={() => setOpen(false)} aria-label="Close notifications"><X size={18} /></button></header>
      <div className="notification-drawer-list">{notifications.map((item) => <article className={item.is_read ? 'read' : 'unread'} key={item.id}><span className="notification-item-icon"><Bell size={16} /></span><div><header><b>{item.title}</b>{!item.is_read && <i />}</header><p>{item.message}</p><small>{studentName(data, item.student) || 'Your account'} · {dateTimeText(item.created_at)}</small>{!item.is_read && <button type="button" onClick={() => markRead(item)}>Mark as read</button>}</div></article>)}{!notifications.length && <Empty text="You have no notifications yet." />}</div>
    </section>}
    <button type="button" className="notification-launcher" onClick={() => setOpen((current) => !current)} aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`} aria-expanded={open}><Bell size={22} />{unread > 0 && <span>{unread > 99 ? '99+' : unread}</span>}</button>
  </div>
}

function AppShell({ user, data, stats, page, setPage, query, setQuery, loading, error, refresh, notify, logout, theme, toggleTheme, children }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigation = navigationFor(user)
  const meta = PAGE_META[page]
  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
      <div className="sidebar-top">
        <BrandLockup theme={theme} />
        <button className="icon-button mobile-only" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X /></button>
      </div>
      <nav>{navigation.map((item) => {
        const ItemIcon = PAGE_META[item].icon
        return <button key={item} className={page === item ? 'active' : ''} onClick={() => { setPage(item); setMobileOpen(false) }}><ItemIcon size={18} /><span>{PAGE_META[item].label}</span></button>
      })}</nav>
      <div className="sidebar-profile"><span className="avatar">{initials(fullName(user))}</span><div><b>{fullName(user)}</b><small>{label(user.role)}</small></div><button className="icon-button" onClick={logout} title="Logout"><LogOut size={18} /></button></div>
    </aside>
    <main className="workspace">
      <header className="top-header">
        <button className="icon-button mobile-only" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu /></button>
        <div className="page-heading"><span className="eyebrow">07 / {meta.label.toUpperCase()}</span><h1>{meta.label}</h1><p>{meta.description}</p></div>
        <div className="header-actions">
          <label className="search"><Search size={17} /><input placeholder="Search…" value={query} onChange={(e) => setQuery(e.target.value)} /></label>
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
          <button className="icon-button" onClick={refresh} disabled={loading} aria-busy={loading} title="Refresh"><RefreshCw className={loading ? 'spin' : ''} size={19} /></button>
        </div>
      </header>
      {error && <div className="alert error workspace-alert">{error}</div>}
      <div className="page-content">{children}</div>
    </main>
    {['admin', 'counselor', 'organization', 'student'].includes(user.role) && <NotificationCenter data={data} refresh={refresh} notify={notify} />}
  </div>
}

function Dashboard({ user, data, stats, setPage }) {
  const student = ownStudent(data)
  if (user.role === 'organization') return <>
    <div className="stat-grid"><Stat label="School students" value={stats?.students_total ?? data.students.length} note="Only students from your school" /><Stat label="Task progress" value={`${stats?.average_task_progress ?? 0}%`} note="Weighted completion" /><Stat label="Roadmap progress" value={`${stats?.average_roadmap_progress ?? 0}%`} note="Mission completion" /><Stat label="Need attention" value={stats?.students_at_risk ?? 0} note="Late task or mission" tone="danger" /></div>
    <Panel title="Student progress" action={<button className="button primary" onClick={() => setPage('students')}>Student profiles <ChevronRight size={17} /></button>}><StudentTable data={data} readOnly /></Panel>
  </>
  if (user.role === 'student') return <StudentDashboard user={user} data={data} stats={stats} setPage={setPage} />
  return <>
    <div className="stat-grid"><Stat label="Students" value={stats?.students_total ?? data.students.length} /><Stat label="Task progress" value={`${stats?.average_task_progress ?? 0}%`} /><Stat label="Roadmap progress" value={`${stats?.average_roadmap_progress ?? 0}%`} /><Stat label="Need attention" value={stats?.students_at_risk ?? stats?.tasks_late ?? 0} tone="danger" /></div>
    <div className="split-grid wide-left"><Panel title="Student progress" action={<button className="button quiet" onClick={() => setPage('students')}>View all <ChevronRight size={16} /></button>}><StudentTable data={data} readOnly /></Panel><Panel title="Deadline radar">{data.tasks.slice(0, 6).map((task) => <Record key={task.id} title={task.title} meta={`${studentName(data, task.student)} • ${dateText(task.due_date)}`} badge={task.status} />)}{!data.tasks.length && <Empty />}</Panel></div>
  </>
}

function StudentDashboard({ user, data, setPage }) {
  const student = ownStudent(data)
  const pendingTasks = data.tasks.filter((item) => item.status !== 'approved')
  const nextBooking = [...data.bookings].filter((item) => new Date(item.starts_at) >= new Date() && item.status !== 'cancelled').sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at))[0]
  const completed = data.tasks.filter((item) => item.status === 'approved').length
  const achievementTotal = data.achievements.length + data.honors.length
  return <div className="section-stack student-portal">
    <section className="student-welcome">
      <div><span className="eyebrow">WELCOME BACK</span><h2>{fullName(user)}</h2><p>Complete today’s priorities and strengthen your application profile.</p><div className="welcome-actions"><button className="button light" onClick={() => setPage('roadmap')}><Compass size={17} /> Open roadmap</button><button className="button ghost-light" onClick={() => setPage('college_search')}><Search size={17} /> Find universities</button></div></div>
      <div className="readiness-ring" style={{ '--progress': `${student?.journey_progress_percent || 0}%` }}><strong>{student?.journey_progress_percent || 0}%</strong><span>Journey progress</span></div>
    </section>
    <div className="student-dashboard-overview">
      <div className="student-dashboard-progress"><JourneyProgress student={student} /><LevelProgress student={student} /></div>
      <DashboardDiscoveryCards setPage={setPage} />
    </div>
    <div className="stat-grid"><Stat label="Active tasks" value={pendingTasks.length} note={`${completed} completed`} /><Stat label="Applications" value={data.applications.length} note={`${data.applications.filter((item) => item.status === 'submitted').length} submitted`} /><Stat label="Essays" value={data.essays.length} note={`${data.essays.filter((item) => item.status === 'approved').length} approved`} /><Stat label="Achievements" value={achievementTotal} note="Honors included" /></div>
    <div className="student-dashboard-grid">
      <div className="student-dashboard-column">
        <Panel title="Next priorities" action={<button className="button quiet small" onClick={() => setPage('roadmap')}>View roadmap <ChevronRight size={14} /></button>}><div className="record-list">{pendingTasks.slice(0, 4).map((task) => <Record key={task.id} title={task.title} meta={`${dateText(task.due_date)} • ${label(task.priority)}`} badge={task.status} />)}{!pendingTasks.length && <Empty text="All tasks are complete." />}</div></Panel>
        <Panel title="Upcoming session" action={<button className="button quiet small" onClick={() => setPage('bookings')}>Bookings</button>}>{nextBooking ? <div className="booking-highlight"><span><CalendarClock size={22} /></span><div><b>{nextBooking.topic}</b><small>{dateTimeText(nextBooking.starts_at)} • {nextBooking.duration_minutes} min</small><p>{nextBooking.counselor_name || 'Assigned counselor'}</p></div><Badge>{nextBooking.status}</Badge></div> : <Empty text="No upcoming sessions." />}</Panel>
      </div>
      <div className="student-dashboard-column">
        <Panel title="Student Center quick access"><div className="quick-grid">{[
          ['Profile & academics', 'student_center', BookOpen], ['Essay Lab', 'essay_lab', PenLine], ['Applications', 'applications', Target], ['Resources', 'resource_index', LibraryBig],
        ].map(([title, page, Icon]) => <button key={page} onClick={() => setPage(page)}><span><Icon size={19} /></span><b>{title}</b><ChevronRight size={15} /></button>)}</div></Panel>
        <Panel title="My Naseeb team" action={<button className="button quiet small" onClick={() => setPage('contacts')}>All contacts</button>}><div className="team-mini-list">{data.team.slice(0, 3).map((member) => <div key={`${member.kind}-${member.id}`}><span className="avatar">{initials(member.name)}</span><div><b>{member.name}</b><small>{member.role}</small></div><button className="icon-button" onClick={() => setPage('messages')} aria-label={`Message ${member.name}`}><MessageCircle size={16} /></button></div>)}{!data.team.length && <Empty text="No team members have been assigned yet." />}</div></Panel>
      </div>
    </div>
  </div>
}

function DashboardDiscoveryCards({ setPage }) {
  const personalityAction = PERSONALITY_QUIZ_URL
    ? <a href={PERSONALITY_QUIZ_URL} target="_blank" rel="noreferrer">Start assessment <ExternalLink size={15} /></a>
    : <button type="button" disabled title="Add VITE_PERSONALITY_QUIZ_URL to enable this assessment">Link coming soon</button>
  return <section className="dashboard-discovery-rail" aria-label="Student discovery tools">
    <article className="dashboard-discovery-card personality">
      <Fingerprint className="discovery-card-art" size={118} strokeWidth={1.35} />
      <div><span>SELF DISCOVERY</span><h3>Personality & Interests</h3><p>Identify your strengths, interests, and future study direction.</p>{personalityAction}</div>
    </article>
    <article className="dashboard-discovery-card university">
      <GraduationCap className="discovery-card-art" size={122} strokeWidth={1.35} />
      <div><span>COLLEGE RESEARCH</span><h3>University Match</h3><p>Find universities that match your academic profile and goals.</p><button type="button" onClick={() => setPage('college_search')}>Explore matches <ChevronRight size={16} /></button></div>
    </article>
  </section>
}

function JourneyProgress({ student }) {
  const rows = [
    ['Tasks', student?.task_progress_percent || 0, `${student?.task_status_counts?.approved || 0} approved`],
    ['Roadmap', student?.roadmap_progress_percent || 0, `${student?.roadmap_status_counts?.completed || 0} completed`],
    ['Overall journey', student?.journey_progress_percent || 0, student?.is_at_risk ? 'A deadline needs your attention' : 'Progress is on track'],
  ]
  return <section className="journey-progress"><div><span className="eyebrow">LIVE PROGRESS</span><h3>Tasks and roadmap progress</h3><p>Every update is added to your overall progress automatically.</p></div><div className="journey-progress-bars">{rows.map(([title, value, note]) => <div key={title}><header><b>{title}</b><strong>{value}%</strong></header><div className="progress"><span style={{ width: `${value}%` }} /></div><small>{note}</small></div>)}</div></section>
}

function LevelProgress({ student }) {
  if (!student) return null
  return <section className="journey-progress"><div><span className="eyebrow">XP & LEVEL</span><h3>Level {student.level || 1}</h3><p>{student.level_up_pending ? `Teacher or counselor approval is pending for Level ${student.eligible_level}.` : `Next level: ${student.next_level_xp} XP`}</p></div><div className="journey-progress-bars"><div><header><b>{student.xp_total || 0} XP</b><strong>{student.xp_progress_percent || 0}%</strong></header><div className="progress"><span style={{ width: `${student.xp_progress_percent || 0}%` }} /></div><small>{student.level_up_pending ? 'XP threshold reached — your level changes only after approval.' : `${Math.max(0, (student.next_level_xp || 0) - (student.xp_total || 0))} XP remaining`}</small></div></div></section>
}

function Stat({ label: title, value, note, tone = '' }) {
  return <article className={`stat-card ${tone}`}><span>{title}</span><strong>{value}</strong>{note && <small>{note}</small>}</article>
}

function Panel({ title, action, children, className = '' }) {
  return <section className={`panel ${className}`}><header><h2>{title}</h2>{action}</header><div className="panel-body">{children}</div></section>
}

function Record({ title, meta, description, badge, actions }) {
  return <article className="record"><div className="record-main"><div><b>{title}</b>{meta && <small>{meta}</small>}</div>{badge && <Badge>{badge}</Badge>}</div>{description && <p>{description}</p>}{actions && <div className="record-actions">{actions}</div>}</article>
}

function GoogleDocsPreview({ previewUrl, title }) {
  if (!previewUrl) return null
  return <div className="google-doc-preview"><div><FileText size={18} /><span><b>Google Docs preview</b><small>The document must allow Viewer access or “Anyone with the link” for the preview to load.</small></span></div><iframe src={previewUrl} title={`${title} Google Docs preview`} loading="lazy" referrerPolicy="no-referrer" /></div>
}

function googleDocsTitle(item) {
  return item.title || item.name || item.organization || item.recommender_name || 'Google Docs record'
}

function GoogleDocsActions({ item, onPreview }) {
  if (!item?.google_docs_url) return null
  return <>
    {item.google_docs_preview_url && onPreview && <button type="button" className="button quiet small" onClick={onPreview}><Eye size={14} /> Preview</button>}
    <a className="button quiet small" href={item.google_docs_url} target="_blank" rel="noreferrer">Open in Google Docs <ExternalLink size={14} /></a>
  </>
}

function GoogleDocsRecordModal({ item, onClose }) {
  const title = googleDocsTitle(item)
  return <Modal title={title} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><span>Google Docs attachment</span><GoogleDocsActions item={item} /></div><GoogleDocsPreview previewUrl={item.google_docs_preview_url} title={title} /></div></Modal>
}

function EssayDetailModal({ essay, onClose }) {
  return <Modal title={essay.title} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><div><Badge>{essay.status}</Badge><span>Version {essay.version} · {essay.university_name || 'General essay'}</span></div><GoogleDocsActions item={essay} /></div><section><span className="detail-label">Essay prompt</span><p>{essay.prompt}</p></section>{essay.google_docs_preview_url ? <GoogleDocsPreview previewUrl={essay.google_docs_preview_url} title={essay.title} /> : <section><span className="detail-label">Current draft</span><div className="essay-content-preview">{essay.content || 'No draft content has been added yet.'}</div></section>}{essay.counselor_comment && <section className="counselor-feedback"><span className="detail-label">Counselor feedback</span><p>{essay.counselor_comment}</p></section>}{essay.revisions?.length > 0 && <section><span className="detail-label">Revision history</span><div className="revision-chips">{essay.revisions.map((revision) => <span key={revision.id}>v{revision.version} · {label(revision.status)} · {dateText(revision.created_at)}</span>)}</div></section>}</div></Modal>
}

function TaskSubmissionModal({ task, onClose }) {
  return <Modal title={`Task response · ${task.title}`} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><div><Badge>{task.status}</Badge><span>{task.submitted_at ? `Submitted ${dateTimeText(task.submitted_at)}` : 'Not submitted yet'}</span></div><div className="detail-actions">{task.submission_file && <a className="button quiet" href={task.submission_file} target="_blank" rel="noreferrer">Open file <ExternalLink size={15} /></a>}{task.submission_url && <a className="button primary" href={task.submission_url} target="_blank" rel="noreferrer">Open submission <ExternalLink size={15} /></a>}</div></div><section><span className="detail-label">Assigned task</span><p>{task.description || 'No additional instructions.'}</p></section><section><span className="detail-label">Student response</span><div className="essay-content-preview">{task.student_response || 'The student has not submitted a written response yet.'}</div></section><GoogleDocsPreview previewUrl={task.submission_preview_url} title={task.title} /></div></Modal>
}

function DocumentPreviewModal({ document: doc, onClose }) {
  return <Modal title={doc.title} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><div><Badge>{doc.status}</Badge><span>{label(doc.document_type)}</span></div><div className="detail-actions">{doc.file && <a className="button quiet" href={doc.file} target="_blank" rel="noreferrer">Open file <ExternalLink size={15} /></a>}<GoogleDocsActions item={doc} /></div></div>{doc.counselor_comment && <section><span className="detail-label">Counselor comment</span><p>{doc.counselor_comment}</p></section>}{doc.google_docs_preview_url ? <GoogleDocsPreview previewUrl={doc.google_docs_preview_url} title={doc.title} /> : !doc.file && <Empty text="No file or Google Docs link has been added for preview." />}</div></Modal>
}

function ProfileCard({ student }) {
  if (!student) return <Panel title="Profile"><Empty text="Student profile not found." /></Panel>
  return <Panel title="Profile overview" className="profile-card"><div className="profile-identity"><span className="avatar large">{initials(fullName(student.user_detail))}</span><div><h3>{fullName(student.user_detail)}</h3><p>{student.user_detail?.email}</p></div></div><div className="detail-grid"><Detail label="School" value={student.school_name} /><Detail label="Grade" value={student.grade === 'gap' ? 'Gap year' : `Grade ${student.grade}`} /><Detail label="Counselor" value={student.counselor_name} /><Detail label="Major" value={student.target_major} /><Detail label="GPA" value={student.gpa} /><Detail label="IELTS" value={student.ielts_score} /><Detail label="SAT" value={student.sat_score} /><Detail label="Countries" value={student.target_countries} /><Detail label="Scholarship" value={student.scholarship_needed ? 'Needed' : 'Not needed'} /></div></Panel>
}

function Detail({ label: title, value }) {
  return <div className="detail"><span>{title}</span><b>{value || '—'}</b></div>
}

function StudentTable({ data, onView, onEdit, onDelete, onApproveLevel, readOnly = false, query = '' }) {
  const rows = data.students.filter((student) => fullName(student.user_detail).toLowerCase().includes(query.toLowerCase()))
  if (!rows.length) return <Empty text="No students found." />
  const hasActions = Boolean(onView || onApproveLevel || (!readOnly && (onEdit || onDelete)))
  return <div className="table-wrap"><table><thead><tr><th>Student</th><th>School</th><th>Target</th><th>Scores</th><th>XP / Level</th><th>Task / Roadmap / Overall</th>{hasActions && <th />}</tr></thead><tbody>{rows.map((student) => <tr key={student.id} className={onView ? 'clickable-row' : ''} onDoubleClick={() => onView?.(student)}><td><div className="person"><span className="avatar">{initials(fullName(student.user_detail))}</span><div><b>{fullName(student.user_detail)}</b><small>{student.user_detail?.email}</small>{student.is_at_risk && <span className="risk-note">Needs attention</span>}</div></div></td><td>{student.school_name || '—'}</td><td><b>{student.target_major || '—'}</b><small>{student.target_countries || '—'}</small></td><td>GPA {student.gpa || '—'}<small>IELTS {student.ielts_score || '—'} • SAT {student.sat_score || '—'}</small></td><td><b>Level {student.level || 1}</b><small>{student.xp_total || 0} XP</small>{student.level_up_pending && <span className="risk-note">Level {student.eligible_level} pending</span>}</td><td><div className="student-progress-stack">{[['Task', student.task_progress_percent], ['Roadmap', student.roadmap_progress_percent], ['Overall', student.journey_progress_percent]].map(([title, value]) => <div key={title}><span>{title}</span><div className="progress"><i style={{ width: `${value || 0}%` }} /></div><b>{value || 0}%</b></div>)}</div></td>{hasActions && <td><div className="row-actions">{onApproveLevel && student.level_up_pending && <button className="button quiet small" onClick={() => onApproveLevel(student)}><CheckCircle2 size={15} /> Approve level</button>}{onView && <button className="icon-button" onClick={() => onView(student)} title="Full profile"><Eye size={16} /></button>}{!readOnly && onEdit && <button className="icon-button" onClick={() => onEdit(student)} title="Edit"><Pencil size={16} /></button>}{!readOnly && onDelete && <button className="icon-button danger" onClick={() => onDelete(student)} title="Delete"><Trash2 size={16} /></button>}</div></td>}</tr>)}</tbody></table></div>
}

const STUDENT_RESOURCE_GROUPS = [
  ['Research', 'researches'], ['Projects', 'projects'], ['Internships', 'internships'],
  ['Activities', 'activities'], ['Honors', 'honors'], ['Achievements', 'achievements'],
  ['Recommendation letters', 'recommendations'], ['Counselor meetings', 'meetings'],
]

function studentItems(data, resource, studentId) {
  return (data[resource] || []).filter((item) => Number(item.student) === Number(studentId))
}

function StudentOverviewList({ title, resource, items, data }) {
  const [viewingGoogleDoc, setViewingGoogleDoc] = useState(null)
  return <><Panel title={title}><div className="record-list">{items.map((item) => <RecordRow key={item.id} resource={resource} item={item} data={data} actions={<GoogleDocsActions item={item} onPreview={() => setViewingGoogleDoc(item)} />} />)}{!items.length && <Empty />}</div></Panel>{viewingGoogleDoc && <GoogleDocsRecordModal item={viewingGoogleDoc} onClose={() => setViewingGoogleDoc(null)} />}</>
}

function StudentTaskList({ items, onView }) {
  return <Panel title="Assigned tasks & responses"><div className="record-list">{items.map((task) => <Record key={task.id} title={task.title} meta={`${dateText(task.due_date)} · ${label(task.priority)}${task.submitted_at ? ` · Submitted ${dateText(task.submitted_at)}` : ''}`} description={task.student_response || task.description} badge={task.status} actions={<button className="button quiet small" onClick={() => onView(task)}><Eye size={14} /> View response</button>} />)}{!items.length && <Empty text="No assigned tasks found." />}</div></Panel>
}

function StudentCollegeList({ items }) {
  return <Panel title="College list"><div className="record-list">{items.map((application) => <Record key={application.id} title={application.university_detail?.name || 'University'} meta={`${application.program} · ${label(application.tier)} · Deadline ${dateText(application.deadline)}`} description={application.notes} badge={application.status} actions={application.application_portal_url && <a className="button quiet small" href={application.application_portal_url} target="_blank" rel="noreferrer">Application portal <ExternalLink size={14} /></a>} />)}{!items.length && <Empty text="The student has not added any universities to the college list yet." />}</div></Panel>
}

function StudentEssayList({ items, onView }) {
  return <Panel title="Essays & Google Docs"><div className="record-list">{items.map((essay) => <Record key={essay.id} title={essay.title} meta={`Version ${essay.version} · ${essay.university_name || 'General essay'}`} description={essay.counselor_comment || essay.prompt} badge={essay.status} actions={<><button className="button quiet small" onClick={() => onView(essay)}><Eye size={14} /> Essay details</button><GoogleDocsActions item={essay} /></>} />)}{!items.length && <Empty text="No essays found." />}</div></Panel>
}

function StudentDocumentList({ title, items, onPreview }) {
  return <Panel title={title}><div className="record-list">{items.map((doc) => <Record key={doc.id} title={doc.title} meta={label(doc.document_type)} description={doc.counselor_comment} badge={doc.status} actions={<>{(doc.google_docs_preview_url || doc.file) && <button className="button quiet small" onClick={() => onPreview(doc)}><Eye size={14} /> Preview</button>}{doc.file && <a className="button quiet small" href={doc.file} target="_blank" rel="noreferrer">Open file</a>}<GoogleDocsActions item={doc} /></>} />)}{!items.length && <Empty />}</div></Panel>
}

function StudentOverview({ student, data, onBack }) {
  const [selectedTask, setSelectedTask] = useState(null)
  const [selectedEssay, setSelectedEssay] = useState(null)
  const [selectedDocument, setSelectedDocument] = useState(null)
  if (!student) return <Empty text="Student profile not found." />
  const documents = studentItems(data, 'documents', student.id)
  const certificates = documents.filter((item) => item.document_type === 'certificate')
  const regularDocuments = documents.filter((item) => item.document_type !== 'certificate')
  const tasks = studentItems(data, 'tasks', student.id)
  const applications = studentItems(data, 'applications', student.id)
  const essays = studentItems(data, 'essays', student.id)
  const notifications = studentItems(data, 'notifications', student.id)

  return <div className="section-stack student-overview">
    <section className="student-overview-hero">
      <div className="student-overview-title">{onBack && <button className="button quiet" onClick={onBack}>← Students</button>}<div className="profile-identity"><span className="avatar large">{initials(fullName(student.user_detail))}</span><div><span className="eyebrow">STUDENT 360° PROFILE</span><h2>{fullName(student.user_detail)}</h2><p>{student.user_detail?.email} • {student.school_name || 'No school assigned'}</p></div></div></div>
      <div className="overview-progress"><strong>{student.progress_percent || 0}%</strong><span>Application readiness</span><div className="progress wide"><span style={{ width: `${student.progress_percent || 0}%` }} /></div></div>
    </section>
    <div className="stat-grid"><Stat label="Level" value={student.level || 1} note={student.level_up_pending ? `Level ${student.eligible_level} approval pending` : 'Teacher approved'} /><Stat label="XP" value={student.xp_total || 0} note={`Next: ${student.next_level_xp} XP`} /><Stat label="Assigned tasks" value={tasks.length} /><Stat label="Applications" value={applications.length} /></div>
    <LevelProgress student={student} />
    <div className="split-grid wide-left"><ProfileCard student={student} /><Panel title="Contact & planning"><div className="detail-grid"><Detail label="Phone" value={student.user_detail?.phone} /><Detail label="Parent contact" value={student.parent_contact} /><Detail label="Budget USD" value={student.budget_usd} /><Detail label="Target countries" value={student.target_countries} /><Detail label="Scholarship" value={student.scholarship_needed ? 'Needed' : 'Not needed'} /><Detail label="Counselor" value={student.counselor_name} /></div>{student.notes && <div className="student-notes"><span>Internal notes</span><p>{student.notes}</p></div>}</Panel></div>
    <div className="overview-grid student-workspace-grid"><StudentTaskList items={tasks} onView={setSelectedTask} /><StudentCollegeList items={applications} /><StudentEssayList items={essays} onView={setSelectedEssay} /><StudentDocumentList title="Documents" items={regularDocuments} onPreview={setSelectedDocument} /></div>
    <div className="overview-grid">
      {STUDENT_RESOURCE_GROUPS.map(([title, resource]) => <StudentOverviewList key={resource} title={title} resource={resource} items={studentItems(data, resource, student.id)} data={data} />)}
      <StudentDocumentList title="Certificates" items={certificates} onPreview={setSelectedDocument} />
      <Panel title="Notifications"><div className="record-list">{notifications.map((item) => <Record key={item.id} title={item.title} meta={dateText(item.created_at)} description={item.message} badge={item.is_read ? 'Read' : 'Unread'} />)}{!notifications.length && <Empty />}</div></Panel>
    </div>
    {selectedTask && <TaskSubmissionModal task={selectedTask} onClose={() => setSelectedTask(null)} />}
    {selectedEssay && <EssayDetailModal essay={selectedEssay} onClose={() => setSelectedEssay(null)} />}
    {selectedDocument && <DocumentPreviewModal document={selectedDocument} onClose={() => setSelectedDocument(null)} />}
  </div>
}

function StudentsPage({ user, data, query, reload, notify }) {
  const [editing, setEditing] = useState(null)
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState(null)

  async function remove(student) {
    if (!window.confirm(`Delete ${fullName(student.user_detail)}’s profile?`)) return
    try { await api.remove('students', student.id); notify('Student deleted.'); reload() } catch (err) { notify(err.message, 'error') }
  }

  async function approveLevel(student) {
    try {
      const result = await api.approveStudentLevel(student.id)
      notify(`Level ${result.level} approved.`)
      reload()
    } catch (err) { notify(err.message, 'error') }
  }

  if (selected) return <StudentOverview student={data.students.find((item) => item.id === selected.id) || selected} data={data} onBack={() => setSelected(null)} />

  return <>
    <Panel title="Students" action={user.role !== 'teacher' && <button className="button primary" onClick={() => { setEditing(null); setOpen(true) }}><Plus size={17} /> Add student</button>}><StudentTable data={data} query={query} onView={setSelected} onApproveLevel={isTaskManager(user) ? approveLevel : undefined} onEdit={user.role !== 'teacher' ? (student) => { setEditing(student); setOpen(true) } : undefined} onDelete={user.role !== 'teacher' ? remove : undefined} /></Panel>
    {open && <StudentForm user={user} data={data} student={editing} onClose={() => setOpen(false)} onSaved={() => { setOpen(false); reload() }} notify={notify} />}
  </>
}

function StudentForm({ user, data, student, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    name: fullName(student?.user_detail) === 'User' ? '' : fullName(student?.user_detail), email: student?.user_detail?.email || '',
    password: '',
    grade: student?.grade || '11', target_major: student?.target_major || '', target_countries: student?.target_countries || '',
    gpa: student?.gpa || '', ielts_score: student?.ielts_score || '', sat_score: student?.sat_score || '',
    budget_usd: student?.budget_usd || '', parent_contact: student?.parent_contact || '', notes: student?.notes || '',
    scholarship_needed: student?.scholarship_needed ?? true, school: student?.school || user.school || '',
  })
  function update(name, value) { setForm((current) => ({ ...current, [name]: value })) }
  async function submit(event) {
    event.preventDefault(); setSaving(true)
    try {
      if (student) await api.update('students', student.id, { grade: form.grade, target_major: form.target_major, target_countries: form.target_countries, gpa: form.gpa || null, ielts_score: form.ielts_score || null, sat_score: form.sat_score || null, budget_usd: form.budget_usd || null, parent_contact: form.parent_contact, notes: form.notes, scholarship_needed: form.scholarship_needed, school: Number(form.school) })
      else await api.quickCreateStudent({ name: form.name, email: form.email, password: form.password, grade: form.grade, major: form.target_major, countries: form.target_countries, gpa: form.gpa, ielts: form.ielts_score, sat: form.sat_score, budget_usd: form.budget_usd, parent_contact: form.parent_contact, notes: form.notes, scholarship_needed: form.scholarship_needed, school: form.school })
      notify(student ? 'Student updated.' : 'Student created.'); onSaved()
    } catch (err) { notify(err.message, 'error') } finally { setSaving(false) }
  }
  return <Modal title={student ? 'Edit student' : 'Add student'} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <Field label="Full name"><input value={form.name} onChange={(e) => update('name', e.target.value)} disabled={Boolean(student)} required /></Field>
    <Field label="Email"><input type="email" value={form.email} onChange={(e) => update('email', e.target.value)} disabled={Boolean(student)} /></Field>
    {!student && <Field label="Initial password"><input type="password" value={form.password} onChange={(e) => update('password', e.target.value)} minLength="12" autoComplete="new-password" required /></Field>}
    <Field label="Grade"><select value={form.grade} onChange={(e) => update('grade', e.target.value)}>{['8','9','10','11','gap'].map((item) => <option key={item} value={item}>{item === 'gap' ? 'Gap year' : `Grade ${item}`}</option>)}</select></Field>
    {isCounselor(user) && <Field label="School"><select value={form.school} onChange={(e) => update('school', e.target.value)} required><option value="">Select school</option>{data.schools.map((school) => <option key={school.id} value={school.id}>{school.name}</option>)}</select></Field>}
    <Field label="Target major"><input value={form.target_major} onChange={(e) => update('target_major', e.target.value)} required /></Field>
    <Field label="Target countries"><input value={form.target_countries} onChange={(e) => update('target_countries', e.target.value)} required /></Field>
    <Field label="GPA"><input type="number" step=".01" value={form.gpa} onChange={(e) => update('gpa', e.target.value)} /></Field>
    <Field label="IELTS"><input type="number" step=".5" value={form.ielts_score} onChange={(e) => update('ielts_score', e.target.value)} /></Field>
    <Field label="SAT"><input type="number" value={form.sat_score} onChange={(e) => update('sat_score', e.target.value)} /></Field>
    <Field label="Annual budget USD"><input type="number" value={form.budget_usd} onChange={(e) => update('budget_usd', e.target.value)} /></Field>
    <Field label="Parent contact"><input value={form.parent_contact} onChange={(e) => update('parent_contact', e.target.value)} /></Field>
    <Field label="Notes"><textarea value={form.notes} onChange={(e) => update('notes', e.target.value)} /></Field>
    <CheckboxControl className="form-wide" checked={form.scholarship_needed} onChange={(e) => update('scholarship_needed', e.target.checked)}>Scholarship needed</CheckboxControl>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? 'Saving…' : 'Save student'}</button></div>
  </form></Modal>
}

function SchoolsPage({ data, reload, notify }) {
  const [open, setOpen] = useState(false)
  async function remove(school) {
    if (!window.confirm(`Delete ${school.name}?`)) return
    try { await api.remove('schools', school.id); notify('School deleted.'); reload() } catch (err) { notify(err.message, 'error') }
  }
  return <><Panel title="Organization schools" action={<button className="button primary" onClick={() => setOpen(true)}><Plus size={17} /> Add school</button>}><div className="card-grid">{data.schools.map((school) => <article className="school-card" key={school.id}><div className="school-number">{String(school.id).padStart(2, '0')}</div><div><h3>{school.name}</h3><p>{school.contact_email || 'No email'} • {school.contact_phone || 'No phone'}</p><span>{school.students_count || 0} students</span></div><button className="icon-button danger" onClick={() => remove(school)} aria-label={`Delete ${school.name}`}><Trash2 size={16} /></button></article>)}{!data.schools.length && <Empty />}</div></Panel>{open && <SchoolForm onClose={() => setOpen(false)} onSaved={() => { setOpen(false); reload() }} notify={notify} />}</>
}

function SchoolForm({ onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false)
  async function submit(event) {
    event.preventDefault(); setSaving(true); const values = new FormData(event.currentTarget)
    try {
      const school = await api.create('schools', { name: values.get('name'), code: values.get('code'), contact_email: values.get('contact_email'), contact_phone: values.get('contact_phone'), is_active: true })
      await api.createSchoolAccount(school.id, { username: values.get('username'), email: values.get('account_email'), password: values.get('password'), first_name: values.get('name'), last_name: 'Organization' })
      notify('School and organization account created.'); onSaved()
    } catch (err) { notify(err.message, 'error') } finally { setSaving(false) }
  }
  return <Modal title="Add organization school" onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label="School name"><input name="name" required /></Field><Field label="Unique code"><input name="code" required /></Field><Field label="Contact email"><input name="contact_email" type="email" /></Field><Field label="Contact phone"><input name="contact_phone" /></Field><Field label="Login username"><input name="username" required /></Field><Field label="Login email"><input name="account_email" type="email" required /></Field><Field label="Temporary password"><input name="password" type="password" minLength="8" required /></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? 'Creating…' : 'Create school'}</button></div></form></Modal>
}

function ResourceSection({ title, resource, data, user, query, reload, notify, canCreate = true }) {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [viewingEssay, setViewingEssay] = useState(null)
  const [viewingTask, setViewingTask] = useState(null)
  const [viewingGoogleDoc, setViewingGoogleDoc] = useState(null)
  const records = data[resource] || []
  const filtered = records.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()))
  const counselorOnly = ['meetings'].includes(resource)
  const staffControlled = resource === 'tasks'
  const allowCreate = canCreate && (staffControlled ? isTaskManager(user) : (isCounselor(user) || (!counselorOnly && user.role === 'student')))
  const allowEdit = staffControlled ? isTaskManager(user) || user.role === 'student' : allowCreate

  async function approve(item) {
    try { const result = await api.approveTask(item.id); notify(`Task approved. +${result.xp_awarded || 0} XP`); reload() } catch (err) { notify(err.message, 'error') }
  }

  async function remove(item) {
    if (!window.confirm('Delete this record?')) return
    try { await api.remove(resource, item.id); notify('Record deleted.'); reload() } catch (err) { notify(err.message, 'error') }
  }
  return <><Panel title={title} action={allowCreate && <button className="button quiet" onClick={() => { setEditing(null); setOpen(true) }}><Plus size={16} /> Add</button>}><div className="record-list">{filtered.map((item) => {
    const lockedAfterApproval = item.status === 'approved'
    return <RecordRow key={item.id} resource={resource} item={item} data={data} actions={<>{resource === 'tasks' && <button className="button quiet small" onClick={() => setViewingTask(item)}><Eye size={14} /> Response</button>}{resource === 'essays' && <button className="button quiet small" onClick={() => setViewingEssay(item)}><Eye size={14} /> Details</button>}{resource !== 'essays' && <GoogleDocsActions item={item} onPreview={() => setViewingGoogleDoc(item)} />}{isTaskManager(user) && staffControlled && item.status === 'submitted' && <button className="button quiet small" onClick={() => approve(item)}><CheckCircle2 size={15} /> Approve</button>}{allowEdit && !lockedAfterApproval && <button className="icon-button" onClick={() => { setEditing(item); setOpen(true) }} aria-label={`Edit ${title}`}><Pencil size={15} /></button>}{allowCreate && <button className="icon-button danger" onClick={() => remove(item)} aria-label={`Delete ${title}`}><Trash2 size={15} /></button>}</>} />
  })}{!filtered.length && <Empty />}</div></Panel>{open && <ResourceForm resource={resource} item={editing} data={data} user={user} onClose={() => setOpen(false)} onSaved={() => { setOpen(false); reload() }} notify={notify} />}{viewingEssay && <EssayDetailModal essay={viewingEssay} onClose={() => setViewingEssay(null)} />}{viewingTask && <TaskSubmissionModal task={viewingTask} onClose={() => setViewingTask(null)} />}{viewingGoogleDoc && <GoogleDocsRecordModal item={viewingGoogleDoc} onClose={() => setViewingGoogleDoc(null)} />}</>
}

function RecordRow({ resource, item, data, actions }) {
  const student = studentName(data, item.student)
  const map = {
    researches: [item.title, `${student} • ${item.field || 'Research'} • ${item.role || '—'}`, item.summary, item.verified ? 'approved' : 'reviewing'],
    projects: [item.title, `${student} • ${item.role || 'Project'} • ${item.technologies || '—'}`, item.description, item.verified ? 'approved' : 'reviewing'],
    internships: [`${item.position} — ${item.organization}`, `${student} • ${dateText(item.start_date)} — ${item.is_current ? 'Current' : dateText(item.end_date)}`, item.description, item.verified ? 'approved' : 'reviewing'],
    activities: [item.name, `${student} • ${label(item.activity_type)} • ${item.role || '—'}`, item.impact || item.description, item.verified ? 'approved' : 'reviewing'],
    honors: [item.title, `${student} • ${item.issuer || '—'} • ${label(item.level)}`, item.description, item.verified ? 'approved' : 'reviewing'],
    achievements: [item.title, `${student} • ${label(item.category)} • ${dateText(item.date)}`, item.impact || item.description, item.verified ? 'approved' : 'reviewing'],
    recommendations: [item.recommender_name, `${student} • ${item.recommender_title || '—'} • ${item.relationship || '—'}`, `Deadline: ${dateText(item.deadline)}`, item.status],
    tasks: [item.title, `${student} • ${dateText(item.due_date)} • ${label(item.priority)}${item.submitted_at ? ` • Submitted ${dateText(item.submitted_at)}` : ''}`, item.student_response || item.description, item.status],
    applications: [item.university_detail?.name || 'University', `${student} • ${item.program} • ${label(item.tier)}`, `Deadline: ${dateText(item.deadline)}`, item.status],
    essays: [item.title, `${student} • Version ${item.version} • ${item.university_name || 'General'}`, item.counselor_comment || item.prompt, item.status],
    meetings: [item.title, `${student} • ${dateText(item.meeting_date)}`, item.next_steps || item.summary, null],
  }
  const [title, meta, description, badge] = map[resource] || ['Record', student, '', null]
  return <Record title={title} meta={meta} description={description} badge={badge} actions={actions} />
}

function ResourceForm({ resource, item, data, user, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false)
  const allFields = RESOURCE_FIELDS[resource] || []
  const fields = resource === 'tasks' && user.role === 'student'
    ? allFields.filter(([name]) => ['status', 'student_response', 'submission_url', 'submission_file'].includes(name))
    : allFields
  async function submit(event) {
    event.preventDefault(); setSaving(true); const values = new FormData(event.currentTarget)
    const usesFileUpload = fields.some(([name, , type]) => type === 'file' && values.get(name)?.size)
    const payload = usesFileUpload ? new FormData() : {}
    for (const [name, , type] of fields) {
      const raw = values.get(name)
      if (type === 'file') {
        if (raw?.size && payload instanceof FormData) payload.append(name, raw)
        continue
      }
      const normalized = type === 'checkbox' ? raw === 'on' : (raw === '' ? null : raw)
      if (payload instanceof FormData) payload.append(name, normalized ?? '')
      else payload[name] = normalized
    }
    if (!item) {
      const studentId = isTaskManager(user) ? Number(values.get('student')) : ownStudent(data)?.id
      if (payload instanceof FormData) payload.append('student', studentId)
      else payload.student = studentId
    }
    try {
      if (item) await api.update(resource, item.id, payload)
      else await api.create(resource, payload)
      notify(item ? 'Record updated.' : 'Record created.'); onSaved()
    } catch (err) { notify(err.message, 'error') } finally { setSaving(false) }
  }
  return <Modal title={`${item ? 'Edit' : 'Add'} ${resource}`} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    {!item && isTaskManager(user) && <Field label="Student"><select name="student" required>{data.students.map((student) => <option key={student.id} value={student.id}>{fullName(student.user_detail)}</option>)}</select></Field>}
    {fields.map(([name, title, type = 'text', required = false, choices = []]) => <DynamicField key={name} name={name} labelText={title} type={type} required={required} choices={choices} value={item?.[name]} data={data} user={user} />)}
    {fields.some(([name]) => name === 'google_docs_url') && <div className="form-wide google-doc-sharing-hint"><ShieldCheck size={16} /><span>Set Google Docs sharing to Viewer or “Anyone with the link” to enable the preview.</span></div>}
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? 'Saving…' : 'Save'}</button></div>
  </form></Modal>
}

function DynamicField({ name, labelText, type, required, choices, value, data, user }) {
  if (name === 'status' && !isTaskManager(user)) choices = choices.filter((choice) => !['approved', 'late', 'rejected', 'waitlisted', 'accepted', 'needs_revision', 'completed'].includes(choice))
  if (type === 'textarea') return <Field label={labelText}><textarea name={name} defaultValue={value || ''} required={required} /></Field>
  if (type === 'select') return <Field label={labelText}><select name={name} defaultValue={value || choices[0]} required={required}>{choices.map((choice) => <option key={choice} value={choice}>{label(choice)}</option>)}</select></Field>
  if (type === 'checkbox') return <CheckboxControl className="form-wide" name={name} defaultChecked={Boolean(value)}>{labelText}</CheckboxControl>
  if (type === 'file') return <Field label={labelText}><input name={name} type="file" accept=".pdf,.doc,.docx,.png,.jpg,.jpeg" /></Field>
  if (type === 'university') return <Field label={labelText}><select name={name} defaultValue={value || ''} required={required}><option value="">Select university</option>{data.universities.map((uni) => <option key={uni.id} value={uni.id}>{uni.name} — {uni.country}</option>)}</select></Field>
  if (type === 'application') return <Field label={labelText}><select name={name} defaultValue={value || ''}><option value="">General essay</option>{data.applications.map((app) => <option key={app.id} value={app.id}>{app.university_detail?.name} — {studentName(data, app.student)}</option>)}</select></Field>
  return <Field label={labelText}><input name={name} type={type} defaultValue={value ?? ''} required={required} /></Field>
}

function DocumentsPage({ user, data, query, reload, notify, typeFilter = '', title = 'Documents' }) {
  const [open, setOpen] = useState(false)
  const [previewing, setPreviewing] = useState(null)
  const docs = data.documents.filter((item) => (!typeFilter || item.document_type === typeFilter) && JSON.stringify(item).toLowerCase().includes(query.toLowerCase()))
  async function approve(doc) { try { await api.update('documents', doc.id, { status: 'approved' }); notify('Document approved.'); reload() } catch (err) { notify(err.message, 'error') } }
  return <><Panel title={title} action={<button className="button primary" onClick={() => setOpen(true)}><Plus size={16} /> {typeFilter === 'certificate' ? 'Upload certificate' : 'Upload document'}</button>}><div className="record-list">{docs.map((doc) => <Record key={doc.id} title={doc.title} meta={`${studentName(data, doc.student)} • ${label(doc.document_type)}`} description={doc.counselor_comment} badge={doc.status} actions={<>{(doc.google_docs_preview_url || doc.file) && <button className="button quiet small" onClick={() => setPreviewing(doc)}><Eye size={14} /> Preview</button>}{doc.file && <a className="button quiet small" href={doc.file} target="_blank" rel="noreferrer">Open file</a>}<GoogleDocsActions item={doc} />{isCounselor(user) && doc.status !== 'approved' && <button className="button quiet small" onClick={() => approve(doc)}><CheckCircle2 size={15} /> Approve</button>}</>} />)}{!docs.length && <Empty />}</div></Panel>{open && <DocumentForm user={user} data={data} defaultType={typeFilter} onClose={() => setOpen(false)} onSaved={() => { setOpen(false); reload() }} notify={notify} />}{previewing && <DocumentPreviewModal document={previewing} onClose={() => setPreviewing(null)} />}</>
}

function DocumentForm({ user, data, defaultType = '', onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false)
  async function submit(event) {
    event.preventDefault(); setSaving(true); const values = new FormData(event.currentTarget); const payload = new FormData()
    payload.append('student', isCounselor(user) ? values.get('student') : ownStudent(data)?.id)
    for (const name of ['title', 'document_type', 'status', 'counselor_comment', 'google_docs_url']) payload.append(name, values.get(name) || '')
    const file = values.get('file'); if (file?.size) payload.append('file', file)
    try { await api.create('documents', payload); notify('Document uploaded.'); onSaved() } catch (err) { notify(err.message, 'error') } finally { setSaving(false) }
  }
  return <Modal title={defaultType === 'certificate' ? 'Upload certificate' : 'Upload document'} onClose={onClose}><form className="form-grid" onSubmit={submit}>{isCounselor(user) && <Field label="Student"><select name="student">{data.students.map((student) => <option value={student.id} key={student.id}>{fullName(student.user_detail)}</option>)}</select></Field>}<Field label="Title"><input name="title" required /></Field><Field label="Type"><select name="document_type" defaultValue={defaultType || 'passport'} disabled={Boolean(defaultType)}>{['passport','transcript','ielts','sat','cv','recommendation','essay','certificate','other'].map((item) => <option key={item} value={item}>{label(item)}</option>)}</select>{defaultType && <input type="hidden" name="document_type" value={defaultType} />}</Field><Field label="Status"><select name="status">{(isCounselor(user) ? ['required','uploaded','reviewing','approved','rejected'] : ['uploaded']).map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></Field><Field label="Comment"><textarea name="counselor_comment" /></Field><Field label="File"><input name="file" type="file" accept=".pdf,.doc,.docx,.png,.jpg,.jpeg" /></Field><Field label="Google Docs URL"><input name="google_docs_url" type="url" placeholder="https://docs.google.com/document/d/.../edit" /></Field><div className="form-wide google-doc-sharing-hint"><ShieldCheck size={16} /><span>Set Google Docs sharing to Viewer or “Anyone with the link” to enable the preview.</span></div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? 'Uploading…' : 'Upload'}</button></div></form></Modal>
}

function NotificationsPage({ data, reload, notify }) {
  async function mark(item) { try { await api.markNotificationRead(item.id); reload() } catch (err) { notify(err.message, 'error') } }
  return <Panel title="Notifications"><div className="record-list">{data.notifications.map((item) => <Record key={item.id} title={item.title} meta={`${studentName(data, item.student)} • ${dateText(item.created_at)}`} description={item.message} badge={item.is_read ? 'Read' : 'Unread'} actions={!item.is_read && <button className="button quiet small" onClick={() => mark(item)}>Mark as read</button>} />)}{!data.notifications.length && <Empty />}</div></Panel>
}

function PortalTabs({ items, active, onChange }) {
  function handleKeyDown(event, index) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length
    onChange(items[nextIndex][0])
    event.currentTarget.parentElement?.querySelectorAll('[role="tab"]')[nextIndex]?.focus()
  }
  return <div className="portal-tabs" role="tablist">{items.map(([key, title], index) => <button type="button" role="tab" aria-selected={active === key} tabIndex={active === key ? 0 : -1} key={key} className={active === key ? 'active' : ''} onClick={() => onChange(key)} onKeyDown={(event) => handleKeyDown(event, index)}>{title}</button>)}</div>
}

function StudentCenterPage({ user, data, query, reload, notify }) {
  const [tab, setTab] = useState('overview')
  return <div className="section-stack student-portal">
    <PortalTabs active={tab} onChange={setTab} items={[["overview", "Overview"], ["academics", "Academics"], ["portfolio", "Portfolio"], ["activities", "Activities & honors"], ["documents", "Documents"]]} />
    {tab === 'overview' && <StudentOverview student={ownStudent(data)} data={data} />}
    {tab === 'academics' && <div className="section-stack"><ProfileCard student={ownStudent(data)} /><ResourceSection title="Research & academic work" resource="researches" {...{ user, data, query, reload, notify }} /></div>}
    {tab === 'portfolio' && <div className="split-grid"><ResourceSection title="Projects" resource="projects" {...{ user, data, query, reload, notify }} /><ResourceSection title="Internships" resource="internships" {...{ user, data, query, reload, notify }} /></div>}
    {tab === 'activities' && <div className="section-stack"><div className="split-grid"><ResourceSection title="Activities" resource="activities" {...{ user, data, query, reload, notify }} /><ResourceSection title="Honors" resource="honors" {...{ user, data, query, reload, notify }} /></div><div className="split-grid"><ResourceSection title="Achievements" resource="achievements" {...{ user, data, query, reload, notify }} /><ResourceSection title="Recommendation letters" resource="recommendations" {...{ user, data, query, reload, notify }} /></div></div>}
    {tab === 'documents' && <DocumentsPage {...{ user, data, query, reload, notify }} />}
  </div>
}

function MissionForm({ mission, user, data, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false)
  const manager = isTaskManager(user)
  const studentSubmitted = !manager && mission?.status === 'submitted'
  async function submit(event) {
    event.preventDefault(); setSaving(true); const values = new FormData(event.currentTarget)
    const payload = manager
      ? { title: values.get('title'), category: values.get('category'), description: values.get('description'), due_date: values.get('due_date') || null, status: values.get('status') }
      : { status: 'submitted', reflection: values.get('reflection') }
    if (manager && !mission) payload.student = Number(values.get('student'))
    try { mission ? await api.update('roadmap-missions', mission.id, payload) : await api.create('roadmap-missions', payload); notify(manager ? (mission ? 'Mission updated.' : 'Mission created.') : 'Mission submitted for approval.'); onSaved() } catch (err) { notify(err.message, 'error') } finally { setSaving(false) }
  }
  const statuses = ['planned', 'in_progress', 'submitted']
  return <Modal title={manager ? (mission ? 'Edit roadmap mission' : 'Assign roadmap mission') : (studentSubmitted ? 'Mission submitted' : 'Submit roadmap mission')} onClose={onClose}><form className="form-grid" onSubmit={submit}>{manager && !mission && <Field label="Student"><select name="student" required>{data.students.map((student) => <option key={student.id} value={student.id}>{fullName(student.user_detail)}</option>)}</select></Field>}{manager && <><Field label="Mission title"><input name="title" defaultValue={mission?.title || ''} required /></Field><Field label="Category"><input name="category" defaultValue={mission?.category || ''} placeholder="Applications, Essays..." /></Field><Field label="Due date"><input name="due_date" type="date" defaultValue={mission?.due_date || ''} /></Field><Field label="Status"><select name="status" defaultValue={mission?.status || 'planned'}>{statuses.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></Field></>}{!manager && <div className={`form-wide mission-submit-status ${studentSubmitted ? 'submitted' : 'planned'}`}>{studentSubmitted ? <Clock3 size={21} /> : <Sparkles size={21} />}<div><b>{studentSubmitted ? 'Submitted' : 'Planned mission'}</b><p>{studentSubmitted ? 'Your work is awaiting teacher or counselor approval.' : 'Complete the mission, write your reflection, then submit it for approval.'}</p></div></div>}{manager ? <Field label="Description"><textarea name="description" defaultValue={mission?.description || ''} /></Field> : <Field label="Reflection"><textarea name="reflection" defaultValue={mission?.reflection || ''} placeholder="What did you learn while completing this mission?" required readOnly={studentSubmitted} /></Field>}<div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{studentSubmitted ? 'Close' : 'Cancel'}</button>{!studentSubmitted && <button className="button primary" disabled={saving} aria-busy={saving}>{saving ? (manager ? 'Saving…' : 'Submitting…') : (manager ? 'Save' : 'Submit mission')}</button>}</div></form></Modal>
}

function LevelOneSetupModal({ data, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false)
  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    const values = new FormData(event.currentTarget)
    try {
      const result = await api.extendLevelOneRoadmap(Number(values.get('student')))
      notify(result.created_count ? `${result.created_count} Level 1 missions added.` : 'Level 1 is already up to date.')
      onSaved()
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }
  return <Modal title="Extend Level 1 roadmap" onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label="Student"><select name="student" required>{data.students.map((student) => <option key={student.id} value={student.id}>{fullName(student.user_detail)}</option>)}</select></Field><div className="form-wide roadmap-setup-note"><Sparkles size={19} /><div><b>8-step Level 1 path</b><p>Missing missions will be added in the correct order. Existing statuses, reflections and approvals stay unchanged.</p></div></div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving || !data.students.length} aria-busy={saving}>{saving ? 'Extending…' : 'Extend Level 1'}</button></div></form></Modal>
}

function StudentRoadmapPath({ student, missions, onOpen }) {
  const level = student?.level || 1
  const levelMissions = missions
    .filter((item) => (item.level || 1) === level)
    .sort((a, b) => (a.sequence || 1) - (b.sequence || 1))
  const missionById = new Map(levelMissions.map((item) => [item.id, item]))
  const completed = levelMissions.filter((item) => item.status === 'completed').length
  const activeIndex = levelMissions.findIndex((item) => item.status !== 'completed')
  const currentIndex = activeIndex === -1 ? Math.max(0, levelMissions.length - 1) : activeIndex
  const nextLevel = student?.level_up_pending ? student.eligible_level : Math.min(50, level + 1)
  const isLocked = (item) => item.prerequisite && missionById.get(item.prerequisite)?.status !== 'completed'
  function missionState(item, index) {
    if (item.status === 'completed') return 'complete'
    if (item.status === 'submitted') return 'approval'
    if (isLocked(item)) return 'locked'
    if (item.status === 'in_progress' || index === currentIndex) return 'current'
    return 'upcoming'
  }
  return <section className="level-roadmap-shell">
    <header className="level-roadmap-summary">
      <div><span className="eyebrow">LEVEL {level} · MISSION {Math.min(completed + 1, Math.max(1, levelMissions.length))} OF {Math.max(1, levelMissions.length)}</span><h2>{levelMissions[currentIndex]?.title || 'Your next milestone'}</h2><p>{student?.level_up_pending ? `You have earned enough XP for Level ${student.eligible_level}. Teacher or counselor approval is pending.` : 'Complete each mission in order, submit your reflection, and earn XP after staff approval.'}</p></div>
      <div className="roadmap-level-score"><span><Award size={18} /> Level {level}</span><strong>{student?.xp_total || 0} XP</strong><small>{student?.level_up_pending ? 'Level approval pending' : `${Math.max(0, (student?.next_level_xp || 0) - (student?.xp_total || 0))} XP to next level`}</small></div>
    </header>
    <div className="roadmap-path-stats"><span><CheckCircle2 size={17} /><b>{completed}</b> approved missions</span><span><Sparkles size={17} /><b>75 XP</b> per approved mission</span><span><Target size={17} /><b>Level {nextLevel}</b> next checkpoint</span></div>
    <div className="roadmap-xp-track"><span style={{ width: `${student?.xp_progress_percent || 0}%` }} /><b>{student?.xp_progress_percent || 0}%</b></div>
    {levelMissions.length ? <div className="level-roadmap-path">{levelMissions.map((item, index) => {
      const state = missionState(item, index)
      const NodeIcon = state === 'complete' ? Check : state === 'approval' ? Clock3 : item.status === 'planned' ? Sparkles : state === 'current' ? BookOpen : state === 'locked' ? ShieldCheck : Sparkles
      return <article className={`roadmap-path-row ${state}`} style={{ '--path-offset': `${[0, -78, 0, 78][index % 4]}px` }} key={item.id}>
        <button type="button" className="roadmap-node" onClick={() => onOpen(item)} disabled={state === 'complete' || state === 'locked'} aria-label={`${item.title}, ${state === 'locked' ? 'locked' : label(item.status)}`}><NodeIcon size={30} strokeWidth={2.7} /></button>
        <div className="roadmap-node-card"><span>Step {item.sequence || index + 1} · {item.category || 'Roadmap'}</span>{item.status === 'planned' && <div className="mission-status-chip"><Sparkles size={12} /> Planned</div>}<h3>{item.title}</h3><p>{state === 'complete' ? 'Approved · XP awarded' : state === 'approval' ? 'Submitted · awaiting staff approval' : state === 'locked' ? 'Locked · complete the previous mission first' : item.status === 'planned' ? 'Complete the task and submit when ready' : state === 'current' ? 'Continue the mission and submit when ready' : `Upcoming · due ${dateText(item.due_date)}`}</p></div>
      </article>
    })}<div className="roadmap-checkpoint"><span><Award size={26} /></span><div><small>NEXT CHECKPOINT</small><h3>Level {nextLevel}</h3><p>{student?.level_up_pending ? 'Ready for staff approval' : `${student?.next_level_xp || 0} total XP required`}</p></div></div></div> : <Empty text="Your counselor has not assigned any roadmap missions yet." />}
  </section>
}

function RoadmapPage({ user, data, query, reload, notify }) {
  const manager = isTaskManager(user)
  const [tab, setTab] = useState(manager ? 'missions' : 'path')
  const [editing, setEditing] = useState(null)
  const [open, setOpen] = useState(false)
  const [setupOpen, setSetupOpen] = useState(false)
  const student = ownStudent(data)
  async function remove(item) { if (!window.confirm('Delete this mission?')) return; try { await api.remove('roadmap-missions', item.id); notify('Mission deleted.'); reload() } catch (err) { notify(err.message, 'error') } }
  async function approve(item) { try { const result = await api.approveRoadmapMission(item.id); notify(`Roadmap mission approved. +${result.xp_awarded || 0} XP`); reload() } catch (err) { notify(err.message, 'error') } }
  const timeline = [
    ...data.tasks.map((item) => ({ id: `task-${item.id}`, title: item.title, date: item.due_date, status: item.status, kind: 'Task' })),
    ...data.roadmapMissions.map((item) => ({ id: `mission-${item.id}`, title: item.title, date: item.due_date, status: item.status, kind: 'Mission' })),
  ].filter((item) => item.date).sort((a, b) => new Date(a.date) - new Date(b.date))
  return <div className="section-stack student-portal">
    <section className="portal-hero roadmap-hero"><div><span className="eyebrow">YOUR APPLICATION PLAN</span><h2>Roadmap</h2><p>{manager ? 'Assign missions, review student submissions, and approve the work that earns XP.' : 'Follow your visual learning path, submit reflections, and level up after teacher or counselor approval.'}</p></div>{manager && <div className="roadmap-hero-actions"><button className="button light" onClick={() => setSetupOpen(true)}><Sparkles size={17} /> Extend Level 1</button><button className="button light" onClick={() => { setEditing(null); setOpen(true) }}><Plus size={17} /> Assign mission</button></div>}</section>
    <PortalTabs active={tab} onChange={setTab} items={manager ? [["missions", "Mission list"], ["tasks", "Task list"], ["timeline", "Timeline view"], ["reflections", "Reflection view"]] : [["path", "Level path"], ["tasks", "Task list"], ["missions", "Mission list"], ["reflections", "Reflections"]]} />
    {tab === 'path' && !manager && <StudentRoadmapPath student={student} missions={data.roadmapMissions} onOpen={(item) => { setEditing(item); setOpen(true) }} />}
    {tab === 'tasks' && <ResourceSection title="My tasks" resource="tasks" {...{ user, data, query, reload, notify }} />}
    {tab === 'missions' && <div className="mission-grid">{data.roadmapMissions.map((item) => <article className="mission-card" key={item.id}><div className="mission-top"><span>Level {item.level || 1} · Step {item.sequence || 1} · {item.category || 'Roadmap'}</span>{item.status === 'planned' ? <div className="mission-status-chip"><Sparkles size={12} /> Planned</div> : <Badge>{item.status}</Badge>}</div><h3>{item.title}</h3><p>{item.description || 'No description provided.'}</p>{manager && <small>{item.student_name} • Assigned by {item.assigned_by_name || 'staff'}</small>}<footer><small><CalendarDays size={14} /> {dateText(item.due_date)}</small><div>{manager && item.status === 'submitted' && <button className="button quiet small" onClick={() => approve(item)}><CheckCircle2 size={15} /> Approve</button>}{item.status !== 'completed' && <button className="icon-button" onClick={() => { setEditing(item); setOpen(true) }} aria-label={`${!manager && item.status === 'submitted' ? 'View' : 'Edit'} ${item.title}`}>{!manager && item.status === 'submitted' ? <Eye size={15} /> : <Pencil size={15} />}</button>}{manager && <button className="icon-button danger" onClick={() => remove(item)} aria-label={`Delete ${item.title}`}><Trash2 size={15} /></button>}</div></footer></article>)}{!data.roadmapMissions.length && <Empty text="No missions have been assigned yet." />}</div>}
    {tab === 'timeline' && <Panel title="Application timeline"><div className="timeline-list">{timeline.map((item) => <div key={item.id}><span className="timeline-dot" /><time>{dateText(item.date)}</time><div><b>{item.title}</b><small>{item.kind}</small></div><Badge>{item.status}</Badge></div>)}{!timeline.length && <Empty />}</div></Panel>}
    {tab === 'reflections' && <div className="reflection-grid">{data.roadmapMissions.map((item) => <article key={item.id}><Sparkles size={20} /><div><span>{item.category || 'Mission'}</span><h3>{item.title}</h3><p>{item.reflection || 'No reflection has been written for this mission yet.'}</p></div>{!manager && item.status !== 'completed' && <button className="button quiet small" onClick={() => { setEditing(item); setOpen(true) }}>{item.status === 'submitted' ? 'View submission' : 'Write reflection'}</button>}</article>)}{!data.roadmapMissions.length && <Empty />}</div>}
    {open && <MissionForm mission={editing} user={user} data={data} onClose={() => setOpen(false)} onSaved={() => { setOpen(false); reload() }} notify={notify} />}
    {setupOpen && <LevelOneSetupModal data={data} onClose={() => setSetupOpen(false)} onSaved={() => { setSetupOpen(false); reload() }} notify={notify} />}
  </div>
}

function CommunityPostForm({ onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false)
  async function submit(event) { event.preventDefault(); setSaving(true); const values = new FormData(event.currentTarget); try { await api.create('community-posts', { title: values.get('title'), body: values.get('body'), post_type: values.get('post_type') }); notify('Post published.'); onSaved() } catch (err) { notify(err.message, 'error') } finally { setSaving(false) } }
  return <Modal title="Create a community post" onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label="Type"><select name="post_type">{['discussion', 'question', 'update'].map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></Field><Field label="Title"><input name="title" required /></Field><Field label="Post"><textarea name="body" required /></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? 'Publishing…' : 'Publish'}</button></div></form></Modal>
}

function CommunityPage({ data, reload, notify }) {
  const [filter, setFilter] = useState('all')
  const [open, setOpen] = useState(false)
  const [communityPosts, setCommunityPosts] = useState(data.communityPosts)
  const [likingIds, setLikingIds] = useState([])
  useEffect(() => setCommunityPosts(data.communityPosts), [data.communityPosts])
  const posts = communityPosts.filter((item) => filter === 'all' || item.post_type === filter)
  async function like(item) {
    if (likingIds.includes(item.id)) return
    const optimistic = { ...item, liked_by_me: !item.liked_by_me, likes_count: Math.max(0, item.likes_count + (item.liked_by_me ? -1 : 1)) }
    setLikingIds((ids) => [...ids, item.id])
    setCommunityPosts((items) => items.map((post) => post.id === item.id ? optimistic : post))
    try {
      const saved = await api.likeCommunityPost(item.id)
      setCommunityPosts((items) => items.map((post) => post.id === item.id ? saved : post))
    } catch (err) {
      setCommunityPosts((items) => items.map((post) => post.id === item.id ? item : post))
      notify(err.message, 'error')
    } finally {
      setLikingIds((ids) => ids.filter((id) => id !== item.id))
    }
  }
  return <div className="section-stack student-portal"><section className="portal-hero community-hero"><div><span className="eyebrow">NASEEB COMMUNITY</span><h2>Learn together. Grow together.</h2><p>Ask questions, share useful resources, and learn from the application experience of other students.</p></div><button className="button light" onClick={() => setOpen(true)}><Plus size={17} /> Create a post</button></section><div className="community-layout"><div><PortalTabs active={filter} onChange={setFilter} items={[["all", "All posts"], ["discussion", "Discussion"], ["question", "Q&A"], ["update", "Updates"]]} /><div className="community-feed">{posts.map((post) => { const liking = likingIds.includes(post.id); return <article className="community-card" key={post.id}><header><span className="avatar">{post.author_initials}</span><div><b>{post.author_name || 'Student'}</b><small>{dateTimeText(post.created_at)} • {label(post.post_type)}</small></div></header><h3>{post.title}</h3><p>{post.body}</p><footer><button className={post.liked_by_me ? 'liked' : ''} onClick={() => like(post)} disabled={liking} aria-pressed={post.liked_by_me} aria-label={`${post.liked_by_me ? 'Unlike' : 'Like'} ${post.title}`} title={post.liked_by_me ? 'Remove your like' : 'Like this post'}><Heart size={17} fill={post.liked_by_me ? 'currentColor' : 'none'} /><span>{post.liked_by_me ? 'Liked' : 'Like'}</span><b>{post.likes_count}</b></button></footer></article> })}{!posts.length && <Empty text="No posts in this section yet." />}</div></div><aside><Panel title="How likes work"><p className="community-like-help"><Heart size={16} /> Tap Like to support a useful post. Tap it again to remove your like. Each student counts once.</p></Panel><Panel title="Community guidelines"><ul className="guide-list"><li>Keep every conversation useful and respectful.</li><li>Do not share passwords or confidential documents.</li><li>Check your sources and ask clear questions.</li></ul></Panel></aside></div>{open && <CommunityPostForm onClose={() => setOpen(false)} onSaved={() => { setOpen(false); reload() }} notify={notify} />}</div>
}

function BookingForm({ onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false)
  async function submit(event) { event.preventDefault(); setSaving(true); const values = new FormData(event.currentTarget); try { await api.create('bookings', { topic: values.get('topic'), starts_at: new Date(values.get('starts_at')).toISOString(), duration_minutes: Number(values.get('duration_minutes')), notes: values.get('notes'), status: 'requested' }); notify('Session request sent.'); onSaved() } catch (err) { notify(err.message, 'error') } finally { setSaving(false) } }
  return <Modal title="Request a counseling session" onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label="Topic"><input name="topic" required placeholder="Essay review, university list..." /></Field><Field label="Date & time"><input name="starts_at" type="datetime-local" required /></Field><Field label="Duration"><select name="duration_minutes" defaultValue="45"><option value="30">30 min</option><option value="45">45 min</option><option value="60">60 min</option></select></Field><Field label="Notes"><textarea name="notes" /></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? 'Requesting…' : 'Request session'}</button></div></form></Modal>
}

function BookingsPage({ data, reload, notify }) {
  const [tab, setTab] = useState('upcoming'); const [open, setOpen] = useState(false); const now = new Date()
  const items = data.bookings.filter((item) => tab === 'upcoming' ? new Date(item.starts_at) >= now && item.status !== 'cancelled' : new Date(item.starts_at) < now || item.status === 'cancelled')
  async function cancel(item) { try { await api.update('bookings', item.id, { status: 'cancelled' }); notify('Booking cancelled.'); reload() } catch (err) { notify(err.message, 'error') } }
  return <div className="section-stack student-portal"><div className="portal-toolbar"><PortalTabs active={tab} onChange={setTab} items={[["upcoming", "Upcoming"], ["past", "Past & cancelled"]]} /><button className="button primary" onClick={() => setOpen(true)}><Plus size={17} /> Create a session</button></div><div className="booking-grid">{items.map((item) => <article className="booking-card" key={item.id}><div className="booking-date"><strong>{new Date(item.starts_at).getDate()}</strong><span>{new Intl.DateTimeFormat('en', { month: 'short' }).format(new Date(item.starts_at))}</span></div><div><h3>{item.topic}</h3><p><Clock3 size={15} /> {dateTimeText(item.starts_at)} • {item.duration_minutes} min</p><small>{item.counselor_name || 'Assigned counselor'}</small>{item.notes && <p>{item.notes}</p>}</div><div><Badge>{item.status}</Badge>{tab === 'upcoming' && <button className="button quiet small" onClick={() => cancel(item)}>Cancel</button>}</div></article>)}{!items.length && <Empty text={tab === 'upcoming' ? 'No upcoming sessions.' : 'No previous sessions.'} />}</div>{open && <BookingForm onClose={() => setOpen(false)} onSaved={() => { setOpen(false); reload() }} notify={notify} />}</div>
}

function MessageChannelForm({ kind, user, onClose, onSaved, notify }) {
  const [contacts, setContacts] = useState([])
  const [selectedMembers, setSelectedMembers] = useState([])
  const [memberSearch, setMemberSearch] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    let active = true
    api.messageContacts().then((items) => active && setContacts(items || [])).catch((err) => notify(err.message, 'error'))
    return () => { active = false }
  }, [])

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    const values = new FormData(event.currentTarget)
    try {
      const channel = kind === 'direct'
        ? await api.openDirectChannel(Number(values.get('contact')))
        : await api.create('message-channels', {
          kind,
          name: values.get('name')?.trim(),
          description: values.get('description')?.trim(),
          members: selectedMembers,
        })
      notify(kind === 'direct' ? 'Direct conversation opened.' : `${label(kind)} created.`)
      onSaved(channel)
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const staffInterface = ['counselor', 'organization'].includes(user.role)
  const normalizedSearch = memberSearch.trim().toLowerCase()
  const visibleContacts = contacts.filter((contact) => !normalizedSearch || `${fullName(contact)} ${contact.role} ${contact.school_name || ''}`.toLowerCase().includes(normalizedSearch))
  function chooseAudience(audience) {
    if (audience === 'clear') { setSelectedMembers([]); return }
    const matches = contacts.filter((contact) => audience === 'all' || (audience === 'students' ? contact.role === 'student' : contact.role !== 'student'))
    setSelectedMembers(matches.map((contact) => contact.id))
  }
  function toggleMember(contactId) {
    setSelectedMembers((current) => current.includes(contactId) ? current.filter((id) => id !== contactId) : [...current, contactId])
  }

  const title = kind === 'direct' ? 'Start a direct conversation' : kind === 'discussion' ? 'Start a discussion' : `Create a ${kind}`
  return <Modal title={title} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    {kind === 'direct'
      ? <Field label={user.role === 'counselor' ? 'Assigned student or school contact' : user.role === 'organization' ? 'Student, teacher or counselor' : 'Contact'}><select name="contact" required defaultValue=""><option value="" disabled>Select a person</option>{contacts.map((contact) => <option key={contact.id} value={contact.id}>{fullName(contact)} · {label(contact.role)}{contact.school_name ? ` · ${contact.school_name}` : ''}</option>)}</select></Field>
      : <><Field label={kind === 'discussion' ? 'Question or topic' : 'Channel name'}><input name="name" required maxLength="160" /></Field><Field label="Description"><textarea name="description" maxLength="2000" /></Field></>}
    {['group', 'community'].includes(kind) && <fieldset className="form-wide member-picker"><legend>Initial members · {selectedMembers.length} selected</legend><p>Add contacts now. People can also join a public Community later.</p>{staffInterface && <div className="audience-shortcuts"><button type="button" onClick={() => chooseAudience('students')}>{user.role === 'counselor' ? 'Assigned students' : 'School students'}</button><button type="button" onClick={() => chooseAudience('staff')}>School staff</button><button type="button" onClick={() => chooseAudience('all')}>All contacts</button><button type="button" onClick={() => chooseAudience('clear')}>Clear</button></div>}<label className="member-search"><Search size={15} /><input value={memberSearch} onChange={(event) => setMemberSearch(event.target.value)} placeholder="Search contacts" /></label><div>{visibleContacts.map((contact) => <CheckboxControl key={contact.id} name="members" value={contact.id} checked={selectedMembers.includes(contact.id)} onChange={() => toggleMember(contact.id)}>{fullName(contact)} · {label(contact.role)}{contact.school_name ? ` · ${contact.school_name}` : ''}</CheckboxControl>)}</div>{!visibleContacts.length && <small>No matching contacts.</small>}</fieldset>}
    {kind === 'discussion' && <div className="alert warning form-wide">Discussions are public. A user must join before posting.</div>}
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving || (kind === 'direct' && !contacts.length)} aria-busy={saving}>{saving ? 'Saving…' : 'Continue'}</button></div>
  </form></Modal>
}

function ChannelMembersModal({ channel, user, onClose, onChanged, notify }) {
  const [members, setMembers] = useState([])
  const [contacts, setContacts] = useState([])
  const [selectedUser, setSelectedUser] = useState('')
  const [selectedRole, setSelectedRole] = useState('member')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    try {
      const [memberItems, contactItems] = await Promise.all([api.channelMembers(channel.id), api.messageContacts()])
      setMembers(memberItems || [])
      setContacts(contactItems || [])
    } catch (err) { notify(err.message, 'error') }
  }, [channel.id, notify])

  useEffect(() => { load() }, [load])
  const memberIds = new Set(members.map((membership) => membership.user))
  const available = contacts.filter((contact) => !memberIds.has(contact.id))

  async function addMember(event) {
    event.preventDefault()
    if (!selectedUser) return
    setSaving(true)
    try {
      await api.addChannelMember(channel.id, Number(selectedUser), selectedRole)
      setSelectedUser('')
      await load()
      await onChanged()
      notify('Channel member added.')
    } catch (err) { notify(err.message, 'error') } finally { setSaving(false) }
  }

  async function changeRole(membership, role) {
    setSaving(true)
    try {
      await api.addChannelMember(channel.id, membership.user, role)
      await load()
      notify(`Member role changed to ${role}.`)
    } catch (err) { notify(err.message, 'error') } finally { setSaving(false) }
  }

  async function removeMember(membership) {
    setSaving(true)
    try {
      await api.removeChannelMember(channel.id, membership.user)
      await load()
      await onChanged()
      notify('Channel member removed.')
    } catch (err) { notify(err.message, 'error') } finally { setSaving(false) }
  }

  return <Modal title={`Manage ${channel.display_name}`} onClose={onClose}><div className="member-manager"><form onSubmit={addMember}><Field label="Add a contact"><select value={selectedUser} onChange={(event) => setSelectedUser(event.target.value)} required><option value="">Select a contact</option>{available.map((contact) => <option key={contact.id} value={contact.id}>{fullName(contact)} · {label(contact.role)}</option>)}</select></Field><Field label="Channel role"><select value={selectedRole} onChange={(event) => setSelectedRole(event.target.value)}><option value="member">Member</option><option value="moderator">Moderator</option></select></Field><button className="button primary" disabled={saving || !selectedUser}><Plus size={16} /> Add</button></form><div className="member-manager-list">{members.map((membership) => <article key={membership.id}><span className="avatar">{initials(fullName(membership.user_detail))}</span><div><b>{fullName(membership.user_detail)}</b><small>{label(membership.user_detail?.role)}{membership.user_detail?.school_name ? ` · ${membership.user_detail.school_name}` : ''}</small></div><Badge>{membership.role}</Badge>{membership.role !== 'owner' && membership.user !== user.id && <div>{membership.role === 'member' ? <button type="button" className="button quiet small" disabled={saving} onClick={() => changeRole(membership, 'moderator')}>Make moderator</button> : <button type="button" className="button quiet small" disabled={saving} onClick={() => changeRole(membership, 'member')}>Make member</button>}<button type="button" className="icon-button danger" disabled={saving} onClick={() => removeMember(membership)} aria-label={`Remove ${fullName(membership.user_detail)}`}><Trash2 size={15} /></button></div>}</article>)}</div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>Done</button></div></div></Modal>
}

function ReportMessageModal({ message, onClose, onReported, notify }) {
  const [reason, setReason] = useState('spam')
  const [details, setDetails] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    try {
      await api.reportChannelMessage(message.id, { reason, details: details.trim() })
      notify('Report submitted. Moderators will review it confidentially.')
      onReported()
    } catch (err) { notify(err.message, 'error') } finally { setSaving(false) }
  }

  return <Modal title="Report this message" onClose={onClose}><form className="form-grid report-message-form" onSubmit={submit}><div className="report-privacy-note form-wide"><ShieldCheck size={19} /><div><b>Your report is confidential</b><p>Only trusted school moderators can see who submitted the report. Other users and the message author cannot see your identity.</p></div></div><Field label="Reason"><select value={reason} onChange={(event) => setReason(event.target.value)}><option value="spam">Spam</option><option value="harassment">Harassment or bullying</option><option value="unsafe">Unsafe content</option><option value="privacy">Privacy concern</option><option value="misinformation">Misinformation</option><option value="other">Other</option></select></Field><Field label="Additional details (optional)"><textarea value={details} onChange={(event) => setDetails(event.target.value)} maxLength="2000" rows="4" placeholder="Briefly explain the issue to the moderator." /></Field><div className="reported-message-preview form-wide"><small>Reported message</small><p>{message.body}</p></div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving} aria-busy={saving}><Flag size={16} /> {saving ? 'Sending…' : 'Submit report'}</button></div></form></Modal>
}

function ModerationQueueModal({ onClose, onChanged, notify }) {
  const [statusFilter, setStatusFilter] = useState('pending')
  const [reports, setReports] = useState([])
  const [notes, setNotes] = useState({})
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState(null)

  const load = useCallback(async (statusValue = statusFilter) => {
    setLoading(true)
    try { setReports(await api.messageReports(statusValue) || []) }
    catch (err) { notify(err.message, 'error') }
    finally { setLoading(false) }
  }, [statusFilter, notify])

  useEffect(() => { load(statusFilter) }, [statusFilter])

  async function moderate(report, mode, action = 'none') {
    setSavingId(report.id)
    try {
      if (mode === 'review') await api.reviewMessageReport(report.id)
      else if (mode === 'dismiss') await api.dismissMessageReport(report.id, { moderator_note: notes[report.id] || '' })
      else await api.resolveMessageReport(report.id, { action, moderator_note: notes[report.id] || '' })
      notify(mode === 'review' ? 'Report reviewga olindi.' : mode === 'dismiss' ? 'Report dismissed.' : 'Moderation action applied.')
      await load(statusFilter)
      await onChanged()
    } catch (err) { notify(err.message, 'error') } finally { setSavingId(null) }
  }

  const openStatuses = ['pending', 'reviewing']
  return <Modal title="Anonymous moderation queue" onClose={onClose}><div className="moderation-queue"><PortalTabs active={statusFilter} onChange={setStatusFilter} items={[["pending", "Pending"], ["reviewing", "Reviewing"], ["resolved", "Resolved"], ["dismissed", "Dismissed"]]} /><div className="moderation-list">{loading && <div className="channel-status">Loading reports…</div>}{!loading && reports.map((report) => <article className="moderation-card" key={report.id}><header><div><Badge>{report.reason}</Badge>{report.message_is_anonymous && <span className="anonymous-report-badge"><ShieldAlert size={13} /> Anonymous post</span>}</div><time>{dateTimeText(report.created_at)}</time></header><blockquote>{report.message_body}</blockquote><div className="moderation-identities"><span>Author <b>{report.sender_name}</b></span><span>Reporter <b>{report.reporter_name}</b></span><span>Channel <b>{report.channel_name}</b></span></div>{report.details && <p className="report-details"><b>Report details:</b> {report.details}</p>}{openStatuses.includes(report.status) ? <><Field label="Moderator note"><textarea value={notes[report.id] || ''} onChange={(event) => setNotes((current) => ({ ...current, [report.id]: event.target.value }))} maxLength="2000" rows="2" /></Field><footer>{report.status === 'pending' && <button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'review')}>Start review</button>}<button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'dismiss')}>Dismiss</button><button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'resolve', 'none')}>Resolve only</button><button className="button danger small" disabled={savingId === report.id} onClick={() => moderate(report, 'resolve', 'content_removed')}>Remove content</button><button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'resolve', 'muted_24h')}>Mute 24h</button><button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'resolve', 'muted_7d')}>Mute 7d</button></footer></> : <div className="moderation-result"><Badge>{report.status}</Badge><span>{label(report.action)}{report.reviewed_by_name ? ` · ${report.reviewed_by_name}` : ''}</span>{report.moderator_note && <p>{report.moderator_note}</p>}</div>}</article>)}{!loading && !reports.length && <Empty text="No reports with this status." />}</div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>Done</button></div></div></Modal>
}

function MessagesPage({ user, data, notify }) {
  const [tab, setTab] = useState('direct')
  const [channels, setChannels] = useState(data.messageChannels || [])
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState([])
  const [body, setBody] = useState('')
  const [anonymous, setAnonymous] = useState(false)
  const [replyTo, setReplyTo] = useState(null)
  const [search, setSearch] = useState('')
  const [loadingChannels, setLoadingChannels] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [saving, setSaving] = useState(false)
  const [open, setOpen] = useState(false)
  const [membersOpen, setMembersOpen] = useState(false)
  const [reportingMessage, setReportingMessage] = useState(null)
  const [moderationOpen, setModerationOpen] = useState(false)
  const [overview, setOverview] = useState(null)

  const visibleChannels = channels.filter((channel) => channel.kind === tab)
  const activeChannel = visibleChannels.find((channel) => channel.id === activeId) || visibleChannels[0] || null
  const staffInterface = ['counselor', 'organization'].includes(user.role)
  const moderationEnabled = isTaskManager(user) || user.role === 'organization'
  const canCreate = tab === 'direct' || tab === 'discussion' || isTaskManager(user) || user.role === 'organization'
  const canAccept = activeChannel?.kind === 'discussion' && (isTaskManager(user) || ['owner', 'moderator'].includes(activeChannel?.my_role))
  const canManageMembers = activeChannel?.kind !== 'direct' && activeChannel?.is_member && (isTaskManager(user) || user.role === 'organization' || ['owner', 'moderator'].includes(activeChannel?.my_role))

  const refreshOverview = useCallback(async () => {
    if (!moderationEnabled && !staffInterface) return null
    try {
      const nextOverview = await api.messagingOverview()
      setOverview(nextOverview)
      return nextOverview
    } catch (err) {
      notify(err.message, 'error')
      return null
    }
  }, [moderationEnabled, staffInterface, notify])

  const refreshChannels = useCallback(async (kind = tab, term = search, preferredId = activeId) => {
    setLoadingChannels(true)
    try {
      const items = await api.messageChannels(kind, term)
      setChannels(items || [])
      setActiveId((current) => {
        if (items.some((item) => item.id === preferredId)) return preferredId
        if (items.some((item) => item.id === current)) return current
        return items[0]?.id || null
      })
      return items || []
    } catch (err) {
      notify(err.message, 'error')
      return []
    } finally {
      setLoadingChannels(false)
    }
  }, [tab, search, activeId, notify])

  const loadMessages = useCallback(async (channel) => {
    if (!channel?.is_member) { setMessages([]); return }
    setLoadingMessages(true)
    try {
      const items = await api.channelMessages(channel.id)
      setMessages([...(items || [])].reverse())
      await api.markChannelRead(channel.id)
      setChannels((current) => current.map((item) => item.id === channel.id ? { ...item, unread_count: 0 } : item))
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setLoadingMessages(false)
    }
  }, [notify])

  useEffect(() => {
    const timer = window.setTimeout(() => refreshChannels(tab, search, null), 220)
    return () => window.clearTimeout(timer)
  }, [tab, search])

  useEffect(() => { refreshOverview() }, [refreshOverview])

  useEffect(() => {
    setReplyTo(null)
    setAnonymous(false)
    loadMessages(activeChannel)
  }, [activeChannel?.id, activeChannel?.is_member])

  async function send(event) {
    event.preventDefault()
    if (!activeChannel || !body.trim()) return
    setSaving(true)
    try {
      await api.create('channel-messages', {
        channel: activeChannel.id,
        body: body.trim(),
        is_anonymous: anonymous,
        ...(replyTo ? { parent: replyTo.id } : {}),
      })
      setBody('')
      setReplyTo(null)
      await loadMessages(activeChannel)
      await refreshChannels(tab, search, activeChannel.id)
      await refreshOverview()
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function join() {
    try {
      await api.joinChannel(activeChannel.id)
      const items = await refreshChannels(tab, search, activeChannel.id)
      const joined = items.find((item) => item.id === activeChannel.id)
      if (joined) await loadMessages(joined)
      await refreshOverview()
      notify('You joined the channel.')
    } catch (err) { notify(err.message, 'error') }
  }

  async function leave() {
    try {
      await api.leaveChannel(activeChannel.id)
      setMessages([])
      await refreshChannels(tab, search, null)
      await refreshOverview()
      notify('You left the channel.')
    } catch (err) { notify(err.message, 'error') }
  }

  async function accept(message) {
    try {
      const accepted = await api.acceptChannelMessage(message.id)
      setMessages((current) => current.map((item) => ({ ...item, is_accepted_answer: item.id === accepted.id })))
      notify('Reply marked as the accepted answer.')
    } catch (err) { notify(err.message, 'error') }
  }

  async function channelSaved(channel) {
    setOpen(false)
    setTab(channel.kind)
    setSearch('')
    const items = await refreshChannels(channel.kind, '', channel.id)
    if (!items.some((item) => item.id === channel.id)) setChannels((current) => [channel, ...current])
    setActiveId(channel.id)
    await refreshOverview()
  }

  return <div className="messaging-page section-stack">
    {staffInterface && <section className="staff-messaging-overview"><div className="staff-messaging-copy"><span><MessageCircle size={22} /></span><div><small>{user.role === 'counselor' ? 'COUNSELOR INBOX' : 'SCHOOL COMMUNICATIONS'}</small><h2>{user.role === 'counselor' ? 'Student and school conversations' : 'Keep your school connected'}</h2><p>{user.role === 'counselor' ? 'Message assigned students, coordinate with school staff and moderate shared channels.' : 'Contact your students, teachers and assigned counselors from one secure inbox.'}</p></div></div><div className="staff-messaging-stats"><div><strong>{overview?.unread_total || 0}</strong><span>Unread</span></div><div><strong>{overview?.students_total || 0}</strong><span>{user.role === 'counselor' ? 'Assigned students' : 'School students'}</span></div><div><strong>{overview?.channel_counts?.direct || 0}</strong><span>Direct chats</span></div><div><strong>{(overview?.channel_counts?.group || 0) + (overview?.channel_counts?.community || 0)}</strong><span>Managed spaces</span></div><div className={overview?.pending_reports ? 'attention' : ''}><strong>{overview?.pending_reports || 0}</strong><span>Open reports</span></div></div><div className="staff-messaging-actions"><button className="button primary" onClick={() => { setTab('direct'); setActiveId(null); setOpen(true) }}><MessageCircle size={16} /> Message a student</button><button className="button quiet" onClick={() => { setTab('group'); setActiveId(null); setOpen(true) }}><UsersRound size={16} /> Create group</button><button className="button quiet" onClick={() => setModerationOpen(true)}><ShieldAlert size={16} /> Moderation queue{overview?.pending_reports ? ` · ${overview.pending_reports}` : ''}</button></div></section>}
    <div className="portal-toolbar messaging-toolbar"><PortalTabs active={tab} onChange={(next) => { setTab(next); setActiveId(null) }} items={[["direct", "Direct"], ["group", "Group"], ["community", "Community"], ["discussion", "Discussions"]]} /><div className="messaging-toolbar-actions">{moderationEnabled && !staffInterface && <button className="button quiet" onClick={() => setModerationOpen(true)}><ShieldAlert size={17} /> Moderation{overview?.pending_reports ? ` · ${overview.pending_reports}` : ''}</button>}{canCreate && <button className="button primary" onClick={() => setOpen(true)}><Plus size={17} /> {tab === 'direct' ? 'New message' : tab === 'discussion' ? 'New discussion' : 'New channel'}</button>}</div></div>
    <div className="messages-shell">
      <aside className="channel-sidebar"><label className="channel-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${tab}`} aria-label={`Search ${tab} channels`} /></label><div className="channel-list">{visibleChannels.map((channel) => <button type="button" key={channel.id} className={`channel-item ${activeChannel?.id === channel.id ? 'active' : ''}`} onClick={() => setActiveId(channel.id)}><span className="avatar">{initials(channel.display_name)}</span><span><b>{channel.display_name}</b><small>{channel.last_message?.body || channel.description || `${channel.members_count} members`}</small></span>{channel.unread_count > 0 && <strong aria-label={`${channel.unread_count} unread`}>{channel.unread_count > 99 ? '99+' : channel.unread_count}</strong>}</button>)}{loadingChannels && <div className="channel-status">Loading channels…</div>}{!loadingChannels && !visibleChannels.length && <Empty text="No channels found in this section." />}</div></aside>
      {activeChannel ? <section className="message-thread"><header><div><b>{activeChannel.display_name}</b><small>{label(activeChannel.kind)}{activeChannel.school_name ? ` · ${activeChannel.school_name}` : ''} · {activeChannel.members_count} members</small></div><div className="channel-actions">{canManageMembers && <button className="button quiet small" onClick={() => setMembersOpen(true)}><UsersRound size={15} /> Manage members</button>}{activeChannel.is_public && !activeChannel.is_member && <button className="button primary small" onClick={join}>Join</button>}{activeChannel.is_member && activeChannel.kind !== 'direct' && activeChannel.my_role !== 'owner' && <button className="button quiet small" onClick={leave}>Leave</button>}<Badge>{activeChannel.kind}</Badge></div></header>
        {activeChannel.is_member ? <><div className="message-list">{loadingMessages && <div className="channel-status">Loading messages…</div>}{messages.map((message) => { const mine = message.sender_id === user.id; return <article key={message.id} className={`message-bubble ${mine ? 'mine' : ''} ${message.parent ? 'reply' : ''} ${message.is_accepted_answer ? 'accepted' : ''}`}>{message.parent_preview && <button type="button" className="parent-preview" onClick={() => document.getElementById(`message-${message.parent}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}>Reply to: {message.parent_preview.body}</button>}<div id={`message-${message.id}`}><b>{message.sender_name}{message.is_anonymous ? ' · Anonymous' : ''}</b>{message.is_accepted_answer && <span className="accepted-label"><CheckCircle2 size={13} /> Accepted answer</span>}</div><p>{message.deleted_at ? 'Message deleted' : message.body}</p><footer><time>{dateTimeText(message.created_at)}{message.is_edited ? ' · edited' : ''}</time>{!message.deleted_at && <button type="button" onClick={() => setReplyTo(message)}>Reply</button>}{!mine && !message.deleted_at && <button type="button" disabled={message.is_reported_by_me} onClick={() => setReportingMessage(message)}><Flag size={11} /> {message.is_reported_by_me ? 'Reported' : 'Report'}</button>}{canAccept && message.parent && !message.deleted_at && !message.is_accepted_answer && <button type="button" onClick={() => accept(message)}>Accept answer</button>}</footer></article> })}{!loadingMessages && !messages.length && <Empty text="Start the conversation with the first message." />}</div><form className="message-compose" onSubmit={send}><div>{replyTo && <div className="replying-to"><span>Replying to <b>{replyTo.sender_name}</b></span><button type="button" className="icon-button" onClick={() => setReplyTo(null)} aria-label="Cancel reply"><X size={15} /></button></div>}<textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder="Write a message…" rows="2" />{['community', 'discussion'].includes(activeChannel.kind) && <CheckboxControl className="compact anonymous-toggle" checked={anonymous} onChange={(event) => setAnonymous(event.target.checked)}>Post anonymously</CheckboxControl>}</div><button className="button primary" disabled={saving || !body.trim()} aria-busy={saving}><Send size={17} /> {saving ? 'Sending…' : 'Send'}</button></form></> : <div className="message-join-state"><UsersRound size={42} /><h3>{activeChannel.display_name}</h3><p>{activeChannel.description || 'Join this channel to read and send messages.'}</p><button className="button primary" onClick={join}>Join channel</button></div>}
      </section> : <section className="message-empty-state"><MessageCircle size={44} /><h3>Select a conversation</h3><p>Select a channel or start a new conversation.</p></section>}
    </div>
    {open && <MessageChannelForm kind={tab} user={user} onClose={() => setOpen(false)} onSaved={channelSaved} notify={notify} />}
    {membersOpen && activeChannel && <ChannelMembersModal channel={activeChannel} user={user} onClose={() => setMembersOpen(false)} onChanged={async () => { await refreshChannels(tab, search, activeChannel.id); await refreshOverview() }} notify={notify} />}
    {reportingMessage && <ReportMessageModal message={reportingMessage} onClose={() => setReportingMessage(null)} onReported={async () => { setMessages((current) => current.map((item) => item.id === reportingMessage.id ? { ...item, is_reported_by_me: true } : item)); setReportingMessage(null); await refreshOverview() }} notify={notify} />}
    {moderationOpen && moderationEnabled && <ModerationQueueModal onClose={() => setModerationOpen(false)} onChanged={refreshOverview} notify={notify} />}
  </div>
}

function ProgramUsagePage({ data }) {
  return <div className="section-stack student-portal"><section className="portal-hero usage-hero"><div><span className="eyebrow">YOUR NASEEB PROGRAM</span><h2>Program usage</h2><p>Active services, mentors, and remaining hours.</p></div><ListChecks size={58} /></section><div className="service-list">{data.programServices.map((service) => { const total = Number(service.total_hours || 0); const used = Number(service.used_hours || 0); const percent = service.unlimited || !total ? 100 : Math.min(100, (used / total) * 100); return <article key={service.id}><header><div><h3>{service.name}</h3><p>{service.category || 'Education support'}</p></div><Badge>{service.status}</Badge></header><div className="service-bar"><span style={{ width: `${percent}%` }} /></div><div className="service-meta"><span>{service.unlimited ? 'Unlimited access' : `${service.remaining_hours}h available`}</span><span>{service.mentor_name || 'Mentor pending'}</span></div></article>})}{!data.programServices.length && <Empty text="No active program services found." />}</div></div>
}

function ResourceIndexPage({ data, query, setPage }) {
  const filtered = data.resourceLibrary.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()))
  const groups = Object.groupBy ? Object.groupBy(filtered, (item) => item.category) : filtered.reduce((acc, item) => ({ ...acc, [item.category]: [...(acc[item.category] || []), item] }), {})
  function open(item) { if (item.destination && PAGE_META[item.destination]) setPage(item.destination); else if (item.external_url) window.open(item.external_url, '_blank', 'noopener,noreferrer') }
  return <div className="section-stack student-portal"><label className="resource-search"><Search size={20} /><input value={query} readOnly placeholder="Use the search field in the top header" /><span>{filtered.length} resources</span></label>{Object.entries(groups).map(([category, items], index) => <section className="resource-group" key={category} style={{ '--group-index': index }}><header><span><LibraryBig size={20} /></span><div><h2>{category}</h2><p>{items.length} student resources</p></div></header><div>{items.map((item) => <button key={item.id} onClick={() => open(item)}><span>{String(item.sort_order + 1).padStart(2, '0')}</span><div><b>{item.title}</b><small>{item.description}</small></div><ChevronRight size={18} /></button>)}</div></section>)}{!filtered.length && <Empty text="No resources found." />}</div>
}

function EssayLabPage({ user, data, query, reload, notify }) {
  const approved = data.essays.filter((item) => item.status === 'approved').length
  const active = data.essays.filter((item) => item.status !== 'approved').length
  return <div className="section-stack student-portal"><section className="portal-hero essay-hero"><div><span className="eyebrow">NASEEB ESSAY LAB</span><h2>Ideas into impact.</h2><p>Manage drafts, revisions, and counselor feedback in one place.</p></div><div className="essay-progress"><div><strong>{data.essays.length}</strong><span>Total</span></div><div><strong>{active}</strong><span>Active</span></div><div><strong>{approved}</strong><span>Approved</span></div></div></section><ResourceSection title="Active essays & supplements" resource="essays" {...{ user, data, query, reload, notify }} /></div>
}

function ApplicationsPortalPage({ user, data, query, reload, notify, setPage }) {
  const submitted = data.applications.filter((item) => ['submitted', 'accepted'].includes(item.status)).length
  return <div className="section-stack student-portal"><section className="portal-hero application-hero"><div><span className="eyebrow">APPLICATION TRACKER</span><h2>Manage every application.</h2><p>Track your university list, statuses, deadlines, and scholarship information.</p></div><button className="button light" onClick={() => setPage('college_search')}><Search size={17} /> Add a university</button></section><div className="stat-grid"><Stat label="Universities" value={data.applications.length} /><Stat label="Submitted" value={submitted} /><Stat label="In progress" value={data.applications.filter((item) => ['shortlisted', 'applying'].includes(item.status)).length} /><Stat label="Decisions" value={data.applications.filter((item) => ['accepted', 'rejected', 'waitlisted'].includes(item.status)).length} /></div><ResourceSection title="My university list" resource="applications" {...{ user, data, query, reload, notify }} /></div>
}

const money = (value) => value === null || value === undefined ? '—' : `$${Number(value).toLocaleString('en-US')}`

function universityFit(university, student) {
  if (!student) return { score: 0, label: 'Profile needed' }
  let score = 20
  const targets = String(student.target_countries || '').toLowerCase()
  if (targets.includes(String(university.country || '').toLowerCase())) score += 25
  if (!university.sat_min || Number(student.sat_score || 0) >= Number(university.sat_min)) score += 25
  if (!university.net_price_usd || !student.budget_usd || Number(university.net_price_usd) <= Number(student.budget_usd)) score += 15
  if (!student.scholarship_needed || university.offers_international_aid || university.offers_merit_aid) score += 15
  const bounded = Math.min(score, 100)
  return { score: bounded, label: bounded >= 80 ? 'Strong fit' : bounded >= 60 ? 'Good fit' : 'Explore' }
}

function scholarshipRequirements(item) {
  return [
    item.requires_transcript && 'Transcript', item.requires_essay && 'Essay',
    item.requires_recommendation && 'Recommendation', item.requires_financial_documents && 'Financial documents',
    item.requires_cv && 'CV', item.requires_portfolio && 'Portfolio',
  ].filter(Boolean)
}

function eligibleScholarship(item, student) {
  if (!student) return false
  if (item.min_gpa && Number(student.gpa || 0) < Number(item.min_gpa)) return false
  if (item.min_ielts && Number(student.ielts_score || 0) < Number(item.min_ielts)) return false
  if (item.min_sat && Number(student.sat_score || 0) < Number(item.min_sat)) return false
  return !item.eligible_grades || String(item.eligible_grades).split(',').map((value) => value.trim()).includes(String(student.grade))
}

function CollegeSearchPage({ data, query, reload, notify }) {
  const [tab, setTab] = useState('universities')
  const [country, setCountry] = useState('all')
  const [institutionType, setInstitutionType] = useState('all')
  const [maxPrice, setMaxPrice] = useState('all')
  const [minimumAcceptance, setMinimumAcceptance] = useState('0')
  const [aid, setAid] = useState('all')
  const [testOptional, setTestOptional] = useState(false)
  const [scoreMatch, setScoreMatch] = useState(false)
  const [scholarshipType, setScholarshipType] = useState('all')
  const [funding, setFunding] = useState('all')
  const [scope, setScope] = useState('all')
  const [eligibleOnly, setEligibleOnly] = useState(false)
  const [research, setResearch] = useState(null)
  const [researchLoading, setResearchLoading] = useState(true)
  const [researchSaving, setResearchSaving] = useState(false)
  const [researchError, setResearchError] = useState('')
  const student = ownStudent(data)
  const researchMap = new Map((research?.recommendations || []).map((item) => [item.university.id, item]))
  const countries = [...new Set(data.universities.map((item) => item.country))].sort()
  const added = new Set(data.applications.map((item) => item.university))

  useEffect(() => {
    let active = true
    setResearchLoading(true)
    api.collegeResearch().then((result) => { if (active) { setResearch(result); setResearchError('') } }).catch((error) => { if (active) setResearchError(error.message) }).finally(() => { if (active) setResearchLoading(false) })
    return () => { active = false }
  }, [])

  async function refreshResearch() {
    setResearchLoading(true); setResearchError('')
    try { setResearch(await api.collegeResearch()) } catch (error) { setResearchError(error.message) } finally { setResearchLoading(false) }
  }

  async function completeResearchProfile(payload) {
    setResearchSaving(true); setResearchError('')
    try {
      const result = await api.updateCollegeResearchProfile(payload)
      setResearch(result)
      notify('Profile details saved and college research updated.')
      reload()
    } catch (error) { setResearchError(error.message) } finally { setResearchSaving(false) }
  }
  const items = data.universities.filter((item) => {
    const aidMatch = aid === 'all' || (aid === 'need' && item.offers_need_based_aid) || (aid === 'merit' && item.offers_merit_aid) || (aid === 'international' && item.offers_international_aid) || (aid === 'full_need' && item.meets_full_need)
    return (country === 'all' || item.country === country)
      && (institutionType === 'all' || item.institution_type === institutionType)
      && (maxPrice === 'all' || Number(item.net_price_usd || Infinity) <= Number(maxPrice))
      && Number(item.acceptance_rate || 0) >= Number(minimumAcceptance)
      && (!testOptional || item.test_optional)
      && (!scoreMatch || !item.sat_min || Number(student?.sat_score || 0) >= Number(item.sat_min))
      && aidMatch && JSON.stringify(item).toLowerCase().includes(query.toLowerCase())
  }).sort((a, b) => (researchMap.get(b.id)?.match_score ?? universityFit(b, student).score) - (researchMap.get(a.id)?.match_score ?? universityFit(a, student).score))
  const scholarships = data.scholarships.filter((item) => (scholarshipType === 'all' || item.scholarship_type === scholarshipType)
    && (funding === 'all' || item.funding_level === funding) && (scope === 'all' || item.scope === scope)
    && (!eligibleOnly || eligibleScholarship(item, student)) && JSON.stringify(item).toLowerCase().includes(query.toLowerCase()))
  async function shortlist(university) { try { await api.create('applications', { student: student?.id, university: university.id, program: student?.target_major || 'Undeclared', tier: 'target', status: 'shortlisted', deadline: university.application_deadline, scholarship_deadline: university.scholarship_deadline }); notify(`${university.name} added to your shortlist.`); reload() } catch (err) { notify(err.message, 'error') } }
  return <div className="section-stack student-portal">
    <section className="college-banner"><div><span className="eyebrow">NASEEB COLLEGE & AID FINDER</span><h2>Universities, scholarships & aid</h2><p>Filter profile-matched options by price, acceptance, testing, and financial aid.</p></div><School size={80} /></section>
    <div className="finder-tabs"><PortalTabs active={tab} onChange={setTab} items={[["universities", "Universities"], ["scholarships", "Scholarships & Aid"], ["aid", "What you need"]]} /></div>
    {tab === 'universities' && researchLoading && <div className="college-research-state"><RefreshCw className="spin" size={22} /><div><b>Analyzing your profile</b><p>Checking SAT, GPA, IELTS, major, budget, and portfolio evidence.</p></div></div>}
    {tab === 'universities' && researchError && <div className="college-research-state error"><X size={22} /><div><b>Research yuklanmadi</b><p>{researchError}</p></div><button className="button quiet small" onClick={refreshResearch}>Retry</button></div>}
    {tab === 'universities' && !researchLoading && research && !research.ready && <CollegeProfileQuestions research={research} saving={researchSaving} onComplete={completeResearchProfile} />}
    {tab === 'universities' && !researchLoading && research?.ready && <><CollegeResearchOverview research={research} onRefresh={refreshResearch} /><div className="finder-layout">
      <aside className="filter-panel"><header><Filter size={18} /><b>University filters</b></header><label>Country<select value={country} onChange={(event) => setCountry(event.target.value)}><option value="all">All countries</option>{countries.map((item) => <option key={item}>{item}</option>)}</select></label><label>Institution type<select value={institutionType} onChange={(event) => setInstitutionType(event.target.value)}><option value="all">Public & private</option><option value="public">Public</option><option value="private">Private</option></select></label><label>Maximum net price<select value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)}><option value="all">Any price</option><option value="15000">Up to $15,000</option><option value="25000">Up to $25,000</option><option value="40000">Up to $40,000</option></select></label><label>Minimum acceptance<select value={minimumAcceptance} onChange={(event) => setMinimumAcceptance(event.target.value)}><option value="0">Any rate</option><option value="10">10%+</option><option value="25">25%+</option><option value="50">50%+</option></select></label><label>Aid type<select value={aid} onChange={(event) => setAid(event.target.value)}><option value="all">Any aid</option><option value="need">Need-based</option><option value="merit">Merit</option><option value="international">International aid</option><option value="full_need">Meets full need</option></select></label><CheckboxControl className="compact" checked={testOptional} onChange={(event) => setTestOptional(event.target.checked)}>Test optional only</CheckboxControl><CheckboxControl className="compact" checked={scoreMatch} onChange={(event) => setScoreMatch(event.target.checked)}>My SAT matches</CheckboxControl></aside>
      <section className="finder-results"><header><div><span className="eyebrow">PROFILE-BASED RESEARCH</span><h3>{items.length} universities found</h3></div><small>The match score is not an admission probability; it measures profile, preference, and affordability fit.</small></header><div className="university-results">{items.map((uni) => { const result = researchMap.get(uni.id); const fit = result ? { score: result.match_score, label: result.match_label } : universityFit(uni, student); return <article className="university-card" key={uni.id}><header><span className="rank">#{uni.ranking || '—'}</span><div><h3>{uni.name}</h3><p><MapPin size={14} /> {uni.city}, {uni.country} · {label(uni.institution_type)}</p></div><div className="university-fit"><span className="fit-badge">{fit.score}% {fit.label}</span>{result && <Badge>{result.admission_band}</Badge>}</div></header><div className="university-metrics"><div><span>Acceptance</span><b>{uni.acceptance_rate ? `${uni.acceptance_rate}%` : '—'}</b></div><div><span>Net price</span><b>{money(uni.net_price_usd)}</b></div><div><span>Average aid</span><b>{money(uni.average_aid_usd)}</b></div><div><span>SAT range</span><b>{uni.sat_min ? `${uni.sat_min}–${uni.sat_max || '—'}` : 'Optional/—'}</b></div></div>{result && <div className="research-breakdown">{Object.entries(result.score_breakdown).map(([name, value]) => <div key={name}><span>{label(name)}</span><div className="progress"><i style={{ width: `${Math.min(100, Number(value) * (name === 'academic' ? 2 : name === 'preferences' ? 4.5 : name === 'financial' ? 5 : 10))}%` }} /></div><b>{value}</b></div>)}</div>}<div className="aid-badges">{uni.offers_need_based_aid && <span>Need-based</span>}{uni.offers_merit_aid && <span>Merit</span>}{uni.offers_international_aid && <span>International aid</span>}{uni.meets_full_need && <span>Meets full need</span>}{uni.test_optional && <span>Test optional</span>}</div>{result && <details className="research-details"><summary>Why this result?</summary><div><ul>{result.reasons.map((reason) => <li key={reason}><CheckCircle2 size={13} /> {reason}</li>)}</ul>{result.gaps.length > 0 && <ul className="gaps">{result.gaps.map((gap) => <li key={gap}><Clock3 size={13} /> {gap}</li>)}</ul>}</div></details>}<footer><div><span>Application: {dateText(uni.application_deadline)}</span><span>Aid: {dateText(uni.scholarship_deadline)}</span></div>{added.has(uni.id) ? <span className="added"><Check size={17} /> Shortlisted</span> : <button className="button primary small" onClick={() => shortlist(uni)}><Plus size={16} /> Shortlist</button>}</footer></article> })}{!items.length && <Empty text="No universities match these filters." />}</div></section>
    </div></>}
    {tab === 'scholarships' && <div className="finder-layout"><aside className="filter-panel"><header><DollarSign size={18} /><b>Scholarship filters</b></header><label>Scholarship type<select value={scholarshipType} onChange={(event) => setScholarshipType(event.target.value)}><option value="all">All types</option><option value="merit">Merit</option><option value="need_based">Need-based</option><option value="leadership">Leadership</option><option value="research">Research</option><option value="full_ride">Full ride</option></select></label><label>Funding<select value={funding} onChange={(event) => setFunding(event.target.value)}><option value="all">Any funding</option><option value="full">Full funding</option><option value="partial">Partial</option><option value="fixed">Fixed amount</option></select></label><label>Scope<select value={scope} onChange={(event) => setScope(event.target.value)}><option value="all">National & International</option><option value="national">National</option><option value="international">International</option></select></label><CheckboxControl className="compact" checked={eligibleOnly} onChange={(event) => setEligibleOnly(event.target.checked)}>Eligible for my profile</CheckboxControl></aside><section className="finder-results"><header><div><span className="eyebrow">FUNDING OPTIONS</span><h3>{scholarships.length} scholarships found</h3></div><small>Eligibility is not a final decision; always verify the official requirements.</small></header><div className="scholarship-grid">{scholarships.map((item) => { const eligible = eligibleScholarship(item, student); return <article className="scholarship-card" key={item.id}><header><div><span>{label(item.scholarship_type)}</span><h3>{item.title}</h3><p>{item.provider}{item.university_name ? ` · ${item.university_name}` : ''}</p></div><Badge>{item.scope}</Badge></header><strong>{item.funding_level === 'fixed' ? money(item.amount_usd) : label(item.funding_level)}</strong><p>{item.coverage}</p><div className="eligibility-row"><span className={eligible ? 'eligible' : 'review'}>{eligible ? 'Profile match' : 'Review requirements'}</span><span>Deadline {dateText(item.deadline)}</span></div><div className="score-requirements">{item.min_gpa && <span>GPA {item.min_gpa}+</span>}{item.min_ielts && <span>IELTS {item.min_ielts}+</span>}{item.min_sat && <span>SAT {item.min_sat}+</span>}</div><div className="requirement-tags">{scholarshipRequirements(item).map((requirement) => <span key={requirement}>{requirement}</span>)}</div>{item.application_url && <a className="button quiet small" href={item.application_url} target="_blank" rel="noreferrer">Application info <ExternalLink size={14} /></a>}</article> })}{!scholarships.length && <Empty text="No matching scholarships found." />}</div></section></div>}
    {tab === 'aid' && <AidChecklist data={data} student={student} />}
  </div>
}

function CollegeProfileQuestions({ research, saving, onComplete }) {
  const [answers, setAnswers] = useState(() => Object.fromEntries(research.questions.map((question) => [question.field, research.profile_snapshot?.[question.field] ?? ''])))
  function submit(event) {
    event.preventDefault()
    onComplete(answers)
  }
  return <section className="college-profile-questions"><div className="research-question-copy"><span><Sparkles size={20} /></span><div><span className="eyebrow">PROFILE DATA REQUIRED</span><h2>A few details are missing from your research profile</h2><p>Your answers will be saved to your student profile and used to rank universities for you.</p></div></div><form onSubmit={submit}><div className="research-question-grid">{research.questions.map((question) => <label key={question.field}><span>{question.label}</span><input type={question.type} min={question.min} max={question.max} step={question.step || (question.type === 'number' ? '1' : undefined)} placeholder={question.placeholder} value={answers[question.field] ?? ''} onChange={(event) => setAnswers((current) => ({ ...current, [question.field]: event.target.value }))} required /></label>)}</div><footer><small>{research.questions.length} answers required</small><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? <><RefreshCw className="spin" size={16} /> Researching…</> : <><Search size={16} /> Save & research</>}</button></footer></form></section>
}

function CollegeResearchOverview({ research, onRefresh }) {
  const profile = research.profile_snapshot || {}
  const evidence = Object.values(profile.evidence || {}).reduce((total, value) => total + Number(value || 0), 0)
  return <section className="college-research-overview"><div><span className="research-status-icon"><CheckCircle2 size={21} /></span><div><span className="eyebrow">RESEARCH READY</span><h3>Results calculated from your student profile</h3><p>{research.methodology}</p></div></div><div className="research-profile-chips"><span>SAT <b>{profile.sat_score}</b></span><span>GPA <b>{profile.gpa}</b></span><span>IELTS <b>{profile.ielts_score}</b></span><span>Major <b>{profile.target_major}</b></span><span>Budget <b>{money(profile.budget_usd)}</b></span><span>Evidence <b>{evidence}</b></span></div><button className="button quiet small" onClick={onRefresh}><RefreshCw size={15} /> Refresh</button></section>
}

function AidChecklist({ data, student }) {
  const shortlisted = data.applications.map((item) => data.universities.find((uni) => uni.id === item.university)).filter(Boolean)
  const needsCss = shortlisted.some((uni) => uni.css_profile_required)
  const needsFafsa = shortlisted.some((uni) => uni.fafsa_required)
  const checklist = [
    ['Academic transcript', 'Official grades and school records', true],
    ['Family financial documents', 'Income, tax or employer statements requested by the institution', student?.scholarship_needed],
    ['Bank or sponsor statement', 'Proof of available funds for international study', true],
    ['Scholarship essays', 'Motivation, impact and financial-need responses', true],
    ['Recommendation letters', 'Teacher or counselor recommendations where requested', true],
    ['CSS Profile', 'Only for shortlisted universities that require it', needsCss],
    ['FAFSA', 'Only where eligibility and university requirements apply', needsFafsa],
  ]
  return <div className="aid-checklist"><section className="aid-intro"><div><span className="eyebrow">AID PREPARATION</span><h2>Prepare for financial aid</h2><p>Core documents based on your shortlist and profile. Verify final requirements on each university’s official financial aid page.</p></div><div className="aid-profile-summary"><Detail label="Budget" value={money(student?.budget_usd)} /><Detail label="Scholarship" value={student?.scholarship_needed ? 'Needed' : 'Optional'} /><Detail label="Shortlisted" value={data.applications.length} /></div></section><div className="checklist-cards">{checklist.map(([title, description, needed]) => <article key={title} className={needed ? 'needed' : ''}><span>{needed ? <CheckCircle2 size={20} /> : <Clock3 size={20} />}</span><div><h3>{title}</h3><p>{description}</p></div><Badge>{needed ? 'Prepare' : 'If required'}</Badge></article>)}</div></div>
}

function ProgramsPage({ data, query }) {
  const [type, setType] = useState('national')
  const [category, setCategory] = useState('all')
  const [delivery, setDelivery] = useState('all')
  const [aidOnly, setAidOnly] = useState(false)
  const nationalCount = data.opportunityPrograms.filter((item) => item.program_type === 'national').length
  const internationalCount = data.opportunityPrograms.filter((item) => item.program_type === 'international').length
  const categories = [...new Set(data.opportunityPrograms.filter((item) => item.program_type === type).map((item) => item.category))].sort()
  const programs = data.opportunityPrograms.filter((item) => item.program_type === type && (category === 'all' || item.category === category) && (delivery === 'all' || item.delivery_mode === delivery) && (!aidOnly || item.scholarship_available) && JSON.stringify(item).toLowerCase().includes(query.toLowerCase()))
  return <div className="section-stack student-portal"><section className="programs-hero"><div><span className="eyebrow">PROFILE-BUILDING OPPORTUNITIES</span><h2>National & International Programs</h2><p>Find research, leadership, competition, and summer programs in one catalog.</p></div><Globe2 size={76} /></section><ChoiceCards name="program-type" label="Program type" value={type} onChange={(nextType) => { setType(nextType); setCategory('all') }} options={[{ value: 'national', label: `National (${nationalCount})`, description: 'Opportunities within Uzbekistan', icon: MapPin }, { value: 'international', label: `International (${internationalCount})`, description: 'Global and overseas opportunities', icon: Globe2 }]} /><div className="program-filters"><label>Category<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="all">All categories</option>{categories.map((item) => <option key={item}>{item}</option>)}</select></label><label>Delivery<select value={delivery} onChange={(event) => setDelivery(event.target.value)}><option value="all">All formats</option><option value="onsite">On-site</option><option value="online">Online</option><option value="hybrid">Hybrid</option></select></label><CheckboxControl className="compact" checked={aidOnly} onChange={(event) => setAidOnly(event.target.checked)}>Scholarship available</CheckboxControl><span>{programs.length} programs</span></div><div className="program-grid">{programs.map((item) => <article className="program-card" key={item.id}><header><span>{item.category}</span><Badge>{item.program_type}</Badge></header><h3>{item.title}</h3><p className="provider">{item.provider}</p><p>{item.description}</p><div className="program-meta"><span><MapPin size={15} /> {[item.city, item.country].filter(Boolean).join(', ')}</span><span><CalendarDays size={15} /> Deadline {dateText(item.deadline)}</span><span><DollarSign size={15} /> {Number(item.fee_usd) === 0 ? 'Free' : money(item.fee_usd)}</span><span><UsersRound size={15} /> Grades {item.eligible_grades || 'Open'}</span></div>{item.scholarship_available && <div className="program-aid"><Sparkles size={16} /><span><b>Financial aid available</b>{item.aid_details}</span></div>}<details><summary>Requirements</summary><p>{item.requirements || 'See official application page.'}</p></details>{item.application_url && <a className="button primary small" href={item.application_url} target="_blank" rel="noreferrer">View program <ExternalLink size={14} /></a>}</article>)}{!programs.length && <Empty text="No programs match these filters." />}</div></div>
}

function StorePage({ data, query, setPage }) {
  const items = data.storeItems.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()))
  return <div className="section-stack student-portal"><section className="store-hero"><div><span className="eyebrow">NASEEB EDUCATION SERVICES</span><h2>Unlock your next step.</h2><p>Explore education and counseling services that support your application journey.</p><button className="button light" onClick={() => setPage('contacts')}>Talk to your team <ChevronRight size={17} /></button></div><PackageOpen size={104} /></section><div className="store-grid">{items.map((item) => <article key={item.id} className={item.is_featured ? 'featured' : ''}><span>{item.category}</span><h3>{item.title}</h3><p>{item.description}</p><footer><b>{item.price_label || 'Ask your counselor'}</b><button className="button quiet small" onClick={() => setPage('contacts')}>Learn more</button></footer></article>)}{!items.length && <Empty />}</div></div>
}

function ContactsPage({ data, setPage }) {
  return <div className="section-stack student-portal"><section className="portal-hero contacts-hero"><div><span className="eyebrow">YOUR SUPPORT NETWORK</span><h2>My Naseeb Team</h2><p>Quickly connect with your counselor and school coordinator.</p></div><ContactRound size={64} /></section><div className="contact-grid">{data.team.map((member) => <article key={`${member.kind}-${member.id}`}><span className="avatar large">{initials(member.name)}</span><div><span>{member.kind === 'counselor' ? 'Primary counselor' : 'School coordinator'}</span><h3>{member.name}</h3><p>{member.role}</p><small>{member.email || 'Email not provided'}</small><small>{member.phone || 'Phone not provided'}</small></div><footer><button className="button primary" onClick={() => setPage('messages')}><MessageCircle size={16} /> Message</button>{member.kind === 'counselor' && <button className="button quiet" onClick={() => setPage('bookings')}><CalendarClock size={16} /> Book</button>}</footer></article>)}{!data.team.length && <Empty text="No team members have been assigned yet." />}</div></div>
}

function PageRouter({ page, user, data, stats, query, reload, notify, setPage }) {
  if (page === 'dashboard') return <Dashboard user={user} data={data} stats={stats} setPage={setPage} />
  if (user.role === 'student' && page === 'student_center') return <StudentCenterPage {...{ user, data, query, reload, notify }} />
  if (isTaskManager(user) && page === 'roadmap') return <RoadmapPage {...{ user, data, query, reload, notify }} />
  if (user.role === 'student' && page === 'roadmap') return <RoadmapPage {...{ user, data, query, reload, notify }} />
  if (user.role === 'student' && page === 'community') return <CommunityPage {...{ data, reload, notify }} />
  if (user.role === 'student' && page === 'bookings') return <BookingsPage {...{ data, reload, notify }} />
  if (page === 'messages') return <MessagesPage {...{ user, data, notify }} />
  if (user.role === 'student' && page === 'program_usage') return <ProgramUsagePage data={data} />
  if (user.role === 'student' && page === 'programs') return <ProgramsPage {...{ data, query }} />
  if (user.role === 'student' && page === 'resource_index') return <ResourceIndexPage {...{ data, query, setPage }} />
  if (user.role === 'student' && page === 'essay_lab') return <EssayLabPage {...{ user, data, query, reload, notify }} />
  if (user.role === 'student' && page === 'applications') return <ApplicationsPortalPage {...{ user, data, query, reload, notify, setPage }} />
  if (user.role === 'student' && page === 'college_search') return <CollegeSearchPage {...{ data, query, reload, notify }} />
  if (user.role === 'student' && page === 'store') return <StorePage {...{ data, query, setPage }} />
  if (user.role === 'student' && page === 'contacts') return <ContactsPage {...{ data, setPage }} />
  if (page === 'schools') return <SchoolsPage data={data} reload={reload} notify={notify} />
  if (page === 'students') return <StudentsPage user={user} data={data} query={query} reload={reload} notify={notify} />
  if (page === 'profile') return <StudentOverview student={ownStudent(data)} data={data} />
  if (page === 'academics') return <div className="section-stack">{user.role === 'student' && <ProfileCard student={ownStudent(data)} />}<ResourceSection title="Research" resource="researches" {...{ user, data, query, reload, notify }} /></div>
  if (page === 'portfolio') return <div className="split-grid"><ResourceSection title="Projects" resource="projects" {...{ user, data, query, reload, notify }} /><ResourceSection title="Internships" resource="internships" {...{ user, data, query, reload, notify }} /></div>
  if (page === 'activities') return <div className="section-stack"><div className="split-grid"><ResourceSection title="Activities" resource="activities" {...{ user, data, query, reload, notify }} /><ResourceSection title="Honors" resource="honors" {...{ user, data, query, reload, notify }} /></div><ResourceSection title="Achievements" resource="achievements" {...{ user, data, query, reload, notify }} /></div>
  if (page === 'recommendations') return <ResourceSection title="Recommendation letters" resource="recommendations" {...{ user, data, query, reload, notify }} />
  if (page === 'documents') return <DocumentsPage {...{ user, data, query, reload, notify }} />
  if (page === 'certificates') return <DocumentsPage typeFilter="certificate" title="Certificates" {...{ user, data, query, reload, notify }} />
  if (page === 'notifications') return <NotificationsPage {...{ data, reload, notify }} />
  const titleMap = { tasks: 'Tasks', applications: 'University applications', essays: 'Essays', meetings: 'Meeting notes' }
  return <ResourceSection title={titleMap[page] || label(page)} resource={page} {...{ user, data, query, reload, notify }} />
}

export default function App() {
  const [theme, setTheme] = useState(initialTheme)
  const [user, setUser] = useState(null)
  const [data, setData] = useState(EMPTY_DATA)
  const [stats, setStats] = useState(null)
  const [page, setPage] = useState('dashboard')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState(null)

  const notify = useCallback((message, type = 'success') => {
    setToast({ message, type })
    window.setTimeout(() => setToast(null), 3500)
  }, [])

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    window.localStorage.setItem(THEME_KEY, theme)
    const favicon = document.querySelector('link[data-theme-icon]')
    if (favicon) favicon.href = theme === 'dark' ? '/brand/naseeb-dark.png' : '/brand/naseeb-light.jpg'
    const themeColor = document.querySelector('meta[name="theme-color"]')
    if (themeColor) themeColor.content = getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim()
  }, [theme])

  const toggleTheme = useCallback(() => setTheme((current) => current === 'dark' ? 'light' : 'dark'), [])

  const loadUser = useCallback(async () => {
    const current = await api.me()
    setUser(current)
    return current
  }, [])

  const loadData = useCallback(async (activeUser = user) => {
    if (!activeUser) return
    setLoading(true); setError('')
    try {
      const studentResources = ['students', 'tasks', 'applications', 'documents', 'essays', 'achievements', 'researches', 'projects', 'internships', 'activities', 'honors', 'recommendations', 'meetings', 'notifications'].map((key) => [key, key])
      const portalResources = [
        ['roadmapMissions', 'roadmap-missions'], ['communityPosts', 'community-posts'], ['bookings', 'bookings'],
        ['messageChannels', 'message-channels'], ['programServices', 'program-services'],
        ['scholarships', 'scholarships'], ['opportunityPrograms', 'opportunity-programs'],
        ['resourceLibrary', 'resource-library'], ['storeItems', 'store-items'], ['team', 'student-team'],
      ]
      const resources = activeUser.role === 'organization'
        ? [...studentResources, ['messageChannels', 'message-channels']]
        : activeUser.role === 'teacher'
          ? [['students', 'students'], ['tasks', 'tasks'], ['roadmapMissions', 'roadmap-missions'], ['messageChannels', 'message-channels']]
          : [...studentResources, ['universities', 'universities'], ...(isCounselor(activeUser) ? [['schools', 'schools'], ['roadmapMissions', 'roadmap-missions'], ['messageChannels', 'message-channels']] : portalResources)]
      const [dashboardStats, ...payloads] = await Promise.all([api.dashboard(), ...resources.map(([, endpoint]) => api.list(endpoint))])
      const nextData = { ...EMPTY_DATA }
      resources.forEach(([key], index) => { nextData[key] = payloads[index] || [] })
      setStats(dashboardStats); setData(nextData)
    } catch (err) {
      if (err.status === 401) { api.logout(); setUser(null) }
      else setError(err.message)
    } finally { setLoading(false) }
  }, [user])

  useEffect(() => {
    if (!api.hasSession()) return
    loadUser().then((current) => loadData(current)).catch(() => { api.logout(); setUser(null) })
  }, [])

  useEffect(() => {
    if (user && !navigationFor(user).includes(page)) setPage('dashboard')
  }, [user, page])

  async function afterLogin() {
    const current = await loadUser()
    await loadData(current)
  }
  function logout() { api.logout(); setUser(null); setData(EMPTY_DATA); setPage('dashboard') }

  if (!user) return <Login onLogin={afterLogin} theme={theme} toggleTheme={toggleTheme} />
  return <>
    <AppShell {...{ user, data, stats, page, setPage, query, setQuery, loading, error, refresh: () => loadData(user), notify, logout, theme, toggleTheme }}>
      <PageRouter {...{ page, user, data, stats, query, reload: () => loadData(user), notify, setPage }} />
    </AppShell>
    {toast && <div className={`toast ${toast.type}`}>{toast.type === 'success' ? <ShieldCheck size={18} /> : <X size={18} />}{toast.message}</div>}
  </>
}
