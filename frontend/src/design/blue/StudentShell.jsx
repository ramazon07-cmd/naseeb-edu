import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bell, Brain, CalendarClock, ChevronRight, ChevronsLeft, ChevronsRight, ClipboardCheck, Clock3, Compass, Download, Globe2, GraduationCap, LayoutDashboard, LifeBuoy, Lock, LogOut, Menu, MessageSquareText, PenLine, School, Search, Settings, ShoppingCart, UsersRound, X } from 'lucide-react';
import { StudentAvatar } from '../../components/records';
import { exportNodePdf } from '../../lib/exportPdf';
import { label as roleLabel, fullName, ownStudent } from '../../lib/labels';
import { canOpenPage, isPageLocked, navigationFor } from '../../lib/routes';
import { t } from '../../i18n';
import { LanguagePicker, ThemePicker } from './controls';
import { useBlueTheme } from './theme';
import { ShellContext } from './ui';

const SIDEBAR_KEY = 'naseeb-edu-sidebar';

// Pages that draw their own blue PageHeader. While their lazy chunk or data is
// still loading the shell does not know that yet, and it used to show a
// fallback heading and wrap the skeleton in the frosted "legacy" panel: when the
// page arrived both vanished and the whole page jumped (layout shift). These
// pages never get them; only a page not on this list can.
const BLUE_HEADER_PAGES = new Set(['dashboard', 'find_personality', 'student_center', 'roadmap', 'tasks', 'bookings', 'messages', 'programs', 'essay_lab', 'applications', 'college_search', 'store', 'notifications']);

// The student navigation in the design's order. A page the account cannot open
// is skipped (Store is the one shown locked). Roadmap is locked for students
// today (lib/routes.js); until it opens, its slot keeps the Tasks page reachable.
function studentNav(user) {
  const offered = new Set(navigationFor(user));
  const slot = canOpenPage('roadmap', user) ? 'roadmap' : 'tasks';
  const items = [
    { key: 'dashboard', label: t('Dashboard'), icon: LayoutDashboard },
    { key: 'find_personality', label: t('Naseeb Mind'), icon: Brain, isNew: true },
    { key: 'student_center', label: t('Student Center'), icon: UsersRound },
    slot === 'roadmap' ? { key: 'roadmap', label: t('Roadmap'), icon: Compass } : { key: 'tasks', label: t('Tasks'), icon: ClipboardCheck },
    { key: 'bookings', label: t('Meetings'), icon: CalendarClock },
    { key: 'messages', label: t('Messages'), icon: MessageSquareText },
    { key: 'programs', label: t('Programs'), icon: Globe2 },
    { key: 'essay_lab', label: t('Essay Lab'), icon: PenLine },
    { key: 'applications', label: t('Applications'), icon: GraduationCap },
    { key: 'college_search', label: t('College Search'), icon: School },
    { key: 'store', label: t('Naseeb Store'), icon: ShoppingCart },
  ];
  return items.filter((item) => offered.has(item.key) || canOpenPage(item.key, user));
}

