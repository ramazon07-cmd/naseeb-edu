import { useCallback, useEffect, useState } from 'react';
import { Copy, Link2, UserPlus } from 'lucide-react';
import { api } from '../api';
import { formatNumberLocale, t, tp } from '../i18n';
import { GRADES, dateTimeText, gradeText, joinParts } from '../lib/format';
import { Field } from './forms';
import { Modal } from './ui';
import { CxAvatar, CxCard, CxHead, CxTabs, CxTag } from './counselorUi';
import { QuickCreateStudentForm } from '../pages/StudentsPage';
import { PageSkeleton } from './states';
import '../invites.css';

// Magic link lifetimes the counselor can pick; one day is the default.
const LINK_HOURS = [[24, '1 day'], [72, '3 days'], [168, '7 days']];

export const inviteUrl = (path) => `${window.location.origin}${path}`;

export function CopyField({ value, notify, label = t('Invitation link') }) {
  async function copy(event) {
    const input = event.currentTarget.parentElement.querySelector('input');
    try {
      await navigator.clipboard.writeText(value);
      notify(t('Copied'));
    } catch {
      input?.select();
      notify(t('Select the text and copy it'), 'error');
    }
  }
  return <div className="invite-copy">
    <input readOnly value={value} aria-label={label} onFocus={(event) => event.target.select()} />
    <button type="button" className="cx-btn primary" onClick={copy}><Copy size={15} aria-hidden="true" />{t('Copy')}</button>
  </div>;
}

// Organization accounts choose the counselor students join; a counselor invites for themselves.
function CounselorField({ counselors, value, onChange }) {
  if (!counselors) return null;
  return <Field label={t('Counselor')}><select value={value} onChange={(event) => onChange(event.target.value)} required>
    <option value="">{t('Choose a counselor')}</option>
    {counselors.map((counselor) => <option key={counselor.id} value={counselor.id}>{counselor.name}</option>)}
  </select></Field>;
}

function PersonalInviteTab({ notify, counselors, counselor, setCounselor }) {
  const empty = { first_name: '', last_name: '', email: '', phone: '', grade: '' };
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [created, setCreated] = useState(null);
  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }));
  async function submit(event) {
    event.preventDefault();
    setSaving(true); setError('');
    try {
      setCreated(await api.createStudentInvite({ kind: 'personal', ...form, ...(counselors ? { counselor } : {}) }));
    } catch (failure) {
      setError(failure.message);
    } finally {
      setSaving(false);
    }
  }
  if (created) return <div className="invite-link-box" role="status">
    <b>{t('Invitation for {name}', { name: joinParts(created.first_name, created.last_name) })}</b>
    <CopyField value={inviteUrl(created.path)} notify={notify} />
    <p className="invite-note">{t('Send this link to {email} yourself. It works once and expires on {date}. It is shown only now.', { email: created.email, date: dateTimeText(created.expires_at) })}</p>
    <div className="invite-actions"><button type="button" className="cx-btn" onClick={() => { setCreated(null); setForm(empty); }}><UserPlus size={15} aria-hidden="true" />{t('Invite another student')}</button></div>
  </div>;
  return <form className="form-grid" onSubmit={submit}>
    <Field label={t('First name')}><input value={form.first_name} onChange={set('first_name')} autoComplete="off" required maxLength={150} /></Field>
    <Field label={t('Last name')}><input value={form.last_name} onChange={set('last_name')} autoComplete="off" required maxLength={150} /></Field>
    <Field label={t('Email')}><input type="email" value={form.email} onChange={set('email')} autoComplete="off" required /></Field>
    <Field label={t('Phone (optional)')}><input type="tel" value={form.phone} onChange={set('phone')} autoComplete="off" maxLength={32} /></Field>
    <Field label={t('Grade')}><select value={form.grade} onChange={set('grade')}><option value="">{t('Not set')}</option>{GRADES.map((grade) => <option key={grade} value={grade}>{gradeText(grade)}</option>)}</select></Field>
    <CounselorField counselors={counselors} value={counselor} onChange={setCounselor} />
    <p className="invite-note form-wide">{t('The student opens the link, checks these details and chooses their own username and password. They must use this email.')}</p>
    {error && <div className="alert error form-wide" role="alert">{error}</div>}
    <div className="form-actions form-wide"><button className="cx-btn primary" disabled={saving} aria-busy={saving}>{saving ? t('Creating…') : t('Create invitation')}</button></div>
  </form>;
}

