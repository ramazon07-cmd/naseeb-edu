import { useState } from 'react';
import { api } from '../api';
import { ArrowLeft, Check, ChevronRight, Circle, LogOut } from 'lucide-react';
import { t } from '../i18n';
import { LanguageSelector, BrandLogo } from '../components/brand';
import { Field, PasswordInput } from '../components/forms';
import { fullName } from '../lib/labels';

export const SHOW_DEMO_ACCOUNTS = import.meta.env.DEV && import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === 'true';

export function Login({ onLogin, onBack, theme, language, changeLanguage }) {
  const [form, setForm] = useState(SHOW_DEMO_ACCOUNTS ?
  { username: 'counselor', password: 'admin12345' } :
  { username: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      await api.login(form.username, form.password);
      await onLogin();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <header className="login-bar">
        <button type="button" className="login-return" onClick={onBack}>
          <ArrowLeft size={17} /> {t("Home")}
        </button>
        <div className="login-preferences">
          <LanguageSelector
            language={language}
            onChange={changeLanguage}
            compact
          />
        </div>
      </header>
      <section className="login-form-panel" aria-label={t("Sign in")}>
        <form className="login-card" onSubmit={submit}>
          <div className="login-card-head">
            <BrandLogo theme={theme} className="login-emblem" />
            <h1>{t("Naseeb Edu")}</h1>
            <span className="brand-tagline">
              {t("Connecting Students to the World Through Education")}
            </span>
          </div>
          <Field label={t("Username")}>
            <input
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              autoComplete="username"
              required
            />
          </Field>
          <Field label={t("Password")}>
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              autoComplete="current-password"
              required
            />
          </Field>
          {error && <div className="alert error" role="alert">{error}</div>}
          <button
            className="button primary full"
            disabled={loading}
            aria-busy={loading}
          >
            {loading ? t("Signing in…") : t("Sign in")}
            <ChevronRight size={18} />
          </button>
          {/* There is no self-service reset: accounts are issued by the school. */}
          <p className="login-help">{t("Forgot your username or password? Ask your school counselor or administrator to reset your login.")}</p>
          {SHOW_DEMO_ACCOUNTS && (
            <div className="demo-hint">{t("Demo: counselor / admin12345")}</div>
          )}
        </form>
      </section>
    </main>
  );
}

// First sign-in with a temporary password: the sign-in page's backdrop and card,
// so choosing a password reads as the next step of signing in.
export function ForcedPasswordChange({ user, onChanged, onSignOut, theme, language, changeLanguage }) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // What the browser can check while they type; the server also refuses common passwords and ones like the name.
  const checks = [
    [t('At least 8 characters'), password.length >= 8],
    [t('Not only numbers'), password !== '' && !/^\d+$/.test(password)],
    [t('Both passwords match'), confirmPassword !== '' && password === confirmPassword],
  ];
  async function submit(event) {
    event.preventDefault();
    if (password !== confirmPassword) {setError(t('Passwords do not match.'));return;}
    setSaving(true);setError('');
    try {const result = await api.changePassword(password, confirmPassword);await onChanged(result.user);}
    catch (requestError) {setError(requestError.message);} finally
    {setSaving(false);}
  }
  return <main className="login-page">
    <header className="login-bar">
      <button type="button" className="login-return" onClick={onSignOut}><LogOut size={17} aria-hidden="true" /> {t('Sign out')}</button>
      <div className="login-preferences"><LanguageSelector language={language} onChange={changeLanguage} compact /></div>
    </header>
    <section className="login-form-panel" aria-labelledby="password-change-title">
      <form className="login-card" onSubmit={submit}>
        <div className="login-card-head">
          <BrandLogo theme={theme} className="login-emblem password-emblem" />
          <h1 id="password-change-title">{t('Welcome, {name}', { name: user.first_name || fullName(user) })}</h1>
          <p className="password-change-lead">{t('Set your own password to open your cabinet. From now on you sign in with it.')}</p>
        </div>
        <Field label={t('New password')}><PasswordInput value={password} onChange={setPassword} autoComplete="new-password" minLength="8" /></Field>
        <Field label={t('Confirm password')}><PasswordInput value={confirmPassword} onChange={setConfirmPassword} autoComplete="new-password" minLength="8" /></Field>
        <ul className="password-checks" aria-label={t('Password requirements')}>
          {checks.map(([text, met]) => <li key={text} className={met ? 'is-met' : undefined}>{met ? <Check size={15} aria-hidden="true" /> : <Circle size={15} aria-hidden="true" />}<span className="sr-only">{met ? t('Done') : t('Not yet')}: </span>{text}</li>)}
        </ul>
        {error && <div className="alert error" role="alert">{error}</div>}
        <button className="button primary full" disabled={saving} aria-busy={saving}>{saving ? t('Saving securely…') : t('Save new password')}<ChevronRight size={18} aria-hidden="true" /></button>
        <p className="login-help">{user.role === 'student' ? t('If you sign out now, ask your counselor for a new temporary password.') : t('Your temporary password has already been consumed. If you leave now, an administrator must reissue it.')}</p>
      </form>
    </section>
  </main>;
}

