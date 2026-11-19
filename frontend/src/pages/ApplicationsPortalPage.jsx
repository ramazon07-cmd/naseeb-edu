import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowDownWideNarrow, ArrowRight, CalendarDays, Check, CheckCircle2, Clock3, GripVertical, Hourglass, Link2, Lock, MapPin, MoreHorizontal, Pencil, Plus, Rows3, Search, Trash2, X, Columns3, Radar } from 'lucide-react';
import { api } from '../api';
import { formatDateLocale, formatNumberLocale, parseDateValue, t, tp, tx } from '../i18n';
import { FilterChip } from '../components/forms';
import { DeadlineChip, TierBand } from '../components/college';
import { money } from '../lib/format';
import { label } from '../lib/labels';
import { institutionStatus } from '../lib/qs';
import { matchesQuery } from '../lib/searchIndex';
import { APPLICATION_STAGES, daysUntil, dueLabel, dueTone, historyDate, longDate, nextDeadline, percentText, priceInfo, satLabel, scalePercent, shortDate, stageOf } from '../lib/college';
import { ApplicationPlan } from '../components/ApplicationPlan';
import { planNextStep } from '../lib/applicationPlan';
import { Modal } from '../components/ui';
import { BlueButton, EmptyState, PageHeader } from '../design/blue/ui';
import '../design/pages/catalog-blue-base.css';
import '../design/pages/apps-blue.css';

function ApplicationSummary({ applications, essays, letters, openApplication, setPage }) {
  const next = nextDeadline(applications);
  const tiers = { dream: 0, target: 0, safety: 0 };
  applications.forEach((application) => {tiers[application.tier] = (tiers[application.tier] || 0) + 1;});
  const countEssays = (status) => essays.filter((essay) => essay.status === status).length;
  const essayNote = [[countEssays('needs_revision'), tx`${countEssays('needs_revision')} need revision`], [countEssays('reviewing'), tx`${countEssays('reviewing')} in review`], [countEssays('draft'), tx`${countEssays('draft')} in draft`]].filter(([count]) => count).map(([, text]) => text).join(', ');
  const approvedEssays = countEssays('approved');
  const approvedLetters = letters.filter((letter) => letter.status === 'approved').length;
  const pendingLetter = letters.find((letter) => letter.status !== 'approved');
  const nextName = next?.application.university_detail?.name || t("University");
  return <div className="summary-grid">
    <section className={`info-card summary-card ${next && next.days <= 3 ? 'hot' : ''}`.trim()} aria-label={t("Next deadline")}>
      <h3>{t("Next deadline")}</h3>
      {next ? <>
        <div className="summary-big"><b>{next.days === 0 ? t("Today") : next.days === 1 ? t("Tomorrow") : formatNumberLocale(next.days)}</b>{next.days > 1 && <span>{t("days left")}</span>}</div>
        <p><b>{next.kind === 'aid' ? tx`${nextName} scholarship deadline` : tx`${nextName} application deadline`}</b><br />{longDate(next.date)} · {next.application.program}</p>
        <button type="button" className="button quiet small" onClick={() => openApplication(next.application)}>{t("Manage application")} <ArrowRight size={14} aria-hidden="true" /></button>
      </> : <>
        <div className="summary-big"><b>—</b></div>
        <p>{t("No upcoming deadlines. Set deadlines on your applications to see them here.")}</p>
      </>}
    </section>
    <section className="info-card summary-card" aria-label={t("Your list")}>
      <h3>{t("Your list")}</h3>
      <div className="summary-big"><b>{formatNumberLocale(applications.length)}</b><span>{t("applications")}</span></div>
      <div className="tier-mix" role="img" aria-label={tx`${tiers.dream} dream, ${tiers.target} target, ${tiers.safety} safety`}>{['dream', 'target', 'safety'].map((tier) => tiers[tier] > 0 && <i key={tier} className={tier} style={{ flex: tiers[tier] }} />)}</div>
      <div className="tier-counts">{['dream', 'target', 'safety'].map((tier) => <div key={tier}><b>{formatNumberLocale(tiers[tier])}</b><TierBand value={tier} /></div>)}</div>
    </section>
    <section className="info-card summary-card" aria-label={t("Essays")}>
      <h3>{t("Essays")}</h3>
      <div className="summary-big"><b>{tx`${approvedEssays} of ${essays.length}`}</b><span>{t("approved")}</span></div>
      <span className="score-bar wide" aria-hidden="true"><i style={{ '--fill': scalePercent(approvedEssays, 0, essays.length || 1) }} /></span>
      <p>{essays.length ? essayNote || t("All essays are approved.") : t("No essays yet")}</p>
      <button type="button" className="button quiet small" onClick={() => setPage('essay_lab')}>{t("Open Essay Lab")} <ArrowRight size={14} aria-hidden="true" /></button>
    </section>
    <section className="info-card summary-card" aria-label={t("Recommendation letters")}>
      <h3>{t("Recommendation letters")}</h3>
      <div className="summary-big"><b>{tx`${approvedLetters} of ${letters.length}`}</b><span>{t("approved")}</span></div>
      <span className="score-bar wide" aria-hidden="true"><i style={{ '--fill': scalePercent(approvedLetters, 0, letters.length || 1) }} /></span>
      <p>{pendingLetter ? `${pendingLetter.recommender_name} · ${label(pendingLetter.status)}. ` : ''}{t("Letters are shared across all applications.")}</p>
    </section>
  </div>;
}

