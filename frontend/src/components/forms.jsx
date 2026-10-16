import { useEffect, useRef, useState } from 'react';
import { formatNumberLocale, t } from '../i18n';
import { Check, Target, CheckCircle2 } from 'lucide-react';

export function Field({ label: title, children, error = '', hint = '' }) {
  return <label className={`field ${error ? 'is-error' : ''}`.trim()}><span>{typeof title === 'string' ? t(title) : title}</span>{children}{error ? <small className="field-error">{error}</small> : hint ? <small className="field-hint">{hint}</small> : null}</label>;
}

// One choice out of a few short ones, all in view (the radios submit with the form like a select would).
export function SegmentedField({ name, label: title, options, value, required = false }) {
  const [current, setCurrent] = useState(value || options[0].value);
  return <div className="field" role="radiogroup" aria-label={t(title)}>
    <span>{t(title)}</span>
    <div className="segmented">
      {options.map((option) => <label key={option.value} className={`segmented-option tone-${option.value}`}>
        <input type="radio" name={name} value={option.value} checked={current === option.value} onChange={() => setCurrent(option.value)} required={required} />
        <span>{option.label}</span>
      </label>)}
    </div>
  </div>;
}

export function CheckboxControl({ children, className = '', ...props }) {
  return <label className={`checkbox-card ${className}`.trim()}>
    <input type="checkbox" {...props} />
    <span className="checkbox-indicator" aria-hidden="true"><Check size={14} strokeWidth={3} /></span>
    <span>{children}</span>
  </label>;
}

export function ChoiceCards({ name, label: groupLabel, value, onChange, options }) {
  function handleKeyDown(event, index) {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const direction = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1;
    const nextIndex = (index + direction + options.length) % options.length;
    onChange(options[nextIndex].value);
    event.currentTarget.closest('.choice-card-group')?.querySelectorAll('input')[nextIndex]?.focus();
  }
  return <div className="choice-card-group" role="radiogroup" aria-label={groupLabel} style={{ '--choice-columns': options.length }}>
    {options.map((option, index) => {
      const OptionIcon = option.icon || Target;
      return <label className="choice-card" key={option.value}>
        <input type="radio" name={name} value={option.value} checked={value === option.value} onChange={() => onChange(option.value)} onKeyDown={(event) => handleKeyDown(event, index)} />
        <OptionIcon aria-hidden="true" />
        <span className="choice-card-copy"><b>{t(option.label)}</b><small>{t(option.description)}</small></span>
        <CheckCircle2 className="choice-card-check" size={19} aria-hidden="true" />
      </label>;
    })}
  </div>;
}

export function FilterChip({ active, onClick, tone = '', children }) {
  return <button type="button" className={`filter-chip ${tone}`.trim()} aria-pressed={active} onClick={onClick}>{children}</button>;
}

export function PortalTabs({ items, active, onChange }) {
  const listRef = useRef(null);
  // On narrow screens the bar scrolls sideways: keep the selected tab in view
  // (a direct link to the last tab), moving only the bar, never the page.
  useEffect(() => {
    const list = listRef.current;
    const tab = list?.querySelector('[aria-selected="true"]');
    if (!tab || list.scrollWidth <= list.clientWidth) return;
    const box = list.getBoundingClientRect();
    const rect = tab.getBoundingClientRect();
    list.scrollLeft += rect.left - box.left - (box.width - rect.width) / 2;
  }, [active]);
  function handleKeyDown(event, index) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length;
    onChange(items[nextIndex][0]);
    event.currentTarget.parentElement?.querySelectorAll('[role="tab"]')[nextIndex]?.focus();
  }
  return <div className="portal-tabs" role="tablist" ref={listRef}>{items.map(([key, title, count], index) => <button type="button" role="tab" aria-selected={active === key} tabIndex={active === key ? 0 : -1} key={key} className={active === key ? "active" : ''} onClick={() => onChange(key)} onKeyDown={(event) => handleKeyDown(event, index)}>{t(title)}{count != null && <span className="tab-count">{formatNumberLocale(count)}</span>}</button>)}</div>;
}
