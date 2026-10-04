import { useState, useEffect, useRef } from 'react';
import { api } from '../api';
import { t, tx, locale, formatDateLocale } from '../i18n';
import { Modal, Badge, Empty, Panel } from '../components/ui';
import { Field, PortalTabs } from '../components/forms';
import { fullName, label } from '../lib/labels';
import { Record } from '../components/records';
import { Plus, Clock3, Check, X, CheckCircle2, CalendarClock, Calendar, CalendarDays, Ban, ArrowLeft, ChevronLeft, ChevronRight, Globe, Trash2 } from 'lucide-react';
import { clockText, dateTimeText, dayLabel, joinParts, relativeDayText } from '../lib/format';
import { isPlatformAdmin } from '../lib/roles';
import { CxAvatar, CxCard, CxHead, CxTag } from '../components/counselorUi';
import { isOpenMeeting, meetingStatus, meetingBadgeStatus, studentMeetingsForTab, pendingMeetings, meetingsThisWeek, needsRebook } from '../lib/meetings';
import { StudentPicker } from '../components/paged';
import './bookings-scheduler.css';

// Local calendar day of a timestamp, as YYYY-MM-DD.
function dayKey(value) {
  const date = new Date(value);
  const pad = (part) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

const monthStart = (value) => { const date = new Date(value); return new Date(date.getFullYear(), date.getMonth(), 1); };

// Browsers ship no Uzbek weekday or time-zone names (they fall back to English),
// so Uzbek uses the translated weekday and a numeric offset ("GMT+5").
const uzbek = () => locale().startsWith('uz');
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

// The viewer's own time zone ("Uzbekistan Standard Time"), in the UI language.
const timeZoneName = () => new Intl.DateTimeFormat(locale(), { timeZoneName: uzbek() ? 'shortOffset' : 'long' }).formatToParts(new Date()).find((part) => part.type === 'timeZoneName')?.value || '';

function slotRange(slot) {
  const end = new Date(new Date(slot.starts_at).getTime() + slot.duration_minutes * 60000);
  return `${clockText(slot.starts_at)} – ${clockText(end)}, ${formatDateLocale(slot.starts_at, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}`;
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
  const today = dayKey(new Date());
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
  const openDays = new Set(slots.filter((slot) => slot.available).map((slot) => dayKey(slot.starts_at)));
  const firstOpen = [...openDays].sort()[0];
  const lastOpen = [...openDays].sort().at(-1);
  const [viewMonth, setViewMonth] = useState(() => monthStart(firstOpen ? `${firstOpen}T00:00` : new Date()));
  const daySlots = slots.filter((slot) => dayKey(slot.starts_at) === selectedDate);
  return <div className={`booking-cal-picker ${selectedDate ? 'has-day' : ''}`.trim()}>
    <div>
      <MonthGrid month={viewMonth} onMonth={setViewMonth} canBack={viewMonth > monthStart(new Date())} canForward={Boolean(lastOpen) && monthStart(`${lastOpen}T00:00`) > viewMonth} marked={openDays} canPick={(key) => openDays.has(key)} selected={selectedDate} onPick={onDate} label={t("Available dates")} />
      <p className="booking-cal-zone"><Globe size={15} aria-hidden="true" /> {timeZoneName()} ({clockText(new Date())})</p>
    </div>
    {selectedDate && <div className="booking-cal-times" role="group" aria-label={t("Available times")}>
      <b>{dayTitle(selectedDate)}</b>
      {daySlots.map((slot) => selectedSlot?.id === slot.id
        ? <div key={slot.id} className="booking-cal-confirm"><span>{clockText(slot.starts_at)}</span><button type="button" onClick={onNext}>{t("Next")}</button></div>
        : <button key={slot.id} type="button" className="booking-cal-time" disabled={!slot.available} onClick={() => onSlot(slot)}>{clockText(slot.starts_at)}</button>)}
    </div>}
  </div>;
}

// `staff`: a counselor/teacher/org member booking with one of their students —
// they pick the student, not a participant (the API sets participant = them).
// `defaultStudentId`/`defaultTopic`: pre-fill for "Rebook" on an expired or declined request.
export function BookingForm({ staff = false, defaultStudentId = null, defaultTopic = '', onClose, onSaved, notify }) {
  const [participants, setParticipants] = useState([]);
  const [participantId, setParticipantId] = useState('');
  const [slots, setSlots] = useState([]);
  const [selectedDate, setSelectedDate] = useState('');
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [step, setStep] = useState('pick');
  const [topic, setTopic] = useState(defaultTopic);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(!staff);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (staff) return undefined;
    let active = true;
    Promise.all([api.bookingParticipants(), api.bookingAvailability()]).then(([people, times]) => {
      if (!active) return;
      const nextPeople = people || [];
      const nextSlots = times || [];
      setParticipants(nextPeople);
      setSlots(nextSlots);
      const firstWithTime = nextPeople.find((person) => nextSlots.some((slot) => slot.participant === person.id && slot.available));
      const first = firstWithTime || nextPeople[0];
      setParticipantId(String(first?.id || ''));
      const firstSlot = nextSlots.filter((slot) => slot.participant === first?.id && slot.available).sort((x, y) => new Date(x.starts_at) - new Date(y.starts_at))[0];
      if (firstSlot) setSelectedDate(dayKey(firstSlot.starts_at));
    }).catch((err) => { if (active) notify(err.message, 'error'); }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {active = false;};
  }, [staff, notify]);
  const personSlots = slots.filter((slot) => slot.participant === Number(participantId)).sort((x, y) => new Date(x.starts_at) - new Date(y.starts_at));
  const person = participants.find((item) => String(item.id) === participantId);
  const personName = person ? fullName(person) || person.username : '';
  const duration = selectedSlot?.duration_minutes || personSlots[0]?.duration_minutes;
  // Nobody can be booked through slots until they publish some: ask for any time instead.
  const freeForm = !loading && Boolean(participantId) && !personSlots.some((slot) => slot.available);
  function choosePerson(id) {
    const next = slots.filter((slot) => slot.participant === id && slot.available).sort((x, y) => new Date(x.starts_at) - new Date(y.starts_at))[0];
    setParticipantId(String(id));
    setSelectedDate(next ? dayKey(next.starts_at) : '');
    setSelectedSlot(null);
  }
  async function submit(event) {
    event.preventDefault();
    if (!staff && !selectedSlot && !freeForm) return;
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.create('bookings', staff ? {
        student: Number(values.get('student')),
        topic: values.get('topic'),
        starts_at: new Date(values.get('starts_at')).toISOString(),
        duration_minutes: Number(values.get('duration_minutes')),
        notes: values.get('notes')
      } : freeForm ? {
        participant: Number(participantId), topic, notes,
        starts_at: new Date(values.get('starts_at')).toISOString(),
        duration_minutes: Number(values.get('duration_minutes')),
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
  if (staff) return <Modal title={t("Request a meeting")} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <StudentPicker required value={defaultStudentId || ''} /><Field label={t("Topic")}><input name="topic" required defaultValue={defaultTopic} placeholder={t("Essay review, university list...")} /></Field><Field label={t("Date & time")}><input name="starts_at" type="datetime-local" required /></Field><Field label={t("Duration")}><select name="duration_minutes" defaultValue="45"><option value="30">{t("30 min")}</option><option value="45">{t("45 min")}</option><option value="60">{t("60 min")}</option></select></Field><Field label={t("Notes")}><textarea name="notes" placeholder={t("What would you like to discuss?")} /></Field>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Requesting…") : t("Send request")}</button></div>
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
        {loading ? <p className="booking-cal-note">{t("Loading available staff…")}</p> : participants.length ? participants.map((item) => {
          const free = slots.filter((slot) => slot.participant === item.id && slot.available).length;
          const name = fullName(item) || item.username;
          return <button key={item.id} type="button" className="booking-cal-person" aria-pressed={participantId === String(item.id)} onClick={() => choosePerson(item.id)}><span className="booking-cal-avatar" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span><span><b>{name}</b><small>{free ? t("{n} available times", { n: free }) : t("No available times")}</small></span></button>;
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
        {loading ? <p className="booking-cal-note">{t("Loading available times…")}</p> : !participantId ? null : freeForm
          ? <div className="booking-cal-fields">
            <p className="booking-cal-note">{t("No published times yet. Suggest a time and they will confirm it.")}</p>
            <Field label={t("Date & time")}><input name="starts_at" type="datetime-local" required /></Field>
            <Field label={t("Duration")}><select name="duration_minutes" defaultValue="45"><option value="30">{t("30 min")}</option><option value="45">{t("45 min")}</option><option value="60">{t("60 min")}</option></select></Field>
            <Field label={t("Topic")}><input name="topic" required value={topic} onChange={(event) => setTopic(event.target.value)} placeholder={t("Essay review, university list...")} /></Field>
            <Field label={t("Notes")}><textarea name="notes" value={notes} onChange={(event) => setNotes(event.target.value)} placeholder={t("What would you like to discuss?")} /></Field>
            <div><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Requesting…") : t("Request meeting")}</button></div>
          </div>
          : <SlotCalendar key={participantId} slots={personSlots} selectedDate={selectedDate} onDate={(key) => { setSelectedDate(key); setSelectedSlot(null); }} selectedSlot={selectedSlot} onSlot={setSelectedSlot} onNext={() => setStep('details')} />}
      </>}
    </section>
  </form></Modal>;
}

const slotEnd = (slot) => new Date(new Date(slot.starts_at).getTime() + slot.duration_minutes * 60000);

// Staff publish the times students can book. Same calendar the student sees:
// days with times are tinted; the chosen day lists its times and adds new ones.
function AvailabilityManager({ onClose, notify }) {
  const [slots, setSlots] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedDay, setSelectedDay] = useState(() => dayKey(new Date()));
  const [viewMonth, setViewMonth] = useState(() => monthStart(new Date()));
  const [time, setTime] = useState('');
  const [duration, setDuration] = useState(45);
  useEffect(() => {
    let active = true;
    api.bookingAvailability().then((items) => {
      if (!active) return;
      const next = (items || []).sort((x, y) => new Date(x.starts_at) - new Date(y.starts_at));
      setSlots(next);
      if (next[0]) { setSelectedDay(dayKey(next[0].starts_at)); setViewMonth(monthStart(next[0].starts_at)); }
    }).catch((err) => { if (active) notify(err.message, 'error'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [notify]);
  const today = dayKey(new Date());
  const slotDays = new Set(slots.map((slot) => dayKey(slot.starts_at)));
  const daySlots = slots.filter((slot) => dayKey(slot.starts_at) === selectedDay);
  const openCount = slots.filter((slot) => slot.available).length;
  async function add(event) {
    event.preventDefault();
    const startsAt = new Date(`${selectedDay}T${time}`);
    if (!time || startsAt <= new Date()) { notify(t("Choose a time in the future."), 'error'); return; }
    setBusy(true);
    try {
      const slot = await api.addBookingAvailability({ starts_at: startsAt.toISOString(), duration_minutes: duration });
      setSlots((current) => [...current, { ...slot, available: true }].sort((x, y) => new Date(x.starts_at) - new Date(y.starts_at)));
      setTime('');
      notify(t("Available time added."));
    } catch (err) { notify(err.message, 'error'); } finally { setBusy(false); }
  }
  async function remove(id) {
    setBusy(true);
    try { await api.removeBookingAvailability(id); setSlots((current) => current.filter((slot) => slot.id !== id)); notify(t("Available time removed.")); }
    catch (err) { notify(err.message, 'error'); } finally { setBusy(false); }
  }
  return <Modal title={t("My available hours")} onClose={onClose} className="booking-scheduler-modal">
    <div className="booking-cal availability-cal">
      <aside className="booking-cal-side">
        <p className="booking-cal-note">{t("Add times students can choose when requesting a meeting. Times are shown in your local time zone.")}</p>
        <MonthGrid month={viewMonth} onMonth={setViewMonth} canBack={viewMonth > monthStart(new Date())} canForward marked={slotDays} canPick={(key) => key >= today} selected={selectedDay} onPick={setSelectedDay} label={t("Choose a date and time")} />
        <p className="booking-cal-zone"><Globe size={15} aria-hidden="true" /> {timeZoneName()}{!loading && <> · {t("{n} available times", { n: openCount })}</>}</p>
      </aside>
      <section className="booking-cal-main availability-day">
        <h3>{dayTitle(selectedDay)}</h3>
        {loading ? <p className="booking-cal-note">{t("Loading available times…")}</p> : daySlots.length ? <ul className="availability-slots">{daySlots.map((slot) => <li key={slot.id} className={slot.available ? '' : 'is-requested'}>
          <span><b>{clockText(slot.starts_at)} – {clockText(slotEnd(slot))}</b><small>{slot.duration_minutes} {t("min")}</small></span>
          <span className="availability-state">{slot.available ? t("Available") : t("Requested")}</span>
          <button type="button" className="availability-remove" disabled={busy || !slot.available} onClick={() => remove(slot.id)} aria-label={`${t("Remove")} ${clockText(slot.starts_at)}`} title={slot.available ? t("Remove") : t("A student already requested this time.")}><Trash2 size={16} aria-hidden="true" /></button>
        </li>)}</ul> : <p className="booking-cal-note">{t("No times on this day yet.")}</p>}
        <form className="availability-add" onSubmit={add}>
          <b>{t("Add available time")}</b>
          <div className="availability-add-row">
            <label className="availability-time"><span className="sr-only">{t("Time")}</span><input type="time" required value={time} onChange={(event) => setTime(event.target.value)} /></label>
            <fieldset className="availability-durations"><legend className="sr-only">{t("Duration")}</legend>{[30, 45, 60].map((value) => <label key={value}><input type="radio" name="availability-duration" checked={duration === value} onChange={() => setDuration(value)} /><span>{value} {t("min")}</span></label>)}</fieldset>
            <button className="button primary" disabled={busy || !time} aria-busy={busy}><Plus size={16} aria-hidden="true" /> {t("Add")}</button>
          </div>
        </form>
      </section>
    </div>
  </Modal>;
}

// `datetime-local` wants local wall-clock time without a zone.
function localInputValue(iso) {
  const date = new Date(iso);
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function RescheduleForm({ booking, staff = false, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(!staff && Boolean(booking.participant));
  const [selectedDate, setSelectedDate] = useState('');
  const [selectedSlot, setSelectedSlot] = useState(null);
  const form = useRef(null);
  useEffect(() => {
    if (staff || !booking.participant) return undefined;
    let active = true;
    const current = new Date(booking.starts_at).getTime();
    api.bookingAvailability(booking.participant).then((items) => {
      if (!active) return;
      // The meeting's own slot (or time) is where it already is, not a new time.
      const next = (items || [])
        .map((slot) => (slot.id === booking.availability_slot || new Date(slot.starts_at).getTime() === current ? { ...slot, available: false } : slot))
        .sort((x, y) => new Date(x.starts_at) - new Date(y.starts_at));
      setSlots(next);
      const first = next.find((slot) => slot.available);
      if (first) setSelectedDate(dayKey(first.starts_at));
    }).catch((err) => { if (active) notify(err.message, 'error'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [staff, booking.participant, booking.availability_slot, booking.starts_at, notify]);
  // Staff, or a participant without open slots: any date and time, as before slots existed.
  const freeForm = staff || (!loading && !slots.some((slot) => slot.available));
  async function submit(event) {
    event.preventDefault();
    if (!freeForm && !selectedSlot) return;
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.rescheduleBooking(booking.id, freeForm ? {
        starts_at: new Date(values.get('starts_at')).toISOString(),
        duration_minutes: Number(values.get('duration_minutes')),
      } : {
        starts_at: selectedSlot.starts_at, duration_minutes: selectedSlot.duration_minutes, availability_slot: selectedSlot.id,
      });
      notify(t("New time sent for confirmation."));
      onSaved();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  const otherParty = (staff ? booking.student_name : booking.participant_name) || t("Meeting participant");
  const calendar = !loading && !freeForm;
  return <Modal title={staff ? t("Suggest another time") : t("Reschedule meeting")} onClose={onClose} className={calendar ? 'booking-scheduler-modal' : undefined}><form ref={form} className="form-grid" onSubmit={submit}><p className="form-wide">{t("The new time goes back to {name} to confirm.", { name: otherParty })}</p>{loading ? <p className="form-wide booking-cal-note">{t("Loading available times…")}</p> : freeForm ? <><Field label={t("Date & time")}><input name="starts_at" type="datetime-local" required defaultValue={localInputValue(booking.starts_at)} /></Field><Field label={t("Duration")}><select name="duration_minutes" defaultValue={String(booking.duration_minutes || 45)}><option value="30">{t("30 min")}</option><option value="45">{t("45 min")}</option><option value="60">{t("60 min")}</option></select></Field></> : <div className="form-wide availability-picker"><h3>{t("Choose a new date and time")}</h3><SlotCalendar slots={slots} selectedDate={selectedDate} onDate={(key) => { setSelectedDate(key); setSelectedSlot(null); }} selectedSlot={selectedSlot} onSlot={setSelectedSlot} onNext={() => form.current?.requestSubmit()} /></div>}<div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || loading || (!freeForm && !selectedSlot)} aria-busy={saving}>{saving ? t("Sending…") : t("Propose new time")}</button></div></form></Modal>;
}

export function MeetingNoteForm({ booking, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.create('meetings', {
        student: booking.student,
        title: values.get('title'),
        meeting_date: booking.starts_at.slice(0, 10),
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
  return <Modal title={t("Meeting notes")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Title")}><input name="title" required defaultValue={booking.topic} /></Field><Field label={t("Summary")}><textarea name="summary" required placeholder={t("What did you cover?")} /></Field><Field label={t("Next steps")}><textarea name="next_steps" placeholder={t("Optional")} /></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : t("Save note")}</button></div></form></Modal>;
}

export function BookingsPage({ user, data, reload, notify }) {
  if (user.role === 'student') return <StudentBookingsPage data={data} reload={reload} notify={notify} />;
  if (user.role === 'counselor' && !isPlatformAdmin(user)) return <CounselorMeetingsPage data={data} reload={reload} notify={notify} />;
  return <StaffMeetingsPage data={data} reload={reload} notify={notify} />;
}

function StudentBookingsPage({ data, reload, notify }) {
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
  return <div className="section-stack student-portal"><div className="portal-toolbar"><PortalTabs active={tab} onChange={setTab} items={tabs} /><button className="button primary" onClick={() => setOpen(true)}><Plus size={17} /> {t("Request meeting")}</button></div><div className="booking-grid">{items.map((item) => { const status = meetingBadgeStatus(meetingStatus(item, now, { student: true })); return <article className={`booking-card is-${status}`} key={item.id}><div className="booking-date"><strong>{new Date(item.starts_at).getDate()}</strong><span>{formatDateLocale(item.starts_at, { month: 'short' })}</span></div><div><h3>{item.topic}</h3><p><Clock3 size={15} /> {joinParts(dateTimeText(item.starts_at), item.duration_minutes > 0 && tx`${item.duration_minutes} min`)}</p><small>{joinParts(t("Meeting with {name}", { name: item.participant_name || t("Meeting participant") }), item.participant_role && label(item.participant_role))}</small>{item.notes && <p>{item.notes}</p>}</div><div><Badge>{status}</Badge>{isOpenMeeting(item, now) && <div className="booking-actions"><button className="button quiet small" disabled={savingId === item.id} onClick={() => setRescheduling(item)}><CalendarClock size={14} /> {t("Reschedule")}</button><button className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'cancel')}><Ban size={14} /> {t("Cancel meeting")}</button></div>}</div></article>; })}{!items.length && <Empty text={tab === 'upcoming' ? t("No upcoming meetings.") : t("No past meetings yet.")} />}</div>{open && <BookingForm onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}{rescheduling && <RescheduleForm booking={rescheduling} onClose={() => setRescheduling(null)} onSaved={() => {setRescheduling(null);reload();}} notify={notify} />}</div>;
}

const meetingTone = (status) => ({ confirmed: 'ok', pending: 'warn' }[status] || 'quiet');
const clockAndLength = (item) => joinParts(clockText(item.starts_at), item.duration_minutes > 0 && tx`${item.duration_minutes} min`);

// "Requests, today and this week" in the Counselor Dashboard design: requests
// waiting for a decision on the left, the week's meetings on the right.
function CounselorMeetingsPage({ data, reload, notify }) {
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
    setSavingId(item.id);
    try {
      const methods = { approve: api.approveBooking, reject: api.rejectBooking, complete: api.completeBooking };
      await methods[action](item.id);
      notify({ approve: t("Meeting confirmed."), reject: t("Meeting declined."), complete: t("Meeting marked as completed.") }[action]);
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
    if (needsRebook(item, now)) return <button type="button" className="cx-btn" onClick={() => setBooking({ studentId: item.student, topic: item.topic })}>{t("Rebook")}</button>;
    return <>
      {status === 'approved' && !isOpenMeeting(item, now) && <button type="button" className="cx-btn" disabled={savingId === item.id} onClick={() => transition(item, 'complete')}>{t("Mark completed")}</button>}
      <button type="button" className="cx-btn" onClick={() => setAddingNote(item)}>{t("Notes")}</button>
    </>;
  }

  return <div className="cx-page cx-meetings">
    <CxHead title={t("Meetings")} subtitle={t("Requests, today and this week")}>
      <button type="button" className="cx-btn" onClick={() => setAvailabilityOpen(true)}><Calendar size={15} aria-hidden="true" />{t("My available hours")}</button>
      <button type="button" className="cx-btn primary" onClick={() => setBooking({})}><Plus size={15} aria-hidden="true" />{t("Book with a student")}</button>
    </CxHead>
    <div className="cx-meet-grid">
      <CxCard title={tx`Requests waiting for you · ${pending.length}`}>
        <div className="cx-requests">
          {pending.map((item) => <article key={item.id} data-pending-id={item.id} className="cx-request">
            <div className="cx-request-head">
              <CxAvatar name={item.student_name} />
              <span className="cx-row-copy">
                <b>{joinParts(item.student_name, item.topic)}</b>
                <small>{joinParts(
                  `${dayLabel(item.starts_at)} ${clockText(item.starts_at)}`,
                  item.duration_minutes > 0 && tx`${item.duration_minutes} min`,
                  item.previous_starts_at ? t('rescheduled from {when}', { when: `${dayLabel(item.previous_starts_at)} ${clockText(item.previous_starts_at)}` }) : item.created_at && t('requested {when}', { when: relativeDayText(item.created_at).toLowerCase() }),
                )}</small>
              </span>
              <CxTag tone="warn">{label(meetingBadgeStatus(item.status))}</CxTag>
            </div>
            <div className="cx-request-actions">
              <button type="button" className="cx-btn" disabled={savingId === item.id} onClick={() => transition(item, 'reject')}>{t("Decline")}</button>
              <button type="button" className="cx-btn" disabled={savingId === item.id} onClick={() => setRescheduling(item)}>{t("Suggest another time")}</button>
              <button type="button" className="cx-btn primary" disabled={savingId === item.id} aria-busy={savingId === item.id} onClick={() => transition(item, 'approve')}>{t("Accept")}</button>
            </div>
          </article>)}
          {!pending.length && <p className="cx-empty">{t("No requests waiting for you.")}</p>}
        </div>
      </CxCard>
      <CxCard title={t("This week")}>
        <div className="cx-week">
          {week.map((item) => {
            const status = meetingBadgeStatus(meetingStatus(item, now, { student: false }));
            return <div key={item.id} className="cx-week-row">
              <span className="cx-week-when"><b>{dayLabel(item.starts_at)}</b><small>{clockAndLength(item)}</small></span>
              <span className="cx-row-copy"><b>{item.student_name}</b><small>{item.topic}</small></span>
              <CxTag tone={meetingTone(status)}>{label(status)}</CxTag>
              <span className="cx-week-actions">{weekActions(item)}</span>
            </div>;
          })}
          {!week.length && <p className="cx-empty">{t("Nothing scheduled this week.")}</p>}
        </div>
      </CxCard>
    </div>
    <CxCard className="cx-meeting-help"><p>{t("Pending → Confirmed → Completed · Cancelled · Expired — not confirmed.")}{' '}{t("Rescheduled meetings appear as new requests, with the previous time shown.")}</p></CxCard>
    {rescheduling && <RescheduleForm booking={rescheduling} staff onClose={() => setRescheduling(null)} onSaved={() => {setRescheduling(null);reload();}} notify={notify} />}
    {addingNote && <MeetingNoteForm booking={addingNote} onClose={() => setAddingNote(null)} onSaved={() => setAddingNote(null)} notify={notify} />}
    {booking && <BookingForm staff defaultStudentId={booking.studentId} defaultTopic={booking.topic} onClose={() => setBooking(null)} onSaved={() => {setBooking(null);reload();}} notify={notify} />}
    {availabilityOpen && <AvailabilityManager onClose={() => setAvailabilityOpen(false)} notify={notify} />}
  </div>;
}

// "Requests, today and this week" (product vision S3.4): the SLA-facing view
// of a counselor's meetings, oldest request first. See lib/meetings.js for
// the pending/this-week/rebook rules.
function StaffMeetingsPage({ data, reload, notify }) {
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
    setSavingId(item.id);
    try {
      const methods = { approve: api.approveBooking, reject: api.rejectBooking, complete: api.completeBooking };
      await methods[action](item.id);
      notify({ approve: t("Meeting confirmed."), reject: t("Meeting declined."), complete: t("Meeting marked as completed.") }[action]);
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
    if (needsRebook(item, now)) return <button type="button" className="button quiet small" onClick={() => setBooking({ studentId: item.student, topic: item.topic })}><CalendarClock size={14} /> {t("Rebook")}</button>;
    return <>
      <button type="button" className="button quiet small" onClick={() => setAddingNote(item)}>{t("Notes")}</button>
      {status === 'approved' && !isOpenMeeting(item, now) && <button type="button" className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'complete')}><CheckCircle2 size={14} /> {t("Mark completed")}</button>}
    </>;
  }

  return <div className="section-stack meetings-staff">
    <div className="portal-toolbar"><h2>{t("Meetings")}</h2><div className="booking-toolbar-actions"><button className="button secondary" onClick={() => setAvailabilityOpen(true)}><Calendar size={17} /> {t("My available hours")}</button><button className="button primary" onClick={() => setBooking({})}><Plus size={17} /> {t("Book with a student")}</button></div></div>
    <div className="split-grid wide-left">
      <Panel title={tx`Requests waiting for you · ${pending.length}`}>
        <div className="record-list">
          {pending.map((item) => <div key={item.id} data-pending-id={item.id}><Record
            title={joinParts(item.student_name, item.topic)}
            meta={joinParts(dateTimeText(item.starts_at), item.duration_minutes > 0 && tx`${item.duration_minutes} min`, item.created_at && tx`requested ${relativeDayText(item.created_at).toLowerCase()}`)}
            badge={meetingBadgeStatus(item.status)}
            actions={<div className="booking-actions">
              <button type="button" className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'reject')}><X size={14} /> {t("Decline")}</button>
              <button type="button" className="button quiet small" disabled={savingId === item.id} onClick={() => setRescheduling(item)}><CalendarClock size={14} /> {t("Suggest another time")}</button>
              <button type="button" className="button primary small" disabled={savingId === item.id} onClick={() => transition(item, 'approve')}><Check size={14} /> {t("Accept")}</button>
            </div>}
          /></div>)}
          {!pending.length && <Empty text={t("No requests waiting for you.")} />}
        </div>
      </Panel>
      <Panel title={t("This week")}>
        <div className="record-list">
          {thisWeek.map((item) => <Record key={item.id} title={joinParts(dateTimeText(item.starts_at), item.topic)} meta={item.student_name} badge={meetingBadgeStatus(meetingStatus(item, now, { student: false }))} actions={weekActions(item)} />)}
          {!thisWeek.length && <Empty text={t("Nothing scheduled this week.")} />}
        </div>
      </Panel>
    </div>
    {rescheduling && <RescheduleForm booking={rescheduling} staff onClose={() => setRescheduling(null)} onSaved={() => {setRescheduling(null);reload();}} notify={notify} />}
    {addingNote && <MeetingNoteForm booking={addingNote} onClose={() => setAddingNote(null)} onSaved={() => setAddingNote(null)} notify={notify} />}
    {booking && <BookingForm staff defaultStudentId={booking.studentId} defaultTopic={booking.topic} onClose={() => setBooking(null)} onSaved={() => {setBooking(null);reload();}} notify={notify} />}
    {availabilityOpen && <AvailabilityManager onClose={() => setAvailabilityOpen(false)} notify={notify} />}
  </div>;
}
