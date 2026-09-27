// IELTS / SAT / AP / IB rules for the profile form. They mirror
// backend/apps/admissions/exam_scores.py and onboarding.py so a student sees the
// same message before saving that the server would send after.

export const TEST_STATUSES = ['not_taken', 'planning', 'scheduled', 'taken', 'not_required'];
export const IELTS_SECTIONS = [['ielts_listening', 'Listening'], ['ielts_reading', 'Reading'], ['ielts_writing', 'Writing'], ['ielts_speaking', 'Speaking']];
export const IELTS_BANDS = Array.from({ length: 19 }, (_, i) => (18 - i) / 2);
export const SUBJECT_SCORE_MAX = { AP: 5, IB: 7 };
export const MAX_ATTEMPTS = 20;
const EARLIEST_TEST_DATE = '2015-01-01';

const blank = (value) => value == null || value === '';
const num = (value) => (blank(value) ? null : Number(value));

// Official band rounding: the mean goes to the nearest half band, .25 and .75 round up.
export function ieltsOverall(sections) {
  if (sections.length !== 4 || sections.some(blank)) return null;
  const mean = sections.reduce((sum, value) => sum + Number(value), 0) / 4;
  return Math.floor(mean * 2 + 0.5) / 2;
}

export function ieltsOverallFromForm(form) {
  return ieltsOverall(IELTS_SECTIONS.map(([key]) => form[key]));
}

export function satSentTotal({ sat_reading, sat_math, sat_superscore, sat_superscore_reading, sat_superscore_math }) {
  if (sat_superscore === true && !blank(sat_superscore_reading) && !blank(sat_superscore_math)) return Number(sat_superscore_reading) + Number(sat_superscore_math);
  if (!blank(sat_reading) && !blank(sat_math)) return Number(sat_reading) + Number(sat_math);
  return null;
}

export const canSuperscore = (form) => form.sat_status === 'taken' && num(form.sat_attempts) >= 2;

const isoDate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

function checkDate(errors, form, key, status, today) {
  const value = form[key];
  if (blank(value)) {
    if (status === 'taken') errors[key] = ['Enter the date you took the test.'];
    else if (status === 'scheduled') errors[key] = ['Enter the date of your booked test.'];
    return;
  }
  const latest = new Date(today); latest.setDate(latest.getDate() + 3 * 366);
  if (status === 'taken' && value > isoDate(today)) errors[key] = ['This date is in the future. If the test has not happened yet, choose "I have booked a test date".'];
  else if (value < EARLIEST_TEST_DATE) errors[key] = ['Enter a date from 2015 or later.'];
  else if (value > isoDate(latest)) errors[key] = ['Enter a date within the next three years.'];
}

function checkAttempts(errors, form, key) {
  const value = num(form[key]);
  if (value != null && (!Number.isInteger(value) || value < 1 || value > MAX_ATTEMPTS)) errors[key] = ['Enter a number from 1 to {0}.', MAX_ATTEMPTS];
}

function checkSatSection(errors, form, key, requiredMessage) {
  const value = num(form[key]);
  if (value == null) { if (requiredMessage) errors[key] = [requiredMessage]; return; }
  if (!Number.isInteger(value) || value < 200 || value > 800) errors[key] = ['SAT section scores go from 200 to 800.'];
  else if (value % 10) errors[key] = ['SAT scores go up in steps of 10, like 650 or 660.'];
}

