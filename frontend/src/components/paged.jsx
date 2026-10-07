import { useEffect, useId, useRef, useState } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import { t, tx, formatNumberLocale } from '../i18n';
import { fullName } from '../lib/labels';
import { usePagedList } from '../hooks/usePagedList';

// Error banner for a paged list; keeps already loaded rows visible.
export function PagedListError({ list }) {
  if (!list.error) return null;
  return <div className="data-state error" role="alert"><div><b>{t("Some information could not be loaded")}</b><p>{list.error}</p></div><button type="button" className="button quiet small" onClick={list.reload}><RefreshCw size={14} /> {t("Retry")}</button></div>;
}

// "Load more" for a server-paged list. The button is the keyboard and
// screen-reader path; scrolling it into view loads the next page as well.
export function LoadMore({ list }) {
  const sentinel = useRef(null);
  const { hasMore, loadingMore, loadMore } = list;
  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasMore || typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadMore();
    }, { rootMargin: '240px' });
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loadMore]);
  return <div className="paged-list-footer" ref={sentinel}>
    <span className="sr-only" role="status" aria-live="polite">{list.loaded ? tx`${formatNumberLocale(list.items.length)} shown` : ''}</span>
    {hasMore && <button type="button" className="button quiet small" onClick={loadMore} disabled={loadingMore} aria-busy={loadingMore}>{loadingMore ? t("Loading…") : t("Load more")}</button>}
  </div>;
}

// True while the first page is on its way and nothing is on screen yet.
export const firstPageLoading = (list) => list.loading && !list.items.length;

// A <select> backed by server search over `resource`, for forms whose options are
// too many to load at once. `value`/`onChange` make it controlled; `name` keeps it
// working inside a plain <form> submitted with FormData. `copy` holds its
// translated texts: search, loading, select, more and selected.
function SearchSelect({ resource, pageSize, toText, copy, name, label, hint = '', required = false, value = '', onChange, selectedLabel = '', disabled = false }) {
  const [search, setSearch] = useState('');
  const [current, setCurrent] = useState(value ? String(value) : '');
  const labelId = useId();
  const list = usePagedList(resource, { search, ordering: 'name', pageSize });
  useEffect(() => {setCurrent(value ? String(value) : '');}, [value]);
  const options = list.items.map((item) => ({ id: String(item.id), text: toText(item) }));
  // Keep the chosen option selectable even when the search hides it.
  if (current && !options.some((option) => option.id === current)) options.unshift({ id: current, text: selectedLabel || copy.selected });
  function choose(event) {
    setCurrent(event.target.value);
    onChange?.(event.target.value);
  }
  return <div className="field student-picker">
    <span id={labelId}>{t(label)}</span>
    <label className="member-search"><Search size={15} /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={copy.search} aria-label={copy.search} disabled={disabled} /></label>
    <select name={name} value={current} onChange={choose} required={required} aria-labelledby={labelId} aria-busy={list.loading} disabled={disabled}>
      <option value="" disabled>{list.loading && !options.length ? copy.loading : copy.select}</option>
      {options.map((option) => <option key={option.id} value={option.id}>{option.text}</option>)}
    </select>
    {list.hasMore && <small className="field-hint">{copy.more}</small>}
    {hint && <small className="field-hint">{hint}</small>}
    {list.error && <small className="field-error">{list.error}</small>}
  </div>;
}

/**
 * A student <select> backed by server search, for forms used by staff with
 * thousands of students.
 */
export function StudentPicker({ name = 'student', label = 'Student', ...props }) {
  const copy = { search: t("Search students"), loading: t("Loading students…"), select: t("Select student"), more: t("Type a name to find more students."), selected: t("Selected student") };
  return <SearchSelect resource="students" pageSize={50} toText={(student) => fullName(student.user_detail)} copy={copy} name={name} label={label} {...props} />;
}

// A university <select> searching the ~1,500-row catalogue on the server instead
// of loading it into the form.
export function UniversityPicker({ name = 'university', label = 'University', ...props }) {
  const copy = { search: t("Search universities"), loading: t("Loading universities…"), select: t("Select university"), more: t("Type a name to find more universities."), selected: t("Selected university") };
  return <SearchSelect resource="universities" pageSize={25} toText={(university) => `${university.name} — ${university.country}`} copy={copy} name={name} label={label} {...props} />;
}
