import { useEffect, useId, useRef, useState } from 'react';
import {
  ArrowRight, CalendarDays, Check, ChevronDown, ChevronUp, CircleAlert, ClipboardCheck, Eye, EyeOff,
  GraduationCap, ListChecks, MessageSquare, RefreshCw, Star, UserRound, UsersRound,
} from 'lucide-react';
import { api } from '../api';
import { formatDateLocale, formatNumberLocale, formatPercentLocale, t, tp, tx } from '../i18n';
import { clockText, dateText, dayMonthText, joinParts } from '../lib/format';
import { REVIEW_SOURCE } from '../lib/reviewQueue';
import { inServerZone, serverRelativeDayText } from '../lib/serverTime';
import { bucketShares, checkInAction, checkedDays, heatmapWeeks, homeReasons, todayMeetingsState } from '../lib/counselorHome';
import { fullName } from '../lib/labels';
import { isExpiredMeeting } from '../lib/meetings';
import { CxAvatar, CxProgress, CxTag, reasonText } from './counselorUi';
import { Modal } from './ui';

// Home's today and week are the server's (Asia/Tashkent), so every time here
// is shown in that zone too (lib/serverTime).

const firstName = (name) => String(name || '').trim().split(/\s+/)[0];

export function HomeCard({ icon: Icon, title, hint, className = '', children, footer }) {
  return <section className={`cx-card ch-card ${className}`.trim()}>
    <header className="ch-card-head">
      <h2>{Icon && <Icon size={15} aria-hidden="true" />}{title}</h2>
      {hint && <small>{hint}</small>}
    </header>
    <div className="ch-card-body">{children}</div>
    {footer && <footer className="ch-card-foot">{footer}</footer>}
  </section>;
}

// A number and its unit are separate words: screen readers and copied text
// read "10 · 8 documents", never "108 documents".
function StatNumber({ value, unit, hot }) {
  return <strong className={`ch-stat-number${hot ? ' hot' : ''}`}>
    <span>{formatNumberLocale(value)}</span>{unit && <>{' '}<span className="ch-stat-unit">{unit}</span></>}
  </strong>;
}

const TODAY_LINE = {
  none: () => t("No meetings today"),
  next: ({ meeting }) => t('Next at {time} · {name}', { time: clockText(inServerZone(meeting.starts_at)), name: firstName(meeting.student_name) }),
  started: () => t("All of today's meetings have started"),
  done: () => t("All of today's meetings are done"),
};

// `meetings`: today's approved and completed meetings; `requests`: every
// request waiting for the counselor, any day (the sidebar's Meetings badge).
export function StatCards({ review, breakdown, needYou, meetings, requests = 0, messages, setPage }) {
  const today = todayMeetingsState(meetings);
  return <div className="ch-stats">
    <button type="button" className="ch-stat primary" onClick={() => setPage('review')}>
      <span className="ch-eyebrow"><ClipboardCheck size={14} aria-hidden="true" />{t("To review")}</span>
      <StatNumber value={review.total} />
      <small>{breakdown || t("Nothing waiting right now")}</small>
      <em>{t("Start reviewing")} <ArrowRight size={15} aria-hidden="true" /></em>
    </button>
    <button type="button" className="ch-stat" onClick={() => setPage('students')}>
      <span className="ch-eyebrow"><CircleAlert size={14} aria-hidden="true" />{t("Students who need you")}</span>
      <StatNumber value={needYou} hot={needYou > 0} />
      <small>{t("Late work or missing documents")}</small>
    </button>
    <button type="button" className="ch-stat" onClick={() => setPage('bookings')}>
      <span className="ch-eyebrow"><CalendarDays size={14} aria-hidden="true" />{t("Today")}</span>
      <StatNumber value={meetings.length} unit={tp('meeting|meetings', meetings.length)} />
      <small>{joinParts(TODAY_LINE[today.state](today), requests > 0 && tp('{n} request waiting|{n} requests waiting', requests, { n: requests }))}</small>
    </button>
    <button type="button" className="ch-stat" onClick={() => setPage('messages')}>
      <span className="ch-eyebrow"><MessageSquare size={14} aria-hidden="true" />{t("Messages")}</span>
      <StatNumber value={messages.unread} unit={t("unread")} />
      <small>{messages.students ? tp('From {n} student|From {n} students', messages.students, { n: messages.students }) : messages.unread ? t("In group chats") : t("You're all caught up")}</small>
    </button>
  </div>;
}

