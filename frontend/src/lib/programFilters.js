// Programs catalog filtering. The whole catalog (a few hundred rows, cached
// server-side) is in memory, so filtering is local and instant; this module
// is framework-free so the rules and the counts are unit tested.
import { withQuery } from './routes.js';

export const PROGRAM_GRADES = ['5', '6', '7', '8', '9', '10', '11', 'gap'];
export const PROGRAM_TYPES = ['national', 'international'];
export const PROGRAM_DELIVERY = ['onsite', 'online', 'hybrid'];

export const PROGRAM_FILTER_DEFAULTS = Object.freeze({ q: '', type: 'all', category: 'all', grade: 'all', delivery: 'all', aid: false, open: true });

const MAX_SEARCH = 100;

export const programGrades = (item) => String(item.eligible_grades || '').split(',').map((part) => part.trim()).filter(Boolean);

export const isClosedProgram = (item, today) => Boolean(item.deadline) && item.deadline < today;

// "6,7,8,9,10,11,gap" -> ['6–11', 'gap']: consecutive grades collapse into a range.
export function compactGrades(grades) {
  const numbers = [...new Set(grades.filter((grade) => /^\d+$/.test(grade)).map(Number))].sort((first, second) => first - second);
  const runs = [];
  for (const grade of numbers) {
    const run = runs[runs.length - 1];
    if (run && grade === run[1] + 1) run[1] = grade; else runs.push([grade, grade]);
  }
  const parts = runs.map(([from, to]) => (from === to ? String(from) : `${from}–${to}`));
  return grades.includes('gap') ? [...parts, 'gap'] : parts;
}

// Most catalog rows keep the counselor sheet's yearly deadline text ("Feb 15",
// "16-Jan-25", "15th June", "08.03", "ED: Dec 13, RD: Feb 12") instead of a
// date. Read the month and day out of it so the row can sit in the timeline;
// the year in the text is last cycle's, so the date is the next one to come.
const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const MONTH_WORD = /\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b/g;
const DAY_AFTER = /^\s*(\d{1,2})(?:st|nd|rd|th)?(?!\d)/;
const DAY_BEFORE = /(?:^|\D)(\d{1,2})(?:st|nd|rd|th)?[\s-]*$/;
const DAY_DOT_MONTH = /(?:^|[^\d.])(\d{1,2})\.(\d{1,2})(?![\d.])/g;

function deadlineTextDays(source) {
  const found = [];
  for (const match of source.matchAll(MONTH_WORD)) {
    const after = DAY_AFTER.exec(source.slice(match.index + match[0].length));
    const before = after ? null : DAY_BEFORE.exec(source.slice(0, match.index));
    const day = Number((after || before)?.[1]) || null;
    // A bare month counts only when spelled out ("Typically in January"); "may" is also a verb.
    if (day || (match[1].length > 3 && match[1] !== 'may')) found.push({ month: MONTHS.indexOf(match[1].slice(0, 3)), day });
  }
  for (const [, day, month] of source.matchAll(DAY_DOT_MONTH)) found.push({ month: Number(month) - 1, day: Number(day) });
  return found.filter(({ month, day }) => month >= 0 && month < 12 && (day === null || (day >= 1 && day <= 31)));
}

const isoDay = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

// -> { date: 'YYYY-MM-DD', exact: false, day, detail } for the next deadline
// the text names (day is null for "Typically in January"), or null when it
// names none. `detail`: the text says more than that one date (other rounds,
// "first come first served"), so it is worth showing as written.
export function usualDeadline(text, today) {
  const source = String(text || '').toLowerCase();
  const candidates = deadlineTextDays(source);
  const [year, month, day] = today.split('-').map(Number);
  const now = new Date(year, month - 1, day);
  let best = null;
  for (const candidate of candidates) {
    for (const offset of [0, 1]) {
      // A bare month runs to its last day, so it sorts after that month's dated rows.
      const date = candidate.day ? new Date(year + offset, candidate.month, candidate.day) : new Date(year + offset, candidate.month + 1, 0);
      if (date.getMonth() !== candidate.month) break; // "31 April"
      if (date < now) continue;
      if (!best || date < best.date) best = { date, day: candidate.day };
      break;
    }
  }
  const words = source.replace(MONTH_WORD, ' ').replace(/\d+(?:st|nd|rd|th)?/g, ' ');
  return best && { date: isoDay(best.date), exact: false, day: best.day, detail: candidates.length > 1 || /[a-z]{3,}/.test(words) };
}

// The date a row is filed under: the real deadline, else the usual one from the text.
export function programDue(item, today) {
  if (item.deadline) return { date: item.deadline, exact: true, day: Number(item.deadline.slice(8, 10)) };
  return usualDeadline(item.deadline_text, today);
}

// The day a countdown runs to: the deadline itself, or for a bare month
// ("Typically in March") its first day, the earliest the deadline can be,
// unless that day has already passed this month.
export function countdownDay(due, today) {
  if (due.day) return due.date;
  const first = `${due.date.slice(0, 8)}01`;
  return first >= today ? first : due.date;
}

// Sorted rows -> [{ key, entries }]: one group per deadline month ('2026-10'),
// then 'undated' (nothing to go on but the official page), then 'closed'.
export function groupProgramsByDeadline(rows) {
  const groups = [];
  for (const row of rows) {
    const key = row.closed ? 'closed' : row.due ? row.due.date.slice(0, 7) : 'undated';
    const last = groups[groups.length - 1];
    if (last?.key === key) last.entries.push(row); else groups.push({ key, entries: [row] });
  }
  return groups;
}

