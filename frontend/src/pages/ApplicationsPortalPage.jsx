import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ArrowDownWideNarrow, ArrowRight, CalendarDays, Check, CheckCircle2, Clock3, GripVertical, Hourglass, Link2, Lock, MapPin, MoreHorizontal, Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { api } from '../api';
import { formatNumberLocale, parseDateValue, t, tx } from '../i18n';
import { FilterChip } from '../components/forms';
import { DeadlineChip, TierBand } from '../components/college';
import { money } from '../lib/format';
import { label } from '../lib/labels';
import { matchesQuery } from '../lib/searchIndex';
import { APPLICATION_STAGES, daysUntil, dueLabel, dueTone, historyDate, longDate, nextDeadline, percentText, satText, scalePercent, shortDate, stageOf } from '../lib/college';
import { ResourceForm } from './ResourceSection';

function ApplicationSummary({ applications, essays, letters, openUniversity }) {
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
        <button type="button" className="button quiet small" onClick={() => openUniversity(next.application.university)}>{t("Open university page")} <ArrowRight size={14} aria-hidden="true" /></button>
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
  const place = [[...new Set([info.city, info.country].filter(Boolean))].join(', '), info.institution_type && label(info.institution_type)].filter(Boolean).join(' · ');
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
      <div><dt>{t("SAT")}</dt><dd>{info.sat_min ? satText(info.sat_min, info.sat_max) : t("Optional")}</dd></div>
      <div><dt>{t("Net price")}</dt><dd>{money(info.net_price_usd)}</dd></div>
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
      <button type="button" className="button primary small" onClick={onOpen}>{t("Open university page")} <ArrowRight size={14} aria-hidden="true" /></button>
      {!decided && <button type="button" className="button quiet small" onClick={onEdit}><Pencil size={14} aria-hidden="true" /> {t("Edit details")}</button>}
    </footer>
  </div>;
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
  // Only deadlines inside three weeks stay on the card; the rest wait in the brief.
  const urgent = decided || stage === 'submitted' ? [] : [['aid', application.scholarship_deadline], ['application', application.deadline]].filter(([, date]) => {
    const days = daysUntil(date);
    return days != null && days <= 21;
  }).sort(([, a], [, b]) => daysUntil(a) - daysUntil(b));

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
            {!decided && <button type="button" onClick={onEdit}><Pencil size={14} aria-hidden="true" /> {t("Edit details")}</button>}
            {!decided && <button type="button" className="danger" onClick={onRemove}><Trash2 size={14} aria-hidden="true" /> {t("Remove from my list")}</button>}
          </div>}
        </div>
      </div>
      <p className="board-card-program">{application.program}</p>
      <TierBand value={application.tier} />
      {(decided || urgent.length > 0) && <div className="tag-row application-card-details">
        {decided ? <DecisionTag application={application} decidedAt={decidedAt} /> : urgent.map(([kind, date]) => <DeadlineChip key={kind} kind={kind} date={date} />)}
      </div>}
    </article>
    {briefOpen && <ApplicationBrief id={briefId} briefRef={briefRef} application={application} info={info} essays={essays} name={name} onOpen={onOpen} onEdit={onEdit} onClose={onBriefClose} />}
  </>;
}