export function ReviewCard({ items, total, onOpen }) {
  return <HomeCard icon={ClipboardCheck} title={t("Needs your review")} hint={t("oldest first")} className="ch-review"
    footer={total > items.length && <button type="button" className="cx-link" onClick={() => onOpen(null)}>{tp('See all {n} in Review|See all {n} in Review', total, { n: total })} <ArrowRight size={14} aria-hidden="true" /></button>}>
    {items.length ? <div className="ch-list">
      {items.map((item) => <button type="button" key={item.id} className="ch-row" onClick={() => onOpen(item)}>
        <CxAvatar name={item.student_name} />
        <span className="ch-row-copy">
          <b>{item.title}</b>
          <small>{joinParts(item.student_name, t(REVIEW_SOURCE[item.kind]?.when || 'submitted {when}', { when: serverRelativeDayText(item.at).toLowerCase() }))}</small>
        </span>
        <CxTag tone={item.kind} small>{t(REVIEW_SOURCE[item.kind]?.label || 'Task')}</CxTag>
      </button>)}
    </div> : <p className="ch-empty">{t("Nothing is waiting for your review.")}</p>}
  </HomeCard>;
}

export function NeedYouCard({ needYou, onOpen }) {
  const { students, total } = needYou;
  return <HomeCard icon={CircleAlert} title={t("Students who need you")} hint={total > students.length ? tp('{n} student|{n} students', total, { n: total }) : null} className="ch-need"
    footer={total > students.length && <button type="button" className="cx-link" onClick={() => onOpen(null)}>{t("View all")} <ArrowRight size={14} aria-hidden="true" /></button>}>
    {students.length ? <div className="ch-list">
      {students.map((student) => <button type="button" key={student.id} className="ch-row" onClick={() => onOpen(student.id)}>
        <CxAvatar name={student.name} />
        <span className="ch-row-copy">
          <b>{student.name}</b>
          <span className="ch-reasons">{homeReasons(student.reasons).map((reason) => <span key={reason.key}>{reasonText(reason)}</span>)}</span>
        </span>
      </button>)}
    </div> : <p className="ch-empty">{t("Nobody needs you right now.")}</p>}
  </HomeCard>;
}

export function TodayCard({ week, today, meetings, onOpenMeeting, onNotes }) {
  const { days } = meetings;
  const todays = meetings.today.filter((meeting) => !isExpiredMeeting(meeting));
  return <HomeCard icon={CalendarDays} title={t("Today")} className="ch-today">
    <ol className="ch-week" aria-label={t("This week")}>
      {week.map((day) => {
        const count = days[day] || 0;
        const isToday = day === today;
        return <li key={day} className={`${isToday ? 'today' : ''}${count ? ' busy' : ''}`.trim()}>
          <span>{isToday ? t("Today") : formatDateLocale(day, { weekday: 'short' })}</span>
          <b aria-label={joinParts(formatDateLocale(day, { weekday: 'long', day: 'numeric', month: 'long' }), count ? tp('{n} meeting|{n} meetings', count, { n: count }) : t("No meetings"))}>{formatDateLocale(day, { day: 'numeric' })}</b>
          {count > 0 && <i className="ch-week-mark" aria-hidden="true" />}
        </li>;
      })}
    </ol>
    {todays.length ? <div className="ch-list">
      {todays.map((meeting) => <div key={meeting.id} className="ch-meeting">
        <b className="ch-time">{clockText(inServerZone(meeting.starts_at))}</b>
        <button type="button" className="ch-row-copy ch-meeting-link" onClick={() => onOpenMeeting(meeting)}>
          <b>{joinParts(meeting.student_name, meeting.topic)}</b>
          <small>{meeting.status === 'pending' ? <CxTag tone="warn" small>{t("Waiting for you")}</CxTag> : joinParts(meeting.status === 'completed' ? t("Completed") : t("Confirmed"), meeting.duration_minutes > 0 && tx`${meeting.duration_minutes} min`)}</small>
        </button>
        {meeting.status !== 'pending' && <button type="button" className="cx-btn" onClick={() => onNotes(meeting)}>{t("Notes")}</button>}
      </div>)}
    </div> : <p className="ch-empty">{t("No meetings today")}</p>}
  </HomeCard>;
}