const BRIEF_ROOM = 360; // px a card needs below it before its brief opens upward instead
// Without the Popover API (older Safari and Firefox) the brief is a plain fixed panel.
const HAS_POPOVER = typeof HTMLElement !== 'undefined' && typeof HTMLElement.prototype.showPopover === 'function';

function DecisionTag({ application, decidedAt }) {
  return <span className={`tag ${application.status === 'accepted' ? 'ok' : application.status === 'rejected' ? 'bad' : 'warn'}`}><CheckCircle2 size={12} aria-hidden="true" /> {label(application.status)}{decidedAt ? ` ${shortDate(decidedAt)}` : ''}</span>;
}

// Everything a compact board card leaves out. It is a non-modal popover: the top layer keeps
// it clear of the board's scroll clipping, and the page closes it on outside click, Escape and scroll.
function ApplicationBrief({ id, briefRef, application, info, essays, name, onOpen, onEdit, onClose }) {
  const stage = stageOf(application.status);
  const decided = stage === 'decision';
  const approved = essays.filter((essay) => essay.status === 'approved').length;
  const submittedAt = historyDate(application, 'submitted');
  const place = [[...new Set([info.city, info.country].filter(Boolean))].join(', '), institutionStatus(info, label)].filter(Boolean).join(' · ');
  const portalMissing = stage === 'applying' && !application.application_portal_url;
  const rows = decided || stage === 'submitted' ?
  [{ Icon: Check, title: t("Submitted"), date: submittedAt, chip: decided ? <DecisionTag application={application} decidedAt={historyDate(application, application.status)} /> : <span className="tag"><Hourglass size={12} aria-hidden="true" /> {t("Waiting")}</span> }] :
  [['aid', application.scholarship_deadline], ['application', application.deadline]].filter(([, date]) => date).sort(([, a], [, b]) => daysUntil(a) - daysUntil(b)).map(([kind, date]) => {
    const days = daysUntil(date);
    return { Icon: kind === 'aid' ? Clock3 : CalendarDays, title: kind === 'aid' ? t("Scholarship") : t("Application"), date, chip: <span className={`due ${dueTone(days)}`.trim()}>{dueLabel(days)}</span> };
  });
  return <div id={id} ref={briefRef} className="app-brief" popover={HAS_POPOVER ? 'manual' : undefined} role="dialog" aria-label={name} tabIndex={-1}>
    <header className="app-brief-head">
      <div>
        <TierBand value={application.tier} />
        <h4>{name}</h4>
        <p>{application.program}</p>
        {place && <small><MapPin size={12} aria-hidden="true" /> {place}</small>}
      </div>
      <button type="button" className="icon-button" aria-label={t("Close")} onClick={onClose}><X size={16} aria-hidden="true" /></button>
    </header>
    <dl className="app-brief-facts">
      <div><dt>{t("Acceptance")}</dt><dd>{percentText(info.acceptance_rate)}</dd></div>
      <div><dt>{t("SAT")}</dt><dd>{satLabel(info)}</dd></div>
      <div><dt>{priceInfo(info).label}</dt><dd>{money(priceInfo(info).amount)}</dd></div>
    </dl>
    <section className="app-brief-block">
      <div className="app-brief-eyebrow"><span>{decided || stage === 'submitted' ? t("Status") : t("Deadlines")}</span></div>
      {rows.length ? <ul className="app-brief-rows">{rows.map(({ Icon, title, date, chip }) => <li key={title}><span><Icon size={14} aria-hidden="true" /> {title}</span><b>{date ? shortDate(date) : '—'}</b>{chip}</li>)}</ul> : <p className="app-brief-empty">{t("No deadlines set")}</p>}
    </section>
    <section className="app-brief-block">
      <div className="app-brief-eyebrow"><span>{t("Essays")}</span>{essays.length > 0 && <span>{tx`${approved} of ${essays.length}`} {t("approved")}</span>}</div>
      {essays.length ? <>
        <span className="score-bar" aria-hidden="true"><i style={{ '--fill': scalePercent(approved, 0, essays.length) }} /></span>
        <ul className="app-brief-essays">{essays.map((essay) => <li key={essay.id}><span>{essay.title}</span><span className={`tag ${essay.status === 'approved' ? 'ok' : essay.status === 'needs_revision' ? 'warn' : ''}`.trim()}>{label(essay.status)}</span></li>)}</ul>
      </> : <p className="app-brief-empty">{t("No essays yet")}</p>}
    </section>
    {(portalMissing || info.css_profile_required) && <div className="app-brief-block tag-row">
      {portalMissing && <span className="tag warn"><Link2 size={12} aria-hidden="true" /> {t("Portal missing")}</span>}
      {info.css_profile_required && <span className="tag">{t("CSS Profile")}</span>}
    </div>}
    <footer className="app-brief-actions">
      <button type="button" className="button primary small" onClick={onEdit}>{t("Manage application")} <ArrowRight size={14} aria-hidden="true" /></button>
      <button type="button" className="button quiet small" onClick={onOpen}>{t("Open university page")}</button>
    </footer>
  </div>;
}

