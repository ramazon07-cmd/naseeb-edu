import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import '@fontsource-variable/roboto/wght.css';
import '../pages/counselor-shell.css';
import { Bell, Calendar, Check, CheckSquare, ChevronDown, ChevronsLeft, ChevronsRight, Compass, Ellipsis, Globe2, LayoutDashboard, LifeBuoy, LogOut, Menu, MessageCircle, Moon, Pencil, Search, Settings, Sun, Users, X } from 'lucide-react';
import { LANGUAGE_OPTIONS, formatNumberLocale, t, tx } from '../i18n';
import { fullName, initials } from '../lib/labels';
import { counselorCounts } from '../lib/counselorCounts';
import { canUseAssistant } from '../lib/assistantAccess';
import { COUNSELOR_NAV } from '../lib/routes';
import { invalidatePagedLists } from '../hooks/usePagedList';
import { CounselorUiContext } from './counselorUi';
import { useAccountPhoto } from './records';

// The sidebar of the "Counselor Dashboard" design: label, icon and the number
// (from counselorCounts) that badges it.
const NAV = {
  dashboard: { label: 'Home', icon: LayoutDashboard },
  students: { label: 'Students', icon: Users, badge: 'students' },
  review: { label: 'Review', icon: CheckSquare, badge: 'review' },
  essays: { label: 'Essays', icon: Pencil, badge: 'essays' },
  bookings: { label: 'Meetings', icon: Calendar, badge: 'meetings' },
  messages: { label: 'Messages', icon: MessageCircle, badge: 'messages' },
  counselor_roadmap: { label: 'Roadmap templates', icon: Compass },
};
// The phone's bottom bar keeps the four daily pages; "More" opens the full list.
const TAB_PAGES = ['dashboard', 'students', 'review', 'messages'];

// Pages that draw their own title row; every other page gets a plain one from the shell.
export const COUNSELOR_SELF_HEADED = new Set(['dashboard', 'students', 'students_joined', 'review', 'bookings', 'notifications', 'messages']);

export const counselorPageLabel = (page) => NAV[page]?.label;

// Pages whose shared description does not fit the counselor workspace.
const DESCRIPTIONS = { account_settings: 'Your profile, password, email and language' };
export const counselorPageDescription = (page) => DESCRIPTIONS[page];

const RAIL_KEY = 'naseeb-edu-counselor-rail';
function readRail() {
  try {
    return window.localStorage.getItem(RAIL_KEY) === '1';
  } catch {
    return false;
  }
}
function writeRail(value) {
  try {
    window.localStorage.setItem(RAIL_KEY, value ? '1' : '0');
  } catch {
    // Only a convenience: the rail just will not be remembered.
  }
}

const SEARCH_SHORTCUT = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || '') ? '⌘K' : 'Ctrl K';

function NavCount({ value }) {
  return value > 0 ? <i className="cx-count">{formatNumberLocale(value)}</i> : null;
}

function useDismiss(open, close, ref) {
  useEffect(() => {
    if (!open) return undefined;
    const outside = (event) => { if (!ref.current?.contains(event.target)) close(); };
    const escape = (event) => { if (event.key === 'Escape') close(); };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [open, close, ref]);
}

function LanguageMenu({ language, changeLanguage }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, close, ref);
  const current = LANGUAGE_OPTIONS.find((option) => option.value === language) || LANGUAGE_OPTIONS[0];
  return <div className="cx-lang" ref={ref}>
    <button type="button" className="cx-topbtn" aria-haspopup="menu" aria-expanded={open} aria-label={`${t('Language')}: ${current.label}`} onClick={() => setOpen(!open)}>
      <Globe2 size={17} aria-hidden="true" /><span>{current.short}</span><ChevronDown size={15} aria-hidden="true" />
    </button>
    {open && <div className="cx-popover cx-lang-menu" role="menu" aria-label={t('Language')}>
      {LANGUAGE_OPTIONS.map((option) => <button type="button" role="menuitemradio" aria-checked={option.value === language} key={option.value} onClick={() => { changeLanguage(option.value); setOpen(false); }}>
        <span>{option.label}</span><b>{option.short}</b>{option.value === language && <Check size={15} aria-hidden="true" />}
      </button>)}
    </div>}
  </div>;
}

