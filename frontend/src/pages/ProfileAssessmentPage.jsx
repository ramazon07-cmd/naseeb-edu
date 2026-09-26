import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, BrainCircuit, Check, CheckCircle2, ChevronRight, CloudOff, Fingerprint, Hexagon, Lock, RefreshCw, Sparkles } from 'lucide-react';
import { api } from '../api';
import { t } from '../i18n';
import { Panel } from '../components/ui';
import { ownStudent } from '../lib/labels';
import { USER_STORAGE, userStorageKey } from '../userStorage';
import {
  assessmentLockReason, isRetryableSaveError, loadPendingAttempts, mergeServerAnswers, saveRetryDelay, storePendingAttempts } from
'../lib/assessmentSync';
import {
  CHALLENGES, RIASEC_NAME, RIASEC_ORDER,
  INSTRUMENT_VERSION, SUBJECT_NAME, TRAIT_LABEL, TRAIT_ORDER,
  scoreChallenge } from
'../challenges';
import {
  MAJOR_ENTRIES, NAMES, recRank, recSignals, subjectPerformance } from
'../careers';

// One challenge per instrument: personality, interests, subjects, and the
// public-domain ICAR-16 cognitive assessment. Each
// bank has its own response scale and its own scoring, and a challenge is only
// scored once its whole instrument is answered -- half an inventory is not a
// result. Fifty questions at once is a wall, so a challenge is paged.
const FP_PAGE_SIZE = 10

function loadChallengeAnswers(storageKey) {
  try {
    const saved = JSON.parse(window.localStorage.getItem(storageKey) || '{}')
    return saved && typeof saved === 'object' ? saved : {}
  } catch { return {} }
}

// The Work Importance Locator is a card sort: exactly four cards in each of five
// columns. The constraint IS the instrument -- allowing everything to be "most
// important" would flatten the ranking it exists to produce -- so a level stops
// accepting cards once it holds four.
function SortRunner({ challenge, answers, onAnswer, onFinish, onBack }) {
  const perColumn = [1, 2, 3, 4, 5].map((level) => challenge.items.filter((item) => answers[item.id] === level).length)
  const placed = perColumn.reduce((a, b) => a + b, 0)
  const legal = perColumn.every((n) => n === challenge.perColumn)
  return <div className="section-stack student-portal">
    <section className="portal-hero"><div><span className="eyebrow">CHALLENGE {challenge.number} · {challenge.instrument}</span><h2>{challenge.title}</h2><p>{challenge.blurb}</p></div><Fingerprint size={64} /></section>
    <Panel title={`${placed} of ${challenge.items.length} placed`} action={<button className="button quiet small" onClick={onBack}>Back to challenges</button>}>
      <div className="sort-tally">{challenge.scale.map((label, index) => <div key={label} className={perColumn[index] === challenge.perColumn ? 'full' : ''}>
        <b>{perColumn[index]}/{challenge.perColumn}</b><span>{label}</span>
      </div>)}</div>
      <div className="challenge-items">{challenge.items.map((item) => <fieldset key={item.id} className={answers[item.id] ? 'answered' : ''}>
        <legend>{item.text}</legend>
        <div className="challenge-scale">
          <span className="scale-pole left">{challenge.scale[0]}</span>
          <div className="scale-dots">{challenge.scale.map((label, position) => {
            const level = position + 1
            const chosen = answers[item.id] === level
            const full = perColumn[position] >= challenge.perColumn && !chosen
            return <label key={label} className={`scale-opt s${level}${chosen ? ' sel' : ''}${full ? ' full' : ''}`} title={full ? `${label} is already full` : label}>
              <input type="radio" name={`item-${item.id}`} checked={chosen} disabled={full} aria-label={label} onChange={() => onAnswer(item.id, level)} />
              <span className="scale-dot" aria-hidden="true" />
            </label>
          })}</div>
          <span className="scale-pole right">{challenge.scale[challenge.scale.length - 1]}</span>
        </div>
      </fieldset>)}</div>
      <div className="challenge-actions">
        <button className="button primary" disabled={!legal} onClick={onFinish}>{legal ? 'Finish challenge' : `Put exactly ${challenge.perColumn} in every level`}<ChevronRight size={17} /></button>
      </div>
    </Panel>
  </div>
}

