import {
  Bell,
  CalendarDays,
  Check,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  FileText,
  Flag,
  FolderOpen,
  GraduationCap,
  Home,
  Map,
  MessageSquareText,
  PenLine,
  Search,
  UsersRound,
} from 'lucide-react'

import { t } from './i18n'

function PreviewBrand() {
  return (
    <div className="landing-preview-brand" aria-label={t('Naseeb Edu')}>
      <span className="brand-logo landing-preview-emblem" aria-hidden="true" />
      <b>Naseeb Edu</b>
    </div>
  )
}

function ProductChrome({ children, label }) {
  return (
    /* role="img": a screen reader should hear what the picture shows, not sixty
       fragments of illustrative dashboard data read as if they were content. */
    <div className="landing-product-window" role="img" aria-label={t(label)}>
      <div className="landing-product-chrome" aria-hidden="true"><i /><i /><i /></div>
      {children}
    </div>
  )
}

function PreviewNav({ items, active }) {
  return (
    <nav aria-label={t('Dashboard preview navigation')}>
      {items.map(({ icon: Icon, label }) => (
        <span className={label === active ? 'is-active' : ''} key={label}>
          <Icon size={16} aria-hidden="true" />
          <span className="landing-preview-label">{t(label)}</span>
        </span>
      ))}
    </nav>
  )
}

function PreviewUser({ initials, name, role }) {
  return (
    <div className="landing-preview-user">
      <span>{initials}</span>
      <div><b>{name}</b><small>{t(role)}</small></div>
      <ChevronRight size={13} aria-hidden="true" />
    </div>
  )
}

const COUNSELOR_NAV = [
  { icon: Home, label: 'Overview' },
  { icon: UsersRound, label: 'Students' },
  { icon: ClipboardCheck, label: 'Reviews' },
  { icon: MessageSquareText, label: 'Messages' },
]

const STUDENT_NAV = [
  { icon: Home, label: 'Home' },
  { icon: Map, label: 'Roadmap' },
  { icon: GraduationCap, label: 'Universities' },
  { icon: PenLine, label: 'Essays' },
  { icon: FolderOpen, label: 'Documents' },
]

const STUDENT_ROWS = [
  { initials: 'AS', name: 'Aisha S.', major: 'Computer Science', progress: 78, status: 'On track', tone: 'success' },
  { initials: 'HK', name: 'Hamza K.', major: 'Mechanical Engineering', progress: 55, status: 'Needs review', tone: 'warning' },
  { initials: 'MN', name: 'Maya N.', major: 'Business Analytics', progress: 92, status: 'On track', tone: 'success' },
  { initials: 'ZA', name: 'Zain A.', major: 'Electrical Engineering', progress: 41, status: 'Deadline soon', tone: 'danger' },
]

const REVIEW_ITEMS = [
  { icon: FileText, title: 'Personal statement', owner: 'Hamza K.', time: '2h ago' },
  { icon: ClipboardCheck, title: 'Activity list', owner: 'Maya N.', time: '5h ago' },
  { icon: PenLine, title: 'Essay draft', owner: 'Zain A.', time: '1d ago' },
]

