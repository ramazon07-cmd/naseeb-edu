import { useState, useEffect, useMemo, useRef } from 'react';
import { api, request } from '../api';
import { t, tx, tp, locale, formatDateLocale } from '../i18n';
import { Modal, Badge, Empty, Panel } from '../components/ui';
import { Field, PortalTabs } from '../components/forms';
import { fullName, label } from '../lib/labels';
import { Record } from '../components/records';
import { Plus, Clock3, Check, X, CheckCircle2, CalendarClock, Calendar, CalendarDays, Ban, ArrowLeft, ChevronLeft, ChevronRight, Globe, Trash2, Pencil, Send, Eye, Link2, Timer, History, UsersRound, MessageCircle } from 'lucide-react';
import { clockText as viewerClockText, dateTimeText as viewerDateTimeText, joinParts, relativeDayText, shortDayText } from '../lib/format';
import { inServerZone } from '../lib/serverTime';
import { usesCounselorLayout } from '../lib/roles';
import { CxAvatar, CxCard, CxHead, CxTag } from '../components/counselorUi';
import { isAwaitingStudent, isOpenMeeting, meetingStatus, meetingBadgeStatus, studentMeetingsForTab, pendingMeetings, meetingsThisWeek, needsRebook, cancelledByStudent, weekCounts, bookedPerDay, bookParam, bookingLink, overviewDays, ownsMeetingHours, studentProfilePath, telegramUrl } from '../lib/meetings';
import { TASHKENT_MINUTES, convertZone, shiftRange, tashkentToZone, zoneToTashkent } from '../lib/weeklyZone';
import { copyText } from '../lib/clipboard';
import { withQuery } from '../lib/routes';
import { isRangeBetween, isRangeEnd, isRangeStart, pickRangeDay, rangeText, windowFromApi, windowProblem, windowToApi } from '../lib/dateRange';
import { StudentSearchInput } from '../components/StudentSearchInput';
import './bookings-scheduler.css';
import '../design/pages/meetings-blue.css';
import { Avatar, BlueButton, Chip, DateTile, EmptyState, GlassCard, KpiRow, KpiTile, PageHeader, PillTabs, tabId } from '../design/blue/ui';
import { InlineLoadError } from '../components/states';
import { resourceDisplayState } from '../lib/resourceState';
import { closeWindow, createLinkWatch, navigateWindow, openBlankWindow } from '../lib/telegramLink';

// Meetings are shown and entered in one chosen zone: Tashkent by default, or
// China for people there. Neither has daylight saving, so each is a fixed offset.
// The choice is the viewer's own and is remembered in this browser. A viewer whose
// clock is in yet another zone also sees their own time.
export const MEETING_ZONES = [
  { id: 'Asia/Tashkent', label: 'Tashkent time', offset: '+05:00', minutes: 300 },
  { id: 'Asia/Shanghai', label: 'China time', offset: '+08:00', minutes: 480 },
];
const ZONE_KEY = 'naseeb.meetingZone';
const zoneById = (id) => MEETING_ZONES.find((zone) => zone.id === id) || MEETING_ZONES[0];
function storedZoneId() {
  try { return zoneById(window.localStorage.getItem(ZONE_KEY)).id; } catch { return MEETING_ZONES[0].id; }
}
let zone = zoneById(storedZoneId());
function setMeetingZone(id) {
  zone = zoneById(id);
  try { window.localStorage.setItem(ZONE_KEY, zone.id); } catch { /* private mode: kept for this visit */ }
}
// A picker inside a dialog changes the zone without redrawing the page behind it;
// when the dialog closes with another zone, the page is told to redraw.
const ZONE_EVENT = 'naseeb:meeting-zone';
function useZoneSync() {
  useEffect(() => {
    const opened = zone.id;
    return () => { if (zone.id !== opened) window.dispatchEvent(new Event(ZONE_EVENT)); };
  }, []);
}
const zoned = (value) => inServerZone(value, zone.id);
const clockText = (value) => viewerClockText(zoned(value));
const dateTimeText = (value) => viewerDateTimeText(zoned(value));
// "Today" / "Tomorrow" / "Fri 13 Nov", with both days counted in the chosen zone
// (not the browser's), so the label is right near midnight wherever the viewer is.
function dayLabel(value) {
  if (!value) return '';
  const midnight = (date) => { const day = new Date(date); day.setHours(0, 0, 0, 0); return day; };
  const days = Math.round((midnight(zoned(value)) - midnight(zoned(new Date()))) / 86400000);
  if (days === 0) return t('Today');
  if (days === 1) return t('Tomorrow');
  return shortDayText(zoned(value));
}
const viewerElsewhere = () => -new Date().getTimezoneOffset() !== zone.minutes;
// "27 Oct, 01:00 your time" when the viewer's clock differs from the chosen zone, else nothing.
const viewerTimeHint = (value) => (viewerElsewhere() ? t('{time} your time', { time: viewerDateTimeText(value) }) : '');
// A wall-clock "YYYY-MM-DDTHH:MM" in the chosen zone (a datetime-local value) as an instant.
const fromZone = (local) => new Date(`${local}:00${zone.offset}`);
function ZonePicker({ value, onChange }) {
  return <label className="meeting-zone"><Globe size={15} aria-hidden="true" /><span className="sr-only">{t("Time zone")}</span>
    <select value={value} onChange={(event) => onChange(event.target.value)}>
      {MEETING_ZONES.map((item) => <option key={item.id} value={item.id}>{t('{zone} (UTC+{hours})', { zone: t(item.label), hours: item.minutes / 60 })}</option>)}
    </select>
  </label>;
}