function ReasoningRunner({ challenge, answers, onAnswer, onFinish, onBack }) {
  const [page, setPage] = useState(0)
  const pageSize = challenge.pageSize || 4
  const pages = Math.ceil(challenge.items.length / pageSize)
  const slice = challenge.items.slice(page * pageSize, (page + 1) * pageSize)
  const answered = challenge.items.filter((item) => answers[item.id]).length
  const pageDone = slice.every((item) => answers[item.id])
  const last = page === pages - 1
  const complete = answered === challenge.items.length

  return <div className="section-stack student-portal reasoning-runner">
    <section className="portal-hero"><div><span className="eyebrow">{t('CHALLENGE')} {challenge.number} · {challenge.instrument}</span><h2>{t(challenge.title)}</h2><p>{t(challenge.blurb)}</p></div><BrainCircuit size={64} /></section>
    <Panel title={t('{answered} of {total} answered', { answered, total: challenge.items.length })} action={<button className="button quiet small" onClick={onBack}>{t('Back to challenges')}</button>}>
      <div className="challenge-progress"><div className="progress wide"><span style={{ width: `${(answered / challenge.items.length) * 100}%` }} /></div><small>{t('Round {page} of {total}', { page: page + 1, total: pages })}</small></div>
      <p className="reasoning-note"><BrainCircuit size={17} /> {t('ICAR-16 is a public-domain cognitive assessment. Complete it without a calculator or outside help for the most useful result.')}</p>
      <div className="reasoning-items">{slice.map((item, index) => <fieldset key={item.id} className={answers[item.id] ? 'answered' : ''}>
        <legend><span>{String(page * pageSize + index + 1).padStart(2, '0')}</span>{t(item.text)}</legend>
        {item.image && <img className="reasoning-item-image" src={item.image} alt={t(item.imageAlt)} />}
        <div className={`reasoning-options${item.image ? ' visual' : ''}`}>{item.options.map((option, position) => {
          const value = position + 1
          const chosen = answers[item.id] === value
          return <label key={option} className={chosen ? 'selected' : ''}>
            <input type="radio" name={`item-${item.id}`} checked={chosen} onChange={() => onAnswer(item.id, value)} />
            <span>{String.fromCharCode(65 + position)}</span><b>{t(option)}</b>{chosen && <Check size={16} />}
          </label>
        })}</div>
      </fieldset>)}</div>
      <div className="challenge-actions">
        {page > 0 && <button className="button quiet" onClick={() => { setPage(page - 1); window.scrollTo(0, 0) }}>{t('Back')}</button>}
        {last
          ? <button className="button primary" disabled={!complete} onClick={onFinish}>{complete ? t('See my cognitive score') : t('Answer every question to finish')}<ChevronRight size={17} /></button>
          : <button className="button primary" disabled={!pageDone} onClick={() => { setPage(page + 1); window.scrollTo(0, 0) }}>{pageDone ? t('Next round') : t('Answer these to continue')}<ChevronRight size={17} /></button>}
      </div>
    </Panel>
  </div>
}

// On a bipolar challenge every item carries its own two ends, so the poles come
// from the item rather than from one scale shared by the whole bank.
const poleText = (challenge, item) => challenge.bipolar
  ? item.poles
  : [challenge.scale[0], challenge.scale[challenge.scale.length - 1]]

// What a screen reader hears on each circle. A bipolar item has no wording of
// its own for the middle three, so they are described by which end they lean
// toward -- "3 of 5" alone would be a number with nothing attached to it.
function optionLabel(challenge, item, position) {
  if (!challenge.bipolar) return t(challenge.scale[position])
  const [left, right] = item.poles
  if (position === 0) return left
  if (position === 4) return right
  if (position === 2) return 'In between'
  return position === 1 ? `Closer to “${left}”` : `Closer to “${right}”`
}

function ChallengeRunner({ challenge, answers, onAnswer, onFinish, onBack }) {
  if (challenge.interaction === 'sort') return <SortRunner {...{ challenge, answers, onAnswer, onFinish, onBack }} />
  if (challenge.interaction === 'quiz') return <ReasoningRunner {...{ challenge, answers, onAnswer, onFinish, onBack }} />
  return <RatingRunner {...{ challenge, answers, onAnswer, onFinish, onBack }} />
}