// The five stages with the current one marked, from the application's status (no history needed).
function StageStepper({ status }) {
  const current = APPLICATION_STAGES.findIndex((stage) => stage.key === stageOf(status));
  return <ol className="apps-stepper" aria-label={t("Application stage")}>{APPLICATION_STAGES.map((stage, index) => <li key={stage.key} className={index < current ? 'is-done' : index === current ? 'is-current' : ''} aria-current={index === current ? 'step' : undefined}><i aria-hidden="true">{index < current ? <Check size={11} /> : index + 1}</i><span>{t(stage.title)}</span></li>)}</ol>;
}

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
function DeadlineRadar({ applications, onOpen, onClose }) {
  const [mine, setMine] = useState(readMyDeadlines);
  const [type, setType] = useState('all');
  const [win, setWin] = useState('all');
  const [form, setForm] = useState(null);
  const saveMine = (list) => { setMine(list); writeMyDeadlines(list); };
  const items = [
    ...applications.flatMap((application) => [['application', application.deadline], ['aid', application.scholarship_deadline]]
      .filter(([, date]) => daysUntil(date) != null && !['accepted', 'rejected', 'waitlisted'].includes(application.status))
      .map(([kind, date]) => ({ key: `${application.id}-${kind}`, group: 'uni', application, kind, date, days: daysUntil(date), title: application.university_detail?.name || t("University"), sub: `${kind === 'aid' ? t("Scholarship") : t("Application")} · ${longDate(date)}` }))),
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
      <div className="nb-radar-cards">{cards.map(([key, tone, title, hint, entries, okText]) => <button type="button" key={key} className={`nb-radar-card ${tone} ${win === key ? 'is-on' : ''} ${entries.length ? '' : 'is-zero'}`.trim()} aria-pressed={win === key} onClick={() => setWin(win === key ? 'all' : key)}>
        <span className="nb-radar-card-title">{title}</span>
        <span className="nb-radar-card-n"><b>{formatNumberLocale(entries.length)}</b><small>{entries.length ? hint : okText}</small></span>
        {entries[0] && <span className="nb-radar-card-next"><small>{t("Next")}</small><b>{entries[0].title}</b><em>{lateLabel(entries[0].days)}</em></span>}
      </button>)}</div>
      <div className="nb-radar-bar">
        <div className="apps-view" role="group" aria-label={t("Deadline type")}>{[['all', t("All types")], ['uni', t("University")], ['mine', t("Mine")]].map(([key, title]) => <button type="button" key={key} aria-pressed={type === key} onClick={() => setType(key)}>{title}</button>)}</div>
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
          <button type="button" onClick={() => item.group === 'mine' ? edit(item) : onOpen(item.application)}>
            <span className="apps-radar-date"><b>{parseDateValue(item.date).getDate()}</b><small>{formatDateLocale(item.date, { month: 'short' }).replace(/\.$/, '')}</small></span>
            <span className="apps-radar-copy"><b>{item.title}</b><small>{item.sub}</small></span>
            <span className={`due ${item.days < 0 ? 'hot' : dueTone(item.days)}`.trim()}>{lateLabel(item.days)}</span>
          </button>
        </li>)}</ul></section>) : <p className="board-empty">{items.length ? t("Nothing here") : t("No upcoming deadlines yet.")}</p>}
    </div>
  </Modal>;
}

