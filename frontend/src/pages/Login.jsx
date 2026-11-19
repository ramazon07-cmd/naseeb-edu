import { useId, useState } from 'react';
import { api } from '../api';
import { ArrowLeft, ArrowRight, Check, Circle, Eye, EyeOff, Lock, LogOut, Mail, User } from 'lucide-react';
import { t } from '../i18n';
import { Field, PasswordInput } from '../components/forms';
import { LanguagePicker, LoginThemeToggle } from '../design/blue/controls';
import { useLoginTheme } from '../design/blue/theme';
import '../design/blue/tokens.css';
import '../design/blue/login.css';
import { GRADES, gradeText } from '../lib/format';
import { fullName } from '../lib/labels';

import { forgetRememberedUsername, rememberUsername, rememberedUsername } from '../lib/rememberedUsername';
export const SHOW_DEMO_ACCOUNTS = import.meta.env.DEV && import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === 'true';

export { forgetRememberedUsername };

function greeting() {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) return `${t('Good morning')}!`;
  if (hour >= 12 && hour < 17) return `${t('Good afternoon')}!`;
  return `${t('Good evening')}!`;
}

// The sign-in backdrop, top bar (logo, language, theme) and footer, shared by
// the sign-in form and the first-password step.
function LoginFrame({ language, changeLanguage, onBrand, brandLabel, leave, children }) {
  const theme = useLoginTheme();
  return <main className="nb-login" data-nb-theme={theme.mode} data-nb-read={theme.reading ? 'true' : 'false'}>
    <div className="nb-backdrop" aria-hidden="true" />
    <header className="nb-login-bar">
      {onBrand ?
      <button type="button" className="nb-login-brand" onClick={onBrand} aria-label={brandLabel}><span className="nb-login-logo" aria-hidden="true" /><b>{t('Naseeb Edu')}</b></button> :
      <span className="nb-login-brand"><span className="nb-login-logo" aria-hidden="true" /><b>{t('Naseeb Edu')}</b></span>}
      <div className="nb-login-prefs">
        {leave}
        <LanguagePicker language={language} onChange={changeLanguage} variant="segmented" />
        <LoginThemeToggle />
      </div>
    </header>
    {children}
    <footer className="nb-login-footer">© {new Date().getFullYear()} {t('Naseeb Edu')}</footer>
  </main>;
}

function LoginHead({ eyebrow = true, title, titleId, children }) {
  return <div className="nb-login-head">
    <span className="nb-login-emblem" aria-hidden="true"><span className="nb-login-logo" /></span>
    {eyebrow && <span className="nb-login-eyebrow">{t('NASEEB EDU')}</span>}
    <h1 id={titleId}>{title}</h1>
    {children}
  </div>;
}

export function Login({ onLogin, onBack, language, changeLanguage }) {
  const [form, setForm] = useState(() => {
    if (SHOW_DEMO_ACCOUNTS) return { username: 'counselor', password: 'admin12345' };
    return { username: rememberedUsername(), password: '' };
  });
  const [remember, setRemember] = useState(() => !SHOW_DEMO_ACCOUNTS && Boolean(rememberedUsername()));
  const [showPassword, setShowPassword] = useState(false);
  const [forgot, setForgot] = useState(false);
  const [firstTime, setFirstTime] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  // The card lifts away once the server accepts the sign-in, while the workspace loads.
  const [leaving, setLeaving] = useState(false);
  const [welcome] = useState(greeting);
  const ids = { user: useId(), pass: useId(), help: useId(), first: useId() };

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      await api.login(form.username, form.password);
      rememberUsername(remember ? form.username : '');
      setLeaving(true);
      await onLogin();
    } catch (err) {
      setLeaving(false);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const passwordLabel = showPassword ? t('Hide password') : t('Show password');
  return (
    <LoginFrame {...{ language, changeLanguage }} onBrand={onBack} brandLabel={t('Home')} leave={onBack ? <button type="button" className="nb-login-leave" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" /> {t('Home')}</button> : null}>
      <section className="nb-login-panel" aria-label={t('Sign in')}>
        <form className={`nb-login-card${leaving ? ' is-leaving' : ''}`} onSubmit={submit}>
          <LoginHead title={welcome}>
            <p className="nb-login-tagline">{t('Connecting Students to the World Through Education')}</p>
          </LoginHead>
          <div className="nb-login-field">
            <label htmlFor={ids.user}>{t('Username')}</label>
            <span className="nb-login-input">
              <User size={18} aria-hidden="true" />
              <input id={ids.user} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} autoComplete="username" required />
            </span>
          </div>
          <div className="nb-login-field">
            <label htmlFor={ids.pass}>{t('Password')}</label>
            <span className="nb-login-input">
              <Lock size={18} aria-hidden="true" />
              <input id={ids.pass} type={showPassword ? 'text' : 'password'} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="current-password" required />
              <button type="button" className="nb-login-eye" onClick={() => {setShowPassword(!showPassword);document.getElementById(ids.pass)?.focus();}} aria-label={passwordLabel} title={passwordLabel} aria-pressed={showPassword}>{showPassword ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}</button>
            </span>
          </div>
          <div className="nb-login-row">
            <label className="nb-login-check"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /><span className="nb-login-box" aria-hidden="true"><Check size={13} strokeWidth={3} /></span><span>{t('Remember me')}</span></label>
            <button type="button" className="nb-login-link" aria-expanded={forgot} aria-controls={ids.help} onClick={() => setForgot(!forgot)}>{t('Forgot password?')}</button>
          </div>
          {/* There is no self-service reset: accounts are issued by the school. */}
          <p id={ids.help} className="nb-login-help is-info" hidden={!forgot}><Mail size={18} aria-hidden="true" /><span>{t("Forgot your username or password? Ask your school counselor or administrator to reset your login.")}</span></p>
          {error && <div className="nb-login-error" role="alert">{error}</div>}
          <button className="nb-login-submit" disabled={loading} aria-busy={loading}>
            {loading ? t("Signing in…") : t("Sign in")}
            {loading ? <span className="nb-login-spin" aria-hidden="true" /> : <ArrowRight size={18} aria-hidden="true" />}
          </button>
          <button type="button" className="nb-login-link nb-login-first" aria-expanded={firstTime} aria-controls={ids.first} onClick={() => { const open = !firstTime; setFirstTime(open); if (open) document.getElementById(ids.user)?.focus(); }}><Lock size={18} aria-hidden="true" /><span>{t('First sign-in with a temporary password')}</span><ArrowRight size={18} aria-hidden="true" className="nb-login-first-go" /></button>
          {/* The same sign-in form: after it, the app asks for a new password. */}
          <p id={ids.first} className="nb-login-help is-info" hidden={!firstTime}><span>{t('Enter your username and the temporary password from your counselor, then press Sign in. You will choose your own password next.')}</span></p>
          {SHOW_DEMO_ACCOUNTS && (
            <div className="nb-login-demo">{t("Demo: counselor / admin12345")}</div>
          )}
        </form>
      </section>
    </LoginFrame>
  );
}