function deadlineLabel(item) {
  if (item.kind === 'application') return t('{name} application', { name: item.title });
  if (item.kind === 'letter') return t('Recommendation letter');
  return item.title;
}

export function DeadlinesCard({ deadlines, onOpenStudents }) {
  const { items, total, overdue } = deadlines;
  return <HomeCard icon={ListChecks} title={t("Deadlines this week")} className="ch-deadlines"
    footer={(overdue > 0 || total > items.length) && <>
      {overdue > 0 && <span className="ch-overdue">{tp('{n} older item still overdue|{n} older items still overdue', overdue, { n: overdue })}</span>}
      {total > items.length && <span>{tp('{n} more this week|{n} more this week', total - items.length, { n: total - items.length })}</span>}
      <button type="button" className="cx-link" onClick={onOpenStudents}>{t("Open Students")} <ArrowRight size={14} aria-hidden="true" /></button>
    </>}>
    {items.length ? <div className="ch-list">
      {items.map((item) => <div key={item.id} className="ch-deadline">
        <span className="ch-row-copy">
          <b>{joinParts(deadlineLabel(item), firstName(item.student_name))}</b>
          {item.due && <small>{dateText(inServerZone(item.due))}</small>}
        </span>
        {item.late && item.due ? <CxTag tone="late" small>{t("Late")}</CxTag> : item.due && <CxTag tone="quiet" small>{dayMonthText(inServerZone(item.due))}</CxTag>}
      </div>)}
    </div> : <p className="ch-empty">{t("No deadlines this week.")}</p>}
  </HomeCard>;
}

const CHECK_IN_ROWS = 8;

export function CheckInsCard({ checkIns, week, today, onToggle, pending, hasMore = false, loadingMore = false, onLoadMore, history }) {
  const [showAll, setShowAll] = useState(false);
  const { students, students_total: total, checked_in: checked } = checkIns;
  const rows = showAll ? students : students.slice(0, CHECK_IN_ROWS);
  const percent = total ? Math.round((checked / total) * 100) : 0;
  return <HomeCard icon={Check} title={t("Weekly check-ins")} className="ch-checkins"
    footer={<>
      <span className="ch-legend"><i className="auto" aria-hidden="true" />{t("From your meetings, notes, reviews, messages and new tasks")}</span>
      <span className="ch-legend"><i className="manual" aria-hidden="true" />{t("Ticked by you")}</span>
      {(students.length > CHECK_IN_ROWS || hasMore) && <button type="button" className="cx-link" onClick={() => { if (!showAll && hasMore && students.length <= CHECK_IN_ROWS) onLoadMore?.(); setShowAll(!showAll); }}>{showAll ? t("Show fewer") : tp('Show all {n} students|Show all {n} students', Math.max(total || 0, students.length), { n: Math.max(total || 0, students.length) })}</button>}
      {showAll && hasMore && <button type="button" className="cx-link" onClick={onLoadMore} disabled={loadingMore} aria-busy={loadingMore}>{loadingMore ? t("Loading…") : t("Load more")}</button>}
    </>}>
    <p className="ch-note">{t("Tap a day when you met or reviewed a student. Days with your meetings, notes, reviews, messages or new tasks fill in on their own.")}</p>
    <p className="ch-checkins-total">{tp('Checked in with {n} of {total} student this week|Checked in with {n} of {total} students this week', total, { n: checked, total })}</p>
    <CxProgress value={percent} label={t("Students checked in this week")} />
    {students.length ? <div className="ch-grid" role="table" aria-label={t("Weekly check-ins")}>
      <div className="ch-grid-row ch-grid-head" role="row">
        <span role="columnheader" className="ch-grid-name">{t("Student")}</span>
        {week.map((day) => <span key={day} role="columnheader" className={day === today ? 'today' : ''}>
          <small>{formatDateLocale(day, { weekday: 'narrow' })}</small>
          <b>{formatDateLocale(day, { day: 'numeric' })}</b>
        </span>)}
        <span role="columnheader" className="ch-grid-count"><span className="sr-only">{t("Days")}</span></span>
      </div>
      {rows.map((row) => <div key={row.student} className="ch-grid-row" role="row">
        <span role="rowheader" className="ch-grid-name"><CxAvatar name={row.name} /><b>{firstName(row.name)}</b></span>
        {row.days.map((state, index) => {
          const day = week[index];
          const action = checkInAction(state, day, today);
          const busy = Boolean(pending?.has?.(`${row.student}:${day}`));
          const dayName = formatDateLocale(day, { weekday: 'long', day: 'numeric', month: 'long' });
          const description = state === 'auto' ? t("Checked in (from your activity)") : state === 'manual' ? t("Checked in (ticked by you)") : day > today ? t("Not yet") : t("No check-in");
          return <span key={day} role="cell">
            <button type="button" className={`ch-dot${state ? ` ${state}` : ''}${day === today ? ' today' : ''}`}
              disabled={!action || busy} aria-pressed={action ? state === 'manual' : undefined}
              aria-label={`${row.name}, ${dayName}: ${description}`} title={description}
              onClick={() => onToggle(row.student, index, action === 'on')}>
              {state && <Check size={14} aria-hidden="true" />}
            </button>
          </span>;
        })}
        <span role="cell" className="ch-grid-count">{`${checkedDays(row)}/7`}</span>
      </div>)}
    </div> : <p className="ch-empty">{t("No students assigned to you yet.")}</p>}
    {history && students.length > 0 && <CheckInHeatmap history={history} />}
  </HomeCard>;
}

