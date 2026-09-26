import { t, tp, locale, formatNumberLocale, tx } from '../i18n';
import { dateText, money } from '../lib/format';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Globe2, Compass, MapPin, CalendarDays, DollarSign, UsersRound, GraduationCap, HandCoins, ExternalLink, Search, SlidersHorizontal, X } from 'lucide-react';
import { ChoiceCards, CheckboxControl } from '../components/forms';
import { Badge, Empty } from '../components/ui';
import { label } from '../lib/labels';
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

export function ProgramsPage({ data, query, search, navigate }) {
  const [filters, setFilters] = useUrlFilters(search, navigate);
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
  const option = (value, text, bucket, selected) => <option key={value} value={value} disabled={!bucket[value] && selected !== value}>{`${text} (${count(bucket[value])})`}</option>;
  const resultText = tp('{count} program|{count} programs', programs.length, { count: programs.length });

  return <div className="section-stack student-portal programs-page">
    <ChoiceCards name="program-type" label={t("Program type")} value={filters.type} onChange={chooseType} options={[{ value: 'all', label: `${t("All programs")} (${count(counts.type.all)})`, description: 'Explore current opportunities', icon: Compass }, { value: 'national', label: `${t("National")} (${count(counts.type.national)})`, description: 'Opportunities within Uzbekistan', icon: MapPin }, { value: 'international', label: `${t("International")} (${count(counts.type.international)})`, description: 'Global and overseas opportunities', icon: Globe2 }]} />
    <div className="program-toolbar">
      <label className="search program-search"><Search size={17} aria-hidden="true" /><input type="search" value={filters.q} maxLength={100} onChange={(event) => update({ q: event.target.value })} placeholder={t("Search programs")} aria-label={t("Search programs")} />{filters.q && <button type="button" className="search-clear" onClick={() => update({ q: '' })} aria-label={t("Clear search")}><X size={14} /></button>}</label>
      <button ref={toggleRef} type="button" className="button quiet program-filter-toggle" onClick={() => setSheetOpen(true)} aria-expanded={sheetOpen} aria-controls="program-filters"><SlidersHorizontal size={17} /> {t("Filters")}{activeCount > 0 && <span className="program-filter-badge">{count(activeCount)}</span>}</button>
    </div>
    {sheetOpen && <div className="program-sheet-backdrop" onClick={() => setSheetOpen(false)} aria-hidden="true" />}
    <section id="program-filters" ref={sheetRef} className={`program-filters ${sheetOpen ? 'is-open' : ''}`.trim()} aria-label={t("Filters")}>
      <header className="program-sheet-head"><b>{t("Filters")}</b><button type="button" className="icon-button" onClick={() => setSheetOpen(false)} aria-label={t("Close filters")}><X size={18} /></button></header>
      <label>{t("Grade")}<select value={filters.grade} onChange={(event) => update({ grade: event.target.value })}><option value="all">{t("All grades")}</option>{PROGRAM_GRADES.map((grade) => option(grade, grade === 'gap' ? t("Gap year") : tx`Grade ${grade}`, counts.grade, filters.grade))}</select></label>
      <label>{t("Category")}<select value={filters.category} onChange={(event) => update({ category: event.target.value })}><option value="all">{t("All categories")}</option>{[...new Set([...categories, ...(filters.category === 'all' ? [] : [filters.category])])].map((category) => option(category, t(category), counts.category, filters.category))}</select></label>
      <label>{t("Delivery")}<select value={filters.delivery} onChange={(event) => update({ delivery: event.target.value })}><option value="all">{t("All formats")}</option>{PROGRAM_DELIVERY.map((mode) => option(mode, t(DELIVERY_LABELS[mode]), counts.delivery, filters.delivery))}</select></label>
      <CheckboxControl className="compact" checked={filters.aid} onChange={(event) => update({ aid: event.target.checked })}>{t("Scholarship available")} ({count(counts.aid)})</CheckboxControl>
      {(counts.closed > 0 || !filters.open) && <CheckboxControl className="compact" checked={filters.open} onChange={(event) => update({ open: event.target.checked })}>{tx`Hide ${count(counts.closed)} closed`}</CheckboxControl>}
      <footer className="program-sheet-foot">{filtered && <button type="button" className="button quiet" onClick={reset}>{t("Reset filters")}</button>}<button type="button" className="button primary" onClick={() => setSheetOpen(false)}>{tp('Show {count} program|Show {count} programs', programs.length, { count: programs.length })}</button></footer>
    </section>
    <div className="program-results-bar"><span role="status" aria-live="polite">{resultText}</span>{filtered && programs.length > 0 && <button type="button" className="button quiet small" onClick={reset}>{t("Reset filters")}</button>}</div>
    <div className="program-grid">{programs.map(({ item, closed }) => {const grades = programGrades(item);const place = [item.city, item.country].filter(Boolean).join(', ') || (item.delivery_mode === 'online' ? t("Online") : '');return <article className={`program-card ${closed ? 'is-closed' : ''}`} key={item.id}>
      <header><span>{t(item.category)}</span><Badge>{label(item.program_type)}</Badge></header>
      <h3>{item.title}</h3>
      {item.provider && <p className="provider">{item.provider}</p>}
      {item.description && <p>{t(item.description)}</p>}
      <div className="program-meta">
        {place && <span><MapPin size={15} /> {place}</span>}
        <span><CalendarDays size={15} /> <ProgramDeadline item={item} closed={closed} /></span>
        {item.fee_usd != null && <span><DollarSign size={15} /> {Number(item.fee_usd) === 0 ? t("Free") : money(item.fee_usd)}</span>}
        {item.eligible_ages && <span><UsersRound size={15} /> {t("Ages")} {item.eligible_ages}</span>}
        {grades.length > 0 && <span><GraduationCap size={15} /> {t("Grades")} {grades.join(', ')}</span>}
      </div>
      {item.scholarship_available && <div className="program-aid"><HandCoins size={16} /><span><b>{t("Financial aid available")}</b>{t(item.aid_details)}</span></div>}
      {(item.requirements || !item.source_key) && <details><summary>{t("Requirements")}</summary><p>{t(item.requirements) || t("See official application page.")}</p></details>}
      {item.application_url && <a className="button primary small" href={item.application_url} target="_blank" rel="noreferrer">{t("View program")} <ExternalLink size={14} /></a>}
    </article>;})}{!programs.length && <div className="program-empty"><Empty text={t("No programs match these filters.")} />{filtered && <><p>{t("Try another search or remove a filter.")}</p><button type="button" className="button primary small" onClick={reset}>{t("Reset filters")}</button></>}</div>}</div>
  </div>;
}
