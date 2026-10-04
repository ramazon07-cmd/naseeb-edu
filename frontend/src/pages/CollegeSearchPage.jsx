import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRight, Check, CheckCircle2, ChevronDown, ChevronUp, ClipboardCheck, Clock3, Filter, List, Pencil, Plus, RefreshCw, Search, Trash2, X } from 'lucide-react';
import { api } from '../api';
import { formatNumberLocale, parseDateValue, t, tp, tx } from '../i18n';
import { Empty, Modal } from '../components/ui';
import { FilterOption, ScoreBreakdown, TierBand } from '../components/college';
import { clockText, money } from '../lib/format';
import { ownStudent } from '../lib/labels';
import { COLLEGE_AID_FLAGS, COLLEGE_PRICE_CAPS, COLLEGE_REGIONS, COLLEGE_SORTS, DEFAULT_COLLEGE_FILTERS, collegeFacetCounts, collegeFilterChips, collegeMatches, collegeSorter, matchingPrograms, percentText, priceCapLabel, satText, shortDate, toggleIn, universityFit } from '../lib/college';
import { UniversityPage } from './UniversityPage';
import './catalog.css';
import './college-redesign.css';

// Crests we ship ourselves (frontend/public). No remote logo service: the CSP
// allows only same-origin images, and a lookup would tell it what students browse.
const UNIVERSITY_LOGO_FILES = {
  'Duke University': '/landing/universities/duke.svg',
  'The Chinese University of Hong Kong': '/landing/universities/cuhk-crest.png',
  'University of Alberta': '/landing/universities/alberta.png',
  'University of Toronto': '/landing/universities/toronto.png',
};

function UniversityLogo({ university }) {
  const [failed, setFailed] = useState(false);
  const initials = university.name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase();
  const src = UNIVERSITY_LOGO_FILES[university.name];
  return <span className="catalog-university-logo" aria-hidden="true">{src && !failed ? <img src={src} alt="" loading="lazy" onError={() => setFailed(true)} /> : <b>{initials}</b>}</span>;
}

function CollegeFilters({ filters, setFilters, counts, budget, showBands, chips }) {
  const patch = (change) => setFilters((current) => ({ ...current, ...change }));
  const clear = chips.length > 0 && <button type="button" className="link-button" onClick={() => setFilters(DEFAULT_COLLEGE_FILTERS)}>{t("Clear")}</button>;
  const groups = <>
    <fieldset className="filter-set"><legend className="sr-only">{t("Where")}</legend>{COLLEGE_REGIONS.map(({ key, label: regionLabel }) => <FilterOption key={key} checked={filters.regions.includes(key)} onChange={() => patch({ regions: toggleIn(filters.regions, key) })} count={counts.regions[key] || 0}>{t(regionLabel)}</FilterOption>)}</fieldset>
    {showBands && <fieldset className="filter-set"><legend className="sr-only">{t("Admission band")}</legend>{['reach', 'target', 'safety'].map((band) => <FilterOption key={band} checked={filters.bands.includes(band)} onChange={() => patch({ bands: toggleIn(filters.bands, band) })} count={counts.bands[band]}><TierBand value={band} /></FilterOption>)}</fieldset>}
    <fieldset className="filter-set"><legend className="sr-only">{t("Net price per year")}</legend>{COLLEGE_PRICE_CAPS.map((cap) => <FilterOption key={cap} type="radio" name="college-price" checked={filters.price === cap} disabled={cap === 'budget' && !budget} onChange={() => patch({ price: cap })} count={cap === 'budget' && budget ? money(budget) : null}>{priceCapLabel(cap)}</FilterOption>)}</fieldset>
    <fieldset className="filter-set"><legend className="sr-only">{t("Financial aid")}</legend>{COLLEGE_AID_FLAGS.map(([flag, title]) => <FilterOption key={flag} checked={filters.aid.includes(flag)} onChange={() => patch({ aid: toggleIn(filters.aid, flag) })} count={counts.aid[flag] || 0}>{t(title)}</FilterOption>)}</fieldset>
    <fieldset className="filter-set"><legend className="sr-only">{t("Testing & type")}</legend>
      <FilterOption checked={filters.testOptional} onChange={() => patch({ testOptional: !filters.testOptional })} count={counts.testOptional}>{t("Test optional")}</FilterOption>
      <FilterOption checked={filters.satFit} onChange={() => patch({ satFit: !filters.satFit })} count={counts.satFit}>{t("My SAT is in range")}</FilterOption>
      <FilterOption checked={filters.publicOnly} onChange={() => patch({ publicOnly: !filters.publicOnly })} count={counts.publicOnly}>{t("Public only")}</FilterOption>
    </fieldset>
  </>;
  return <details className="filters-inline"><summary><Filter size={17} aria-hidden="true" /><b>{t("Filters")}</b>{chips.length > 0 && <span className="tab-count">{formatNumberLocale(chips.length)}</span>}<ChevronDown size={15} aria-hidden="true" /></summary><div className="filters-inline-body">{clear && <header>{clear}</header>}{groups}</div></details>;
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
    <div className="tag-row"><span className="tag">{t("SAT")} {profile.sat_score}</span><span className="tag">{t("GPA")} {profile.gpa}</span><span className="tag">{t("IELTS")} {profile.ielts_score}</span><span className="tag">{profile.target_major}</span><span className="tag">{t("Budget")} {money(profile.budget_usd)}</span></div>
    <div className="profile-strip-actions">
      <button type="button" className="icon-button" title={t("Edit profile")} aria-label={t("Edit profile")} onClick={onEdit}><Pencil size={15} /></button>
      <button type="button" className="icon-button" title={updated} aria-label={t("Refresh")} disabled={refreshing} aria-busy={refreshing} onClick={onRefresh}><RefreshCw className={refreshing ? 'spin' : ''} size={15} /></button>
    </div>
  </section>;
}