// `canExport`: the page's content is one a student may print (PDF_EXPORT_PAGES in App.jsx).
export function StudentShell({ user, data, page, pageMeta, setPage, setQuery, language, changeLanguage, bellCount, bellLabel, notificationsOpen, openNotifications, openSearch, unreadChats, supportBadge, logout, canExport, banners, overlays, children }) {
  const theme = useBlueTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const accountRef = useRef(null);
  const [headers, setHeaders] = useState(0);
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(SIDEBAR_KEY) === 'collapsed'; } catch { return false; }
  });
  const nav = studentNav(user);
  const navLabels = Object.fromEntries(nav.map((item) => [item.key, item.label]));
  const shellContext = useMemo(() => ({
    // A page that draws its own PageHeader hides the shell's fallback heading.
    registerPageHeader: () => { setHeaders((count) => count + 1); return () => setHeaders((count) => Math.max(0, count - 1)); },
  }), []);

  useEffect(() => {
    function outside(event) { if (!accountRef.current?.contains(event.target)) setProfileOpen(false); }
    function keys(event) {
      if (event.key !== 'Escape') return;
      setProfileOpen(false);
      setMobileOpen(false);
    }
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', keys);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', keys); };
  }, []);

  const toggleSidebar = useCallback(() => {
    setCollapsed((current) => {
      const next = !current;
      try { localStorage.setItem(SIDEBAR_KEY, next ? 'collapsed' : 'expanded'); } catch { /* Collapse is a per-browser convenience only. */ }
      return next;
    });
  }, []);
  const go = (key) => { setPage(key); setQuery(''); setMobileOpen(false); setProfileOpen(false); };
  const collapseLabel = collapsed ? t('Expand navigation') : t('Collapse navigation');
  const openDrawerLabel = t('Open navigation');
  const searchLabel = t('Search pages and records');
  const dock = [
    { key: 'dashboard', label: t('Home'), icon: LayoutDashboard },
    nav.find((item) => item.key === 'roadmap' || item.key === 'tasks'),
    nav.find((item) => item.key === 'messages'),
    nav.find((item) => item.key === 'programs'),
  ].filter(Boolean);
  // A page known to draw its own header shows neither the fallback heading nor the legacy panel while it loads.
  const showFallbackTitle = headers === 0 && !BLUE_HEADER_PAGES.has(page);
  const title = pageMeta ? (navLabels[page] || t(pageMeta.label)) : '';

  return <ShellContext.Provider value={shellContext}>
    <div className={`app-shell role-student nb-blue${collapsed ? ' nb-collapsed' : ''}`} data-nb-theme={theme.mode} data-nb-read={theme.reading ? 'true' : 'false'} data-nb-page={page}>
      <div className="nb-backdrop" aria-hidden="true" />
      <aside className={`nb-side${mobileOpen ? ' is-open' : ''}`} id="nb-sidebar" aria-label={t('Main navigation')}>
        <div className="nb-side-top">
          <button type="button" className="nb-brand" onClick={() => go('dashboard')} aria-label={t('Dashboard')}>
            <span className="nb-logo" aria-hidden="true" /><b>{t('Naseeb Edu')}</b>
          </button>
          <button type="button" className="nb-side-collapse nb-desktop-only" onClick={toggleSidebar} title={collapseLabel} aria-label={collapseLabel} aria-expanded={!collapsed}>{collapsed ? <ChevronsRight size={20} aria-hidden="true" /> : <ChevronsLeft size={20} aria-hidden="true" />}</button>
          <button type="button" className="nb-side-collapse nb-mobile-only" onClick={() => setMobileOpen(false)} aria-label={t('Close navigation')}><X size={20} aria-hidden="true" /></button>
        </div>
        <button type="button" className={`nb-nav-item nb-notify${notificationsOpen ? ' is-active' : ''}`} onClick={() => { setMobileOpen(false); openNotifications(); }} title={bellLabel} aria-label={bellLabel}>
          <Bell size={20} aria-hidden="true" /><span>{t('Notifications')}</span>{bellCount > 0 && <i className="nb-dot" aria-hidden="true" />}
        </button>
        <div className="nb-side-label" aria-hidden="true">{t('MENU')}</div>
        <nav className="nb-nav" aria-label={t('Main navigation')}>
          {nav.map((item) => {
            const Icon = item.icon;
            if (isPageLocked(item.key, user)) return <button key={item.key} type="button" className="nb-nav-item is-locked" disabled aria-disabled="true" title={t('Coming soon')} aria-label={`${item.label} — ${t('Coming soon')}`}><Icon size={20} aria-hidden="true" /><span>{item.label}</span><Lock size={14} className="nb-nav-end" aria-hidden="true" /></button>;
            const active = page === item.key;
            return <button key={item.key} type="button" className={`nb-nav-item${active ? ' is-active' : ''}`} aria-current={active ? 'page' : undefined} title={collapsed ? item.label : undefined} aria-label={item.label} onClick={() => go(item.key)}>
              <Icon size={20} aria-hidden="true" /><span>{item.label}</span>{item.isNew && <em className="nb-new">{t('New')}</em>}
              {item.key === 'messages' && unreadChats > 0 && <i className="nb-dot nb-nav-end" aria-hidden="true" />}
            </button>;
          })}
        </nav>
        <div className="nb-account" ref={accountRef}>
          {profileOpen && <div className="nb-menu nb-account-menu" role="menu" aria-label={t('Account menu')}>
            {canOpenPage('account_settings', user) && <button type="button" role="menuitem" onClick={() => go('account_settings')}><Settings size={17} aria-hidden="true" />{t('Account settings')}</button>}
            {canOpenPage('screen_time', user) && <button type="button" role="menuitem" onClick={() => go('screen_time')}><Clock3 size={17} aria-hidden="true" />{t('Screen Time')}</button>}
            {navigationFor(user).includes('support') && <button type="button" role="menuitem" onClick={() => go('support')}><LifeBuoy size={17} aria-hidden="true" />{t('Support')}{supportBadge > 0 && <b>{supportBadge}</b>}</button>}
            <button type="button" role="menuitem" onClick={logout}><LogOut size={17} aria-hidden="true" />{t('Logout')}</button>
          </div>}
          <button type="button" className="nb-account-trigger" aria-haspopup="menu" aria-expanded={profileOpen} aria-label={t('Account menu')} title={t('Account menu')} onClick={() => setProfileOpen(!profileOpen)}>
            <StudentAvatar student={ownStudent(data)} />
            <span className="nb-account-copy"><b>{user.first_name || fullName(user)}</b><small>{roleLabel(user.role)}</small></span>
            <ChevronRight size={17} className="nb-account-chevron" aria-hidden="true" />
          </button>
        </div>
      </aside>
      {mobileOpen && <div className="nb-scrim" onClick={() => setMobileOpen(false)} aria-hidden="true" />}
      <main className={`nb-main nb-page-${page}`}>
        <div className="nb-topbar">
          <button type="button" className="nb-control nb-icon-control nb-mobile-only nb-menu-button" onClick={() => setMobileOpen(true)} aria-label={openDrawerLabel} aria-controls="nb-sidebar" aria-expanded={mobileOpen}><Menu size={20} aria-hidden="true" /></button>
          <div className="nb-top-tools">
            <div id="nb-header-tools" className="nb-header-tools" />
            {page !== 'essay_lab' && <button type="button" className="nb-control nb-icon-control" onClick={openSearch} title={searchLabel + ' (Ctrl+K)'} aria-label={searchLabel} aria-keyshortcuts="Control+K Meta+K"><Search size={18} aria-hidden="true" /></button>}
            {canExport && <button type="button" className="nb-control nb-icon-control" onClick={() => exportNodePdf(document.querySelector('.page-content'))} title={t('Export PDF')} aria-label={t('Export PDF')}><Download size={18} aria-hidden="true" /></button>}
            <LanguagePicker language={language} onChange={changeLanguage} />
            <ThemePicker />
          </div>
        </div>
        {banners}
        {showFallbackTitle && pageMeta && <header className="nb-page-header nb-fallback-header">
          <div className="nb-page-title"><h1>{title}</h1><p>{t(pageMeta.description)}</p></div>
        </header>}
        <div className={`page-content nb-content${showFallbackTitle ? ' is-legacy' : ''}`}>{children}</div>
      </main>
      <nav className="nb-dock" aria-label={t('Quick navigation')}>
        {dock.map((item) => {
          const Icon = item.icon;
          const active = page === item.key;
          return <button key={item.key} type="button" className={`nb-dock-item${active ? ' is-active' : ''}`} aria-current={active ? 'page' : undefined} onClick={() => go(item.key)}>
            <Icon size={20} aria-hidden="true" /><span>{item.label}</span>
            {item.key === 'messages' && unreadChats > 0 && <i className="nb-dot" aria-hidden="true" />}
          </button>;
        })}
        <button type="button" className={`nb-dock-item${mobileOpen ? ' is-active' : ''}`} onClick={() => setMobileOpen(true)} aria-controls="nb-sidebar" aria-expanded={mobileOpen}><Menu size={20} aria-hidden="true" /><span>{t('Menu')}</span></button>
      </nav>
      {overlays}
    </div>
  </ShellContext.Provider>;
}
