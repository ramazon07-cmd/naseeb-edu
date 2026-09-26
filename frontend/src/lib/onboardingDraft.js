// Onboarding helpers: a per-user draft so a six-step form survives a reload,
// and mapping of server validation errors back onto fields and steps.

export const ONBOARDING_STEP_FIELDS = [
  ['first_name', 'middle_name', 'last_name', 'gender', 'grade', 'graduation_year', 'first_generation', 'family_income', 'residency_status', 'guardian_name', 'guardian_relation', 'guardian_contact', 'photo'],
  ['school_name', 'country', 'state', 'city', 'class_size', 'class_rank', 'gpa_scale', 'gpa'],
  ['ielts_status', 'ielts_score', 'ielts_listening', 'ielts_reading', 'ielts_writing', 'ielts_speaking', 'ielts_test_date', 'ielts_attempts',
    'sat_status', 'sat_reading', 'sat_math', 'sat_test_date', 'sat_attempts', 'sat_superscore', 'sat_superscore_reading', 'sat_superscore_math', 'subjects'],
  ['target_countries', 'interests', 'program_strengths', 'personal_story'],
  ['honors'],
  ['activities'],
];

export function loadDraft(storage, key) {
  try {
    const draft = JSON.parse(storage.getItem(key) || 'null');
    if (!draft || typeof draft !== 'object' || !draft.form || typeof draft.form !== 'object') return null;
    const step = Number.isInteger(draft.step) && draft.step >= 0 && draft.step < ONBOARDING_STEP_FIELDS.length ? draft.step : 0;
    return { form: draft.form, step };
  } catch {
    return null;
  }
}

export function saveDraft(storage, key, form, step) {
  try { storage.setItem(key, JSON.stringify({ form, step, savedAt: Date.now() })); } catch { /* private mode */ }
}

export function clearDraft(storage, key) {
  try { storage.removeItem(key); } catch { /* private mode */ }
}

// {"gpa": ["Ensure this value is less than or equal to 5."], "honors": [{}, {"role": [...]}]}
// -> { gpa: "Ensure ...", honors: "Ensure ..." }
export function fieldErrorsFrom(details) {
  if (!details || typeof details !== 'object' || Array.isArray(details)) return {};
  const flatten = (value) => {
    if (value == null) return [];
    if (Array.isArray(value)) return value.flatMap(flatten);
    if (typeof value === 'object') return Object.values(value).flatMap(flatten);
    return [String(value)];
  };
  const out = {};
  for (const [field, value] of Object.entries(details)) {
    if (field === 'detail' || field === 'non_field_errors') continue;
    const messages = flatten(value).filter(Boolean);
    if (messages.length) out[field] = messages.join(' ');
  }
  return out;
}

export function firstStepWithError(fieldErrors, stepFields = ONBOARDING_STEP_FIELDS) {
  const index = stepFields.findIndex((fields) => fields.some((field) => field in fieldErrors));
  return index;
}