function ApplicationCard({ application, university, essays, menuOpen, briefOpen, dragging, busy, onMenu, onBrief, onBriefClose, onDragStart, onDragEnd, onMove, onOpen, onEdit, onRemove }) {
  const stage = stageOf(application.status);
  const decided = stage === 'decision';
  const info = university || application.university_detail || {};
  const name = info.name || t("University");
  const decidedAt = historyDate(application, application.status);
  const briefId = `application-brief-${application.id}`;
  const cardRef = useRef(null);
  const briefRef = useRef(null);
  // Every set deadline counts down on the card: the last three weeks stand out, later ones stay quiet.
  const deadlines = decided || stage === 'submitted' ? [] : [['aid', application.scholarship_deadline], ['application', application.deadline]].filter(([, date]) => daysUntil(date) != null).sort(([, a], [, b]) => daysUntil(a) - daysUntil(b));

  useLayoutEffect(() => {
    const brief = briefRef.current;
    if (!briefOpen || !brief) return undefined;
    const rect = cardRef.current.getBoundingClientRect();
    const below = window.innerHeight - rect.bottom;
    const above = below < BRIEF_ROOM && rect.top > below;
    brief.dataset.side = above ? 'above' : 'below';
    brief.style.setProperty('--brief-x', `${rect.left}px`);
    brief.style.setProperty('--brief-y', `${(above ? window.innerHeight - rect.top : rect.bottom) + 8}px`);
    if (HAS_POPOVER && !brief.matches(':popover-open')) brief.showPopover();
    brief.focus({ preventScroll: true });
    return () => {if (HAS_POPOVER && brief.matches(':popover-open')) brief.hidePopover();};
  }, [briefOpen]);

  return <>
    <article ref={cardRef} className={`board-card ${dragging ? 'is-dragging' : ''} ${briefOpen ? 'is-open' : ''}`.trim()} draggable={!decided && !busy} aria-busy={busy} onDragStart={onDragStart} onDragEnd={onDragEnd} onClick={(event) => {if (!event.target.closest('.card-menu')) onBrief();}}>
      <div className="board-card-top">
        <button type="button" className="board-card-title" aria-haspopup="dialog" aria-expanded={briefOpen} aria-controls={briefOpen ? briefId : undefined}>{name}</button>
        {!decided && <span className="grip" role="img" aria-label={t("Drag to move")}><GripVertical size={14} /></span>}
        <div className="card-menu">
          <button type="button" className="icon-button" aria-expanded={menuOpen} aria-label={tx`Actions for ${name}`} onClick={onMenu}><MoreHorizontal size={16} /></button>
          {menuOpen && <div className="card-menu-list">
            {!decided && <><span className="card-menu-title">{t("Move to")}</span>{['researching', 'shortlisted', 'applying', 'submitted'].filter((status) => status !== application.status).map((status) => <button type="button" key={status} onClick={() => onMove(status)}>{label(status)}</button>)}<hr /></>}
            <button type="button" onClick={onOpen}><ArrowRight size={14} aria-hidden="true" /> {t("Open university page")}</button>
            <button type="button" onClick={onEdit}><Pencil size={14} aria-hidden="true" /> {t("Manage application")}</button>
            {!decided && <button type="button" className="danger" onClick={onRemove}><Trash2 size={14} aria-hidden="true" /> {t("Remove from my list")}</button>}
          </div>}
        </div>
      </div>
      <p className="board-card-program">{application.program}</p>
      <p className="board-card-next"><small>{t("Next step")}</small>{t(planNextStep(application, essays))}</p>
      <TierBand value={application.tier} />
      {(decided || deadlines.length > 0) && <div className="tag-row application-card-details">
        {decided ? <DecisionTag application={application} decidedAt={decidedAt} /> : deadlines.map(([kind, date]) => <DeadlineChip key={kind} kind={kind} date={date} />)}
      </div>}
    </article>
    {briefOpen && <ApplicationBrief id={briefId} briefRef={briefRef} application={application} info={info} essays={essays} name={name} onOpen={onOpen} onEdit={onEdit} onClose={onBriefClose} />}
  </>;
}

