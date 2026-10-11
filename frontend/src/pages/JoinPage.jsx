import { useEffect, useState } from 'react';
import { CheckCircle2, Clock3, LogIn, UserPlus } from 'lucide-react';
import { api } from '../api';
import { t } from '../i18n';
import { gradeText } from '../lib/format';
import { initials } from '../lib/labels';
import { BrandLockup, LanguageSelector, ThemeToggle } from '../components/brand';
import { Field } from '../components/forms';
import '../invites.css';

const GRADES = ['8', '9', '10', '11', 'gap'];

function Card({ theme, toggleTheme, language, changeLanguage, children, footer }) {
  return <main className="password-change-page join-page"><section className="password-change-card">
    <header><BrandLockup theme={theme} /><div className="password-change-preferences"><LanguageSelector language={language} onChange={changeLanguage} compact /><ThemeToggle theme={theme} onToggle={toggleTheme} /></div></header>
    {children}
    {footer && <footer>{footer}</footer>}
  </section></main>;
}

// Which school and counselor the student is joining (schools have no logo yet: their initials).
function SchoolCard({ school, counselor }) {
  return <div className="join-school">
    <span className="join-school-logo" aria-hidden="true">{initials(school.name)}</span>
    <span className="join-school-copy"><span>{t('You are joining')}</span><b>{school.name}</b>{counselor && <small>{t('Counselor: {name}', { name: counselor })}</small>}</span>
  </div>;
}

// /join/<token>: a personal invite (details prefilled) or a magic link (the student types them).
export function JoinPage({ token, onSignIn, ...chrome }) {
  const [invite, setInvite] = useState(null);
  const [failure, setFailure] = useState('');
  const [form, setForm] = useState({ first_name: '', last_name: '', email: '', phone: '', grade: '', username: '', password: '', confirm: '' });
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [joined, setJoined] = useState(null);
  useEffect(() => {
    let live = true;
    api.joinInvite(token).then((info) => {
      if (!live) return;
      setInvite(info);
      if (info.student) setForm((current) => ({ ...current, ...Object.fromEntries(Object.entries(info.student).map(([key, value]) => [key, value || ''])) }));
    }, (error) => { if (live) setFailure(error.message); });
    return () => { live = false; };
  }, [token]);
  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }));
  const personal = invite?.kind === 'personal';

  async function submit(event) {
    event.preventDefault();
    if (form.password !== form.confirm) { setErrors({ confirm: t('Passwords do not match.') }); return; }
    setSaving(true); setErrors({});
    const { confirm: _confirm, ...payload } = form;
    try {
      setJoined(await api.acceptInvite(token, payload));
    } catch (error) {
      const details = error.details || {};
      const fieldErrors = Object.fromEntries(['first_name', 'last_name', 'email', 'phone', 'grade', 'username', 'password']
        .filter((key) => details[key]).map((key) => [key, [].concat(details[key]).join(' ')]));
      if (error.status === 404) setFailure(error.message);
      setErrors(Object.keys(fieldErrors).length ? fieldErrors : { form: error.message });
    } finally {
      setSaving(false);
    }
  }

  if (joined) return <Card {...chrome}>
    <div className="password-change-intro join-success" role="status">
      <span className="password-change-icon"><CheckCircle2 size={24} /></span>
      <h1>{t('Your account is ready')}</h1>
      <p>{t('{counselor} will confirm you as a student of {school}. Until then you can sign in and see only a waiting screen.', { counselor: joined.counselor_name, school: joined.school_name })}</p>
      <p>{t('Your username: {username}', { username: joined.username })}</p>
      <button type="button" className="button primary" onClick={onSignIn}><LogIn size={17} />{t('Sign in')}</button>
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

  const field = (key, title, props = {}) => <Field label={title} error={errors[key]}><input value={form[key]} onChange={set(key)} aria-invalid={Boolean(errors[key])} {...props} /></Field>;
  return <Card {...chrome} footer={t('Your counselor confirms you before you can use Naseeb Edu.')}>
    <SchoolCard school={invite.school} counselor={invite.counselor?.name} />
    <div className="password-change-intro">
      <span className="eyebrow">{personal ? t('Personal invitation') : t('Join link')}</span>
      <h1>{t('Create your student account')}</h1>
      <p>{personal ? t('Check your details, then choose a username and password.') : t('Enter your name and email, then choose a username and password.')}</p>
    </div>
    <form className="form-grid" onSubmit={submit}>
      {field('first_name', t('First name'), { required: true, maxLength: 150, autoComplete: 'given-name' })}
      {field('last_name', t('Last name'), { required: true, maxLength: 150, autoComplete: 'family-name' })}
      {field('email', t('Email'), { type: 'email', required: true, autoComplete: 'email', readOnly: personal })}
      {field('phone', t('Phone (optional)'), { type: 'tel', maxLength: 32, autoComplete: 'tel' })}
      <Field label={t('Grade')} error={errors.grade}><select value={form.grade} onChange={set('grade')}><option value="">{t('Not set')}</option>{GRADES.map((grade) => <option key={grade} value={grade}>{gradeText(grade)}</option>)}</select></Field>
      {field('username', t('Username'), { required: true, maxLength: 150, autoComplete: 'username', autoCapitalize: 'none', spellCheck: false })}
      {field('password', t('Password'), { type: 'password', required: true, minLength: 8, autoComplete: 'new-password' })}
      {field('confirm', t('Confirm password'), { type: 'password', required: true, minLength: 8, autoComplete: 'new-password' })}
      {errors.form && <div className="alert error form-wide" role="alert">{errors.form}</div>}
      <div className="form-actions form-wide">
        <button type="button" className="button quiet" onClick={onSignIn}>{t('I already have an account')}</button>
        <button className="button primary" disabled={saving} aria-busy={saving}><UserPlus size={17} />{saving ? t('Creating…') : t('Create account')}</button>
      </div>
    </form>
  </Card>;
}

// A student who joined by invite, before their counselor confirms them: the only screen they get.
export function AwaitingConfirmation({ user, onCheck, onSignOut, ...chrome }) {
  const [checking, setChecking] = useState(false);
  const pending = user.pending_join || {};
  async function check() {
    setChecking(true);
    try { await onCheck(); } finally { setChecking(false); }
  }
  return <Card {...chrome} footer={`${user.first_name || user.username} · ${user.username}`}>
    {pending.school_name && <SchoolCard school={{ name: pending.school_name }} counselor={pending.counselor_name} />}
    <div className="password-change-intro" role="status">
      <span className="password-change-icon"><Clock3 size={24} /></span>
      <h1>{t('Waiting for your counselor to confirm you')}</h1>
      <p>{t('Your account is ready. As soon as your counselor confirms you, your workspace opens here.')}</p>
    </div>
    <div className="form-actions">
      <button type="button" className="button quiet" onClick={onSignOut}>{t('Sign out')}</button>
      <button type="button" className="button primary" onClick={check} disabled={checking} aria-busy={checking}>{checking ? t('Checking…') : t('Check again')}</button>
    </div>
  </Card>;
}
