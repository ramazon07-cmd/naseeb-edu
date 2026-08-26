import { useEffect, useRef } from 'react'
import {
  ChevronRight,
  ClipboardCheck,
  Compass,
  FileText,
  Fingerprint,
  Globe2,
  GraduationCap,
  MessageSquareText,
  Moon,
  PenLine,
  Sun,
} from 'lucide-react'

import { LANGUAGE_OPTIONS, formatNumberLocale, t, tx } from './i18n'
import { ReachMapSection } from './components/ReachMapSection'
import './landing.css'

const SCHOOL_CONTACT_URL = (import.meta.env.VITE_SCHOOL_CONTACT_URL || '').trim()

function BrandLogo({ className = '' }) {
  return <span className={`brand-logo ${className}`} role="img" aria-label={t('Naseeb Edu')} />
}

function BrandLockup() {
  return (
    <div className="brand-lockup">
      <BrandLogo />
      <div>
        <b>{t('Naseeb Edu')}</b>
        <small>{t('Education Counseling Platform')}</small>
      </div>
    </div>
  )
}

function LanguageSelector({ language, onChange }) {
  return (
    <label className="language-selector compact" aria-label={t('Language')}>
      <Globe2 size={15} />
      <select value={language} onChange={(event) => onChange(event.target.value)}>
        {LANGUAGE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>{option.short}</option>
        ))}
      </select>
    </label>
  )
}