function RatingRunner({ challenge, answers, onAnswer, onFinish, onBack }) {
  const [page, setPage] = useState(0)
  const pages = Math.ceil(challenge.items.length / FP_PAGE_SIZE)
  const slice = challenge.items.slice(page * FP_PAGE_SIZE, (page + 1) * FP_PAGE_SIZE)
  const answered = challenge.items.filter((item) => answers[item.id]).length
  const pageDone = slice.every((item) => answers[item.id])
  const last = page === pages - 1
  const complete = answered === challenge.items.length
  const listRef = useRef(null)

  // Auto-advance, copied rule for rule from TestMind.
  //
  //  - POINTER ONLY. Chrome fires a synthetic click for arrow-key selection, and
  //    those report detail 0. Advancing on an arrow press would carry the student
  //    past the option they were still travelling towards.
  //  - ONLY FROM THE CURRENT QUESTION. Going back to change an earlier answer
  //    must not fling the page forward; that is the student re-reading, not
  //    progressing.
  //  - THE NEXT ROW LANDS WHERE THE LAST ONE WAS. Every row has identical
  //    geometry, so matching the row of circles means the pointer is already on
  //    the next question and never has to travel.
  const advanceFrom = useCallback((itemId) => {
    const list = listRef.current
    if (!list) return
    const sets = Array.from(list.querySelectorAll('fieldset'))
    const fromIndex = sets.findIndex((f) => f.querySelector(`input[name="item-${itemId}"]`))
    if (fromIndex < 0) return
    // Only the question they were on. Anything earlier still unanswered means
    // they skipped back, and we leave the scroll where they put it.
    if (sets.slice(0, fromIndex).some((f) => !f.querySelector('input:checked'))) return
    const anchorRow = sets[fromIndex].querySelector('.scale-dots')
    const anchor = anchorRow ? anchorRow.getBoundingClientRect() : null
    const anchorMid = anchor ? anchor.top + anchor.height / 2 : null

    // After the re-render, so "unanswered" reflects the answer just given.
    requestAnimationFrame(() => {
      const fresh = Array.from(list.querySelectorAll('fieldset'))
      const next = fresh.slice(fromIndex + 1).find((f) => !f.querySelector('input:checked'))
      const smooth = !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      const behavior = smooth ? 'smooth' : 'auto'
      if (!next) {
        // Page finished. Bring the button that continues into view rather than
        // leaving them at the bottom of a page with nothing obvious to do.
        list.parentElement?.querySelector('.challenge-actions')
          ?.scrollIntoView({ behavior, block: 'center' })
        return
      }
      next.querySelector('input[type=radio]')?.focus({ preventScroll: true })
      const nextRow = next.querySelector('.scale-dots')
      if (anchorMid !== null && nextRow) {
        const r = nextRow.getBoundingClientRect()
        window.scrollBy({ top: (r.top + r.height / 2) - anchorMid, behavior })
      } else {
        next.scrollIntoView({ behavior, block: 'center' })
      }
    })
  }, [])

  return <div className="section-stack student-portal">
    <section className="portal-hero"><div><span className="eyebrow">{t('CHALLENGE')} {challenge.number} · {challenge.instrument}</span><h2>{t(challenge.title)}</h2><p>{t(challenge.blurb)}</p></div><Fingerprint size={64} /></section>
    <Panel title={t('{answered} of {total} answered', { answered, total: challenge.items.length })} action={<button className="button quiet small" onClick={onBack}>{t('Back to challenges')}</button>}>
      <div className="challenge-progress"><div className="progress wide"><span style={{ width: `${(answered / challenge.items.length) * 100}%` }} /></div><small>{t('Page {page} of {total}', { page: page + 1, total: pages })}</small></div>
      {/* A challenge whose items carry a section shows it at the top of every page
          and again wherever the block changes mid-page. Without it, a student who
          turns the page into "…makes me anxious" has no idea they are being asked
          a different question about the same eleven subjects.

          The heading is a SIBLING of the fieldset, not a child: an answered
          fieldset drops to .45 opacity, and opacity applies to the whole subtree,
          so a heading inside it would fade exactly when someone scrolls back to
          ask what this block was. */}
      <div className="challenge-items" ref={listRef}>{slice.flatMap((item, index) => [
        item.section && (index === 0 || item.section !== slice[index - 1].section)
          ? <p key={`s-${item.id}`} className="challenge-section"><span className="eyebrow">{t(item.section)}</span></p>
          : null,
        <fieldset key={item.id} className={answers[item.id] ? 'answered' : ''}>
        <legend className={challenge.bipolar ? 'sr-only' : undefined}>{t(item.text)}</legend>
        <div className="challenge-scale">
          <span className="scale-pole left" aria-hidden={challenge.bipolar || undefined}>{t(poleText(challenge, item)[0])}</span>
          <div className="scale-dots">{challenge.scale.map((scaleLabel, position) => {
            const chosen = answers[item.id] === position + 1
            const label = optionLabel(challenge, item, position)
            return <label key={scaleLabel} className={`scale-opt s${position + 1}${chosen ? ' sel' : ''}`} title={label}>
              <input
                type="radio"
                name={`item-${item.id}`}
                checked={chosen}
                aria-label={label}
                onChange={() => onAnswer(item.id, position + 1)}
                // detail is 0 for a keyboard-generated click, so this fires only
                // on a real tap. onChange above still records arrow-key answers.
                onClick={(event) => { if (event.detail > 0) advanceFrom(item.id) }}
              />
              <span className="scale-dot" aria-hidden="true" />
            </label>
          })}</div>
          <span className="scale-pole right" aria-hidden={challenge.bipolar || undefined}>{t(poleText(challenge, item)[1])}</span>
        </div>
      </fieldset>,
      ].filter(Boolean))}</div>
      <div className="challenge-actions">
        {page > 0 && <button className="button quiet" onClick={() => { setPage(page - 1); window.scrollTo(0, 0) }}>{t('Back')}</button>}
        {last
          ? <button className="button primary" disabled={!complete} onClick={onFinish}>{complete ? t('Finish challenge') : t('Answer every question to finish')}<ChevronRight size={17} /></button>
          : <button className="button primary" disabled={!pageDone} onClick={() => { setPage(page + 1); window.scrollTo(0, 0) }}>{pageDone ? t('Next') : t('Answer these to continue')}<ChevronRight size={17} /></button>}
      </div>
    </Panel>
  </div>
}

