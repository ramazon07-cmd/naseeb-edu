import { useEffect, useId, useRef, useState } from 'react';
import { Check, ChevronDown, Globe2, Moon, Sun } from 'lucide-react';
import { LANGUAGE_OPTIONS, t } from '../../i18n';
import { BLUE_MODES, isDarkMode, useBlueTheme, useLoginTheme } from './theme';

// A button that opens a small menu: closes on outside press, Escape and blur.
function useMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const outside = (event) => { if (!ref.current?.contains(event.target)) setOpen(false); };
    const escape = (event) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      ref.current?.querySelector('[aria-haspopup]')?.focus();
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [open]);
  return { open, setOpen, ref };
}

// EN / UZ / RU. `variant="segmented"` (sign-in page) shows all three as pills;
// the default is the shell's compact "globe EN v" menu.
export function LanguagePicker({ language, onChange, variant = 'menu' }) {
  const menu = useMenu();
  const id = useId();
  const current = LANGUAGE_OPTIONS.find((option) => option.value === language) || LANGUAGE_OPTIONS[0];
  if (variant === 'segmented') {
    const order = ['uz', 'ru', 'en'].map((value) => LANGUAGE_OPTIONS.find((option) => option.value === value)).filter(Boolean);
    return <div className="nb-lang-seg" role="group" aria-label={t('Language')}>
      {order.map((option) => <button key={option.value} type="button" aria-pressed={option.value === language} lang={option.value} title={option.label} onClick={() => onChange(option.value)}>{option.short}</button>)}
    </div>;
  }
  return <div className="nb-menu-wrap" ref={menu.ref}>
    <button type="button" className="nb-control nb-lang-button" aria-haspopup="menu" aria-expanded={menu.open} aria-controls={menu.open ? id : undefined} aria-label={`${t('Language')}: ${current.label}`} onClick={() => menu.setOpen(!menu.open)}>
      <Globe2 size={17} aria-hidden="true" /><b>{current.short}</b><ChevronDown size={14} aria-hidden="true" />
    </button>
    {menu.open && <div className="nb-menu" id={id} role="menu" aria-label={t('Language')}>
      {LANGUAGE_OPTIONS.map((option) => <button key={option.value} type="button" role="menuitemradio" aria-checked={option.value === language} lang={option.value} onClick={() => { onChange(option.value); menu.setOpen(false); }}>
        <span>{option.label}</span>{option.value === language && <Check size={16} aria-hidden="true" />}
      </button>)}
    </div>}
  </div>;
}

const MODE_LABELS = () => ({ light: t('Light'), tinted: t('Dark · Tinted'), night: t('Dark · Night') });

// The sign-in page's single moon button. It uses the sign-in page's own
// appearance store, so it never changes the in-app student theme.
export function LoginThemeToggle() {
  const theme = useLoginTheme();
  const label = isDarkMode(theme.mode) ? t('Light') : t('Dark · Tinted');
  const CurrentIcon = isDarkMode(theme.mode) ? Moon : Sun;
  return <button type="button" className="nb-control nb-icon-control" onClick={theme.toggleDark} aria-label={label} title={label}><CurrentIcon size={18} aria-hidden="true" /></button>;
}

// Light / Dark Tinted / Dark Night plus Reading mode (menu), for the student app.
export function ThemePicker() {
  const theme = useBlueTheme();
  const menu = useMenu();
  const id = useId();
  const labels = MODE_LABELS();
  const CurrentIcon = isDarkMode(theme.mode) ? Moon : Sun;
  return <div className="nb-menu-wrap" ref={menu.ref}>
    <button type="button" className="nb-control nb-icon-control" aria-haspopup="menu" aria-expanded={menu.open} aria-controls={menu.open ? id : undefined} aria-label={`${t('Theme')}: ${labels[theme.mode]}`} title={t('Theme')} onClick={() => menu.setOpen(!menu.open)}>
      <CurrentIcon size={18} aria-hidden="true" />
    </button>
    {menu.open && <div className="nb-menu nb-theme-menu" id={id} role="menu" aria-label={t('Theme')}>
      {BLUE_MODES.map((mode) => {
        return <button key={mode} type="button" role="menuitemradio" aria-checked={theme.mode === mode} onClick={() => theme.setMode(mode)}>
          <i className={`nb-swatch nb-swatch-${mode}`} aria-hidden="true" /><span>{labels[mode]}</span>{theme.mode === mode && <Check size={16} aria-hidden="true" />}
        </button>;
      })}
      <hr />
      <button type="button" role="menuitemcheckbox" aria-checked={theme.reading} onClick={() => theme.setReading(!theme.reading)}>
        <i className="nb-swatch nb-swatch-read" aria-hidden="true" /><span>{t('Reading mode')}</span>{theme.reading && <Check size={16} aria-hidden="true" />}
      </button>
    </div>}
  </div>;
}
