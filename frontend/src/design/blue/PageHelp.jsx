import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { CircleHelp, X } from 'lucide-react';
import { t } from '../../i18n';
import './tour.css';

// The "?" help sheet: every tip of the page in one list, with a button to walk through them.
export function PageHelp({ tips, tipsOff, onToggleTips, onStart, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    const back = document.activeElement;
    ref.current?.querySelector('[data-help-start]')?.focus();
    const keys = (event) => {
      if (event.key === 'Escape') { event.stopPropagation(); onClose(); return; }
      if (event.key !== 'Tab' || !ref.current) return;
      const items = [...ref.current.querySelectorAll('button:not([disabled])')];
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', keys, true);
    return () => { document.removeEventListener('keydown', keys, true); if (back?.isConnected) back.focus({ preventScroll: true }); };
  }, [onClose]);
  return createPortal(<div className="ng-help" onPointerDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="ng-hcard" ref={ref} role="dialog" aria-modal="true" aria-labelledby="ng-help-title">
      <div className="ng-hh">
        <span className="ng-hq" aria-hidden="true"><CircleHelp size={22} /></span>
        <h2 id="ng-help-title">{t('How this page works')}</h2>
        <button type="button" className="ng-x" onClick={onClose} aria-label={t('Close')}><X size={18} aria-hidden="true" /></button>
      </div>
      <ol className="ng-hl">{tips.map((tip, index) => <li key={tip.id}><span aria-hidden="true">{index + 1}</span><div><b>{tip.title}</b><p>{tip.text}</p></div></li>)}</ol>
      <div className="ng-hb">
        <button type="button" className="ng-skip" onClick={onToggleTips} aria-pressed={!tipsOff}>{tipsOff ? t('Turn on page tips') : t('Turn off page tips')}</button>
        <button type="button" className="ng-btn" onClick={onClose}>{t('Close')}</button>
        <button type="button" className="ng-btn is-primary" data-help-start onClick={onStart}>{t('Show me')}</button>
      </div>
    </div>
  </div>, document.querySelector('.nb-blue') || document.body);
}
