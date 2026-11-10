import { useState, useEffect, useMemo, useRef } from 'react';
import { api, request } from '../api';
import { t, tx, locale, formatDateLocale } from '../i18n';
import { Modal, Badge, Empty, Panel } from '../components/ui';
import { Field, PortalTabs } from '../components/forms';
import { fullName, label } from '../lib/labels';
import { Record } from '../components/records';
import { Plus, Clock3, Check, X, CheckCircle2, CalendarClock, Calendar, CalendarDays, Ban, ArrowLeft, ChevronLeft, ChevronRight, Globe, Trash2, Pencil } from 'lucide-react';
import { clockText as viewerClockText, dateTimeText as viewerDateTimeText, dayLabel as viewerDayLabel, joinParts, relativeDayText } from '../lib/format';
import { inServerZone } from '../lib/serverTime';
import { usesCounselorLayout } from '../lib/roles';
import { CxAvatar, CxCard, CxHead, CxTag } from '../components/counselorUi';
import { isOpenMeeting, meetingStatus, meetingBadgeStatus, studentMeetingsForTab, pendingMeetings, meetingsThisWeek, needsRebook } from '../lib/meetings';
import { StudentSearchInput } from '../components/StudentSearchInput';
import './bookings-scheduler.css';
import { InlineLoadError } from '../components/states';

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
const zoned = (value) => inServerZone(value, zone.id);
const clockText = (value) => viewerClockText(zoned(value));
const dateTimeText = (value) => viewerDateTimeText(zoned(value));
const dayLabel = (value) => viewerDayLabel(zoned(value));
const viewerElsewhere = () => -new Date().getTimezoneOffset() !== zone.minutes;
// "27 Oct, 01:00 your time" when the viewer's clock differs from the chosen zone, else nothing.
const viewerTimeHint = (value) => (viewerElsewhere() ? t('{time} your time', { time: viewerDateTimeText(value) }) : '');
// A wall-clock "YYYY-MM-DDTHH:MM" in the chosen zone (a datetime-local value) as an instant.
const fromZone = (local) => new Date(`${local}:00${zone.offset}`);
// A Tashkent "HH:MM" (weekly hours are kept on Tashkent's clock) on the chosen zone's clock.
function fromTashkentClock(value) {
  const minutes = Number(value.slice(0, 2)) * 60 + Number(value.slice(3, 5)) + zone.minutes - 300;
  const day = Math.floor(minutes / 1440);
  const wrapped = ((minutes % 1440) + 1440) % 1440;
  const text = `${String(Math.floor(wrapped / 60)).padStart(2, '0')}:${String(wrapped % 60).padStart(2, '0')}`;
  return day > 0 ? `${text} (+1)` : text;
}

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
function MonthGrid({ month, onMonth, canBack, canForward, marked, canPick, selected, onPick, label }) {
  const today = meetingDay();
  const offset = (month.getDay() + 6) % 7;
  const length = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const days = Array.from({ length }, (_, index) => new Date(month.getFullYear(), month.getMonth(), index + 1));
  const weekdays = WEEKDAYS.map((name, index) => (uzbek() ? t(name).slice(0, 2) : formatDateLocale(new Date(2024, 0, 1 + index), { weekday: 'short' })));
  const shift = (step) => onMonth(new Date(month.getFullYear(), month.getMonth() + step, 1));
  return <div className="booking-cal-month">
    <header>
      <button type="button" className="booking-cal-nav" disabled={!canBack} onClick={() => shift(-1)} aria-label={t("Previous month")}><ChevronLeft size={20} /></button>
      <b aria-live="polite">{formatDateLocale(month, { month: 'long', year: 'numeric' })}</b>
      <button type="button" className="booking-cal-nav" disabled={!canForward} onClick={() => shift(1)} aria-label={t("Next month")}><ChevronRight size={20} /></button>
    </header>
    <div className="booking-cal-days" role="group" aria-label={label}>
      {weekdays.map((name) => <span key={name} className="booking-cal-weekday" aria-hidden="true">{name}</span>)}
      {days.map((date, index) => {
        const key = dayKey(date);
        return <button key={key} type="button" style={index === 0 ? { gridColumnStart: offset + 1 } : undefined} className={`booking-cal-day ${marked.has(key) ? 'is-open' : ''} ${key === today ? 'is-today' : ''}`.trim()} disabled={!canPick(key)} aria-pressed={selected === key} aria-label={dayTitle(key)} onClick={() => onPick(key)}>{date.getDate()}</button>;
      })}
    </div>
  </div>;
}

