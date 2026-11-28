import { t, tp, tx, locale, formatDateLocale, formatNumberLocale } from '../i18n';
import { InlineLoadError } from '../components/states';
import { dateText, localDateKey, money } from '../lib/format';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MapPin, CalendarDays, CalendarSearch, DollarSign, UsersRound, GraduationCap, HandCoins, ExternalLink, Search, SlidersHorizontal, ChevronDown, ChevronRight, ArrowLeft, ArrowUpRight, ListChecks, X, Check, Bookmark, Monitor, Award, Gift, Globe2, Heart, Star, Clock3, TriangleAlert } from 'lucide-react';
import { request } from '../api';
import './catalog.css';
import './programs-redesign.css';
import '../design/pages/catalog-blue-base.css';
import '../design/pages/programs-blue.css';
import { BlueButton, DaysChip, GlassCard, KpiRow, KpiTile, PageHeader } from '../design/blue/ui';
import { FilterOption } from '../components/college';
import { Empty } from '../components/ui';
import { withQuery } from '../lib/routes';
import { countryFlag } from '../lib/countries';
import { DeadlineRadar, DeadlineRadarButton } from '../components/DeadlineRadar';
import { PAGE_PATHS } from '../lib/routes';
import { daysUntil, dueLabel, dueTone } from '../lib/college';
import { PROGRAM_DELIVERY, PROGRAM_FILTER_DEFAULTS, PROGRAM_GRADES, activeProgramFilterCount, adoptProgramFilterUrl, compactGrades, countdownDay, filterPrograms, isUnverifiedTelegramImport, groupProgramsByDeadline, extraFeeText, hasProgramFilters, isFreeProgram, programFilterState, programFilterWrite, programGrades, selectedGrades, toggleGrade } from '../lib/programFilters';

// The catalog is a yearly list: only a few rows carry a real date, the rest keep the
// counselor sheet's own deadline text and have to be confirmed on the official page.
export function ProgramDeadline({ item, closed }) {
  if (item.deadline) return <>{closed ? t("Closed") : t("Deadline")} {dateText(item.deadline)}</>;
  if (item.deadline_text) return <>{t("Usual deadline")} {item.deadline_text} · {t("confirm the date")}</>;
  return <>{t("Deadline on the official page")}</>;
}

// Filters live in the URL query (/programs?type=national&grade=10), so a
// reload, a bookmark or a shared link shows the same list. The query comes
// from the app's location state, so Back/Forward and sidebar links update the
// filters and the app always knows the current URL.
function useUrlFilters(search, navigate) {
  const [state, setState] = useState(() => programFilterState(search));
  const current = adoptProgramFilterUrl(state, search);
  if (current !== state) setState(current);
  const setFilters = useCallback((change) => setState((previous) => ({
    ...previous, filters: typeof change === 'function' ? change(previous.filters) : change,
  })), []);
  useEffect(() => {
    // Debounced: browsers rate-limit history updates, and typing is fast.
    const timer = window.setTimeout(() => {
      const next = programFilterWrite(current, search);
      if (next === null) return;
      try {
        navigate(`${window.location.pathname}${next}${window.location.hash}`, { replace: true });
        setState((previous) => ({ ...previous, synced: next }));
      } catch {/* URL keeps the previous filters. */}
    }, 250);
    return () => window.clearTimeout(timer);
  }, [current, search, navigate]);
  return [current.filters, setFilters];
}

const DELIVERY_LABELS = { onsite: 'On-site', online: 'Online', hybrid: 'Hybrid' };

const PROGRAM_LOGOS = [
  [/northwestern/i, '/landing/universities/northwestern.svg'],
  [/new york university|\bnyu\b/i, '/landing/universities/nyu.svg'],
  [/duke university/i, '/landing/universities/duke.svg'],
  [/university of toronto/i, '/landing/universities/toronto.png'],
  [/kaist/i, '/landing/universities/kaist.svg'],
  [/purdue/i, '/landing/universities/purdue.svg'],
  [/launchx/i, '/landing/programs/launchx.svg'],
  [/lumiere/i, '/landing/programs/lumiere-wordmark.png'],
  [/united world colleges|\buwc\b/i, '/landing/programs/uwc.svg'],
  [/flex program|future leaders exchange/i, '/landing/programs/flex.png'],
];

const programLogo = (item) => PROGRAM_LOGOS.find(([pattern]) => pattern.test(`${item.provider || ''} ${item.title || ''}`))?.[1];

// Hover text for a dashed date: it is the usual yearly date, not a confirmed one.
const usualHint = () => `${t('Usual deadline')} · ${t('confirm the date')}`;

// The deadline, read at a glance: day over month. A real date is solid and
// tinted by urgency; a usual date read from the yearly text is dashed, because
// it still has to be confirmed on the official page.
function DueTile({ due, closed, tone }) {
  if (!due) return <span className="program-tile is-unknown" aria-hidden="true"><CalendarSearch size={24} /></span>;
  const state = closed ? 'is-closed' : due.exact ? tone : 'is-usual';
  return <span className={`program-tile ${state}`.trim()} aria-hidden="true" title={state === 'is-usual' ? usualHint() : undefined}>
    {due.day && <b>{formatNumberLocale(due.day)}</b>}<small>{formatDateLocale(due.date, { month: 'short' })}</small>
  </span>;
}

// My List: the days left in place of the date, inside a ring that empties
// over the last 30 days. Solid = a real deadline; dashed = counted to the
// usual date from the yearly text, still to be confirmed.
const RING_RADIUS = 26;
const RING_LENGTH = 2 * Math.PI * RING_RADIUS;
const RING_DAYS = 30;
const RING_DASH = [3, 4];

// The drawn part of the ring as a stroke-dasharray: one solid arc, or the
// track's dash pattern cut off at `length`, so the dashes line up.
function ringDashes(length, dashed) {
  if (!dashed) return `${length} ${RING_LENGTH}`;
  const parts = [];
  for (let drawn = 0; drawn + RING_DASH[0] <= length; drawn += RING_DASH[0] + RING_DASH[1]) parts.push(...RING_DASH);
  return [...parts, 0, RING_LENGTH].join(' ');
}