function ThemeButton({ theme, toggleTheme, className = 'cx-topbtn cx-topicon' }) {
  const dark = theme === 'dark';
  const label = dark ? t('Switch to light mode') : t('Switch to dark mode');
  return <button type="button" className={className} aria-label={label} title={label} onClick={toggleTheme}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button>;
}

// On the phone the menu also carries language and theme, which the top bar
// has no room for.
function AccountMenu({ user, variant, theme, toggleTheme, language, changeLanguage, logout, openSupport, openAssistant, openAccountSettings, supportBadge, setAccountActionsHost, rail }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const photo = useAccountPhoto(user);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, close, ref);
  const attachActions = useCallback((element) => {
    setAccountActionsHost(element ? { element, close: () => setOpen(false) } : null);
  }, [setAccountActionsHost]);
  const dark = theme === 'dark';
  const name = fullName(user);
  const face = photo ? <img src={photo} alt="" /> : initials(name);
  const phone = variant === 'avatar';
  const trigger = phone
    ? <button type="button" className="cx-avatar self cx-avatar-button" aria-haspopup="menu" aria-expanded={open} aria-label={t('Account menu')} onClick={() => setOpen(!open)}>{face}</button>
    : <button type="button" className="cx-account-trigger" aria-haspopup="menu" aria-expanded={open} aria-label={t('Account menu')} title={rail ? name : undefined} onClick={() => setOpen(!open)}>
      <span className="cx-avatar self" aria-hidden="true">{face}</span>
      <span className="cx-account-copy"><b>{name}</b><small>{user.position || t('School counselor')}</small></span>
      <ChevronDown size={16} className="cx-account-chevron" aria-hidden="true" />
    </button>;
  return <div className={`cx-account cx-account-${variant}`} ref={ref}>
    {trigger}
    {open && <div className="cx-account-menu" role="menu">
      {phone && <div className="cx-menu-row" role="group" aria-label={t('Language')}>
        <span>{t('Language')}</span>
        <div className="cx-segmented">{LANGUAGE_OPTIONS.map((option) => <button type="button" key={option.value} className={language === option.value ? 'active' : ''} aria-pressed={language === option.value} onClick={() => changeLanguage(option.value)}>{option.short}</button>)}</div>
      </div>}
      {phone && <button type="button" role="menuitem" aria-pressed={dark} onClick={toggleTheme}>{dark ? <Sun size={17} /> : <Moon size={17} />}{dark ? t('Light mode') : t('Dark mode')}</button>}
      <button type="button" role="menuitem" onClick={() => { setOpen(false); openAccountSettings(); }}><Settings size={17} />{t('Account settings')}</button>
      {openAssistant && <button type="button" role="menuitem" onClick={() => { setOpen(false); openAssistant(); }}><span className="cx-bird" aria-hidden="true" />{t('Naseeb AI assistant')}</button>}
      {openSupport && <button type="button" role="menuitem" onClick={() => { setOpen(false); openSupport(); }}><LifeBuoy size={17} />{t('Support')}{supportBadge > 0 && <i className="cx-count">{formatNumberLocale(supportBadge)}</i>}</button>}
      <div ref={attachActions} />
      <button type="button" role="menuitem" className="cx-signout" onClick={logout}><LogOut size={17} />{t('Sign out')}</button>
    </div>}
  </div>;
}

