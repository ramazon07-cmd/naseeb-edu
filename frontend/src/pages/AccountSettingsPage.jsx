import { useEffect, useMemo, useState } from 'react';
import { Eye, EyeOff, Globe2, KeyRound, Mail, RefreshCw, ShieldCheck, UserRound, UsersRound } from 'lucide-react';
import { api } from '../api';
import { t } from '../i18n';
import { Field } from '../components/forms';
import { LanguageSelector } from '../components/brand';
import { ProfilePhotoField } from '../components/profileFields';
import { dateText } from '../lib/format';
import { fullName, initials } from '../lib/labels';
import { accountFieldErrors } from '../lib/accountSettings';

const RELATIONSHIPS = { mother: 'Mother', father: 'Father', guardian: 'Guardian', other: 'Other' };
const SECTIONS = { applications: 'Applications', documents: 'Documents', meetings: 'Meetings' };
const ALWAYS_VISIBLE = { profile: 'Profile summary', progress: 'Progress and level', tasks: 'Tasks and deadlines' };
const NEVER_VISIBLE = {
  private_essays: 'Essays', messages: 'Messages', counselor_notes: 'Counselor notes',
  task_responses: 'Task responses', document_files: 'Document files',
};

const errorsFrom = (error) => accountFieldErrors(error?.details, error?.message, t);

function PasswordInput({ value, onChange, autoComplete, invalid, ...props }) {
  const [visible, setVisible] = useState(false);
  const label = visible ? t('Hide password') : t('Show password');
  return <span className="account-password-input"><input type={visible ? 'text' : 'password'} value={value} onChange={(event) => onChange(event.target.value)} autoComplete={autoComplete} aria-invalid={invalid || undefined} required {...props} /><button type="button" className="icon-button" onClick={() => setVisible(!visible)} aria-label={label} title={label}>{visible ? <EyeOff size={17} /> : <Eye size={17} />}</button></span>;
}

const PROFILE_FIELDS = ['first_name', 'last_name', 'phone', 'position'];

// A counselor's own name, phone, position and photo (students edit theirs in Student Center).
function ProfileSection({ user, onUserChange, notify }) {
  const [form, setForm] = useState(() => Object.fromEntries(PROFILE_FIELDS.map((name) => [name, user[name] || ''])));
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const unchanged = PROFILE_FIELDS.every((name) => form[name].trim() === (user[name] || ''));
  // Photo writes save at once and return the account, whose avatar URL carries the new version.
  const photo = useMemo(() => ({
    load: (id) => api.accountAvatar(id),
    upload: async (id, file) => onUserChange({ avatar: (await api.uploadAccountAvatar(id, file)).avatar }),
    remove: async (id) => onUserChange({ avatar: (await api.removeAccountAvatar(id)).avatar }),
  }), [onUserChange]);
  const input = (name) => ({ value: form[name], onChange: (event) => setForm((current) => ({ ...current, [name]: event.target.value })), 'aria-invalid': Boolean(errors[name]) || undefined });
  async function submit(event) {
    event.preventDefault();
    if (unchanged) return;
    setSaving(true);setErrors({});
    try {
      const updated = await api.update('users/accounts', user.id, Object.fromEntries(PROFILE_FIELDS.map((name) => [name, form[name].trim()])));
      onUserChange(Object.fromEntries(PROFILE_FIELDS.map((name) => [name, updated[name]])));
      notify(t('Your profile was updated.'));
    } catch (error) {
      setErrors(errorsFrom(error));
    } finally {setSaving(false);}
  }
  return <section className="panel account-settings-panel" aria-labelledby="account-profile-title">
    <header><UserRound size={18} aria-hidden="true" /><h2 id="account-profile-title">{t('Profile')}</h2></header>
    <form className="panel-body form-grid" onSubmit={submit}>
      <div className="form-wide"><ProfilePhotoField profileId={user.id} hasPhoto={Boolean(user.avatar)} initials={initials(fullName(user))} photo={photo} hint={t('PNG, JPG or WebP · up to 2 MB')} onError={(message) => message && notify(message, 'error')} /></div>
      <Field label={t('First name')} error={errors.first_name}><input {...input('first_name')} autoComplete="given-name" maxLength="150" placeholder={t('e.g. Dilnoza')} required /></Field>
      <Field label={t('Last name')} error={errors.last_name}><input {...input('last_name')} autoComplete="family-name" maxLength="150" placeholder={t('e.g. Karimova')} /></Field>
      <Field label={t('Phone')} error={errors.phone}><input {...input('phone')} type="tel" autoComplete="tel" maxLength="32" placeholder={t('e.g. +998 90 123 45 67')} /></Field>
      <Field label={t('Position')} error={errors.position}><input {...input('position')} maxLength="120" placeholder={t('School counselor')} /></Field>
      {errors.form && <div className="alert error form-wide" role="alert">{errors.form}</div>}
      <div className="form-actions"><button className="button primary" disabled={saving || unchanged} aria-busy={saving}>{saving ? t('Saving…') : t('Save profile')}</button></div>
    </form>
  </section>;
}

