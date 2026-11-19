import { useState } from 'react';
import { Plus, Radar, Trash2, X } from 'lucide-react';
import { formatDateLocale, formatNumberLocale, parseDateValue, t, tp } from '../i18n';
import { daysUntil, dueLabel, dueTone, longDate } from '../lib/college';
import { Modal } from './ui';
import '../design/pages/apps-blue.css';

// The student's own deadlines (thesis, a school form, a test date) live in this browser only.
const MY_DEADLINES_KEY = 'nsb-mydl';
const MY_KINDS = [['task', 'Task'], ['uni', 'University'], ['prog', 'Program']];
function readMyDeadlines() {
  try {
    const list = JSON.parse(window.localStorage.getItem(MY_DEADLINES_KEY) || '[]');
    return Array.isArray(list) ? list.filter((entry) => entry && typeof entry.t === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(entry.d)) : [];
  } catch { return []; }
}
function writeMyDeadlines(list) {
  try { window.localStorage.setItem(MY_DEADLINES_KEY, JSON.stringify(list)); } catch {/* The deadline stays for this visit only. */}
}

const lateLabel = (days) => days < 0 ? tp('{n} day late|{n} days late', -days, { n: formatNumberLocale(-days) }) : dueLabel(days);

// Every application and scholarship deadline on the page plus the student's own, in four views:
// what is overdue, what is due in two weeks, what comes in four months, and by type.
function RadarDialog({ programs = [], onOpenProgram, applications, applicationsLoaded, onOpenApplications, onOpen, onClose }) {
  const [mine, setMine] = useState(readMyDeadlines);
  const [type, setType] = useState('all');
  const [win, setWin] = useState('all');
  const [form, setForm] = useState(null);
  const saveMine = (list) => { setMine(list); writeMyDeadlines(list); };
  const items = [
    ...applications.flatMap((application) => [['application', application.deadline], ['aid', application.scholarship_deadline]]
      .filter(([, date]) => daysUntil(date) != null && !['accepted', 'rejected', 'waitlisted'].includes(application.status))
      .map(([kind, date]) => ({ key: `${application.id}-${kind}`, group: 'uni', application, kind, date, days: daysUntil(date), title: application.university_detail?.name || t("University"), sub: `${kind === 'aid' ? t("Scholarship") : t("Application")} · ${longDate(date)}` }))),
    ...programs.map((program) => ({ key: `prog-${program.id}`, group: 'prog', programId: program.id, date: program.date, days: daysUntil(program.date), title: program.title, sub: program.exact ? t('Program') : `${t('My List')} · ≈` })),
    ...mine.map((entry, index) => ({ key: `mine-${index}`, group: 'mine', index, date: entry.d, days: daysUntil(entry.d), title: entry.t, sub: `${t(MY_KINDS.find(([kind]) => kind === entry.k)?.[1] || 'Task')} · ${longDate(entry.d)}` })),
  ].filter((item) => item.days != null).sort((a, b) => a.days - b.days);
  const over = items.filter((item) => item.days < 0);
  const soon = items.filter((item) => item.days >= 0 && item.days <= 14);
  const plan = items.filter((item) => item.days > 14 && item.days <= 120);
  const inWindow = (item) => win === 'all' || (win === 'over' ? item.days < 0 : win === 'soon' ? item.days >= 0 && item.days <= 14 : item.days > 14 && item.days <= 120);
  const list = items.filter((item) => (type === 'all' || item.group === type) && inWindow(item));
  const groups = [];
  const add = (key, title, entries) => { if (entries.length) groups.push({ key, title, entries }); };
  add('over', t("Overdue"), list.filter((item) => item.days < 0));
  add('week', t("This week"), list.filter((item) => item.days >= 0 && item.days <= 7));
  add('month', t("Next 30 days"), list.filter((item) => item.days > 7 && item.days <= 30));
  list.filter((item) => item.days > 30).forEach((item) => {
    const key = item.date.slice(0, 7);
    let group = groups.find((entry) => entry.key === key);
    if (!group) groups.push(group = { key, title: formatDateLocale(`${key}-01`, { month: 'long', year: 'numeric' }), entries: [] });
    group.entries.push(item);
  });
  const cards = [['over', 'is-over', t("Overdue"), t("Needs your action now"), over, t("Nothing overdue")], ['soon', 'is-soon', t("Due in the next 14 days"), t("Start these first"), soon, t("Nothing due in the next two weeks")], ['plan', 'is-plan', t("Coming up in 4 months"), t("Plan ahead"), plan, '']];
  function submit(event) {
    event.preventDefault();
    const name = form.name.trim();
    if (!name || !/^\d{4}-\d{2}-\d{2}$/.test(form.date)) { setForm({ ...form, error: true }); return; }
    const record = { t: name, d: form.date, k: form.kind };
    saveMine(form.index == null ? [...mine, record] : mine.map((entry, index) => index === form.index ? record : entry));
    setForm(null);
  }
  const edit = (item) => setForm({ index: item.index, name: mine[item.index].t, date: mine[item.index].d, kind: mine[item.index].k || 'task', error: false });
  return <Modal title={t("Deadline radar")} onClose={onClose} className="apps-radar">
    <div className="nb-radar">
      {!applicationsLoaded && <p className="nb-radar-notice" role="note"><span>{t("Open Applications to include university deadlines")}</span>{onOpenApplications && <button type="button" className="button quiet small" onClick={onOpenApplications}>{t("Go to Applications")}</button>}</p>}
      <div className="nb-radar-cards">{cards.map(([key, tone, title, hint, entries, okText]) => <button type="button" key={key} className={`nb-radar-card ${tone} ${win === key ? 'is-on' : ''} ${entries.length ? '' : 'is-zero'}`.trim()} aria-pressed={win === key} onClick={() => setWin(win === key ? 'all' : key)}>
        <span className="nb-radar-card-title">{title}</span>
        <span className="nb-radar-card-n"><b>{formatNumberLocale(entries.length)}</b><small>{entries.length ? hint : okText}</small></span>
        {entries[0] && <span className="nb-radar-card-next"><small>{t("Next")}</small><b>{entries[0].title}</b><em>{lateLabel(entries[0].days)}</em></span>}
      </button>)}</div>
      <div className="nb-radar-bar">
        <div className="apps-view" role="group" aria-label={t("Deadline type")}>{[['all', t("All types")], ['uni', t("University")], ...(programs.length ? [['prog', t("Programs")]] : []), ['mine', t("Mine")]].map(([key, title]) => <button type="button" key={key} aria-pressed={type === key} onClick={() => setType(key)}>{title}</button>)}</div>
        {win !== 'all' && <button type="button" className="nb-radar-showing" onClick={() => setWin('all')}>{t("Showing")}: {cards.find(([key]) => key === win)[2]}<X size={13} aria-hidden="true" /></button>}
        <button type="button" className="button quiet small nb-radar-add" onClick={() => setForm({ index: null, name: '', date: '', kind: 'task', error: false })}><Plus size={14} aria-hidden="true" /> {t("Add your own")}</button>
      </div>
      {form && <form className="nb-radar-form" onSubmit={submit} noValidate>
        <label><span>{t("Name")}</span><input value={form.name} maxLength={80} autoFocus placeholder={t("e.g. Passport renewal")} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        <label><span>{t("Date")}</span><input type="date" value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} /></label>
        <label><span>{t("Type")}</span><select value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value })}>{MY_KINDS.map(([key, title]) => <option key={key} value={key}>{t(title)}</option>)}</select></label>
        {form.error && <p className="nb-radar-error" role="alert">{t("Enter a name and a date.")}</p>}
        <div className="nb-radar-form-actions">
          {form.index != null && <button type="button" className="button quiet small danger" onClick={() => { saveMine(mine.filter((_, index) => index !== form.index)); setForm(null); }}><Trash2 size={14} aria-hidden="true" /> {t("Delete")}</button>}
          <span />
          <button type="button" className="button quiet small" onClick={() => setForm(null)}>{t("Cancel")}</button>
          <button type="submit" className="button primary small">{t("Save")}</button>
        </div>
      </form>}
      {groups.length ? groups.map((group) => <section className={`nb-radar-group g-${group.key.length === 7 ? 'later' : group.key}`} key={group.key}><h3><span>{group.title}</span><i>{formatNumberLocale(group.entries.length)}</i></h3>
        <ul className="apps-radar-list">{group.entries.map((item) => <li key={item.key} className={item.days < 0 ? 'is-over' : item.days <= 7 ? 'is-hot' : ''}>
          <button type="button" onClick={() => item.group === 'mine' ? edit(item) : item.group === 'prog' ? onOpenProgram?.(item.programId) : onOpen(item.application)}>
            <span className="apps-radar-date"><b>{parseDateValue(item.date).getDate()}</b><small>{formatDateLocale(item.date, { month: 'short' }).replace(/\.$/, '')}</small></span>
            <span className="apps-radar-copy"><b>{item.title}</b><small>{item.sub}</small></span>
            <span className={`due ${item.days < 0 ? 'hot' : dueTone(item.days)}`.trim()}>{lateLabel(item.days)}</span>
          </button>
        </li>)}</ul></section>) : <p className="board-empty">{items.length ? t("Nothing here") : t("No upcoming deadlines yet.")}</p>}
    </div>
  </Modal>;
}

// Reusable radar: the caller passes the applications it already has and decides what opening one does.
// The student's own deadlines are read from and written to this browser only.
export function DeadlineRadar({ open, onClose, programs = [], onOpenProgram, applications = [], applicationsLoaded = true, onOpenApplications, onOpen }) {
  if (!open) return null;
  return <RadarDialog programs={programs} onOpenProgram={onOpenProgram} applications={applications} applicationsLoaded={applicationsLoaded} onOpenApplications={onOpenApplications} onOpen={onOpen || (() => {})} onClose={onClose} />;
}

export function DeadlineRadarButton({ onClick, className = '', size = 16 }) {
  return <button type="button" className={`button quiet apps-radar-button ${className}`.trim()} aria-haspopup="dialog" onClick={onClick}><Radar size={size} aria-hidden="true" /> {t("Deadline radar")}</button>;
}
