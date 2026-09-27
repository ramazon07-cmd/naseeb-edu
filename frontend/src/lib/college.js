// Pure helpers for College Search, the university pages and the Applications
// board: filtering, sorting, deadlines and application stages.
import { formatDateLocale, formatNumberLocale, formatPercentLocale, parseDateValue, t, tp, tx } from '../i18n.js';
import { money } from './format.js';
import { label } from './labels.js';
import { matchesQuery } from './searchIndex.js';

export const COLLEGE_REGIONS = [
  { key: 'us', label: 'US', countries: ['usa', 'united states', 'united states of america'] },
  { key: 'canada', label: 'Canada', countries: ['canada'] },
  { key: 'china', label: 'China', countries: ['china', 'mainland china'] },
  { key: 'hong_kong', label: 'Hong Kong', countries: ['hong kong', 'hong kong sar'] },
];

export function universityRegion(university) {
  const market = String(university?.market || '').trim().toLowerCase();
  if (COLLEGE_REGIONS.some((region) => region.key === market)) return market;
  const country = String(university?.country || '').trim().toLowerCase();
  return COLLEGE_REGIONS.find((region) => region.countries.includes(country))?.key || null;
}

export function universityFit(university, student) {
  if (!student) return { score: 0, label: 'Profile needed' };
  let score = 20;
  const targets = String(student.target_countries || '').toLowerCase();
  if (targets.includes(String(university.country || '').toLowerCase())) score += 25;
  if (!university.sat_min || Number(student.sat_score || 0) >= Number(university.sat_min)) score += 25;
  if (!university.net_price_usd || !student.budget_usd || Number(university.net_price_usd) <= Number(student.budget_usd)) score += 15;
  if (!student.scholarship_needed || university.offers_international_aid || university.offers_merit_aid) score += 15;
  const bounded = Math.min(score, 100);
  return { score: bounded, label: bounded >= 80 ? 'Strong fit' : bounded >= 60 ? 'Good fit' : 'Explore' };
}

export function scholarshipRequirements(item) {
  return [
  item.requires_transcript && 'Transcript', item.requires_essay && 'Essay',
  item.requires_recommendation && 'Recommendation', item.requires_financial_documents && 'Financial documents',
  item.requires_cv && 'CV', item.requires_portfolio && 'Portfolio'].
  filter(Boolean);
}

export function eligibleScholarship(item, student) {
  if (!student) return false;
  if (item.min_gpa && Number(student.gpa || 0) < Number(item.min_gpa)) return false;
  if (item.min_ielts && Number(student.ielts_score || 0) < Number(item.min_ielts)) return false;
  if (item.min_sat && Number(student.sat_score || 0) < Number(item.min_sat)) return false;
  return !item.eligible_grades || String(item.eligible_grades).split(',').map((value) => value.trim()).includes(String(student.grade));
}

export const DEFAULT_COLLEGE_FILTERS = { regions: COLLEGE_REGIONS.map((region) => region.key), bands: ['reach', 'target', 'safety'], price: 'all', aid: [], testOptional: false, satFit: false, publicOnly: false };

export const COLLEGE_PRICE_CAPS = ['all', 'budget', '25000', '40000'];

export const COLLEGE_AID_FLAGS = [['offers_need_based_aid', 'Need-based'], ['offers_merit_aid', 'Merit'], ['offers_international_aid', 'International aid'], ['meets_full_need', 'Meets full need']];

export const COLLEGE_SORTS = [['fit', 'Best fit'], ['price', 'Lowest net price'], ['deadline', 'Nearest deadline'], ['acceptance', 'Highest acceptance rate'], ['ranking', 'Best ranking']];

export const SCORE_PARTS = [['academic', 48], ['preferences', 22], ['financial', 20], ['profile_strength', 10]];

export const SAT_SCALE = [1000, 1600];

export const PRICE_SCALE_MAX = 70000;

export const toggleIn = (list, value) => list.includes(value) ? list.filter((item) => item !== value) : [...list, value];

export const satText = (min, max) => `${formatNumberLocale(min, { useGrouping: false })}–${max ? formatNumberLocale(max, { useGrouping: false }) : '—'}`;

export const satInRange = (university, student) => !university.sat_min || Number(student?.sat_score || 0) >= Number(university.sat_min);

export const scalePercent = (value, min, max) => `${Math.max(0, Math.min(100, (Number(value) - min) / (max - min) * 100))}%`;

export const priceCapLabel = (cap) => cap === 'all' ? t("Any price") : cap === 'budget' ? t("Within budget") : tx`Up to ${money(Number(cap))}`;

export function collegeMatches(university, result, filters, student, query) {
  const cap = filters.price === 'budget' ? Number(student?.budget_usd) || 0 : Number(filters.price);
  return filters.regions.includes(universityRegion(university)) && (
  filters.bands.length === 3 || filters.bands.includes(result?.admission_band)) && (
  filters.price === 'all' || Number(university.net_price_usd || Infinity) <= cap) &&
  filters.aid.every((flag) => university[flag]) && (
  !filters.testOptional || university.test_optional) && (
  !filters.satFit || satInRange(university, student)) && (
  !filters.publicOnly || university.institution_type === 'public') &&
  matchesQuery(university, query);
}

export function collegeSorter(sort, researchMap, student) {
  const fit = (university) => researchMap.get(university.id)?.match_score ?? universityFit(university, student).score;
  const time = (value) => value ? parseDateValue(value).getTime() : Infinity;
  const last = (value) => value == null ? Infinity : Number(value);
  return {
    fit: (a, b) => fit(b) - fit(a),
    price: (a, b) => last(a.net_price_usd) - last(b.net_price_usd),
    deadline: (a, b) => time(a.application_deadline) - time(b.application_deadline),
    acceptance: (a, b) => Number(b.acceptance_rate ?? -1) - Number(a.acceptance_rate ?? -1),
    ranking: (a, b) => last(a.ranking) - last(b.ranking)
  }[sort];
}

