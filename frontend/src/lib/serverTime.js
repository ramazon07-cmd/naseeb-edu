// Counselor Home and Review show times in the server's zone (settings.TIME_ZONE):
// Home's "today" and week strip come from the server, so a submission's day and
// "2 days ago" must be counted there too, whatever zone the browser is in.
import { t, tp } from '../i18n.js';
import { dateText } from './format.js';

export const SERVER_TIME_ZONE = 'Asia/Tashkent';
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

const zoneFormats = new Map();
function zoneParts(date, timeZone) {
  if (!zoneFormats.has(timeZone)) {
    zoneFormats.set(timeZone, new Intl.DateTimeFormat('en-US', {
      timeZone, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
    }));
  }
  return Object.fromEntries(zoneFormats.get(timeZone).formatToParts(date).map(({ type, value }) => [type, Number(value)]));
}

// A timestamp -> a local Date holding the server zone's wall-clock time, so the
// usual formatters (which use the browser's zone) print the server's day and
// hour. Calendar dates ("YYYY-MM-DD") and empty values pass through unchanged.
export function inServerZone(value, timeZone = SERVER_TIME_ZONE) {
  if (!value || (typeof value === 'string' && DATE_ONLY.test(value))) return value;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const p = zoneParts(date, timeZone);
  return new Date(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
}

// The server zone's calendar day of a timestamp (or of now), "YYYY-MM-DD".
export function serverDateKey(value = new Date(), timeZone = SERVER_TIME_ZONE) {
  if (typeof value === 'string' && DATE_ONLY.test(value)) return value;
  const p = zoneParts(new Date(value), timeZone);
  return `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`;
}

// "Today" / "Yesterday" / "{n} days ago" for the first week, then a plain date,
// with both days taken in the server zone.
export function serverRelativeDayText(value, now = new Date(), timeZone = SERVER_TIME_ZONE) {
  if (!value) return '';
  const days = Math.round((Date.parse(serverDateKey(now, timeZone)) - Date.parse(serverDateKey(value, timeZone))) / 86400000);
  if (days <= 0) return t('Today');
  if (days === 1) return t('Yesterday');
  if (days < 7) return tp('{n} day ago|{n} days ago', days, { n: days });
  return dateText(inServerZone(value, timeZone));
}
