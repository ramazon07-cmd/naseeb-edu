import { Check, X } from 'lucide-react';
import { t } from '../i18n';
import { PLAN_FEATURES, SEATS } from '../lib/workspacePlan';

// What a plan allows: seat limits (empty = unlimited) and its feature flags.
export function PlanFacts({ plan }) {
  if (!plan) return null;
  return <div className="plan-facts form-wide">
    <div className="seat-usage">{SEATS.map(([key, title]) => <span key={key}>{t(title)} <b>{plan[key] ?? '∞'}</b></span>)}</div>
    <ul className="plan-features">{PLAN_FEATURES.map(([key, title]) => <li key={key} className={plan.features?.[key] ? 'on' : 'off'}>{plan.features?.[key] ? <Check size={14} aria-hidden="true" /> : <X size={14} aria-hidden="true" />}<span>{t(title)}</span><span className="sr-only">{plan.features?.[key] ? t("Included in the plan") : t("Not included in the plan")}</span></li>)}</ul>
  </div>;
}