export function ApplicationsPortalPage({ data, query, reload, notify, setPage }) {
  const [tier, setTier] = useState('all');
  const [sort, setSort] = useState('deadline');
  const [view, setView] = useState('list');
  const [pageWindow, setPageWindow] = useState({ key: '', limit: 10 });
  const [menuId, setMenuId] = useState(null);
  const [briefId, setBriefId] = useState(null);
  const [dragId, setDragId] = useState(null);
  const [overStage, setOverStage] = useState(null);
  const [moves, setMoves] = useState({});
  const [editing, setEditing] = useState(null);
  const [removingId, setRemovingId] = useState(null);
  const [radarOpen, setRadarOpen] = useState(false);
  const openUniversity = (id) => setPage('college_search', { universityId: id });
  const applications = data.applications.map((application) => moves[application.id] ? { ...application, status: moves[application.id] } : application);
  const visible = applications.filter((application) => (tier === 'all' || application.tier === tier) && matchesQuery(application, query));
  // Each application carries its university, so the board needs no catalogue.
  const nameOf = (application) => application.university_detail?.name || t("University");
  const order = sort === 'name' ? (a, b) => nameOf(a).localeCompare(nameOf(b)) : (a, b) => (a.deadline ? parseDateValue(a.deadline).getTime() : Infinity) - (b.deadline ? parseDateValue(b.deadline).getTime() : Infinity);
  // Filter/sort changes start a fresh window; summary totals still cover the whole list.
  const windowKey = JSON.stringify([tier, query, sort]);
  if (pageWindow.key !== windowKey) setPageWindow({ key: windowKey, limit: 10 });
  const limit = pageWindow.key === windowKey ? pageWindow.limit : 10;
  const shown = visible.slice().sort(order).slice(0, limit);
  const remaining = Math.min(10, visible.length - shown.length);

  useEffect(() => {
    if (menuId == null) return undefined;
    const close = (event) => {if (!event.target.closest?.('.card-menu')) setMenuId(null);};
    const escape = (event) => {if (event.key === 'Escape') {document.querySelector('.card-menu > [aria-expanded="true"]')?.focus();setMenuId(null);}};
    document.addEventListener('pointerdown', close);document.addEventListener('keydown', escape);
    return () => {document.removeEventListener('pointerdown', close);document.removeEventListener('keydown', escape);};
  }, [menuId]);

  useEffect(() => {
    if (briefId == null) return undefined;
    const close = () => setBriefId(null);
    const outside = (event) => {if (!event.target.closest?.('.app-brief, .board-card')) close();};
    const escape = (event) => {if (event.key === 'Escape') {document.querySelector('.board-card-title[aria-expanded="true"]')?.focus();close();}};
    const scrolled = (event) => {if (!event.target.closest?.('.app-brief')) close();};
    document.addEventListener('pointerdown', outside);document.addEventListener('keydown', escape);document.addEventListener('scroll', scrolled, true);window.addEventListener('resize', close);
    return () => {document.removeEventListener('pointerdown', outside);document.removeEventListener('keydown', escape);document.removeEventListener('scroll', scrolled, true);window.removeEventListener('resize', close);};
  }, [briefId]);

  async function moveTo(application, status) {
    if (!application || application.status === status) return;
    setMenuId(null);
    if (status === 'submitted') { setBriefId(null); setEditing(application); return; }
    setMoves((current) => ({ ...current, [application.id]: status }));
    try {
      await api.update('applications', application.id, { status });
      await reload();
      notify(tx`${nameOf(application)} moved to ${label(status)}.`);
    } catch (err) {notify(err.message, 'error');} finally {
      setMoves((current) => {const next = { ...current };delete next[application.id];return next;});
    }
  }

  async function removeApplication(application) {
    setMenuId(null);
    if (!window.confirm(t("Remove this university from your list?"))) return;
    setRemovingId(application.id);
    try {
      await api.remove('applications', application.id);
      await reload();
      notify(tx`${nameOf(application)} removed from your list.`);
    } catch (err) {notify(err.message, 'error');} finally {setRemovingId(null);}
  }

  const header = <PageHeader title={t('Applications')} subtitle={t('University application pipeline')} />;
  if (!data.applications.length) return <div className="section-stack student-portal nb-bridge nb-apps">{header}<EmptyState icon={Search} title={t("Your application list is empty")} text={t("Add universities from College Search and they will appear here as cards you can move through each stage.")} action={<BlueButton icon={Search} onClick={() => setPage('college_search')}>{t("Find universities")}</BlueButton>} /></div>;

  const renderCard = (application) => <ApplicationCard key={application.id} application={application} university={application.university_detail} essays={data.essays.filter((essay) => essay.application === application.id)} menuOpen={menuId === application.id} briefOpen={briefId === application.id} dragging={dragId === application.id} busy={removingId === application.id || application.id in moves}
            onMenu={() => {setBriefId(null);setMenuId(menuId === application.id ? null : application.id);}} onBrief={() => {setMenuId(null);setBriefId(briefId === application.id ? null : application.id);}} onBriefClose={() => setBriefId(null)} onDragStart={(event) => {event.dataTransfer.setData('text/plain', String(application.id));event.dataTransfer.effectAllowed = 'move';setBriefId(null);setDragId(application.id);}} onDragEnd={() => {setDragId(null);setOverStage(null);}}
            onMove={(status) => moveTo(data.applications.find((item) => item.id === application.id), status)} onOpen={() => openUniversity(application.university)} onEdit={() => {setMenuId(null);setBriefId(null);setEditing(data.applications.find((item) => item.id === application.id));}} onRemove={() => removeApplication(application)} />;
  return <div className="section-stack student-portal applications-page nb-bridge nb-apps">
    {header}
    <ApplicationSummary applications={applications} essays={data.essays} letters={data.recommendations} openApplication={setEditing} setPage={setPage} />
    <div className="board-toolbar">
      <div className="chip-row" role="group" aria-label={t("Filter by tier")}>
        <FilterChip active={tier === 'all'} onClick={() => setTier('all')}>{t("All")} <span className="chip-count">{formatNumberLocale(applications.length)}</span></FilterChip>
        {['dream', 'target', 'safety'].map((value) => <FilterChip key={value} active={tier === value} onClick={() => setTier(value)}><TierBand value={value} /> <span className="chip-count">{formatNumberLocale(applications.filter((application) => application.tier === value).length)}</span></FilterChip>)}
      </div>
      <div className="board-toolbar-actions">
        <div className="apps-view" role="group" aria-label={t("View as")}>
          <button type="button" aria-pressed={view === 'list'} onClick={() => setView('list')}><Rows3 size={15} aria-hidden="true" /> {t("List")}</button>
          <button type="button" aria-pressed={view === 'board'} onClick={() => setView('board')}><Columns3 size={15} aria-hidden="true" /> {t("Board")}</button>
        </div>
        <label className="sort-control application-sort"><ArrowDownWideNarrow size={15} aria-hidden="true" /><span className="sr-only">{t("Sort by")}</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option value="deadline">{t("Deadline")}</option><option value="name">{t("University")}</option></select></label>
        <button type="button" className="button quiet apps-radar-button" onClick={() => setRadarOpen(true)}><Radar size={16} aria-hidden="true" /> {t("Deadline radar")}</button>
        <button type="button" className="button primary" onClick={() => setPage('college_search')}><Plus size={16} aria-hidden="true" /> {t("Add university")}</button>
      </div>
    </div>
    {view === 'list' && <div className="apps-list">{shown.map((application) => <div className="apps-row" key={application.id}><StageStepper status={application.status} />{renderCard(application)}</div>)}{!shown.length && <p className="board-empty">{t("Nothing here yet.")}</p>}</div>}
    {view === 'board' && <div className="board">{APPLICATION_STAGES.map((stage) => {
        const stageCards = visible.filter((application) => stageOf(application.status) === stage.key);
        const cards = shown.filter((application) => stageOf(application.status) === stage.key);
        return <section key={stage.key} className={`board-column ${overStage === stage.key ? 'is-over' : ''}`.trim()} aria-label={t(stage.title)}
        onDragOver={(event) => {if (dragId != null && !stage.locked) {event.preventDefault();setOverStage(stage.key);}}}
        onDragLeave={(event) => {if (!event.currentTarget.contains(event.relatedTarget)) setOverStage(null);}}
        onDrop={(event) => {
          event.preventDefault();
          const record = data.applications.find((item) => item.id === dragId);
          setDragId(null);setOverStage(null);
          if (record && !stage.locked) moveTo(record, stage.key);
        }}>
          <header><div><h3>{t(stage.title)}</h3><span className="count-pill neutral">{formatNumberLocale(stageCards.length)}</span>{stage.locked && <span className="board-lock" role="img" aria-label={t("Set by your counselor")}><Lock size={14} /></span>}</div><p>{t(stage.description)}</p></header>
          <div className="board-stack">
            {cards.map(renderCard)}
            {!stageCards.length && <p className="board-empty">{stage.locked ? t("No decisions yet.") : t("Nothing here yet.")}</p>}
          </div>
        </section>;
      })}</div>}
    <div className="paged-list-footer">
      <span role="status" aria-live="polite">{tx`${formatNumberLocale(shown.length)} shown`}</span>
      {remaining > 0 && <button type="button" className="button quiet" onClick={() => setPageWindow({ key: windowKey, limit: limit + 10 })}>{t('Show {n} more', { n: formatNumberLocale(remaining) })}</button>}
    </div>
    {radarOpen && <DeadlineRadar applications={applications} onOpen={(application) => { setRadarOpen(false); setEditing(data.applications.find((item) => item.id === application.id)); }} onClose={() => setRadarOpen(false)} />}
    {editing && <ApplicationPlan key={editing.id} application={editing} data={data} setPage={setPage} onClose={() => setEditing(null)} onSaved={reload} notify={notify} />}
  </div>;
}