function CountdownRing({ days, exact, tone }) {
  const number = formatNumberLocale(days);
  const unit = tp('{n} day|{n} days', days, { n: number }).replace(number, '').trim();
  const left = (Math.min(days, RING_DAYS) / RING_DAYS) * RING_LENGTH;
  return <span className={`program-ring ${exact ? '' : 'is-usual'} ${tone}`.trim()} aria-hidden="true" title={exact ? undefined : usualHint()}>
    <svg viewBox="0 0 60 60"><circle className="program-ring-track" cx="30" cy="30" r={RING_RADIUS} strokeDasharray={exact ? undefined : RING_DASH.join(' ')} />{left > 0 && <circle className="program-ring-left" cx="30" cy="30" r={RING_RADIUS} strokeDasharray={ringDashes(left, !exact)} />}</svg>
    <span className="program-ring-label"><b className={days > 99 ? 'is-long' : undefined}>{number}</b><small>{unit}</small></span>
  </span>;
}

function ProgramRow({ item, closed, due, today, saved, busy, onToggle, onOpen, countdown }) {
  const grades = compactGrades(programGrades(item)).map((grade) => (grade === 'gap' ? t('Gap year') : grade));
  const place = [item.city, item.country].filter(Boolean).join(', ') || (item.delivery_mode === 'online' ? t('Online') : '');
  const kind = item.program_type === 'national' ? 'National' : item.program_type === 'international' ? 'International' : 'To verify';
  // The catalog shows the date and counts down to real deadlines only; My List
  // (`countdown`) shows the days left instead of the date, usual dates included.
  const days = due && !closed && (due.exact || countdown) ? daysUntil(countdownDay(due, today)) : null;
  const tone = days != null ? dueTone(days) : '';
  const ring = countdown && days != null && days >= 0;
  const logo = programLogo(item);
  return <article className={`program-row ${closed ? 'is-closed' : ''}`.trim()}>
    {ring ? <CountdownRing days={days} exact={due.exact} tone={tone} /> : <DueTile due={due} closed={closed} tone={tone} />}
    <div className="program-row-body">
      <h3><button type="button" className="program-row-open" onClick={() => onOpen(item.id)}>{item.title}</button></h3>
      {due && <span className="sr-only">{ring ? `${due.exact ? '' : '≈ '}${dueLabel(days)}` : <ProgramDeadline item={item} closed={closed} />}</span>}
      <p className="program-row-byline">{logo && <img src={logo} alt="" loading="lazy" />}{item.provider && <><span className="program-row-provider">{item.provider}</span>{' '}</>}<span>{t(item.category)}</span>{' '}<span>{t(kind)}</span></p>
      <div className="program-row-facts">
        {countdown && due ? <span><CalendarDays size={15} aria-hidden="true" /> <ProgramDeadline item={item} closed={closed} /></span> : due?.detail && <span><CalendarDays size={15} aria-hidden="true" /> {item.deadline_text}</span>}
        {grades.length > 0 && <span><GraduationCap size={15} aria-hidden="true" /> {t('Grades')} {grades.join(', ')}</span>}
        {item.eligible_ages && <span><UsersRound size={15} aria-hidden="true" /> {t('Ages')} {item.eligible_ages}</span>}
        {place && <span><MapPin size={15} aria-hidden="true" /> {place}</span>}
        {item.delivery_mode !== 'unspecified' && <span><Monitor size={15} aria-hidden="true" /> {t(DELIVERY_LABELS[item.delivery_mode] || 'To verify')}</span>}
        {item.fee_usd != null && item.fee_usd !== '' && <span><DollarSign size={15} aria-hidden="true" /> {isFreeProgram(item) ? t('Free') : money(item.fee_usd)}</span>}
        {item.scholarship_available && <span className="program-row-aid" title={t(item.aid_details)}><HandCoins size={15} aria-hidden="true" /> {t('Financial aid available')}</span>}
        {isUnverifiedTelegramImport(item) && <span className="program-row-unverified"><TriangleAlert size={15} aria-hidden="true" /> {t('From Telegram, not yet verified')}</span>}
      </div>
      {(item.description || item.requirements) && <details className="program-row-details"><summary>{t('Requirements')}</summary>{item.description && <p>{t(item.description)}</p>}{item.requirements && <p>{t(item.requirements)}</p>}</details>}
    </div>
    <div className="program-row-actions">
      {!countdown && days != null && days >= 0 && <span className={`program-row-countdown ${tone}`.trim()}>{dueLabel(days)}</span>}
      <button type="button" className="program-icon-button" aria-pressed={saved} aria-label={saved ? t('In My List') : t('Add to My List')} title={saved ? t('In My List') : t('Add to My List')} disabled={busy} onClick={onToggle}><Bookmark size={18} fill={saved ? 'currentColor' : 'none'} aria-hidden="true" /></button>
      {item.application_url && <a className="program-icon-button" href={item.application_url} target="_blank" rel="noreferrer" aria-label={`${t('View program')}: ${item.title}`} title={t('View program')}><ExternalLink size={18} aria-hidden="true" /></a>}
    </div>
  </article>;
}

// LinkedIn people search for the program's core name: "Yale Young Global Scholars (YYGS) 2027" -> "Yale Young Global Scholars".
const programCore = (title) => String(title || '').split(' – ')[0].replace(/\s*\(.*?\)/g, '').replace(/\b20\d\d\b/g, '').replace(/\s+/g, ' ').trim();
const linkHost = (link) => { try { return new URL(link).hostname.replace(/^www\./, ''); } catch { return link; } };
const linkedInSearch = (query) => `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(query)}`;

function DetailFact({ icon: Icon, title, children }) {
  if (!children) return null;
  return <div className="nb-pd-fact"><span className="nb-pd-fact-icon" aria-hidden="true"><Icon size={18} /></span><span><small>{title}</small><b>{children}</b></span></div>;
}

// A titled bullet list ("What you get"). Renders nothing when the program has no items.
function DetailList({ title, items, icon: Icon }) {
  const list = (Array.isArray(items) ? items : []).map((entry) => (typeof entry === 'string' || typeof entry === 'number' ? String(entry).trim() : '')).filter(Boolean);
  if (!list.length) return null;
  return <GlassCard tone="solid" title={title} headingLevel="h3"><ul className="nb-pd-list">{list.map((entry, index) => <li key={`${index}-${entry}`}><Icon size={16} aria-hidden="true" /><span>{entry}</span></li>)}</ul></GlassCard>;
}