function ThemeToggle({ theme, onToggle }) {
  const isDark = theme === 'dark'
  return (
    <button
      type="button"
      className="icon-button theme-toggle"
      onClick={onToggle}
      title={isDark ? t('Light mode') : t('Dark mode')}
      aria-label={isDark ? t('Switch to light mode') : t('Switch to dark mode')}
      aria-pressed={isDark}
    >
      {isDark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  )
}

export default function LandingPage({ onLogin, theme, toggleTheme, language, changeLanguage }) {
  const pageRef = useRef(null)
  const path = [
    { title: 'Set the direction', description: 'Turn a student’s goals into a focused university and scholarship strategy.' },
    { title: 'Build the profile', description: 'Academics, activities, honors and documents collected in one verified profile.' },
    { title: 'Prepare applications', description: 'Tasks, essays, recommendations and deadlines, each with a clear owner.' },
    { title: 'Make the decision', description: 'Compare offers, funding and fit, then commit to the right final choice.' },
  ]
  const capabilities = [
    { icon: Compass, title: 'Roadmap', description: 'Level-linked missions a teacher or counselor approves, so progress is earned rather than claimed.', note: 'Staff approved' },
    { icon: GraduationCap, title: 'College Search', description: 'Universities ranked against the student’s real GPA, SAT, IELTS, budget and scholarship needs.', note: 'Profile driven' },
    { icon: PenLine, title: 'Essay Lab', description: 'Drafts, revision history and counselor feedback stay with the application they belong to.', note: 'Versioned' },
    { icon: FileText, title: 'Documents', description: 'Transcripts, certificates and evidence stream through authenticated links, never public URLs.', note: 'Private storage' },
    { icon: MessageSquareText, title: 'Messaging', description: 'Direct, group and school channels, with moderation and reporting built in.', note: 'Moderated' },
    { icon: ClipboardCheck, title: 'Student 360', description: 'One reviewable view per student for staff — with private notes and drafts deliberately excluded.', note: 'Audited' },
  ]
  const ledger = [
    { figure: 6, label: 'Roles', description: 'Admin, counselor, teacher, school, student and parent — each with its own data scope.' },
    { figure: 3, label: 'Languages', description: 'Uzbek, Russian and English across the whole product, not just the marketing page.' },
    { figure: 0, label: 'Public sign-ups', description: 'Accounts are issued by a school or counselor. Nobody can register their way into student data.' },
  ]
  const governance = [
    { title: 'Approved, not asserted', description: 'Progress counts only once a teacher or counselor has approved the evidence behind it. Nobody marks their own work complete.' },
    { title: 'Scoped by role', description: 'A counselor sees the students assigned to them, a school sees its own, and a parent sees only the sections consent allows.' },
    { title: 'Private by default', description: 'Messages, counselor notes, essay drafts and task submissions stay out of staff overviews unless policy puts them there.' },
  ]

  useEffect(() => {
    const page = pageRef.current
    if (!page) return undefined
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const paths = [...page.querySelectorAll('.landing-path-list')]
    const steps = [...page.querySelectorAll('.landing-path-list li')]
    const groups = reduced ? [] : [...page.querySelectorAll('[data-reveal]')]
    if (!reduced) page.classList.add('is-animated')
    let frame = 0

    const update = () => {
      frame = 0
      const viewport = window.innerHeight
      page.classList.toggle('is-scrolled', window.scrollY > 8)
      page.classList.toggle('is-compact', window.scrollY > viewport * 0.6)
      groups.forEach((group) => group.classList.toggle('is-in', group.getBoundingClientRect().top < viewport * 0.88))
      paths.forEach((list) => list.classList.toggle('is-in', list.getBoundingClientRect().top < viewport * 0.92))
      if (steps.length) {
        let nearest = 0
        let shortestDistance = Infinity
        steps.forEach((step, index) => {
          const distance = Math.abs(step.getBoundingClientRect().top - viewport * 0.38)
          if (distance < shortestDistance) {
            nearest = index
            shortestDistance = distance
          }
        })
        steps.forEach((step, index) => step.classList.toggle('is-active', index === nearest))
      }
    }
    const onChange = () => {
      if (!frame) frame = window.requestAnimationFrame(update)
    }
    update()
    window.addEventListener('scroll', onChange, { passive: true })
    window.addEventListener('resize', onChange, { passive: true })
    return () => {
      window.removeEventListener('scroll', onChange)
      window.removeEventListener('resize', onChange)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [])

  return (
    <div className="landing-page" id="landing-top" ref={pageRef}>
      <a className="landing-skip" href="#landing-main">{t('Skip to content')}</a>
      <header className="landing-nav">
        <div className="lp-shell">
          <a href="#landing-top" className="landing-brand" aria-label={t('Naseeb Edu home')}><BrandLockup /></a>
          <nav aria-label={t('Landing navigation')}>
            <a href="#reach">{t('Reach')}</a>
            <a href="#journey">{t('Journey')}</a>
            <a href="#platform">{t('Platform')}</a>
            <a href="#trust">{t('Trust')}</a>
          </nav>
          <div className="landing-nav-actions">
            <LanguageSelector language={language} onChange={changeLanguage} />
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
              <h1><span>{t('The application')}</span> <span>{t('is a long year.')}</span> <em>{t('Hold it together.')}</em></h1>
              <p className="landing-hero-lede">{t('One workspace where a school, a counselor and a student run an international university application together — from the first goal to the final offer.')}</p>
              <div className="landing-hero-actions">
                <a className="landing-primary-cta" href="#journey">{t('See how it works')} <ChevronRight size={17} /></a>
                {SCHOOL_CONTACT_URL ? (
                  <a className="landing-text-cta" href={SCHOOL_CONTACT_URL}>{t('Bring Naseeb Edu to your school')} <ChevronRight size={15} /></a>
                ) : (
                  <button type="button" className="landing-text-cta" onClick={onLogin}>{t('Sign in')} <ChevronRight size={15} /></button>
                )}
              </div>
              <p className="landing-access-note"><Fingerprint size={15} /> {t('Students receive a temporary login from their school or counselor. There is no public sign-up.')}</p>
            </div>
            <figure className="landing-hero-media">
              <img src="/landing/naseeb-counseling-hero.jpg" alt={t('A student and counselor planning a university application together.')} width="1600" height="853" decoding="async" />
            </figure>
          </div>
          <div className="landing-rail">
            <div className="lp-shell">
              {ledger.map((item) => (
                <article key={item.label}>
                  <b>{formatNumberLocale(item.figure)}</b>
                  <span>{t(item.label)}</span>
                  <small>{t(item.description)}</small>
                </article>
              ))}
            </div>
          </div>
        </section>

        <ReachMapSection theme={theme} />

        <section className="landing-band landing-journey" id="journey">
          <div className="lp-shell">
            <div className="landing-section-head" data-reveal>
              <h2>{t('Four steps, in order.')}</h2>
              <p>{t('Each step unlocks the next only after a counselor approves the work behind it.')}</p>
              <figure className="landing-specimen">
                <figcaption>{t('Step 3')} · {t('Applications')}</figcaption>
                <p>{t('Build a balanced university shortlist')}</p>
                <div><span className="landing-specimen-status">{t('Submitted for approval')}</span><b>{tx`+${formatNumberLocale(75)} XP`}</b></div>
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
              {capabilities.map(({ icon: Icon, title, description, note }) => (
                <article className="landing-capability" key={title}>
                  <Icon size={19} aria-hidden="true" />
                  <h3>{t(title)}</h3>
                  <p>{t(description)}</p>
                  <span className="landing-capability-note">{t(note)}</span>
                </article>
              ))}
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
              {governance.map((item) => <div key={item.title}><dt>{t(item.title)}</dt><dd>{t(item.description)}</dd></div>)}
            </dl>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="lp-shell">
          <small>© {new Date().getFullYear()} Naseeb Edu</small>
          <a className="landing-footer-mark" href="#landing-top" aria-label={t('Back to top')} title={t('Back to top')}><BrandLockup /></a>
          <nav className="landing-footer-links" aria-label={t('Footer navigation')}>
            <a href="#reach">{t('Reach')}</a>
            <a href="#journey">{t('Journey')}</a>
            <a href="#platform">{t('Platform')}</a>
            <a href="#trust">{t('Trust')}</a>
            {SCHOOL_CONTACT_URL && <a href={SCHOOL_CONTACT_URL}>{t('Contact')}</a>}
          </nav>
        </div>
      </footer>
    </div>
  )
}
