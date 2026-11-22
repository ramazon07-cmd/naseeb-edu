// Admin "AI usage" panel helpers. The list of features comes from the backend
// (feature_names / features), so a new AI feature shows up without a frontend change;
// the labels below are only nicer names, with the key itself as the fallback.
import { tp, tx, formatNumberLocale, formatPercentLocale } from '../i18n.js';
import { joinParts } from './format.js';

const AI_FEATURE_LABELS = {
  assistant: 'AI assistant',
  essay_coach: 'Essay coach',
  recommendation_letter: 'Letter suggestions',
  education_match: 'Major explanations',
  telegram_import: 'Telegram program import',
};

export function aiFeatureLabel(key) {
  if (AI_FEATURE_LABELS[key]) return AI_FEATURE_LABELS[key];
  const words = String(key).replace(/[_-]+/g, ' ').trim();
  return words ? words[0].toUpperCase() + words.slice(1) : String(key);
}

// One row per feature the backend reports, in its order. A feature the payload has no
// numbers for is skipped (never crashes the page).
export function aiUsageRows(data) {
  if (!data) return [];
  const sources = [data.features, data.today_from_log].filter((source) => source && typeof source === 'object');
  const keys = [...(Array.isArray(data.feature_names) ? data.feature_names : []), ...sources.flatMap(Object.keys)];
  return [...new Set(keys)].flatMap((key) => {
    const usage = data.features?.[key] || null;
    const log = data.today_from_log?.[key] || null;
    if (!usage && !log) return [];
    return [{ key, title: aiFeatureLabel(key), usage, log, tokens: data.tokens?.features?.[key] || null, cost: data.cost_estimate?.features?.[key] ?? null }];
  });
}

// "30 days: 12 paid calls, 34,000 tokens, 8% errors (2 calls with estimated tokens, 1 refunded)".
export function aiTokenLine(tokens, days = 30) {
  if (!tokens || !(tokens.paid_calls || tokens.refunded_calls)) return '';
  const bits = [
    tp('{n} paid call|{n} paid calls', tokens.paid_calls, { n: formatNumberLocale(tokens.paid_calls) }),
    tx`${formatNumberLocale(tokens.total_tokens?.sum || 0)} tokens`,
    tokens.error_rate > 0 && tx`${formatPercentLocale(tokens.error_rate)} errors`,
    tokens.estimated_calls > 0 && tp('{n} call with estimated tokens|{n} calls with estimated tokens', tokens.estimated_calls, { n: tokens.estimated_calls }),
    tokens.refunded_calls > 0 && tp('{n} refunded call|{n} refunded calls', tokens.refunded_calls, { n: tokens.refunded_calls }),
  ];
  return `${tx`Last ${days} days`}: ${joinParts(...bits)}`;
}

export function aiCostLine(estimate, days = 30) {
  if (!estimate || typeof estimate.total_usd !== 'number') return '';
  const total = estimate.total_usd.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
  return tx`Estimated cost, last ${days} days: ${total}. This assumes one price for every model.`;
}
