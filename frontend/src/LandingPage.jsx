import { useEffect, useRef, useState } from 'react'
import {
  Building2,
  ChevronRight,
  ClipboardCheck,
  Compass,
  FileText,
  Globe2,
  GraduationCap,
  HeartHandshake,
  Instagram,
  Linkedin,
  MessageSquareText,
  Moon,
  PenLine,
  Presentation,
  Send,
  ShieldCheck,
  Sun,
  UserRoundCheck,
  Youtube,
} from 'lucide-react'

import { LANGUAGE_OPTIONS, formatNumberLocale, t, tx } from './i18n'
import { CounselorDashboardPreview, StudentDashboardPreview } from './LandingDashboardPreviews'
import HeroParticleNetwork from './HeroParticleNetwork'
import './landing.css'

/* ---------------------------------------------------------------------------
   SAMPLE CONTENT — replace every entry below with quotes the customer has
   approved in writing before this page is deployed. The section renders only
   what is in this array: empty it and the whole band, plus its Journey/Stories
   navigation entries, disappear rather than announcing that we have no
   customers yet. Never add a metric, rating or university name here — the
   badge may say a person's role and school and nothing more.
   `name` and `organization` are proper nouns and must never be wrapped in t().
--------------------------------------------------------------------------- */
const CUSTOMER_STORIES = [
  {
    id: 'story-counselor-1',
    quote: 'Every student’s progress, deadlines and submitted work now live in one place. I stopped rebuilding the same spreadsheet every September.',
    name: 'Sample Name',
    initials: 'SN',
    role: 'Counselors',
    organization: 'Sample School',
    featured: true,
  },
  {
    id: 'story-school-1',
    quote: 'We can see how our whole cohort is moving without asking anyone for a status update.',
    name: 'Sample Name',
    initials: 'SN',
    role: 'Schools',
    organization: 'Sample School',
    featured: false,
  },
  {
    id: 'story-student-1',
    quote: 'The roadmap tells me what to do next, and my counselor sees it the moment I submit it.',
    name: 'Sample Name',
    initials: 'SN',
    role: 'Students',
    organization: '',
    featured: false,
  },
  {
    id: 'story-parent-1',
    quote: 'I can follow how my daughter’s application is going without having to ask her about it every evening.',
    name: 'Sample Name',
    initials: 'SN',
    role: 'Parents',
    organization: '',
    featured: false,
  },
]

/* ---------------------------------------------------------------------------
   Universities our students were admitted to. Add an entry only for a real,
   confirmed placement — this strip is a factual claim about our own students,
   not a partner or customer list.

   Each entry needs a logo file at frontend/public/landing/universities/<file>
   (SVG preferred, or a transparent PNG at least 2x the rendered 44px height).
   Use the mark the university publishes on its own brand/identity page, and
   follow that page's usage terms.

   While the array is empty the connected-roles strip stands in its place, so
   the band is never blank and never claims a placement we cannot show.
--------------------------------------------------------------------------- */
const UNIVERSITY_PLACEMENTS = [
  { name: 'Massachusetts Institute of Technology', file: 'mit.svg' },
  { name: 'Northeastern University', file: 'northeastern.svg' },
  { name: 'Boston University', file: 'boston-university.svg' },
  { name: 'University of Chicago', file: 'chicago.svg' },
  { name: 'University of Washington', file: 'washington.svg' },
  { name: 'University of Michigan', file: 'michigan.svg' },
  { name: 'Stanford University', file: 'stanford.svg' },
]