export function CounselorLayout({ user, data, stats, bell, page, title, setPage, setQuery, theme, toggleTheme, language, changeLanguage, logout, openNotifications, openSearch, openAssistant, openSupport, supportBadge, children }) {
  const [drawer, setDrawer] = useState(false);
  const [rail, setRail] = useState(readRail);
  const [accountActionsHost, setAccountActionsHost] = useState(null);
  const counts = useMemo(() => counselorCounts(stats, data, new Date(), bell), [stats, data, bell]);
  const ui = useMemo(() => ({ openSearch, counts, stats, accountActionsHost }), [openSearch, counts, stats, accountActionsHost]);
  useEffect(() => {
    if (!drawer) return undefined;
    const escape = (event) => { if (event.key === 'Escape') setDrawer(false); };
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [drawer]);
  const toggleRail = () => setRail((current) => {
    writeRail(!current);
    return !current;
  });
  const go = (next) => { setPage(next); setQuery(''); setDrawer(false); };
  // The full list always opens on the newest notices, never a cached page.
  const openNotificationsPage = () => { invalidatePagedLists(['notifications']); go('notifications'); };
  const account = { user, theme, toggleTheme, language, changeLanguage, logout, rail, openAssistant: canUseAssistant(user) ? openAssistant : null, openSupport: openSupport && (() => { setDrawer(false); openSupport(); }), openAccountSettings: () => go('account_settings'), supportBadge, setAccountActionsHost };
  const item = (next, className = 'cx-nav-item', badges = true) => {
    const { label, icon: Icon, badge } = NAV[next];
    const active = page === next;
    const text = t(label);
    return <button type="button" key={next} className={`${className}${active ? ' active' : ''}`} aria-current={active ? 'page' : undefined} title={rail && badges ? text : undefined} onClick={() => go(next)}>
      <Icon size={18} aria-hidden="true" /><span>{text}</span>{badges && badge && <NavCount value={counts[badge]} />}
    </button>;
  };
  const railLabel = rail ? t('Expand navigation') : t('Collapse navigation');
  const bellCount = counts.notifications;
  const bellLabel = bellCount > 0 ? tx`Notifications, ${bellCount > 99 ? '99+' : formatNumberLocale(bellCount)} unread` : t('Notifications');
  const onNotifications = page === 'notifications';
  return <CounselorUiContext.Provider value={ui}>
    <aside className={`cx-sidebar${drawer ? ' open' : ''}${rail ? ' rail' : ''}`} aria-label={t('Main navigation')}>
      <div className="cx-side-card">
        <div className="cx-brand">
          <span className="cx-logo" role="img" aria-label={t('Naseeb Edu')} /><b>{t('Naseeb Edu')}</b>
          <button type="button" className="cx-rail-toggle" onClick={toggleRail} aria-label={railLabel} title={railLabel} aria-expanded={!rail}>{rail ? <ChevronsRight size={18} /> : <ChevronsLeft size={18} />}</button>
          <button type="button" className="cx-side-close" onClick={() => setDrawer(false)} aria-label={t('Close navigation')}><X size={18} /></button>
        </div>
        <button type="button" className={`cx-nav-item cx-notifications${onNotifications ? ' active' : ''}`} aria-current={onNotifications ? 'page' : undefined} title={rail ? t('Notifications') : undefined} onClick={openNotificationsPage}><Bell size={18} aria-hidden="true" /><span>{t('Notifications')}</span><NavCount value={bellCount} /></button>
        <nav className="cx-nav" aria-label={t('Main navigation')}>{COUNSELOR_NAV.map((next) => item(next))}</nav>
        <AccountMenu {...account} variant="card" />
      </div>
    </aside>
    <div className="cx-column">
      <header className="cx-topbar">
        <button type="button" className="cx-topbtn cx-topicon cx-burger" onClick={() => setDrawer(true)} aria-label={t('Open navigation')} aria-expanded={drawer}><Menu size={20} /></button>
        <b className="cx-topbar-title">{title}</b>
        <button type="button" className="cx-topsearch" onClick={() => { setDrawer(false); openSearch(); }} aria-label={t('Search students and work…')} aria-keyshortcuts="Control+K Meta+K">
          <Search size={17} aria-hidden="true" /><span>{t('Search students and work…')}</span><kbd aria-hidden="true">{SEARCH_SHORTCUT}</kbd>
        </button>
        <LanguageMenu language={language} changeLanguage={changeLanguage} />
        <ThemeButton theme={theme} toggleTheme={toggleTheme} />
        <button type="button" className="cx-topbtn cx-topicon cx-bell" onClick={openNotifications} aria-label={bellLabel} title={bellLabel}><Bell size={18} />{bellCount > 0 && <i className="cx-bell-dot" aria-hidden="true" />}</button>
        <AccountMenu {...account} variant="avatar" />
      </header>
      {children}
    </div>
    <nav className="cx-tabbar" aria-label={t('Quick navigation')}>
      {TAB_PAGES.map((next) => item(next, 'cx-tab', false))}
      <button type="button" className={`cx-tab${drawer ? ' active' : ''}`} aria-expanded={drawer} onClick={() => setDrawer(!drawer)}><Ellipsis size={18} aria-hidden="true" /><span>{t('More')}</span></button>
    </nav>
    {drawer && <button type="button" className="cx-drawer-backdrop" aria-label={t('Close navigation')} onClick={() => setDrawer(false)} />}
  </CounselorUiContext.Provider>;
}
