import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import '@fontsource-variable/roboto/wght.css';
import { Bell, Calendar, CheckSquare, Compass, Ellipsis, LayoutDashboard, LifeBuoy, LogOut, MessageCircle, Moon, Pencil, Search, Sun, Users, X } from 'lucide-react';
import { LANGUAGE_OPTIONS, formatNumberLocale, t } from '../i18n';
import { fullName, initials } from '../lib/labels';
import { counselorCounts } from '../lib/counselorCounts';
import { COUNSELOR_NAV } from '../lib/routes';
import { CounselorUiContext } from './counselorUi';

// The sidebar of the "Counselor Dashboard" design: label, icon and the number
// (from counselorCounts) that badges it.
const NAV = {
  dashboard: { label: 'Home', icon: LayoutDashboard },
  students: { label: 'Students', icon: Users },
  review: { label: 'Review', icon: CheckSquare, badge: 'review' },
  essays: { label: 'Essays', icon: Pencil, badge: 'essays' },
  bookings: { label: 'Meetings', icon: Calendar, badge: 'meetings' },
  messages: { label: 'Messages', icon: MessageCircle, badge: 'messages' },
  counselor_roadmap: { label: 'Roadmap templates', icon: Compass },
};
// The phone's bottom bar keeps the four daily pages; "More" opens the full list.
const TAB_PAGES = ['dashboard', 'students', 'review', 'messages'];

// Pages that draw their own title row; every other page gets a plain one from the shell.
export const COUNSELOR_SELF_HEADED = new Set(['dashboard', 'students', 'review', 'bookings']);

export const counselorPageLabel = (page) => NAV[page]?.label;

function NavCount({ value }) {
  return value > 0 ? <i className="cx-count">{formatNumberLocale(value)}</i> : null;
}

