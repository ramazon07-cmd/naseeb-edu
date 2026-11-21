import { useEffect, useRef } from 'react';
import { ChevronRight, FileText, Search } from 'lucide-react';
import { t } from '../i18n';
import { Empty } from './ui';
import '../design/blue/search.css';

// The Ctrl+K palette body. `items` are already the rows to show (pages when the
// box is empty, matches otherwise); the caller owns the query, the active row and
// opening a result. `look="student"` is the blue palette (grouped rows, icons,
// highlighted active row, Esc hint); any other look keeps the classic list.
export function SearchPalette({ look, query, onQuery, items, active, onPick, onKeyDown, onHover, icons, searching }) {
  const listRef = useRef(null);
  const student = look === 'student';
  useEffect(() => {
    if (!student) return;
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
  }, [student, active, items]);
  const input = <input autoFocus value={query} onChange={(event) => onQuery(event.target.value)} placeholder={t('Search pages and records…')} aria-label={t('Search pages and records')} onKeyDown={onKeyDown}
  {...(student ? { role: 'combobox', 'aria-expanded': 'true', 'aria-controls': 'nb-pal-list', 'aria-activedescendant': items[active] ? `nb-pal-${items[active].id}` : undefined, autoComplete: 'off' } : {})} />;
  if (!student) {
    return <div className="sidebar-utility-panel"><label className="search"><Search size={18} />{input}</label><div className="sidebar-search-results">{items.map((result) => <button key={result.id} onClick={() => onPick(result)}><span>{result.title}{result.kind === 'record' && result.subtitle && <small>{result.subtitle}</small>}</span><ChevronRight size={16} /></button>)}{query.trim() && !items.length && <Empty text={t('No information available yet.')} />}</div></div>;
  }
  let lastKind = '';
  return <div className="nb-pal">
    <label className="nb-pal-in"><Search size={18} aria-hidden="true" />{input}<kbd>Esc</kbd></label>
    <div className="nb-pal-res" id="nb-pal-list" role="listbox" aria-label={t('Search')} ref={listRef}>
      {items.map((result, index) => {
        const Icon = icons[result.destination] || FileText;
        const heading = result.kind !== lastKind ? (result.kind === 'record' ? t('Records') : t('Pages')) : null;
        lastKind = result.kind;
        return <div key={result.id} role="presentation">
          {heading && <p className="nb-pal-group" role="presentation">{heading}</p>}
          <button type="button" id={`nb-pal-${result.id}`} role="option" aria-selected={index === active} tabIndex={-1} className={`nb-pal-item${index === active ? ' is-active' : ''}`} onClick={() => onPick(result)} onMouseMove={() => onHover(index)}>
            <Icon size={18} aria-hidden="true" /><span>{result.title}</span>{result.kind === 'record' && result.subtitle && <small>{result.subtitle}</small>}
          </button>
        </div>;
      })}
      {query.trim() && !items.length && <p className="nb-pal-empty" role="status">{searching ? t('Searching…') : t('No results found')}</p>}
    </div>
  </div>;
}
