import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRight, Bookmark, CalendarPlus, Check, CheckCircle2, ChevronDown, ChevronUp, ClipboardCheck, Clock3, Filter, GraduationCap, Pencil, Plus, RefreshCw, Search, Trash2, X } from 'lucide-react';
import { api } from '../api';
import { formatNumberLocale, parseDateValue, t, tp, tx } from '../i18n';
import { Empty, Modal } from '../components/ui';
import { FilterOption, ScoreBreakdown, TierBand } from '../components/college';
import { clockText, localDateKey, money } from '../lib/format';
import { ownStudent } from '../lib/labels';
import { BAND_TIERS, COLLEGE_AID_FLAGS, COLLEGE_PRICE_CAPS, COLLEGE_SORTS, DEFAULT_COLLEGE_FILTERS, collegeFacetCounts, collegeFilterChips, collegeMatches, collegeSorter, daysUntil, dueLabel, dueTone, matchingPrograms, percentText, priceCapLabel, rankText, satLabel, shortDate, toggleIn, universityFit } from '../lib/college';
import { UniversityPage } from './UniversityPage';
import { QsUniversityDetails } from '../components/QsUniversityDetails';
import { CollegeFilterSelect } from '../components/CollegeFilterSelect';
import { QS_CLASSIFICATIONS, QS_TABLE_COLUMNS, institutionStatus, qsClassification, qsScore, qsScoreText } from '../lib/qs';
import { universityLogoSrc } from '../lib/universityLogos';
import './catalog.css';
import './college-redesign.css';
import './college-toolbar.css';

// Downloaded university logos are served locally, including under the image CSP.
function UniversityLogo({ university }) {
  const [failedSrc, setFailedSrc] = useState('');
  const initials = university.name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase();
  const src = universityLogoSrc(university);
  return <span className="catalog-university-logo" aria-hidden="true">{src && failedSrc !== src ? <img src={src} alt="" loading="lazy" onError={() => setFailedSrc(src)} /> : <b>{initials}</b>}</span>;
}

function CollegeFilters({ filters, setFilters, counts, budget, showBands, chips }) {
  const patch = (change) => setFilters((current) => ({ ...current, ...change }));
  const clear = chips.length > 0 && <button type="button" className="link-button" onClick={() => setFilters(DEFAULT_COLLEGE_FILTERS)}>{t("Clear")}</button>;
  const groups = <>
    <fieldset className="filter-set"><legend className="college-filter-legend">{t("Where")}</legend><select className="filter-country" aria-label={t("Country")} value={filters.country} onChange={(event) => patch({ country: event.target.value })}><option value="">{t("All countries")}</option>{Object.entries(counts.countries).sort(([a], [b]) => a.localeCompare(b)).map(([country, count]) => <option key={country} value={country}>{`${country} (${formatNumberLocale(count)})`}</option>)}</select></fieldset>
    {showBands && <fieldset className="filter-set"><legend className="college-filter-legend">{t("Admission band")}</legend>{['reach', 'target', 'safety'].map((band) => <FilterOption key={band} checked={filters.bands.includes(band)} onChange={() => patch({ bands: toggleIn(filters.bands, band) })} count={counts.bands[band]}><TierBand value={band} /></FilterOption>)}</fieldset>}
    <fieldset className="filter-set"><legend className="college-filter-legend">{t("Net price per year")}</legend>{COLLEGE_PRICE_CAPS.map((cap) => <FilterOption key={cap} type="radio" name="college-price" checked={filters.price === cap} disabled={cap === 'budget' && !budget} onChange={() => patch({ price: cap })} count={cap === 'budget' && budget ? money(budget) : null}>{priceCapLabel(cap)}</FilterOption>)}</fieldset>
    <fieldset className="filter-set"><legend className="college-filter-legend">{t("Financial aid")}</legend>{COLLEGE_AID_FLAGS.map(([flag, title]) => <FilterOption key={flag} checked={filters.aid.includes(flag)} onChange={() => patch({ aid: toggleIn(filters.aid, flag) })} count={counts.aid[flag] || 0}>{t(title)}</FilterOption>)}</fieldset>
    <fieldset className="filter-set"><legend className="college-filter-legend">{t("Testing & type")}</legend>
      <FilterOption checked={filters.testOptional} onChange={() => patch({ testOptional: !filters.testOptional })} count={counts.testOptional}>{t("Test optional")}</FilterOption>
      <FilterOption checked={filters.satFit} onChange={() => patch({ satFit: !filters.satFit })} count={counts.satFit}>{t("My SAT is in range")}</FilterOption>
      <FilterOption checked={filters.publicOnly} onChange={() => patch({ publicOnly: !filters.publicOnly })} count={counts.publicOnly}>{t("Public only")}</FilterOption>
    </fieldset>
  </>;
  return <div className="college-advanced-filters" id="college-advanced-filters">{clear && <header>{clear}</header>}{groups}</div>;
}

