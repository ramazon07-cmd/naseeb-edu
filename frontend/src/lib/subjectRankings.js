// The Subject rankings view of College Search: the request it makes and how a row reads.
// Nothing here loads at start-up: the view's chunk imports this file when a student opens the view.
import { formatNumberLocale } from '../i18n.js';

// Same page sizes as the QS rankings view, minus 100: a subject page never needs more than 50 rows.
export const SUBJECT_PAGE_SIZES = [10, 25, 50];

// The page size of the shared "Show" control, kept to what a subject page offers (100 becomes 50).
export const subjectLimit = (pageSize) => SUBJECT_PAGE_SIZES.includes(pageSize) ? pageSize : pageSize > SUBJECT_PAGE_SIZES.at(-1) ? SUBJECT_PAGE_SIZES.at(-1) : SUBJECT_PAGE_SIZES[0];

// The subject shown when the student's major names none.
export const FALLBACK_SUBJECT = 'COM02';

const QS_FILTER_KEYS = ['region', 'size', 'focus', 'research'];

// The student's own major subject: the first one the research profile names that `areas` (the page's subject
// list) holds, else the fallback.
export function presetSubject(research, areas) {
  const known = new Set(areas.flatMap((area) => [area.code, ...area.subjects.map(([code]) => code)]));
  return research?.subjects?.find((code) => known.has(code)) || FALLBACK_SUBJECT;
}

// Gold is for the world top 10: a real position, never a range.
export const isTopRank = (rank, label = '') => Number(rank) <= 10 && !/[-–]/.test(String(label || ''));

// Everything that picks the rows, without the offset: a change here starts the list again from the top.
export function subjectRankingsQuery({ subject, query = '', country = '', qsFilters = {}, limit = SUBJECT_PAGE_SIZES[0] }) {
  const params = new URLSearchParams();
  params.set('subject', subject);
  const term = String(query).trim().slice(0, 100);
  if (term) params.set('search', term);
  if (country) params.set('country', country);
  QS_FILTER_KEYS.forEach((key) => { if (qsFilters[key]) params.set(key, qsFilters[key]); });
  params.set('limit', String(SUBJECT_PAGE_SIZES.includes(limit) ? limit : SUBJECT_PAGE_SIZES[0]));
  return params.toString();
}

export const subjectRankingsPath = (query, offset = 0) => `${query}&offset=${offset}`;

// The rank as QS publishes it: "#12", a tie "=4", a range "201–250".
export function publishedRank(rank, label = '') {
  const text = String(label || '').trim();
  if (!text) return `#${formatNumberLocale(rank, { useGrouping: false })}`;
  return text.replace('-', '–');
}

export const INDICATOR_TITLES = {
  academic: 'Academic reputation',
  employer: 'Employer reputation',
  citations: 'Citations per paper',
  h_index: 'H-index',
  irn: 'International research network',
};

export const scoreText = (value) => typeof value === 'number' && Number.isFinite(value) ? formatNumberLocale(value, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '—';

// Weight as a percentage: 0.125 -> "12.5%".
export const weightText = (weight) => `${formatNumberLocale(Math.round(weight * 1000) / 10)}%`;

// The next page is appended after the rows already loaded, never twice.
export function appendRows(rows, page) {
  const seen = new Set(rows.map((row) => row.id));
  return [...rows, ...page.filter((row) => !seen.has(row.id))];
}

// "Show more" may page a query only from rows that query itself produced: after a failed reload the rows and
// offset on screen belong to the previous query.
export const canLoadMore = (state, query) => state.query === query && state.nextOffset != null && !state.loading && !state.loadingMore;
