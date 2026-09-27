import { useEffect, useRef } from 'react';
import { Inbox, X } from 'lucide-react';
import { t } from '../i18n';
import { label } from '../lib/labels';

export function Badge({ children, tone = '' }) {
  const normalized = String(children || '').toLowerCase().replaceAll(' ', '-');
  return <span className={`badge ${tone || normalized}`}>{label(children)}</span>;
}

export function Modal({ title, onClose, children, className = '', backdropClassName = '' }) {
  const modalRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    const modal = modalRef.current;
    const focusable = () => [...(modal?.querySelectorAll('button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])') || [])];
    focusable()[0]?.focus();
    function handleKeyDown(event) {
      if (event.key === 'Escape') {event.preventDefault();onCloseRef.current();return;}
      if (event.key !== 'Tab') return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {event.preventDefault();last.focus();} else
      if (!event.shiftKey && document.activeElement === last) {event.preventDefault();first.focus();}
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => {document.removeEventListener('keydown', handleKeyDown);previous?.focus?.();};
  }, []);
  return <div className={`modal-backdrop ${backdropClassName}`.trim()} role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
    <section ref={modalRef} className={`modal ${className}`} role="dialog" aria-modal="true" aria-label={t(title)} tabIndex="-1">
      <header><div><span className="eyebrow">{t("NASEEB EDU")}</span><h2>{t(title)}</h2></div><button className="icon-button" onClick={onClose} aria-label={t('Close')}><X /></button></header>
      {children}
    </section>
  </div>;
}

export function Empty({ text = 'No information available yet.', action = null }) {
  return <div className="empty"><span aria-hidden="true"><Inbox size={34} strokeWidth={1.4} /></span><p>{t(text)}</p>{action}</div>;
}

export function Panel({ title, action, utility, children, footer, className = '' }) {
  return <section className={`panel ${className}`}><header><h2>{t(title)}</h2>{utility ? <div className="panel-actions panel-header-actions">{utility}{action}</div> : action}</header><div className="panel-body">{children}</div>{footer && <div className="panel-footer">{footer}</div>}</section>;
}
