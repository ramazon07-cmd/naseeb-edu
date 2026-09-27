import { formatDateLocale, formatNumberLocale, formatCurrencyLocale, t, tp, tx } from '../i18n.js';
import { fullName } from './labels.js';

export const dateText = (value) => formatDateLocale(value);

export const dateTimeText = (value) => formatDateLocale(value, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });

export const clockText = (value) => formatDateLocale(value, { hour: '2-digit', minute: '2-digit' });

export const chatStampText = (value) => {
  if (!value) return '';
  const moment = new Date(value);
  return moment.toDateString() === new Date().toDateString() ? clockText(value) : formatDateLocale(value, { day: '2-digit', month: 'short' });
};

export const studentName = (data, id) => fullName(data.students?.find((student) => student.id === Number(id))?.user_detail);

export const localDateKey = () => {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
};

export const formatFileSize = (bytes = 0) => {
  if (!bytes) return '—';
  if (bytes < 1024 * 1024) return `${formatNumberLocale(Math.max(1, Math.round(bytes / 1024)))} KB`;
  return `${formatNumberLocale(bytes / (1024 * 1024), { maximumFractionDigits: 1 })} MB`;
};

export const money = (value) => formatCurrencyLocale(value);

// Joins the parts of a meta line with " · ", skipping missing values so a line
// never starts, ends or doubles up on a separator.
export const joinParts = (...parts) => parts.flat().filter((part) => {
  if (part === null || part === undefined || part === false) return false;
  const text = String(part).trim();
  return text !== '' && text !== '—';
}).join(' · ');

// joinParts keeps a real 0, so optional counts must be gated explicitly.
export const programUsageCaption = ({ total, used, unlimited, hours }) => joinParts(
  total > 0 && tx`${hours(used)} used of ${hours(total)}`,
  unlimited > 0 && tp('{n} unlimited service|{n} unlimited services', unlimited, { n: unlimited }),
);

export const testScoreCaption = ({ ielts_score: ielts, sat_score: sat }) => joinParts(
  Number(ielts) > 0 && `${t('IELTS')} ${ielts}`,
  Number(sat) > 0 && `${t('SAT')} ${sat}`,
);

export const gradeText = (grade) => {
  if (!grade) return '';
  return grade === 'gap' ? t('Gap year') : tx`Grade ${grade}`;
};
