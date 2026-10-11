import { useEffect, useId, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { api, request } from '../api';
import { t } from '../i18n';
import { fullName } from '../lib/labels';
import './student-search.css';

const toChoice = (student) => ({ id: student.id, name: fullName(student.user_detail) || student.user_detail?.username || '' });

/**
 * One input that finds a student by name on the server and picks them.
 * `value`: the chosen student ({ id, name }) or null; a value without a name
 * has its name looked up. `onChange(student | null)`. `name` adds a hidden
 * input carrying the id, for forms read with FormData.
 */
export function StudentSearchInput({ value = null, onChange, name, label = 'Student', required = false, disabled = false, hint = '' }) {
  const labelId = useId();
  const listId = useId();
  const [failedId, setFailedId] = useState(null);
  const lookupFailed = Boolean(value?.id) && !value.name && failedId === value.id;
  const lookingUp = Boolean(value?.id) && !value.name && !lookupFailed;
  const shownName = value?.name || (lookupFailed ? `${t('Student')} #${value.id}` : '');
  const [query, setQuery] = useState(shownName);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [found, setFound] = useState({ term: null, items: [], error: '' });
  const term = query.trim();
  const typing = open && term !== shownName;
  const searchTerm = typing ? term : '';

  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => { setQuery(shownName); }, [shownName]);

  useEffect(() => {
    if (!value?.id || value.name) return undefined;
    let live = true;
    const id = value.id;
    request(`/students/${id}/`).then((student) => { if (live && student) onChangeRef.current?.(toChoice(student)); }).catch(() => { if (live) setFailedId(id); });
    return () => { live = false; };
  }, [value?.id, value?.name]);

  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api.page('students', `?${new URLSearchParams({ search: searchTerm, page_size: '10' })}`, controller.signal)
        .then((data) => setFound({ term: searchTerm, items: (data?.results || []).map(toChoice), error: '' }))
        .catch((err) => { if (err?.name !== 'AbortError') setFound({ term: searchTerm, items: [], error: err?.message || t("Check your connection and try again.") }); });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [open, searchTerm]);

  const searching = found.term !== searchTerm;
  const options = searching ? [] : found.items;
  function close() {
    setOpen(false);
    setQuery(shownName);
  }
  function pick(choice) {
    onChange?.(choice);
    setQuery(choice.name);
    setOpen(false);
  }
  function onKeyDown(event) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setOpen(true);
      if (options.length) setActive((index) => (index + (event.key === 'ArrowDown' ? 1 : options.length - 1)) % options.length);
    } else if (event.key === 'Enter' && open) {
      event.preventDefault();
      if (options[active]) pick(options[active]);
    } else if (event.key === 'Escape' && open) {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  }
  const optionId = (index) => `${listId}-${index}`;
  return <div className="field student-search">
    <span id={labelId}>{t(label)}</span>
    <div className="student-search-box">
      <Search size={15} aria-hidden="true" />
      <input aria-labelledby={labelId} type="text" role="combobox" autoComplete="off" required={required && !value?.id} disabled={disabled}
        aria-expanded={open} aria-controls={listId} aria-autocomplete="list"
        aria-activedescendant={open && options[active] ? optionId(active) : undefined}
        placeholder={lookingUp ? t("Loading…") : t("Search students")} value={query}
        onFocus={(event) => { setOpen(true); setActive(0); event.target.select(); }}
        onBlur={close}
        onChange={(event) => { setQuery(event.target.value); setActive(0); setOpen(true); }}
        onKeyDown={onKeyDown} />
      {name && <input type="hidden" name={name} value={value?.id ?? ''} />}
      {open && <ul id={listId} className="student-search-options" role="listbox" aria-label={t("Students")}>
        {options.map((choice, index) => <li key={choice.id} id={optionId(index)} role="option" aria-selected={index === active}
          className={`${index === active ? 'is-active' : ''}${choice.id === value?.id ? ' is-current' : ''}`}
          onMouseDown={(event) => event.preventDefault()} onMouseEnter={() => setActive(index)} onClick={() => pick(choice)}>{choice.name}</li>)}
        {searching ? <li className="student-search-note" role="status">{t("Searching…")}</li>
          : found.error ? <li className="student-search-note" role="alert">{found.error}</li>
            : !options.length && <li className="student-search-note">{t("No students found.")}</li>}
      </ul>}
    </div>
    {hint && <small className="field-hint">{hint}</small>}
  </div>;
}