// URL query -> filters. Unknown values fall back to the default instead of
// producing an empty list nobody can explain.
export function readProgramFilters(search) {
  const params = new URLSearchParams(search || '');
  const pick = (key, allowed) => (allowed.includes(params.get(key)) ? params.get(key) : PROGRAM_FILTER_DEFAULTS[key]);
  const category = (params.get('category') || '').trim().slice(0, 100);
  return {
    q: (params.get('q') || '').slice(0, MAX_SEARCH),
    type: pick('type', PROGRAM_TYPES),
    category: category || 'all',
    grade: pick('grade', PROGRAM_GRADES),
    delivery: pick('delivery', PROGRAM_DELIVERY),
    aid: params.get('aid') === '1',
    open: params.get('open') !== '0',
  };
}

export const programFiltersQuery = (search, filters) => withQuery(search, filters, PROGRAM_FILTER_DEFAULTS);

// Filter state kept in step with the URL. `synced` is the last query the
// filters were read from or written to: a different query (Back/Forward, a
// sidebar link to bare /programs) replaces the filters, while the page's own
// debounced write does not, so half-typed text such as a trailing space stays.
export const programFilterState = (search) => ({ synced: search || '', filters: readProgramFilters(search) });

export const adoptProgramFilterUrl = (state, search) => ((search || '') === state.synced ? state : programFilterState(search));

// The query to write for the current filters, or null when the URL already
// matches them.
export function programFilterWrite(state, search) {
  const next = programFiltersQuery(search, state.filters);
  return next === (search || '') ? null : next;
}

export const activeProgramFilterCount = (filters) => Object.keys(PROGRAM_FILTER_DEFAULTS)
  .filter((key) => key !== 'q' && filters[key] !== PROGRAM_FILTER_DEFAULTS[key]).length;

export const hasProgramFilters = (filters) => activeProgramFilterCount(filters) > 0 || Boolean(filters.q.trim());

// Every word must appear (AND), in any order, in the fields a student reads.
const haystacks = new WeakMap();
function haystack(item, translate, localeTag) {
  let perLocale = haystacks.get(item);
  if (!perLocale) haystacks.set(item, (perLocale = new Map()));
  if (!perLocale.has(localeTag)) {
    const fields = [item.title, item.provider, item.category, item.description, item.country, item.city, item.requirements, item.aid_details, item.eligible_ages];
    const text = [...fields, ...[item.category, item.description, item.aid_details].map((value) => (value ? translate(value) : ''))]
      .filter(Boolean).join(' \u0001 ');
    perLocale.set(localeTag, text.toLocaleLowerCase(localeTag || undefined));
  }
  return perLocale.get(localeTag);
}

export const searchTerms = (text, localeTag = '') => String(text || '').toLocaleLowerCase(localeTag || undefined).split(/\s+/).filter(Boolean);

const FACETS = ['search', 'type', 'category', 'grade', 'delivery', 'aid', 'open'];

// -> { programs, counts }. counts.<facet> counts the rows that match every
// other active filter, so each number is what choosing that option shows.
export function filterPrograms(catalog, filters, { today, query = '', translate = (value) => value, localeTag = '' } = {}) {
  const terms = [...searchTerms(filters.q, localeTag), ...searchTerms(query, localeTag)];
  const counts = { type: { all: 0 }, category: {}, grade: {}, delivery: {}, aid: 0, closed: 0 };
  const programs = [];
  const bump = (bucket, key) => { bucket[key] = (bucket[key] || 0) + 1; };
  for (const item of catalog) {
    const closed = isClosedProgram(item, today);
    const grades = programGrades(item);
    const text = terms.length ? haystack(item, translate, localeTag) : '';
    const pass = {
      search: terms.every((term) => text.includes(term)),
      type: filters.type === 'all' || item.program_type === filters.type,
      category: filters.category === 'all' || item.category === filters.category,
      grade: filters.grade === 'all' || grades.includes(filters.grade),
      delivery: filters.delivery === 'all' || item.delivery_mode === filters.delivery,
      aid: !filters.aid || Boolean(item.scholarship_available),
      open: !filters.open || !closed,
    };
    const failed = FACETS.filter((facet) => !pass[facet]);
    if (failed.length > 1) continue;
    const only = failed[0];
    // Passes everything except (at most) `only`: it counts for that facet.
    const counted = (facet) => !only || only === facet;
    if (counted('type')) { counts.type.all += 1; bump(counts.type, item.program_type); }
    if (counted('category')) bump(counts.category, item.category);
    if (counted('grade')) for (const grade of new Set(grades)) bump(counts.grade, grade);
    if (counted('delivery')) bump(counts.delivery, item.delivery_mode);
    if (counted('aid') && item.scholarship_available) counts.aid += 1;
    if (counted('open') && closed) counts.closed += 1;
    if (!only) programs.push({ item, closed, due: programDue(item, today) });
  }
  programs.sort((first, second) => (first.closed - second.closed)
    || (first.due?.date || '9999').localeCompare(second.due?.date || '9999')
    || String(first.item.title).localeCompare(String(second.item.title)));
  return { programs, counts };
}