// Django's UserAttributeSimilarityValidator (max_similarity 0.7), so the checklist refuses what the server refuses.
function looksLikeAccount(password, user) {
  const typed = Array.from(password.toLowerCase());
  return [user.username, user.first_name, user.last_name, user.email].some((value) => {
    if (!value) return false;
    const whole = value.toLowerCase();
    return [...whole.split(/[^\p{L}\p{N}_]+/u), whole].some((part) => {
      const chars = Array.from(part);
      if (typed.length >= 10 * chars.length && chars.length < 0.35 * typed.length) return false;
      const left = {};
      chars.forEach((char) => {left[char] = (left[char] || 0) + 1;});
      const shared = typed.filter((char) => left[char] > 0 && left[char]--).length;
      return 2 * shared / (typed.length + chars.length) >= 0.7;
    });
  });
}

// First sign-in with a temporary password: the sign-in page's backdrop and card,
// so choosing a password reads as the next step of signing in.
export function ForcedPasswordChange({ user, onChanged, onSignOut, language, changeLanguage }) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [grade, setGrade] = useState('');
  const isStudent = user.role === 'student';
  // A new student picks their class here and their counselor sees it next to their name;
  // a student with a finished profile (a reissued login) already has one.
  const asksClass = isStudent && !user.student_profile_complete;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // What the browser can check while they type; the server also refuses common passwords.
  const checks = [
    [t('At least 8 characters'), password.length >= 8],
    [t('Not only numbers'), password !== '' && !/^\d+$/.test(password)],
    [t('Not like your name or login'), password !== '' && !looksLikeAccount(password, user)],
    [t('Both passwords match'), confirmPassword !== '' && password === confirmPassword],
  ];
  async function submit(event) {
    event.preventDefault();
    if (password !== confirmPassword) {setError(t('Passwords do not match.'));return;}
    setSaving(true);setError('');
    try {const result = await api.changePassword(password, confirmPassword, grade);await onChanged(result.user);}
    catch (requestError) {setError(requestError.message);} finally
    {setSaving(false);}
  }
  return <LoginFrame {...{ language, changeLanguage }} leave={<button type="button" className="nb-login-leave" onClick={onSignOut}><LogOut size={16} aria-hidden="true" /> {t('Sign out')}</button>}>
    <section className="nb-login-panel" aria-labelledby="password-change-title">
      <form className="nb-login-card" onSubmit={submit}>
        <LoginHead eyebrow={false} titleId="password-change-title" title={t('Welcome, {name}', { name: user.first_name || fullName(user) })}>
          <p className="nb-login-tagline">{t('Set your own password to open your cabinet. From now on you sign in with it.')}</p>
        </LoginHead>
        {asksClass && <fieldset className="nb-login-classes"><legend>{t('Your class')}</legend><div className="nb-login-class-grid">{GRADES.map((value, index) => <label key={value} className="nb-login-class" title={gradeText(value)}><input type="radio" name="student-class" value={value} checked={grade === value} onChange={() => setGrade(value)} required={index === 0} /><span aria-hidden="true">{value}</span><span className="sr-only">{gradeText(value)}</span></label>)}</div></fieldset>}
        <Field label={t('New password')}><PasswordInput value={password} onChange={setPassword} autoComplete="new-password" minLength="8" /></Field>
        <Field label={t('Confirm password')}><PasswordInput value={confirmPassword} onChange={setConfirmPassword} autoComplete="new-password" minLength="8" /></Field>
        <ul className="password-checks" aria-label={t('Password requirements')}>
          {checks.map(([text, met]) => <li key={text} className={met ? 'is-met' : undefined}>{met ? <Check size={15} aria-hidden="true" /> : <Circle size={15} aria-hidden="true" />}<span className="sr-only">{met ? t('Done') : t('Not yet')}: </span>{text}</li>)}
        </ul>
        {error && <div className="nb-login-error" role="alert">{error}</div>}
        <button className="nb-login-submit" disabled={saving} aria-busy={saving}>{saving ? t('Saving securely…') : t('Save new password')}<ArrowRight size={18} aria-hidden="true" /></button>
        <p className="nb-login-help">{isStudent ? t('If you sign out now, ask your counselor for a new temporary password.') : t('Your temporary password has already been consumed. If you leave now, an administrator must reissue it.')}</p>
      </form>
    </section>
  </LoginFrame>;
}