function EmailSection({ user, onUserChange, notify }) {
  const [email, setEmail] = useState(user.email || '');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const unchanged = email.trim().toLowerCase() === (user.email || '').toLowerCase();
  async function submit(event) {
    event.preventDefault();
    if (unchanged) return;
    setSaving(true);setErrors({});
    try {
      const updated = await api.changeOwnEmail(password, email.trim());
      onUserChange({ email: updated.email });
      setEmail(updated.email);setPassword('');
      notify(t('Your email address was updated.'));
    } catch (error) {
      setErrors(errorsFrom(error));
    } finally {setSaving(false);}
  }
  return <section className="panel account-settings-panel" aria-labelledby="account-email-title">
    <header><Mail size={18} aria-hidden="true" /><h2 id="account-email-title">{t('Sign-in details')}</h2></header>
    <form className="panel-body form-grid" onSubmit={submit}>
      <Field label={t('Username')} hint={t('Your username cannot be changed.')}><input value={user.username || ''} readOnly aria-readonly="true" autoComplete="username" /></Field>
      <Field label={t('Email address')} error={errors.email}><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" maxLength="254" aria-invalid={Boolean(errors.email) || undefined} required /></Field>
      {!unchanged && <Field label={t('Current password')} hint={t('Confirm it is you to change your email.')} error={errors.current_password}><PasswordInput value={password} onChange={setPassword} autoComplete="current-password" invalid={Boolean(errors.current_password)} /></Field>}
      {errors.form && <div className="alert error form-wide" role="alert">{errors.form}</div>}
      <div className="form-actions"><button className="button primary" disabled={saving || unchanged || !password} aria-busy={saving}>{saving ? t('Saving…') : t('Save email')}</button></div>
    </form>
  </section>;
}

function PasswordSection({ onUserChange, notify }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    if (next !== confirm) {setErrors({ confirm_password: t('Passwords do not match.') });return;}
    setSaving(true);setErrors({});
    try {
      const result = await api.changeOwnPassword(current, next, confirm);
      if (result.user) onUserChange(result.user);
      setCurrent('');setNext('');setConfirm('');
      notify(t('Password changed. You are still signed in here; other devices were signed out.'));
    } catch (error) {
      setErrors(errorsFrom(error));
    } finally {setSaving(false);}
  }
  return <section className="panel account-settings-panel" aria-labelledby="account-password-title">
    <header><KeyRound size={18} aria-hidden="true" /><h2 id="account-password-title">{t('Password')}</h2></header>
    <form className="panel-body form-grid" onSubmit={submit}>
      <Field label={t('Current password')} error={errors.current_password}><PasswordInput value={current} onChange={setCurrent} autoComplete="current-password" invalid={Boolean(errors.current_password)} /></Field>
      <span className="account-settings-spacer" aria-hidden="true" />
      <Field label={t('New password')} hint={t('Use at least 8 characters with upper/lowercase letters and a number.')} error={errors.new_password}><PasswordInput value={next} onChange={setNext} autoComplete="new-password" minLength="8" invalid={Boolean(errors.new_password)} /></Field>
      <Field label={t('Confirm password')} error={errors.confirm_password}><PasswordInput value={confirm} onChange={setConfirm} autoComplete="new-password" minLength="8" invalid={Boolean(errors.confirm_password)} /></Field>
      {errors.form && <div className="alert error form-wide" role="alert">{errors.form}</div>}
      <div className="form-actions"><button className="button primary" disabled={saving || !current || !next || !confirm} aria-busy={saving}>{saving ? t('Saving securely…') : t('Change password')}</button></div>
    </form>
  </section>;
}