export function CheckInHeatmap({ history }) {
  const weeks = heatmapWeeks(history);
  if (!weeks.length) return null;
  const active = weeks.flat().filter((cell) => cell.count > 0).length;
  const cellText = (cell) => `${formatDateLocale(cell.day, { weekday: 'long', day: 'numeric', month: 'long' })}: ${cell.future ? t("Not yet") : tp('{n} student|{n} students', cell.count, { n: cell.count })}`;
  return <section className="ch-heat" aria-label={t("Last 12 weeks")}>
    <div className="ch-heat-head">
      <h3>{t("Last 12 weeks")}</h3>
      <span className="ch-heat-legend" aria-hidden="true">{t("Fewer students")}{[0, 1, 2, 3, 4].map((level) => <i key={level} className={`ch-hm l${level}`} />)}{t("More students")}</span>
    </div>
    <div className="ch-heat-grid" role="img" aria-label={tp('Checked in on {n} day in the last 12 weeks|Checked in on {n} days in the last 12 weeks', active, { n: active })}>
      {weeks.flat().map((cell) => <i key={cell.day} className={`ch-hm l${cell.level}${cell.future ? ' future' : ''}${cell.today ? ' now' : ''}`} title={cellText(cell)} />)}
    </div>
  </section>;
}

const BUCKETS = [
  ['on_track', 'On track'],
  ['behind', 'Behind'],
  ['needs_attention', 'Needs attention'],
];

