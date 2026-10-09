// The student's profile answers, split into the sections the Student Center
// edits one at a time. Onboarding asks the same questions as six steps.
import { ONBOARDING_STEP_FIELDS } from './onboardingDraft.js';
import { testScoresFromProfile, testScoresPayload, validateTestScores } from './testScores.js';

export const PROFILE_SECTIONS = [
  { key: 'personal', title: 'Personal & contact', step: 0 },
  { key: 'academics', title: 'Academics', step: 1 },
  { key: 'tests', title: 'Test scores', step: 2 },
  { key: 'goal', title: 'Study goal & targets', step: 3 },
  { key: 'honors', title: 'Honors', step: 4 },
  { key: 'activities', title: 'Activities', step: 5 },
].map((section) => ({ ...section, fields: ONBOARDING_STEP_FIELDS[section.step].filter((name) => name !== 'photo') }));

// A counselor's review of each section, as the profile payload's
// section_reviews reports it. Saving a change sends a section back to waiting.
export const REVIEW_STATUSES = {
  not_reviewed: { label: 'Not reviewed', tone: '' },
  waiting: { label: 'Waiting for review', tone: 'is-pending' },
  approved: { label: 'Approved', tone: 'is-verified' },
  changes_requested: { label: 'Needs changes', tone: 'is-changes' },
};

export function sectionReview(student, key) {
  const review = student?.section_reviews?.[key];
  const status = review && REVIEW_STATUSES[review.status] ? review.status : 'not_reviewed';
  return { status, ...REVIEW_STATUSES[status], note: status === 'changes_requested' ? String(review?.note || '').trim() : '' };
}

// Review notices name their section by position (1-based), so the reader's
// language can title it.
export const sectionFromNotice = (targetId) => PROFILE_SECTIONS[Number(targetId) - 1] || null;

export const sectionByKey = (key) => PROFILE_SECTIONS.find((section) => section.key === key) || null;

export const COUNTRIES = ['US', 'UK', 'Canada', 'Turkey', 'Vietnam', 'Hong Kong', 'China'];
// Older records hold spellings this form never offered ('USA', 'Singapore').
// They match no checkbox, so they stay invisible on screen yet are still sent
// on save, and the backend rejects the whole field for a country the student
// cannot see or untick. Map what has an equivalent, drop what does not.
export const COUNTRY_ALIASES = { USA: 'US', 'United States': 'US', 'United Kingdom': 'UK', GB: 'UK', HK: 'Hong Kong' };
export const supportedCountries = (list) => [...new Set(list.map((c) => COUNTRY_ALIASES[c] || c).filter((c) => COUNTRIES.includes(c)))];
export const INCOMES = ['Under $10,000', '$10,000–$25,000', '$25,000–$50,000', '$50,000–$100,000', '$100,000+'];
export const INTERESTS = ['Arts', 'Humanities', 'Political science', 'Business', 'Economics', 'Accounting', 'Communications', 'Health and Medicine', 'Public and Social Services', 'Math and Statistics', 'Environmental Science', 'Computer Technologies', 'Science', 'Education', 'Engineering', 'English', 'History', 'Psychology'];
export const STRENGTHS = ['STEM', 'Liberal Arts', 'Specialized programs', 'Research opportunities', 'No Preference'];
// CV answers (backend/apps/admissions/onboarding.py has the same limits).
export const LANGUAGE_LEVELS = ['Native', 'Fluent', 'Advanced', 'Intermediate', 'Basic'];
export const MAX_LANGUAGES = 10;
// Skills and hobbies are typed as one comma-separated line and saved as a list.
const PHRASE_LISTS = { skills: 30, hobbies: 20 };
const PHRASE_LENGTH = 60;
const NUMERIC = ['graduation_year', 'class_size', 'class_rank', 'gpa'];
// Test answers once lived in application_profile; the columns are authoritative now.
const LEGACY_TEST_KEYS = ['ielts_status', 'ielts_score', 'sat_status', 'sat_reading', 'sat_math', 'sat_attempts'];
const DEFAULTS = { subjects: [], certificates: [], interests: [], program_strengths: [], honors: [], activities: [], languages: [], linkedin_url: '', website_url: '' };

export const splitList = (value) => (Array.isArray(value) ? value : String(value || '').split(',').map((c) => c.trim()).filter(Boolean));

// "Singapore,Hong Kong" → "Singapore, Hong Kong" for display.
export const listText = (value) => splitList(value).join(', ');

