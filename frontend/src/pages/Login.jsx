import { useState } from 'react';
import { api } from '../api';
import { ArrowLeft, ChevronRight, Fingerprint, ShieldAlert } from 'lucide-react';
import { t } from '../i18n';
import { LanguageSelector, ThemeToggle, BrandLogo, BrandLockup } from '../components/brand';
import { Field } from '../components/forms';
import { fullName, label } from '../lib/labels';

export const SHOW_DEMO_ACCOUNTS = import.meta.env.DEV && import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === 'true';

export function Login({ onLogin, onBack, theme, toggleTheme, language, changeLanguage }) {
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
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
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

export function ForcedPasswordChange({ user, onChanged, onSignOut, theme, toggleTheme, language, changeLanguage }) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    if (password !== confirmPassword) {setError(t('Passwords do not match.'));return;}
    setSaving(true);setError('');
    try {const result = await api.changePassword(password, confirmPassword);await onChanged(result.user);}
    catch (requestError) {setError(requestError.message);} finally
    {setSaving(false);}
  }
  return <main className="password-change-page"><section className="password-change-card"><header><BrandLockup theme={theme} /><div className="password-change-preferences"><LanguageSelector language={language} onChange={changeLanguage} compact /><ThemeToggle theme={theme} onToggle={toggleTheme} /></div></header><div className="password-change-intro"><span className="password-change-icon"><Fingerprint size={24} /></span><span className="eyebrow">{t('Temporary login')}</span><h1>{t('Change temporary password')}</h1><p>{t('Create a permanent password before opening your cabinet.')}</p></div><form className="form-grid" onSubmit={submit}><Field label={t('New password')} hint={t('Use at least 8 characters with upper/lowercase letters and a number.')}><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength="8" autoComplete="new-password" required /></Field><Field label={t('Confirm password')}><input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} minLength="8" autoComplete="new-password" required /></Field>{error && <div className="alert error form-wide">{error}</div>}<div className="password-change-warning form-wide"><ShieldAlert size={17} /><p>{t('Your temporary password has already been consumed. If you leave now, an administrator must reissue it.')}</p></div><div className="form-actions form-wide"><button type="button" className="button quiet" onClick={onSignOut}>{t('Sign out')}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving securely…") : t("Save new password")}</button></div></form><footer>{fullName(user)} · {user.school_name || label(user.role)}</footer></section></main>;
}