// Calendar key of a local Date (grid days, date arithmetic), as YYYY-MM-DD.
function dayKey(value) {
  const date = new Date(value);
  const pad = (part) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// The chosen zone's calendar day of a timestamp (or of now).
const meetingDay = (value = new Date()) => dayKey(zoned(value));

const byStart = (x, y) => new Date(x.starts_at) - new Date(y.starts_at);
const NO_SLOTS = [];

function groupByParticipant(slots) {
  const groups = new Map();
  for (const slot of slots) {
    if (!groups.has(slot.participant)) groups.set(slot.participant, []);
    groups.get(slot.participant).push(slot);
  }
  for (const list of groups.values()) list.sort(byStart);
  return groups;
}

const monthStart = (value) => { const date = new Date(value); return new Date(date.getFullYear(), date.getMonth(), 1); };

// Browsers ship no Uzbek weekday or time-zone names (they fall back to English),
// so Uzbek uses the translated weekday and a numeric offset ("GMT+5").
const uzbek = () => locale().startsWith('uz');
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

// "14:00 (Tashkent time)", plus "· 17:00 your time" for a viewer in another zone.
const timeZoneName = () => joinParts(
  t('{time} ({zone})', { time: clockText(new Date()), zone: t(zone.label) }),
  viewerElsewhere() && t('{time} your time', { time: viewerClockText(new Date()) }),
);

function slotRange(slot) {
  const end = new Date(new Date(slot.starts_at).getTime() + slot.duration_minutes * 60000);
  return joinParts(`${clockText(slot.starts_at)} – ${clockText(end)}, ${formatDateLocale(zoned(slot.starts_at), { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}`, viewerTimeHint(slot.starts_at));
}

// "Sunday, 4 October". Uzbek gets the translated weekday (see WEEKDAYS).
function dayTitle(key) {
  const date = new Date(`${key}T00:00`);
  if (!uzbek()) return formatDateLocale(date, { weekday: 'long', month: 'long', day: 'numeric' });
  return `${t(WEEKDAYS[(date.getDay() + 6) % 7])}, ${formatDateLocale(date, { month: 'long', day: 'numeric' })}`;
}

// One month of day buttons, Monday first. `marked` days are tinted (they have
// times); only days `canPick` accepts are clickable.
// `range` ({start, end}) shades a chosen span; `today` overrides the day marked as today;
// `showBack`/`showForward` hide an arrow (a two-month view shows one on each side).
function MonthGrid({ month, onMonth, canBack, canForward, marked, canPick, selected, onPick, label, range, today = meetingDay(), showBack = true, showForward = true }) {
  const offset = (month.getDay() + 6) % 7;
  const length = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const days = Array.from({ length }, (_, index) => new Date(month.getFullYear(), month.getMonth(), index + 1));
  const weekdays = WEEKDAYS.map((name, index) => (uzbek() ? t(name).slice(0, 2) : formatDateLocale(new Date(2024, 0, 1 + index), { weekday: 'short' })));
  const shift = (step) => onMonth(new Date(month.getFullYear(), month.getMonth() + step, 1));
  return <div className="booking-cal-month">
    <header>
      {showBack ? <button type="button" className="booking-cal-nav" disabled={!canBack} onClick={() => shift(-1)} aria-label={t("Previous month")}><ChevronLeft size={20} /></button> : <span className="booking-cal-nav" aria-hidden="true" />}
      <b aria-live="polite">{formatDateLocale(month, { month: 'long', year: 'numeric' })}</b>
      {showForward ? <button type="button" className="booking-cal-nav" disabled={!canForward} onClick={() => shift(1)} aria-label={t("Next month")}><ChevronRight size={20} /></button> : <span className="booking-cal-nav" aria-hidden="true" />}
    </header>
    <div className="booking-cal-days" role="group" aria-label={label}>
      {weekdays.map((name) => <span key={name} className="booking-cal-weekday" aria-hidden="true">{name}</span>)}
      {days.map((date, index) => {
        const key = dayKey(date);
        const edge = isRangeStart(key, range) || isRangeEnd(key, range);
        const classes = ['booking-cal-day', marked?.has(key) && 'is-open', key === today && 'is-today', isRangeBetween(key, range) && 'is-range-mid', isRangeStart(key, range) && range.end && range.end !== range.start && 'is-range-start', isRangeEnd(key, range) && range.end !== range.start && 'is-range-end'].filter(Boolean).join(' ');
        return <button key={key} type="button" style={index === 0 ? { gridColumnStart: offset + 1 } : undefined} className={classes} disabled={!canPick(key)} aria-pressed={selected === key || edge} aria-label={dayTitle(key)} onClick={() => onPick(key)}>{date.getDate()}</button>;
      })}
    </div>
  </div>;
}

// Month view of one person's open slots: available days are tinted, the chosen
// day lists its times, and choosing a time reveals "Confirm" beside it.
function SlotCalendar({ slots, selectedDate, onDate, selectedSlot, onSlot, onNext, onZone, readOnly = false }) {
  const openDays = new Set(slots.filter((slot) => slot.available).map((slot) => meetingDay(slot.starts_at)));
  const firstOpen = [...openDays].sort()[0];
  const lastOpen = [...openDays].sort().at(-1);
  const [viewMonth, setViewMonth] = useState(() => monthStart(firstOpen ? `${firstOpen}T00:00` : new Date()));
  const daySlots = slots.filter((slot) => meetingDay(slot.starts_at) === selectedDate);
  return <div className={`booking-cal-picker ${selectedDate ? 'has-day' : ''}`.trim()}>
    <div>
      <MonthGrid month={viewMonth} onMonth={setViewMonth} canBack={viewMonth > monthStart(new Date())} canForward={Boolean(lastOpen) && monthStart(`${lastOpen}T00:00`) > viewMonth} marked={openDays} canPick={(key) => openDays.has(key)} selected={selectedDate} onPick={onDate} label={t("Available dates")} />
      <div className="booking-cal-zone-row">
        <b>{t("Time zone")}</b>
        <ZonePicker value={zone.id} onChange={onZone} />
        <p className="booking-cal-zone">{timeZoneName()}</p>
      </div>
    </div>
    {selectedDate && <div className="booking-cal-times" role="group" aria-label={t("Available times")}>
      <b>{dayTitle(selectedDate)}</b>
      {daySlots.map((slot) => selectedSlot?.id === slot.id
        ? <div key={slot.id} className="booking-cal-confirm"><span>{clockText(slot.starts_at)}</span><button type="button" onClick={onNext} disabled={readOnly} title={readOnly ? t("Preview only — students can confirm here") : undefined}>{t("Confirm")}</button></div>
        : <button key={slot.id} type="button" className="booking-cal-time" disabled={!slot.available} onClick={() => onSlot(slot)}>{clockText(slot.starts_at)}</button>)}
    </div>}
  </div>;
}

// Matches OVERVIEW_SLOTS_PER_PARTICIPANT in backend meetings.py.
const OVERVIEW_SLOTS = 20;

// `staff`: a counselor/teacher/org member booking with one of their students —
// they pick the student, not a participant (the API sets participant = them).
// `defaultStudentId`/`defaultTopic`: pre-fill for "Rebook" on an expired or declined request.
// `initialParticipantId` (a shared booking link): open on that staff member's date & time step; when the
// student may not book them, `onUnavailable` is called and nothing about that person is loaded.
export function BookingForm({ staff = false, defaultStudentId = null, defaultStudentName = '', defaultTopic = '', initialParticipantId = null, onUnavailable, onClose, onSaved, notify }) {
  const [student, setStudent] = useState(defaultStudentId ? { id: defaultStudentId, name: defaultStudentName } : null);
  const [participants, setParticipants] = useState([]);
  const [participantId, setParticipantId] = useState('');
  const [slots, setSlots] = useState([]);
  const [selectedDate, setSelectedDate] = useState('');
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [step, setStep] = useState('pick');
  const [topic, setTopic] = useState(defaultTopic);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(!staff);
  const [peopleError, setPeopleError] = useState('');
  const [overviewKnown, setOverviewKnown] = useState(false);
  const [peopleAttempt, setPeopleAttempt] = useState(0);
  const [slotStates, setSlotStates] = useState({});
  const [slotAttempt, setSlotAttempt] = useState(0);
  const [saving, setSaving] = useState(false);
  const [zoneTick, setZoneTick] = useState(0);
  useZoneSync();
  useEffect(() => {
    if (staff) return undefined;
    let active = true;
    setLoading(true); setPeopleError('');
    Promise.allSettled([api.bookingParticipants(), api.bookingAvailability()]).then(([people, times]) => {
      if (!active) return;
      if (people.status === 'rejected') { setPeopleError(people.reason.message); return; }
      const nextPeople = people.value || [];
      const nextSlots = times.status === 'fulfilled' ? times.value || [] : [];
      setOverviewKnown(times.status === 'fulfilled');
      setParticipants(nextPeople);
      setSlots(nextSlots);
      const groups = groupByParticipant(nextSlots);
      const firstFree = (id) => (groups.get(id) || NO_SLOTS).find((slot) => slot.available);
      const wanted = initialParticipantId ? nextPeople.find((person) => person.id === initialParticipantId) : null;
      if (initialParticipantId && !wanted) { onUnavailable?.(); return; }
      const first = wanted || nextPeople.find((person) => firstFree(person.id)) || nextPeople[0];
      setParticipantId(String(first?.id || ''));
      const firstSlot = first && firstFree(first.id);
      if (firstSlot) setSelectedDate(meetingDay(firstSlot.starts_at));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {active = false;};
  }, [staff, peopleAttempt]); // eslint-disable-line react-hooks/exhaustive-deps -- the link's person is read once, on load
  // The overview holds only each person's next few times; the chosen person's full list replaces them.
  useEffect(() => {
    if (staff || !participantId) return undefined;
    let active = true;
    const id = Number(participantId);
    setSlotStates((current) => ({ ...current, [id]: { loading: true, error: '' } }));
    api.bookingAvailability(id).then((items) => {
      if (!active) return;
      const theirs = items || [];
      setSlotStates((current) => ({ ...current, [id]: { loading: false, error: '' } }));
      setSlots((current) => [...current.filter((slot) => slot.participant !== id), ...theirs]);
      const first = [...theirs].sort(byStart).find((slot) => slot.available);
      setSelectedDate((day) => theirs.some((slot) => slot.available && meetingDay(slot.starts_at) === day) ? day : first ? meetingDay(first.starts_at) : '');
    }).catch((err) => { if (active) setSlotStates((current) => ({ ...current, [id]: { loading: false, error: err.message } })); });
    return () => { active = false; };
  }, [staff, participantId, slotAttempt]);
  const slotsByPerson = useMemo(() => groupByParticipant(slots), [slots]);
  const personSlots = slotsByPerson.get(Number(participantId)) || NO_SLOTS;
  const person = participants.find((item) => String(item.id) === participantId);
  const personName = person ? fullName(person) || person.username : '';
  const duration = selectedSlot?.duration_minutes || personSlots[0]?.duration_minutes;
  // Students book only from published times; until there are some, there is nothing to pick.
  const slotState = slotStates[Number(participantId)];
  const loadingSlots = Boolean(participantId) && (!slotState || slotState.loading);
  const slotError = slotState?.error;
  const noTimes = !loading && !loadingSlots && !slotError && Boolean(participantId) && !personSlots.some((slot) => slot.available);
  function choosePerson(id) {
    if (String(id) === participantId) return;
    setSlotStates((current) => ({ ...current, [id]: { loading: true, error: '' } }));
    const next = (slotsByPerson.get(id) || NO_SLOTS).find((slot) => slot.available);
    setParticipantId(String(id));
    setSelectedDate(next ? meetingDay(next.starts_at) : '');
    setSelectedSlot(null);
  }
  // A new zone moves every time to another clock (and maybe another day): start the pick over.
  function changeZone(id) {
    setMeetingZone(id);
    const next = [...personSlots].sort(byStart).find((slot) => slot.available);
    setSelectedDate(next ? meetingDay(next.starts_at) : '');
    setSelectedSlot(null);
    setZoneTick((value) => value + 1);
  }
  async function submit(event) {
    event.preventDefault();
    if (!staff && !selectedSlot) return;
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.create('bookings', staff ? {
        student: Number(values.get('student')),
        topic: values.get('topic'),
        starts_at: fromZone(values.get('starts_at')).toISOString(),
        duration_minutes: Number(values.get('duration_minutes')),
        notes: values.get('notes'),
        ask_student: values.get('ask_student') === 'on'
      } : {
        participant: Number(participantId), availability_slot: selectedSlot.id,
        topic, starts_at: selectedSlot.starts_at, duration_minutes: selectedSlot.duration_minutes, notes
      });
      notify(staff ? (values.get('ask_student') === 'on' ? t("Invitation sent. Waiting for the student to confirm.") : t("Meeting confirmed.")) : t("Meeting request sent for approval."));
      onSaved();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  if (staff) return <Modal title={t("Book a meeting")} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <StudentSearchInput name="student" required value={student} onChange={setStudent} /><Field label={t("Topic")}><input name="topic" required defaultValue={defaultTopic} placeholder={t("Essay review, university list...")} /></Field><Field label={t("Date & time")}><input name="starts_at" type="datetime-local" required /></Field><Field label={t("Duration")}><select name="duration_minutes" defaultValue="45"><option value="30">{t("30 min")}</option><option value="45">{t("45 min")}</option><option value="60">{t("60 min")}</option></select></Field><Field label={t("Notes")}><textarea name="notes" placeholder={t("What would you like to discuss?")} /></Field>
    <label className="weekly-day"><input type="checkbox" name="ask_student" defaultChecked /> {t("Ask the student to confirm")}</label>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Booking…") : t("Book meeting")}</button></div>
  </form></Modal>;
  const details = step === 'details' && selectedSlot;
  return <Modal title={t("Request a meeting")} onClose={onClose} className="booking-scheduler-modal"><form className="booking-cal" onSubmit={submit}>
    <aside className="booking-cal-side">
      {details ? <>
        <button type="button" className="booking-cal-back" onClick={() => setStep('pick')} aria-label={t("Back")}><ArrowLeft size={20} /></button>
        <small className="booking-cal-role">{joinParts(label(person?.role), person?.position)}</small>
        <h3 className="booking-cal-host">{personName}</h3>
      </> : <section className="booking-cal-people" aria-label={t("Meet with")}>
        <h3>{t("Meet with")}</h3>
        {loading ? <p className="booking-cal-note">{t("Loading available staff…")}</p> : peopleError ? <InlineLoadError message={peopleError} onRetry={() => setPeopleAttempt((value) => value + 1)} /> : participants.length ? participants.map((item) => {
          const free = (slotsByPerson.get(item.id) || NO_SLOTS).filter((slot) => slot.available).length;
          // Until a person is picked only their next OVERVIEW_SLOTS times are loaded: a full page means "or more".
          const partial = participantId !== String(item.id) && free >= OVERVIEW_SLOTS;
          const name = fullName(item) || item.username;
          const state = slotStates[item.id];
          const known = state ? !state.loading && !state.error : overviewKnown;
          return <button key={item.id} type="button" className="booking-cal-person" aria-pressed={participantId === String(item.id)} onClick={() => choosePerson(item.id)}><span className="booking-cal-avatar" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span><span><b>{name}</b><small>{state?.loading ? t('Loading…') : !known ? '—' : free ? t(partial ? "{n}+ available times" : "{n} available times", { n: free }) : t("No available times")}</small></span></button>;
        }) : <p className="booking-cal-note">{t("No counselor, teacher, or school representative is available for your account.")}</p>}
      </section>}
      <ul className="booking-cal-meta">
        {duration && <li><Clock3 size={18} aria-hidden="true" /> {duration} {t("min")}</li>}
        {details && <li><CalendarDays size={18} aria-hidden="true" /> {slotRange(selectedSlot)}</li>}
        {details && <li><Globe size={18} aria-hidden="true" /> {timeZoneName()}</li>}
      </ul>
    </aside>
    <section className="booking-cal-main">
      {details ? <>
        <h3>{t("Enter details")}</h3>
        <div className="booking-cal-fields">
          <Field label={t("Topic")}><input name="topic" required value={topic} onChange={(event) => setTopic(event.target.value)} placeholder={t("Essay review, university list...")} /></Field>
          <Field label={t("Notes")}><textarea name="notes" value={notes} onChange={(event) => setNotes(event.target.value)} placeholder={t("What would you like to discuss?")} /></Field>
          <div><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Requesting…") : t("Request meeting")}</button></div>
        </div>
      </> : <>
        <h3>{t("Choose a date and time")}</h3>
        {loading || loadingSlots ? <p className="booking-cal-note">{t("Loading available times…")}</p> : !participantId ? null : slotError ? <InlineLoadError message={slotError} onRetry={() => {setSelectedSlot(null);setSlotAttempt((value) => value + 1);}} /> : noTimes
          ? <p className="booking-cal-note" role="status">{t("{name} hasn't published available times yet. Message them or check back later.", { name: personName || t("Meeting participant") })}</p>
          : <SlotCalendar key={`${participantId}-${zoneTick}`} onZone={changeZone} slots={personSlots} selectedDate={selectedDate} onDate={(key) => { setSelectedDate(key); setSelectedSlot(null); }} selectedSlot={selectedSlot} onSlot={setSelectedSlot} onNext={() => setStep('details')} />}
      </>}
    </section>
  </form></Modal>;
}

// A past slot, or one any meeting points at (`editable` from the API), stays as it is; the server refuses to move it.
const isPast = (slot) => new Date(slot.starts_at) <= new Date();
const canEdit = (slot) => slot.available && slot.editable !== false && !isPast(slot);
function editTitle(slot) {
  if (!slot.available) return t("A student already requested this time.");
  if (slot.editable === false || isPast(slot)) return t("Locked");
  return t("Edit");
}

const slotEnd = (slot) => new Date(new Date(slot.starts_at).getTime() + slot.duration_minutes * 60000);

const weekdayName = (index) => (uzbek() ? t(WEEKDAYS[index]) : formatDateLocale(new Date(2024, 0, 1 + index), { weekday: 'long' }));
const DEFAULT_RANGE = ['09:00', '17:00'];
// The range offered by "add hours": the hour after the day's last one, while the day has room.
function nextRange(ranges) {
  const last = ranges.at(-1)?.[1];
  if (!last || last >= '23:00') return DEFAULT_RANGE;
  return [last, `${String(Number(last.slice(0, 2)) + 1).padStart(2, '0')}${last.slice(2)}`];
}
const rangesOverlap = (ranges) => [...ranges].sort().some((range, index, sorted) => index > 0 && range[0] < sorted[index - 1][1]);

const DURATIONS = [15, 20, 30, 45, 60, 90];
const monthShort = (index) => formatDateLocale(new Date(2024, index, 1), { month: 'short' });
const hoursText = (count) => tp('{n} hour|{n} hours', count, { n: count });
// The weekly-availability window the counselor's tab works in Tashkent days (that is where the server counts it).
const tashkentToday = () => dayKey(inServerZone(new Date(), 'Asia/Tashkent'));
// Fills {name} slots of a translated sentence with bold values.
const richText = (template, values) => template.split(/(\{\w+\})/).map((part, index) => {
  const name = part.match(/^\{(\w+)\}$/)?.[1];
  return name && values[name] !== undefined ? <b key={index}>{values[name]}</b> : part;
});
const WINDOW_PROBLEMS = {
  days: 'Enter a number of days between 1 and 365.',
  range_missing: 'Choose the first and last day.',
  range_order: 'The last day cannot be before the first day.',
  range_past: 'The last day cannot be in the past.',
};
// DRF field errors ({field: ["message"]}) of a failed save, joined per field.
function fieldErrors(err) {
  const details = err?.details;
  if (!details || typeof details !== 'object' || Array.isArray(details)) return {};
  return Object.fromEntries(Object.entries(details).map(([name, value]) => [name, [].concat(value).map((item) => (typeof item === 'string' ? item : JSON.stringify(item))).join(' ')]));
}

// Two months side by side (stacked on a phone): first click starts the range,
// the second ends it; Apply keeps it, Cancel / Esc / a click outside drops it.
function DateRangePopover({ value, today, boundary, onApply, onCancel }) {
  const [draft, setDraft] = useState({ start: value.start, end: value.end });
  const [view, setView] = useState(() => monthStart(`${value.start && value.start >= today ? value.start : today}T00:00`));
  const popover = useRef(null);
  const cancel = useRef(onCancel);
  cancel.current = onCancel;
  useEffect(() => {
    popover.current?.focus();
    const away = (event) => { if (!boundary.current?.contains(event.target)) cancel.current(); };
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, [boundary]);
  const next = new Date(view.getFullYear(), view.getMonth() + 1, 1);
  const thisMonth = monthStart(`${today}T00:00`);
  const shared = { canPick: (key) => key >= today, onPick: (key) => setDraft((current) => pickRangeDay(current, key, today)), range: draft, today };
  return <div ref={popover} className="range-popover" role="dialog" aria-label={t("Choose a date range")} tabIndex={-1} onKeyDown={(event) => { if (event.key === 'Escape') { event.stopPropagation(); event.preventDefault(); onCancel(); } }}>
    <div className="range-popover-months">
      <MonthGrid {...shared} month={view} onMonth={setView} canBack={view > thisMonth} canForward showForward={false} label={t("Choose a date range")} />
      <MonthGrid {...shared} month={next} onMonth={(month) => setView(new Date(month.getFullYear(), month.getMonth() - 1, 1))} canBack showBack={false} canForward label={t("Choose a date range")} />
    </div>
    <p className="range-popover-hint" aria-live="polite">{draft.start ? (draft.end ? rangeText(draft.start, draft.end, monthShort) : t("Now choose the last day.")) : t("Choose the first day.")}</p>
    <div className="range-popover-actions">
      <button type="button" className="button quiet" onClick={onCancel}>{t("Cancel")}</button>
      <button type="button" className="button primary" disabled={!draft.start} onClick={() => onApply({ start: draft.start, end: draft.end || draft.start })}>{t("Apply")}</button>
    </div>
  </div>;
}

// "= Tashkent time: 21:00–23:15" for a range typed in another zone; another day is named ("Sun 22:00–23:00").
function tashkentEquivalent(day, from, to) {
  const pieces = shiftRange(day, from, to, TASHKENT_MINUTES - zone.minutes);
  const text = pieces.map((piece) => `${piece.day === day ? '' : `${weekdayName(piece.day).slice(0, 3)} `}${piece.from}–${piece.to}`).join(' + ');
  return `= ${t('Tashkent time')}: ${text}`;
}

// Weekly hours, laid out like Calendly: meeting duration, the window invitees
// can book in (with the notice), then one row per weekday with its from–to
// hours. The server turns it all into the dated times students book.
function WeeklyHours({ notify, onSaved, onZone }) {
  const [hours, setHours] = useState(null);
  const [duration, setDuration] = useState(45);
  const [notice, setNotice] = useState('12');
  const [win, setWin] = useState(windowFromApi());
  const [stats, setStats] = useState(null);
  const [errors, setErrors] = useState({});
  const [pickingRange, setPickingRange] = useState(false);
  const rangeBox = useRef(null);
  const rangeButton = useRef(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setError('');
    api.weeklyAvailability().then((data) => {
      if (!active) return;
      setHours(tashkentToZone(data.hours || {}, zone.minutes));
      setDuration(data.duration_minutes || 45);
      setNotice(String(data.min_notice_hours ?? 12));
      setWin(windowFromApi(data));
      setStats(typeof data.upcoming_booked === 'number' || typeof data.free_slots === 'number' ? { booked: data.upcoming_booked ?? 0, free: data.free_slots ?? 0 } : null);
    }).catch((err) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [attempt]);
  const setDay = (day, ranges) => setHours((current) => ({ ...current, [day]: ranges }));
  const setTime = (day, index, side, value) => setDay(day, hours[day].map((range, at) => (at === index ? (side ? [range[0], value] : [value, range[1]]) : range)));
  // The typed hours move to the new zone's clock (through Tashkent's), so nothing is lost by switching.
  function changeHoursZone(id) {
    const before = zone.minutes;
    setMeetingZone(id);
    setHours((current) => convertZone(current, before, zone.minutes));
    onZone();
  }
  const today = tashkentToday();
  const noticeNumber = Number(notice);
  const noticeShown = notice !== '' && Number.isInteger(noticeNumber) && noticeNumber >= 0 ? noticeNumber : 0;
  const daysNumber = Number(win.days);
  const summary = win.mode === 'range'
    ? (win.start ? rangeText(win.start, win.end, monthShort) : t("a date range"))
    : tp('{n} calendar day into the future|{n} calendar days into the future', daysNumber || 0, { n: win.days === '' ? 0 : daysNumber });
  function closeRange(apply) {
    if (apply) setWin((current) => ({ ...current, mode: 'range', ...apply }));
    setPickingRange(false);
    rangeButton.current?.focus();
  }
  async function save(event) {
    event.preventDefault();
    const days = Object.values(hours);
    const problems = {};
    if (days.some((ranges) => ranges.some(([from, to]) => !from || !to || (to <= from && to !== '00:00')))) problems.hours = t("Choose an end time after the start time.");
    else if (days.some(rangesOverlap)) problems.hours = t("Hours on the same day cannot overlap.");
    if (notice === '' || !Number.isInteger(noticeNumber) || noticeNumber < 0 || noticeNumber > 168) problems.min_notice_hours = t("Enter a notice between 0 and 168 hours.");
    const windowProblemCode = windowProblem(win, today);
    if (windowProblemCode) problems.window = t(WINDOW_PROBLEMS[windowProblemCode]);
    setErrors(problems);
    if (Object.keys(problems).length) return;
    setBusy(true);
    try {
      // The inputs hold the chosen zone's clock; the server keeps Tashkent's.
      const saved = await api.saveWeeklyAvailability({ duration_minutes: duration, hours: zoneToTashkent(hours, zone.minutes), min_notice_hours: noticeNumber, ...windowToApi(win) });
      // Keep the numbers when an older API does not send them back.
      setHours(tashkentToZone(saved.hours || {}, zone.minutes));
      setNotice(String(saved.min_notice_hours ?? noticeNumber));
      if (saved.window_mode) setWin(windowFromApi(saved));
      if (typeof saved.upcoming_booked === 'number' || typeof saved.free_slots === 'number') setStats({ booked: saved.upcoming_booked ?? 0, free: saved.free_slots ?? 0 });
      notify(t("Weekly hours saved."));
      onSaved();
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length) setErrors({ ...fields, window: [fields.window_days, fields.window_start, fields.window_end, fields.window_mode].filter(Boolean).join(' ') || undefined });
      else notify(err.message, 'error');
    } finally { setBusy(false); }
  }
  if (error) return <div className="availability-weekly"><InlineLoadError message={error} onRetry={() => setAttempt((value) => value + 1)} /></div>;
  if (!hours) return <div className="availability-weekly"><p className="booking-cal-note">{t("Loading available times…")}</p></div>;
  const durations = DURATIONS.includes(duration) ? DURATIONS : [...DURATIONS, duration].sort((x, y) => x - y);
  const general = errors.detail || errors.non_field_errors;
  return <form className="availability-weekly" onSubmit={save} noValidate>
    {general && <p className="field-error" role="alert">{general}</p>}
    <div className="availability-block">
      <label htmlFor="weekly-duration"><b>{t("Meeting duration")}</b></label>
      <select id="weekly-duration" value={duration} onChange={(event) => setDuration(Number(event.target.value))} aria-invalid={Boolean(errors.duration_minutes) || undefined}>
        {durations.map((value) => <option key={value} value={value}>{value} {t("min")}</option>)}
      </select>
      {errors.duration_minutes && <small className="field-error" role="alert">{errors.duration_minutes}</small>}
    </div>
    <section className="availability-block window-block" aria-labelledby="window-title">
      <h4 id="window-title">{t("Date range")}</h4>
      <p className="window-sentence">{richText(t("Invitees can schedule within {summary} with at least {notice} notice"), { summary, notice: hoursText(noticeShown) })}</p>
      <div className="window-options">
        <label className="window-option">
          <input type="radio" name="window-mode" checked={win.mode === 'rolling'} onChange={() => setWin({ ...win, mode: 'rolling' })} />
          <input type="number" inputMode="numeric" min="1" max="365" step="1" value={win.days} onFocus={() => win.mode !== 'rolling' && setWin({ ...win, mode: 'rolling' })} onChange={(event) => setWin({ ...win, mode: 'rolling', days: event.target.value })} aria-label={t("Calendar days into the future")} aria-invalid={(win.mode === 'rolling' && Boolean(errors.window)) || undefined} />
          <span>{t("calendar days into the future")}</span>
        </label>
        <div className="window-option window-range" ref={rangeBox}>
          <label><input type="radio" name="window-mode" checked={win.mode === 'range'} onChange={() => setWin({ ...win, mode: 'range' })} /> <span>{t("Within a date range")}</span></label>
          <button type="button" ref={rangeButton} className="window-range-field" aria-haspopup="dialog" aria-expanded={pickingRange} aria-invalid={(win.mode === 'range' && Boolean(errors.window)) || undefined} onClick={() => { setWin({ ...win, mode: 'range' }); setPickingRange(true); }}>
            <CalendarDays size={16} aria-hidden="true" /> {win.start ? rangeText(win.start, win.end, monthShort) : t("Choose dates")}
          </button>
          {pickingRange && <DateRangePopover value={win} today={today} boundary={rangeBox} onApply={closeRange} onCancel={() => closeRange(null)} />}
        </div>
      </div>
      {errors.window && <small className="field-error" role="alert">{errors.window}</small>}
      <div className="window-notice">
        <label htmlFor="weekly-notice"><b>{t("Students must book at least")}</b></label>
        <input id="weekly-notice" type="number" inputMode="numeric" min="0" max="168" step="1" value={notice} onChange={(event) => setNotice(event.target.value)} aria-invalid={Boolean(errors.min_notice_hours) || undefined} />
        <span>{t("hours ahead")}</span>
      </div>
      {errors.min_notice_hours && <small className="field-error" role="alert">{errors.min_notice_hours}</small>}
    </section>
    <section className="availability-block" aria-labelledby="weekly-title">
      <div className="availability-block-head">
        <h4 id="weekly-title">{t("Weekly hours")}</h4>
        <ZonePicker value={zone.id} onChange={changeHoursZone} />
      </div>
      <p className="booking-cal-note">{t("Set the hours you can meet each week.")} <b className="weekly-zone-label">{t("Times in {zone}", { zone: t('{zone} (UTC+{hours})', { zone: t(zone.label), hours: zone.minutes / 60 }) })}</b>{zone.minutes !== TASHKENT_MINUTES && <> {t("They are saved on Tashkent's clock for students.")}</>}</p>
      <ul className="weekly-days">{WEEKDAYS.map((name, day) => {
        const ranges = hours[day] || [];
        const dayName = weekdayName(day);
        return <li key={name}>
          <label className="weekly-day"><input type="checkbox" checked={ranges.length > 0} onChange={(event) => setDay(day, event.target.checked ? [DEFAULT_RANGE] : [])} /> {dayName}</label>
          <div className="weekly-ranges">{ranges.length ? ranges.map(([from, to], index) => <div key={index} className="weekly-range">
            <label className="availability-time"><span className="sr-only">{t("{day}: from", { day: dayName })}</span><input type="time" required value={from} onChange={(event) => setTime(day, index, 0, event.target.value)} /></label>
            <span aria-hidden="true">–</span>
            <label className="availability-time"><span className="sr-only">{t("{day}: until", { day: dayName })}</span><input type="time" required value={to} onChange={(event) => setTime(day, index, 1, event.target.value)} /></label>
            {zone.minutes !== TASHKENT_MINUTES && from && to && (to > from || to === '00:00') ? <span className="weekly-equivalent">{tashkentEquivalent(day, from, to)}</span> : null}
            <button type="button" className="availability-remove" onClick={() => setDay(day, ranges.filter((_, at) => at !== index))} aria-label={t("Remove {day} {from}–{to}", { day: dayName, from, to })} title={t("Remove")}><X size={16} aria-hidden="true" /></button>
          </div>) : <span className="weekly-off">{t("Unavailable")}</span>}</div>
          <button type="button" className="availability-remove weekly-add" disabled={ranges.length >= 4} onClick={() => setDay(day, [...ranges, nextRange(ranges)])} aria-label={t("Add hours on {day}", { day: dayName })} title={t("Add hours")}><Plus size={16} aria-hidden="true" /></button>
        </li>;
      })}</ul>
      {errors.hours && <small className="field-error" role="alert">{errors.hours}</small>}
    </section>
    {stats && <p className="window-stats">{t("{booked} booked · {free} free times in this window", { booked: stats.booked, free: stats.free })}</p>}
    <div className="availability-add-actions"><button type="submit" className="button primary" disabled={busy} aria-busy={busy}><Check size={16} aria-hidden="true" /> {busy ? t("Saving…") : t("Save weekly hours")}</button></div>
  </form>;
}

// Staff publish the times students can book. Same calendar the student sees:
// days with times are tinted; the chosen day lists its times and adds new ones.
function AvailabilityManager({ onClose, notify }) {
  const [slots, setSlots] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedDay, setSelectedDay] = useState(() => meetingDay());
  const [viewMonth, setViewMonth] = useState(() => monthStart(new Date()));
  const [time, setTime] = useState('');
  // Optional: with an end time the range is cut into `duration` slots (09:00–12:00 → 09:00, 09:45, …).
  const [endTime, setEndTime] = useState('');
  const [duration, setDuration] = useState(45);
  const [editing, setEditing] = useState(null);
  const [tab, setTab] = useState('weekly');
  const [, setZoneTick] = useState(0);
  useZoneSync();
  // Bumped after the weekly hours are saved: the dated times were rebuilt.
  const [slotsVersion, setSlotsVersion] = useState(0);
  // A day that already has times shows them, with the add form behind one button.
  const [adding, setAdding] = useState(false);
  const sortSlots = (items) => [...items].sort((x, y) => new Date(x.starts_at) - new Date(y.starts_at));
  useEffect(() => {
    let active = true;
    api.bookingAvailability().then((items) => {
      if (!active) return;
      const next = sortSlots(items || []);
      setSlots(next);
      if (next[0]) { setSelectedDay(meetingDay(next[0].starts_at)); setViewMonth(monthStart(zoned(next[0].starts_at))); }
    }).catch((err) => { if (active) notify(err.message, 'error'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [notify, slotsVersion]);
  const today = meetingDay();
  const slotDays = new Set(slots.map((slot) => meetingDay(slot.starts_at)));
  const daySlots = slots.filter((slot) => meetingDay(slot.starts_at) === selectedDay);
  const openCount = slots.filter((slot) => slot.available).length;
  const selectedWeekday = (new Date(`${selectedDay}T00:00`).getDay() + 6) % 7;
  function pickDay(key) {
    setSelectedDay(key);
    setAdding(false);
    setEditing(null);
  }
  async function add(event) {
    event.preventDefault();
    const startsAt = fromZone(`${selectedDay}T${time}`);
    if (!time || startsAt <= new Date()) { notify(t("Choose a time in the future."), 'error'); return; }
    if (endTime && endTime <= time) { notify(t("Choose an end time after the start time."), 'error'); return; }
    setBusy(true);
    try {
      if (endTime) {
        // One day's range, cut into slots by the endpoint that repeats a time over dates.
        const result = await api.repeatBookingAvailability({
          weekdays: [selectedWeekday], time, end_time: endTime, duration_minutes: duration,
          start_date: selectedDay, end_date: selectedDay, timezone: zone.id,
        });
        setSlots((current) => sortSlots([...current, ...(result.slots || [])]));
        notify(result.skipped
          ? t("{created} times added, {skipped} skipped (past or overlapping).", { created: result.created, skipped: result.skipped })
          : t("{created} times added.", { created: result.created }), result.created ? undefined : 'error');
      } else {
        const slot = await api.addBookingAvailability({ starts_at: startsAt.toISOString(), duration_minutes: duration });
        setSlots((current) => sortSlots([...current, { ...slot, available: true }]));
        notify(t("Available time added."));
      }
      setTime('');
      setEndTime('');
      setAdding(false);
    } catch (err) { notify(err.message, 'error'); } finally { setBusy(false); }
  }
  async function remove(id) {
    setBusy(true);
    try { await api.removeBookingAvailability(id); setSlots((current) => current.filter((slot) => slot.id !== id)); notify(t("Available time removed.")); }
    catch (err) { notify(err.message, 'error'); } finally { setBusy(false); }
  }
  async function saveEdit(event) {
    event.preventDefault();
    const startsAt = fromZone(`${editing.date}T${editing.time}`);
    if (!editing.date || !editing.time || startsAt <= new Date()) { notify(t("Choose a time in the future."), 'error'); return; }
    setBusy(true);
    try {
      const slot = await api.editBookingAvailability(editing.id, { starts_at: startsAt.toISOString(), duration_minutes: editing.duration });
      setSlots((current) => sortSlots(current.map((item) => (item.id === slot.id ? slot : item))));
      setSelectedDay(meetingDay(slot.starts_at));
      setEditing(null);
      notify(t("Available time updated."));
    } catch (err) { notify(err.message, 'error'); } finally { setBusy(false); }
  }
  const startEdit = (slot) => setEditing({ id: slot.id, date: meetingDay(slot.starts_at), time: localInputValue(slot.starts_at).slice(11), duration: slot.duration_minutes });
  return <Modal title={t("My available hours")} onClose={onClose} className="booking-scheduler-modal">
    <div className="availability-tabs"><PortalTabs active={tab} onChange={setTab} items={[['weekly', 'Weekly hours'], ['dates', 'Specific dates']]} /></div>
    {tab === 'weekly' ? <WeeklyHours notify={notify} onSaved={() => setSlotsVersion((value) => value + 1)} onZone={() => setZoneTick((value) => value + 1)} /> : <div className="booking-cal availability-cal">
      <aside className="booking-cal-side">
        <p className="booking-cal-note">{t("Add times students can choose when requesting a meeting.")} {t("Times are in {zone}.", { zone: t(zone.label) })}</p>
        <MonthGrid month={viewMonth} onMonth={setViewMonth} canBack={viewMonth > monthStart(new Date())} canForward marked={slotDays} canPick={(key) => key >= today} selected={selectedDay} onPick={pickDay} label={t("Choose a date and time")} />
        <p className="booking-cal-zone"><Globe size={15} aria-hidden="true" /> {timeZoneName()}{!loading && <> · {t("{n} available times", { n: openCount })}</>}</p>
      </aside>
      <section className="booking-cal-main availability-day">
        <h3>{dayTitle(selectedDay)}</h3>
        {loading ? <p className="booking-cal-note">{t("Loading available times…")}</p> : daySlots.length ? <ul className="availability-slots">{daySlots.map((slot) => <li key={slot.id} className={slot.available ? '' : 'is-requested'}>
          {editing?.id === slot.id ? <form className="availability-add-row" style={{ gridColumn: '1 / -1' }} onSubmit={saveEdit} aria-label={`${t("Edit")} ${clockText(slot.starts_at)}`}>
            <label className="availability-time"><span className="sr-only">{t("Date")}</span><input type="date" required min={today} value={editing.date} onChange={(event) => setEditing({ ...editing, date: event.target.value })} /></label>
            <label className="availability-time"><span className="sr-only">{t("Time")}</span><input type="time" required value={editing.time} onChange={(event) => setEditing({ ...editing, time: event.target.value })} /></label>
            <fieldset className="availability-durations"><legend className="sr-only">{t("Duration")}</legend>{[30, 45, 60].map((value) => <label key={value}><input type="radio" name={`availability-edit-${slot.id}`} checked={editing.duration === value} onChange={() => setEditing({ ...editing, duration: value })} /><span>{value} {t("min")}</span></label>)}</fieldset>
            <button type="button" className="button quiet" disabled={busy} onClick={() => setEditing(null)}>{t("Cancel")}</button>
            <button className="button primary" disabled={busy} aria-busy={busy}>{t("Save")}</button>
          </form> : <>
            <span><b>{clockText(slot.starts_at)} – {clockText(slotEnd(slot))}</b><small>{slot.duration_minutes} {t("min")}</small></span>
            <span className="availability-state">{slot.available ? t("Available") : t("Requested")}</span>
            <span style={{ display: 'flex', gap: 4 }}>
              <button type="button" className="availability-remove" disabled={busy || !canEdit(slot)} onClick={() => startEdit(slot)} aria-label={`${t("Edit")} ${clockText(slot.starts_at)}`} title={editTitle(slot)}><Pencil size={16} aria-hidden="true" /></button>
              <button type="button" className="availability-remove" disabled={busy || !slot.available} onClick={() => remove(slot.id)} aria-label={`${t("Remove")} ${clockText(slot.starts_at)}`} title={slot.available ? t("Remove") : t("A student already requested this time.")}><Trash2 size={16} aria-hidden="true" /></button>
            </span>
          </>}
        </li>)}</ul> : <p className="booking-cal-note">{t("No times on this day yet.")}</p>}
        {daySlots.length > 0 && !adding ? <div className="availability-add-actions"><button type="button" className="button light" onClick={() => setAdding(true)}><Plus size={16} aria-hidden="true" /> {t("Add more times")}</button></div> : <form className="availability-add" onSubmit={add}>
          <b>{t("Add available time")}</b>
          <p className="booking-cal-note">{t("Set an end time to fill the whole range with meeting slots.")}</p>
          <div className="availability-add-row">
            <label className="availability-time"><span className="sr-only">{t("Time")}</span><input type="time" required value={time} onChange={(event) => setTime(event.target.value)} /></label>
            <span aria-hidden="true">–</span>
            <label className="availability-time"><span className="sr-only">{t("Until (optional)")}</span><input type="time" min={time || undefined} value={endTime} onChange={(event) => setEndTime(event.target.value)} title={t("Until (optional)")} /></label>
            <fieldset className="availability-durations"><legend className="sr-only">{t("Duration")}</legend>{[30, 45, 60].map((value) => <label key={value}><input type="radio" name="availability-duration" checked={duration === value} onChange={() => setDuration(value)} /><span>{value} {t("min")}</span></label>)}</fieldset>
          </div>
          {/* An empty start time is caught by the input's `required`, so Save stays clickable and says why. */}
          <div className="availability-add-actions"><button type="submit" className="button primary" disabled={busy} aria-busy={busy}><Check size={16} aria-hidden="true" /> {t("Save")}</button></div>
        </form>}
      </section>
    </div>}
  </Modal>;
}

// `datetime-local` wants wall-clock time without a zone: the chosen zone's, like the rest of the page.
function localInputValue(iso) {
  const date = zoned(iso);
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function RescheduleForm({ booking, staff = false, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(staff || Boolean(booking.participant));
  const [slotsError, setSlotsError] = useState('');
  const [slotsAttempt, setSlotsAttempt] = useState(0);
  const [selectedDate, setSelectedDate] = useState('');
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [staffSlotId, setStaffSlotId] = useState('');
  const form = useRef(null);
  useEffect(() => {
    // Staff see their own slots, usable only on a meeting they take part in; a student sees the participant's free ones.
    if (!staff && !booking.participant) return undefined;
    let active = true;
    setLoading(true); setSlotsError('');
    const current = new Date(booking.starts_at).getTime();
    // `reschedule`: this meeting's own time does not block the slots it overlaps.
    const query = new URLSearchParams({ reschedule: booking.id });
    if (!staff) query.set('participant', booking.participant);
    request(`/bookings/availability/?${query}`).then((items) => {
      if (!active) return;
      // The meeting's own slot (or time) is where it already is, not a new time.
      const next = (items || [])
        .filter((slot) => !staff || slot.participant === booking.participant)
        .map((slot) => (slot.id === booking.availability_slot || new Date(slot.starts_at).getTime() === current ? { ...slot, available: false } : slot))
        .sort((x, y) => new Date(x.starts_at) - new Date(y.starts_at));
      setSlots(next);
      const first = next.find((slot) => slot.available);
      if (first) setSelectedDate(meetingDay(first.starts_at));
    }).catch((err) => { if (active) setSlotsError(err.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [staff, booking.id, booking.participant, booking.availability_slot, booking.starts_at, slotsAttempt]);
  const openSlots = slots.filter((slot) => slot.available);
  // Staff may also suggest any free time; students only move onto a published slot.
  const staffSlot = staff ? openSlots.find((slot) => String(slot.id) === staffSlotId) : null;
  const chosen = staff ? staffSlot : selectedSlot;
  async function submit(event) {
    event.preventDefault();
    if (!staff && !selectedSlot) return;
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.rescheduleBooking(booking.id, chosen ? {
        starts_at: chosen.starts_at, duration_minutes: chosen.duration_minutes, availability_slot: chosen.id,
      } : {
        starts_at: fromZone(values.get('starts_at')).toISOString(),
        duration_minutes: Number(values.get('duration_minutes')),
      });
      notify(staff ? t("Meeting moved.") : t("New time sent for confirmation."));
      onSaved();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  const otherParty = (staff ? booking.student_name : booking.participant_name) || t("Meeting participant");
  const calendar = !staff && !loading && openSlots.length > 0;
  let body;
  if (slotsError && !staff) body = <InlineLoadError message={slotsError} onRetry={() => {setSelectedSlot(null);setSlotsAttempt((value) => value + 1);}} />;
  else if (loading) body = <p className="form-wide booking-cal-note">{t("Loading available times…")}</p>;
  else if (staff) body = <>
    {openSlots.length > 0 && <Field label={t("My available times")}><select value={staffSlotId} onChange={(event) => setStaffSlotId(event.target.value)}><option value="">{t("Another time")}</option>{openSlots.map((slot) => <option key={slot.id} value={slot.id}>{slotRange(slot)}</option>)}</select></Field>}
    {!staffSlot && <><Field label={t("Date & time")}><input name="starts_at" type="datetime-local" required defaultValue={localInputValue(booking.starts_at)} /></Field><Field label={t("Duration")}><select name="duration_minutes" defaultValue={String(booking.duration_minutes || 45)}><option value="30">{t("30 min")}</option><option value="45">{t("45 min")}</option><option value="60">{t("60 min")}</option></select></Field></>}
  </>;
  else if (calendar) body = <div className="form-wide availability-picker"><h3>{t("Choose a new date and time")}</h3><SlotCalendar slots={slots} selectedDate={selectedDate} onDate={(key) => { setSelectedDate(key); setSelectedSlot(null); }} selectedSlot={selectedSlot} onSlot={setSelectedSlot} onNext={() => form.current?.requestSubmit()} /></div>;
  else body = <p className="form-wide booking-cal-note" role="status">{t("{name} hasn't published available times yet. Message them or check back later.", { name: otherParty })}</p>;
  const title = staff ? t("Move meeting") : t("Reschedule meeting");
  return <Modal title={title} onClose={onClose} className={calendar ? 'booking-scheduler-modal' : undefined}><form ref={form} className="form-grid" onSubmit={submit}><p className="form-wide">{staff ? t("The meeting moves to the new time and stays confirmed; {name} is notified.", { name: otherParty }) : t("The new time goes back to {name} to confirm.", { name: otherParty })}</p>{body}<div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || loading || (!staff && !selectedSlot)} aria-busy={saving}>{saving ? t("Sending…") : staff ? t("Move meeting") : t("Propose new time")}</button></div></form></Modal>;
}

export function MeetingNoteForm({ booking, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [earlier, setEarlier] = useState([]);
  // The meeting's local calendar day; the ISO string is UTC and can be a day off.
  // A bare YYYY-MM-DD is already a local day (new Date() would read it as UTC).
  const meetingDate = /^\d{4}-\d{2}-\d{2}$/.test(booking.starts_at) ? booking.starts_at : meetingDay(booking.starts_at);
  // Opened from a meeting: show what was already written about that day, so "Notes" reads them back.
  useEffect(() => {
    if (!booking.id) return undefined;
    const controller = new AbortController();
    api.page('meetings', `?${new URLSearchParams({ student: booking.student, meeting_from: meetingDate, meeting_to: meetingDate, page_size: '20' })}`, controller.signal)
      .then((data) => setEarlier(data?.results || []))
      .catch((err) => { if (err?.name !== 'AbortError') notify(err.message, 'error'); });
    return () => controller.abort();
  }, [booking.id, booking.student, meetingDate, notify]);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.create('meetings', {
        student: booking.student,
        title: values.get('title'),
        meeting_date: meetingDate,
        summary: values.get('summary'),
        next_steps: values.get('next_steps'),
      });
      notify(t("Note saved."));
      onSaved();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("Meeting notes")} onClose={onClose}><form className="form-grid" onSubmit={submit}>{earlier.length > 0 && <section className="form-wide"><h3>{t("Notes from this day")}</h3><div className="record-list">{earlier.map((note) => <Record key={note.id} title={note.title} meta={joinParts(note.summary, note.next_steps && `${t("Next steps")}: ${note.next_steps}`)} />)}</div></section>}<Field label={t("Title")}><input name="title" required defaultValue={booking.topic} /></Field><Field label={t("Summary")}><textarea name="summary" required placeholder={t("What did you cover?")} /></Field><Field label={t("Next steps")}><textarea name="next_steps" placeholder={t("Optional")} /></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : t("Save note")}</button></div></form></Modal>;
}

// A student connects Telegram once with one tap: the site opens a one-time bot link, the student presses
// Start there, and from then on the meeting answers and reminders arrive in that chat. Without it they
// still see and manage the meetings they have; only a new request needs it (as the API does).
const needsTelegram = (user) => user.role === 'student' && Boolean(user.telegram?.enabled) && !user.telegram?.linked;

function TelegramConnectDialog({ onLinked, onClose, notify }) {
  // idle -> starting (asking for the link) -> waiting (Start not pressed yet) -> expired | error
  const [phase, setPhase] = useState('idle');
  const [link, setLink] = useState('');
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState('');
  const dialogRef = useRef(null);
  const watchRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const callbacks = useRef({});
  callbacks.current = { onLinked, notify };
  useEffect(() => () => watchRef.current?.stop(), []);
  async function connect() {
    if (phase === 'starting') return;
    // Opened now, in the click itself, and pointed at the link once the server has made it.
    const win = openBlankWindow();
    watchRef.current?.stop();
    setPhase('starting');
    setError('');
    setBlocked(false);
    try {
      const { url, expires_in: expiresIn } = await api.startTelegramLink();
      setLink(url);
      setBlocked(!navigateWindow(win, url));
      const watch = createLinkWatch({
        check: () => api.telegramStatus(),
        ttlMs: (Number(expiresIn) || 900) * 1000,
        onLinked: (telegram) => {
          callbacks.current.notify(t("Telegram connected"));
          callbacks.current.onLinked(telegram);
          onCloseRef.current();
        },
        onExpired: () => setPhase('expired'),
      });
      watchRef.current = watch;
      watch.start();
      setPhase('waiting');
    } catch (err) {
      closeWindow(win);
      setError(err.message);
      setPhase('error');
    }
  }
  useEffect(() => {
    const previous = document.activeElement;
    dialogRef.current?.querySelector('button, a[href]')?.focus();
    function handleKeyDown(event) {
      if (event.key === 'Escape') {event.preventDefault();onCloseRef.current();return;}
      if (event.key !== 'Tab') return;
      const items = [...(dialogRef.current?.querySelectorAll('a[href], button:not(:disabled)') || [])];
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {event.preventDefault();last.focus();} else
      if (!event.shiftKey && document.activeElement === last) {event.preventDefault();first.focus();}
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => {document.removeEventListener('keydown', handleKeyDown);previous?.focus?.();};
  }, []);
  const waiting = phase === 'waiting';
  return <div className="telegram-dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section ref={dialogRef} className="telegram-dialog" role="dialog" aria-modal="true" aria-labelledby="telegram-dialog-title" tabIndex="-1">
      <span className="telegram-dialog-icon" aria-hidden="true"><Send size={26} /></span>
      <h2 id="telegram-dialog-title">{t("Connect your Telegram")}</h2>
      <p className="telegram-dialog-lead">{t("Meeting confirmations and reminders will come to your Telegram.")}</p>
      {waiting ? <div className="telegram-dialog-waiting" role="status">
        <span className="telegram-dialog-spinner" aria-hidden="true" />
        <b>{t("Press Start in Telegram…")}</b>
        {blocked && <p className="telegram-dialog-hint">{t("Your browser blocked the new tab. Use the link below.")}</p>}
        <a className="telegram-dialog-again" href={link} target="_blank" rel="noopener noreferrer">{t("Open Telegram again")}</a>
      </div> : <>
        <BlueButton className="telegram-dialog-login" icon={Send} onClick={connect} disabled={phase === 'starting'} aria-busy={phase === 'starting'}>{phase === 'starting' ? t("Connecting…") : t("Connect Telegram")}</BlueButton>
        {phase === 'idle' && <p className="telegram-dialog-hint">{t("We open the bot for you. Just press Start there.")}</p>}
        {phase === 'expired' && <p className="telegram-dialog-error" role="alert">{t("Link expired, try again")}</p>}
        {phase === 'error' && <p className="telegram-dialog-error" role="alert">{error}</p>}
      </>}
      <button type="button" className="telegram-dialog-later" onClick={onClose}>{t("Later")}</button>
    </section>
  </div>;
}

// Shown on the page while the dialog is closed and Telegram is still not connected.
function TelegramReminder({ onOpen }) {
  return <div className="telegram-reminder" role="status"><Send size={16} aria-hidden="true" /><span>{t("Connect Telegram to request meetings")}</span><BlueButton size="sm" onClick={onOpen}>{t("Connect")}</BlueButton></div>;
}

// The staff member's booking page as students see it, read-only: only what the student request path lets
// through (booking window, minimum notice, free times), with Confirm disabled.
function StudentPreview({ user, onClose, onEdit }) {
  const [slots, setSlots] = useState(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [selectedDate, setSelectedDate] = useState('');
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [zoneTick, setZoneTick] = useState(0);
  useZoneSync();
  useEffect(() => {
    let active = true;
    setError('');
    api.bookingAvailability(user.id, { asStudent: true }).then((items) => {
      if (!active) return;
      const next = [...(items || [])].sort(byStart);
      setSlots(next);
      setSelectedDate(next[0] ? meetingDay(next[0].starts_at) : '');
    }).catch((err) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [user.id, attempt]);
  function changeZone(id) {
    setMeetingZone(id);
    setSelectedDate(slots?.[0] ? meetingDay(slots[0].starts_at) : '');
    setSelectedSlot(null);
    setZoneTick((value) => value + 1);
  }
  const name = fullName(user) || user.username;
  return <Modal title={t("Select a Date & Time")} onClose={onClose} className="booking-scheduler-modal"><div className="booking-cal booking-preview">
    <aside className="booking-cal-side">
      <p className="booking-preview-banner" role="status"><Eye size={16} aria-hidden="true" /> <span><b>{t("Preview — students see this")}</b><small>{t("Only your free times inside the booking window and after the minimum notice. Nothing can be booked here.")}</small></span></p>
      <small className="booking-cal-role">{joinParts(label(user.role), user.position)}</small>
      <h3 className="booking-cal-host">{name}</h3>
      <ul className="booking-cal-meta">
        {slots?.[0] && <li><Clock3 size={18} aria-hidden="true" /> {slots[0].duration_minutes} {t("min")}</li>}
        <li><Globe size={18} aria-hidden="true" /> {timeZoneName()}</li>
      </ul>
    </aside>
    <section className="booking-cal-main">
      <h3>{t("Choose a date and time")}</h3>
      {error ? <InlineLoadError message={error} onRetry={() => setAttempt((value) => value + 1)} /> : !slots ? <p className="booking-cal-note">{t("Loading available times…")}</p> : !slots.length
        ? <p className="booking-cal-note" role="status">{t("Students see no available times right now.")} <button type="button" className="button light small" onClick={onEdit}>{t("Edit hours")}</button></p>
        : <SlotCalendar key={zoneTick} readOnly onZone={changeZone} slots={slots} selectedDate={selectedDate} onDate={(key) => { setSelectedDate(key); setSelectedSlot(null); }} selectedSlot={selectedSlot} onSlot={setSelectedSlot} onNext={() => {}} />}
    </section>
  </div></Modal>;
}

// A student's name as a link to their profile, opened in the app without a reload.
function StudentLink({ item }) {
  const name = item.student_name || t("Student");
  if (!item.student) return name;
  const path = studentProfilePath(item.student);
  const open = (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    window.history.pushState(null, '', path);
    window.dispatchEvent(new PopStateEvent('popstate'));
  };
  return <a className="meet-student-link" href={path} onClick={open} title={t("Open student profile")}>{name}</a>;
}

// "@username" linking to t.me, or "Telegram not linked".
function TelegramTag({ item }) {
  const url = telegramUrl(item.student_telegram_username);
  return url
    ? <a className="meet-tg" href={url} target="_blank" rel="noopener noreferrer">@{item.student_telegram_username}</a>
    : <span className="meet-tg is-none">{t("Telegram not linked")}</span>;
}

const statusWords = (booking) => (booking.status === 'approved' ? t('Confirmed') : booking.staff_requested ? t('Waiting for student') : t('Waiting for you'));

// "Your booking page": what students can book (window, notice, zone), a month calendar of free and booked
// times, and the link, preview and hours buttons. Free times come from the staff member's own slots
// (inside the window) and meetings from the page's bookings; the counts are the server's.
function BookingOverview({ user, bookings, notify, onEditHours, version, autoPreview = false }) {
  const [state, setState] = useState({ loading: true, error: '', settings: null, slots: [] });
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState('');
  const [viewMonth, setViewMonth] = useState(() => monthStart(new Date()));
  const [previewing, setPreviewing] = useState(autoPreview);
  const signature = bookings.map((item) => `${item.id}:${item.status}:${item.starts_at}`).join(',');
  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, loading: true, error: '' }));
    Promise.all([api.weeklyAvailability(), api.bookingAvailability()]).then(([settings, slots]) => {
      if (active) setState({ loading: false, error: '', settings: settings || {}, slots: slots || [] });
    }).catch((err) => { if (active) setState((current) => ({ ...current, loading: false, error: err.message })); });
    return () => { active = false; };
  }, [version, attempt, signature]);
  const { settings, slots } = state;
  const now = new Date();
  const days = useMemo(() => (settings ? overviewDays({ slots, bookings, settings, now: new Date(), dayOf: meetingDay, windowDayOf: (value) => dayKey(inServerZone(value, 'Asia/Tashkent')) }) : new Map()), [settings, slots, bookings]);
  const dayKeys = useMemo(() => [...days.keys()].sort(), [days]);
  // The first day with times, until the staff member picks another.
  const shownDay = days.has(selected) ? selected : dayKeys[0] || '';
  useEffect(() => { if (dayKeys[0] && !days.has(selected)) setViewMonth(monthStart(`${dayKeys[0]}T00:00`)); }, [dayKeys, days, selected]);
  const name = fullName(user) || user.username;
  const link = bookingLink(window.location.origin, user.id);
  async function copy() {
    notify((await copyText(link)) ? t("Link copied") : t("Copy this link: {link}", { link }));
  }
  const hasHours = Boolean(settings) && (Object.values(settings.hours || {}).some((ranges) => ranges.length) || slots.some((slot) => new Date(slot.starts_at) > now));
  const head = <header className="meet-overview-head">
    <span className="meet-overview-avatar" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>
    <span><b>{name}</b><small>{joinParts(label(user.role), user.position)}</small></span>
  </header>;
  let body;
  if (state.error && !settings) body = <InlineLoadError message={state.error} onRetry={() => setAttempt((value) => value + 1)} />;
  else if (!settings) body = <p className="booking-cal-note">{t("Loading available times…")}</p>;
  else if (!hasHours) body = <div className="meet-overview-empty">
    {head}
    <p>{t("Students can't book you yet. Set your available hours and share your booking link.")}</p>
    <button type="button" className="button primary" onClick={onEditHours}><Calendar size={16} aria-hidden="true" /> {t("Set your available hours")}</button>
  </div>;
  else {
    const windowText = settings.window_mode === 'range' && settings.window_start
      ? rangeText(settings.window_start, settings.window_end, monthShort)
      : tp('Next {n} day|Next {n} days', settings.window_days ?? 60, { n: settings.window_days ?? 60 });
    const notice = settings.min_notice_hours ?? 12;
    const day = days.get(shownDay) || { free: [], booked: [] };
    const times = [...day.free.map((slot) => ({ kind: 'free', item: slot })), ...day.booked.map((meeting) => ({ kind: 'booked', item: meeting }))].sort((x, y) => new Date(x.item.starts_at) - new Date(y.item.starts_at));
    body = <div className="meet-overview-grid">
      <div className="meet-overview-info">
        {head}
        <ul className="booking-cal-meta">
          <li><Clock3 size={18} aria-hidden="true" /> {settings.duration_minutes || 45} {t("min")}</li>
          <li><CalendarDays size={18} aria-hidden="true" /> {windowText}</li>
          <li><Clock3 size={18} aria-hidden="true" /> {tp('at least {n} hour notice|at least {n} hours notice', notice, { n: notice })}</li>
          <li><Globe size={18} aria-hidden="true" /> {timeZoneName()}</li>
        </ul>
        <p className="meet-overview-counts"><b>{t("{booked} booked · {free} free times", { booked: settings.upcoming_booked ?? 0, free: settings.free_slots ?? 0 })}</b></p>
        <div className="meet-overview-actions">
          <button type="button" className="button primary small" onClick={copy}><Link2 size={15} aria-hidden="true" /> {t("Copy booking link")}</button>
          <button type="button" className="button light small" onClick={() => setPreviewing(true)}><Eye size={15} aria-hidden="true" /> {t("Preview as student")}</button>
          <button type="button" className="button light small" onClick={onEditHours}><Pencil size={15} aria-hidden="true" /> {t("Edit hours")}</button>
        </div>
      </div>
      <div className="meet-overview-cal">
        <MonthGrid month={viewMonth} onMonth={setViewMonth} canBack={viewMonth > monthStart(new Date())} canForward={Boolean(dayKeys.at(-1)) && monthStart(`${dayKeys.at(-1)}T00:00`) > viewMonth} marked={new Set(dayKeys)} canPick={(key) => days.has(key)} selected={shownDay} onPick={setSelected} label={t("Days with times")} />
        {shownDay ? <div className="meet-overview-day" role="group" aria-label={t("Times on {day}", { day: dayTitle(shownDay) })}>
          <b>{dayTitle(shownDay)}</b>
          <div className="meet-overview-chips">{times.map(({ kind, item }) => kind === 'free'
            ? <span key={`s${item.id}`} className="meet-chip is-free" title={t("Free time")}>{clockText(item.starts_at)}</span>
            : <span key={`b${item.id}`} className={`meet-chip is-booked${item.status === 'pending' ? ' is-waiting' : ''}`}><b>{clockText(item.starts_at)}</b> <StudentLink item={item} /> <TelegramTag item={item} /><small>{statusWords(item)}</small></span>)}</div>
        </div> : <p className="booking-cal-note">{t("No free times or meetings coming up.")}</p>}
      </div>
    </div>;
  }
  return <section className="meet-overview" aria-label={t("Your booking page")}>
    <h2 className="meet-overview-title">{t("Your booking page")}</h2>
    {body}
    {previewing && <StudentPreview user={user} onClose={() => setPreviewing(false)} onEdit={() => { setPreviewing(false); onEditHours(); }} />}
  </section>;
}

export function BookingsPage({ user, data, reload, notify, updateUser, setPage, resourceStatus, retryResources }) {
  const [zoneId, setZoneId] = useState(zone.id);
  const changeZone = (id) => { setMeetingZone(id); setZoneId(id); };
  // A dialog's own zone picker changed the zone: redraw once it has closed.
  useEffect(() => {
    const sync = () => setZoneId(zone.id);
    window.addEventListener(ZONE_EVENT, sync);
    return () => window.removeEventListener(ZONE_EVENT, sync);
  }, []);
  const picker = <ZonePicker value={zoneId} onChange={changeZone} />;
  // The link can end on the server (the bot was blocked), so the page asks again instead of trusting
  // the status loaded with the account; a changed answer brings the dialog back.
  const checkTelegram = user.role === 'student' && Boolean(user.telegram?.enabled);
  useEffect(() => {
    if (!checkTelegram) return undefined;
    let live = true;
    api.telegramStatus().then((telegram) => { if (live) updateUser?.({ telegram }); }).catch(() => {});
    return () => { live = false; };
  }, [checkTelegram, updateUser]);
  const locked = needsTelegram(user);
  const [telegramOpen, setTelegramOpen] = useState(locked);
  useEffect(() => { if (locked) setTelegramOpen(true); }, [locked]);
  // A button that starts something new opens the Telegram dialog while Telegram is not connected.
  const showDialog = () => setTelegramOpen(true);
  const guard = (start) => (locked ? showDialog : start);
  const banner = locked ? (telegramOpen
    ? <TelegramConnectDialog notify={notify} onClose={() => setTelegramOpen(false)} onLinked={(telegram) => updateUser?.({ telegram })} />
    : <TelegramReminder onOpen={showDialog} />) : null;
  // A shared booking link (/meetings?book=<staff id>) is read once, then dropped from the address bar.
  const [bookId] = useState(() => bookParam(window.location.search));
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has('book')) {
      window.history.replaceState(window.history.state, '', `${window.location.pathname}${withQuery(window.location.search, { book: null })}${window.location.hash}`);
    }
  }, []);
  const props = { user, data, reload, notify, guard, banner, picker, bookId, locked, setPage, resourceStatus, retryResources };
  // key: a new zone redraws every time on the page.
  if (user.role === 'student') return <StudentBookingsPage key={zoneId} {...props} />;
  if (usesCounselorLayout(user)) return <CounselorMeetingsPage key={zoneId} {...props} />;
  return <StaffMeetingsPage key={zoneId} {...props} />;
}

const statusChip = (status) => ({ confirmed: 'ok', completed: 'ok', pending: 'warn', cancelled: 'overdue', rejected: 'overdue', expired_unconfirmed: 'overdue' }[status] || 'default');

// "My Naseeb team" (counselor, school contact): the same list the dashboard shows. The workspace loader
// fetches it with this page (data.team), so loading and error come from its resource status.
function useStudentTeam(data, resourceStatus, retryResources) {
  const state = resourceDisplayState(resourceStatus?.team);
  return {
    items: Array.isArray(data.team) ? data.team : [],
    loading: state === 'loading',
    error: state === 'error' ? resourceStatus.team.error : '',
    retry: () => retryResources?.(['team']),
  };
}

function StudentBookingsPage({ data, reload, notify, guard, banner, picker, bookId, locked, setPage, resourceStatus, retryResources }) {
  const [tab, setTab] = useState('upcoming');
  const [open, setOpen] = useState(false);
  // The staff member a shared link names, until the dialog closes (then Request meeting opens it as usual).
  const [linked, setLinked] = useState(bookId);
  // A booking link opens the picker for that person; while Telegram is not connected the dialog shows first,
  // and the picker follows as soon as the link is confirmed.
  useEffect(() => { if (bookId && !locked) setOpen(true); }, [bookId, locked]);
  const [savingId, setSavingId] = useState(null);
  const [rescheduling, setRescheduling] = useState(null);
  const teamRef = useRef(null);
  const team = useStudentTeam(data, resourceStatus, retryResources);
  const [openingId, setOpeningId] = useState(null);
  // A direct chat with a team member: open (or find) it, then land on it in Messages by its id.
  async function messageMember(member) {
    if (openingId) return;
    setOpeningId(member.id);
    try {
      const channel = await api.openDirectChannel(member.id);
      setPage('messages', { channelId: channel.id });
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      // Navigation may not happen (page changed elsewhere, request failed): never leave the buttons disabled.
      setOpeningId(null);
    }
  }
  const now = new Date();
  const upcoming = studentMeetingsForTab(data.bookings, 'upcoming', now);
  const past = studentMeetingsForTab(data.bookings, 'history', now);
  const items = tab === 'upcoming' ? upcoming : past;
  // Minutes spent in meetings that took place (confirmed and past, or marked completed).
  const minutes = past.reduce((total, item) => (['completed', 'past_unmarked'].includes(meetingStatus(item, now, { student: true })) ? total + (Number(item.duration_minutes) || 0) : total), 0);
  const tabs = [{ key: 'upcoming', label: t('Upcoming') }, { key: 'history', label: t('Past'), count: past.length }];
  async function transition(item, action) {
    if (action === 'cancel' && !window.confirm(t("Cancel this meeting?"))) return;
    if (action === 'reject' && !window.confirm(t("Decline this meeting?"))) return;
    setSavingId(item.id);
    try {
      const methods = { cancel: api.cancelBooking, approve: api.approveBooking, reject: api.rejectBooking };
      await methods[action](item.id);
      notify({ cancel: t("Meeting cancelled."), approve: t("Meeting confirmed."), reject: t("Meeting declined.") }[action]);
      reload();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSavingId(null);
    }
  }
  const requestButton = <BlueButton icon={Plus} onClick={guard(() => setOpen(true))}>{t("Request meeting")}</BlueButton>;
  return <div className="nb-meet student-portal">
    <PageHeader title={t("Meetings")} subtitle={t("Schedule and manage meetings")} actions={requestButton} />
    {banner}
    <KpiRow label={t("Meetings summary")}>
      <KpiTile tone={0} icon={CalendarClock} value={upcoming.length} label={t("Upcoming")} onClick={() => setTab('upcoming')} actionLabel={tx`Upcoming · ${upcoming.length}`} />
      <KpiTile tone={1} icon={History} value={past.length} label={t("Past meetings")} onClick={() => setTab('history')} actionLabel={tx`Past meetings · ${past.length}`} />
      <KpiTile tone={2} icon={Timer} value={minutes} unit={t("min")} label={t("Minutes in meetings")} />
      <KpiTile tone={3} icon={UsersRound} value={team.items.length} loading={team.loading} label={t("My Naseeb team")} onClick={() => teamRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })} actionLabel={t("My Naseeb team")} />
    </KpiRow>
    <div className="nb-meet-bar">
      <PillTabs tabs={tabs} value={tab} onChange={setTab} label={t("Meetings")} idPrefix="nb-meet" />
      <div className="nb-meet-zone">{picker}<p className="booking-cal-zone"><Globe size={15} aria-hidden="true" /> {timeZoneName()}</p></div>
    </div>
    <div className="nb-meet-grid">
      <GlassCard tone="solid" className="nb-meet-list" role="tabpanel" aria-labelledby={tabId('nb-meet', tab)}>
        {items.length ? <div className="nb-meet-rows">{items.map((item) => {
          const status = meetingBadgeStatus(meetingStatus(item, now, { student: true }));
          const isOpen = isOpenMeeting(item, now);
          const awaiting = isAwaitingStudent(item, now);
          return <article className={`nb-meet-row is-${awaiting ? 'awaiting-you' : status}`} key={item.id}>
            <DateTile day={zoned(item.starts_at).getDate()} month={formatDateLocale(zoned(item.starts_at), { month: 'short' })} hot={tab === 'upcoming'} />
            <div className="nb-meet-copy">
              <h3>{item.topic}</h3>
              <p><Clock3 size={15} aria-hidden="true" /> {joinParts(dateTimeText(item.starts_at), item.duration_minutes > 0 && tx`${item.duration_minutes} min`)}</p>
              <small>{joinParts(t("Meeting with {name}", { name: item.participant_name || t("Meeting participant") }), item.participant_role && label(item.participant_role))}</small>
              {item.notes && <p className="nb-meet-notes">{item.notes}</p>}
            </div>
            <div className="nb-meet-side">
              <Chip variant={awaiting ? 'warn' : statusChip(status)}>{awaiting ? t("Waiting for your confirmation") : label(status)}</Chip>
              <div className="nb-meet-actions">
                {awaiting && <>
                  <BlueButton size="sm" icon={Check} disabled={savingId === item.id} aria-busy={savingId === item.id} onClick={() => transition(item, 'approve')}>{t("Confirm")}</BlueButton>
                  <BlueButton variant="ghost" size="sm" icon={X} disabled={savingId === item.id} onClick={() => transition(item, 'reject')}>{t("Decline")}</BlueButton>
                </>}
                {isOpen ? <>
                  <BlueButton variant="ghost" size="sm" icon={CalendarClock} disabled={savingId === item.id} onClick={() => setRescheduling(item)}>{t("Reschedule")}</BlueButton>
                  <BlueButton variant="ghost" size="sm" icon={Ban} disabled={savingId === item.id} onClick={() => transition(item, 'cancel')}>{t("Cancel meeting")}</BlueButton>
                </> : <BlueButton variant="ghost" size="sm" icon={Trash2} disabled={savingId === item.id} onClick={() => deleteMeeting(item, { setSavingId, reload, notify, question: t("Delete this meeting? It disappears for your counselor too.") })}>{t("Delete")}</BlueButton>}
              </div>
            </div>
          </article>;
        })}</div> : <EmptyState icon={CalendarClock} title={tab === 'upcoming' ? t("No upcoming meetings.") : t("No past meetings yet.")} text={tab === 'upcoming' ? t("Make time for your next step.") : undefined} action={tab === 'upcoming' ? requestButton : undefined} />}
      </GlassCard>
      <GlassCard tone="solid" className="nb-meet-team" title={t("My Naseeb team")} icon={UsersRound} ref={teamRef}>
        {team.loading ? <p className="nb-meet-note" role="status">{t("Loading…")}</p> : team.error ? <InlineLoadError message={team.error} onRetry={team.retry} /> : team.items.length ? <ul className="nb-meet-people">{team.items.map((member) => <li key={`${member.kind}-${member.id}`}>
          <Avatar name={member.name} size={44} />
          <span><b>{member.name}</b><small>{t(member.role)}</small></span>
          {setPage && <button type="button" className="nb-meet-msg" disabled={Boolean(openingId)} onClick={() => messageMember(member)} aria-label={tx`Message ${member.name}`} title={t("Message")}><MessageCircle size={18} aria-hidden="true" /></button>}
        </li>)}</ul> : <p className="nb-meet-note">{t("No team members have been assigned yet.")}</p>}
      </GlassCard>
    </div>
    {open && <BookingForm initialParticipantId={linked} onUnavailable={() => {setOpen(false);setLinked(null);notify(t("This booking link isn't available for your account."), 'error');}} onClose={() => {setOpen(false);setLinked(null);}} onSaved={() => {setOpen(false);setLinked(null);reload();}} notify={notify} />}
    {rescheduling && <RescheduleForm booking={rescheduling} onClose={() => setRescheduling(null)} onSaved={() => {setRescheduling(null);reload();}} notify={notify} />}
  </div>;
}

const meetingTone = (status) => ({ confirmed: 'ok', pending: 'warn' }[status] || 'quiet');
const clockAndLength = (item) => joinParts(clockText(item.starts_at), item.duration_minutes > 0 && tx`${item.duration_minutes} min`, viewerTimeHint(item.starts_at));

// "Requests, today and this week" in the Counselor Dashboard design: requests
// waiting for a decision on the left, the week's meetings on the right.
// Staff clear a closed or past meeting off their list (the API refuses an upcoming open one).
async function deleteMeeting(item, { setSavingId, reload, notify, question = t("Delete this meeting? It disappears for the student too.") }) {
  if (!window.confirm(question)) return;
  setSavingId(item.id);
  try {
    await api.remove('bookings', item.id);
    notify(t("Meeting deleted."));
    reload();
  } catch (err) {
    notify(err.message, 'error');
  } finally {
    setSavingId(null);
  }
}

// "5 booked · 2 cancelled this week", then how many meetings each day has.
function WeekSummary({ items }) {
  if (!items.length) return null;
  const { booked, cancelled } = weekCounts(items);
  const today = meetingDay();
  const tomorrow = dayKey(new Date(`${today}T00:00`).getTime() + 86400000);
  const dayName = (key) => (key === today ? t('Today') : key === tomorrow ? t('Tomorrow') : formatDateLocale(new Date(`${key}T00:00`), { weekday: 'short', day: 'numeric', month: 'short' }));
  const perDay = bookedPerDay(items, meetingDay);
  return <p className="week-summary">
    <b>{t("{booked} booked · {cancelled} cancelled this week", { booked, cancelled })}</b>
    {perDay.length > 0 && <small>{perDay.map(([key, count]) => `${dayName(key)}: ${count}`).join(' · ')}</small>}
  </p>;
}

function CounselorMeetingsPage({ user, data, reload, notify, guard, banner, picker, bookId }) {
  const [savingId, setSavingId] = useState(null);
  const [rescheduling, setRescheduling] = useState(null);
  const [addingNote, setAddingNote] = useState(null);
  const [booking, setBooking] = useState(null);
  const [availabilityOpen, setAvailabilityOpen] = useState(false);
  const [hoursVersion, setHoursVersion] = useState(0);
  const now = new Date();
  const pending = pendingMeetings(data.bookings, now);
  const week = meetingsThisWeek(data.bookings, now);

  async function transition(item, action) {
    if (action === 'reject' && !window.confirm(t("Decline this meeting?"))) return;
    if (action === 'cancel' && !window.confirm(t("Cancel this meeting?"))) return;
    setSavingId(item.id);
    try {
      const methods = { approve: api.approveBooking, reject: api.rejectBooking, complete: api.completeBooking, cancel: api.cancelBooking };
      await methods[action](item.id);
      notify({ approve: t("Meeting confirmed."), reject: t("Meeting declined."), complete: t("Meeting marked as completed."), cancel: t("Meeting cancelled.") }[action]);
      reload();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSavingId(null);
    }
  }

  function scrollToPending(id) {
    document.querySelector(`[data-pending-id="${id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function weekActions(item) {
    const status = meetingStatus(item, now, { student: false });
    if (isAwaitingStudent(item, now)) return <>
      <button type="button" className="cx-btn" onClick={() => setRescheduling(item)}>{t("Move meeting")}</button>
      <button type="button" className="cx-btn" disabled={savingId === item.id} onClick={() => transition(item, 'cancel')}>{t("Cancel meeting")}</button>
    </>;
    if (status === 'pending') return <button type="button" className="cx-btn" onClick={() => scrollToPending(item.id)}>{t("Open")}</button>;
    if (needsRebook(item, now)) return <button type="button" className="cx-btn" onClick={guard(() => setBooking({ studentId: item.student, studentName: item.student_name, topic: item.topic }))}>{t("Rebook")}</button>;
    return <>
      {status === 'approved' && !isOpenMeeting(item, now) && <button type="button" className="cx-btn" disabled={savingId === item.id} onClick={() => transition(item, 'complete')}>{t("Mark completed")}</button>}
      {status === 'approved' && isOpenMeeting(item, now) && <button type="button" className="cx-btn" onClick={() => setRescheduling(item)}>{t("Move meeting")}</button>}
      {status === 'approved' && isOpenMeeting(item, now) && <button type="button" className="cx-btn" disabled={savingId === item.id} onClick={() => transition(item, 'cancel')}>{t("Cancel meeting")}</button>}
      <button type="button" className="cx-btn" onClick={() => setAddingNote(item)}>{t("Notes")}</button>
    </>;
  }

  return <div className="cx-page cx-meetings">
    <CxHead title={t("Meetings")} subtitle={joinParts(t("Requests, today and this week"), timeZoneName())}>
      {picker}
      <button type="button" className="cx-btn" onClick={guard(() => setAvailabilityOpen(true))}><Calendar size={15} aria-hidden="true" />{t("My available hours")}</button>
      <button type="button" className="cx-btn primary" onClick={guard(() => setBooking({}))}><Plus size={15} aria-hidden="true" />{t("Book with a student")}</button>
    </CxHead>
    {banner}
    {ownsMeetingHours(user) && <BookingOverview user={user} bookings={data.bookings} notify={notify} version={hoursVersion} autoPreview={bookId === user.id} onEditHours={guard(() => setAvailabilityOpen(true))} />}
    {pending.length || week.length ? <div className={`cx-meet-grid${pending.length && week.length ? '' : ' is-single'}`}>
      {pending.length > 0 && <CxCard title={tx`Requests waiting for you · ${pending.length}`}>
        <div className="cx-requests">
          {pending.map((item) => <article key={item.id} data-pending-id={item.id} className="cx-request">
            <div className="cx-request-head">
              <CxAvatar name={item.student_name} />
              <span className="cx-row-copy">
                <b><StudentLink item={item} />{item.topic ? ` · ${item.topic}` : ''}</b>
                <small><TelegramTag item={item} /></small>
                <small>{joinParts(
                  `${dayLabel(item.starts_at)} ${clockText(item.starts_at)}`,
                  item.duration_minutes > 0 && tx`${item.duration_minutes} min`,
                  viewerTimeHint(item.starts_at),
                  item.previous_starts_at ? t('rescheduled from {when}', { when: `${dayLabel(item.previous_starts_at)} ${clockText(item.previous_starts_at)}` }) : item.created_at && t('requested {when}', { when: relativeDayText(item.created_at).toLowerCase() }),
                )}</small>
              </span>
              <CxTag tone="warn">{label(meetingBadgeStatus(item.status))}</CxTag>
            </div>
            <div className="cx-request-actions">
              <button type="button" className="cx-btn" disabled={savingId === item.id} onClick={() => transition(item, 'reject')}>{t("Decline")}</button>
              <button type="button" className="cx-btn" disabled={savingId === item.id} onClick={() => setRescheduling(item)}>{t("Move meeting")}</button>
              <button type="button" className="cx-btn primary" disabled={savingId === item.id} aria-busy={savingId === item.id} onClick={() => transition(item, 'approve')}>{t("Accept")}</button>
            </div>
          </article>)}
        </div>
      </CxCard>}
      {week.length > 0 && <CxCard title={t("This week")}>
        <WeekSummary items={week} />
        <div className="cx-week">
          {week.map((item) => {
            const status = meetingBadgeStatus(meetingStatus(item, now, { student: false }));
            return <div key={item.id} className={`cx-week-row${item.status === 'cancelled' ? ' is-cancelled' : ''}`}>
              <span className="cx-week-when"><b>{dayLabel(item.starts_at)}</b><small>{clockAndLength(item)}</small></span>
              <span className="cx-row-copy"><b><StudentLink item={item} /></b><small>{item.topic} · <TelegramTag item={item} /></small></span>
              <CxTag tone={meetingTone(status)}>{isAwaitingStudent(item, now) ? t("Waiting for student") : cancelledByStudent(item) ? t("Cancelled by student") : label(status)}</CxTag>
              <span className="cx-week-actions">{weekActions(item)}{!isOpenMeeting(item, now) && <button type="button" className="cx-btn" disabled={savingId === item.id} aria-label={tx`Delete ${item.topic}`} onClick={() => deleteMeeting(item, { setSavingId, reload, notify })}><Trash2 size={15} aria-hidden="true" />{t("Delete")}</button>}</span>
            </div>;
          })}
        </div>
      </CxCard>}
    </div> : <CxCard title={t("This week")}><p className="cx-empty">{t("No requests waiting and nothing scheduled this week.")}</p></CxCard>}
    {rescheduling && <RescheduleForm booking={rescheduling} staff onClose={() => setRescheduling(null)} onSaved={() => {setRescheduling(null);reload();}} notify={notify} />}
    {addingNote && <MeetingNoteForm booking={addingNote} onClose={() => setAddingNote(null)} onSaved={() => setAddingNote(null)} notify={notify} />}
    {booking && <BookingForm staff defaultStudentId={booking.studentId} defaultStudentName={booking.studentName} defaultTopic={booking.topic} onClose={() => setBooking(null)} onSaved={() => {setBooking(null);reload();}} notify={notify} />}
    {availabilityOpen && <AvailabilityManager onClose={() => {setAvailabilityOpen(false);setHoursVersion((value) => value + 1);}} notify={notify} />}
  </div>;
}

// "Requests, today and this week" (product vision S3.4): the SLA-facing view
// of a counselor's meetings, oldest request first. See lib/meetings.js for
// the pending/this-week/rebook rules.
function StaffMeetingsPage({ user, data, reload, notify, guard, banner, picker, bookId }) {
  const [savingId, setSavingId] = useState(null);
  const [rescheduling, setRescheduling] = useState(null);
  const [addingNote, setAddingNote] = useState(null);
  const [booking, setBooking] = useState(null);
  const [availabilityOpen, setAvailabilityOpen] = useState(false);
  const [hoursVersion, setHoursVersion] = useState(0);
  const now = new Date();
  const pending = pendingMeetings(data.bookings, now);
  const thisWeek = meetingsThisWeek(data.bookings, now);

  async function transition(item, action) {
    if (action === 'reject' && !window.confirm(t("Decline this meeting?"))) return;
    if (action === 'cancel' && !window.confirm(t("Cancel this meeting?"))) return;
    setSavingId(item.id);
    try {
      const methods = { approve: api.approveBooking, reject: api.rejectBooking, complete: api.completeBooking, cancel: api.cancelBooking };
      await methods[action](item.id);
      notify({ approve: t("Meeting confirmed."), reject: t("Meeting declined."), complete: t("Meeting marked as completed."), cancel: t("Meeting cancelled.") }[action]);
      reload();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSavingId(null);
    }
  }

  function scrollToPending(id) {
    document.querySelector(`[data-pending-id="${id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function weekActions(item) {
    const status = meetingStatus(item, now, { student: false });
    if (isAwaitingStudent(item, now)) return <>
      <button type="button" className="button quiet small" onClick={() => setRescheduling(item)}><CalendarClock size={14} /> {t("Move meeting")}</button>
      <button type="button" className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'cancel')}><Ban size={14} /> {t("Cancel meeting")}</button>
    </>;
    if (status === 'pending') return <button type="button" className="button quiet small" onClick={() => scrollToPending(item.id)}>{t("Open")}</button>;
    if (needsRebook(item, now)) return <button type="button" className="button quiet small" onClick={guard(() => setBooking({ studentId: item.student, studentName: item.student_name, topic: item.topic }))}><CalendarClock size={14} /> {t("Rebook")}</button>;
    return <>
      <button type="button" className="button quiet small" onClick={() => setAddingNote(item)}>{t("Notes")}</button>
      {status === 'approved' && !isOpenMeeting(item, now) && <button type="button" className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'complete')}><CheckCircle2 size={14} /> {t("Mark completed")}</button>}
      {status === 'approved' && isOpenMeeting(item, now) && <button type="button" className="button quiet small" onClick={() => setRescheduling(item)}><CalendarClock size={14} /> {t("Move meeting")}</button>}
      {status === 'approved' && isOpenMeeting(item, now) && <button type="button" className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'cancel')}><Ban size={14} /> {t("Cancel meeting")}</button>}
    </>;
  }

  return <div className="section-stack meetings-staff">
    {banner}<div className="portal-toolbar"><h2>{t("Meetings")}</h2><div className="booking-toolbar-actions">{picker}<button className="button secondary" onClick={guard(() => setAvailabilityOpen(true))}><Calendar size={17} /> {t("My available hours")}</button><button className="button primary" onClick={guard(() => setBooking({}))}><Plus size={17} /> {t("Book with a student")}</button></div></div>
    <p className="booking-cal-zone"><Globe size={15} aria-hidden="true" /> {timeZoneName()}</p>
    {ownsMeetingHours(user) && <BookingOverview user={user} bookings={data.bookings} notify={notify} version={hoursVersion} autoPreview={bookId === user.id} onEditHours={guard(() => setAvailabilityOpen(true))} />}
    <div className="split-grid wide-left">
      <Panel title={tx`Requests waiting for you · ${pending.length}`}>
        <div className="record-list">
          {pending.map((item) => <div key={item.id} data-pending-id={item.id}><Record
            title={<><StudentLink item={item} />{item.topic ? ` · ${item.topic}` : ''}</>}
            meta={<><TelegramTag item={item} /> · {joinParts(dateTimeText(item.starts_at), item.duration_minutes > 0 && tx`${item.duration_minutes} min`, item.created_at && tx`requested ${relativeDayText(item.created_at).toLowerCase()}`)}</>}
            badge={meetingBadgeStatus(item.status)}
            actions={<div className="booking-actions">
              <button type="button" className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'reject')}><X size={14} /> {t("Decline")}</button>
              <button type="button" className="button quiet small" disabled={savingId === item.id} onClick={() => setRescheduling(item)}><CalendarClock size={14} /> {t("Move meeting")}</button>
              <button type="button" className="button primary small" disabled={savingId === item.id} onClick={() => transition(item, 'approve')}><Check size={14} /> {t("Accept")}</button>
            </div>}
          /></div>)}
          {!pending.length && <Empty text={t("No requests waiting for you.")} />}
        </div>
      </Panel>
      <Panel title={t("This week")}>
        <WeekSummary items={thisWeek} />
        <div className="record-list">
          {thisWeek.map((item) => <Record key={item.id} className={item.status === 'cancelled' ? 'is-cancelled' : undefined} title={joinParts(dateTimeText(item.starts_at), item.topic)} meta={<><StudentLink item={item} /> <TelegramTag item={item} />{' · '}{joinParts(cancelledByStudent(item) && t("Cancelled by student"), viewerTimeHint(item.starts_at))}</>} badge={isAwaitingStudent(item, now) ? 'waiting_for_student' : meetingBadgeStatus(meetingStatus(item, now, { student: false }))} actions={<>{weekActions(item)}{!isOpenMeeting(item, now) && <button type="button" className="button quiet small" disabled={savingId === item.id} aria-label={tx`Delete ${item.topic}`} title={t("Delete")} onClick={() => deleteMeeting(item, { setSavingId, reload, notify })}><Trash2 size={14} aria-hidden="true" /> {t("Delete")}</button>}</>} />)}
          {!thisWeek.length && <Empty text={t("Nothing scheduled this week.")} />}
        </div>
      </Panel>
    </div>
    {rescheduling && <RescheduleForm booking={rescheduling} staff onClose={() => setRescheduling(null)} onSaved={() => {setRescheduling(null);reload();}} notify={notify} />}
    {addingNote && <MeetingNoteForm booking={addingNote} onClose={() => setAddingNote(null)} onSaved={() => setAddingNote(null)} notify={notify} />}
    {booking && <BookingForm staff defaultStudentId={booking.studentId} defaultStudentName={booking.studentName} defaultTopic={booking.topic} onClose={() => setBooking(null)} onSaved={() => {setBooking(null);reload();}} notify={notify} />}
    {availabilityOpen && <AvailabilityManager onClose={() => {setAvailabilityOpen(false);setHoursVersion((value) => value + 1);}} notify={notify} />}
  </div>;
}