// Month view of one person's open slots: available days are tinted, the chosen
// day lists its times, and choosing a time reveals "Next" beside it.
function SlotCalendar({ slots, selectedDate, onDate, selectedSlot, onSlot, onNext }) {
  const openDays = new Set(slots.filter((slot) => slot.available).map((slot) => meetingDay(slot.starts_at)));
  const firstOpen = [...openDays].sort()[0];
  const lastOpen = [...openDays].sort().at(-1);
  const [viewMonth, setViewMonth] = useState(() => monthStart(firstOpen ? `${firstOpen}T00:00` : new Date()));
  const daySlots = slots.filter((slot) => meetingDay(slot.starts_at) === selectedDate);
  return <div className={`booking-cal-picker ${selectedDate ? 'has-day' : ''}`.trim()}>
    <div>
      <MonthGrid month={viewMonth} onMonth={setViewMonth} canBack={viewMonth > monthStart(new Date())} canForward={Boolean(lastOpen) && monthStart(`${lastOpen}T00:00`) > viewMonth} marked={openDays} canPick={(key) => openDays.has(key)} selected={selectedDate} onPick={onDate} label={t("Available dates")} />
      <p className="booking-cal-zone"><Globe size={15} aria-hidden="true" /> {timeZoneName()}</p>
    </div>
    {selectedDate && <div className="booking-cal-times" role="group" aria-label={t("Available times")}>
      <b>{dayTitle(selectedDate)}</b>
      {daySlots.map((slot) => selectedSlot?.id === slot.id
        ? <div key={slot.id} className="booking-cal-confirm"><span>{clockText(slot.starts_at)}</span><button type="button" onClick={onNext}>{t("Next")}</button></div>
        : <button key={slot.id} type="button" className="booking-cal-time" disabled={!slot.available} onClick={() => onSlot(slot)}>{clockText(slot.starts_at)}</button>)}
    </div>}
  </div>;
}

// Matches OVERVIEW_SLOTS_PER_PARTICIPANT in backend meetings.py.
const OVERVIEW_SLOTS = 20;

// `staff`: a counselor/teacher/org member booking with one of their students —
// they pick the student, not a participant (the API sets participant = them).
// `defaultStudentId`/`defaultTopic`: pre-fill for "Rebook" on an expired or declined request.
export function BookingForm({ staff = false, defaultStudentId = null, defaultStudentName = '', defaultTopic = '', onClose, onSaved, notify }) {
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
      const first = nextPeople.find((person) => firstFree(person.id)) || nextPeople[0];
      setParticipantId(String(first?.id || ''));
      const firstSlot = first && firstFree(first.id);
      if (firstSlot) setSelectedDate(meetingDay(firstSlot.starts_at));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {active = false;};
  }, [staff, peopleAttempt]);
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
        notes: values.get('notes')
      } : {
        participant: Number(participantId), availability_slot: selectedSlot.id,
        topic, starts_at: selectedSlot.starts_at, duration_minutes: selectedSlot.duration_minutes, notes
      });
      notify(staff ? t("Meeting confirmed.") : t("Meeting request sent for approval."));
      onSaved();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  if (staff) return <Modal title={t("Book a meeting")} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <StudentSearchInput name="student" required value={student} onChange={setStudent} /><Field label={t("Topic")}><input name="topic" required defaultValue={defaultTopic} placeholder={t("Essay review, university list...")} /></Field><Field label={t("Date & time")}><input name="starts_at" type="datetime-local" required /></Field><Field label={t("Duration")}><select name="duration_minutes" defaultValue="45"><option value="30">{t("30 min")}</option><option value="45">{t("45 min")}</option><option value="60">{t("60 min")}</option></select></Field><Field label={t("Notes")}><textarea name="notes" placeholder={t("What would you like to discuss?")} /></Field>
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
          : <SlotCalendar key={participantId} slots={personSlots} selectedDate={selectedDate} onDate={(key) => { setSelectedDate(key); setSelectedSlot(null); }} selectedSlot={selectedSlot} onSlot={setSelectedSlot} onNext={() => setStep('details')} />}
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