function MagicLinkTab({ notify, counselors, counselor, setCounselor }) {
  const [hours, setHours] = useState(24);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [created, setCreated] = useState(null);
  const [links, setLinks] = useState(null);
  const load = useCallback(() => api.studentInvites('?status=active&kind=link').then(setLinks, () => setLinks([])), []);
  useEffect(() => { load(); }, [load]);
  async function create() {
    setSaving(true); setError('');
    try {
      setCreated(await api.createStudentInvite({ kind: 'link', expires_in_hours: hours, ...(counselors ? { counselor } : {}) }));
      load();
    } catch (failure) {
      setError(failure.message);
    } finally {
      setSaving(false);
    }
  }
  async function revoke(id) {
    try {
      await api.revokeStudentInvite(id);
      if (created?.id === id) setCreated(null);
      notify(t('Link revoked'));
      load();
    } catch (failure) {
      notify(failure.message, 'error');
    }
  }
  return <div className="invite-modal">
    <p className="invite-note">{t('Anyone with this link can join your school as your student until it expires or you revoke it. Each student enters their name and email, then sets a username and password. You confirm everyone who joins.')}</p>
    <div className="form-grid">
      <CounselorField counselors={counselors} value={counselor} onChange={setCounselor} />
      <Field label={t('Link expires after')}><select value={hours} onChange={(event) => setHours(Number(event.target.value))}>{LINK_HOURS.map(([value, text]) => <option key={value} value={value}>{t(text)}</option>)}</select></Field>
      <div className="form-actions"><button type="button" className="cx-btn primary" onClick={create} disabled={saving} aria-busy={saving}><Link2 size={15} aria-hidden="true" />{saving ? t('Creating…') : t('Create magic link')}</button></div>
    </div>
    {error && <div className="alert error" role="alert">{error}</div>}
    {created && <div className="invite-link-box" role="status">
      <b>{t('Your magic link')}</b>
      <CopyField value={inviteUrl(created.path)} notify={notify} />
      <p className="invite-note">{t('Expires on {date}. Copy it now: the link is shown only once.', { date: dateTimeText(created.expires_at) })}</p>
      <div className="invite-actions"><button type="button" className="cx-btn" onClick={() => revoke(created.id)}>{t('Revoke')}</button></div>
    </div>}
    {links?.length > 0 && <section>
      <h3 className="invite-note">{t('Active magic links')}</h3>
      <ul className="invite-list">{links.map((link) => <li key={link.id}>
        <span className="invite-row-copy"><b>{t('Expires {date}', { date: dateTimeText(link.expires_at) })}</b><small>{joinParts(t('Created {date}', { date: dateTimeText(link.created_at) }), tp('{n} student joined|{n} students joined', link.use_count, { n: formatNumberLocale(link.use_count) }))}</small></span>
        <button type="button" className="cx-btn" onClick={() => revoke(link.id)}>{t('Revoke')}</button>
      </li>)}</ul>
    </section>}
  </div>;
}

// The counselor creates the account and hands the student the login card.
function CreateAccountTab({ user, data, notify, onCreated, onClose }) {
  return <>
    <p className="invite-note">{t('Create the account and give the student the login and password. They choose their own password at the first sign-in.')}</p>
    <QuickCreateStudentForm user={user} data={data} notify={notify} onCreated={onCreated} onCancel={onClose} />
  </>;
}

// "Add student": an account created now and, while self-join is switched on
// (STUDENT_SELF_JOIN_ENABLED), a personal invite or a shareable magic link.
// `onJoined` opens Recently joined; `onCreated` runs after a direct creation.
export function AddStudentModal({ user, data, onClose, notify, onJoined, onCreated }) {
  const selfJoin = Boolean(user?.student_self_join);
  const [tab, setTab] = useState('create');
  const [counselor, setCounselor] = useState('');
  // Organization accounts pick the counselor; counselors invite for themselves.
  const [counselors, setCounselors] = useState(null);
  const picksCounselor = selfJoin && user?.role === 'organization';
  useEffect(() => {
    if (!picksCounselor) return;
    api.studentInviteCounselors().then((rows) => {
      setCounselors(rows);
      if (rows.length === 1) setCounselor(String(rows[0].id));
    }, (failure) => notify(failure.message, 'error'));
  }, [picksCounselor, notify]);
  const picker = { counselors: picksCounselor ? counselors || [] : null, counselor, setCounselor };
  const createTab = <CreateAccountTab user={user} data={data} notify={notify} onCreated={onCreated} onClose={onClose} />;
  return <Modal title={t('Add student')} onClose={onClose}>
    <div className="invite-modal invite-dialog">
      {selfJoin ? <>
        <CxTabs label={t('How to add the student')} active={tab} onChange={setTab} items={[['create', 'Create account now'], ['personal', 'Invite by email/details'], ['link', 'Magic link']]} />
        <div role="tabpanel" aria-labelledby={`cx-tab-${tab}`}>
          {tab === 'personal' && <PersonalInviteTab notify={notify} {...picker} />}
          {tab === 'link' && <MagicLinkTab notify={notify} {...picker} />}
          {tab === 'create' && createTab}
        </div>
        {onJoined && tab !== 'create' && <p className="invite-note">{t('Students who join wait for your confirmation in Recently joined.')} <button type="button" className="cx-link" onClick={() => { onClose(); onJoined(); }}>{t('Open Recently joined')}</button></p>}
      </> : createTab}
    </div>
  </Modal>;
}