export function collegeFacetCounts(universities, researchMap, student) {
  const counts = { regions: {}, bands: { reach: 0, target: 0, safety: 0 }, aid: {}, testOptional: 0, satFit: 0, publicOnly: 0 };
  universities.forEach((university) => {
    const region = universityRegion(university);
    const band = researchMap.get(university.id)?.admission_band;
    if (region) counts.regions[region] = (counts.regions[region] || 0) + 1;
    if (band) counts.bands[band] += 1;
    COLLEGE_AID_FLAGS.forEach(([flag]) => {if (university[flag]) counts.aid[flag] = (counts.aid[flag] || 0) + 1;});
    if (university.test_optional) counts.testOptional += 1;
    if (satInRange(university, student)) counts.satFit += 1;
    if (university.institution_type === 'public') counts.publicOnly += 1;
  });
  return counts;
}

export function collegeFilterChips(filters, setFilters, budget) {
  const reset = (change) => () => setFilters((current) => ({ ...current, ...change }));
  const chips = [];
  if (filters.regions.length < COLLEGE_REGIONS.length) chips.push({ key: 'regions', text: COLLEGE_REGIONS.filter((region) => filters.regions.includes(region.key)).map((region) => t(region.label)).join(', ') || t("No country"), clear: reset({ regions: DEFAULT_COLLEGE_FILTERS.regions }) });
  if (filters.bands.length < 3) chips.push({ key: 'bands', text: filters.bands.map(label).join(', ') || t("No band"), clear: reset({ bands: DEFAULT_COLLEGE_FILTERS.bands }) });
  if (filters.price !== 'all') chips.push({ key: 'price', text: filters.price === 'budget' ? `${t("Within budget")} ${money(budget)}` : priceCapLabel(filters.price), clear: reset({ price: 'all' }) });
  COLLEGE_AID_FLAGS.filter(([flag]) => filters.aid.includes(flag)).forEach(([flag, title]) => chips.push({ key: flag, text: t(title), clear: reset({ aid: filters.aid.filter((item) => item !== flag) }) }));
  if (filters.testOptional) chips.push({ key: 'testOptional', text: t("Test optional"), clear: reset({ testOptional: false }) });
  if (filters.satFit) chips.push({ key: 'satFit', text: t("My SAT is in range"), clear: reset({ satFit: false }) });
  if (filters.publicOnly) chips.push({ key: 'publicOnly', text: t("Public only"), clear: reset({ publicOnly: false }) });
  return chips;
}

export function matchingPrograms(university, major) {
  const target = String(major || '').trim().toLowerCase();
  if (!target) return [];
  return (university.programs || []).filter((program) => {
    const canonical = String(program.canonical_major || '').trim().toLowerCase();
    return canonical && (canonical.includes(target) || target.includes(canonical));
  });
}

export const shortDate = (value) => formatDateLocale(value, { day: 'numeric', month: 'short' });

export const longDate = (value) => formatDateLocale(value, { weekday: 'long', day: 'numeric', month: 'long' });

export const percentText = (value) => value == null || value === '' ? '—' : formatPercentLocale(value, { maximumFractionDigits: 1 });

// Whole calendar days from today to a due date (negative once it has passed).
export function daysUntil(value) {
  if (!value) return null;
  const date = parseDateValue(value);
  if (Number.isNaN(date.getTime())) return null;
  const now = new Date();
  return Math.round((new Date(date.getFullYear(), date.getMonth(), date.getDate()) - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
}

export const dueLabel = (days) => days < 0 ? t("Overdue") : days === 0 ? t("Today") : days === 1 ? t("Tomorrow") : tp('{n} day left|{n} days left', days, { n: days });

export const dueTone = (days) => days <= 3 ? 'hot' : days <= 21 ? 'soon' : '';

export function essayProgress(essays) {
  const total = essays.length;
  const approved = essays.filter((essay) => essay.status === 'approved').length;
  if (!total) return { tone: 'dash', text: t("No essays yet") };
  if (approved === total) return { tone: 'ok', text: tx`Essays ${approved}/${total}` };
  if (essays.some((essay) => essay.status === 'needs_revision')) return { tone: 'warn', text: tx`Essays ${approved}/${total} · revise` };
  return { tone: '', text: essays.some((essay) => essay.status === 'reviewing') ? tx`Essays ${approved}/${total} · in review` : tx`Essays ${approved}/${total} · draft` };
}

export const APPLICATION_STAGES = [
  { key: 'researching', title: 'Researching', description: 'Looking at options' },
  { key: 'shortlisted', title: 'Shortlisted', description: 'On your list' },
  { key: 'applying', title: 'Applying', description: 'Preparing your documents' },
  { key: 'submitted', title: 'Submitted', description: 'Waiting for a decision' },
  { key: 'decision', title: 'Decision', description: 'Recorded by your counselor', locked: true }
];

export const DECISION_STATUSES = ['accepted', 'rejected', 'waitlisted'];

export const stageOf = (status) => DECISION_STATUSES.includes(status) ? 'decision' : status;

export const historyDate = (application, status) => application.status_history?.find((entry) => entry.status === status)?.created_at;

export function nextDeadline(applications) {
  return applications.
  filter((application) => ['researching', 'shortlisted', 'applying'].includes(application.status)).
  flatMap((application) => [['application', application.deadline], ['aid', application.scholarship_deadline]].map(([kind, date]) => ({ application, kind, date, days: daysUntil(date) }))).
  filter((item) => item.days != null && item.days >= 0).
  sort((a, b) => a.days - b.days)[0];
}
