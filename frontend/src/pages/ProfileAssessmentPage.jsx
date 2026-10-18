import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, BrainCircuit, Check, CheckCircle2, ChevronRight, CloudOff, Fingerprint, Hexagon, Lock, RefreshCw, RotateCw } from 'lucide-react';
import { api } from '../api';
import { t } from '../i18n';
import { Panel } from '../components/ui';
import { ProfileResultCard } from '../components/ProfileResultCard';
import { fullName, ownStudent } from '../lib/labels';
import { profileCardData } from '../lib/profileCard';
import { USER_STORAGE, userStorageKey } from '../userStorage';
import {
  assessmentLockReason, isRetryableSaveError, loadPendingAttempts, mergeServerAnswers, saveRetryDelay, storePendingAttempts } from
'../lib/assessmentSync';
import {
  CHALLENGES, RIASEC_NAME, RIASEC_ORDER,
  INSTRUMENT_VERSION, REASONING_DOMAIN_LABEL, RIASEC_LEAD, SUBJECT_NAME, TRAIT_BLURB, TRAIT_LABEL, TRAIT_ORDER, TRAIT_SHORT,
  VALUE_NAME, WIL_LEAD, WIL_NAME, WIL_SHORT,
  scoreChallenge } from
'../challenges';
import { EQ_LEAD, EQ_NAME, EQ_ORDER } from '../challengeBanksMind';
import './assessment-hub.css';
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

// The circles come in five sizes and tones, ends large and the middle small. A
// seven-point scale (EQ) shares them out evenly: 1 2 2 3 4 4 5.
const scaleTone = (points, position) => Math.round(1 + (position * 4) / (points - 1))

