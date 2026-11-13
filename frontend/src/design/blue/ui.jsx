import { createContext, isValidElement, useContext, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowRight, ChevronRight } from 'lucide-react';
import { t, tp } from '../../i18n';

// Shared building blocks of the blue (student) design. Class names are prefixed
// `nb-` and styled in ui.css under `.nb-blue`. See README.md for the contract.

const cx = (...parts) => parts.filter(Boolean).join(' ');

// An icon is passed as a lucide component (`icon={Bell}`) or as a ready element.
function renderIcon(icon, size = 20) {
  if (!icon) return null;
  if (isValidElement(icon)) return icon;
  const Icon = icon;
  return <Icon size={size} aria-hidden="true" />;
}

// The shell gives pages a way to say "I draw my own title": the shell then
// drops its fallback heading. PageHeader does this by itself.
export const ShellContext = createContext({ registerPageHeader: () => () => {} });

// A title row: large title, subtitle, and the page's primary actions on the right.
export function PageHeader({ title, subtitle, actions, className = '', headingId }) {
  const { registerPageHeader } = useContext(ShellContext);
  useLayoutEffect(() => registerPageHeader(), [registerPageHeader]);
  return <header className={cx('nb-page-header', className)}>
    <div className="nb-page-title">
      <h1 id={headingId}>{title}</h1>
      {subtitle ? <p>{subtitle}</p> : null}
    </div>
    {actions ? <div className="nb-page-actions">{actions}</div> : null}
  </header>;
}

// Controls for the shell's top-right row (the dashboard's "Customize"): they
// are drawn beside the language and theme pickers, not where this is placed.
export function HeaderTools({ children }) {
  const [host, setHost] = useState(null);
  useLayoutEffect(() => { setHost(document.getElementById('nb-header-tools')); }, []);
  return host ? createPortal(children, host) : null;
}

export function SectionTitle({ children, action, as: Tag = 'h2', className = '' }) {
  return <div className={cx('nb-section-title', className)}><Tag>{children}</Tag>{action ? <div className="nb-section-action">{action}</div> : null}</div>;
}

// A row of saturated blue tiles. `columns` defaults to the number of tiles (max 4).
export function KpiRow({ children, columns, className = '', label }) {
  return <div className={cx('nb-kpi-row', className)} style={columns ? { '--nb-kpi-cols': columns } : undefined} role={label ? 'group' : undefined} aria-label={label}>{children}</div>;
}

// tone 0-3 picks the gradient (the row alternates when omitted).
export function KpiTile({ icon, value, unit, label, onClick, href, tone = 0, className = '', actionLabel, loading = false }) {
  const body = <>
    <span className="nb-kpi-icon">{renderIcon(icon, 22)}</span>
    <span className="nb-kpi-copy">
      <span className="nb-kpi-value">{loading ? '–' : value}{unit && !loading ? <small>{unit}</small> : null}</span>
      <span className="nb-kpi-label">{label}</span>
    </span>
    {(onClick || href) ? <span className="nb-kpi-go" aria-hidden="true"><ChevronRight size={16} /></span> : null}
  </>;
  const classes = cx('nb-kpi', `nb-kpi-tone-${tone % 4}`, (onClick || href) && 'is-action', className);
  if (href) return <a className={classes} href={href} aria-label={actionLabel}>{body}</a>;
  if (onClick) return <button type="button" className={classes} onClick={onClick} aria-label={actionLabel}>{body}</button>;
  return <div className={classes}>{body}</div>;
}

// A frosted card. `tone="solid"` is the white card, `tone="hero"` the navy panel.
export function GlassCard({ title, icon, action, footer, children, tone = 'glass', as: Tag = 'section', className = '', headingLevel: Heading = 'h3', ...rest }) {
  const headingId = useId();
  return <Tag className={cx('nb-card', `nb-card-${tone}`, className)} aria-labelledby={title ? headingId : undefined} {...rest}>
    {(title || action) ? <header className="nb-card-head">
      {icon ? <span className="nb-chip-icon">{renderIcon(icon, 18)}</span> : null}
      {title ? <Heading id={headingId} className="nb-card-title">{title}</Heading> : null}
      {action ? <div className="nb-card-action">{action}</div> : null}
    </header> : null}
    <div className="nb-card-body">{children}</div>
    {footer ? <footer className="nb-card-foot">{footer}</footer> : null}
  </Tag>;
}

