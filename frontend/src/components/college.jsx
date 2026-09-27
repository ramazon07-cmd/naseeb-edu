// Small pieces shared by the College Search, university and Applications pages.
import { CalendarDays, Check, Clock3, HandCoins } from 'lucide-react';
import { formatNumberLocale, t, tx } from '../i18n';
import { dateText } from '../lib/format';
import { label } from '../lib/labels';
import { COLLEGE_AID_FLAGS, PRICE_SCALE_MAX, SAT_SCALE, SCORE_PARTS, daysUntil, dueLabel, dueTone, scalePercent, shortDate } from '../lib/college';

export function TierBand({ value }) {
  return <span className={`tier-band ${value}`}>{label(value)}</span>;
}

export function DeadlineChip({ date, kind }) {
  const days = daysUntil(date);
  if (days == null) return null;
  const Icon = kind === 'aid' ? Clock3 : CalendarDays;
  const urgent = days <= 21;
  const text = urgent ? `${kind === 'aid' ? t("Scholarship") : t("Apply")} · ${dueLabel(days)}` : kind === 'aid' ? tx`Scholarship by ${shortDate(date)}` : tx`Apply by ${shortDate(date)}`;
  return <span className={`due ${urgent ? dueTone(days) : ''}`.trim()}><Icon size={12} aria-hidden="true" /> {text}</span>;
}

export function SatRange({ min, max, score }) {
  return <span className="range-meter" aria-hidden="true"><i style={{ '--from': scalePercent(min, ...SAT_SCALE), '--to': scalePercent(max || min, ...SAT_SCALE) }} />{Number(score) > 0 && <b style={{ '--at': scalePercent(score, ...SAT_SCALE) }} />}</span>;
}

export function PriceMeter({ price, budget }) {
  return <span className="range-meter price" aria-hidden="true"><i style={{ '--from': '0%', '--to': scalePercent(price, 0, PRICE_SCALE_MAX) }} />{Number(budget) > 0 && <b className="budget" style={{ '--at': scalePercent(budget, 0, PRICE_SCALE_MAX) }} />}</span>;
}

export function ScoreBreakdown({ breakdown }) {
  return <div className="score-breakdown">{SCORE_PARTS.map(([key, max]) => <div key={key}><span>{label(key)}</span><span className="score-bar" aria-hidden="true"><i style={{ '--fill': scalePercent(breakdown[key], 0, max) }} /></span><b>{formatNumberLocale(breakdown[key])}/{formatNumberLocale(max)}</b></div>)}</div>;
}

export function AidTags({ university }) {
  return <div className="tag-row">{COLLEGE_AID_FLAGS.filter(([flag]) => university[flag] && flag !== 'meets_full_need').map(([flag, title]) => <span className="tag" key={flag}>{t(title)}</span>)}{university.meets_full_need && <span className="tag ok"><Check size={12} aria-hidden="true" /> {t("Meets full need")}</span>}{university.test_optional && <span className="tag">{t("Test optional")}</span>}</div>;
}

export function InfoCard({ title, className = '', children }) {
  return <section className={`info-card ${className}`.trim()} aria-label={t(title)}><h3>{t(title)}</h3>{children}</section>;
}

export function DeadlineCard({ title = "Deadlines", university, application, showAid = true }) {
  const applicationDate = application?.deadline || university.application_deadline;
  const aidDate = application?.scholarship_deadline || university.scholarship_deadline;
  const days = daysUntil(applicationDate);
  return <InfoCard title={title}>
    <div className="kv"><span><CalendarDays size={15} aria-hidden="true" /> {t("Application")}</span><b>{applicationDate ? dateText(applicationDate) : '—'}</b></div>
    {showAid && <div className="kv"><span><HandCoins size={15} aria-hidden="true" /> {t("Aid")}</span><b>{aidDate ? dateText(aidDate) : '—'}</b></div>}
    {days != null && <span className={`due ${dueTone(days)}`.trim()}><Clock3 size={12} aria-hidden="true" /> {dueLabel(days)}</span>}
  </InfoCard>;
}