function ChallengeRunner({ challenge, answers, onAnswer, onFinish, onBack }) {
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
          <div className={`scale-dots${challenge.scale.length === 7 ? ' is-seven' : ''}`}>{challenge.scale.map((scaleLabel, position) => {
            const chosen = answers[item.id] === position + 1
            const label = optionLabel(challenge, item, position)
            return <label key={scaleLabel} className={`scale-opt s${scaleTone(challenge.scale.length, position)}${chosen ? ' sel' : ''}`} title={label}>
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
      ? <><strong>{axes.find((a) => a.key === hover).label}</strong> — {t('{value} of 5', { value: axes.find((a) => a.key === hover).value.toFixed(1) })}</>
      : caption}</figcaption>
  </figure>
}

// Majors unlock once all seven challenges are finished and saved. Interests
// lead the deterministic ranking, subjects and personality sharpen it.
const LOCK_TEXT = {
  incomplete: 'Complete all seven tests to unlock your three majors.',
  loading: 'Checking the results saved to your account…',
  pending: 'Your results are still being saved. Your majors unlock once your account has them.',
  unsynced: 'Your account doesn’t have all seven results yet. Load your saved results to unlock your majors.',
}

// Finished results by scoring kind ('riasec', 'bigfive', 'subjects', ...).
const scoredBy = (results) => Object.fromEntries(results.filter(([, r]) => r).map(([c, r]) => [c.scoring, r]))

// The deterministic major shortlist, as major keys.
function majorShortlist(scored, limit) {
  const signals = recSignals(
    scored.riasec.means,
    // The ability/interest/cost composite, not a bare confidence rating -- still
    // on 1..5, so this call is unchanged. The scorer wants {score 0..1, weight},
    // and a self-report is discounted against a real mark either way.
    scored.subjects ? subjectPerformance(scored.subjects.bySubject) : null,
    scored.bigfive || null,
  )
  return recRank(MAJOR_ENTRIES, signals, 'major', limit).map((row) => row.key)
}

// The three majors the student revealed on the next-step card, kept in this
// browser so they are still on the card after a reload or the next visit.
function loadRevealedMajors(storageKey) {
  try {
    const saved = JSON.parse(window.localStorage.getItem(storageKey) || 'null')
    return Array.isArray(saved?.majors) && saved.majors.every((key) => MAJOR_ENTRIES[key]) ? saved : null
  } catch { return null }
}

function storeRevealedMajors(storageKey, majors) {
  try { window.localStorage.setItem(storageKey, JSON.stringify({ majors, revealedAt: new Date().toISOString() })) } catch { /* private mode */ }
}

// The two school subjects a major leans on most, from the shared majors data.
const coreSubjects = (key) => Object.entries(MAJOR_ENTRIES[key]?.subjects || {})
  .sort((a, b) => b[1] - a[1]).slice(0, 2).map(([subject]) => t(SUBJECT_NAME[subject]))

// Which columns go where. The profile card's back is an ID card with room for
// three columns, so the three newer tests are listed under the card instead.
// Reasoning has no column: its hub card's back carries the score.
const CARD_BACK_KEYS = ['personality', 'interests', 'subjects']
const UNDER_CARD_KEYS = ['values', 'workimportance', 'eq']
const DETAIL_KEYS = [...CARD_BACK_KEYS, ...UNDER_CARD_KEYS]

// The score behind every finished challenge, as columns of label and value.
function ResultNumbers({ results, keys = DETAIL_KEYS, highlight }) {
  const done = Object.fromEntries(results.filter(([, r]) => r).map(([c, r]) => [c.key, [c, r]]))
  const numberColumns = [
    done.personality && ['personality', 'PERSONALITY', TRAIT_ORDER.map((trait) => [TRAIT_LABEL[trait], done.personality[1][trait]])],
    done.interests && ['interests', 'INTERESTS', RIASEC_ORDER.map((scale) => [RIASEC_NAME[scale], done.interests[1].means[scale]])],
    done.values && ['values', 'WHAT MATTERS AT WORK', done.values[1].ranked.slice(0, 6).map((dim) => [VALUE_NAME[dim], done.values[1].byDim[dim]])],
    done.subjects && ['subjects', 'HOW SCHOOL FEELS', done.subjects[1].ranked.slice(0, 6).map((subject) => [SUBJECT_NAME[subject], done.subjects[1].bySubject[subject]])],
    done.workimportance && ['workimportance', 'WHAT MATTERS MOST', done.workimportance[1].ranked.map((value) => [WIL_NAME[value], done.workimportance[1].scores[value]])],
    done.eq && ['eq', 'EQ · OUT OF 7', EQ_ORDER.map((dim) => [EQ_NAME[dim], done.eq[1].scores[dim]])],
  ].filter((column) => column && keys.includes(column[0]))
  if (!numberColumns.length) return null
  return <div className="assessment-number-breakdown" aria-label={t('Assessment score details')}>
    {numberColumns.map(([key, title, rows]) => <article id={`assessment-result-${key}`} className={`assessment-number-column${highlight === key ? ' is-highlighted' : ''}`} key={key}>
      <h3>{t(title)}</h3>
      <div>{rows.map(([label, value]) => <div key={label}><span>{t(label)}</span><strong>{Number(value).toFixed(1)}</strong></div>)}</div>
    </article>)}
  </div>
}

// Before Interests is finished there is no card yet: the hexagon placeholder
// and whatever numbers exist stand in for it.
function ResultsSummary({ results, highlight }) {
  const done = results.filter(([, r]) => r)
  if (!done.length) return null
  const interests = done.find(([c]) => c.scoring === 'riasec')

  return <section className="assessment-number-summary">
    <div className="assessment-number-hexagon">
      {interests && <ProfilePolygon
        caption={t('Your interest profile')}
        axes={RIASEC_ORDER.map((s) => ({ key: s, label: t(RIASEC_NAME[s]), short: s, value: interests[1].means[s] }))}
      />}
      {!interests && <div className="assessment-number-placeholder"><Hexagon size={38} /><span>{t('Complete Interests to reveal your hexagon.')}</span></div>}
    </div>
    <ResultNumbers results={results} highlight={highlight} />
  </section>
}

// The Naseeb Mind hub: one card per challenge, in its order and its words.
const HUB_CARD = {
  personality: { title: 'Personality', brief: 'Discover what makes you unique.', image: '/assessment/hub/personality-hero.webp' },
  interests: { title: 'Interests', brief: 'Find out what interests you.', image: '/assessment/hub/interests.webp' },
  values: { title: 'What matters at work', brief: 'Learn what matters to you in work.', image: '/assessment/hub/values.webp' },
  subjects: { title: 'How school feels', brief: 'Understand how school feels to you.', image: '/assessment/hub/school.webp' },
  workimportance: { title: 'What matters most', brief: 'Identify your work priorities.', image: '/assessment/hub/workimportance.webp' },
  reasoning: { title: 'Reasoning', brief: 'Find the connections between patterns.', image: '/assessment/hub/reasoning.webp' },
  eq: { title: 'EQ · Emotional intelligence', brief: 'Understand your emotions and how you respond to them.', image: '/assessment/hub/eq.svg' },
}

const answeredCount = (challenge, answers) => challenge.items.filter((item) => answers[item.id]).length

// ---- the back of a finished card ----
// One conclusion and, where the test has a shape worth seeing, a small chart.
// Everything comes from the scored result; nothing is stored or sent.

// Label above a bar, value beside it. `min..max` is the test's own scale.
function MiniBars({ rows, min = 1, max = 5 }) {
  return <ul className="hub-mini-bars">{rows.map(([label, value]) => <li key={label}>
    <span title={label}>{label}</span>
    <i aria-hidden="true"><b style={{ width: `${Math.max(4, ((value - min) / (max - min)) * 100)}%` }} /></i>
    <strong>{Number(value).toFixed(1)}</strong>
  </li>)}</ul>
}

// The six interest scales in Holland's order; the student's code is lit.
function MiniHexagon({ means, code }) {
  const size = 140, mid = size / 2, radius = 46
  const point = (index, scale) => {
    const angle = (Math.PI * 2 * index) / RIASEC_ORDER.length - Math.PI / 2
    return [mid + Math.cos(angle) * radius * scale, mid + Math.sin(angle) * radius * scale]
  }
  const polygon = (scale) => RIASEC_ORDER.map((_, index) => point(index, scale).map((n) => n.toFixed(1)).join(',')).join(' ')
  const shape = RIASEC_ORDER.map((scale, index) => point(index, Math.max(0.06, (means[scale] - 1) / 4)).map((n) => n.toFixed(1)).join(',')).join(' ')
  return <svg className="hub-mini-hex" viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
    {[0.5, 1].map((scale) => <polygon key={scale} className="ring" points={polygon(scale)} />)}
    <polygon className="shape" points={shape} />
    {RIASEC_ORDER.map((scale, index) => {
      const [x, y] = point(index, 1.3)
      return <text key={scale} x={x} y={y} className={code.includes(scale) ? 'top' : ''} fontSize="13" textAnchor="middle" dominantBaseline="central">{scale}</text>
    })}
  </svg>
}

function MiniRing({ value, total }) {
  const radius = 40, length = 2 * Math.PI * radius
  return <svg className="hub-mini-ring" viewBox="0 0 100 100" aria-hidden="true">
    <circle className="track" cx="50" cy="50" r={radius} />
    <circle className="fill" cx="50" cy="50" r={radius} strokeDasharray={`${(value / total) * length} ${length}`} transform="rotate(-90 50 50)" />
    <text x="50" y="47" fontSize="26" textAnchor="middle" dominantBaseline="central">{value}</text>
    <text className="of" x="50" y="66" fontSize="12" textAnchor="middle" dominantBaseline="central">/ {total}</text>
  </svg>
}

const strongest = (order, scores) => [...order].sort((a, b) => scores[b] - scores[a])[0]

// EQ bar labels: the full area names do not fit a card's chart column.
const EQ_SHORT = { SEA: 'Own emotions', OEA: 'Others’ emotions', UOE: 'Self-motivation', ROE: 'Self-control' }

function cardSummary(key, result) {
  if (key === 'personality') {
    const top = strongest(TRAIT_ORDER, result)
    return {
      headline: t('Strongest trait: {trait}', { trait: t(TRAIT_LABEL[top]) }),
      text: t(TRAIT_BLURB[top]),
      chart: <MiniBars rows={TRAIT_ORDER.map((trait) => [t(TRAIT_SHORT[trait]), result[trait]])} />,
    }
  }
  if (key === 'interests') return {
    headline: t('Your interest code: {code}', { code: result.code.join('') }),
    text: t(RIASEC_LEAD[result.code[0]]),
    chart: <MiniHexagon means={result.means} code={result.code} />,
  }
  if (key === 'values') {
    const [first, second, third] = result.ranked
    return {
      headline: t('You want most: {value}', { value: t(VALUE_NAME[first]) }),
      text: t('Your top three for a future job.'),
      chart: <ol className="hub-mini-rank">{[first, second, third].map((dim) => <li key={dim}>{t(VALUE_NAME[dim])}</li>)}</ol>,
    }
  }
  if (key === 'subjects') return {
    headline: t('Best fit: {subject}', { subject: t(SUBJECT_NAME[result.ranked[0]]) }),
    text: t('Where your ability, interest and ease meet.'),
    chart: <MiniBars rows={result.ranked.slice(0, 3).map((subject) => [t(SUBJECT_NAME[subject]), result.bySubject[subject]])} />,
  }
  if (key === 'workimportance') return {
    headline: t('Top priority: {value}', { value: t(WIL_NAME[result.ranked[0]]) }),
    text: t(WIL_LEAD[result.ranked[0]]),
    chart: <MiniBars rows={result.ranked.slice(0, 4).map((value) => [t(WIL_SHORT[value]), result.scores[value]])} />,
  }
  if (key === 'reasoning') return {
    headline: t('{correct} of {total} correct', { correct: result.correct, total: result.total }),
    text: result.strongestDomains.length === result.rankedDomains.length
      ? t('Even across all four areas.')
      : t('Strongest area: {area}', { area: t(REASONING_DOMAIN_LABEL[result.strongestDomains[0]]) }),
    chart: <MiniRing value={result.correct} total={result.total} />,
  }
  if (key === 'eq') {
    const top = result.ranked[0]
    const even = EQ_ORDER.every((dim) => result.scores[dim] === result.scores[top])
    return {
      headline: even ? t('All four areas are even') : t('Strongest area: {area}', { area: t(EQ_NAME[top]) }),
      text: even ? t('Your answers rate every area the same.') : t(EQ_LEAD[top]),
      chart: <MiniBars rows={EQ_ORDER.map((dim) => [t(EQ_SHORT[dim]), result.scores[dim]])} max={7} />,
    }
  }
  return null
}

function HubCard({ challenge, result, answers, saveState, onRetrySave, onOpen, onSeeResult }) {
  // Hover turns a finished card over; touch and keyboard use the flip button.
  const [flipped, setFlipped] = useState(false)
  const frontFlip = useRef(null)
  const backFlip = useRef(null)
  const turned = useRef(false)
  // The face being left goes inert, so keyboard focus follows to the other one.
  useEffect(() => {
    if (!turned.current) return
    turned.current = false
    const target = flipped ? backFlip.current : frontFlip.current
    target?.focus({ preventScroll: true })
  }, [flipped])
  const turn = (value) => { turned.current = true; setFlipped(value) }
  const meta = HUB_CARD[challenge.key]
  // Reasoning has no score columns on the page; its back is its result.
  const hasDetails = DETAIL_KEYS.includes(challenge.key)
  // A result still being saved keeps its front, where Retry lives.
  const unsaved = Boolean(result) && (saveState === 'pending' || saveState === 'failed')
  const answered = answeredCount(challenge, answers)
  const total = challenge.items.length
  const started = answered > 0 && !result
  const action = result ? t('See the result') : started ? t('Continue') : t('Start')
  const summary = result ? cardSummary(challenge.key, result) : null
  const go = <button type="button" className="hub-card-go" aria-label={`${action}: ${t(meta.title)}`} onClick={!result ? onOpen : hasDetails ? onSeeResult : () => turn(true)}>
    {action}<span aria-hidden="true">→</span>
  </button>
  const backTab = flipped ? 0 : -1
  return <li className={`hub-card${result ? ' is-done' : ''}${unsaved ? ' is-unsaved' : ''}${flipped ? ' is-flipped' : ''}`} data-kind={challenge.key}>
    <div className="hub-card-inner">
      <div className="hub-card-face hub-card-front" inert={flipped}>
        <div className="hub-card-body">
          <h2>{t(meta.title)}</h2>
          <p>{t(meta.brief)}</p>
          <div className="hub-card-side">
            {started && <>
              <span className="hub-card-part">{t('{answered} of {total}', { answered, total })}</span>
              <span className="hub-card-progress" aria-hidden="true"><i style={{ width: `${Math.round((answered / total) * 100)}%` }} /></span>
            </>}
            {result && saveState === 'pending' && <span className="hub-card-save" role="status"><RefreshCw size={12} className="spin" aria-hidden="true" />{t('Not saved yet — retrying')}</span>}
            {result && saveState === 'failed' && <span className="hub-card-save" role="alert"><CloudOff size={12} aria-hidden="true" />{t('Not saved')}<button type="button" onClick={onRetrySave}>{t('Retry')}</button></span>}
            {go}
          </div>
        </div>
        <img className="hub-card-art" src={meta.image} alt="" decoding="async" />
        {summary && <button ref={frontFlip} type="button" className="hub-card-flip" aria-label={t('Show summary: {test}', { test: t(meta.title) })} onClick={() => turn(true)}><RotateCw size={16} aria-hidden="true" /></button>}
      </div>
      {/* Not inert: a hover turns the card without changing state, and the back's
          button must take that click. Keyboard and screen readers reach it only
          once the flip button has turned it. */}
      {summary && <div className="hub-card-face hub-card-back" aria-hidden={!flipped}>
        <div className="hub-card-body">
          <span className="hub-card-eyebrow">{t(meta.title)}</span>
          <h3>{summary.headline}</h3>
          <p>{summary.text}</p>
          <div className="hub-card-side">
            {hasDetails && <button type="button" className="hub-card-go" tabIndex={backTab} aria-label={`${t('See the result')}: ${t(meta.title)}`} onClick={onSeeResult}>
              {t('See the result')}<span aria-hidden="true">→</span>
            </button>}
            <button type="button" className={hasDetails ? 'hub-card-review' : 'hub-card-go'} tabIndex={backTab} aria-label={`${t('Review answers')}: ${t(meta.title)}`} onClick={onOpen}>
              {t('Review answers')}{!hasDetails && <span aria-hidden="true">→</span>}
            </button>
          </div>
        </div>
        <div className="hub-card-chart">{summary.chart}</div>
        <button ref={backFlip} type="button" className="hub-card-flip" aria-label={t('Show the front: {test}', { test: t(meta.title) })} tabIndex={backTab} onClick={() => turn(false)}><RotateCw size={16} aria-hidden="true" /></button>
      </div>}
    </div>
  </li>
}

// The hub's third column. While a core test is unfinished it points at the
// next one; once all seven are saved, Continue turns it into the student's three
// majors, which stay on the card (and in this browser) from then on.
function HubNextCard({ results, answers, lockReason, shortlist, revealed, onReveal, onOpen, student, reload, notify }) {
  const [pick, setPick] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const done = results.filter(([, result]) => result).length
  const dots = <div className="hub-next-dots" aria-hidden="true">{results.map(([challenge, result]) => <i key={challenge.key} className={result ? 'is-done' : ''} />)}</div>
  const status = <div className="hub-next-status"><span>{t('{done} / {total} completed', { done, total: results.length })}</span>{dots}</div>
  const logo = <img className="hub-next-logo" src="/assessment/hub/logo.png" alt="" />

  const majors = revealed && !lockReason ? revealed.majors : null
  if (majors) {
    const saved = student?.target_major || ''
    const chosen = pick || majors.find((key) => NAMES.majors[key] === saved) || ''
    const unsaved = Boolean(chosen) && NAMES.majors[chosen] !== saved
    async function save() {
      if (!unsaved || !student) return
      setSaving(true)
      setError('')
      try {
        await api.update('students', student.id, { target_major: NAMES.majors[chosen] })
        notify?.(t('{major} saved as your current study direction.', { major: t(NAMES.majors[chosen]) }))
        setPick('')
        reload?.()
      } catch (requestError) {
        setError(requestError.message || t('We could not save your selected major.'))
      } finally {
        setSaving(false)
      }
    }
    return <aside className="hub-next has-picks" aria-labelledby="hub-next-title">
      <div className="hub-next-eyebrow">{t('Recommended majors')}</div>
      <h2 id="hub-next-title">{t('Your three majors')}</h2>
      <p>{t('Based on your results. Saved on this computer.')}</p>
      <div className="hub-next-majors" role="radiogroup" aria-label={t('Your three majors')}>
        {majors.map((key, index) => <button key={key} type="button" role="radio" aria-checked={chosen === key} className={chosen === key ? 'selected' : ''} onClick={() => setPick(key)}>
          <span>{String(index + 1).padStart(2, '0')}</span>
          <strong>{t(NAMES.majors[key])}{coreSubjects(key).length > 0 && <small>{coreSubjects(key).join(' · ')}</small>}</strong>
          {chosen === key && <Check size={16} aria-hidden="true" />}
        </button>)}
      </div>
      <button type="button" className="hub-next-button" onClick={save} disabled={!unsaved || saving || !student}>
        {saving ? t('Saving choice…') : unsaved ? t('Choose {major}', { major: t(NAMES.majors[chosen]) }) : saved && chosen ? <><CheckCircle2 size={18} aria-hidden="true" />{t('Saved as your study direction')}</> : t('Select one major')}
      </button>
      {error && <p className="hub-next-error" role="alert">{error}</p>}
    </aside>
  }

  const ready = !lockReason && shortlist.length > 0
  if (ready || (lockReason && lockReason !== 'incomplete')) return <aside className="hub-next" aria-labelledby="hub-next-title">
    {logo}
    <div className="hub-next-eyebrow">{t('Next step')}</div>
    <h2 id="hub-next-title">{t('Recommended majors')}</h2>
    <p>{ready ? t('All seven tests are complete. Continue to see your three majors.') : t(LOCK_TEXT[lockReason])}</p>
    {status}
    <button type="button" className="hub-next-button" onClick={() => onReveal(shortlist)} disabled={!ready}>
      {lockReason === 'loading' ? <RefreshCw size={18} className="spin" aria-hidden="true" /> : !ready ? <Lock size={18} aria-hidden="true" /> : null}
      <span>{t('Continue')}</span>{ready && <ArrowRight size={18} aria-hidden="true" />}
    </button>
  </aside>

  // The test they left half-way wins over the first one they have not started.
  const open = results.filter(([, result]) => !result).map(([challenge]) => challenge)
  const next = open.find((challenge) => answeredCount(challenge, answers) > 0) || open[0]
  if (!next) return null
  const paused = answeredCount(next, answers) > 0
  return <aside className="hub-next" aria-labelledby="hub-next-title">
    {logo}
    <div className="hub-next-eyebrow">{t('Next step')}</div>
    <h2 id="hub-next-title">{t(HUB_CARD[next.key].title)}</h2>
    <p>{paused ? t('Continue the test you started. Your answers are saved.') : done ? t('Take the assessments to understand yourself better.') : t('Start with this test to understand your personal traits.')}</p>
    {status}
    <button type="button" className="hub-next-button" onClick={() => onOpen(next.key)}>
      <span>{paused ? t('Continue') : t('Start')}</span><ArrowRight size={18} aria-hidden="true" />
    </button>
  </aside>
}

// Every challenge, EQ included, is needed before the majors unlock.
const CORE_CHALLENGE_KEYS = CHALLENGES.map((challenge) => challenge.key)

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
  const [highlight, setHighlight] = useState(null)
  const [cardFlipRequest, setCardFlipRequest] = useState(0)
  // "See the result" marks its column for a moment, then lets it go.
  useEffect(() => {
    if (!highlight) return undefined
    const timer = window.setTimeout(() => setHighlight(null), 2600)
    return () => window.clearTimeout(timer)
  }, [highlight])
  const MAJORS_KEY = userStorageKey(USER_STORAGE.assessmentMajors, user.id)
  const [revealed, setRevealed] = useState(() => loadRevealedMajors(MAJORS_KEY))
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
    challengeKeys: CORE_CHALLENGE_KEYS,
    completedKeys: results.filter(([, result]) => result).map(([challenge]) => challenge.key),
    saved, pending, loading: loadState === 'loading', loadFailed: loadState === 'error',
  })
  const doneCount = results.filter(([, result]) => result).length
  const student = ownStudent(data)
  const open = CHALLENGES.find((challenge) => challenge.key === openKey)
  const scored = scoredBy(results)
  const shortlist = scored.riasec && !lockReason ? majorShortlist(scored, 3) : []
  const shortlistKey = shortlist.join('|')
  // A retake that moves the ranking replaces the three already on the card.
  useEffect(() => {
    if (!revealed || !shortlistKey || revealed.majors.join('|') === shortlistKey) return
    const next = shortlistKey.split('|')
    storeRevealedMajors(MAJORS_KEY, next)
    setRevealed({ majors: next })
  }, [revealed, shortlistKey, MAJORS_KEY])
  const revealMajors = useCallback((majors) => {
    storeRevealedMajors(MAJORS_KEY, majors)
    setRevealed({ majors })
  }, [MAJORS_KEY])
  // Majors join the card only once recommendations unlock, as they do on the page.
  const person = student?.user_detail || user
  const card = profileCardData({
    results,
    majors: shortlist.length ? shortlist.map((key) => NAMES.majors[key]) : null,
    firstName: person?.first_name || fullName(person),
    lastName: person?.last_name || '',
  })
  const openChallenge = (key) => { setOpenKey(key); window.scrollTo(0, 0) }
  // A finished card leads to its own numbers: on the profile card's back for
  // the three it carries (turning the card over), in the list under it for the rest.
  const seeResult = (key) => {
    const onCardBack = Boolean(card) && CARD_BACK_KEYS.includes(key)
    const target = onCardBack ? document.querySelector('.profile-card-panel') : document.getElementById(`assessment-result-${key}`)
    if (!target) return
    if (onCardBack) setCardFlipRequest((value) => value + 1)
    setHighlight(key)
    target.scrollIntoView({ behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' })
  }

  if (open) return <ChallengeRunner challenge={open} answers={answers} onAnswer={answerItem} onFinish={() => finishChallenge(open)} onBack={() => setOpenKey(null)} />

  return <div className="section-stack student-portal profile-assessment-page">
    {loadState === 'error' && <div className="assessment-load-error" role="alert">
      <CloudOff size={16} aria-hidden="true" />
      <span>{t('We couldn’t load the results saved to your account.')}</span>
      <button type="button" className="button quiet small" onClick={loadAttempts}><RefreshCw size={14} aria-hidden="true" /> {t('Retry')}</button>
    </div>}
    <div className="hub-layout">
      <ol className="hub-list" aria-label={t('Profile assessment challenges')}>{results.map(([challenge, result]) => <HubCard
        key={challenge.key}
        challenge={challenge}
        result={result}
        answers={answers}
        saveState={failed[challenge.key] ? 'failed' : pending[challenge.key] ? 'pending' : saved[challenge.key] ? 'saved' : null}
        onRetrySave={retrySave}
        onOpen={() => openChallenge(challenge.key)}
        onSeeResult={() => seeResult(challenge.key)}
      />)}</ol>
      <HubNextCard
        results={results}
        answers={answers}
        lockReason={lockReason}
        shortlist={shortlist}
        revealed={revealed}
        onReveal={revealMajors}
        onOpen={openChallenge}
        student={student}
        reload={reload}
        notify={notify}
      />
    </div>

    {doneCount > 0 && <div id="assessment-results" className="assessment-results-stack">
      {card
        ? <>
          <ProfileResultCard card={card} student={student} flipRequest={cardFlipRequest}><ResultNumbers results={results} keys={CARD_BACK_KEYS} highlight={highlight} /></ProfileResultCard>
          <ResultNumbers results={results} keys={UNDER_CARD_KEYS} highlight={highlight} />
        </>
        : <ResultsSummary results={results} highlight={highlight} />}
    </div>}
  </div>
}