// Returns { field: [message, ...args] } with English source text; the caller translates.
export function validateTestScores(form, today = new Date()) {
  const errors = {};
  if (form.ielts_status === 'taken') {
    const sections = IELTS_SECTIONS.map(([key]) => form[key]);
    const given = sections.map((value) => !blank(value));
    if (given.some(Boolean) && !given.every(Boolean)) IELTS_SECTIONS.forEach(([key], i) => { if (!given[i]) errors[key] = ['Enter all four section scores, or leave all four empty.']; });
    const overall = ieltsOverall(sections);
    if (overall == null && blank(form.ielts_score)) errors.ielts_score = ['Enter your overall band score.'];
    else if (overall != null && !blank(form.ielts_score) && Number(form.ielts_score) !== overall) errors.ielts_score = ['With these section scores your overall band is {0}. Check your test report.', overall];
    checkDate(errors, form, 'ielts_test_date', 'taken', today);
    checkAttempts(errors, form, 'ielts_attempts');
  } else if (form.ielts_status === 'planning' || form.ielts_status === 'scheduled') {
    checkDate(errors, form, 'ielts_test_date', form.ielts_status, today);
  }
  if (form.sat_status === 'taken') {
    checkSatSection(errors, form, 'sat_reading', 'Enter this section score.');
    checkSatSection(errors, form, 'sat_math', 'Enter this section score.');
    checkDate(errors, form, 'sat_test_date', 'taken', today);
    checkAttempts(errors, form, 'sat_attempts');
    if (canSuperscore(form) && !errors.sat_attempts) {
      if (form.sat_superscore == null) errors.sat_superscore = ['Choose Yes or No.'];
      else if (form.sat_superscore === true) {
        for (const [best, day] of [['sat_superscore_reading', 'sat_reading'], ['sat_superscore_math', 'sat_math']]) {
          checkSatSection(errors, form, best, 'Enter your highest score for this section.');
          if (!errors[best] && !errors[day] && Number(form[best]) < Number(form[day])) errors[best] = ['Your highest score cannot be lower than your best test day score.'];
        }
      }
    }
  } else if (form.sat_status === 'planning' || form.sat_status === 'scheduled') {
    checkDate(errors, form, 'sat_test_date', form.sat_status, today);
  }
  (form.subjects || []).forEach((row, i) => {
    if (!String(row.subject || '').trim()) errors[`subjects.${i}.subject`] = ['Enter the subject.'];
    const max = SUBJECT_SCORE_MAX[row.type];
    const score = num(row.score);
    if (!max) errors[`subjects.${i}.type`] = ['Choose AP or IB.'];
    else if (score == null) errors[`subjects.${i}.score`] = ['Choose your score.'];
    else if (!Number.isInteger(score) || score < 1 || score > max) errors[`subjects.${i}.score`] = [row.type === 'AP' ? 'AP scores go from 1 to 5.' : 'IB scores go from 1 to 7.'];
  });
  return errors;
}

// The form keeps inputs as strings; the API wants numbers, booleans and nulls.
export function testScoresPayload(form) {
  const out = {};
  const ints = ['ielts_attempts', 'sat_reading', 'sat_math', 'sat_attempts', 'sat_superscore_reading', 'sat_superscore_math'];
  const bands = ['ielts_score', ...IELTS_SECTIONS.map(([key]) => key)];
  for (const key of [...ints, ...bands]) out[key] = num(form[key]);
  if (form.ielts_status === 'taken' && out.ielts_score == null) out.ielts_score = ieltsOverallFromForm(form);
  for (const key of ['ielts_test_date', 'sat_test_date']) out[key] = blank(form[key]) ? null : form[key];
  out.sat_superscore = canSuperscore(form) ? form.sat_superscore ?? null : null;
  out.subjects = (form.subjects || []).map((row) => ({ type: row.type, subject: String(row.subject || '').trim(), score: num(row.score) }));
  return out;
}

// Profile API -> form state (strings for inputs, null for an unanswered yes/no).
export function testScoresFromProfile(profile) {
  const text = (value) => (value == null ? '' : String(value));
  const band = (value) => (value == null || value === '' ? '' : String(Number(value)));
  const form = {
    ielts_status: profile.ielts_status || (profile.ielts_score != null ? 'taken' : 'not_taken'),
    ielts_score: band(profile.ielts_score),
    ielts_test_date: text(profile.ielts_test_date),
    ielts_attempts: text(profile.ielts_attempts),
    sat_status: profile.sat_status || (profile.sat_score != null ? 'taken' : 'not_taken'),
    sat_reading: text(profile.sat_reading),
    sat_math: text(profile.sat_math),
    sat_test_date: text(profile.sat_test_date),
    sat_attempts: text(profile.sat_attempts),
    sat_superscore: profile.sat_superscore ?? null,
    sat_superscore_reading: text(profile.sat_superscore_reading),
    sat_superscore_math: text(profile.sat_superscore_math),
  };
  for (const [key] of IELTS_SECTIONS) form[key] = band(profile[key]);
  return form;
}
