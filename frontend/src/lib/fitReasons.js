import { formatNumberLocale, t } from '../i18n.js';
import { fitReasonKey } from '../translations/fitReasons.js';
import { money } from './format.js';

const MONEY_PARAMS = new Set(['cost', 'budget']);

const paramText = (name, value) => {
  if (MONEY_PARAMS.has(name)) return money(value);
  // Test scores read as written (1450, not 1 450), with the locale's decimal mark (7,5).
  return typeof value === 'number' ? formatNumberLocale(value, { useGrouping: false }) : String(value ?? '');
};

// One fit reason or watch-out ({code, params, text}) in the active language. An unknown
// code shows the server's English text; an old cached payload sends a plain string.
export function fitReasonText(item) {
  if (typeof item === 'string') return item;
  if (!item) return '';
  const key = fitReasonKey(item.code);
  const params = Object.fromEntries(Object.entries(item.params || {}).map(([name, value]) => [name, paramText(name, value)]));
  const text = t(key, params);
  return text === key ? item.text || '' : text;
}
