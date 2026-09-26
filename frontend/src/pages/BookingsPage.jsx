import { useState, useEffect } from 'react';
import { api } from '../api';
import { t, tx, locale } from '../i18n';
import { Modal, Badge, Empty } from '../components/ui';
import { Field, PortalTabs } from '../components/forms';
import { fullName, label } from '../lib/labels';
import { ShieldAlert, Plus, UserRound, Clock3, Check, X, CheckCircle2, CalendarClock, Ban } from 'lucide-react';
import { dateTimeText, joinParts } from '../lib/format';
import { isOpenMeeting, meetingStatus, meetingsForTab } from '../lib/meetings';

export function BookingForm({ onClose, onSaved, notify }) {
  const [participants, setParticipants] = useState([]);
  const [loadingParticipants, setLoadingParticipants] = useState(true);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    api.bookingParticipants().
    then((items) => active && setParticipants(items || [])).
    catch((err) => notify(err.message, 'error')).
    finally(() => active && setLoadingParticipants(false));
    return () => {active = false;};
  }, [notify]);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.create('bookings', {
        participant: Number(values.get('participant')),
        topic: values.get('topic'),
        starts_at: new Date(values.get('starts_at')).toISOString(),
        duration_minutes: Number(values.get('duration_minutes')),
        notes: values.get('notes')
      });
      notify(t("Meeting request sent for approval."));
      onSaved();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("Request a meeting")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Meet with")}><select name="participant" required defaultValue="" disabled={loadingParticipants}><option value="" disabled>{loadingParticipants ? t("Loading available staff…") : t("Select counselor, teacher, or school representative")}</option>{participants.map((participant) => <option key={participant.id} value={participant.id}>{joinParts(fullName(participant), label(participant.role), participant.position)}</option>)}</select></Field><Field label={t("Topic")}><input name="topic" required placeholder={t("Essay review, university list...")} /></Field><Field label={t("Date & time")}><input name="starts_at" type="datetime-local" required /></Field><Field label={t("Duration")}><select name="duration_minutes" defaultValue="45"><option value="30">{t("30 min")}</option><option value="45">{t("45 min")}</option><option value="60">{t("60 min")}</option></select></Field><Field label={t("Notes")}><textarea name="notes" /></Field>{!loadingParticipants && !participants.length && <div className="form-wide booking-participant-warning"><ShieldAlert size={18} /><span>{t("No counselor, teacher, or school representative is available for your account.")}</span></div>}<div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || loadingParticipants || !participants.length} aria-busy={saving}>{saving ? t("Requesting…") : t("Request meeting")}</button></div></form></Modal>;
}

// `datetime-local` wants local wall-clock time without a zone.
function localInputValue(iso) {
  const date = new Date(iso);
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function RescheduleForm({ booking, onClose, onSaved, notify }) {
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
      notify(t("New time sent for approval."));
      onSaved();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("Reschedule meeting")} onClose={onClose}><form className="form-grid" onSubmit={submit}><p className="form-wide">{t("The new time goes back to {name} for approval.", { name: booking.participant_name || t("Meeting participant") })}</p><Field label={t("Date & time")}><input name="starts_at" type="datetime-local" required defaultValue={localInputValue(booking.starts_at)} /></Field><Field label={t("Duration")}><select name="duration_minutes" defaultValue={String(booking.duration_minutes || 45)}><option value="30">{t("30 min")}</option><option value="45">{t("45 min")}</option><option value="60">{t("60 min")}</option></select></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Sending…") : t("Propose new time")}</button></div></form></Modal>;
}

export function BookingsPage({ user, data, reload, notify }) {
  const staff = user.role !== 'student';
  const [tab, setTab] = useState(staff ? 'pending' : 'upcoming');
  const [open, setOpen] = useState(false);
  const [savingId, setSavingId] = useState(null);
  const [rescheduling, setRescheduling] = useState(null);
  const now = new Date();
  const tabs = staff ?
  [['pending', 'Pending approval'], ['upcoming', 'Upcoming'], ['history', 'History']] :
  [['upcoming', 'Upcoming'], ['history', 'History']];
  const items = meetingsForTab(data.bookings, tab, staff, now);
  async function transition(item, action) {
    if (action === 'cancel' && !window.confirm(t("Cancel this meeting?"))) return;
    setSavingId(item.id);
    try {
      const methods = { approve: api.approveBooking, reject: api.rejectBooking, complete: api.completeBooking, cancel: api.cancelBooking };
      await methods[action](item.id);
      notify({ approve: t("Meeting approved."), reject: t("Meeting declined."), complete: t("Meeting marked as completed."), cancel: t("Meeting cancelled.") }[action]);
      reload();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSavingId(null);
    }
  }
  return <div className="section-stack student-portal"><div className="portal-toolbar"><PortalTabs active={tab} onChange={setTab} items={tabs} />{!staff && <button className="button primary" onClick={() => setOpen(true)}><Plus size={17} /> {t("Request meeting")}</button>}</div><div className="booking-grid">{items.map((item) => <article className="booking-card" key={item.id}><div className="booking-date"><strong>{new Date(item.starts_at).getDate()}</strong><span>{new Intl.DateTimeFormat(locale(), { month: 'short' }).format(new Date(item.starts_at))}</span></div><div><h3>{item.topic}</h3>{staff && <span className="booking-student"><UserRound size={14} /> {item.student_name}</span>}<p><Clock3 size={15} /> {joinParts(dateTimeText(item.starts_at), item.duration_minutes > 0 && tx`${item.duration_minutes} min`)}</p><small>{joinParts(t("Meeting with {name}", { name: item.participant_name || t("Meeting participant") }), item.participant_role && label(item.participant_role))}</small>{item.notes && <p>{item.notes}</p>}</div><div><Badge>{meetingStatus(item, now)}</Badge>{staff && item.status === 'pending' && isOpenMeeting(item, now) && <div className="booking-actions"><button className="button primary small" disabled={savingId === item.id} onClick={() => transition(item, 'approve')}><Check size={14} /> {t("Approve")}</button><button className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'reject')}><X size={14} /> {t("Reject")}</button></div>}{staff && item.status === 'approved' && <button className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'complete')}><CheckCircle2 size={14} /> {t("Mark completed")}</button>}{isOpenMeeting(item, now) && (!staff || item.status === 'approved') && <div className="booking-actions">{!staff && <button className="button quiet small" disabled={savingId === item.id} onClick={() => setRescheduling(item)}><CalendarClock size={14} /> {t("Reschedule")}</button>}<button className="button quiet small" disabled={savingId === item.id} onClick={() => transition(item, 'cancel')}><Ban size={14} /> {t("Cancel meeting")}</button></div>}</div></article>)}{!items.length && <Empty text={tab === 'pending' ? t("No meetings need approval.") : tab === 'upcoming' ? t("No upcoming meetings.") : t("No meeting history yet.")} />}</div>{open && <BookingForm onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}{rescheduling && <RescheduleForm booking={rescheduling} onClose={() => setRescheduling(null)} onSaved={() => {setRescheduling(null);reload();}} notify={notify} />}</div>;
}
