import {
  Activity, Award, BookOpen, CalendarDays, ChevronDown, ChevronRight,
  ClipboardCheck, Clock3, Compass, ContactRound, ExternalLink, Eye,
  FileText, Fingerprint, FolderOpen, Globe2, GraduationCap, LayoutDashboard,
  Library, LifeBuoy, ListChecks, LogOut, MessageSquareText, Moon, Pencil,
  PenLine, Plus, RefreshCw, School, Search, ShoppingCart, Sun, Target,
  Trash2, UsersRound,
} from 'lucide-react'

import { getLanguage, t, tx } from './i18n'

// Static previews of the real product. Never fetch student records or expose
// contact details on the public landing page.
function ProductChrome({ children, label }) {
  return (
    <div className="landing-product-window" role="img" aria-label={t(label)}>
      <div className="landing-product-chrome" aria-hidden="true"><i /><i /><i /></div>
      <div aria-hidden="true">{children}</div>
    </div>
  )
}

function PreviewSidebar({ items, active, initials, name, role }) {
  return (
    <aside className="landing-preview-sidebar">
      <div className="landing-preview-brand">
        <span className="brand-logo landing-preview-emblem" />
        <div><b>Naseeb Edu</b><small>{t('Education Counseling Platform')}</small></div>
      </div>
      <div className="landing-preview-nav">
        {items.map(([Icon, label]) => (
          <span className={label === active ? 'is-active' : ''} key={label}>
            <Icon size={15} /><span className="landing-preview-label">{t(label)}</span>
          </span>
        ))}
      </div>
      <div className="landing-preview-user">
        <span>{initials}</span>
        <div><b>{name}</b><small>{t(role)}</small></div>
        <LogOut size={14} />
      </div>
    </aside>
  )
}

function PreviewToolbar({ title, description }) {
  return (
    <header className="landing-preview-toolbar">
      <div className="landing-preview-heading"><span>{t(title)}</span><h3>{t(title)}</h3><p>{t(description)}</p></div>
      <div className="landing-preview-tools">
        <span className="landing-preview-search"><Search size={14} />{t('Search pages and records…')}</span>
        <span><Globe2 size={13} /><b>{getLanguage().toUpperCase()}</b><ChevronDown size={11} /></span>
        <span><Moon className="landing-preview-moon" size={14} /><Sun className="landing-preview-sun" size={14} /></span>
        <span><RefreshCw size={14} /></span>
      </div>
    </header>
  )
}

function PreviewProgress({ label, value, note }) {
  return (
    <div className="landing-preview-progress-row">
      <b>{t(label)}</b><strong>{value}%</strong>
      <i style={{ '--landing-progress': `${value}%` }} />
      {note && <small>{note}</small>}
    </div>
  )
}

const STUDENT_NAV = [
  [LayoutDashboard, 'Dashboard'], [UsersRound, 'Student Center'], [Compass, 'Roadmap'],
  [UsersRound, 'Community'], [CalendarDays, 'Meetings'], [MessageSquareText, 'Messages'],
  [ListChecks, 'Program Usage'], [Globe2, 'Programs'], [Library, 'Resource Index'],
  [PenLine, 'Essay Lab'], [Target, 'Applications'], [School, 'College Search'],
  [ShoppingCart, 'Naseeb Store'], [ContactRound, 'Contacts'], [Clock3, 'Screen Time'],
  [LifeBuoy, 'Support'],
]

const COUNSELOR_NAV = [
  [LayoutDashboard, 'Dashboard'], [School, 'Schools'], [UsersRound, 'Students'],
  [Compass, 'Counselor Roadmap'], [BookOpen, 'Academics'], [FolderOpen, 'Portfolio'],
  [Activity, 'Activities'], [MessageSquareText, 'Recommendations'], [ClipboardCheck, 'Tasks'],
  [Compass, 'Roadmap'], [ListChecks, 'Program Usage'], [Target, 'Applications'],
  [FileText, 'Documents'], [Award, 'Certificates'], [GraduationCap, 'Essays'],
  [CalendarDays, 'Meetings'], [MessageSquareText, 'Messages'], [Clock3, 'Screen Time'],
]