// Fixed team formats are translated; any other researched wording stays as written (English for now).
const teamLabel = (value) => {
  const text = typeof value === 'string' ? value.trim() : '';
  if (/^individual( applicants?| applications?| attendees| delegates)?$/i.test(text)) return t('Individual');
  const range = text.match(/^(individual or )?teams? of (\d+)\s*[–-]\s*(\d+)(?: students| members)?$/i);
  if (range) return range[1] ? t('Individual or teams of {min}–{max}', { min: range[2], max: range[3] }) : t('Teams of {min}–{max}', { min: range[2], max: range[3] });
  if (/^individual or teams$/i.test(text)) return t('Individual or teams');
  const upTo = text.match(/^(individual or )?teams? of up to (\d+)$/i);
  if (upTo) return upTo[1] ? t('Individual or teams of up to {n}', { n: upTo[2] }) : t('Teams of up to {n}', { n: upTo[2] });
  return text;
};

const roleLabel = (role) => {
  const key = typeof role === 'string' ? role.toLowerCase() : '';
  if (/winner|laureate|champion|medal/.test(key)) return t('Program winner');
  if (/finalist/.test(key)) return t('Program finalist');
  return key ? t('Program participant') : '';
};

// Up to five public past participants from Uzbekistan, each with a LinkedIn profile and the page that shows the participation.
function PastParticipants({ people, core }) {
  // Defensive: stored data is edited through the admin API, so a bad entry is skipped, never allowed to crash the page.
  const webLink = (value) => (typeof value === 'string' && /^https?:\/\//i.test(value.trim()) ? value.trim() : '');
  const list = (Array.isArray(people) ? people : []).map((person) => ({
    name: typeof person?.name === 'string' ? person.name.trim() : '', role: person?.role, year: Number.isInteger(person?.year) ? person.year : '',
    linkedin_url: webLink(person?.linkedin_url), source_url: webLink(person?.source_url),
  })).filter((person) => person.name).slice(0, 5);
  if (!list.length) return <GlassCard tone="solid" title={t('Past participants and winners')} headingLevel="h3">
    <p className="nb-pd-sub">{t('See how past participants and winners describe this program on LinkedIn and what they did next.')}</p>
    <div className="nb-pd-people">{[[t('Participants on LinkedIn'), core], [t('Winners on LinkedIn'), `${core} winner`]].map(([title, query]) => <a key={title} href={linkedInSearch(query)} target="_blank" rel="noreferrer"><span className="nb-pd-in" aria-hidden="true">in</span><span><b>{title}</b><small>“{query}”</small></span><ArrowUpRight size={16} aria-hidden="true" /></a>)}</div>
    <p className="nb-pd-note">{t('Opens LinkedIn search in a new tab · you may need to sign in')}</p>
  </GlassCard>;
  return <GlassCard tone="solid" title={t('Past participants from Uzbekistan')} headingLevel="h3">
    <p className="nb-pd-sub">{t('Students from Uzbekistan who took part in this program, from public pages.')}</p>
    <ul className="nb-pd-alumni">{list.map((person, index) => <li key={`${index}-${person.name}`}>
      <span className="nb-pd-avatar" aria-hidden="true">{person.name.trim().charAt(0).toUpperCase()}</span>
      <span className="nb-pd-alumni-text"><b>{person.name}</b><small>{[roleLabel(person.role), person.year].filter(Boolean).join(' · ')}</small></span>
      <span className="nb-pd-alumni-links">
        {person.linkedin_url && <a className="nb-pd-li" href={person.linkedin_url} target="_blank" rel="noreferrer noopener" aria-label={`${t('LinkedIn profile')}: ${person.name}`}><span className="nb-pd-in" aria-hidden="true">in</span>LinkedIn</a>}
        {person.source_url && <a className="nb-pd-src" href={person.source_url} target="_blank" rel="noreferrer noopener" aria-label={`${t('Source')}: ${person.name}`}>{t('Source')}<ArrowUpRight size={13} aria-hidden="true" /></a>}
      </span>
    </li>)}</ul>
    <p className="nb-pd-note">{t('Opens in a new tab · LinkedIn may ask you to sign in')}</p>
  </GlassCard>;
}

// A whole program page inside Programs: everything the catalog row holds, the date state, people
// links and a few other open programs. It only reads data the page already has.
function ProgramDetail({ entry, similar, saved, saveBusy, today, onToggle, onBack, onOpen }) {
  const { item, closed, due } = entry;
  const headingRef = useRef(null);
  useEffect(() => { headingRef.current?.focus({ preventScroll: true }); window.scrollTo({ top: 0, left: 0, behavior: 'auto' }); }, [item.id]);
  const kind = item.program_type === 'national' ? 'National' : item.program_type === 'international' ? 'International' : 'To verify';
  const grades = compactGrades(programGrades(item)).map((grade) => (grade === 'gap' ? t('Gap year') : grade));
  const place = [item.city, item.country].filter(Boolean).join(', ');
  const delivery = item.delivery_mode && item.delivery_mode !== 'unspecified' ? t(DELIVERY_LABELS[item.delivery_mode] || 'To verify') : '';
  // Open to international students: only said when the official site says so (null = unknown, nothing shown).
  const openTo = [item.open_to_international === true ? t('Open to international students') : item.open_to_international === false ? t('Not open to international students') : '',
    item.open_to_uzbekistan === true ? t('Open to students from Uzbekistan') : item.open_to_uzbekistan === false ? t('Not open to students from Uzbekistan') : ''];
  const who = [grades.length ? `${t('Grades')} ${grades.join(', ')}` : '', item.eligible_ages ? `${t('Ages')} ${item.eligible_ages}` : '', ...openTo].filter(Boolean).join(' · ');
  const fee = item.fee_usd != null && item.fee_usd !== '' ? (isFreeProgram(item) ? t('Free') : money(item.fee_usd)) : '';
  const cost = [fee, extraFeeText(item, fee), item.scholarship_available ? t('Financial aid available') : ''].filter(Boolean).join(' · ');
  const dates = item.start_date ? [dateText(item.start_date), item.end_date && item.end_date !== item.start_date ? dateText(item.end_date) : ''].filter(Boolean).join(' – ') : '';
  const sources = [...new Set([item.source_url, ...(item.official_sources || [])].filter(Boolean))];
  const verified = !item.needs_verification && Boolean(item.official_verified_at);
  const days = due && !closed ? daysUntil(countdownDay(due, today)) : null;
  const tone = days != null ? dueTone(days) : '';
  const core = programCore(item.title);
  const logo = programLogo(item);
  const state = closed ? 'Closed' : due?.exact ? 'Date confirmed' : due ? 'Expected · based on last year' : 'Date not announced yet';
  const url = item.application_url;
  const whoList = Array.isArray(item.who_can_apply) ? item.who_can_apply : [];
  // The Telegram-post style header: country (with flag), format, age group, team, cost, deadline. Only what is known.
  const flag = countryFlag(item.country);
  const ageGroup = item.eligible_ages ? item.eligible_ages : grades.length ? `${t('Grades')} ${grades.join(', ')}` : '';
  const keyFacts = [
    [t('Country'), item.country ? `${flag ? `${flag} ` : ''}${item.country}` : ''],
    [t('Format'), delivery],
    [t('Age group'), ageGroup],
    [t('Team'), teamLabel(item.team_format)],
    [t('Cost'), cost],
    [t('Deadline'), due ? dateText(due.date) : ''],
  ].filter(([, value]) => value);
  const deadline =<section className={`nb-pd-deadline ${closed ? 'is-over' : tone === 'hot' ? 'is-hot' : ''}`.trim()} aria-label={t('Deadline')}>
    {due ? <span className="nb-pd-cal" aria-hidden="true">{due.day && <b>{formatNumberLocale(due.day)}</b>}<small>{formatDateLocale(due.date, { month: 'short' })}</small></span> : <span className="nb-pd-cal is-none" aria-hidden="true"><CalendarSearch size={22} /></span>}
    <div><small>{t('Deadline')}</small><b><ProgramDeadline item={item} closed={closed} /></b><span className={`nb-pd-state ${due?.exact && !closed ? 'is-ok' : ''}`.trim()}>{t(state)}</span></div>
    {days != null && days >= 0 && <em className={`nb-pd-left ${tone}`.trim()}>{dueLabel(days)}</em>}
  </section>;
  return <div className="section-stack student-portal programs-page nb-bridge nb-programs nb-pd">
    <PageHeader title={t('Programs')} subtitle={t('National and international opportunity catalog')} />
    <button type="button" className="nb-pd-back" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" />{t('All programs')}</button>
    <GlassCard tone="hero" as="header" className="nb-pd-hero">
      <span className="nb-pd-gem" aria-hidden="true">{logo ? <img src={logo} alt="" /> : <Award size={26} />}</span>
      <div><p className="nb-prog-eyebrow">{[t(item.category), t(kind)].filter(Boolean).join(' · ')}</p><h2 ref={headingRef} tabIndex={-1}>{item.title}</h2>{item.provider && <small>{item.provider}</small>}</div>
    </GlassCard>
    <div className="nb-pd-grid">
      <div className="nb-pd-main">
        {isUnverifiedTelegramImport(item) && <p className="nb-pd-warn" role="note"><TriangleAlert size={18} aria-hidden="true" /><span><b>{t('From Telegram, not yet verified')}.</b> {t('We added this from a public Telegram channel and have not checked it yet. Confirm the details on the official page before you apply.')}{item.source_url && <> <a href={item.source_url} target="_blank" rel="noreferrer">{t('Original Telegram post')}</a></>}</span></p>}
        {!due?.exact && !closed && <p className="nb-pd-warn" role="note"><TriangleAlert size={18} aria-hidden="true" /><span>{t("We haven't confirmed this year's dates. Check the official site before you apply.")}</span></p>}
        {keyFacts.length > 0 && <ul className="nb-pd-keyfacts" aria-label={t('Key facts')}>{keyFacts.map(([label, value]) => <li key={label}><small>{label}</small><b>{value}</b></li>)}</ul>}
        {(item.overview || item.description) && <GlassCard tone="solid" title={t('About this program')} headingLevel="h3"><p className="nb-pd-about">{t(item.overview || item.description)}</p></GlassCard>}
        <DetailList title={t('What you get')} items={item.benefits} icon={Gift} />
        {whoList.length > 0 ? <DetailList title={t('Who can apply')} items={whoList} icon={UsersRound} /> : null}
        <DetailList title={t('Requirements')} items={item.requirements_list} icon={ListChecks} />
        {item.selection_process && <GlassCard tone="solid" title={t('How selection works')} headingLevel="h3"><p className="nb-pd-about">{item.selection_process}</p></GlassCard>}
        <div className="nb-pd-facts">
          {whoList.length === 0 && <DetailFact icon={UsersRound} title={t('Who can apply')}>{who}</DetailFact>}
          <DetailFact icon={MapPin} title={t('Format and place')}>{[delivery, place].filter(Boolean).join(' · ')}</DetailFact>
          <DetailFact icon={CalendarDays} title={t('Program dates')}>{dates}</DetailFact>
          <DetailFact icon={DollarSign} title={t('Cost')}>{cost}</DetailFact>
          <DetailFact icon={HandCoins} title={t('Financial aid')}>{item.aid_details ? t(item.aid_details) : ''}</DetailFact>
          {!(item.requirements_list || []).length && <DetailFact icon={ListChecks} title={t('Requirements')}>{item.requirements ? t(item.requirements) : ''}</DetailFact>}
        </div>
        {verified && sources.length > 0 && <p className="nb-pd-note">{t('Official source')}: {sources.slice(0, 3).map((link, index) => <span key={link}>{index > 0 && ' · '}<a href={link} target="_blank" rel="noreferrer">{linkHost(link)}</a></span>)} · {tx`Checked on ${dateText(item.official_verified_at)}`}</p>}
        <PastParticipants people={item.past_participants} core={core} />
      </div>
      <aside className="nb-pd-side">
        {deadline}
        <GlassCard tone="solid" title={t('Ready to apply?')} headingLevel="h3" className="nb-pd-cta">
          <p className="nb-pd-sub">{t('Read the full rules and apply on the official website.')}</p>
          <BlueButton variant="ghost" icon={Bookmark} aria-pressed={saved} disabled={saveBusy} onClick={onToggle}>{saved ? t('In My List') : t('Add to My List')}</BlueButton>
          {url ? <BlueButton href={url} target="_blank" rel="noreferrer" iconRight={ExternalLink}>{t('Go to the official website')}</BlueButton> : <span className="nb-pd-nosite">{t('No official website listed')}</span>}
        </GlassCard>
        {similar.length > 0 && <GlassCard tone="solid" title={t('Similar open programs')} headingLevel="h3" className="nb-pd-rec">
          <p className="nb-pd-sub">{t('Other programs you can still apply to.')}</p>
          <ul>{similar.map(({ item: other, due: otherDue }) => <li key={other.id}><button type="button" onClick={() => onOpen(other.id)}><span className="nb-pd-rd" aria-hidden="true"><b>{otherDue.day ? formatNumberLocale(otherDue.day) : ''}</b><small>{formatDateLocale(otherDue.date, { month: 'short' })}</small></span><span className="nb-pd-rt"><b>{other.title}</b><small>{t(other.category)} · {dueLabel(daysUntil(otherDue.date))}</small></span><ChevronRight size={16} aria-hidden="true" /></button></li>)}</ul>
        </GlassCard>}
      </aside>
    </div>
  </div>;
}

// A filter pill that opens a small menu under itself. `children(close)`
// renders the options; picking one closes the menu.
function FilterMenu({ label, value, children }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const root = ref.current;
    (root?.querySelector('.program-pill-menu input:checked, .program-pill-menu [aria-pressed="true"]')
      || root?.querySelector('.program-pill-menu input:not(:disabled), .program-pill-menu button:not(:disabled)'))?.focus();
    const onPointer = (event) => { if (!root?.contains(event.target)) setOpen(false); };
    const onKey = (event) => { if (event.key === 'Escape') { setOpen(false); root?.querySelector('button')?.focus(); } };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('pointerdown', onPointer); document.removeEventListener('keydown', onKey); };
  }, [open]);
  const close = () => { setOpen(false); ref.current?.querySelector('button')?.focus(); };
  return <div className={`program-pill ${value ? 'is-active' : ''}`.trim()} ref={ref}>
    <button type="button" className="program-pill-button" aria-expanded={open} onClick={() => setOpen((current) => !current)}>{label}{value && <b>{value}</b>}<ChevronDown size={15} aria-hidden="true" /></button>
    {open && <div className="program-pill-menu" role="group" aria-label={label}>{children(close)}</div>}
  </div>;
}

