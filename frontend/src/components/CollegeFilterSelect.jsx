import { useEffect, useId, useRef, useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { formatNumberLocale } from '../i18n';

export function CollegeFilterSelect({ label, value, options, onChange }) {
  const id = useId();
  const root = useRef(null);
  const trigger = useRef(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const selected = Math.max(0, options.findIndex((option) => option.value === value));

  useEffect(() => {
    if (!open) return;
    const dismiss = (event) => { if (!root.current?.contains(event.target)) setOpen(false); };
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [open]);

  function choose(index) {
    onChange(options[index].value);
    setOpen(false);
    trigger.current?.focus();
  }

  function onKeyDown(event) {
    if (event.key === 'Tab') { setOpen(false); return; }
    if (event.key === 'Escape') { setOpen(false); event.stopPropagation(); return; }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(event.key)) {
      event.preventDefault();
      if (event.key === 'Enter' || event.key === ' ') {
        if (open) choose(active);
        else { setActive(selected); setOpen(true); }
        return;
      }
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      setActive(event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : open ? (active + direction + options.length) % options.length : selected);
      setOpen(true);
    } else if (event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey) {
      const index = options.findIndex((option, index) => index > active && option.label.toLocaleLowerCase().startsWith(event.key.toLocaleLowerCase()));
      const match = index >= 0 ? index : options.findIndex((option) => option.label.toLocaleLowerCase().startsWith(event.key.toLocaleLowerCase()));
      if (match >= 0) { setActive(match); setOpen(true); }
    }
  }

  return <div ref={root} className={`college-select-field ${value ? 'is-selected' : ''} ${open ? 'is-open' : ''}`} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <button ref={trigger} type="button" className="college-select-trigger" role="combobox" aria-label={label} aria-expanded={open} aria-haspopup="listbox" aria-controls={`${id}-options`} aria-activedescendant={open ? `${id}-option-${active}` : undefined} onKeyDown={onKeyDown} onClick={() => { setActive(selected); setOpen(!open); }}>
      <span className="college-select-label">{label}</span><span className="college-select-value"><b>{options[selected]?.label}</b><ChevronDown size={15} aria-hidden="true" /></span>
    </button>
    {open && <div id={`${id}-options`} className="college-select-menu" role="listbox" aria-label={label}>{options.map((option, index) => <div id={`${id}-option-${index}`} role="option" aria-selected={option.value === value} className={index === active ? 'is-active' : ''} key={option.value} onPointerMove={() => setActive(index)} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(index)}>
      <span>{option.label}</span>{option.count != null && <small>{formatNumberLocale(option.count)}</small>}<Check size={15} aria-hidden="true" className={option.value === value ? '' : 'is-hidden'} />
    </div>)}</div>}
  </div>;
}