export function CounselorDashboardPreview() {
  return (
    <ProductChrome label="Counselor dashboard preview: student list, progress and review queue.">
      <div className="landing-product-layout landing-counselor-ui">
        <aside className="landing-preview-sidebar">
          <PreviewBrand />
          <PreviewNav items={COUNSELOR_NAV} active="Overview" />
          <PreviewUser initials="SC" name="Sara Karimova" role="Counselor" />
        </aside>
        <div className="landing-preview-main">
          <header className="landing-preview-toolbar">
            <div><span>{t('Counselor workspace')}</span><h3>{t('Student progress')}</h3></div>
            <label><Search size={13} aria-hidden="true" /><span>{t('Search students')}</span></label>
            <Bell size={16} aria-hidden="true" />
          </header>
          <div className="landing-preview-metrics">
            <div><UsersRound size={17} /><strong>24</strong><span>{t('Students')}</span></div>
            <div><ClipboardCheck size={17} /><strong>7</strong><span>{t('Reviews')}</span></div>
            <div><CalendarDays size={17} /><strong>3</strong><span>{t('Deadlines')}</span></div>
          </div>
          <div className="landing-counselor-grid">
            <div className="landing-student-table">
              <header><span>{t('Student')}</span><span>{t('Target major')}</span><span>{t('Roadmap progress')}</span><span>{t('Status')}</span></header>
              {STUDENT_ROWS.map((student) => (
                <div className="landing-student-row" key={student.name}>
                  <span className="landing-preview-person"><i>{student.initials}</i><b>{student.name}</b></span>
                  <span>{student.major}</span>
                  <span className="landing-preview-progress"><i style={{ '--landing-progress': `${student.progress}%` }} /><b>{student.progress}%</b></span>
                  <span className={`landing-preview-status ${student.tone}`}>{t(student.status)}</span>
                </div>
              ))}
              <footer>{t('View all students')} <ChevronRight size={13} /></footer>
            </div>
            <aside className="landing-review-queue">
              <header><div><h4>{t('Review queue')}</h4><span>{t('Waiting for your review')}</span></div><b>7</b></header>
              {REVIEW_ITEMS.map(({ icon: Icon, title, owner, time }) => (
                <div key={title}><Icon size={14} /><span><b>{t(title)}</b><small>{owner}</small></span><time>{t(time)}</time></div>
              ))}
              <footer>{t('View all reviews')} <ChevronRight size={13} /></footer>
            </aside>
          </div>
        </div>
      </div>
    </ProductChrome>
  )
}

const TODAY_ITEMS = [
  ['Compare Computer Science programs', '30 min'],
  ['Outline personal statement', '45 min'],
  ['Request a recommendation', '15 min'],
]

export function StudentDashboardPreview() {
  return (
    <ProductChrome label="Student dashboard preview: roadmap progress, next priority and today’s plan.">
      <div className="landing-product-layout landing-student-ui">
        <aside className="landing-preview-sidebar">
          <PreviewBrand />
          <PreviewNav items={STUDENT_NAV} active="Home" />
          <PreviewUser initials="AS" name="Aisha Siddiqi" role="Class of 2026" />
        </aside>
        <div className="landing-preview-main">
          <header className="landing-preview-toolbar landing-student-toolbar">
            <div><span>{t('Your application workspace')}</span><h3>{t('Good morning, Aisha')}</h3></div>
            <Bell size={16} aria-hidden="true" />
          </header>
          <div className="landing-student-overview">
            <section className="landing-journey-progress">
              <header><span>{t('Application journey')}</span></header>
              <div className="landing-progress-ring"><strong>64%</strong></div>
              <p><b>{t('Keep going')}</b><span>{t('16 of 25 roadmap steps complete')}</span></p>
            </section>
            <section className="landing-next-priority">
              <header><Flag size={14} /><span>{t('Next priority')}</span></header>
              <h4>{t('Finalize university shortlist')}</h4>
              <p>{t('Refine 8–10 universities that fit your goals and academic profile.')}</p>
              <small><CalendarDays size={13} /> {t('Due Friday')}</small>
            </section>
            <section className="landing-today-plan">
              <header><span>{t("Today's plan")}</span></header>
              {TODAY_ITEMS.map(([title, duration]) => (
                <div key={title}><i><Check size={11} /></i><span>{t(title)}</span><small><Clock3 size={11} /> {t(duration)}</small><ChevronRight size={12} /></div>
              ))}
            </section>
            <section className="landing-application-counts">
              <header><span>{t('Applications')}</span></header>
              <div><span><b>3</b><small>{t('Draft')}</small></span><span><b>2</b><small>{t('Reviewing')}</small></span><span className="ready"><b>1</b><small>{t('Ready')}</small></span></div>
            </section>
          </div>
          <div className="landing-check-in"><MessageSquareText size={15} /><span><b>{t('Counselor check-in')}</b><small>{t('Your next check-in is Wednesday at 4:00 PM.')}</small></span><i>{t('Send a message')}</i></div>
        </div>
      </div>
    </ProductChrome>
  )
}