export function ApplicationsPortalPage({ user, data, query, reload, notify, setPage }) {
  const [tier, setTier] = useState('all');
  const [sort, setSort] = useState('deadline');
  const [menuId, setMenuId] = useState(null);
  const [briefId, setBriefId] = useState(null);
  const [dragId, setDragId] = useState(null);
  const [overStage, setOverStage] = useState(null);
  const [moves, setMoves] = useState({});
  const [editing, setEditing] = useState(null);
  const [removingId, setRemovingId] = useState(null);
  const openUniversity = (id) => setPage('college_search', { universityId: id });
  const universities = useMemo(() => new Map(data.universities.map((item) => [item.id, item])), [data.universities]);
  const applications = data.applications.map((application) => moves[application.id] ? { ...application, status: moves[application.id] } : application);
  const visible = applications.filter((application) => (tier === 'all' || application.tier === tier) && matchesQuery(application, query));
  const nameOf = (application) => universities.get(application.university)?.name || application.university_detail?.name || t("University");
  const order = sort === 'name' ? (a, b) => nameOf(a).localeCompare(nameOf(b)) : (a, b) => (a.deadline ? parseDateValue(a.deadline).getTime() : Infinity) - (b.deadline ? parseDateValue(b.deadline).getTime() : Infinity);

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

  if (!data.applications.length) return <div className="section-stack student-portal"><section className="info-card applications-empty"><h3>{t("Your application list is empty")}</h3><p className="note">{t("Add universities from College Search and they will appear here as cards you can move through each stage.")}</p><button type="button" className="button primary" onClick={() => setPage('college_search')}><Search size={16} aria-hidden="true" /> {t("Find universities")}</button></section></div>;

  return <div className="section-stack student-portal applications-page">
    <ApplicationSummary applications={applications} essays={data.essays} letters={data.recommendations} openUniversity={openUniversity} />
    <div className="board-toolbar">
      <div className="chip-row" role="group" aria-label={t("Filter by tier")}>
        <FilterChip active={tier === 'all'} onClick={() => setTier('all')}>{t("All")} <span className="chip-count">{formatNumberLocale(applications.length)}</span></FilterChip>
        {['dream', 'target', 'safety'].map((value) => <FilterChip key={value} active={tier === value} onClick={() => setTier(value)}><TierBand value={value} /> <span className="chip-count">{formatNumberLocale(applications.filter((application) => application.tier === value).length)}</span></FilterChip>)}
      </div>
      <div className="board-toolbar-actions">
        <label className="sort-control application-sort"><ArrowDownWideNarrow size={15} aria-hidden="true" /><span className="sr-only">{t("Sort by")}</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option value="deadline">{t("Deadline")}</option><option value="name">{t("University")}</option></select></label>
        <button type="button" className="button primary" onClick={() => setPage('college_search')}><Plus size={16} aria-hidden="true" /> {t("Add university")}</button>
      </div>
    </div>
    <div className="board">{APPLICATION_STAGES.map((stage) => {
        const cards = visible.filter((application) => stageOf(application.status) === stage.key).sort(order);
        return <section key={stage.key} className={`board-column ${overStage === stage.key ? 'is-over' : ''}`.trim()} aria-label={t(stage.title)}
        onDragOver={(event) => {if (dragId != null && !stage.locked) {event.preventDefault();setOverStage(stage.key);}}}
        onDragLeave={(event) => {if (!event.currentTarget.contains(event.relatedTarget)) setOverStage(null);}}
        onDrop={(event) => {
          event.preventDefault();
          const record = data.applications.find((item) => item.id === dragId);
          setDragId(null);setOverStage(null);
          if (record && !stage.locked) moveTo(record, stage.key);
        }}>
          <header><div><h3>{t(stage.title)}</h3><span className="count-pill neutral">{formatNumberLocale(cards.length)}</span>{stage.locked && <span className="board-lock" role="img" aria-label={t("Set by your counselor")}><Lock size={14} /></span>}</div><p>{t(stage.description)}</p></header>
          <div className="board-stack">
            {cards.map((application) => <ApplicationCard key={application.id} application={application} university={universities.get(application.university)} essays={data.essays.filter((essay) => essay.application === application.id)} menuOpen={menuId === application.id} briefOpen={briefId === application.id} dragging={dragId === application.id} busy={removingId === application.id || application.id in moves}
            onMenu={() => {setBriefId(null);setMenuId(menuId === application.id ? null : application.id);}} onBrief={() => {setMenuId(null);setBriefId(briefId === application.id ? null : application.id);}} onBriefClose={() => setBriefId(null)} onDragStart={(event) => {event.dataTransfer.setData('text/plain', String(application.id));event.dataTransfer.effectAllowed = 'move';setBriefId(null);setDragId(application.id);}} onDragEnd={() => {setDragId(null);setOverStage(null);}}
            onMove={(status) => moveTo(data.applications.find((item) => item.id === application.id), status)} onOpen={() => openUniversity(application.university)} onEdit={() => {setMenuId(null);setBriefId(null);setEditing(data.applications.find((item) => item.id === application.id));}} onRemove={() => removeApplication(application)} />)}
            {!cards.length && <p className="board-empty">{stage.locked ? t("No decisions yet.") : t("Nothing here yet.")}</p>}
          </div>
        </section>;
      })}</div>
    {editing && <ResourceForm resource="applications" item={editing} data={data} user={user} onClose={() => setEditing(null)} onSaved={() => {setEditing(null);reload();}} notify={notify} />}
  </div>;
}
