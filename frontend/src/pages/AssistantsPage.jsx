import { useCallback, useEffect, useMemo, useState } from 'react';
import { Clock3, Mail, Search, UserPlus, Users, X } from 'lucide-react';
import { api } from '../api';
import { formatNumberLocale, t, tp } from '../i18n';
import { dateTimeText } from '../lib/format';
import { fullName } from '../lib/labels';
import { CheckboxControl, Field } from '../components/forms';
import { Modal } from '../components/ui';
import { CxAvatar, CxCard, CxHead, CxTag } from '../components/counselorUi';
import { PageSkeleton } from '../components/states';
import { CopyField, inviteUrl } from '../components/StudentInvites';
import '../invites.css';
import './assistants.css';

function InviteAssistantModal({ onClose, onCreated, notify }) {
  const empty = { first_name: '', last_name: '', email: '' };
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [created, setCreated] = useState(null);
  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }));
  async function submit(event) {
    event.preventDefault();
    setSaving(true); setError('');
    try {
      const invite = await api.createAssistantInvite(form);
      setCreated(invite);
      onCreated();
    } catch (failure) {
      setError(failure.details?.email ? [].concat(failure.details.email).join(' ') : failure.message);
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t('Invite an assistant')} onClose={onClose}>
    <div className="invite-modal invite-dialog">
      {created ? <div className="invite-link-box" role="status">
        <b>{created.emailed ? t('Invitation sent to {email}', { email: created.email }) : t('Invitation for {name}', { name: fullName(created) })}</b>
        <CopyField value={inviteUrl(created.path)} notify={notify} />
        <p className="invite-note">{created.emailed
          ? t('The link is also here in case the email does not arrive. It works once and expires on {date}. It is shown only now.', { date: dateTimeText(created.expires_at) })
          : t('Email is not set up yet: send this link to {email} yourself. It works once and expires on {date}. It is shown only now.', { email: created.email, date: dateTimeText(created.expires_at) })}</p>
        <div className="invite-actions"><button type="button" className="cx-btn" onClick={() => { setCreated(null); setForm(empty); }}><UserPlus size={15} aria-hidden="true" />{t('Invite another assistant')}</button></div>
      </div> : <form className="form-grid" onSubmit={submit}>
        <Field label={t('First name')}><input value={form.first_name} onChange={set('first_name')} autoComplete="off" required maxLength={150} /></Field>
        <Field label={t('Last name')}><input value={form.last_name} onChange={set('last_name')} autoComplete="off" required maxLength={150} /></Field>
        <Field label={t('Email')}><input type="email" value={form.email} onChange={set('email')} autoComplete="off" required /></Field>
        <p className="invite-note form-wide">{t('The assistant gets an email link, sets their own username and password, and then sees only the students you give them. They can review work and send it back; approving stays with you.')}</p>
        {error && <div className="alert error form-wide" role="alert">{error}</div>}
        <div className="form-actions form-wide"><button className="cx-btn primary" disabled={saving} aria-busy={saving}><Mail size={15} aria-hidden="true" />{saving ? t('Sending…') : t('Send invitation')}</button></div>
      </form>}
    </div>
  </Modal>;
}