function CollegeRow({ university, result, student, application, expanded, busy, onToggle, onOpen, onAdd }) {
  const fit = result ? { score: result.match_score } : universityFit(university, student);
  const panelId = `college-details-${university.id}`;
  return <div className={`uni-row ${expanded ? 'is-open' : ''}`.trim()} role="row">
    <div className="uni-fit" role="cell"><b>{university.ranking ? `#${formatNumberLocale(university.ranking)}` : '—'}</b></div>
    <div className="uni-name" role="cell"><UniversityLogo university={university} /><span><button type="button" onClick={onOpen}>{university.name}</button><small>{[university.city, university.country].filter(Boolean).join(', ')}{university.institution_type ? ` · ${t(university.institution_type)}` : ''}</small></span></div>
    <div className="uni-facts">
      <div className="uni-value uni-score" role="cell" data-label={t("Fit")}><span className="v">{formatNumberLocale(fit.score)}<small>/100</small></span></div>
      <div className="uni-band" role="cell" data-label={t("Band")}>{result ? <TierBand value={result.admission_band} /> : <span className="muted-copy">—</span>}</div>
      <div className="uni-value" role="cell" data-label={t("Acceptance")}><span className="v">{percentText(university.acceptance_rate)}</span></div>
      <div className="uni-value" role="cell" data-label={t("SAT")}><span className="v">{university.sat_min ? satText(university.sat_min, university.sat_max) : t("Optional")}</span></div>
      <div className="uni-value" role="cell" data-label={t("Net price")}><span className="v">{money(university.net_price_usd)}</span></div>
      <div className="uni-value" role="cell" data-label={t("Deadline")}><span className="v">{university.application_deadline ? shortDate(university.application_deadline) : '—'}</span></div>
    </div>
    <div className="uni-action" role="cell">{application ? <span className="uni-added"><Check size={14} aria-hidden="true" /> {t("Added")}</span> : <button type="button" className="button quiet small" aria-label={t("Add to my list")} disabled={busy} aria-busy={busy} onClick={onAdd}><Plus size={14} aria-hidden="true" /> {t("Add")}</button>}</div>
    <div className="uni-chevron" role="cell"><button type="button" aria-expanded={expanded} aria-controls={panelId} aria-label={t("Show why this result")} onClick={onToggle}>{expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</button></div>
    {expanded && <div className="uni-expand" id={panelId} role="cell">
      {result && <div className="uni-expand-grid">
        <section className="college-detail-score"><h4>{t("Fit")}</h4><ScoreBreakdown breakdown={result.score_breakdown} /></section><div className="college-detail-notes"><section><h4>{t("Why it fits")}</h4>
        <ul className="note-list ok" aria-label={t("Why it fits")}>{result.reasons.map((reason) => <li key={reason}><CheckCircle2 size={14} aria-hidden="true" /><span>{reason}</span></li>)}</ul></section><section><h4>{t("Watch-outs")}</h4>
        <ul className="note-list gap" aria-label={t("Watch-outs")}>{result.gaps.map((gap) => <li key={gap}><Clock3 size={14} aria-hidden="true" /><span>{gap}</span></li>)}</ul></section></div>
      </div>}
      <button type="button" className="button quiet small uni-open" onClick={onOpen}>{t("Open university")} <ArrowRight size={13} aria-hidden="true" /></button>
    </div>}
  </div>;
}

function CollegeListDrawer({ applications, universities, researchMap, busyId, onClose, onOpen, onRemove, onApplications }) {
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
          const score = researchMap.get(application.university)?.match_score;
          return <article className="drawer-row" key={application.id} onClick={() => onOpen(application.university)}>
            <div className="drawer-copy">{university && <UniversityLogo university={university} />}<span><button type="button" className="drawer-name" onClick={(event) => {event.stopPropagation();onOpen(application.university);}}>{name}</button><div className="drawer-sub"><TierBand value={bandOf(application)} /><span>{[university?.city, university?.country].filter(Boolean).join(', ')}</span></div></span></div>
            {score != null && <div className="drawer-score"><b>{formatNumberLocale(score)}</b><small>{t("fit")}</small></div>}
            <div className="drawer-row-footer"><small>{money(university?.net_price_usd)} · {deadlineOf(application) ? shortDate(deadlineOf(application)) : '—'}</small><button type="button" className="drawer-remove" aria-label={tx`Remove ${name} from my list`} disabled={busyId === application.university} aria-busy={busyId === application.university} onClick={(event) => {event.stopPropagation();onRemove(application);}}><Trash2 size={13} aria-hidden="true" />{t("Remove")}</button></div>
          </article>;
        })}{!sorted.length && <Empty text={t("Your list is empty. Add universities from the results.")} />}</div>
    </div>
    <footer className="drawer-foot"><button type="button" className="button primary" onClick={onApplications}>{t("Open in Applications")} <ArrowRight size={14} aria-hidden="true" /></button></footer>
  </Modal>;
}

