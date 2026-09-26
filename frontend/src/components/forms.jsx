import { t } from '../i18n';
import { Check, Target, CheckCircle2 } from 'lucide-react';

export function Field({ label: title, children, error = '', hint = '' }) {
  return <label className={`field ${error ? 'is-error' : ''}`.trim()}><span>{typeof title === 'string' ? t(title) : title}</span>{children}{error ? <small className="field-error">{error}</small> : hint ? <small className="field-hint">{hint}</small> : null}</label>;
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
  function handleKeyDown(event, index) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length;
    onChange(items[nextIndex][0]);
    event.currentTarget.parentElement?.querySelectorAll('[role="tab"]')[nextIndex]?.focus();
  }
  return <div className="portal-tabs" role="tablist">{items.map(([key, title], index) => <button type="button" role="tab" aria-selected={active === key} tabIndex={active === key ? 0 : -1} key={key} className={active === key ? "active" : ''} onClick={() => onChange(key)} onKeyDown={(event) => handleKeyDown(event, index)}>{t(title)}</button>)}</div>;
}