export function ProgressCard({ progress, onOpen, onViewAll }) {
  const { buckets, students, total } = progress;
  const shares = bucketShares(buckets);
  return <HomeCard icon={UsersRound} title={t("Student progress")} hint={t("Roadmap completion")} className="ch-progress"
    footer={<button type="button" className="cx-btn" onClick={onViewAll}>{tp('View all {n} student|View all {n} students', total, { n: total })}</button>}>
    {total ? <>
      <div className="ch-stack" role="img" aria-label={BUCKETS.map(([key, title]) => `${t(title)}: ${formatNumberLocale(buckets[key])}`).join(', ')}>
        {BUCKETS.map(([key]) => shares[key] > 0 && <span key={key} className={key} style={{ width: `${shares[key]}%` }} />)}
      </div>
      <div className="ch-buckets">
        {BUCKETS.map(([key, title]) => <span key={key} className={`ch-bucket ${key}`}><i aria-hidden="true" />{t(title)} <b>{formatNumberLocale(buckets[key])}</b></span>)}
      </div>
      <p className="ch-list-label">{t("Lowest progress")}</p>
      <div className="ch-list">
        {students.map((student) => <button type="button" key={student.id} className="ch-row ch-progress-row" onClick={() => onOpen(student.id)}>
          <CxAvatar name={student.name} />
          <span className="ch-row-copy">
            <b>{student.name}</b>
            <span className={`ch-bar ${student.bucket}`}><CxProgress value={student.completion} label={t("Roadmap completion")} /><small>{formatPercentLocale(student.completion)}</small></span>
          </span>
          {student.late > 0 && <span className="ch-late" title={tp('{n} late item|{n} late items', student.late, { n: student.late })}>{tp('{n} late|{n} late', student.late, { n: formatNumberLocale(student.late) })}</span>}
        </button>)}
      </div>
    </> : <p className="ch-empty">{t("No students assigned to you yet.")}</p>}
  </HomeCard>;
}

const CARD_TITLES = {
  stats: 'Summary cards',
  snapshot: 'Student snapshot',
  review: 'Needs your review',
  need_you: 'Students who need you',
  today: 'Today',
  deadlines: 'Deadlines this week',
  check_ins: 'Weekly check-ins',
  progress: 'Student progress',
};

export function CustomizeHome({ layout, onToggle, onMove, onReset, onClose }) {
  return <Modal title={t("Customize Home")} onClose={onClose} className="ch-customize">
    <p className="ch-note">{t("Choose the cards Home shows and their order. This is saved on this device.")}</p>
    <h3 className="ch-customize-title">{t("Show on Home")}</h3>
    <ol className="ch-customize-list">
      {layout.order.map((id, index) => {
        const shown = !layout.hidden.includes(id);
        const title = t(CARD_TITLES[id]);
        return <li key={id} className={shown ? '' : 'off'}>
          <button type="button" className="cx-btn ch-icon-btn" aria-pressed={shown} onClick={() => onToggle(id)} aria-label={shown ? t('Hide {card}', { card: title }) : t('Show {card}', { card: title })}>
            {shown ? <Eye size={16} aria-hidden="true" /> : <EyeOff size={16} aria-hidden="true" />}
          </button>
          <span>{title}</span>
          <button type="button" className="cx-btn ch-icon-btn" disabled={index === 0} onClick={() => onMove(id, -1)} aria-label={t('Move {card} up', { card: title })}><ChevronUp size={16} aria-hidden="true" /></button>
          <button type="button" className="cx-btn ch-icon-btn" disabled={index === layout.order.length - 1} onClick={() => onMove(id, 1)} aria-label={t('Move {card} down', { card: title })}><ChevronDown size={16} aria-hidden="true" /></button>
        </li>;
      })}
    </ol>
    <div className="ch-customize-actions">
      <button type="button" className="cx-btn" onClick={onReset}>{t("Reset to default")}</button>
      <button type="button" className="cx-btn primary" onClick={onClose}>{t("Done")}</button>
    </div>
  </Modal>;
}

export function HomeSkeleton() {
  return <div className="ch-skeleton" role="status" aria-label={t("Loading your Home")}>
    <div className="ch-stats">{[0, 1, 2, 3].map((index) => <span key={index} className="ch-skeleton-block tall" />)}</div>
    <div className="ch-grid-cards">{[0, 1, 2, 3].map((index) => <span key={index} className="ch-skeleton-block" />)}</div>
  </div>;
}

export function HomeError({ message, onRetry }) {
  return <section className="cx-card ch-error" role="alert">
    <CircleAlert size={22} aria-hidden="true" />
    <div><b>{t("Home could not load.")}</b><p>{message || t("Check your connection and try again.")}</p></div>
    <button type="button" className="cx-btn" onClick={onRetry}><RefreshCw size={15} aria-hidden="true" /> {t("Retry")}</button>
  </section>;
}