// The counselor ticks which of their students this assistant works with.
function AssistantStudentsModal({ assistant, assistants, onClose, onSaved, notify }) {
  const [students, setStudents] = useState(null);
  const [error, setError] = useState('');
  const [chosen, setChosen] = useState(new Set());
  const [search, setSearch] = useState('');
  const [saving, setSaving] = useState(false);
  const names = useMemo(() => new Map(assistants.map((row) => [row.id, row.full_name])), [assistants]);
  useEffect(() => {
    let live = true;
    api.list('students', '?page_size=100').then((rows) => {
      if (!live) return;
      setStudents(rows);
      setChosen(new Set(rows.filter((row) => row.assigned_assistant === assistant.id).map((row) => row.id)));
    }, (failure) => { if (live) setError(failure.message); });
    return () => { live = false; };
  }, [assistant.id]);
  const visible = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return (students || []).filter((row) => !needle || fullName(row.user_detail).toLocaleLowerCase().includes(needle));
  }, [students, search]);
  function toggle(id) {
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  async function save() {
    setSaving(true);
    try {
      await api.setAssistantStudents(assistant.id, [...chosen]);
      notify(tp('{n} student given to {name}|{n} students given to {name}', chosen.size, { n: formatNumberLocale(chosen.size), name: assistant.full_name }));
      onSaved();
    } catch (failure) {
      notify(failure.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t('Students for {name}', { name: assistant.full_name })} onClose={onClose}>
    <div className="invite-modal invite-dialog assistant-students">
      {error && <div className="alert error" role="alert">{error}</div>}
      {!students && !error ? <PageSkeleton /> : students && <>
        <label className="search"><Search size={16} aria-hidden="true" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('Search students')} aria-label={t('Search students')} /></label>
        <p className="invite-note" role="status">{tp('{n} selected|{n} selected', chosen.size, { n: formatNumberLocale(chosen.size) })}</p>
        {visible.length ? <ul className="assistant-student-list">{visible.map((row) => {
          const other = row.assigned_assistant && row.assigned_assistant !== assistant.id ? names.get(row.assigned_assistant) : null;
          return <li key={row.id}><CheckboxControl checked={chosen.has(row.id)} onChange={() => toggle(row.id)}>
            <b>{fullName(row.user_detail)}</b>
            {other && <small>{t('Now with {name}', { name: other })}</small>}
          </CheckboxControl></li>;
        })}</ul> : <p className="cx-empty">{students.length ? t('No students match your search.') : t('You have no students yet.')}</p>}
        <div className="form-actions">
          <button type="button" className="cx-btn" onClick={onClose}>{t('Cancel')}</button>
          <button type="button" className="cx-btn primary" onClick={save} disabled={saving} aria-busy={saving}>{saving ? t('Saving…') : t('Save')}</button>
        </div>
      </>}
    </div>
  </Modal>;
}

// A counselor's assistants: who they are, which students each has, and open invitations.
export function AssistantsPage({ notify }) {
  const [assistants, setAssistants] = useState(null);
  const [invites, setInvites] = useState([]);
  const [error, setError] = useState('');
  const [inviting, setInviting] = useState(false);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(null);
  const load = useCallback(() => Promise.all([api.assistants(), api.assistantInvites()]).then(([rows, inviteRows]) => {
    setAssistants(rows);
    setInvites(inviteRows.filter((invite) => invite.status === 'active'));
    setError('');
  }, (failure) => setError(failure.message)), []);
  useEffect(() => { load(); }, [load]);

  async function revoke(invite) {
    setBusy(`invite-${invite.id}`);
    try {
      await api.revokeAssistantInvite(invite.id);
      notify(t('Invitation revoked'));
      load();
    } catch (failure) {
      notify(failure.message, 'error');
    } finally {
      setBusy(null);
    }
  }
  async function deactivate(assistant) {
    if (!window.confirm(t('Deactivate {name}? They can no longer sign in, and their students stay with you.', { name: assistant.full_name }))) return;
    setBusy(`assistant-${assistant.id}`);
    try {
      await api.deactivateAssistant(assistant.id);
      notify(t('{name} was deactivated.', { name: assistant.full_name }));
      load();
    } catch (failure) {
      notify(failure.message, 'error');
    } finally {
      setBusy(null);
    }
  }

  return <div className="cx-page assistants-page">
    <CxHead title={t('Assistants')} subtitle={t('Give your assistants some of your students. They work with them and their teachers, and you make the final decisions.')}>
      <button type="button" className="cx-btn primary" onClick={() => setInviting(true)}><UserPlus size={16} aria-hidden="true" />{t('Invite assistant')}</button>
    </CxHead>
    {error && <div className="alert error" role="alert">{error} <button type="button" className="cx-btn" onClick={load}>{t('Retry')}</button></div>}
    {!assistants && !error ? <PageSkeleton /> : assistants && <>
      <CxCard className="assistants-section" title={t('Your assistants')} hint={formatNumberLocale(assistants.length)}>
        {assistants.length ? <ul className="assistants-list">{assistants.map((row) => <li key={row.id} className="assistants-row">
          <div className="assistants-identity">
            <CxAvatar name={row.full_name} />
            <div className="assistants-person"><b>{row.full_name}</b><span>{row.email}</span></div>
          </div>
          <div className="assistants-details">
            {row.is_active ? <>
              <CxTag tone={row.students_count ? 'quiet' : 'warn'} small>{tp('{n} student|{n} students', row.students_count, { n: formatNumberLocale(row.students_count) })}</CxTag>
              <small>{row.last_login ? t('Last sign-in {date}', { date: dateTimeText(row.last_login) }) : t('Not signed in yet')}</small>
            </> : <CxTag small>{t('Deactivated')}</CxTag>}
          </div>
          {row.is_active && <div className="assistants-actions">
            <button type="button" className="cx-btn" onClick={() => setEditing(row)}><Users size={15} aria-hidden="true" />{t('Students')}</button>
            <button type="button" className="cx-btn assistants-action-muted" onClick={() => deactivate(row)} disabled={busy === `assistant-${row.id}`} aria-busy={busy === `assistant-${row.id}`}>{t('Deactivate')}</button>
          </div>}
        </li>)}</ul> : <p className="cx-empty">{t('No assistants yet. Invite one by email to share your students with them.')}</p>}
      </CxCard>
      {invites.length > 0 && <CxCard className="assistants-section assistants-pending" title={t('Waiting for sign-up')} hint={formatNumberLocale(invites.length)}>
        <ul className="assistants-list">{invites.map((invite) => <li key={invite.id} className="assistants-row">
          <div className="assistants-identity">
            <span className="assistants-mail" aria-hidden="true"><Mail size={18} /></span>
            <div className="assistants-person"><b>{fullName(invite)}</b><span>{invite.email}</span></div>
          </div>
          <div className="assistants-expiry"><Clock3 size={14} aria-hidden="true" /><time dateTime={invite.expires_at}>{t('Expires {date}', { date: dateTimeText(invite.expires_at) })}</time></div>
          <div className="assistants-actions">
            <button type="button" className="cx-btn assistants-action-muted" onClick={() => revoke(invite)} disabled={busy === `invite-${invite.id}`} aria-busy={busy === `invite-${invite.id}`}><X size={14} aria-hidden="true" />{t('Revoke')}</button>
          </div>
        </li>)}</ul>
      </CxCard>}
    </>}
    {inviting && <InviteAssistantModal notify={notify} onClose={() => setInviting(false)} onCreated={load} />}
    {editing && <AssistantStudentsModal assistant={editing} assistants={assistants || []} notify={notify} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
  </div>;
}
