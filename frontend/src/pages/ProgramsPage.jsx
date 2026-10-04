import { t, tp, locale, formatNumberLocale } from '../i18n';
import { dateText, money } from '../lib/format';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MapPin, CalendarDays, DollarSign, UsersRound, GraduationCap, HandCoins, ExternalLink, Search, SlidersHorizontal, ChevronDown, X, Plus, Check, Bookmark, Monitor, Building2 } from 'lucide-react';
import { request } from '../api';
import './catalog.css';
import './programs-redesign.css';
import { FilterOption } from '../components/college';
import { Empty } from '../components/ui';
import { PROGRAM_DELIVERY, PROGRAM_FILTER_DEFAULTS, PROGRAM_GRADES, activeProgramFilterCount, adoptProgramFilterUrl, filterPrograms, hasProgramFilters, programFilterState, programFilterWrite, programGrades } from '../lib/programFilters';

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

function ProgramMark({ item }) {
  const identity = `${item.provider || ''} ${item.title || ''}`;
  const logo = PROGRAM_LOGOS.find(([pattern]) => pattern.test(identity))?.[1];
  const initials = (item.provider || item.title || 'P').split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase();
  return <span className="program-database-mark" aria-hidden="true">{logo ? <img src={logo} alt="" loading="lazy" /> : <b>{initials}</b>}</span>;
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
  const [filters, setFilters] = useUrlFilters(search, navigate);
  const [savedIds, setSavedIds] = useState(new Set());
  const [savedLoading, setSavedLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);
  const [onlySaved, setOnlySaved] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const sheetRef = useRef(null);
  const toggleRef = useRef(null);
  const catalog = data.opportunityPrograms;
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const localeTag = locale();
  const { programs, counts } = useMemo(
    () => filterPrograms(catalog, filters, { today, query, translate: t, localeTag }),
    [catalog, filters, today, query, localeTag],
  );
  const categories = useMemo(() => [...new Set(catalog.map((item) => item.category).filter(Boolean))].sort(), [catalog]);
  const activeCount = activeProgramFilterCount(filters);
  const filtered = hasProgramFilters(filters);
  const update = (patch) => setFilters((current) => ({ ...current, ...patch }));
  const reset = () => setFilters({ ...PROGRAM_FILTER_DEFAULTS });
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
  const resultText = tp('{count} program|{count} programs', programs.length, { count: programs.length });

  useEffect(() => {
    let active = true;
    request('/opportunity-programs/saved/').then((result) => {
      if (active) setSavedIds(new Set(result.program_ids));
    }).catch((error) => { if (active) notify?.(error.message, 'error'); }).finally(() => {
      if (active) setSavedLoading(false);
    });
    return () => { active = false; };
  }, [notify]);

  async function toggleSaved(item) {
    if (savingId != null || savedLoading) return;
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

  const shownPrograms = onlySaved ? programs.filter(({ item }) => savedIds.has(item.id)) : programs;

  const typeLabel = { all: 'All programs', national: 'National', international: 'International' };
  const rail = <aside id="program-filters" ref={sheetRef} className={`program-rail ${sheetOpen ? 'is-open' : ''}`.trim()} aria-label={t('Filters')}>
    <header className="program-rail-head"><b>{t('Filters')}</b>{filtered && <button type="button" className="link-button" onClick={reset}>{t('Clear')}</button>}<button type="button" className="icon-button program-rail-close" onClick={() => setSheetOpen(false)} aria-label={t('Close filters')}><X size={18} /></button></header>
    <fieldset className="filter-set"><legend>{t('Program type')}</legend>{['all', 'national', 'international'].map((type) => <FilterOption key={type} type="radio" name="program-type" checked={filters.type === type} onChange={() => chooseType(type)} count={counts.type[type] || 0}>{t(typeLabel[type])}</FilterOption>)}</fieldset>
    <fieldset className="filter-set"><legend>{t('Grade')}</legend><div className="program-grade-chips">{PROGRAM_GRADES.map((grade) => <button key={grade} type="button" aria-pressed={filters.grade === grade} disabled={!counts.grade[grade] && filters.grade !== grade} onClick={() => update({ grade: filters.grade === grade ? 'all' : grade })}>{grade === 'gap' ? t('Gap year') : grade}</button>)}</div></fieldset>
    <fieldset className="filter-set"><legend>{t('Delivery')}</legend>{['all', ...PROGRAM_DELIVERY].map((mode) => <FilterOption key={mode} type="radio" name="program-delivery" checked={filters.delivery === mode} disabled={mode !== 'all' && !counts.delivery[mode] && filters.delivery !== mode} onChange={() => update({ delivery: mode })} count={mode === 'all' ? null : counts.delivery[mode] || 0}>{mode === 'all' ? t('All formats') : t(DELIVERY_LABELS[mode])}</FilterOption>)}</fieldset>
    <fieldset className="filter-set"><legend>{t('Category')}</legend><FilterOption type="radio" name="program-category" checked={filters.category === 'all'} onChange={() => update({ category: 'all' })}>{t('All categories')}</FilterOption>{[...new Set([...categories, ...(filters.category === 'all' ? [] : [filters.category])])].map((category) => <FilterOption key={category} type="radio" name="program-category" checked={filters.category === category} disabled={!counts.category[category] && filters.category !== category} onChange={() => update({ category })} count={counts.category[category] || 0}>{t(category)}</FilterOption>)}</fieldset>
    <fieldset className="filter-set"><legend className="sr-only">{t('More filters')}</legend>
      <FilterOption checked={filters.aid} onChange={(event) => update({ aid: event.target.checked })} count={counts.aid}>{t('Scholarship available')}</FilterOption>
      {(counts.closed > 0 || !filters.open) && <FilterOption checked={filters.open} onChange={(event) => update({ open: event.target.checked })} count={counts.closed}>{t('Hide closed')}</FilterOption>}
    </fieldset>
    <footer className="program-rail-foot"><button type="button" className="button primary" onClick={() => setSheetOpen(false)}>{tp('Show {count} program|Show {count} programs', programs.length, { count: programs.length })}</button></footer>
  </aside>;

  // Wide screens: filter pills under the search box (the bottom-right corner
  // belongs to the assistant launcher). Phones: the same filters in a sheet.
  const categoryOptions = [...new Set([...categories, ...(filters.category === 'all' ? [] : [filters.category])])];
  const filterBar = <div className="program-filterbar" role="group" aria-label={t('Filters')}>
    <FilterMenu label={t('Program type')} value={filters.type === 'all' ? '' : t(typeLabel[filters.type])}>{(close) => ['all', 'national', 'international'].map((type) => <FilterOption key={type} type="radio" name="program-type-menu" checked={filters.type === type} onChange={() => { chooseType(type); close(); }} count={counts.type[type] || 0}>{t(typeLabel[type])}</FilterOption>)}</FilterMenu>
    <FilterMenu label={t('Grade')} value={filters.grade === 'all' ? '' : filters.grade === 'gap' ? t('Gap year') : filters.grade}>{(close) => <div className="program-grade-chips">{PROGRAM_GRADES.map((grade) => <button key={grade} type="button" aria-pressed={filters.grade === grade} disabled={!counts.grade[grade] && filters.grade !== grade} onClick={() => { update({ grade: filters.grade === grade ? 'all' : grade }); close(); }}>{grade === 'gap' ? t('Gap year') : grade}</button>)}</div>}</FilterMenu>
    <FilterMenu label={t('Delivery')} value={filters.delivery === 'all' ? '' : t(DELIVERY_LABELS[filters.delivery])}>{(close) => ['all', ...PROGRAM_DELIVERY].map((mode) => <FilterOption key={mode} type="radio" name="program-delivery-menu" checked={filters.delivery === mode} disabled={mode !== 'all' && !counts.delivery[mode] && filters.delivery !== mode} onChange={() => { update({ delivery: mode }); close(); }} count={mode === 'all' ? null : counts.delivery[mode] || 0}>{mode === 'all' ? t('All formats') : t(DELIVERY_LABELS[mode])}</FilterOption>)}</FilterMenu>
    <FilterMenu label={t('Category')} value={filters.category === 'all' ? '' : t(filters.category)}>{(close) => <><FilterOption type="radio" name="program-category-menu" checked={filters.category === 'all'} onChange={() => { update({ category: 'all' }); close(); }}>{t('All categories')}</FilterOption>{categoryOptions.map((category) => <FilterOption key={category} type="radio" name="program-category-menu" checked={filters.category === category} disabled={!counts.category[category] && filters.category !== category} onChange={() => { update({ category }); close(); }} count={counts.category[category] || 0}>{t(category)}</FilterOption>)}</>}</FilterMenu>
    <button type="button" className="program-pill-toggle" aria-pressed={filters.aid} onClick={() => update({ aid: !filters.aid })}>{filters.aid && <Check size={15} aria-hidden="true" />}{t('Scholarship available')}<span>{count(counts.aid)}</span></button>
    {(counts.closed > 0 || !filters.open) && <button type="button" className="program-pill-toggle" aria-pressed={filters.open} onClick={() => update({ open: !filters.open })}>{filters.open && <Check size={15} aria-hidden="true" />}{t('Hide closed')}<span>{count(counts.closed)}</span></button>}
    {filtered && <button type="button" className="link-button program-filterbar-clear" onClick={reset}>{t('Clear')}</button>}
  </div>;

  return <div className="section-stack student-portal programs-page catalog-programs program-database">
    <div className="program-layout">
    <div className="program-main">
    <div className="program-topbar">
      <label className="search program-search"><Search size={19} aria-hidden="true" /><input type="search" value={filters.q} maxLength={100} onChange={(event) => update({ q: event.target.value })} placeholder={t('Search programs')} aria-label={t('Search programs')} />{filters.q && <button type="button" className="search-clear" onClick={() => update({ q: '' })} aria-label={t('Clear search')}><X size={15} /></button>}</label>
      <button ref={toggleRef} type="button" className="button quiet program-rail-toggle" onClick={() => setSheetOpen(true)} aria-expanded={sheetOpen} aria-controls="program-filters"><SlidersHorizontal size={18} /> {t('Filters')}{activeCount > 0 && <span className="program-filter-badge">{count(activeCount)}</span>}</button>
    </div>
    {filterBar}

    <div className="program-results-bar"><span role="status" aria-live="polite">{onlySaved ? tp('{count} saved program|{count} saved programs', shownPrograms.length, { count: shownPrograms.length }) : resultText}</span><div className="catalog-list-controls"><button type="button" className={`button quiet small ${onlySaved ? 'is-active' : ''}`} aria-pressed={onlySaved} onClick={() => setOnlySaved((value) => !value)}><Bookmark size={16} /> {t('My List')} <span>{savedIds.size}</span></button></div></div>

    <div className="program-grid">{shownPrograms.map(({ item, closed }) => {
      const grades = programGrades(item);
      const place = [item.city, item.country].filter(Boolean).join(', ') || (item.delivery_mode === 'online' ? t('Online') : '');
      const isSaved = savedIds.has(item.id);
      return <article className={`program-card ${closed ? 'is-closed' : ''}`} key={item.id}>
        <div className="program-database-identity"><ProgramMark item={item} /><div className="program-database-copy"><h3>{item.title}</h3><div className="program-database-byline">{item.provider && <span><Building2 size={15} /> {item.provider}</span>}<span>{t(item.category)}</span><span>{t(item.program_type === 'national' ? 'National' : item.program_type === 'international' ? 'International' : 'To verify')}</span></div></div></div>
        <div className="program-database-facts">
          {place && <span><MapPin size={16} /> {place}</span>}
          {item.delivery_mode !== 'unspecified' && <span><Monitor size={16} /> {t(DELIVERY_LABELS[item.delivery_mode] || 'To verify')}</span>}
          <span className={closed ? 'program-database-deadline is-closed' : 'program-database-deadline'}><CalendarDays size={16} /> <ProgramDeadline item={item} closed={closed} /></span>
          {grades.length > 0 && <span><GraduationCap size={16} /> {t('Grades')} {grades.join(', ')}</span>}
          {item.eligible_ages && <span><UsersRound size={16} /> {t('Ages')} {item.eligible_ages}</span>}
          {item.fee_usd != null && <span><DollarSign size={16} /> {Number(item.fee_usd) === 0 ? t('Free') : money(item.fee_usd)}</span>}
          {item.scholarship_available && <span className="program-database-aid" title={t(item.aid_details)}><HandCoins size={16} /> {t('Financial aid available')}</span>}
        </div>
        {(item.description || item.requirements) && <details className="program-database-details"><summary>{t('Requirements')}</summary>{item.description && <p>{t(item.description)}</p>}{item.requirements && <p>{t(item.requirements)}</p>}</details>}
        <div className="program-database-actions"><button type="button" className={`program-database-save ${isSaved ? 'is-saved' : ''}`} aria-pressed={isSaved} disabled={savedLoading || savingId === item.id} onClick={() => toggleSaved(item)}>{isSaved ? <><Check size={16} /> {t('In My List')}</> : <><Plus size={16} /> {t('Add to My List')}</>}</button>{item.application_url && <a className="program-database-link" href={item.application_url} target="_blank" rel="noreferrer" aria-label={`${t('View program')}: ${item.title}`} title={t('View program')}><ExternalLink size={18} /></a>}</div>
      </article>;
    })}{!shownPrograms.length && <div className="program-empty"><Empty text={onlySaved ? t('No saved programs match these filters.') : t('No programs match these filters.')} />{onlySaved ? <button type="button" className="button primary small" onClick={() => setOnlySaved(false)}>{t('Browse programs')}</button> : filtered && <><p>{t('Try another search or remove a filter.')}</p><button type="button" className="button primary small" onClick={reset}>{t('Reset filters')}</button></>}</div>}</div>
    </div>
    {sheetOpen && <div className="program-sheet-backdrop" onClick={() => setSheetOpen(false)} aria-hidden="true" />}
    {rail}
    </div>
  </div>;
}