// Ten items per trait cannot separate a 3.2 from a 3.4, so the wording stays
// banded. No trait direction is described as the better one.

// A profile shape: pentagon for the five traits, hexagon for the six interest
// scales, and so on -- the polygon takes as many sides as the instrument has
// scales, so each challenge has a recognisably different silhouette.
//
// Only used up to six axes. Past that the labels crowd the corners and the shape
// stops being readable, so values (10) and subjects (11) stay as bars -- which is
// also what the more-than-seven-classes rule says.
//
// Two things this shape gets wrong if you let it, and the guards against them:
//  - AREA LIES. A radius twice as long draws four times the area, so a middling
//    profile can look dramatic. Guarded by drawing the fill faint and the outline
//    thin, keeping every ring visible so the scale is readable, and always
//    shipping the numbers underneath rather than instead.
//  - THE ORDER SHAPES THE SHAPE. Reordering the axes changes the silhouette
//    without changing the data. For interests that order is not arbitrary -- it
//    is Holland's own hexagon, where neighbours are the most alike -- but for the
//    Big Five it IS arbitrary, so the shape is a picture of the profile and never
//    evidence about it.

function ProfilePolygon({ axes, caption }) {
  const [hover, setHover] = useState(null)
  // Wider than tall on purpose: the left and right labels sit outside the shape
  // and need room, and without it they overflow into whatever is beside the
  // chart. Sized so the longest label fits inside the viewBox rather than
  // relying on overflow.
  const W = 360, H = 268
  const cx = W / 2, cy = H / 2
  const rMax = 84
  const rings = [0.25, 0.5, 0.75, 1]

  // Straight up for the first axis, then clockwise.
  const pointAt = (index, t) => {
    const angle = (Math.PI * 2 * index) / axes.length - Math.PI / 2
    return [cx + Math.cos(angle) * rMax * t, cy + Math.sin(angle) * rMax * t]
  }
  const ringPath = (t) => axes.map((_, i) => pointAt(i, t).map((n) => n.toFixed(1)).join(',')).join(' ')
  // 1..5 onto 0..1, so the centre is "lowest" rather than "none".
  const norm = (value) => Math.max(0, Math.min(1, (value - 1) / 4))
  const shape = axes.map((axis, i) => pointAt(i, norm(axis.value)).map((n) => n.toFixed(1)).join(',')).join(' ')

  return <figure className="profile-polygon">
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={caption}>
      {rings.map((t) => <polygon key={t} className="ring" points={ringPath(t)} />)}
      {axes.map((_, i) => {
        const [x, y] = pointAt(i, 1)
        return <line key={i} className="spoke" x1={cx} y1={cy} x2={x} y2={y} />
      })}
      <polygon className="shape" points={shape} />
      {axes.map((axis, i) => {
        const [x, y] = pointAt(i, norm(axis.value))
        const [lx, ly] = pointAt(i, 1.22)
        const anchor = Math.abs(lx - cx) < 6 ? 'middle' : lx > cx ? 'start' : 'end'
        return <g key={axis.key}>
          <circle
            className={`vertex ${hover === axis.key ? 'on' : ''}`} cx={x} cy={y} r={hover === axis.key ? 6 : 4.5}
            onMouseEnter={() => setHover(axis.key)} onMouseLeave={() => setHover(null)}
          />
          <text className="axis-label" x={lx} y={ly} textAnchor={anchor} dominantBaseline="middle">
            {axis.short || axis.label}
          </text>
        </g>
      })}
    </svg>
    <figcaption>{hover
      ? <><strong>{axes.find((a) => a.key === hover).label}</strong> — {axes.find((a) => a.key === hover).value.toFixed(1)} of 5</>
      : caption}</figcaption>
  </figure>
}