const STUDENT_ROWS = [
  { initials: 'AM', name: 'Abbos Misraliyev', major: 'Computer Science', country: 'China', gpa: '4.90', ielts: '6.0', sat: '—', level: 3, xp: 550, task: 80, roadmap: 63, overall: 72 },
  { initials: 'AA', name: 'Akbar Alipov', major: 'Law', country: 'America', gpa: '4.80', ielts: '6.5', sat: '1340', level: 3, xp: 500, task: 60, roadmap: 75, overall: 68 },
  { initials: 'AM', name: 'Akmal Mirzayev', major: 'Economics', country: 'USA', gpa: '4.80', ielts: '6.5', sat: '1340', level: 2, xp: 250, task: 40, roadmap: 38, overall: 39 },
  { initials: 'ES', name: 'Ergashova Shohinur', major: 'Digital marketing leader', country: 'China', gpa: '5.00', ielts: '—', sat: '—', level: 4, xp: 875, task: 100, roadmap: 88, overall: 94 },
  { initials: 'ED', name: 'Esonboyev Dilyorbek', major: 'Computer science/game development', country: 'Korea', gpa: '4.95', ielts: '7.5', sat: '1310', level: 3, xp: 450, task: 80, roadmap: 50, overall: 65 },
  { initials: 'KO', name: 'Karimberdiyeva Odinaxon', major: 'Digital Education', country: 'UK', gpa: '5.00', ielts: '7.0', sat: '—', level: 4, xp: 625, task: 80, roadmap: 75, overall: 78 },
  { initials: 'MD', name: 'Musayeva Dinara', major: 'Hospitality Management', country: 'Netherlands', gpa: '—', ielts: '—', sat: '—', level: 2, xp: 300, task: 40, roadmap: 50, overall: 45 },
  { initials: 'NO', name: 'Nilufar Otabekova', major: "International Relations (minor in Women's Rights)", country: 'Europe', gpa: '5.00', ielts: '7.0', sat: '—', level: 4, xp: 725, task: 80, roadmap: 88, overall: 84 },
  { initials: 'SX', name: 'Shabnam Xamzayeva', major: 'Educational policy', country: 'Hong Kong', gpa: '4.80', ielts: '7.0', sat: '—', level: 3, xp: 475, task: 70, roadmap: 62, overall: 66 },
]