// "View all >" style link for a card footer.
export function CardLink({ children, onClick, href }) {
  const body = <>{children}<ChevronRight size={15} aria-hidden="true" /></>;
  return href ? <a className="nb-card-link" href={href}>{body}</a> : <button type="button" className="nb-card-link" onClick={onClick}>{body}</button>;
}

// An accessible tablist (arrow keys, Home/End). The panel is the caller's:
// give it `role="tabpanel"` and `aria-labelledby={tabId(idPrefix, key)}`.
export const tabId = (idPrefix, key) => `${idPrefix}-tab-${key}`;
export function PillTabs({ tabs, value, onChange, label, idPrefix = 'nb', className = '' }) {
  const refs = useRef({});
  function move(event, index) {
    const keys = { ArrowRight: 1, ArrowLeft: -1 };
    let next = null;
    if (event.key in keys) next = (index + keys[event.key] + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    if (next === null) return;
    event.preventDefault();
    onChange(tabs[next].key);
    refs.current[tabs[next].key]?.focus();
  }
  return <div className={cx('nb-tabs', className)} role="tablist" aria-label={label}>
    {tabs.map((tab, index) => {
      const active = tab.key === value;
      return <button key={tab.key} id={tabId(idPrefix, tab.key)} ref={(node) => { refs.current[tab.key] = node; }} type="button" role="tab" aria-selected={active} tabIndex={active ? 0 : -1} className={cx('nb-tab', active && 'is-active')} onClick={() => onChange(tab.key)} onKeyDown={(event) => move(event, index)}>
        {tab.label}{tab.count !== undefined && tab.count !== null ? <span className="nb-tab-count">{tab.count}</span> : null}
      </button>;
    })}
  </div>;
}

// variant: default | days | overdue | ok | warn | gold | new
export function Chip({ variant = 'default', icon, children, className = '', ...rest }) {
  return <span className={cx('nb-chip', `nb-chip-${variant}`, className)} {...rest}>{renderIcon(icon, 13)}{children}</span>;
}

// "N days left" for a number of whole days (negative = overdue, 0 = due today).
export function DaysChip({ days, className = '' }) {
  if (days === null || days === undefined || Number.isNaN(Number(days))) return null;
  const n = Math.round(Number(days));
  if (n < 0) return <Chip variant="overdue" className={className}>{t('Overdue')}</Chip>;
  if (n === 0) return <Chip variant="days" className={className}>{t('Due today')}</Chip>;
  return <Chip variant="days" className={className}>{tp('{n} day left|{n} days left', n, { n })}</Chip>;
}

// variant: primary | ghost; size: md | sm. Renders <a> when `href` is given.
export function BlueButton({ variant = 'primary', size = 'md', icon, iconRight, arrow = false, href, children, className = '', type = 'button', ...rest }) {
  const classes = cx('nb-btn', `nb-btn-${variant}`, size === 'sm' && 'nb-btn-sm', className);
  const content = <>{renderIcon(icon, 17)}<span>{children}</span>{arrow ? <ArrowRight size={17} aria-hidden="true" /> : renderIcon(iconRight, 17)}</>;
  return href ? <a className={classes} href={href} {...rest}>{content}</a> : <button type={type} className={classes} {...rest}>{content}</button>;
}

// A big blue icon tile, title, text and an optional action.
export function EmptyState({ icon, title, text, action, className = '' }) {
  return <div className={cx('nb-empty', className)}>
    {icon ? <span className="nb-empty-icon">{renderIcon(icon, 34)}</span> : null}
    {title ? <h3>{title}</h3> : null}
    {text ? <p>{text}</p> : null}
    {action ? <div className="nb-empty-action">{action}</div> : null}
  </div>;
}

// Day / month tile used by deadline and notification rows. `hot` fills it navy.
export function DateTile({ day, month, hot = false, className = '' }) {
  return <span className={cx('nb-date', hot && 'is-hot', className)}><b>{day}</b><small>{month}</small></span>;
}

const initialsOf = (name) => String(name || '').trim().split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || '?';

// `src` is optional; without it the initials sit on a blue tile.
export function Avatar({ name, src, size = 40, className = '' }) {
  const style = { '--nb-avatar': `${size}px` };
  return <span className={cx('nb-avatar', className)} style={style} role="img" aria-label={name || undefined}>
    {src ? <img src={src} alt="" /> : <span aria-hidden="true">{initialsOf(name)}</span>}
  </span>;
}