// The account card (desktop) or avatar (phone) and the menu it opens: language,
// theme, support and sign out — the controls the old top bar carried.
function AccountMenu({ user, variant, theme, toggleTheme, language, changeLanguage, logout, openSupport, openAssistant, supportBadge, setAccountActionsHost }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const attachActions = useCallback((element) => {
    setAccountActionsHost(element ? { element, close: () => setOpen(false) } : null);
  }, [setAccountActionsHost]);
  useEffect(() => {
    if (!open) return undefined;
    const outside = (event) => { if (!ref.current?.contains(event.target)) setOpen(false); };
    const escape = (event) => { if (event.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);
  const dark = theme === 'dark';
  const name = fullName(user);
  const trigger = variant === 'card'
    ? <button type="button" className="cx-account-trigger" aria-haspopup="menu" aria-expanded={open} aria-label={t('Account menu')} onClick={() => setOpen(!open)}>
      <span className="cx-avatar self" aria-hidden="true">{initials(name)}</span>
      <span className="cx-account-copy"><b>{name}</b><small>{t('School counselor')}</small></span>
    </button>
    : <button type="button" className="cx-avatar self cx-avatar-button" aria-haspopup="menu" aria-expanded={open} aria-label={t('Account menu')} onClick={() => setOpen(!open)}>{initials(name)}</button>;
  return <div className={`cx-account cx-account-${variant}`} ref={ref}>
    {trigger}
    {open && <div className="cx-account-menu" role="menu">
      <div className="cx-menu-row" role="group" aria-label={t('Language')}>
        <span>{t('Language')}</span>
        <div className="cx-segmented">{LANGUAGE_OPTIONS.map((option) => <button type="button" key={option.value} className={language === option.value ? 'active' : ''} aria-pressed={language === option.value} onClick={() => changeLanguage(option.value)}>{option.short}</button>)}</div>
      </div>
      <button type="button" role="menuitem" aria-pressed={dark} onClick={toggleTheme}>{dark ? <Sun size={17} /> : <Moon size={17} />}{dark ? t('Light mode') : t('Dark mode')}</button>
      <button type="button" role="menuitem" onClick={() => { setOpen(false); openAssistant(); }}><span className="cx-bird" aria-hidden="true" />{t('Naseeb AI assistant')}</button>
      {openSupport && <button type="button" role="menuitem" onClick={() => { setOpen(false); openSupport(); }}><LifeBuoy size={17} />{t('Support')}{supportBadge > 0 && <i className="cx-count">{formatNumberLocale(supportBadge)}</i>}</button>}
      <div ref={attachActions} />
      <button type="button" role="menuitem" onClick={logout}><LogOut size={17} />{t('Logout')}</button>
    </div>}
  </div>;
}

// Sidebar, phone header and bottom bar around the workspace: the design's
// chrome. `children` is the <main> of the page.
export function CounselorLayout({ user, data, stats, page, title, setPage, setQuery, theme, toggleTheme, language, changeLanguage, logout, openNotifications, openSearch, openAssistant, openSupport, supportBadge, children }) {
  const [drawer, setDrawer] = useState(false);
  const [accountActionsHost, setAccountActionsHost] = useState(null);
  const counts = useMemo(() => counselorCounts(stats, data), [stats, data]);
  const ui = useMemo(() => ({ openSearch, counts, stats, accountActionsHost }), [openSearch, counts, stats, accountActionsHost]);
  useEffect(() => {
    if (!drawer) return undefined;
    const escape = (event) => { if (event.key === 'Escape') setDrawer(false); };
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [drawer]);
  const go = (next) => { setPage(next); setQuery(''); setDrawer(false); };
  const account = { user, theme, toggleTheme, language, changeLanguage, logout, openAssistant, openSupport: openSupport && (() => { setDrawer(false); openSupport(); }), supportBadge, setAccountActionsHost };
  const item = (next, className = 'cx-nav-item', badges = true) => {
    const { label, icon: Icon, badge } = NAV[next];
    const active = page === next;
    return <button type="button" key={next} className={`${className}${active ? ' active' : ''}`} aria-current={active ? 'page' : undefined} onClick={() => go(next)}>
      <Icon size={18} aria-hidden="true" /><span>{t(label)}</span>{badges && badge && <NavCount value={counts[badge]} />}
    </button>;
  };
  return <CounselorUiContext.Provider value={ui}>
    <aside className={`cx-sidebar${drawer ? ' open' : ''}`}>
      <div className="cx-side-card">
        <div className="cx-brand"><span className="cx-logo" role="img" aria-label={t('Naseeb Edu')} /><b>{t('Naseeb Edu')}</b><button type="button" className="cx-side-close" onClick={() => setDrawer(false)} aria-label={t('Close navigation')}><X size={18} /></button></div>
        <button type="button" className="cx-nav-item cx-search-item" onClick={() => { setDrawer(false); openSearch(); }}><Search size={18} aria-hidden="true" /><span>{t('Search')}</span></button>
        <button type="button" className="cx-nav-item cx-notifications" onClick={() => { setDrawer(false); openNotifications(); }}><Bell size={18} aria-hidden="true" /><span>{t('Notifications')}</span><NavCount value={counts.notifications} /></button>
        <nav className="cx-nav" aria-label={t('Main navigation')}>{COUNSELOR_NAV.map((next) => item(next))}</nav>
        <AccountMenu {...account} variant="card" />
      </div>
    </aside>
    {children}
    <header className="cx-mobilebar">
      <span className="cx-logo" role="img" aria-label={t('Naseeb Edu')} />
      <b>{title}</b>
      <AccountMenu {...account} variant="avatar" />
    </header>
    <nav className="cx-tabbar" aria-label={t('Quick navigation')}>
      {TAB_PAGES.map((next) => item(next, 'cx-tab', false))}
      <button type="button" className={`cx-tab${drawer ? ' active' : ''}`} aria-expanded={drawer} onClick={() => setDrawer(!drawer)}><Ellipsis size={18} aria-hidden="true" /><span>{t('More')}</span></button>
    </nav>
    {drawer && <button type="button" className="cx-drawer-backdrop" aria-label={t('Close navigation')} onClick={() => setDrawer(false)} />}
  </CounselorUiContext.Provider>;
}