// Profile API -> form state for every question.
export function profileAnswers(profile) {
  const stored = Object.fromEntries(Object.entries(profile.application_profile || {}).filter(([key]) => !LEGACY_TEST_KEYS.includes(key)));
  const form = {
    ...DEFAULTS,
    ...stored,
    guardian_name: profile.guardian_name || '',
    guardian_relation: profile.guardian_relation || '',
    guardian_contact: profile.parent_contact || '',
    first_name: profile.user_detail?.first_name ?? stored.first_name ?? '',
    last_name: profile.user_detail?.last_name ?? stored.last_name ?? '',
    grade: profile.grade,
    school_name: profile.school_name,
    gpa: profile.gpa ?? '',
    gpa_scale: profile.gpa_scale != null ? String(profile.gpa_scale) : (stored.gpa_scale ?? ''),
    ...testScoresFromProfile(profile),
  };
  for (const key of ['subjects', 'certificates', 'interests', 'program_strengths', 'honors', 'activities', 'languages']) if (!Array.isArray(form[key])) form[key] = [];
  for (const key of Object.keys(PHRASE_LISTS)) form[key] = splitList(form[key]).join(', ');
  form.subjects = form.subjects.map((row) => ({ ...row, score: row.score == null ? '' : String(row.score) }));
  form.certificates = form.certificates.map((row) => ({ ...row, score: row.score == null ? '' : String(row.score), test_date: row.test_date || '' }));
  form.target_countries = supportedCountries(splitList(profile.target_countries));
  return form;
}

// Form state -> API payload. With a section, only that section's answers.
export function answersPayload(form, sectionKey = null) {
  const payload = { ...form, ...testScoresPayload(form), target_countries: (form.target_countries || []).join(', ') };
  for (const key of Object.keys(PHRASE_LISTS)) payload[key] = phraseList(form[key]);
  payload.languages = (form.languages || []).map((row) => ({ name: String(row.name || '').trim(), level: row.level || '' }));
  NUMERIC.forEach((key) => { payload[key] = form[key] === '' || form[key] == null ? null : Number(form[key]); });
  const section = sectionKey ? sectionByKey(sectionKey) : null;
  if (!section) return payload;
  return Object.fromEntries(section.fields.filter((name) => name in payload).map((name) => [name, payload[name]]));
}

// "Python, , python, SQL" -> ['Python', 'SQL']: trimmed, blanks and repeats dropped.
export function phraseList(value) {
  const seen = new Set();
  return splitList(value).filter((item) => {
    const key = item.toLocaleLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// Checks the browser can make before saving; { field: [message, ...args] }.
export function validateSection(sectionKey, form, today = new Date()) {
  if (sectionKey === 'tests') return validateTestScores(form, today);
  if (sectionKey !== 'goal') return {};
  const errors = {};
  if (!(form.target_countries || []).length) errors.target_countries = ['Select at least one country.'];
  const languages = form.languages || [];
  if (languages.length > MAX_LANGUAGES) errors.languages = ['You can add up to {0} languages.', MAX_LANGUAGES];
  languages.forEach((row, i) => {
    if (!String(row.name || '').trim()) errors[`languages.${i}.name`] = ['Enter the language.'];
    if (!LANGUAGE_LEVELS.includes(row.level)) errors[`languages.${i}.level`] = ['Choose a level.'];
  });
  for (const [key, max] of Object.entries(PHRASE_LISTS)) {
    const items = phraseList(form[key]);
    if (items.length > max) errors[key] = [key === 'skills' ? 'You can add up to {0} skills.' : 'You can add up to {0} interests.', max];
    else if (items.some((item) => item.length > PHRASE_LENGTH)) errors[key] = ['Keep each item under {0} characters.', PHRASE_LENGTH];
  }
  return errors;
}

// Readiness items the backend reports as missing -> what the student can do.
export const READINESS_HINTS = {
  photo: 'add a profile photo',
  graduation_year: 'add your graduation year',
  guardian: 'add a guardian and their contact',
  school: 'add your school, country and city',
  gpa: 'add your GPA',
  ielts: 'add your IELTS result or plan',
  sat: 'add your SAT result or plan',
  countries: 'choose the countries you apply to',
  interests: 'choose your areas of interest',
  story: 'write a short personal story',
  activities: 'add an activity',
  honors: 'add an honor',
};

// The first missing items the hint names (the backend lists them in order).
export function readinessHints(readiness, limit = 2) {
  return (readiness?.missing || []).map((item) => ({ ...item, text: READINESS_HINTS[item.key] })).filter((item) => item.text).slice(0, limit);
}