function CollegeSkyline() {
  return <svg className="college-skyline" viewBox="0 0 460 194" fill="none" aria-hidden="true" focusable="false">
    <path d="M20 178h420" stroke="#f0e3bf" strokeWidth="2" opacity=".65" />
    <path d="M35 178v-55h24v55m-17-55V99h10v24m-5-24V87m-11 54h22m-20 14h20" stroke="#f0e3bf" strokeWidth="3" strokeLinejoin="round" opacity=".9" />
    <path d="M91 178v-42h58v42m-53-42v-22h48v22m-43-22v-11h38v11m-29-11V91h20v12m-20 27h20m-36 20h52m-52 13h52" fill="#f0e3bf" stroke="#f0e3bf" strokeWidth="2" />
    <path d="M104 147v31m15-31v31m15-31v31" stroke="#c7ae76" strokeWidth="6" />
    <path d="M177 178V88h51v90m-56-90h61m-50-10h39m-32-10h25m-13 0V52m-13 51h5m12 0h5m-22 16h5m12 0h5m-22 16h5m12 0h5m-22 16h5m12 0h5" stroke="#f0e3bf" strokeWidth="3" strokeLinejoin="round" />
    <path d="M252 178v-66l43-33 43 33v66m-86-66h86m-72 0v66m58-66v66m-46-37h34m-34 13h34m-22-75V62h10v17" fill="#c7ae76" stroke="#f0e3bf" strokeWidth="3" strokeLinejoin="round" />
    <path d="M352 178v-46h42v46m-44-46h46m-34-15h22v15m-18-15v-13h14v13m-7-13V91m-14 55h28m-28 12h28" stroke="#f0e3bf" strokeWidth="3" strokeLinejoin="round" />
    <path d="M166 53l18 5-18 5V53Zm123-18 19 5-19 5V35Zm-78 11 16 5-16 5V46Z" fill="#fff7df" />
    <path d="M166 52v34m123-51v27m-78-16v22" stroke="#f0e3bf" strokeWidth="2" />
    <path d="M17 181c47-7 58-7 105 0 61-8 102-5 134 0 66-6 110-7 188 0" stroke="#c7ae76" strokeWidth="8" strokeLinecap="round" />
    <path d="M16 186h428" stroke="#c7ae76" strokeWidth="6" strokeLinecap="round" />
  </svg>;
}

function CollegeProfileStrip({ research, refreshing, onRefresh, onEdit }) {
  const profile = research.profile_snapshot || {};
  const updated = research.generated_at ? `${t("Updated")} ${clockText(research.generated_at)}` : t("Refresh");
  return <section className="profile-strip" aria-label={t("Ranked for your profile")}>
    <span className="college-profile-caption"><GraduationCap size={18} aria-hidden="true" />{t('Your profile')}</span>
    <div className="college-profile-values">{[['SAT', profile.sat_score], ['GPA', profile.gpa], ['IELTS', profile.ielts_score], ['Major', profile.target_major], ['Budget', money(profile.budget_usd)]].map(([title, value]) => <span key={title}><small>{t(title)}</small><b>{value ?? '—'}</b></span>)}</div>
    <div className="profile-strip-actions">
      <button type="button" className="icon-button" title={t("Edit profile")} aria-label={t("Edit profile")} onClick={onEdit}><Pencil size={15} /></button>
      <button type="button" className="icon-button" title={updated} aria-label={t("Refresh")} disabled={refreshing} aria-busy={refreshing} onClick={onRefresh}><RefreshCw className={refreshing ? 'spin' : ''} size={15} /></button>
    </div>
  </section>;
}