export function ProgramsPage({ data, query, search, navigate, notify }) {
  const programId = useMemo(() => { const id = Number(new URLSearchParams(search || '').get('program')); return Number.isInteger(id) && id > 0 ? id : null; }, [search]);
  const [filters, setFilters] = useUrlFilters(search, navigate);
  const [savedIds, setSavedIds] = useState(new Set());
  const [savedLoading, setSavedLoading] = useState(true);
  const [savedKnown, setSavedKnown] = useState(false);
  const [savedError, setSavedError] = useState('');
  const [savedAttempt, setSavedAttempt] = useState(0);
  const [savingId, setSavingId] = useState(null);
  const [onlySaved, setOnlySaved] = useState(false);
  // Extra list narrowing from the top tiles and the Free pill; the URL filters stay as they are.
  const [onlyOpen, setOnlyOpen] = useState(false);
  const [onlyFree, setOnlyFree] = useState(false);
  // The open program lives in the URL (`?program=<id>`), so Back and the Programs nav item close it.
  const detailId = programId;
  const setDetailId = useCallback((id) => {
    const next = withQuery(search, { program: id });
    navigate(`${window.location.pathname}${next}${window.location.hash}`);
  }, [search, navigate]);
  const [radarOpen, setRadarOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const sheetRef = useRef(null);
  const toggleRef = useRef(null);
  const catalog = data.opportunityPrograms;
  // The viewer's own calendar day: UTC would still say yesterday in Tashkent before 05:00.
  const today = useMemo(() => localDateKey(), []);
  const localeTag = locale();
  const { programs, counts } = useMemo(
    () => filterPrograms(catalog, filters, { today, query, translate: t, localeTag }),
    [catalog, filters, today, query, localeTag],
  );
  // Catalog-wide numbers for the tiles and the featured card: they ignore the filters below.
  const overall = useMemo(() => filterPrograms(catalog, PROGRAM_FILTER_DEFAULTS, { today, translate: t, localeTag }), [catalog, today, localeTag]);
  // Every loaded program, closed ones included, so a closed row's title still opens its details.
  const everyProgram = useMemo(() => filterPrograms(catalog, { ...PROGRAM_FILTER_DEFAULTS, open: false }, { today, translate: t, localeTag }).programs, [catalog, today, localeTag]);
  const openNow = useMemo(() => overall.programs.filter(({ due }) => due?.exact).length, [overall]);
  const featured = useMemo(() => overall.programs.find(({ closed, due }) => !closed && due?.exact) || null, [overall]);
  const nextUp = useMemo(() => overall.programs.filter(({ closed, due }) => !closed && due?.exact).slice(1, 5), [overall]);
  const categories = useMemo(() => [...new Set(catalog.map((item) => item.category).filter(Boolean))].sort(), [catalog]);
  const activeCount = activeProgramFilterCount(filters);
  const filtered = hasProgramFilters(filters);
  const update = (patch) => setFilters((current) => ({ ...current, ...patch }));
  const reset = () => { setFilters({ ...PROGRAM_FILTER_DEFAULTS }); setOnlyOpen(false); setOnlyFree(false); };
  // A category that the new type does not have would only empty the list.
  const chooseType = (type) => setFilters((current) => ({
    ...current, type,
    category: current.category === 'all' || catalog.some((item) => (type === 'all' || item.program_type === type) && item.category === current.category) ? current.category : 'all',
  }));

  useEffect(() => {
    if (!sheetOpen) return undefined;
    sheetRef.current?.querySelector('button, select, input')?.focus();
    const onKey = (event) => {if (event.key === 'Escape') setSheetOpen(false);};
    document.addEventListener('keydown', onKey);
    const toggle = toggleRef.current;
    return () => {
      document.removeEventListener('keydown', onKey);
      // Closing the sheet (Escape, backdrop or the close button) hands focus
      // back to the button that opened it.
      if (toggle?.isConnected) toggle.focus();
    };
  }, [sheetOpen]);

  const count = (value) => formatNumberLocale(value || 0);

  useEffect(() => {
    let active = true;
    setSavedLoading(true); setSavedError('');
    request('/opportunity-programs/saved/').then((result) => {
      if (active) { setSavedIds(new Set(result.program_ids)); setSavedKnown(true); }
    }).catch((error) => { if (active) setSavedError(error.message); }).finally(() => {
      if (active) setSavedLoading(false);
    });
    return () => { active = false; };
  }, [savedAttempt]);

  async function toggleSaved(item) {
    if (savingId != null || savedLoading || !savedKnown) return;
    const wasSaved = savedIds.has(item.id);
    setSavingId(item.id);
    try {
      await request(`/opportunity-programs/${item.id}/save/`, { method: wasSaved ? 'DELETE' : 'POST' });
      setSavedIds((current) => {
        const next = new Set(current);
        if (wasSaved) next.delete(item.id); else next.add(item.id);
        return next;
      });
      notify?.(wasSaved ? t('Removed from My List.') : t('Added to My List.'));
    } catch (error) { notify?.(error.message, 'error'); }
    finally { setSavingId(null); }
  }

  const isFree = isFreeProgram;
  const freeCount = programs.filter(({ item }) => isFree(item)).length;
  // Program deadlines for the radar, from what this page already holds: programs with a confirmed
  // date that are still open, plus saved programs that only have a usual (approximate) date.
  const radarPrograms = useMemo(() => everyProgram.filter(({ item, closed, due }) => due && !closed && (due.exact || savedIds.has(item.id)))
    .map(({ item, due }) => ({ id: item.id, title: item.title, date: due.date, exact: due.exact, saved: savedIds.has(item.id) })), [everyProgram, savedIds]);
  const shownPrograms = programs.filter(({ item, closed, due }) => (!onlySaved || savedIds.has(item.id)) && (!onlyOpen || (!closed && due?.exact)) && (!onlyFree || isFree(item)));
  const resultText = tp('{count} program|{count} programs', shownPrograms.length, { count: shownPrograms.length });
  const narrowed = filtered || onlyOpen || onlyFree;
  const detail = detailId != null ? everyProgram.find(({ item }) => item.id === detailId) : null;
  if (detail) {
    const similar = overall.programs.filter(({ item, closed, due }) => item.id !== detail.item.id && !closed && due?.exact);
    const near = [...similar.filter(({ item }) => item.category === detail.item.category), ...similar.filter(({ item }) => item.category !== detail.item.category)].slice(0, 4);
    return <ProgramDetail entry={detail} similar={near} today={today} saved={savedIds.has(detail.item.id)} saveBusy={savedLoading || !savedKnown || savingId === detail.item.id} onToggle={() => toggleSaved(detail.item)} onBack={() => setDetailId(null)} onOpen={setDetailId} />;
  }

  const pickedGrades = selectedGrades(filters.grade);
  const gradeLabel = (grade) => (grade === 'gap' ? t('Gap year') : grade);
  // Several grades can be on at once; the pills toggle without closing their menu.
  const gradeChips = <div className="program-grade-chips">{PROGRAM_GRADES.map((grade) => <button key={grade} type="button" aria-pressed={pickedGrades.includes(grade)} disabled={!counts.grade[grade] && !pickedGrades.includes(grade)} onClick={() => update({ grade: toggleGrade(filters.grade, grade) })}>{gradeLabel(grade)}</button>)}</div>;
  const typeLabel = { all: 'All programs', national: 'National', international: 'International' };
  const rail = <aside id="program-filters" ref={sheetRef} className={`program-rail ${sheetOpen ? 'is-open' : ''}`.trim()} aria-label={t('Filters')}>
    <header className="program-rail-head"><b>{t('Filters')}</b>{filtered && <button type="button" className="link-button" onClick={reset}>{t('Clear')}</button>}<button type="button" className="icon-button program-rail-close" onClick={() => setSheetOpen(false)} aria-label={t('Close filters')}><X size={18} /></button></header>
    <fieldset className="filter-set"><legend>{t('Program type')}</legend>{['all', 'national', 'international'].map((type) => <FilterOption key={type} type="radio" name="program-type" checked={filters.type === type} onChange={() => chooseType(type)} count={counts.type[type] || 0}>{t(typeLabel[type])}</FilterOption>)}</fieldset>
    <fieldset className="filter-set"><legend>{t('Grade')}</legend>{gradeChips}</fieldset>
    <fieldset className="filter-set"><legend>{t('Delivery')}</legend>{['all', ...PROGRAM_DELIVERY].map((mode) => <FilterOption key={mode} type="radio" name="program-delivery" checked={filters.delivery === mode} disabled={mode !== 'all' && !counts.delivery[mode] && filters.delivery !== mode} onChange={() => update({ delivery: mode })} count={mode === 'all' ? null : counts.delivery[mode] || 0}>{mode === 'all' ? t('All formats') : t(DELIVERY_LABELS[mode])}</FilterOption>)}</fieldset>
    <fieldset className="filter-set"><legend>{t('Category')}</legend><FilterOption type="radio" name="program-category" checked={filters.category === 'all'} onChange={() => update({ category: 'all' })}>{t('All categories')}</FilterOption>{[...new Set([...categories, ...(filters.category === 'all' ? [] : [filters.category])])].map((category) => <FilterOption key={category} type="radio" name="program-category" checked={filters.category === category} disabled={!counts.category[category] && filters.category !== category} onChange={() => update({ category })} count={counts.category[category] || 0}>{t(category)}</FilterOption>)}</fieldset>
    <fieldset className="filter-set"><legend className="sr-only">{t('More filters')}</legend>
      <FilterOption checked={filters.aid} onChange={(event) => update({ aid: event.target.checked })} count={counts.aid}>{t('Scholarship available')}</FilterOption>
      {(freeCount > 0 || onlyFree) && <FilterOption checked={onlyFree} onChange={(event) => setOnlyFree(event.target.checked)} count={freeCount}>{t('Free')}</FilterOption>}
      {(counts.closed > 0 || !filters.open) && <FilterOption checked={filters.open} onChange={(event) => update({ open: event.target.checked })} count={counts.closed}>{t('Hide closed')}</FilterOption>}
    </fieldset>
    <footer className="program-rail-foot"><button type="button" className="button primary" onClick={() => setSheetOpen(false)}>{tp('Show {count} program|Show {count} programs', shownPrograms.length, { count: shownPrograms.length })}</button></footer>
  </aside>;

  // Wide screens: filter pills under the search box (the bottom-right corner
  // belongs to the assistant launcher). Phones: the same filters in a sheet.
  const categoryOptions = [...new Set([...categories, ...(filters.category === 'all' ? [] : [filters.category])])];
  const filterBar = <div className="program-filterbar" role="group" aria-label={t('Filters')}>
    <FilterMenu label={t('Program type')} value={filters.type === 'all' ? '' : t(typeLabel[filters.type])}>{(close) => ['all', 'national', 'international'].map((type) => <FilterOption key={type} type="radio" name="program-type-menu" checked={filters.type === type} onChange={() => { chooseType(type); close(); }} count={counts.type[type] || 0}>{t(typeLabel[type])}</FilterOption>)}</FilterMenu>
    <FilterMenu label={t('Grade')} value={pickedGrades.map(gradeLabel).join(', ')}>{() => gradeChips}</FilterMenu>
    <FilterMenu label={t('Delivery')} value={filters.delivery === 'all' ? '' : t(DELIVERY_LABELS[filters.delivery])}>{(close) => ['all', ...PROGRAM_DELIVERY].map((mode) => <FilterOption key={mode} type="radio" name="program-delivery-menu" checked={filters.delivery === mode} disabled={mode !== 'all' && !counts.delivery[mode] && filters.delivery !== mode} onChange={() => { update({ delivery: mode }); close(); }} count={mode === 'all' ? null : counts.delivery[mode] || 0}>{mode === 'all' ? t('All formats') : t(DELIVERY_LABELS[mode])}</FilterOption>)}</FilterMenu>
    <FilterMenu label={t('Category')} value={filters.category === 'all' ? '' : t(filters.category)}>{(close) => <><FilterOption type="radio" name="program-category-menu" checked={filters.category === 'all'} onChange={() => { update({ category: 'all' }); close(); }}>{t('All categories')}</FilterOption>{categoryOptions.map((category) => <FilterOption key={category} type="radio" name="program-category-menu" checked={filters.category === category} disabled={!counts.category[category] && filters.category !== category} onChange={() => { update({ category }); close(); }} count={counts.category[category] || 0}>{t(category)}</FilterOption>)}</>}</FilterMenu>
    <button type="button" className="program-pill-toggle" aria-pressed={filters.aid} onClick={() => update({ aid: !filters.aid })}>{filters.aid && <Check size={15} aria-hidden="true" />}{t('Scholarship available')}<span>{count(counts.aid)}</span></button>
    {(freeCount > 0 || onlyFree) && <button type="button" className="program-pill-toggle" aria-pressed={onlyFree} onClick={() => setOnlyFree((value) => !value)}>{onlyFree && <Check size={15} aria-hidden="true" />}{t('Free')}<span>{count(freeCount)}</span></button>}
    {(counts.closed > 0 || !filters.open) && <button type="button" className="program-pill-toggle" aria-pressed={filters.open} onClick={() => update({ open: !filters.open })}>{filters.open && <Check size={15} aria-hidden="true" />}{t('Hide closed')}<span>{count(counts.closed)}</span></button>}
    {narrowed && <button type="button" className="link-button program-filterbar-clear" onClick={reset}>{t('Clear')}</button>}
  </div>;

  const featuredDays = featured ? daysUntil(featured.due.date) : null;
  const featuredSaved = featured ? savedIds.has(featured.item.id) : false;
  return <div className="section-stack student-portal programs-page catalog-programs program-database nb-bridge nb-programs">
    <PageHeader title={t('Programs')} subtitle={t('National and international opportunity catalog')} />
    <div className={`nb-prog-top${featured ? '' : ' is-plain'}`}>
      {featured && <GlassCard tone="hero" as="section" className={`nb-prog-featured${nextUp.length ? ' has-next' : ''}`} aria-label={t('Next deadline')}>
        <div className="nb-prog-featured-main">
          <span className="nb-prog-eyebrow"><Star size={14} aria-hidden="true" />{t('Featured · next deadline')}</span>
          <div className="nb-prog-featured-card">
            <span className="nb-prog-featured-date" aria-hidden="true"><b>{featured.due.day ? formatNumberLocale(featured.due.day) : ''}</b><small>{formatDateLocale(featured.due.date, { month: 'short' })}</small></span>
            <div>
              <h2>{featured.item.title}</h2>
              <p>{[featured.item.provider, t(featured.item.category), t(featured.item.program_type === 'national' ? 'National' : 'International')].filter(Boolean).join(' · ')}</p>
            </div>
          </div>
          <DaysChip days={featuredDays} />
          <div className="nb-prog-featured-actions">
            <BlueButton size="sm" arrow onClick={() => setDetailId(featured.item.id)}>{t('Details')}</BlueButton>
            {featured.item.application_url && <BlueButton variant="ghost" size="sm" href={featured.item.application_url} target="_blank" rel="noreferrer" iconRight={ExternalLink}>{t('View program')}</BlueButton>}
            <BlueButton variant="ghost" size="sm" icon={Bookmark} aria-pressed={featuredSaved} disabled={savedLoading || !savedKnown || savingId === featured.item.id} onClick={() => toggleSaved(featured.item)}>{featuredSaved ? t('In My List') : t('Add to My List')}</BlueButton>
          </div>
        </div>
        {nextUp.length > 0 && <div className="nb-prog-nextup"><span className="nb-prog-eyebrow"><Clock3 size={14} aria-hidden="true" />{t('Next up')}</span><ul>{nextUp.map(({ item, due }) => <li key={item.id}><button type="button" className="nb-prog-nextup-open" onClick={() => setDetailId(item.id)}><span className="nb-prog-nextup-date" aria-hidden="true"><b>{due.day ? formatNumberLocale(due.day) : ''}</b><small>{formatDateLocale(due.date, { month: 'short' })}</small></span><span className="nb-prog-nextup-copy"><b>{item.title}</b><small>{tp('{n} day left|{n} days left', daysUntil(due.date), { n: formatNumberLocale(daysUntil(due.date)) })}</small></span></button></li>)}</ul><DeadlineRadarButton onClick={() => setRadarOpen(true)} /></div>}
        {/* No other upcoming deadline to list: the radar stays reachable for this one and any saved program. */}
        {nextUp.length === 0 && <div className="nb-prog-nextup is-radar-only"><DeadlineRadarButton onClick={() => setRadarOpen(true)} /></div>}
      </GlassCard>}
      {!featured && radarPrograms.length > 0 && <div className="nb-prog-radar-only"><DeadlineRadarButton onClick={() => setRadarOpen(true)} /></div>}
      <KpiRow columns={4} className="nb-prog-kpis">
        <KpiTile tone={0} icon={Award} value={count(openNow)} label={t('Open for applications')} onClick={() => setOnlyOpen((value) => !value)} actionLabel={`${t('Open for applications')}: ${openNow}`} />
        <KpiTile tone={1} icon={Globe2} value={count(overall.programs.length)} label={t('Open programs in the catalog')} onClick={() => { reset(); setOnlySaved(false); }} actionLabel={`${t('Open programs in the catalog')}: ${overall.programs.length}`} />
        <KpiTile tone={2} icon={Bookmark} value={savedKnown ? count(savedIds.size) : '—'} label={t('My List')} onClick={() => setOnlySaved((value) => !value)} actionLabel={`${t('My List')}: ${savedKnown ? savedIds.size : '—'}`} />
        <KpiTile tone={3} icon={Heart} value={count(overall.counts.aid)} label={t('Scholarship available')} onClick={() => update({ aid: !filters.aid })} actionLabel={`${t('Scholarship available')}: ${overall.counts.aid}`} />
      </KpiRow>
    </div>
    <div className="program-layout">
    <div className="program-main">
    <div className="program-topbar">
      <label className="search program-search"><Search size={19} aria-hidden="true" /><input type="search" value={filters.q} maxLength={100} onChange={(event) => update({ q: event.target.value })} placeholder={t('Search programs')} aria-label={t('Search programs')} />{filters.q && <button type="button" className="search-clear" onClick={() => update({ q: '' })} aria-label={t('Clear search')}><X size={15} /></button>}</label>
      <button ref={toggleRef} type="button" className="button quiet program-rail-toggle" onClick={() => setSheetOpen(true)} aria-expanded={sheetOpen} aria-controls="program-filters"><SlidersHorizontal size={18} /> {t('Filters')}{activeCount > 0 && <span className="program-filter-badge">{count(activeCount)}</span>}</button>
    </div>
    {filterBar}

    <div className="program-results-bar"><span role="status" aria-live="polite">{onlySaved && !savedKnown ? '—' : onlySaved ? tp('{count} saved program|{count} saved programs', shownPrograms.length, { count: shownPrograms.length }) : resultText}</span><div className="catalog-list-controls"><button type="button" className={`button quiet small ${onlySaved ? 'is-active' : ''}`} aria-pressed={onlySaved} onClick={() => setOnlySaved((value) => !value)}><Bookmark size={16} /> {t('My List')} <span>{savedKnown ? savedIds.size : '—'}</span></button></div></div>

    {savedError && <InlineLoadError message={savedError} onRetry={() => setSavedAttempt((value) => value + 1)} />}
    {savedLoading && onlySaved && <p role="status">{t('Loading…')}</p>}
    <div className="program-timeline">{groupProgramsByDeadline(shownPrograms).map(({ key, entries }) => <section className="program-month" key={key} aria-labelledby={`program-month-${key}`}>
      <h2 className="program-month-head" id={`program-month-${key}`}><span>{key === 'closed' ? t('Closed') : key === 'undated' ? t('Deadline on the official page') : formatDateLocale(`${key}-01`, { month: 'long', year: 'numeric' })}</span><small>{tp('{count} program|{count} programs', entries.length, { count: entries.length })}</small></h2>
      {entries.map(({ item, closed, due }) => <ProgramRow key={item.id} item={item} closed={closed} due={due} today={today} saved={savedIds.has(item.id)} busy={savedLoading || !savedKnown || savingId === item.id} onToggle={() => toggleSaved(item)} onOpen={setDetailId} countdown={onlySaved} />)}
    </section>)}{!shownPrograms.length && (!onlySaved || savedKnown) && <div className="program-empty"><Empty text={onlySaved ? t('No saved programs match these filters.') : t('No programs match these filters.')} />{onlySaved ? <button type="button" className="button primary small" onClick={() => setOnlySaved(false)}>{t('Browse programs')}</button> : narrowed && <><p>{t('Try another search or remove a filter.')}</p><button type="button" className="button primary small" onClick={reset}>{t('Reset filters')}</button></>}</div>}</div>
    </div>
    {sheetOpen && <div className="program-sheet-backdrop" onClick={() => setSheetOpen(false)} aria-hidden="true" />}
    {rail}
    </div>
    <DeadlineRadar open={radarOpen} onClose={() => setRadarOpen(false)} applications={data.applications || []} applicationsLoaded={(data.applications || []).length > 0} onOpenApplications={() => { setRadarOpen(false); navigate(PAGE_PATHS.applications); }} programs={radarPrograms} onOpenProgram={(id) => { setRadarOpen(false); setDetailId(id); }} onOpen={() => { setRadarOpen(false); navigate(PAGE_PATHS.applications); }} />
  </div>;
}