export function CollegeSearchPage({ data, query, reload, notify, setPage, universityId }) {
  const [localQuery, setLocalQuery] = useState(query || '');
  const [filters, setFilters] = useState(DEFAULT_COLLEGE_FILTERS);
  const [sort, setSort] = useState('fit');
  const [expandedId, setExpandedId] = useState(null);
  const [listOpen, setListOpen] = useState(false);
  const [busyId, setBusyId] = useState(null);
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
  const universities = useMemo(() => new Map(data.universities.map((item) => [item.id, item])), [data.universities]);
  const listed = useMemo(() => new Map(data.applications.map((item) => [item.university, item])), [data.applications]);
  const counts = useMemo(() => collegeFacetCounts(data.universities, researchMap, student), [data.universities, researchMap, student]);
  const rows = useMemo(() => data.universities.filter((item) => collegeMatches(item, researchMap.get(item.id), filters, student, localQuery)).sort(collegeSorter(sort, researchMap, student)), [data.universities, researchMap, filters, student, localQuery, sort]);

  useEffect(() => { setLocalQuery(query || ''); }, [query]);
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

  async function addToList(university) {
    const band = researchMap.get(university.id)?.admission_band;
    const program = matchingPrograms(university, student?.target_major)[0]?.name || student?.target_major || 'Undeclared';
    setBusyId(university.id);
    try {
      await api.create('applications', { student: student?.id, university: university.id, program, tier: band === 'reach' ? 'dream' : band === 'safety' ? 'safety' : 'target', status: 'shortlisted', deadline: university.application_deadline, scholarship_deadline: university.scholarship_deadline });
      await reload();
      notify(tx`${university.name} added to your list.`);
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

  const university = universityId == null ? null : universities.get(universityId);
  if (university) return <UniversityPage {...{ data, university, research, researchLoading, setPage }} result={researchMap.get(university.id)} application={listed.get(university.id)} busy={busyId === university.id} onAdd={() => addToList(university)} onRemove={() => removeFromList(listed.get(university.id))} onBack={closeUniversity} />;

  const chips = collegeFilterChips(filters, setFilters, budget);
  const ready = Boolean(research?.ready);
  const filtersPanel = <CollegeFilters {...{ filters, setFilters, counts, budget, chips }} showBands />;
  return <div className="section-stack student-portal college-page">
    <div className="catalog-hero catalog-college-hero"><div className="college-hero-content"><span className="catalog-eyebrow">NASEEB EDU / {t('College Search')}</span><h1>{t('College Search')}</h1><p>{t('Explore admissions, cost, deadlines, and your personal fit in one place.')}</p><form className="catalog-hero-search" role="search" onSubmit={submitSearch}><input ref={searchRef} type="search" value={localQuery} onChange={(event) => setLocalQuery(event.target.value)} placeholder={t('Search by university or location')} aria-label={t('Search universities')} />{localQuery && <button type="button" className="catalog-hero-clear" onClick={() => { setLocalQuery(''); searchRef.current?.focus(); }} aria-label={t('Clear search')}><X size={16} aria-hidden="true" /></button>}<button type="submit" className="college-search-icon" aria-label={t('Search')}><Search size={20} aria-hidden="true" /></button></form></div><CollegeSkyline /></div>
    {researchLoading && !research && <div className="college-research-state"><RefreshCw className="spin" size={22} /><div><b>{t("Analyzing your profile")}</b><p>{t("Checking SAT, GPA, IELTS, major, budget, and portfolio evidence.")}</p></div></div>}
    {researchError && <div className="college-research-state error"><X size={22} /><div><b>{t("College research could not be loaded")}</b><p>{researchError}</p></div><button className="button quiet small" onClick={refreshResearch}>{t("Retry")}</button></div>}
    {research && !research.ready && <CollegeProfileQuestions research={research} saving={researchSaving} onComplete={completeResearchProfile} />}
    {ready && <div className="college-layout">
      <div className="college-main">
      {filtersPanel}
      <div className="uni-meta" ref={resultsRef}>
        <p className="filter-count" aria-live="polite"><b>{formatNumberLocale(rows.length)}</b> {t("Universities")}</p>
        {chips.map((chip) => <span className="filter-token" key={chip.key}>{chip.text}<button type="button" aria-label={tx`Remove ${chip.text} filter`} onClick={chip.clear}><X size={13} aria-hidden="true" /></button></span>)}
        <div className="uni-meta-actions">
          <div className="sort-control"><select aria-label={t("Sort by")} value={sort} onChange={(event) => setSort(event.target.value)}>{COLLEGE_SORTS.map(([value, title]) => <option value={value} key={value}>{t(title)}</option>)}</select></div>
          <button type="button" className="button primary" onClick={() => setListOpen(true)}><List size={16} aria-hidden="true" /> {t("My college list")}<span className="count-pill">{formatNumberLocale(data.applications.length)}</span></button>
        </div>
      </div>
      <CollegeProfileStrip research={research} refreshing={researchLoading} onRefresh={refreshResearch} onEdit={() => setPage('student_center')} />
      <div className="uni-table" role="table" aria-label={t("Universities")}>
        <div className="uni-row uni-head" role="row"><span role="columnheader">{t("Rank")}</span><span role="columnheader">{t("University")}</span><div className="uni-facts"><span role="columnheader">{t("Fit")}</span><span role="columnheader">{t("Band")}</span><span role="columnheader">{t("Acceptance")}</span><span role="columnheader">{t("SAT")}</span><span role="columnheader">{t("Net price")}</span><span role="columnheader">{t("Deadline")}</span></div><span role="columnheader" className="sr-only">{t("Add to my list")}</span><span role="columnheader" className="sr-only">{t("Show why this result")}</span></div>
        {rows.map((item) => <CollegeRow key={item.id} university={item} result={researchMap.get(item.id)} student={student} application={listed.get(item.id)} expanded={expandedId === item.id} busy={busyId === item.id} onToggle={() => setExpandedId(expandedId === item.id ? null : item.id)} onOpen={() => openUniversity(item.id)} onAdd={() => addToList(item)} />)}
        {!rows.length && <Empty text={t("No universities match these filters.")} />}
      </div>
      <p className="uni-note">{t("Fit is not an admission probability.")}</p>
      </div>
    </div>}
    {listOpen && <CollegeListDrawer applications={data.applications} universities={universities} researchMap={researchMap} busyId={busyId} onClose={() => setListOpen(false)} onOpen={(id) => {setListOpen(false);openUniversity(id);}} onRemove={removeFromList} onApplications={() => setPage('applications')} />}
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
