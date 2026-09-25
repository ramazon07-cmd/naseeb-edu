import { t, LANGUAGE_OPTIONS } from '../i18n';
import { Globe2, WifiOff, RefreshCw, Sun, Moon } from 'lucide-react';

export const THEME_ICONS = {
  light: '/brand/favicon-light-32.png',
  dark: '/brand/favicon-dark-32.png',
};

export function themeIconFor(theme) {
  return THEME_ICONS[theme] || THEME_ICONS.light;
}

export function BrandLogo({ className = '' }) {return <span className={`brand-logo ${className}`} role="img" aria-label={t("Naseeb Edu")} />;}

export function BrandLockup({ theme, subtitle = true }) {
  return <div className="brand-lockup"><BrandLogo theme={theme} /><div><b>{t("Naseeb Edu")}</b>{subtitle && <small>{t('Education Counseling Platform')}</small>}</div></div>;
}

export function LanguageSelector({ language, onChange, compact = false }) {
  return <label className={`language-selector ${compact ? 'compact' : ''}`} aria-label={t('Language')}><Globe2 size={15} /><select value={language} onChange={(event) => onChange(event.target.value)}>{LANGUAGE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{compact ? option.short : option.label}</option>)}</select></label>;
}

export function AppBootLoader({ message = 'Preparing your workspace…' }) {
  return <main className="app-boot" role="status" aria-label={message}><div className="app-boot-card"><div className="app-boot-mark" aria-hidden="true"><i /></div><div className="app-boot-copy"><b>{t("Naseeb Edu")}</b><span>{message}</span></div><div className="app-boot-line" aria-hidden="true" /></div></main>;
}

export function BootstrapError({ message, onRetry, onSignOut }) {
  return <main className="app-boot"><section className="bootstrap-error" role="alert"><WifiOff size={30} /><span className="eyebrow">{t("CONNECTION INTERRUPTED")}</span><h1>{t("We could not open your workspace.")}</h1><p>{message}</p><div><button type="button" className="button primary" onClick={onRetry}><RefreshCw size={16} /> {t("Retry")}</button><button type="button" className="button quiet" onClick={onSignOut}>{t("Return to sign in")}</button></div></section></main>;
}

export function ThemeToggle({ theme, onToggle }) {
  const isDark = theme === 'dark';
  return <button type="button" className="icon-button theme-toggle" onClick={onToggle} title={isDark ? t("Light mode") : t("Dark mode")} aria-label={isDark ? t("Switch to light mode") : t("Switch to dark mode")} aria-pressed={isDark}>{isDark ? <Sun size={18} /> : <Moon size={18} />}</button>;
}