// Weekly hours, the way Calendly asks for them: one row per weekday with its
// from–to hours. The server turns them into the dated times students book.
function WeeklyHours({ notify, onSaved }) {
  const [hours, setHours] = useState(null);
  const [duration, setDuration] = useState(45);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setError('');
    api.weeklyAvailability().then((data) => {
      if (!active) return;
      setHours(data.hours || {});
      setDuration(data.duration_minutes || 45);
    }).catch((err) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [attempt]);
  const setDay = (day, ranges) => setHours((current) => ({ ...current, [day]: ranges }));
  const setTime = (day, index, side, value) => setDay(day, hours[day].map((range, at) => (at === index ? (side ? [range[0], value] : [value, range[1]]) : range)));
  async function save(event) {
    event.preventDefault();
    const days = Object.values(hours);
    if (days.some((ranges) => ranges.some(([from, to]) => !from || !to || to <= from))) { notify(t("Choose an end time after the start time."), 'error'); return; }
    if (days.some(rangesOverlap)) { notify(t("Hours on the same day cannot overlap."), 'error'); return; }
    setBusy(true);
    try {
      const saved = await api.saveWeeklyAvailability({ duration_minutes: duration, hours });
      setHours(saved.hours || {});
      notify(t("Weekly hours saved."));
      onSaved();
    } catch (err) { notify(err.message, 'error'); } finally { setBusy(false); }
  }
  if (error) return <div className="availability-weekly"><InlineLoadError message={error} onRetry={() => setAttempt((value) => value + 1)} /></div>;
  if (!hours) return <div className="availability-weekly"><p className="booking-cal-note">{t("Loading available times…")}</p></div>;
  return <form className="availability-weekly" onSubmit={save}>
    <p className="booking-cal-note">{t("Set the hours you can meet each week. Students pick a time inside them for the next 4 weeks. Times are in Tashkent time.")}</p>
    <div className="availability-add-row">
      <b>{t("Meeting length")}</b>
      <fieldset className="availability-durations"><legend className="sr-only">{t("Meeting length")}</legend>{[30, 45, 60].map((value) => <label key={value}><input type="radio" name="weekly-duration" checked={duration === value} onChange={() => setDuration(value)} /><span>{value} {t("min")}</span></label>)}</fieldset>
    </div>
    <ul className="weekly-days">{WEEKDAYS.map((name, day) => {
      const ranges = hours[day] || [];
      const dayName = weekdayName(day);
      return <li key={name}>
        <label className="weekly-day"><input type="checkbox" checked={ranges.length > 0} onChange={(event) => setDay(day, event.target.checked ? [DEFAULT_RANGE] : [])} /> {dayName}</label>
        <div className="weekly-ranges">{ranges.length ? ranges.map(([from, to], index) => <div key={index} className="weekly-range">
          <label className="availability-time"><span className="sr-only">{t("{day}: from", { day: dayName })}</span><input type="time" required value={from} onChange={(event) => setTime(day, index, 0, event.target.value)} /></label>
          <span aria-hidden="true">–</span>
          <label className="availability-time"><span className="sr-only">{t("{day}: until", { day: dayName })}</span><input type="time" required value={to} onChange={(event) => setTime(day, index, 1, event.target.value)} /></label>
          {zone.minutes !== 300 && <span className="weekly-equivalent">= {fromTashkentClock(from)}–{fromTashkentClock(to)} {t(zone.label)}</span>}
          <button type="button" className="availability-remove" onClick={() => setDay(day, ranges.filter((_, at) => at !== index))} aria-label={t("Remove {day} {from}–{to}", { day: dayName, from, to })} title={t("Remove")}><X size={16} aria-hidden="true" /></button>
        </div>) : <span className="weekly-off">{t("Unavailable")}</span>}</div>
        <button type="button" className="availability-remove weekly-add" disabled={ranges.length >= 4} onClick={() => setDay(day, [...ranges, nextRange(ranges)])} aria-label={t("Add hours on {day}", { day: dayName })} title={t("Add hours")}><Plus size={16} aria-hidden="true" /></button>
      </li>;
    })}</ul>
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
    {tab === 'weekly' ? <WeeklyHours notify={notify} onSaved={() => setSlotsVersion((value) => value + 1)} /> : <div className="booking-cal availability-cal">
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

// Students and counselors connect a Google account once: its verified email
// receives the meeting confirmations and reminders. Without it they still see and
// manage the meetings they have; only new requests and published times need it (as the API does).
const GOOGLE_ROLES = ['student', 'counselor', 'assistant'];
const needsGoogle = (user) => Boolean(user.google_connect_enabled) && GOOGLE_ROLES.includes(user.role) && !user.google_email;

async function connectGoogle(notify) {
  try {
    const { url } = await api.startGoogleConnect();
    window.location.assign(url);
  } catch (err) {
    notify(err.message, 'error');
  }
}

function GoogleConnectBanner({ user, notify }) {
  const [busy, setBusy] = useState(false);
  const failed = new URLSearchParams(window.location.search).get('google') === 'failed';
  async function connect() {
    setBusy(true);
    await connectGoogle(notify);
    setBusy(false);
  }
  const body = <div className="google-gate">
    <p>{t("Connect the Google account whose inbox you read to request new meetings and get email confirmations and reminders. Your current meetings keep working.")}</p>
    {failed && <p className="google-gate-error" role="alert">{t("Google could not confirm your account. Try again.")}</p>}
    <button type="button" className="button primary" disabled={busy} aria-busy={busy} onClick={connect}>{busy ? t("Opening Google…") : t("Continue with Google")}</button>
  </div>;
  if (usesCounselorLayout(user)) return <CxCard title={t("Connect your Google account")}>{body}</CxCard>;
  return <Panel title={t("Connect your Google account")}>{body}</Panel>;
}

export function BookingsPage({ user, data, reload, notify }) {
  const [zoneId, setZoneId] = useState(zone.id);
  const changeZone = (id) => { setMeetingZone(id); setZoneId(id); };
  const picker = <ZonePicker value={zoneId} onChange={changeZone} />;
  const locked = needsGoogle(user);
  // A button that starts something new goes to Google first while the account is not connected.
  const guard = (start) => (locked ? () => connectGoogle(notify) : start);
  const banner = locked ? <GoogleConnectBanner user={user} notify={notify} /> : null;
  const props = { data, reload, notify, guard, banner, picker };
  // key: a new zone redraws every time on the page.
  if (user.role === 'student') return <StudentBookingsPage key={zoneId} {...props} />;
  if (usesCounselorLayout(user)) return <CounselorMeetingsPage key={zoneId} {...props} />;
  return <StaffMeetingsPage key={zoneId} {...props} />;
}

function StudentBookingsPage({ data, reload, notify, guard, banner, picker }) {
  const [tab, setTab] = useState('upcoming');
  const [open, setOpen] = useState(false);
  const [savingId, setSavingId] = useState(null);
  const [rescheduling, setRescheduling] = useState(null);
  const now = new Date();
  const tabs = [['upcoming', 'Upcoming'], ['history', 'Past']];
  const items = studentMeetingsForTab(data.bookings, tab, now);
  async function transition(item, action) {
    if (action === 'cancel' && !window.confirm(t("Cancel this meeting?"))) return;
    setSavingId(item.id);
    try {
      const methods = { cancel: api.cancelBooking };
      await methods[action](item.id);
      notify({ cancel: t("Meeting cancelled.") }[action]);
      reload();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSavingId(null);
    }
  }
  return <div className="section-stack student-portal">{banner}<div className="portal-toolbar"><PortalTabs active={tab} onChange={setTab} items={tabs} /><div className="booking-toolbar-actions">{picker}<button className="button primary" onClick={guard(() => setOpen(true))}><Plus size={17} /> {t("Request meeting")}</button></div></div><p className="booking-cal-zone"><Globe size={15} aria-hidden="true" /> {timeZoneName()}</p><div className="booking-grid">{items.map((item) => { const status = meetingBadgeStatus(meetingStatus(item, now, { student: true })); return <article className={`booking-card is-${status}`} key={item.id}><div className="booking-date"><strong>{zoned(item.starts_at).getDate()}</strong><span>{formatDateLocale(item.starts_at, { month: 'short' })}</span></div><div><h3>{item.topic}</h3><p><Clock3 size={15} /> {joinParts(dateTimeText(item.starts_at), item.duration_minutes > 0 && tx`${item.duration_minutes} min`)}</p><small>{joinParts(t("Meeting with {name}", { name: item.participant_name || t("Meeting participant") }), item.participant_role && label(item.participant_role))}</small>{item.notes && <p>{item.notes}</p>}</div><div><Badge>{status}</Badge>{isOpenMeeting(item, now) && <div className="booking-actions"><button className="button quiet small" disabled={savingId === item.id} onClick={() => setRescheduling(item)}><CalendarClock size={14} /> {t("Reschedule")}</button><button className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'cancel')}><Ban size={14} /> {t("Cancel meeting")}</button></div>}{!isOpenMeeting(item, now) && <div className="booking-actions"><button className="button quiet small" disabled={savingId === item.id} onClick={() => deleteMeeting(item, { setSavingId, reload, notify, question: t("Delete this meeting? It disappears for your counselor too.") })}><Trash2 size={14} /> {t("Delete")}</button></div>}</div></article>; })}{!items.length && <Empty text={tab === 'upcoming' ? t("No upcoming meetings.") : t("No past meetings yet.")} />}</div>{open && <BookingForm onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}{rescheduling && <RescheduleForm booking={rescheduling} onClose={() => setRescheduling(null)} onSaved={() => {setRescheduling(null);reload();}} notify={notify} />}</div>;
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

function CounselorMeetingsPage({ data, reload, notify, guard, banner, picker }) {
  const [savingId, setSavingId] = useState(null);
  const [rescheduling, setRescheduling] = useState(null);
  const [addingNote, setAddingNote] = useState(null);
  const [booking, setBooking] = useState(null);
  const [availabilityOpen, setAvailabilityOpen] = useState(false);
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
    {pending.length || week.length ? <div className={`cx-meet-grid${pending.length && week.length ? '' : ' is-single'}`}>
      {pending.length > 0 && <CxCard title={tx`Requests waiting for you · ${pending.length}`}>
        <div className="cx-requests">
          {pending.map((item) => <article key={item.id} data-pending-id={item.id} className="cx-request">
            <div className="cx-request-head">
              <CxAvatar name={item.student_name} />
              <span className="cx-row-copy">
                <b>{joinParts(item.student_name, item.topic)}</b>
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
        <div className="cx-week">
          {week.map((item) => {
            const status = meetingBadgeStatus(meetingStatus(item, now, { student: false }));
            return <div key={item.id} className="cx-week-row">
              <span className="cx-week-when"><b>{dayLabel(item.starts_at)}</b><small>{clockAndLength(item)}</small></span>
              <span className="cx-row-copy"><b>{item.student_name}</b><small>{item.topic}</small></span>
              <CxTag tone={meetingTone(status)}>{label(status)}</CxTag>
              <span className="cx-week-actions">{weekActions(item)}{!isOpenMeeting(item, now) && <button type="button" className="cx-btn" disabled={savingId === item.id} aria-label={tx`Delete ${item.topic}`} onClick={() => deleteMeeting(item, { setSavingId, reload, notify })}><Trash2 size={15} aria-hidden="true" />{t("Delete")}</button>}</span>
            </div>;
          })}
        </div>
      </CxCard>}
    </div> : <CxCard title={t("This week")}><p className="cx-empty">{t("No requests waiting and nothing scheduled this week.")}</p></CxCard>}
    {rescheduling && <RescheduleForm booking={rescheduling} staff onClose={() => setRescheduling(null)} onSaved={() => {setRescheduling(null);reload();}} notify={notify} />}
    {addingNote && <MeetingNoteForm booking={addingNote} onClose={() => setAddingNote(null)} onSaved={() => setAddingNote(null)} notify={notify} />}
    {booking && <BookingForm staff defaultStudentId={booking.studentId} defaultStudentName={booking.studentName} defaultTopic={booking.topic} onClose={() => setBooking(null)} onSaved={() => {setBooking(null);reload();}} notify={notify} />}
    {availabilityOpen && <AvailabilityManager onClose={() => setAvailabilityOpen(false)} notify={notify} />}
  </div>;
}

// "Requests, today and this week" (product vision S3.4): the SLA-facing view
// of a counselor's meetings, oldest request first. See lib/meetings.js for
// the pending/this-week/rebook rules.
function StaffMeetingsPage({ data, reload, notify, guard, banner, picker }) {
  const [savingId, setSavingId] = useState(null);
  const [rescheduling, setRescheduling] = useState(null);
  const [addingNote, setAddingNote] = useState(null);
  const [booking, setBooking] = useState(null);
  const [availabilityOpen, setAvailabilityOpen] = useState(false);
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
    <div className="split-grid wide-left">
      <Panel title={tx`Requests waiting for you · ${pending.length}`}>
        <div className="record-list">
          {pending.map((item) => <div key={item.id} data-pending-id={item.id}><Record
            title={joinParts(item.student_name, item.topic)}
            meta={joinParts(dateTimeText(item.starts_at), item.duration_minutes > 0 && tx`${item.duration_minutes} min`, item.created_at && tx`requested ${relativeDayText(item.created_at).toLowerCase()}`)}
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
        <div className="record-list">
          {thisWeek.map((item) => <Record key={item.id} title={joinParts(dateTimeText(item.starts_at), item.topic)} meta={joinParts(item.student_name, viewerTimeHint(item.starts_at))} badge={meetingBadgeStatus(meetingStatus(item, now, { student: false }))} actions={<>{weekActions(item)}{!isOpenMeeting(item, now) && <button type="button" className="button quiet small" disabled={savingId === item.id} aria-label={tx`Delete ${item.topic}`} title={t("Delete")} onClick={() => deleteMeeting(item, { setSavingId, reload, notify })}><Trash2 size={14} aria-hidden="true" /> {t("Delete")}</button>}</>} />)}
          {!thisWeek.length && <Empty text={t("Nothing scheduled this week.")} />}
        </div>
      </Panel>
    </div>
    {rescheduling && <RescheduleForm booking={rescheduling} staff onClose={() => setRescheduling(null)} onSaved={() => {setRescheduling(null);reload();}} notify={notify} />}
    {addingNote && <MeetingNoteForm booking={addingNote} onClose={() => setAddingNote(null)} onSaved={() => setAddingNote(null)} notify={notify} />}
    {booking && <BookingForm staff defaultStudentId={booking.studentId} defaultStudentName={booking.studentName} defaultTopic={booking.topic} onClose={() => setBooking(null)} onSaved={() => {setBooking(null);reload();}} notify={notify} />}
    {availabilityOpen && <AvailabilityManager onClose={() => setAvailabilityOpen(false)} notify={notify} />}
  </div>;
}
