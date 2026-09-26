import { useEffect, useId, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { t } from '../i18n';
import { nextMenuIndex } from '../lib/menuNavigation';

// One primary "Add" button that asks what to add. A dropdown menu on wide
// screens, a bottom sheet on phones (CSS only, same markup and keyboard model).
export function AddMenu({ items, onSelect, label = t('Add'), heading = t('What do you want to add?') }) {
  const [open, setOpen] = useState(false);
  const root = useRef(null);
  const trigger = useRef(null);
  const menuId = useId();
  const headingId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => { if (!root.current?.contains(event.target)) setOpen(false); };
    document.addEventListener('pointerdown', close);
    root.current?.querySelector('[role="menuitem"]')?.focus();
    return () => document.removeEventListener('pointerdown', close);
  }, [open]);

  function dismiss() {
    setOpen(false);
    trigger.current?.focus();
  }

  function onMenuKeyDown(event) {
    const entries = [...(root.current?.querySelectorAll('[role="menuitem"]') || [])];
    const index = entries.indexOf(document.activeElement);
    const move = nextMenuIndex(event.key, index, entries.length);
    if (move !== null) {
      event.preventDefault();
      entries[move]?.focus();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      dismiss();
    } else if (event.key === 'Tab') {
      setOpen(false);
    }
  }

  function onTriggerKeyDown(event) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setOpen(true);
    }
  }

  function choose(key) {
    setOpen(false);
    onSelect(key);
  }

  return <div className="add-menu" ref={root}>
    <button ref={trigger} type="button" className="button primary add-menu-trigger" aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
      onClick={() => setOpen((value) => !value)} onKeyDown={onTriggerKeyDown}><Plus size={17} aria-hidden="true" /> {label}</button>
    {open && <>
      <div className="add-menu-backdrop" aria-hidden="true" onClick={dismiss} />
      <div className="add-menu-list" role="menu" id={menuId} aria-labelledby={headingId} onKeyDown={onMenuKeyDown}>
        <p className="add-menu-heading" id={headingId}>{heading}</p>
        {items.map(({ key, label: text, hint, icon: Icon }) => <button key={key} type="button" role="menuitem" onClick={() => choose(key)}>
          {Icon && <Icon size={18} aria-hidden="true" />}
          <span><b>{text}</b>{hint && <small>{hint}</small>}</span>
        </button>)}
      </div>
    </>}
  </div>;
}
