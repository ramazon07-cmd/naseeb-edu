import {
  ArrowRight, Calendar, CalendarClock, Check, CheckSquare, ChevronDown, Compass, Fingerprint,
  Globe2, GraduationCap, LayoutDashboard, Lock, LogOut, MessageCircle, Pencil, PenLine,
  Plus, RefreshCw, School, Search, ShoppingCart, Target, UserPlus, Users, UsersRound,
} from 'lucide-react'

import { getLanguage, t } from './i18n'

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

function PreviewSidebar({ items, active, locked = [], initials, name, role }) {
  return (
    <aside className="landing-preview-sidebar">
      <div className="landing-preview-brand">
        <span className="brand-logo landing-preview-emblem" />
        <div><b>Naseeb Edu</b></div>
      </div>
      <div className="landing-preview-nav">
        {items.map(([Icon, label]) => (
          <span className={label === active ? 'is-active' : locked.includes(label) ? 'is-locked' : ''} key={label}>
            <Icon size={15} /><span className="landing-preview-label">{t(label)}</span>
            {locked.includes(label) && <Lock size={11} />}
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

function PreviewToolbar({ title }) {
  return (
    <header className="landing-preview-toolbar">
      <div className="landing-preview-heading"><h3>{t(title)}</h3></div>
      <div className="landing-preview-tools">
        <span className="landing-preview-search"><Search size={14} />{t('Search pages and records…')}</span>
        <span><Globe2 size={13} /><b>{getLanguage().toUpperCase()}</b><ChevronDown size={11} /></span>
        <span><RefreshCw size={14} /></span>
      </div>
    </header>
  )
}

// The sidebars below list what each role gets today; Roadmap and the store are
// shown locked, as in the product.
const STUDENT_NAV = [
  [LayoutDashboard, 'Dashboard'], [UsersRound, 'Student Center'], [Fingerprint, 'Profile Assessment'],
  [CheckSquare, 'Tasks'], [Calendar, 'Meetings'], [MessageCircle, 'Messages'],
  [School, 'Programs'], [PenLine, 'Essay Lab'], [Target, 'Applications'],
  [GraduationCap, 'College Search'], [Compass, 'Roadmap'], [ShoppingCart, 'Naseeb Store'],
]

const COUNSELOR_NAV = [
  [LayoutDashboard, 'Home'], [Users, 'Students'], [CheckSquare, 'Tasks'], [Check, 'Review'],
  [Pencil, 'Essays'], [Calendar, 'Meetings'], [MessageCircle, 'Messages'], [Compass, 'Roadmap'],
]

const ROSTER_PILLS = [['All', 9], ['Need you', 3], ['Late work', 2], ['Missing documents', 1], ['On track', 5]]

// tone: late | warn | ok | quiet, the same four the counselor table uses.
const ROSTER = [
  { initials: 'AM', name: 'Abbos Misraliyev', grade: 11, late: 'Essay draft', target: 'China', status: 'Needs you', tone: 'late' },
  { initials: 'AA', name: 'Akbar Alipov', grade: 12, late: null, target: 'USA, UK', status: 'To review', tone: 'warn' },
  { initials: 'AM', name: 'Akmal Mirzayev', grade: 10, late: null, target: 'USA', status: 'On track', tone: 'ok' },
  { initials: 'ES', name: 'Ergashova Shohinur', grade: 11, late: 'Transcript', target: 'Hong Kong', status: 'Needs you', tone: 'late' },
  { initials: 'ED', name: 'Esonboyev Dilyorbek', grade: 12, late: null, target: 'Korea', status: 'On track', tone: 'ok' },
]

export function CounselorDashboardPreview() {
  return (
    <ProductChrome label="Counselor Students page preview: who needs attention, late work, targets and status.">
      <div className="landing-product-layout landing-counselor-ui">
        <PreviewSidebar items={COUNSELOR_NAV} active="Students" locked={['Roadmap']} initials="MC" name="Madina" role="School Counselor" />
        <div className="landing-preview-main">
          <PreviewToolbar title="Students" />
          <div className="landing-preview-page-head">
            <p>{t('Your students and what they need from you')}</p>
            <div className="landing-preview-actions">
              <span><Plus size={13} />{t('Assign task to several')}</span>
              <span className="is-primary"><UserPlus size={13} />{t('Add student')}</span>
            </div>
          </div>
          <div className="landing-preview-pills">
            {ROSTER_PILLS.map(([label, count], index) => (
              <span className={index === 0 ? 'is-active' : ''} key={label}>{t(label)}<b>{count}</b></span>
            ))}
          </div>
          <section className="landing-preview-roster">
            <table>
              <thead><tr>{['Student', 'Late work', 'Target', 'Status'].map((label) => <th key={label}>{t(label)}</th>)}</tr></thead>
              <tbody>{ROSTER.map((student) => (
                <tr key={student.name}>
                  <td><span className="landing-preview-person"><i>{student.initials}</i><span><b>{student.name}</b><small>{t('Grade')} {student.grade}</small></span></span></td>
                  <td>{student.late ? <span className="landing-preview-tone is-late">{student.late}</span> : <span className="landing-preview-faint">{t('No late work')}</span>}</td>
                  <td>{student.target}</td>
                  <td><span className={`landing-preview-tone is-${student.tone}`}>{t(student.status)}</span></td>
                </tr>
              ))}</tbody>
            </table>
          </section>
        </div>
      </div>
    </ProductChrome>
  )
}

export function StudentDashboardPreview() {
  return (
    <ProductChrome label="Student dashboard preview: study goal, meetings, applications and next priorities.">
      <div className="landing-product-layout landing-student-ui">
        <PreviewSidebar items={STUDENT_NAV} active="Dashboard" locked={['Roadmap', 'Naseeb Store']} initials="RE" name="Ramazon Ergashev" role="Student" />
        <div className="landing-preview-main">
          <PreviewToolbar title="Dashboard" />
          <h4 className="landing-preview-greeting">{t('Good evening')}, <b>Ramazon</b></h4>
          <div className="landing-preview-tiles">
            <section className="is-goal">
              <span className="landing-preview-eyebrow"><Target size={12} />{t('Study goal')}</span>
              <h5>Business, Economics</h5>
              <p>US, UK, Vietnam</p>
              <span className="landing-preview-link">{t('Edit study goal')}<ArrowRight size={12} /></span>
            </section>
            <section className="is-meetings">
              <span className="landing-preview-eyebrow"><CalendarClock size={12} />{t('Meetings')}</span>
              <p>{t('Make time for your next step.')}</p>
              <span className="landing-preview-link">{t('Request a meeting')}<ArrowRight size={12} /></span>
            </section>
            <section className="is-apps">
              <span className="landing-preview-eyebrow"><GraduationCap size={12} />{t('Applications')}</span>
              <div className="landing-preview-figure"><strong>2</strong><span>{t('Universities on your list')}</span></div>
              <dl>
                {[['Submitted', 0], ['Essays', 3], ['Accepted', 0], ['Achievements', 2]].map(([label, value]) => (
                  <div key={label}><dd>{value}</dd><dt>{t(label)}</dt></div>
                ))}
              </dl>
            </section>
            <section className="is-discovery">
              <span className="landing-preview-eyebrow">{t('Student discovery tools')}</span>
              {[['Profile Assessment', 'Discover your strengths and study interests.'], ['College Search', 'Compare universities with your goals.']].map(([title, text]) => (
                <div key={title}><b>{t(title)}</b><p>{t(text)}</p><i><ArrowRight size={12} /></i></div>
              ))}
            </section>
          </div>
        </div>
      </div>
    </ProductChrome>
  )
}