// Above the Students list while someone waits for confirmation. With `onInvite`
// (organization accounts, whose list has no invite button) it always shows.
export function JoinedBanner({ count, onOpen, onInvite }) {
  if (!(count > 0) && !onInvite) return null;
  return <div className="joined-banner" role="status">
    <UserPlus size={18} aria-hidden="true" />
    <p>{count > 0 ? tp('{n} student joined and waits for your confirmation.|{n} students joined and wait for your confirmation.', count, { n: formatNumberLocale(count) }) : t('Invite students with a personal invitation or a magic link.')}</p>
    {onInvite && <button type="button" className="cx-btn" onClick={onInvite}>{t('Invite students')}</button>}
    <button type="button" className={`cx-btn${count > 0 ? ' primary' : ''}`} onClick={onOpen}>{count > 0 ? t('Review') : t('Recently joined')}</button>
  </div>;
}

const inviteKindText = (invite) => (invite?.kind === 'personal' ? t('Personal invite') : invite?.kind === 'link' ? t('Magic link') : t('Invite'));

// The counselor's confirmation queue: students who joined by invite.
// `headless`: the shell already draws the page title (organization workspace).
export function RecentlyJoinedPage({ user, data, notify, onChanged, onBack, headless = false }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null);
  const [rejecting, setRejecting] = useState(null);
  const [adding, setAdding] = useState(false);
  const load = useCallback(() => api.pendingStudents().then((items) => { setRows(items); setError(''); }, (failure) => setError(failure.message)), []);
  useEffect(() => { load(); }, [load]);
  async function decide(row, confirm) {
    setBusy(row.id);
    try {
      await (confirm ? api.confirmPendingStudent(row.id) : api.rejectPendingStudent(row.id));
      notify(confirm ? t('{name} is now your student.', { name: row.full_name }) : t('{name} was removed.', { name: row.full_name }));
      setRows((current) => current.filter((item) => item.id !== row.id));
      setRejecting(null);
      onChanged?.();
    } catch (failure) {
      if (failure.status === 409 && failure.details?.status === 'confirmed') {
        // Someone confirmed this student first: nothing was removed.
        notify(t('{name} was already confirmed and stays a student.', { name: row.full_name }), 'error');
        setRows((current) => current.filter((item) => item.id !== row.id));
        setRejecting(null);
        onChanged?.();
      } else {
        notify(failure.message, 'error');
        load();
      }
    } finally {
      setBusy(null);
    }
  }
  const actions = <>
    {onBack && <button type="button" className="cx-btn" onClick={onBack}>{t('Students')}</button>}
    <button type="button" className="cx-btn primary" onClick={() => setAdding(true)}><UserPlus size={15} aria-hidden="true" />{t('Add student')}</button>
  </>;
  return <div className="cx-page">
    {headless ? <div className="invite-actions joined-actions">{actions}</div> : <CxHead title={t('Recently joined')} subtitle={t('Students who joined with your invitation or magic link. Confirm the ones who are yours.')}>{actions}</CxHead>}
    {error && <div className="alert error" role="alert">{error} <button type="button" className="cx-btn" onClick={load}>{t('Retry')}</button></div>}
    {!rows && !error ? <PageSkeleton /> : rows && <CxCard title={t('Waiting for you')} hint={formatNumberLocale(rows.length)}>
      {rows.length ? <ul className="joined-list">{rows.map((row) => <li key={row.id} className="joined-row">
        <CxAvatar name={row.full_name} />
        <span className="joined-row-copy">
          <b>{row.full_name}</b>
          <small>{joinParts(row.email, row.phone, gradeText(row.grade) || `${t('Grade')} —`)}</small>
          <small>{joinParts(t('Joined {date}', { date: dateTimeText(row.joined_at) }), inviteKindText(row.invite))}</small>
        </span>
        <span className="joined-row-actions">{rejecting === row.id ? <>
          <CxTag tone="late" small>{t('Remove this account?')}</CxTag>
          <button type="button" className="cx-btn" onClick={() => setRejecting(null)} disabled={busy === row.id}>{t('Cancel')}</button>
          <button type="button" className="cx-btn primary" onClick={() => decide(row, false)} disabled={busy === row.id} aria-busy={busy === row.id}>{t('Reject')}</button>
        </> : <>
          <button type="button" className="cx-btn" onClick={() => setRejecting(row.id)} disabled={busy === row.id}>{t('Reject')}</button>
          <button type="button" className="cx-btn primary" onClick={() => decide(row, true)} disabled={busy === row.id} aria-busy={busy === row.id}>{t('Confirm · my student')}</button>
        </>}</span>
      </li>)}</ul> : <p className="cx-empty">{t('Nobody is waiting. Students who join with your links appear here.')}</p>}
    </CxCard>}
    {adding && <AddStudentModal user={user} data={data} onClose={() => setAdding(false)} notify={notify} onCreated={onChanged} />}
  </div>;
}