// Major guidance starts once interests are complete. Personality and subjects
// sharpen the deterministic ranking; AI explains that shortlist but does not
// choose universities in this release.
const LOCK_TEXT = {
  incomplete: ['Complete all four challenges to unlock your recommendations.', 'Profile incomplete'],
  loading: ['Checking the results saved to your account…', 'Checking'],
  pending: ['Your results are still being saved. Recommendations unlock once your account has them.', 'Not saved yet'],
  unsynced: ['Your account doesn’t have all four results yet. Load your saved results to unlock recommendations.', 'Not saved yet'],
}

function AIEducationGuidance({ majors, subjects, lockReason, student, reload, notify }) {
  const locked = Boolean(lockReason)
  const lockText = LOCK_TEXT[lockReason] || LOCK_TEXT.incomplete
  const [guidance, setGuidance] = useState(null)
  const [selectedMajor, setSelectedMajor] = useState(student?.target_major || '')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function generate() {
    if (locked) return
    setLoading(true)
    setError('')
    try {
      const nextGuidance = await api.educationMatchAI({ major_candidates: majors, subject_strengths: subjects })
      setGuidance(nextGuidance)
      setSelectedMajor('')
    } catch (requestError) {
      setError(requestError.message || t('AI guidance is unavailable right now.'))
    } finally {
      setLoading(false)
    }
  }

  async function confirmMajor() {
    if (!selectedMajor || !student) return
    setSaving(true)
    setError('')
    try {
      await api.update('students', student.id, { target_major: selectedMajor })
      notify?.(t('{major} saved as your current study direction.', { major: selectedMajor }))
      reload?.()
    } catch (requestError) {
      setError(requestError.message || t('We could not save your selected major.'))
    } finally {
      setSaving(false)
    }
  }

  const topFits = guidance?.major_guidance?.slice(0, 3) || []

  return <section id="assessment-ai-panel" className={`assessment-ai-panel ${locked ? 'locked' : ''}`}>
    <div className="assessment-ai-orbit" aria-hidden="true"><span className="assessment-ai-orbit-mark" /></div>
    <span className="eyebrow">{t('AI MAJOR MATCH')}</span>
    <h3>{guidance ? t('Choose your strongest fit') : t("Now let's find your direction")}</h3>
    <p>{locked ? t(lockText[0]) : guidance ? t('These are your three strongest current matches. Select one to make it your study direction.') : t('AI will compare your interests, personality, subjects, and reasoning snapshot to return your three strongest major fits.')}</p>
    <div className="assessment-ai-readiness">
      <span>{locked ? t(lockText[1]) : guidance ? t('Recommendations ready') : t('Profile ready')}</span>
      {locked ? <Lock size={16} /> : <CheckCircle2 size={16} />}
    </div>
    <button type="button" className="assessment-ai-generate" onClick={generate} disabled={locked || loading}>
      {loading ? <><RefreshCw className="spin" size={17} /> {t("Generating…")}</> : <><Sparkles size={17} /> {guidance ? t('Generate again') : t('Generate recommendations with AI')}</>}
    </button>
    {error && <p className="education-ai-error" role="alert">{error}</p>}
    {topFits.length > 0 && <div className="assessment-ai-fits" role="radiogroup" aria-label={t('Top three major fits')}>
      {topFits.map((item, index) => <button key={item.major} type="button" role="radio" aria-checked={selectedMajor === item.major} className={selectedMajor === item.major ? 'selected' : ''} onClick={() => setSelectedMajor(item.major)}>
        <span>{String(index + 1).padStart(2, '0')}</span>
        <div><b>{item.major}</b><small>{item.why_fit}</small></div>
        <span className="assessment-ai-choice">{selectedMajor === item.major ? <Check size={15} /> : null}</span>
      </button>)}
      <button type="button" className="assessment-ai-confirm" onClick={confirmMajor} disabled={!selectedMajor || saving}>{saving ? t('Saving choice…') : selectedMajor ? t('Choose {major}', { major: selectedMajor }) : t('Select one major')}</button>
      <small className="assessment-ai-disclaimer">{t('You can regenerate or change this choice later. AI guidance supports your decision; it does not limit it.')}</small>
    </div>}
  </section>
}

