import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, X } from 'lucide-react';
import { daysUntil } from '../../lib/college';
import { isOpenTask } from '../../lib/metrics';
import { t, tp } from '../../i18n';
import './urgent.css';

export const URGENT_DAY_KEY = 'naseeb-urgent-day-v1';
const WAIT_MS = 90000; // the design shows it 90 seconds after the student arrives
const RETRY_MS = 8000; // a window or the tour is open: wait a little

const today = () => new Date().toISOString().slice(0, 10);
const shownToday = (userId) => { try { return localStorage.getItem(`${URGENT_DAY_KEY}:${userId}`) === today(); } catch { return true; } };
const markShown = (userId) => { try { localStorage.setItem(`${URGENT_DAY_KEY}:${userId}`, today()); } catch { /* shown again next time */ } };

// Open tasks that are already late, most overdue first. Real data only: nothing is shown without one.
export function overdueTasks(tasks) {
  return (tasks || []).filter(isOpenTask)
    .map((task) => ({ task, days: daysUntil(task.due_date) }))
    .filter((row) => row.days != null && row.days < 0)
    .sort((a, b) => a.days - b.days);
}

// The one urgent thing arrives as a gentle pop-up, once a day. It reads the tasks the shell
// already holds, so it makes no request. "Open tasks" is the real action; Ignore closes it.
export function UrgentPopup({ userId, tasks, canOpenTasks, openTasks, suspended }) {
  const [rows, setRows] = useState(null);
  const tasksRef = useRef(tasks);
  const suspendedRef = useRef(suspended);
  const cardRef = useRef(null);
  const backRef = useRef(null);
  tasksRef.current = tasks;
  suspendedRef.current = suspended;

  useEffect(() => {
    if (shownToday(userId)) return undefined;
    let timer = window.setTimeout(function attempt() {
      const busy = suspendedRef.current || document.querySelector('.nb-blue [role="dialog"], .nb-blue [aria-modal="true"]');
      if (busy) { timer = window.setTimeout(attempt, RETRY_MS); return; }
      const late = overdueTasks(tasksRef.current);
      if (!late.length) return; // nothing urgent: not shown, and tried again tomorrow
      markShown(userId);
      backRef.current = document.activeElement;
      setRows(late);
    }, WAIT_MS);
    return () => window.clearTimeout(timer);
  }, [userId]);

  const close = () => {
    setRows(null);
    const back = backRef.current;
    if (back?.isConnected) requestAnimationFrame(() => back.focus({ preventScroll: true }));
  };

  useEffect(() => {
    if (!rows) return undefined;
    cardRef.current?.querySelector('[data-urgent-primary]')?.focus();
    const keys = (event) => {
      if (event.key === 'Escape') { event.stopPropagation(); close(); return; }
      if (event.key !== 'Tab' || !cardRef.current) return;
      const items = [...cardRef.current.querySelectorAll('button:not([disabled])')];
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', keys, true);
    return () => document.removeEventListener('keydown', keys, true);
  }, [rows]);

  if (!rows) return null;
  const shown = rows.slice(0, 3);
  return createPortal(<div className="nb-urgent-scrim" onPointerDown={(event) => { if (event.target === event.currentTarget) close(); }}>
    <div className="nb-urgent" ref={cardRef} role="alertdialog" aria-modal="true" aria-labelledby="nb-urgent-title">
      <button type="button" className="nb-urgent-x" onClick={close} aria-label={t('Close')}><X size={18} aria-hidden="true" /></button>
      <span className="nb-urgent-icon" aria-hidden="true"><AlertCircle size={26} /></span>
      <h2 id="nb-urgent-title">{tp('{n} overdue task|{n} overdue tasks', rows.length, { n: rows.length })}</h2>
      <p>{t('These need your attention first. Send your response or ask your counselor for a new date.')}</p>
      <ul>{shown.map(({ task, days }) => <li key={task.id}><b>{task.title}</b><small>{tp('{n} day late|{n} days late', -days, { n: -days })}</small></li>)}</ul>
      {rows.length > shown.length && <p className="nb-urgent-more">{t('+{n} more overdue', { n: rows.length - shown.length })}</p>}
      <div className="nb-urgent-actions">
        <button type="button" className="nb-urgent-ghost" onClick={close}>{t('Ignore')}</button>
        {canOpenTasks && <button type="button" className="nb-urgent-primary" data-urgent-primary onClick={() => { close(); openTasks(); }}>{t('Go to Tasks')}</button>}
      </div>
    </div>
  </div>, document.querySelector('.nb-blue') || document.body);
}