function ParentAccessSection() {
  const [state, setState] = useState({ loading: true, error: '', data: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    api.myParents().then(
      (data) => { if (active) setState({ loading: false, error: '', data }); },
      (error) => { if (active) setState({ loading: false, error: error.message, data: null }); },
    );
    return () => { active = false; };
  }, [attempt]);
  const retry = () => { setState({ loading: true, error: '', data: null }); setAttempt((value) => value + 1); };
  const parents = state.data?.parents || [];
  const always = (state.data?.always_visible || []).filter((key) => ALWAYS_VISIBLE[key]);
  const never = (state.data?.never_visible || []).filter((key) => NEVER_VISIBLE[key]);
  return <section className="panel account-settings-panel account-parent-access" aria-labelledby="account-parents-title">
    <header><UsersRound size={18} aria-hidden="true" /><h2 id="account-parents-title">{t('Who can see my data')}</h2></header>
    <div className="panel-body">
      {state.loading && <p className="account-settings-muted" role="status">{t('Loading…')}</p>}
      {state.error && <div className="data-state error" role="alert"><div><b>{t('Some information could not be loaded')}</b><p>{state.error}</p></div><button type="button" className="button quiet small" onClick={retry}><RefreshCw size={14} /> {t('Retry')}</button></div>}
      {state.data && !parents.length && <p className="account-settings-muted">{t('No parent or guardian is linked to your account.')}</p>}
      {parents.length > 0 && <ul className="account-parent-list">{parents.map((parent) => <li key={parent.id}>
        <div className="account-parent-heading"><b>{parent.name}</b><span className="account-parent-relationship">{t(RELATIONSHIPS[parent.relationship] || 'Other')}</span><span className={`badge ${parent.status === 'active' ? 'approved' : 'open'}`}>{parent.status === 'active' ? t('Can see your data') : t('Invitation pending')}</span></div>
        {parent.status === 'active' ? <p className="account-settings-muted">{parent.consented_at ? t('Linked since {date}', { date: dateText(parent.consented_at) }) : t('Linked')}</p> : <p className="account-settings-muted">{t('Sees nothing until they accept the invitation.')}</p>}
        <ul className="account-parent-sections" aria-label={t('Sections')}>
          {always.map((key) => <li key={key} className="is-visible">{t(ALWAYS_VISIBLE[key])}</li>)}
          {Object.entries(SECTIONS).map(([key, name]) => <li key={key} className={parent.sections?.[key] ? 'is-visible' : 'is-hidden'}>{t(name)}<span className="sr-only">{parent.sections?.[key] ? ` — ${t('visible')}` : ` — ${t('hidden')}`}</span></li>)}
        </ul>
      </li>)}</ul>}
      {state.data && never.length > 0 && <p className="account-parent-never"><ShieldCheck size={16} aria-hidden="true" /><span>{t('Parents never see: {list}.', { list: never.map((key) => t(NEVER_VISIBLE[key])).join(', ') })}</span></p>}
      {state.data && <p className="account-settings-muted">{t('Ask your counselor to change who can see your data or which sections they see.')}</p>}
    </div>
  </section>;
}

export function AccountSettingsPage({ user, language, changeLanguage, onUserChange, notify }) {
  const student = user.role === 'student';
  return <div className="section-stack account-settings">
    {!student && <ProfileSection user={user} onUserChange={onUserChange} notify={notify} />}
    <EmailSection user={user} onUserChange={onUserChange} notify={notify} />
    <PasswordSection onUserChange={onUserChange} notify={notify} />
    <section className="panel account-settings-panel" aria-labelledby="account-language-title">
      <header><Globe2 size={18} aria-hidden="true" /><h2 id="account-language-title">{t('Language')}</h2></header>
      <div className="panel-body account-language"><p className="account-settings-muted">{t('Choose the language for Naseeb Edu on this device.')}</p><LanguageSelector language={language} onChange={changeLanguage} /></div>
    </section>
    {student && <ParentAccessSection />}
  </div>;
}