export function CounselorDashboardPreview() {
  return (
    <ProductChrome label="Counselor Students page preview: student profiles, targets, scores, XP and progress.">
      <div className="landing-product-layout landing-counselor-ui">
        <PreviewSidebar items={COUNSELOR_NAV} active="Students" initials="MC" name="Madina" role="School Counselor" />
        <div className="landing-preview-main">
          <PreviewToolbar title="Students" description="Student profiles and progress" />
          <section className="landing-preview-students-panel">
            <header><h4>{t('Students')}</h4><div className="landing-preview-actions">
              <span><UsersRound size={13} />{t('Connect students')}</span>
              <span className="is-primary"><Plus size={13} />{t('Add student')}</span>
            </div></header>
            <div className="landing-preview-table-wrap">
              <table className="landing-preview-students-table">
                <thead><tr>
                  {['Student', 'School', 'Target', 'Scores', 'XP / Level', 'Task / Roadmap / Overall'].map((label) => <th key={label}>{t(label)}</th>)}
                  <th />
                </tr></thead>
                <tbody>{STUDENT_ROWS.slice(0, 5).map((student) => (
                  <tr key={student.name}>
                    <td><span className="landing-preview-person"><i>{student.initials}</i><b>{student.name}</b></span></td>
                    <td>RBIS</td>
                    <td><b>{t(student.major)}</b><small>{t(student.country)}</small></td>
                    <td>GPA {student.gpa}<small>IELTS {student.ielts} · SAT {student.sat}</small></td>
                    <td><b>{t('Level')} {student.level}</b><small>{student.xp} XP</small></td>
                    <td><div className="landing-preview-progress-stack">{[['Task', student.task], ['Roadmap', student.roadmap], ['Overall', student.overall]].map(([label, value]) => <PreviewProgress key={label} label={label} value={value} />)}</div></td>
                    <td><span className="landing-preview-row-actions"><i><Eye size={12} /></i><i><Pencil size={12} /></i><i className="is-danger"><Trash2 size={12} /></i></span></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <footer className="landing-preview-table-footer">
              <span>{tx`Showing ${5} of ${STUDENT_ROWS.length} students`}</span>
              <span>{t('View all students')} <ChevronRight size={12} /></span>
            </footer>
          </section>
        </div>
      </div>
    </ProductChrome>
  )
}

const DISCOVERY_CARDS = [
  { icon: Fingerprint, eyebrow: 'SELF DISCOVERY', title: 'Personality & Interests', description: 'Identify your strengths, interests, and future study direction.', action: 'Start assessment', actionIcon: ExternalLink },
  { icon: GraduationCap, eyebrow: 'COLLEGE RESEARCH', title: 'University Match', description: 'Find universities that match your academic profile and goals.', action: 'Explore matches', actionIcon: ChevronRight },
]

export function StudentDashboardPreview() {
  const metrics = [
    ['Active tasks', 4, tx`${12} completed`], ['Applications', 3, tx`${2} submitted`],
    ['Essays', 3, tx`${2} approved`], ['Achievements', 2, t('Honors included')],
  ]

  return (
    <ProductChrome label="Student dashboard preview: welcome, journey progress, XP, assessments and applications.">
      <div className="landing-product-layout landing-student-ui">
        <PreviewSidebar items={STUDENT_NAV} active="Dashboard" initials="RE" name="Ramazon Ergashev" role="Student" />
        <div className="landing-preview-main">
          <PreviewToolbar title="Dashboard" description="A complete view of the application journey" />
          <section className="landing-preview-welcome">
            <div>
              <span className="landing-preview-eyebrow">{t('WELCOME BACK')}</span>
              <h4>Ramazon Ergashev</h4>
              <p>{t('Complete today’s priorities and strengthen your application profile.')}</p>
              <div className="landing-preview-actions">
                <span className="is-light"><Compass size={14} />{t('Open roadmap')}</span>
                <span className="is-ghost"><Search size={14} />{t('Find universities')}</span>
              </div>
            </div>
            <div className="landing-preview-journey-ring" style={{ '--landing-progress': '72%' }}>
              <strong>72%</strong><span>{t('Journey progress')}</span>
            </div>
          </section>
          <div className="landing-preview-dashboard-grid">
            <div className="landing-preview-progress-panels">
              <section className="landing-preview-progress-card">
                <div><span className="landing-preview-eyebrow">{t('LIVE PROGRESS')}</span><h4>{t('Tasks and roadmap progress')}</h4><p>{t('Every update is added to your overall progress automatically.')}</p></div>
                <div>
                  <PreviewProgress label="Tasks" value={80} note={tx`${12} approved`} />
                  <PreviewProgress label="Roadmap" value={63} note={tx`${7} completed`} />
                  <PreviewProgress label="Overall journey" value={72} note={t('A deadline needs your attention')} />
                </div>
              </section>
              <section className="landing-preview-progress-card">
                <div><span className="landing-preview-eyebrow">{t('XP & LEVEL')}</span><h4>{t('Level')} 3</h4><p>{tx`Next level: ${600} XP`}</p></div>
                <div><PreviewProgress label="550 XP" value={92} note={tx`${50} XP remaining`} /></div>
              </section>
            </div>
            <div className="landing-preview-discovery-cards">
              {DISCOVERY_CARDS.map(({ icon: Icon, eyebrow, title, description, action, actionIcon: ActionIcon }) => (
                <section className="landing-preview-discovery" key={title}>
                  <Icon className="landing-preview-discovery-art" size={74} strokeWidth={1.4} />
                  <div><span className="landing-preview-eyebrow">{t(eyebrow)}</span><h4>{t(title)}</h4><p>{t(description)}</p><span className="landing-preview-discovery-action">{t(action)}<ActionIcon size={12} /></span></div>
                </section>
              ))}
            </div>
          </div>
          <div className="landing-preview-stat-cards">
            {metrics.map(([label, value, note]) => <section key={label}><h4>{t(label)}</h4><strong>{value}</strong><p>{note}</p></section>)}
          </div>
        </div>
      </div>
    </ProductChrome>
  )
}
