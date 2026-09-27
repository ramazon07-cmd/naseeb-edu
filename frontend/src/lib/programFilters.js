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
    if (!only) programs.push({ item, closed });
  }
  programs.sort((first, second) => (first.closed - second.closed)
    || (first.item.deadline || '9999').localeCompare(second.item.deadline || '9999')
    || String(first.item.title).localeCompare(String(second.item.title)));
  return { programs, counts };
}