const SCHOOL_CONTACT_URL = (import.meta.env.VITE_SCHOOL_CONTACT_URL || '').trim()
const DEFAULT_BOOK_MEETING_URL = 'https://calendly.com/khumoyunnasipkulov/full-support-asia'
const BOOK_MEETING_URL = (import.meta.env.VITE_BOOK_MEETING_URL || DEFAULT_BOOK_MEETING_URL).trim()
const SOCIAL_LINKS = [
  { label: 'Instagram', href: (import.meta.env.VITE_INSTAGRAM_URL || '').trim(), icon: Instagram },
  { label: 'LinkedIn', href: (import.meta.env.VITE_LINKEDIN_URL || 'https://www.linkedin.com/in/khumoyun-nasipkulov').trim(), icon: Linkedin },
  { label: 'YouTube', href: (import.meta.env.VITE_YOUTUBE_URL || '').trim(), icon: Youtube },
  { label: 'Telegram', href: (import.meta.env.VITE_TELEGRAM_URL || 'https://t.me/naseeb_edu').trim(), icon: Send },
]

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
  const railRef = useRef(null)
  const [activeStory, setActiveStory] = useState(0)
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
  const aboutPrinciples = [
    { title: 'Built for international applications', description: 'Designed for students, counselors and schools navigating universities across borders.' },
    { title: 'Human guidance, supported by software', description: 'The platform organizes progress and evidence; counselors keep every decision personal.' },
    { title: 'From first plan to final offer', description: 'Goals, documents, applications and outcomes stay connected across the whole journey.' },
  ]
  const connectedRoles = [
    { icon: Building2, label: 'Schools' },
    { icon: UserRoundCheck, label: 'Counselors' },
    { icon: GraduationCap, label: 'Students' },
    { icon: Presentation, label: 'Teachers' },
    { icon: HeartHandshake, label: 'Parents' },
    { icon: ShieldCheck, label: 'Admins' },
  ]
  const hasPlacements = UNIVERSITY_PLACEMENTS.length > 0
  const featuredStory = CUSTOMER_STORIES.find((story) => story.featured) || CUSTOMER_STORIES[0]
  const railStories = CUSTOMER_STORIES.filter((story) => story !== featuredStory)
  const hasStories = Boolean(featuredStory)

  const scrollRailTo = (index) => {
    const rail = railRef.current
    const card = rail?.children[index]
    if (!rail || !card) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    rail.scrollTo({ left: card.offsetLeft - rail.offsetLeft, behavior: reduced ? 'auto' : 'smooth' })
  }

  useEffect(() => {
    const page = pageRef.current
    if (!page) return undefined
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const paths = [...page.querySelectorAll('.landing-path-list')]
    const steps = [...page.querySelectorAll('.landing-path-list li')]
    const groups = [...page.querySelectorAll('[data-reveal]')]
    const navLinks = [...page.querySelectorAll('.landing-nav nav a')]
    const navTargets = navLinks.map((link) => page.querySelector(link.getAttribute('href')))
    const rail = railRef.current
    if (!reduced) page.classList.add('is-animated')

    /* Reveals are observed, not scroll-computed. A scroll listener only fires
       when the user scrolls: an instant jump, a restored scroll position, a
       resize that moves a section into view or a stalled frame all leave the
       section stuck at opacity 0 with nothing to un-stick it. That is how the
       dashboards ended up invisible. The observer fires on layout, and if it
       is unavailable everything is revealed outright — content must never be
       hidden by a decoration that might not run. */
    const revealTargets = [...groups, ...paths]
    let observer = null
    if ('IntersectionObserver' in window) {
      observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            /* Already on screen on the observer's first pass: reveal it
               without ever arming it, so above-the-fold copy cannot flash. */
            entry.target.classList.remove('is-armed')
            entry.target.classList.add('is-in')
            observer.unobserve(entry.target)
          } else {
            entry.target.classList.add('is-armed')
          }
        })
      }, { rootMargin: '0px 0px -10% 0px' })
      revealTargets.forEach((target) => observer.observe(target))
    }
    let frame = 0
    let railFrame = 0

    const update = () => {
      frame = 0
      const viewport = window.innerHeight
      page.classList.toggle('is-scrolled', window.scrollY > 24)
      page.classList.toggle('is-compact', window.scrollY > viewport * 0.6)
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
      let current = -1
      navTargets.forEach((section, index) => {
        if (section && section.getBoundingClientRect().top <= viewport * 0.38) current = index
      })
      navLinks.forEach((link, index) => {
        if (index === current) link.setAttribute('aria-current', 'true')
        else link.removeAttribute('aria-current')
      })
    }
    const syncRail = () => {
      railFrame = 0
      if (!rail || !rail.children.length) return
      const step = rail.scrollWidth / rail.children.length
      setActiveStory(Math.min(rail.children.length - 1, Math.round(rail.scrollLeft / step)))
    }
    const onRailScroll = () => {
      if (!railFrame) railFrame = window.requestAnimationFrame(syncRail)
    }
    const onChange = () => {
      if (!frame) frame = window.requestAnimationFrame(update)
    }
    update()
    window.addEventListener('scroll', onChange, { passive: true })
    window.addEventListener('resize', onChange, { passive: true })
    rail?.addEventListener('scroll', onRailScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onChange)
      window.removeEventListener('resize', onChange)
      rail?.removeEventListener('scroll', onRailScroll)
      observer?.disconnect()
      if (frame) window.cancelAnimationFrame(frame)
      if (railFrame) window.cancelAnimationFrame(railFrame)
    }
  }, [])

  return (
    <div className="landing-page" id="landing-top" ref={pageRef}>
      <a className="landing-skip" href="#landing-main">{t('Skip to content')}</a>
      <header className="landing-nav">
        <div className="lp-shell">
          <a href="#landing-top" className="landing-brand" aria-label={t('Naseeb Edu home')}><BrandLockup /></a>
          <nav aria-label={t('Landing navigation')}>
            <a href="#journey">{t('Journey')}</a>
            <a href="#platform">{t('Platform')}</a>
            <a href="#about">{t('About us')}</a>
            {hasStories && <a href="#reviews">{t('Stories')}</a>}
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
          <HeroParticleNetwork theme={theme} />
          <div className="lp-shell landing-hero-grid">
            <div className="landing-hero-copy">
              <p className="lp-eyebrow">{t('For schools, counselors and students in Uzbekistan')}</p>
              <h1><span>{t('The application')}</span> <span>{t('is a long year.')}</span> <em>{t('Hold it together.')}</em></h1>
              <p className="landing-hero-lede">{t('One workspace where a school, a counselor and a student run an international university application together — from the first goal to the final offer.')}</p>
              <div className="landing-hero-actions">
                <a className="landing-primary-cta" href="#journey">{t('See how it works')} <ChevronRight size={17} /></a>
              </div>
            </div>
            <figure className="landing-hero-media">
              <img src="/landing/naseeb-counseling-hero-v2.jpg" alt={t('A student and counselor planning a university application together.')} width="1717" height="916" decoding="async" />
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

        <section className="landing-role-strip" aria-labelledby="connected-roles-title">
          {hasPlacements ? (
            <>
              <p id="connected-roles-title">{t('Our students were admitted to')}</p>
              <ul className="landing-role-accessible">
                {UNIVERSITY_PLACEMENTS.map(({ name }) => <li key={name}>{name}</li>)}
              </ul>
              <div className="landing-role-marquee landing-logo-marquee" aria-hidden="true">
                {[0, 1].map((row) => (
                  <div className={`landing-role-track landing-role-track-${row + 1}`} key={row}>
                    {[...UNIVERSITY_PLACEMENTS, ...UNIVERSITY_PLACEMENTS].map(({ name, file }, index) => (
                      <span key={`${row}-${file}-${index}`}>
                        <img src={`/landing/universities/${file}`} alt="" loading="lazy" decoding="async" />
                      </span>
                    ))}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <>
              <p id="connected-roles-title">{t('One workspace, every role connected')}</p>
              <ul className="landing-role-accessible">
                {connectedRoles.map(({ label }) => <li key={label}>{t(label)}</li>)}
              </ul>
              <div className="landing-role-marquee" aria-hidden="true">
                {[0, 1].map((row) => (
                  <div className={`landing-role-track landing-role-track-${row + 1}`} key={row}>
                    {[...connectedRoles, ...connectedRoles].map(({ icon: Icon, label }, index) => (
                      <span key={`${row}-${label}-${index}`}><Icon size={27} aria-hidden="true" />{t(label)}</span>
                    ))}
                  </div>
                ))}
              </div>
            </>
          )}
        </section>

        <section className="landing-band landing-journey" id="journey">
          <div className="lp-shell">
            <div className="landing-journey-grid">
            <div className="landing-section-head" data-reveal>
              <h2>{t('Four steps, in order.')}</h2>
              <p>{t('The application journey moves through four clear stages.')}</p>
            </div>
            <ol className="landing-path-list">
              {path.map((step) => <li key={step.title}><h3>{t(step.title)}</h3><p>{t(step.description)}</p></li>)}
            </ol>
            <figure className="landing-specimen">
              <figcaption>{t('Step 3')} · {t('Applications')}</figcaption>
              <p>{t('Build a balanced university shortlist')}</p>
              <div><span className="landing-specimen-status">{t('Submitted for approval')}</span><b>{tx`+${formatNumberLocale(75)} XP`}</b></div>
              <small>{t('The next step stays locked until a counselor approves this one. XP counts toward the student’s level.')}</small>
            </figure>
            </div>
            <div className="landing-product-showcase landing-student-showcase" data-reveal>
              <div className="landing-showcase-copy">
                <p className="lp-eyebrow">{t('For students')}</p>
                <h3>{t('Know what comes next.')}</h3>
              </div>
              <p className="landing-showcase-note">{t('Follow your roadmap, prepare each application and ask for help before a deadline becomes a problem.')}</p>
              <StudentDashboardPreview />
            </div>
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
            <div className="landing-product-showcase landing-counselor-showcase" data-reveal>
              <div className="landing-showcase-copy">
                <p className="lp-eyebrow">{t('For counselors')}</p>
                <h3>{t('Every student, one clear view.')}</h3>
              </div>
              <p className="landing-showcase-note">{t('See progress, deadlines and submitted work without losing the person behind the application.')}</p>
              <CounselorDashboardPreview />
            </div>
          </div>
        </section>

        <section className="landing-band landing-about" id="about">
          <div className="lp-shell landing-about-grid">
            <header className="landing-about-head" data-reveal>
              <p className="lp-eyebrow">{t('About Naseeb Edu')}</p>
              <h2>{t('Guidance works better when everyone works from the same record.')}</h2>
              <p>{t('Naseeb Edu is an education counseling platform built for schools, counselors, students and families navigating international university applications from Uzbekistan.')}</p>
            </header>
            <dl className="landing-about-principles" data-reveal>
              {aboutPrinciples.map((item, index) => (
                <div key={item.title}>
                  <span aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
                  <dt>{t(item.title)}</dt>
                  <dd>{t(item.description)}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {hasStories && (
          <section className="landing-band landing-reviews" id="reviews">
            <div className="lp-shell">
              <header className="landing-reviews-head" data-reveal>
                <p className="lp-eyebrow">{t('Customer stories')}</p>
                <div>
                  <h2>{t('What our customers say')}</h2>
                  <p>{t('Words from the schools and counselors who use Naseeb Edu.')}</p>
                </div>
              </header>

              <figure className="landing-story-lead" data-reveal>
                <blockquote>{t(featuredStory.quote)}</blockquote>
                <figcaption className="landing-story-byline">
                  <span className="landing-story-who">
                    <span className="landing-story-avatar" aria-hidden="true">{featuredStory.initials}</span>
                    <span>
                      <b>{featuredStory.name}</b>
                      <small>{t(featuredStory.role)}{featuredStory.organization ? ` · ${featuredStory.organization}` : ''}</small>
                    </span>
                  </span>
                </figcaption>
              </figure>
            </div>

            {railStories.length > 0 && (
              <>
                <ul className="landing-story-rail" role="group" aria-label={t('Customer stories')} ref={railRef}>
                  {railStories.map((story) => (
                    <li className="landing-story-card" key={story.id}>
                      <span className="landing-story-badge">
                        {t(story.role)}{story.organization ? ` · ${story.organization}` : ''}
                      </span>
                      <blockquote>{t(story.quote)}</blockquote>
                      <footer>
                        <span className="landing-story-avatar" aria-hidden="true">{story.initials}</span>
                        <span><b>{story.name}</b><small>{t(story.role)}</small></span>
                      </footer>
                    </li>
                  ))}
                </ul>
                {railStories.length > 1 && (
                  <div className="landing-story-dots">
                    {railStories.map((story, index) => (
                      <button
                        type="button"
                        key={story.id}
                        aria-label={tx`Story ${index + 1} of ${railStories.length}`}
                        aria-current={index === activeStory}
                        onClick={() => scrollRailTo(index)}
                      />
                    ))}
                  </div>
                )}
              </>
            )}
          </section>
        )}

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

        <section className="landing-closing">
          <div className="lp-shell" data-reveal>
            <h2>{t('Bring every application into one clear workspace.')}</h2>
            <p>{t('Give counselors and students one shared place to plan, review and move forward.')}</p>
            <div className="landing-closing-actions">
              {BOOK_MEETING_URL ? (
                <a className="landing-primary-cta" href={BOOK_MEETING_URL}>{t('Book a call')} <ChevronRight size={17} /></a>
              ) : (
                <button type="button" className="landing-primary-cta" disabled>{t('Book a call')} <ChevronRight size={17} /></button>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <a className="landing-footer-emblem" href="#landing-top" aria-label={t('Back to top')} title={t('Back to top')}><BrandLogo /></a>
        <div className={`lp-shell landing-footer-grid ${SCHOOL_CONTACT_URL ? 'has-access' : ''}`}>
          <div className="landing-footer-brand">
            <BrandLockup />
            <nav className="landing-social-links" aria-label={t('Social media')}>
              {SOCIAL_LINKS.map(({ label, href, icon: Icon }) => (
                href ? (
                  <a key={label} href={href} target="_blank" rel="noreferrer" aria-label={label} title={label}>
                    <Icon size={18} aria-hidden="true" />
                  </a>
                ) : (
                  <span key={label} aria-disabled="true" aria-label={`${label} — ${t('link coming soon')}`} title={`${label} — ${t('link coming soon')}`}>
                    <Icon size={18} aria-hidden="true" />
                  </span>
                )
              ))}
            </nav>
          </div>
          <nav className="landing-footer-links" aria-label={t('Footer navigation')}>
            <span>{t('Explore')}</span>
            <a href="#journey">{t('Journey')}</a>
            <a href="#platform">{t('Platform')}</a>
            <a href="#about">{t('About us')}</a>
            {hasStories && <a href="#reviews">{t('Stories')}</a>}
            <a href="#trust">{t('Trust')}</a>
          </nav>
          {SCHOOL_CONTACT_URL && (
            <nav className="landing-footer-links" aria-label={t('Access links')}>
              <span>{t('Access')}</span>
              <a href={SCHOOL_CONTACT_URL}>{t('Contact')}</a>
            </nav>
          )}
          <small>© {new Date().getFullYear()} Naseeb Edu. {t('All rights reserved.')}</small>
        </div>
      </footer>
    </div>
  )
}