export function AllSetOverlay({ onClose }) {
  const titleId = useId();
  const button = useRef(null);
  const close = useRef(onClose);
  useEffect(() => { close.current = onClose; }, [onClose]);
  useEffect(() => {
    button.current?.focus();
    const onKey = (event) => { if (event.key === 'Escape') close.current(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  return <div className="ch-allset-backdrop" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="ch-allset" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <span className="ch-allset-pill">{t("All done")}<i aria-hidden="true" /></span>
      <h2 id={titleId}>{t("You’re all set!")}</h2>
      <p>{t("Nothing is waiting for you. Great work today.")}</p>
      <div className="ch-allset-scene" aria-hidden="true">
        <span className="ch-allset-ring r1" /><span className="ch-allset-ring r2" /><span className="ch-allset-ring r3" />
        <span className="ch-allset-check"><Check size={40} strokeWidth={2.5} /></span>
        {[0, 1, 2, 3, 4, 5].map((index) => <i key={index} className={`ch-allset-spark s${index}`} />)}
      </div>
      <button type="button" ref={button} className="cx-btn primary lg" onClick={onClose}>{t("Back to dashboard")}</button>
    </div>
  </div>;
}

function SnapshotNumber({ value, label }) {
  return <div><b>{formatNumberLocale(value)}</b><span>{label}</span></div>;
}

function SnapshotPicker({ choices, selected, onSelect }) {
  const inputId = useId();
  const listId = useId();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [found, setFound] = useState({ term: '', items: [], error: '' });
  const term = query.trim();
  useEffect(() => {
    if (!term) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api.page('students', `?${new URLSearchParams({ search: term, page_size: '20' })}`, controller.signal)
        .then((data) => setFound({ term, items: (data?.results || []).map((student) => ({ id: student.id, name: fullName(student.user_detail) })), error: '' }))
        .catch((err) => { if (err?.name !== 'AbortError') setFound({ term, items: [], error: err?.message || t("Check your connection and try again.") }); });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [term]);
  const searching = Boolean(term) && found.term !== term;
  const options = term ? (searching ? [] : found.items) : choices;
  const pick = (choice) => {
    onSelect(choice);
    setQuery('');
    setOpen(false);
  };
  function onKeyDown(event) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setOpen(true);
      if (options.length) setActive((index) => (index + (event.key === 'ArrowDown' ? 1 : options.length - 1)) % options.length);
    } else if (event.key === 'Enter' && open && options[active]) {
      event.preventDefault();
      pick(options[active]);
    } else if (event.key === 'Escape' && open) {
      event.preventDefault();
      setQuery('');
      setOpen(false);
    }
  }
  const optionId = (index) => `${listId}-${index}`;
  return <div className="ch-snap-picker">
    <label className="sr-only" htmlFor={inputId}>{t("Student")}</label>
    <input id={inputId} className="ch-snap-select" type="search" role="combobox" autoComplete="off"
      aria-expanded={open} aria-controls={listId} aria-autocomplete="list"
      aria-activedescendant={open && options[active] ? optionId(active) : undefined}
      placeholder={selected?.name || t("Search students")} value={open ? query : selected?.name || ''}
      onFocus={(event) => { setOpen(true); setActive(0); event.target.select(); }}
      onBlur={() => { setOpen(false); setQuery(''); }}
      onChange={(event) => { setQuery(event.target.value); setActive(0); setOpen(true); }}
      onKeyDown={onKeyDown} />
    {open && <ul id={listId} className="ch-snap-options" role="listbox" aria-label={t("Students")}>
      {options.map((choice, index) => <li key={choice.id} id={optionId(index)} role="option" aria-selected={index === active}
        className={`${index === active ? 'is-active' : ''}${choice.id === selected?.id ? ' is-current' : ''}`}
        onMouseDown={(event) => event.preventDefault()} onClick={() => pick(choice)}>{choice.name}</li>)}
      {term && (searching ? <li className="ch-snap-note" role="status">{t("Searching…")}</li>
        : found.error ? <li className="ch-snap-note" role="alert">{found.error}</li>
          : !options.length && <li className="ch-snap-note">{t("No students found.")}</li>)}
    </ul>}
  </div>;
}

export function SnapshotCard({ choices, selected, onSelect, state, onOpenStudent, onRetry }) {
  const data = state.data;
  const name = data?.name || selected?.name || '';
  const missions = data?.roadmap;
  const segments = missions && missions.total > 0 && missions.total <= 12 ? Array.from({ length: missions.total }, (_, index) => index < missions.approved) : null;
  return <HomeCard icon={UserRound} title={t("Student snapshot")} className="ch-snapshot"
    footer={selected && <button type="button" className="cx-btn" onClick={() => onOpenStudent(selected.id)}>{t("Open student")} <ArrowRight size={14} aria-hidden="true" /></button>}>
    {choices.length || selected ? <>
      <div className="ch-snap-top">
        <CxAvatar name={name} />
        <span className="ch-snap-who">
          <SnapshotPicker choices={choices} selected={selected} onSelect={onSelect} />
          {name && <span className="ch-snap-pill"><Eye size={13} aria-hidden="true" />{t('As {name} sees it', { name: firstName(name) })}</span>}
        </span>
      </div>
      {state.error ? <div className="ch-snap-error" role="alert"><p>{state.error}</p><button type="button" className="cx-btn" onClick={onRetry}><RefreshCw size={14} aria-hidden="true" /> {t("Retry")}</button></div>
        : !data ? <div className="ch-snap-loading" role="status" aria-label={t("Loading…")}><span className="ch-skeleton-block" /><span className="ch-skeleton-block" /></div>
          : <div className={`ch-snap-body${state.loading ? ' is-loading' : ''}`} aria-busy={state.loading || undefined}>
            <div className="ch-snap-goal">
              {data.study_goal && <><span className="ch-snap-k">{t("Study goal")}</span><b><GraduationCap size={18} aria-hidden="true" />{data.study_goal}</b></>}
              {data.target_countries && <span className="ch-snap-countries">{data.target_countries.map((country) => t(country)).join(', ')}</span>}
              <span className="ch-snap-level"><Star size={13} aria-hidden="true" />{tx`Level ${data.level}`}<span aria-hidden="true">·</span>{tp('{n} star|{n} stars', data.stars, { n: data.stars })}</span>
            </div>
            {missions && <div className="ch-snap-road">
              <span className="ch-snap-k">{t("Roadmap")}</span>
              <div className="ch-snap-road-row"><b>{formatPercentLocale(missions.percent)}</b><small>{missions.total ? `${formatNumberLocale(missions.approved)}/${formatNumberLocale(missions.total)} ${t("Missions approved")}` : t("No roadmap missions assigned yet.")}</small></div>
              {segments ? <div className="ch-snap-segs" aria-hidden="true">{segments.map((done, index) => <i key={index} className={done ? 'on' : ''} />)}</div>
                : missions.total > 0 && <CxProgress value={missions.percent} label={t("Roadmap progress")} />}
            </div>}
            <span className="ch-snap-k">{t("Applications")}</span>
            <div className="ch-snap-apps">
              <SnapshotNumber value={data.applications.total} label={t("Universities on list")} />
              <SnapshotNumber value={data.applications.submitted} label={t("Submitted")} />
              <SnapshotNumber value={data.applications.accepted} label={t("Accepted")} />
              <SnapshotNumber value={data.achievements} label={t("Achievements")} />
            </div>
            <div className="ch-snap-prio-head"><span className="ch-snap-k">{t("Next priorities")}</span><small>{tp('{n} open task|{n} open tasks', data.open_tasks, { n: data.open_tasks })}</small></div>
            {data.priorities.length ? <ol className="ch-snap-prio">
              {data.priorities.map((task, index) => <li key={task.id}>
                <i>{String(index + 1).padStart(2, '0')}</i>
                <span><b>{task.title}</b><small>{task.due ? (task.late ? <CxTag tone="late" small>{t("Late")}</CxTag> : dateText(inServerZone(task.due))) : t("No deadline")}</small></span>
              </li>)}
            </ol> : <p className="ch-empty">{t("All tasks are complete.")}</p>}
          </div>}
    </> : <p className="ch-empty">{t("No students assigned to you yet.")}</p>}
  </HomeCard>;
}