function CollegeRow({ university, detail, view, result, score, scored, student, application, expanded, busy, onToggle, onOpen, onAdd }) {
  // Research scores a set of plausible universities; the rest have no fit, not a guessed one.
  const fit = score ? score.match_score : scored ? null : universityFit(university, student).score;
  const panelId = `college-details-${university.id}`;
  const days = daysUntil(university.application_deadline);
  const status = institutionStatus(university, t);
  return <div className={`uni-row ${expanded ? 'is-open' : ''}`.trim()} role="row">
    <div className="uni-fit" role="cell"><b>{rankText(university)}</b></div>
    <div className="uni-name" role="cell"><UniversityLogo university={university} /><span><button type="button" onClick={onOpen}>{university.name}</button><small>{[university.city, university.country].filter(Boolean).join(', ')}{status ? ` · ${status}` : ''}</small></span></div>
    <div className="uni-facts">
      {view === 'qs' ? QS_TABLE_COLUMNS.map(([code, title]) => <div className={`uni-value ${code === 'overall' ? 'qs-score-primary' : ''}`} role="cell" data-label={t(title)} key={code}><span className="v">{qsScoreText(qsScore(university.qs_data, code))}</span></div>) : <>
      <div className="uni-value uni-score" role="cell" data-label={t("Fit")}><span className="v">{fit == null ? '—' : <>{formatNumberLocale(fit)}<small>/100</small></>}</span></div>
      <div className="uni-band" role="cell" data-label={t("Band")}>{score?.admission_band ? <TierBand value={score.admission_band} /> : <span className="muted-copy">—</span>}</div>
      <div className="uni-value" role="cell" data-label={t("Acceptance")}><span className="v">{percentText(university.acceptance_rate)}</span></div>
      <div className="uni-value" role="cell" data-label={t("SAT")}><span className="v">{satLabel(university)}</span></div>
      <div className="uni-value" role="cell" data-label={t("Net price")}><span className="v">{money(university.net_price_usd)}</span></div>
      <div className="uni-value" role="cell" data-label={t("Deadline")}><span className="v">{university.application_deadline ? shortDate(university.application_deadline) : '—'}</span>{days != null && days >= 0 && <small className="uni-due">{dueLabel(days)}</small>}</div>
      </>}
    </div>
    <div className="uni-action" role="cell">{application ? <span className="uni-added"><Check size={14} aria-hidden="true" /> {t("Added")}</span> : <button type="button" className="button quiet small" aria-label={t("Add to my list")} disabled={busy} aria-busy={busy} onClick={onAdd}><Plus size={14} aria-hidden="true" /> {t("Add")}</button>}</div>
    <div className="uni-chevron" role="cell"><button type="button" aria-expanded={expanded} aria-controls={panelId} aria-label={view === 'qs' ? t("Show QS details") : t("Show why this result")} onClick={onToggle}>{expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</button></div>
    {expanded && <div className="uni-expand" id={panelId} role="cell">
      {view === 'qs' ? detail ? <QsUniversityDetails university={detail} /> : <p role="status">{t('Loading…')}</p> : result && <div className="uni-expand-grid">
        <section className="college-detail-score"><h4>{t("Fit")}</h4><ScoreBreakdown breakdown={result.score_breakdown} /></section><div className="college-detail-notes"><section><h4>{t("Why it fits")}</h4>
        <ul className="note-list ok" aria-label={t("Why it fits")}>{result.reasons.map((reason) => <li key={reason}><CheckCircle2 size={14} aria-hidden="true" /><span>{reason}</span></li>)}</ul></section><section><h4>{t("Watch-outs")}</h4>
        <ul className="note-list gap" aria-label={t("Watch-outs")}>{result.gaps.map((gap) => <li key={gap}><Clock3 size={14} aria-hidden="true" /><span>{gap}</span></li>)}</ul></section></div>
      </div>}
      <button type="button" className="button quiet small uni-open" onClick={onOpen}>{t("Open university")} <ArrowRight size={13} aria-hidden="true" /></button>
    </div>}
  </div>;
}

// A date picked here becomes the application's own deadline. Only today or later
// counts, so the partial years a typed date passes through (0002, 0020…) never save.
function DeadlinePicker({ name, busy, onPick }) {
  const today = localDateKey();
  return <label className="drawer-deadline" onClick={(event) => event.stopPropagation()}><CalendarPlus size={13} aria-hidden="true" /><span>{t("Set deadline")}</span><input type="date" min={today} disabled={busy} aria-busy={busy} aria-label={tx`Set deadline for ${name}`} onChange={(event) => {if (event.target.value >= today) onPick(event.target.value);}} /></label>;
}

function CollegeListDrawer({ applications, universities, fits, busyId, onClose, onOpen, onRemove, onDeadline, onApplications }) {
  const deadlineOf = (application) => application.deadline || universities.get(application.university)?.application_deadline;
  const sorted = [...applications].sort((a, b) => (deadlineOf(a) ? parseDateValue(deadlineOf(a)).getTime() : Infinity) - (deadlineOf(b) ? parseDateValue(deadlineOf(b)).getTime() : Infinity));
  const bandOf = (application) => application.tier === 'dream' ? 'reach' : application.tier;
  return <Modal title="My college list" className="drawer-modal" backdropClassName="drawer-backdrop" onClose={onClose}>
    <div className="drawer-body">
      <div className="drawer-summary"><h3>{tp('{n} university|{n} universities', applications.length, { n: applications.length })}</h3>
        <div className="drawer-tiers">{['reach', 'target', 'safety'].map((band) => <span key={band}><b>{formatNumberLocale(applications.filter((application) => bandOf(application) === band).length)}</b><TierBand value={band} /></span>)}</div></div>
      <div className="drawer-list">{sorted.map((application) => {
          const university = universities.get(application.university);
          const name = university?.name || application.university_detail?.name || t("University");
          const score = fits.get(application.university)?.match_score;
          const deadline = deadlineOf(application);
          const days = daysUntil(deadline);
          const busy = busyId === application.university;
          return <article className="drawer-row" key={application.id} onClick={() => onOpen(application.university)}>
            <div className="drawer-copy">{university && <UniversityLogo university={university} />}<span><button type="button" className="drawer-name" onClick={(event) => {event.stopPropagation();onOpen(application.university);}}>{name}</button><div className="drawer-sub"><TierBand value={bandOf(application)} /><span>{[university?.city, university?.country].filter(Boolean).join(', ')}</span></div>{days != null && <span className={`due drawer-due ${dueTone(days)}`.trim()}><Clock3 size={12} aria-hidden="true" /> {dueLabel(days)}</span>}</span></div>
            {score != null && <div className="drawer-score"><b>{formatNumberLocale(score)}</b><small>{t("fit")}</small></div>}
            <div className="drawer-row-footer"><small>{money(university?.net_price_usd)} · {deadline ? shortDate(deadline) : <DeadlinePicker name={name} busy={busy} onPick={(date) => onDeadline(application, date)} />}</small><button type="button" className="drawer-remove" aria-label={tx`Remove ${name} from my list`} disabled={busyId === application.university} aria-busy={busyId === application.university} onClick={(event) => {event.stopPropagation();onRemove(application);}}><Trash2 size={13} aria-hidden="true" />{t("Remove")}</button></div>
          </article>;
        })}{!sorted.length && <Empty text={t("Your list is empty. Add universities from the results.")} />}</div>
    </div>
    <footer className="drawer-foot"><button type="button" className="button primary" onClick={onApplications}>{t("Open in Applications")} <ArrowRight size={14} aria-hidden="true" /></button></footer>
  </Modal>;
}

// Research has no admission data to place this university, so the student picks its band.
function TierPicker({ university, busy, onPick, onClose }) {
  return <Modal title="Pick a band" onClose={onClose}><div className="tier-picker">
    <p>{tx`There is no admission data to tell whether ${university.name} is a reach, target or safety for you. Pick one; you can change it later in Applications.`}</p>
    <div className="chip-row">{Object.entries(BAND_TIERS).map(([band, tier]) => <button type="button" key={tier} className="button quiet small" disabled={busy} aria-busy={busy} onClick={() => onPick(tier)}><TierBand value={band} /></button>)}</div>
  </div></Modal>;
}

// The catalogue holds ~1,500 universities; the table grows by this many rows at a time.
const ROWS_PER_STEP = 50;

export function CollegeSearchPage({ data, query, reload, notify, setPage, universityId }) {
  const [localQuery, setLocalQuery] = useState(query || '');
  const [filters, setFilters] = useState(DEFAULT_COLLEGE_FILTERS);
  const [sort, setSort] = useState('ranking');
  const [view, setView] = useState('qs');
  const [qsFilters, setQsFilters] = useState({});
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [shown, setShown] = useState(ROWS_PER_STEP);
  const [expandedId, setExpandedId] = useState(null);
  const [listOpen, setListOpen] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [tierFor, setTierFor] = useState(null);
  // The catalogue list is slim; a university's page and QS panel load its full record.
  const [details, setDetails] = useState({});
  const [detailError, setDetailError] = useState('');
  const requestedDetails = useRef(new Set());
  const [research, setResearch] = useState(null);
  const [researchLoading, setResearchLoading] = useState(true);
  const [researchSaving, setResearchSaving] = useState(false);
  const [researchError, setResearchError] = useState('');
  const previousQuery = useRef(query);
  const openUniversity = useCallback((id) => setPage('college_search', { universityId: id }), [setPage]);
  const closeUniversity = useCallback(() => setPage('college_search'), [setPage]);
  const student = ownStudent(data);
  const budget = Number(student?.budget_usd) || 0;
  const researchMap = useMemo(() => new Map((research?.recommendations || []).map((item) => [item.university.id, item])), [research]);
  // Score and band of every university; only the best matches (researchMap) explain theirs.
  const fits = useMemo(() => new Map(Object.entries(research?.scores || {}).map(([id, [match_score, admission_band]]) => [Number(id), { match_score, admission_band }])), [research]);
  const universities = useMemo(() => new Map(data.universities.map((item) => [item.id, item])), [data.universities]);
  const listed = useMemo(() => new Map(data.applications.map((item) => [item.university, item])), [data.applications]);
  const counts = useMemo(() => collegeFacetCounts(data.universities, fits, student), [data.universities, fits, student]);
  const qsFacets = useMemo(() => Object.fromEntries(QS_CLASSIFICATIONS.slice(0, 4).map(([key]) => [key, data.universities.reduce((counts, item) => { const value = item.qs_data?.[key]; if (value) counts[value] = (counts[value] || 0) + 1; return counts; }, {})])), [data.universities]);
  const rows = useMemo(() => data.universities.filter((item) => collegeMatches(item, fits.get(item.id), filters, student, localQuery) && (view !== 'qs' || Object.entries(qsFilters).every(([key, value]) => !value || item.qs_data?.[key] === value))).sort(collegeSorter(sort, fits, student)), [data.universities, fits, filters, student, localQuery, sort, view, qsFilters]);

  const loadDetail = useCallback((id) => {
    if (id == null || requestedDetails.current.has(id)) return;
    requestedDetails.current.add(id);
    setDetailError('');
    api.retrieve('universities', id).then((item) => setDetails((current) => ({ ...current, [id]: item }))).catch((error) => {requestedDetails.current.delete(id);setDetailError(error.message);});
  }, []);
  useEffect(() => { loadDetail(universityId); }, [universityId, loadDetail]);
  useEffect(() => { if (view === 'qs') loadDetail(expandedId); }, [view, expandedId, loadDetail]);

  useEffect(() => { setLocalQuery(query || ''); }, [query]);
  useEffect(() => { setShown(ROWS_PER_STEP); }, [filters, sort, localQuery, view, qsFilters]);
  const searchRef = useRef(null);
  const resultsRef = useRef(null);
  // The list filters as you type; Enter or the search button brings the results into view.
  function submitSearch(event) {
    event.preventDefault();
    const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    resultsRef.current?.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' });
  }

  useEffect(() => {
    let active = true;
    setResearchLoading(true);
    api.collegeResearch().then((result) => {if (active) {setResearch(result);setResearchError('');}}).catch((error) => {if (active) setResearchError(error.message);}).finally(() => {if (active) setResearchLoading(false);});
    return () => {active = false;};
  }, []);

  // Searching from a university page returns to the results.
  useEffect(() => {
    if (previousQuery.current !== query && query.trim() && universityId != null) closeUniversity();
    previousQuery.current = query;
  }, [query, universityId, closeUniversity]);

  useEffect(() => {window.scrollTo({ top: 0, left: 0, behavior: 'auto' });}, [universityId]);

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

  // Without a known band the student picks the tier: an unknown band is never filed as "target".
  async function addToList(university, pickedTier) {
    const tier = pickedTier || BAND_TIERS[fits.get(university.id)?.admission_band];
    if (!tier) {setTierFor(university);return;}
    setBusyId(university.id);
    try {
      // Programs are only in the full record.
      const full = details[university.id] || (student?.target_major ? await api.retrieve('universities', university.id) : university);
      const program = matchingPrograms(full, student?.target_major)[0]?.name || student?.target_major || 'Undeclared';
      await api.create('applications', { student: student?.id, university: university.id, program, tier, status: 'shortlisted', deadline: university.application_deadline, scholarship_deadline: university.scholarship_deadline });
      await reload();
      setTierFor(null);
      notify(tx`${university.name} added to your list.`);
    } catch (err) {notify(err.message, 'error');} finally {setBusyId(null);}
  }

  async function saveDeadline(application, deadline) {
    setBusyId(application.university);
    try {
      await api.update('applications', application.id, { deadline });
      await reload();
      notify(t("Deadline saved."));
    } catch (err) {notify(err.message, 'error');} finally {setBusyId(null);}
  }

  async function removeFromList(application) {
    if (!window.confirm(t("Remove this university from your list?"))) return;
    const name = universities.get(application.university)?.name || t("University");
    setBusyId(application.university);
    try {
      await api.remove('applications', application.id);
      await reload();
      notify(tx`${name} removed from your list.`);
    } catch (err) {notify(err.message, 'error');} finally {setBusyId(null);}
  }

  const tierPicker = tierFor && <TierPicker university={tierFor} busy={busyId === tierFor.id} onPick={(tier) => addToList(tierFor, tier)} onClose={() => setTierFor(null)} />;
  const university = universityId == null ? null : universities.get(universityId);
  const detail = university && details[university.id];
  if (university && !detail) return <div className="section-stack student-portal college-page">{detailError ? <div className="college-research-state error"><X size={22} /><div><b>{t("University")}</b><p>{detailError}</p></div><button type="button" className="button quiet small" onClick={() => loadDetail(university.id)}>{t("Retry")}</button></div> : <div className="college-research-state" role="status"><RefreshCw className="spin" size={22} /><div><b>{t('Loading…')}</b></div></div>}</div>;
  if (university) return <><UniversityPage {...{ data, research, researchLoading, setPage }} university={detail} result={researchMap.get(university.id)} application={listed.get(university.id)} busy={busyId === university.id} onAdd={() => addToList(university)} onRemove={() => removeFromList(listed.get(university.id))} onBack={closeUniversity} />{tierPicker}</>;

  const chips = collegeFilterChips(filters, setFilters, budget);
  const ready = Boolean(research?.ready);
  const filtersPanel = <CollegeFilters {...{ filters, setFilters, counts, budget, chips }} showBands={ready} />;
  return <div className="section-stack student-portal college-page">
    <div className="catalog-hero catalog-college-hero"><div className="college-hero-content"><span className="catalog-eyebrow">NASEEB EDU / {t('College Search')}</span><h1>{t('College Search')}</h1><p>{t('Explore admissions, cost, deadlines, and your personal fit in one place.')}</p><form className="catalog-hero-search" role="search" onSubmit={submitSearch}><input ref={searchRef} type="search" value={localQuery} onChange={(event) => setLocalQuery(event.target.value)} placeholder={t('Search by university or location')} aria-label={t('Search universities')} />{localQuery && <button type="button" className="catalog-hero-clear" onClick={() => { setLocalQuery(''); searchRef.current?.focus(); }} aria-label={t('Clear search')}><X size={16} aria-hidden="true" /></button>}<button type="submit" className="college-search-icon" aria-label={t('Search')}><Search size={20} aria-hidden="true" /></button></form></div><CollegeSkyline /></div>
    {researchLoading && !research && <div className="college-research-state"><RefreshCw className="spin" size={22} /><div><b>{t("Analyzing your profile")}</b><p>{t("Checking SAT, GPA, IELTS, major, budget, and portfolio evidence.")}</p></div></div>}
    {researchError && <div className="college-research-state error"><X size={22} /><div><b>{t("College research could not be loaded")}</b><p>{researchError}</p></div><button className="button quiet small" onClick={refreshResearch}>{t("Retry")}</button></div>}
    {research && !research.ready && <CollegeProfileQuestions research={research} saving={researchSaving} onComplete={completeResearchProfile} />}
    {(ready || view === 'qs') && <div className="college-layout">
      <div className="college-main">
      <section className="college-toolbar" aria-label={t('University data view')} ref={resultsRef}>
        <header className="college-toolbar-header">
          <div className="college-data-views" role="group" aria-label={t('University data view')}>{[['qs', 'QS rankings'], ['admissions', 'Admissions & costs']].map(([key, title]) => <button type="button" key={key} aria-pressed={view === key} onClick={() => { setView(key); setExpandedId(null); setSort(key === 'qs' ? 'ranking' : 'fit'); }}>{t(title)}{key === 'qs' && <span className="college-edition">2027</span>}</button>)}</div>
          <button type="button" className="college-saved-button" onClick={() => setListOpen(true)} aria-label={t('My college list')}><Bookmark size={17} aria-hidden="true" /><span>{t('My List')}</span><b>{formatNumberLocale(data.applications.length)}</b></button>
        </header>
        <div className="college-filter-row">
          {view === 'qs' && <div className="college-qs-filters">{QS_CLASSIFICATIONS.slice(0, 4).map(([key, title, values]) => <CollegeFilterSelect key={key} label={t(title)} value={qsFilters[key] || ''} onChange={(value) => setQsFilters((current) => ({ ...current, [key]: value }))} options={[{ value: '', label: t('All') }, ...Object.keys(values).filter((value) => qsFacets[key][value]).map((value) => ({ value, label: qsClassification(key, value), count: qsFacets[key][value] }))]} />)}</div>}
          <button type="button" className="college-filters-toggle" aria-expanded={filtersOpen} aria-controls="college-advanced-filters" onClick={() => setFiltersOpen(!filtersOpen)}><Filter size={16} aria-hidden="true" />{t('Filters')}{chips.length > 0 && <b>{formatNumberLocale(chips.length)}</b>}<ChevronDown size={14} aria-hidden="true" /></button>
        </div>
        {filtersOpen && filtersPanel}
        <div className="uni-meta">
          <p className="filter-count" aria-live="polite"><b>{formatNumberLocale(rows.length)}</b> {t('Universities')}</p>
          {chips.map((chip) => <span className="filter-token" key={chip.key}>{chip.text}<button type="button" aria-label={tx`Remove ${chip.text} filter`} onClick={chip.clear}><X size={13} aria-hidden="true" /></button></span>)}
          {view === 'qs' && Object.values(qsFilters).some(Boolean) && <button type="button" className="college-reset-filters" onClick={() => setQsFilters({})}><X size={13} aria-hidden="true" />{t('Clear')}</button>}
          <div className="sort-control"><span>{t('Sort by')}</span><select aria-label={t('Sort by')} value={sort} onChange={(event) => setSort(event.target.value)}>{COLLEGE_SORTS.map(([value, title]) => <option value={value} key={value}>{t(title)}</option>)}</select></div>
        </div>
        {ready && <CollegeProfileStrip research={research} refreshing={researchLoading} onRefresh={refreshResearch} onEdit={() => setPage('student_center')} />}
      </section>
      <div className={`uni-table ${view === 'qs' ? 'qs-table' : ''}`} role="table" aria-label={t("Universities")}>
        <div className="uni-row uni-head" role="row"><span role="columnheader">{t("Rank")}</span><span role="columnheader">{t("University")}</span><div className="uni-facts">{view === 'qs' ? QS_TABLE_COLUMNS.map(([code, title]) => <span role="columnheader" key={code}>{t(title)}</span>) : <><span role="columnheader">{t("Fit")}</span><span role="columnheader">{t("Band")}</span><span role="columnheader">{t("Acceptance")}</span><span role="columnheader">{t("SAT")}</span><span role="columnheader">{t("Net price")}</span><span role="columnheader">{t("Deadline")}</span></>}</div><span role="columnheader" className="sr-only">{t("Add to my list")}</span><span role="columnheader" className="sr-only">{t(view === 'qs' ? "Show QS details" : "Show why this result")}</span></div>
        {rows.slice(0, shown).map((item) => <CollegeRow key={item.id} view={view} university={item} detail={details[item.id]} result={researchMap.get(item.id)} score={fits.get(item.id)} scored={fits.size > 0} student={student} application={listed.get(item.id)} expanded={expandedId === item.id} busy={busyId === item.id} onToggle={() => setExpandedId(expandedId === item.id ? null : item.id)} onOpen={() => openUniversity(item.id)} onAdd={() => addToList(item)} />)}
        {!rows.length && <Empty text={t("No universities match these filters.")} />}
      </div>
      {rows.length > shown && <button type="button" className="button quiet uni-more" onClick={() => setShown(shown + ROWS_PER_STEP)}>{t('Show {n} more', { n: formatNumberLocale(Math.min(ROWS_PER_STEP, rows.length - shown)) })}</button>}
      <p className="uni-note">{t(view === 'qs' ? "Published QS scores out of 100." : "Fit is not an admission probability.")} {t("Rankings: QS World University Rankings 2027.")}</p>
      </div>
    </div>}
    {tierPicker}
    {listOpen && <CollegeListDrawer applications={data.applications} universities={universities} fits={fits} busyId={busyId} onClose={() => setListOpen(false)} onOpen={(id) => {setListOpen(false);openUniversity(id);}} onRemove={removeFromList} onDeadline={saveDeadline} onApplications={() => setPage('applications')} />}
  </div>;
}

export function CollegeProfileQuestions({ research, saving, onComplete }) {
  const [answers, setAnswers] = useState(() => Object.fromEntries(research.questions.map((question) => [question.field, research.profile_snapshot?.[question.field] ?? ''])));
  function submit(event) {
    event.preventDefault();
    onComplete(answers);
  }
  return <section className="college-profile-questions"><div className="research-question-copy"><span><ClipboardCheck size={20} /></span><div><span className="eyebrow">{t("PROFILE DATA REQUIRED")}</span><h2>{t("A few details are missing from your research profile")}</h2><p>{t("Your answers will be saved to your student profile and used to rank universities for you.")}</p></div></div><form onSubmit={submit}><div className="research-question-grid">{research.questions.map((question) => <label key={question.field}><span>{question.label}</span><input type={question.type} min={question.min} max={question.max} step={question.step || (question.type === 'number' ? '1' : undefined)} placeholder={question.placeholder} value={answers[question.field] ?? ''} onChange={(event) => setAnswers((current) => ({ ...current, [question.field]: event.target.value }))} required /></label>)}</div><footer><small>{tp('{n} answer required|{n} answers required', research.questions.length, { n: research.questions.length })}</small><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? <><RefreshCw className="spin" size={16} /> {t("Researching…")}</> : <><Search size={16} /> {t("Save & research")}</>}</button></footer></form></section>;
}