function MajorMatches({ results, lockReason, student, reload, notify }) {
  const scored = Object.fromEntries(results.filter(([, r]) => r).map(([c, r]) => [c.scoring, r]))
  if (!scored.riasec) return <AIEducationGuidance majors={[]} subjects={[]} lockReason={lockReason || 'incomplete'} student={student} reload={reload} notify={notify} />

  const signals = recSignals(
    scored.riasec.means,
    // The ability/interest/cost composite, not a bare confidence rating -- still
    // on 1..5, so this call is unchanged. The scorer wants {score 0..1, weight},
    // and a self-report is discounted against a real mark either way.
    scored.subjects ? subjectPerformance(scored.subjects.bySubject) : null,
    scored.bigfive || null,
  )
  const majors = recRank(MAJOR_ENTRIES, signals, 'major', 5)
  if (!majors.length) return null

  return <AIEducationGuidance
      majors={majors.map((row) => NAMES.majors[row.key])}
      subjects={scored.subjects ? scored.subjects.ranked.slice(0, 6).map((subject) => SUBJECT_NAME[subject]) : []}
      lockReason={lockReason}
      student={student}
      reload={reload}
      notify={notify}
    />
}

function ResultsSummary({ results }) {
  const done = results.filter(([, r]) => r)
  if (!done.length) return null
  const personality = done.find(([c]) => c.scoring === 'bigfive')
  const interests = done.find(([c]) => c.scoring === 'riasec')
  const subjects = done.find(([c]) => c.scoring === 'subjects')
  const numberColumns = [
    personality && ['PERSONALITY', TRAIT_ORDER.slice(0, 6).map((trait) => [TRAIT_LABEL[trait], personality[1][trait]])],
    interests && ['INTERESTS', RIASEC_ORDER.slice(0, 6).map((scale) => [RIASEC_NAME[scale], interests[1].means[scale]])],
    subjects && ['STRONGEST SUBJECTS', subjects[1].ranked.slice(0, 6).map((subject) => [SUBJECT_NAME[subject], subjects[1].bySubject[subject]])],
  ].filter(Boolean)

  return <section className="assessment-number-summary">
    <div className="assessment-number-hexagon">
      {interests && <ProfilePolygon
        caption={t('Your interest profile')}
        axes={RIASEC_ORDER.map((s) => ({ key: s, label: t(RIASEC_NAME[s]), short: s, value: interests[1].means[s] }))}
      />}
      {!interests && <div className="assessment-number-placeholder"><Hexagon size={38} /><span>{t('Complete Interests to reveal your hexagon.')}</span></div>}
    </div>
    {numberColumns.length > 0 && <div className="assessment-number-breakdown" aria-label={t('Assessment score details')}>
      {numberColumns.map(([title, rows]) => <article className="assessment-number-column" key={title}>
        <h4>{t(title)}</h4>
        <div>{rows.map(([label, value]) => <div key={label}><span>{t(label)}</span><strong>{Number(value).toFixed(1)}</strong></div>)}</div>
      </article>)}
    </div>}
  </section>
}

const ASSESSMENT_CARD_META = {
  personality: {
    description: 'Understand how you think, learn, collaborate, and make decisions.',
    visualClass: 'personality',
  },
  interests: {
    description: 'Explore the activities and problems that naturally motivate you.',
    visualClass: 'interests',
  },
  subjects: {
    description: 'Identify the academic areas where ability and enjoyment meet.',
    visualClass: 'subjects',
  },
  reasoning: {
    description: 'Complete the research-backed ICAR-16 cognitive assessment.',
    visualClass: 'reasoning',
  },
}

const ASSESSMENT_CARD_ORDER = ['personality', 'interests', 'subjects', 'reasoning']

function AssessmentChallengeCard({ challenge, result, answers, saveState, onRetrySave, onOpen }) {
  const answered = challenge.items.filter((item) => answers[item.id]).length
  const visual = ASSESSMENT_CARD_META[challenge.key]
  return <article className={`assessment-card assessment-card-${visual.visualClass} ${result ? 'done' : answered ? 'active' : ''}`}>
    <div className="assessment-card-copy">
      <header><span>{t('STEP')} {String(challenge.number).padStart(2, '0')}</span>{result ? <CheckCircle2 size={21} /> : <span className="assessment-card-count">{answered}/{challenge.items.length}</span>}</header>
      <h3>{t(challenge.title)}</h3>
      <p>{t(visual.description)}</p>
      {challenge.licencePending && <small className="licence-pending"><AlertTriangle size={11} /> {challenge.licencePending}</small>}
      <div className="assessment-card-progress" aria-label={t('{answered} of {total} questions answered', { answered, total: challenge.items.length })}><strong>{answered} / {challenge.items.length}</strong><div className="progress"><span style={{ width: `${(answered / challenge.items.length) * 100}%` }} /></div></div>
      <footer>
        {result && saveState === 'pending'
          ? <span className="assessment-save-state" role="status"><RefreshCw size={12} className="spin" aria-hidden="true" />{t('Not saved yet — retrying')}</span>
          : result && saveState === 'failed'
            ? <span className="assessment-save-state is-failed" role="alert"><CloudOff size={12} aria-hidden="true" />{t('Not saved')}<button type="button" className="assessment-save-retry" onClick={onRetrySave}>{t('Retry')}</button></span>
            : <span>{result ? (saveState === 'saved' ? t('Completed and saved') : t('Completed')) : answered ? t('In progress') : t('{count} questions', { count: challenge.items.length })}</span>}
        <button type="button" className="assessment-card-action" onClick={onOpen}>{result ? t('Review') : answered ? t('Continue') : t('Start')}<ChevronRight size={15} /></button>
      </footer>
    </div>
    <div className="assessment-card-visual" aria-hidden="true" />
  </article>
}

