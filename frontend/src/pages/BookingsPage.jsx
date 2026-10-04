import { useState, useEffect } from 'react';
import { api } from '../api';
import { t, tx, locale } from '../i18n';
import { Modal, Badge, Empty, Panel } from '../components/ui';
import { Field, PortalTabs } from '../components/forms';
import { fullName, label } from '../lib/labels';
import { Record } from '../components/records';
import { ShieldAlert, Plus, Clock3, Check, X, CheckCircle2, CalendarClock, Calendar, Ban } from 'lucide-react';
import { clockText, dateTimeText, dayLabel, joinParts, relativeDayText } from '../lib/format';
import { isPlatformAdmin } from '../lib/roles';
import { CxAvatar, CxCard, CxHead, CxTag } from '../components/counselorUi';
import { isOpenMeeting, meetingStatus, meetingBadgeStatus, studentMeetingsForTab, pendingMeetings, meetingsThisWeek, needsRebook } from '../lib/meetings';
import { StudentPicker } from '../components/paged';

// `staff`: a counselor/teacher/org member booking with one of their students —
// they pick the student, not a participant (the API sets participant = them).
// `defaultStudentId`/`defaultTopic`: pre-fill for "Rebook" on an expired or declined request.
export function BookingForm({ staff = false, defaultStudentId = null, defaultTopic = '', onClose, onSaved, notify }) {
  const [participants, setParticipants] = useState([]);
  const [loadingParticipants, setLoadingParticipants] = useState(staff ? false : true);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (staff) return undefined;
    let active = true;
    api.bookingParticipants().
    then((items) => active && setParticipants(items || [])).
    catch((err) => notify(err.message, 'error')).
    finally(() => active && setLoadingParticipants(false));
    return () => {active = false;};
  }, [staff, notify]);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.create('bookings', {
        ...(staff ? { student: Number(values.get('student')) } : { participant: Number(values.get('participant')) }),
        topic: values.get('topic'),
        starts_at: new Date(values.get('starts_at')).toISOString(),
        duration_minutes: Number(values.get('duration_minutes')),
        notes: values.get('notes')
      });
      notify(staff ? t("Meeting confirmed.") : t("Meeting request sent for approval."));
      onSaved();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("Request a meeting")} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    {staff ? <StudentPicker required value={defaultStudentId || ''} /> : <Field label={t("Meet with")}><select name="participant" required defaultValue="" disabled={loadingParticipants}><option value="" disabled>{loadingParticipants ? t("Loading available staff…") : t("Select counselor, teacher, or school representative")}</option>{participants.map((participant) => <option key={participant.id} value={participant.id}>{joinParts(fullName(participant), label(participant.role), participant.position)}</option>)}</select></Field>}
    <Field label={t("Topic")}><input name="topic" required defaultValue={defaultTopic} placeholder={t("Essay review, university list...")} /></Field><Field label={t("Date & time")}><input name="starts_at" type="datetime-local" required /></Field><Field label={t("Duration")}><select name="duration_minutes" defaultValue="45"><option value="30">{t("30 min")}</option><option value="45">{t("45 min")}</option><option value="60">{t("60 min")}</option></select></Field><Field label={t("Notes")}><textarea name="notes" /></Field>{!staff && !loadingParticipants && !participants.length && <div className="form-wide booking-participant-warning"><ShieldAlert size={18} /><span>{t("No counselor, teacher, or school representative is available for your account.")}</span></div>}<div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || (!staff && (loadingParticipants || !participants.length))} aria-busy={saving}>{saving ? t("Requesting…") : staff ? t("Send request") : t("Request meeting")}</button></div></form></Modal>;
}

// `datetime-local` wants local wall-clock time without a zone.
function localInputValue(iso) {
  const date = new Date(iso);
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function RescheduleForm({ booking, staff = false, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.rescheduleBooking(booking.id, {
        starts_at: new Date(values.get('starts_at')).toISOString(),
        duration_minutes: Number(values.get('duration_minutes'))
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
  return <Modal title={staff ? t("Suggest another time") : t("Reschedule meeting")} onClose={onClose}><form className="form-grid" onSubmit={submit}><p className="form-wide">{t("The new time goes back to {name} to confirm.", { name: otherParty })}</p><Field label={t("Date & time")}><input name="starts_at" type="datetime-local" required defaultValue={localInputValue(booking.starts_at)} /></Field><Field label={t("Duration")}><select name="duration_minutes" defaultValue={String(booking.duration_minutes || 45)}><option value="30">{t("30 min")}</option><option value="45">{t("45 min")}</option><option value="60">{t("60 min")}</option></select></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Sending…") : t("Propose new time")}</button></div></form></Modal>;
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
  return <div className="section-stack student-portal"><div className="portal-toolbar"><PortalTabs active={tab} onChange={setTab} items={tabs} /><button className="button primary" onClick={() => setOpen(true)}><Plus size={17} /> {t("Request meeting")}</button></div><div className="booking-grid">{items.map((item) => <article className="booking-card" key={item.id}><div className="booking-date"><strong>{new Date(item.starts_at).getDate()}</strong><span>{new Intl.DateTimeFormat(locale(), { month: 'short' }).format(new Date(item.starts_at))}</span></div><div><h3>{item.topic}</h3><p><Clock3 size={15} /> {joinParts(dateTimeText(item.starts_at), item.duration_minutes > 0 && tx`${item.duration_minutes} min`)}</p><small>{joinParts(t("Meeting with {name}", { name: item.participant_name || t("Meeting participant") }), item.participant_role && label(item.participant_role))}</small>{item.notes && <p>{item.notes}</p>}</div><div><Badge>{meetingBadgeStatus(meetingStatus(item, now, { student: true }))}</Badge>{isOpenMeeting(item, now) && <div className="booking-actions"><button className="button quiet small" disabled={savingId === item.id} onClick={() => setRescheduling(item)}><CalendarClock size={14} /> {t("Reschedule")}</button><button className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'cancel')}><Ban size={14} /> {t("Cancel meeting")}</button></div>}</div></article>)}{!items.length && <Empty text={tab === 'upcoming' ? t("No upcoming meetings.") : t("No past meetings yet.")} />}</div>{open && <BookingForm onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}{rescheduling && <RescheduleForm booking={rescheduling} onClose={() => setRescheduling(null)} onSaved={() => {setRescheduling(null);reload();}} notify={notify} />}</div>;
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
      <button type="button" className="cx-btn" disabled title={t("Coming soon")}><Calendar size={15} aria-hidden="true" />{t("My available hours")}</button>
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
    <div className="portal-toolbar"><h2>{t("Meetings")}</h2><button className="button primary" onClick={() => setBooking({})}><Plus size={17} /> {t("Book with a student")}</button></div>
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
  </div>;
}
