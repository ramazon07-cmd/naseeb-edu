import { createContext, useContext } from 'react';
import { createPortal } from 'react-dom';
import { formatNumberLocale, t, tp } from '../i18n';
import { initials } from '../lib/labels';
import { joinParts, relativeDayText } from '../lib/format';

// Building blocks of the counselor workspace ("Counselor Dashboard" design):
// a page head, initials avatars, status tags, filter pills and a progress bar.
// Colours and radii come from the --cx-* tokens in styles.css.

// What the counselor shell shares with the page it wraps.
export const CounselorUiContext = createContext({ openSearch: () => {}, counts: {}, stats: null });
export const useCounselorUi = () => useContext(CounselorUiContext);

// Occasional student administration belongs in the account menu, leaving the
// workspace focused on the review and progress actions in the design.
export function CxAccountActions({ children }) {
  const { accountActionsHost } = useCounselorUi();
  return accountActionsHost ? createPortal(
    <div className="cx-account-actions" onClick={accountActionsHost.close}>{children}</div>,
    accountActionsHost.element,
  ) : null;
}

// The page title, an optional line under it, and actions aligned to its right.
export function CxHead({ title, subtitle, children }) {
  return <header className="cx-head">
    <div className="cx-head-copy"><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>
    {children && <div className="cx-head-actions">{children}</div>}
  </header>;
}

export function CxAvatar({ name, className = '' }) {
  return <span className={`cx-avatar ${className}`.trim()} aria-hidden="true">{initials(name)}</span>;
}

// `tone`: late | warn | ok | quiet | task | roadmap | portfolio | document.
export function CxTag({ tone = 'quiet', small = false, children }) {
  return <span className={`cx-tag cx-tag-${tone}${small ? ' cx-tag-sm' : ''}`}>{children}</span>;
}

// A reason a student needs the counselor, in words (lib/studentReasons.js keeps it translation-free).
export function reasonText(reason) {
  if (reason.key === 'quiet') return tp('Quiet for {n} day|Quiet for {n} days', reason.quietDays, { n: reason.quietDays });
  if (reason.key === 'missing_document') return reason.title ? t('{title} missing', { title: reason.title }) : tp('{n} document missing|{n} documents missing', reason.count, { n: reason.count });
  return tp(reason.countPattern, reason.count, { n: reason.count });
}

const REASON_TONE = { danger: 'late', warning: 'warn', muted: 'quiet' };

export function ReasonTags({ reasons }) {
  return <span className="cx-reasons">{reasons.map((reason) => <CxTag key={reason.key} tone={REASON_TONE[reason.tone] || 'quiet'}>{reasonText(reason)}</CxTag>)}</span>;
}

// One thing waiting for review: who sent it, what, when, and its kind.
export function CxQueueRow({ item, active, onClick }) {
  return <button type="button" className={`cx-row${active ? ' active' : ''}`} aria-pressed={active === undefined ? undefined : active} onClick={onClick}>
    <CxAvatar name={item.studentName} />
    <span className="cx-row-copy"><b>{item.title}</b><small>{joinParts(item.studentName, t(item.when, { when: relativeDayText(item.at).toLowerCase() }))}</small></span>
    <CxTag tone={item.kind} small>{t(item.label)}</CxTag>
  </button>;
}

// Filter pills: [key, label, count?]. Toggle buttons, not tabs — they narrow one list.
export function CxPills({ items, active, onChange, label }) {
  return <div className="cx-pills" role="group" aria-label={label}>
    {items.map(([key, title, total]) => <button type="button" key={key} className={`cx-pill${active === key ? ' active' : ''}`} aria-pressed={active === key} onClick={() => onChange(key)}>
      {t(title)}{total !== undefined && ` ${formatNumberLocale(total)}`}
    </button>)}
  </div>;
}

export function CxProgress({ value, label }) {
  const percent = Math.max(0, Math.min(100, Number(value) || 0));
  return <div className="cx-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-label={label}><span style={{ width: `${percent}%` }} /></div>;
}

// A white card with an optional title row: `hint` sits beside the title, `action` at the far end.
export function CxCard({ title, hint, action, className = '', children }) {
  return <section className={`cx-card ${className}`.trim()}>
    {title && <header className="cx-card-head"><h2>{title}{hint && <small>{hint}</small>}</h2>{action}</header>}
    {children}
  </section>;
}

// The tab bar of a Student 360: [key, label, count?]. Arrow keys, Home and End move between tabs.
export function CxTabs({ items, active, onChange, label }) {
  function onKeyDown(event, index) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length;
    onChange(items[next][0]);
    event.currentTarget.parentElement?.querySelectorAll('[role="tab"]')[next]?.focus();
  }
  return <div className="cx-tabs" role="tablist" aria-label={label}>
    {items.map(([key, title, total], index) => <button type="button" role="tab" key={key} id={`cx-tab-${key}`} aria-selected={active === key} tabIndex={active === key ? 0 : -1} className={active === key ? 'active' : ''} onClick={() => onChange(key)} onKeyDown={(event) => onKeyDown(event, index)}>
      {t(title)}{total !== undefined && ` · ${formatNumberLocale(total)}`}
    </button>)}
  </div>;
}