const withoutKey = (object, key) => {
  if (!(key in object)) return object
  const { [key]: _removed, ...rest } = object
  return rest
}

function attemptPayload(challenge, answers, scores, completedAt) {
  return {
    challenge: challenge.key,
    instrument_version: INSTRUMENT_VERSION[challenge.key] || '1',
    answers: Object.fromEntries(challenge.items.map((item) => [item.id, answers[item.id]])),
    scores,
    completed_at: completedAt,
  }
}

export default function ProfileAssessmentPage({ user, notify, data, reload }) {
  const FP_STORAGE_KEY = userStorageKey(USER_STORAGE.assessment, user.id)
  const [answers, setAnswers] = useState(() => loadChallengeAnswers(FP_STORAGE_KEY))
  const [openKey, setOpenKey] = useState(null)
  // Completed attempts already on the server, newest per challenge.
  const [saved, setSaved] = useState({})
  const [loadState, setLoadState] = useState('loading') // loading | ready | error
  // Finished results the server has not confirmed yet, kept across visits.
  const PENDING_KEY = userStorageKey(USER_STORAGE.assessmentPending, user.id)
  const [pending, setPending] = useState(() => loadPendingAttempts(window.localStorage, PENDING_KEY))
  const [failed, setFailed] = useState({}) // challenge -> true when the server refused the save
  const pendingRef = useRef(pending)
  const answersRef = useRef(answers)
  const notifyRef = useRef(notify)
  useEffect(() => { answersRef.current = answers; notifyRef.current = notify })
  const sync = useRef({ alive: true, busy: false, again: false, attempt: 0, timer: null })

  const updatePending = useCallback((change) => {
    const next = change(pendingRef.current)
    if (next === pendingRef.current) return
    pendingRef.current = next
    setPending(next)
    storePendingAttempts(window.localStorage, PENDING_KEY, next)
  }, [PENDING_KEY])

  // Sends every pending result; retryable failures are tried again with
  // backoff, and on the next visit or when the connection comes back.
  const flush = useCallback(async (announce = false) => {
    const state = sync.current
    if (state.busy) { state.again = true; return }
    window.clearTimeout(state.timer)
    state.timer = null
    state.busy = true
    let retry = false
    let savedCount = 0
    try {
      for (const payload of Object.values(pendingRef.current)) {
        try {
          const row = await api.saveChallengeAttempt(payload)
          if (!state.alive) return
          savedCount += 1
          setSaved((prev) => ({ ...prev, [payload.challenge]: row }))
          setFailed((prev) => withoutKey(prev, payload.challenge))
          updatePending((prev) => prev[payload.challenge]?.completed_at === payload.completed_at ? withoutKey(prev, payload.challenge) : prev)
        } catch (error) {
          if (!state.alive) return
          if (isRetryableSaveError(error)) retry = true
          else setFailed((prev) => ({ ...prev, [payload.challenge]: true }))
        }
      }
    } finally {
      state.busy = false
    }
    if (announce && savedCount) notifyRef.current?.(t('Saved to your account.'))
    if (announce && retry) notifyRef.current?.(t('Not saved yet — we’ll keep trying to reach your account.'), 'error')
    if (state.again) {
      state.again = false
      flush()
    } else if (retry) {
      state.timer = window.setTimeout(() => flush(), saveRetryDelay(state.attempt))
      state.attempt += 1
    } else {
      state.attempt = 0
    }
  }, [updatePending])

  const loadAttempts = useCallback(async () => {
    setLoadState('loading')
    try {
      const rows = await api.challengeAttempts()
      if (!sync.current.alive) return
      // The API returns newest first, so the first row seen for a challenge is
      // the current one; the older ones stay for the year-on-year comparison.
      const latest = {}
      for (const row of rows) if (!latest[row.challenge]) latest[row.challenge] = row
      setSaved(latest)
      setLoadState('ready')
      // Server answers win over whatever is half-finished on this device.
      const merged = mergeServerAnswers(answersRef.current, latest, pendingRef.current)
      setAnswers(merged)
      // A result finished here that the account never received (an older
      // version kept it on this device only) is queued for saving now.
      const completedAt = new Date().toISOString()
      updatePending((prev) => {
        let next = prev
        for (const challenge of CHALLENGES) {
          if (latest[challenge.key] || prev[challenge.key]) continue
          const result = scoreChallenge(challenge, merged)
          if (result) next = { ...next, [challenge.key]: attemptPayload(challenge, merged, result, completedAt) }
        }
        return next
      })
    } catch {
      if (sync.current.alive) setLoadState('error')
    }
    flush()
  }, [flush, updatePending])

  useEffect(() => {
    const state = sync.current
    state.alive = true
    loadAttempts()
    const onOnline = () => { state.attempt = 0; flush() }
    window.addEventListener('online', onOnline)
    return () => {
      state.alive = false
      window.clearTimeout(state.timer)
      window.removeEventListener('online', onOnline)
    }
  }, [loadAttempts, flush])

  // The device copy is for a challenge left half-finished; the account holds the
  // completed ones. Losing this is an inconvenience, losing those is the product.
  useEffect(() => {
    try { window.localStorage.setItem(FP_STORAGE_KEY, JSON.stringify(answers)) } catch { /* private mode */ }
  }, [answers, FP_STORAGE_KEY])

  const answerItem = useCallback((id, value) => setAnswers((prev) => ({ ...prev, [id]: value })), [])

  const finishChallenge = useCallback((challenge) => {
    setOpenKey(null)
    window.scrollTo(0, 0)
    const result = scoreChallenge(challenge, answers)
    if (!result) return
    updatePending((prev) => ({ ...prev, [challenge.key]: attemptPayload(challenge, answers, result, new Date().toISOString()) }))
    setFailed((prev) => withoutKey(prev, challenge.key))
    sync.current.attempt = 0
    flush(true)
  }, [answers, flush, updatePending])

  const retrySave = useCallback(() => {
    setFailed({})
    sync.current.attempt = 0
    flush(true)
  }, [flush])
  const results = CHALLENGES.map((challenge) => [challenge, scoreChallenge(challenge, answers)])
  const lockReason = assessmentLockReason({
    challengeKeys: CHALLENGES.map((challenge) => challenge.key),
    completedKeys: results.filter(([, result]) => result).map(([challenge]) => challenge.key),
    saved, pending, loading: loadState === 'loading', loadFailed: loadState === 'error',
  })
  const doneCount = results.filter(([, result]) => result).length
  const student = ownStudent(data)
  const open = CHALLENGES.find((challenge) => challenge.key === openKey)
  const resultByKey = Object.fromEntries(results.map(([challenge, result]) => [challenge.key, { challenge, result }]))

  if (open) return <ChallengeRunner challenge={open} answers={answers} onAnswer={answerItem} onFinish={() => finishChallenge(open)} onBack={() => setOpenKey(null)} />

  return <div className="section-stack student-portal profile-assessment-page">
    {loadState === 'error' && <div className="assessment-load-error" role="alert">
      <CloudOff size={16} aria-hidden="true" />
      <span>{t('We couldn’t load the results saved to your account.')}</span>
      <button type="button" className="button quiet small" onClick={loadAttempts}><RefreshCw size={14} aria-hidden="true" /> {t('Retry')}</button>
    </div>}
    <div className="assessment-overview-layout">
      <section className="assessment-card-grid" aria-label={t('Profile assessment challenges')}>{ASSESSMENT_CARD_ORDER.map((key) => {
        const challengeEntry = resultByKey[key]
        return <AssessmentChallengeCard
          key={key}
          challenge={challengeEntry.challenge}
          result={challengeEntry.result}
          answers={answers}
          saveState={failed[key] ? 'failed' : pending[key] ? 'pending' : saved[key] ? 'saved' : null}
          onRetrySave={retrySave}
          onOpen={() => { setOpenKey(key); window.scrollTo(0, 0) }}
        />
      })}</section>

      <MajorMatches results={results} lockReason={lockReason} student={student} reload={reload} notify={notify} />
    </div>

    {doneCount > 0 && <div id="assessment-results" className="assessment-results-stack">
      <ResultsSummary results={results} />
    </div>}
  </div>
}
