import { useEffect, useState } from 'react';
import { CheckCircle2, Clock3, LogIn, UserPlus } from 'lucide-react';
import { api } from '../api';
import { t } from '../i18n';
import { fullName } from '../lib/labels';
import { enterAssistantInvite } from '../lib/assistantInviteSession';
import { Field, PasswordInput } from '../components/forms';
import { Card, SchoolCard } from './JoinPage';
import '../invites.css';

// /assistant-invite/<token>: the assistant the counselor invited sets their own username and password.
export function AssistantInvitePage({ token, onSignIn, onLogin, ...chrome }) {
  const [invite, setInvite] = useState(null);
  const [failure, setFailure] = useState('');
  const [form, setForm] = useState({ username: '', password: '', confirm: '' });
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [ready, setReady] = useState(null);
  useEffect(() => {
    let live = true;
    api.assistantInvite(token).then((info) => { if (live) setInvite(info); }, (error) => { if (live) setFailure(error.message); });
    return () => { live = false; };
  }, [token]);
  const set = (key) => (value) => setForm((current) => ({ ...current, [key]: value }));

  async function submit(event) {
    event.preventDefault();
    if (form.password !== form.confirm) { setErrors({ confirm: t('Passwords do not match.') }); return; }
    await complete();
  }

  async function complete(account = null) {
    setSaving(true); setErrors({});
    try {
      const result = await enterAssistantInvite({ token, credentials: { username: form.username, password: form.password }, account }, {
        acceptInvite: api.acceptAssistantInvite,
        signIn: api.login,
        openWorkspace: onLogin,
      });
      setReady(result.account);
      if (result.error) setErrors({ form: result.error.message });
    } catch (error) {
      const details = error.details || {};
      const fieldErrors = Object.fromEntries(['username', 'password'].filter((key) => details[key]).map((key) => [key, [].concat(details[key]).join(' ')]));
      if (error.status === 404) setFailure(error.message);
      setErrors(Object.keys(fieldErrors).length ? fieldErrors : { form: error.message });
    } finally {
      setSaving(false);
    }
  }

  if (ready) return <Card {...chrome}>
    <div className="password-change-intro join-success" role="status">
      <span className="password-change-icon"><CheckCircle2 size={24} /></span>
      <h1>{t('Your account is ready')}</h1>
      <p>{t('You are now {counselor}’s assistant at {school}. Sign in to see the students they give you.', { counselor: ready.counselor_name, school: ready.school_name })}</p>
      <p>{t('Your username: {username}', { username: ready.username })}</p>
      {errors.form && <div className="alert error" role="alert">{errors.form}</div>}
      <button type="button" className="button primary" disabled={saving} aria-busy={saving} onClick={() => complete(ready)}><LogIn size={17} />{saving ? t('Signing in…') : t('Sign in')}</button>
      <button type="button" className="button quiet" disabled={saving} onClick={onSignIn}>{t('Return to sign in')}</button>
    </div>
  </Card>;
  if (failure) return <Card {...chrome}>
    <div className="password-change-intro" role="alert">
      <span className="password-change-icon"><Clock3 size={24} /></span>
      <h1>{t('This link does not work')}</h1>
      <p>{failure}</p>
      <button type="button" className="button quiet" onClick={onSignIn}><LogIn size={17} />{t('Sign in')}</button>
    </div>
  </Card>;
  if (!invite) return <Card {...chrome}><p className="invite-note" role="status">{t('Checking your invitation…')}</p></Card>;

  const { assistant } = invite;
  return <Card {...chrome} footer={t('You see only the students your counselor gives you.')}>
    <SchoolCard school={invite.school} counselor={invite.counselor?.name} />
    <div className="password-change-intro">
      <span className="eyebrow">{t('Assistant invitation')}</span>
      <h1>{t('Set up your assistant account')}</h1>
      <p>{t('{name}, choose the username and password you will sign in with.', { name: fullName(assistant) })}</p>
    </div>
    <form className="form-grid" onSubmit={submit}>
      <Field label={t('Email')}><input value={assistant.email} readOnly /></Field>
      <Field label={t('Username')} error={errors.username}><input value={form.username} onChange={(event) => set('username')(event.target.value)} aria-invalid={Boolean(errors.username)} required maxLength={150} autoComplete="username" autoCapitalize="none" spellCheck={false} /></Field>
      <Field label={t('Password')} error={errors.password}><PasswordInput value={form.password} onChange={set('password')} autoComplete="new-password" invalid={Boolean(errors.password)} required minLength={8} /></Field>
      <Field label={t('Confirm password')} error={errors.confirm}><PasswordInput value={form.confirm} onChange={set('confirm')} autoComplete="new-password" invalid={Boolean(errors.confirm)} required minLength={8} /></Field>
      {errors.form && <div className="alert error form-wide" role="alert">{errors.form}</div>}
      <div className="form-actions form-wide">
        <button type="button" className="button quiet" disabled={saving} onClick={onSignIn}>{t('I already have an account')}</button>
        <button className="button primary" disabled={saving} aria-busy={saving}><UserPlus size={17} />{saving ? t('Creating…') : t('Create account')}</button>
      </div>
    </form>
  </Card>;
}
