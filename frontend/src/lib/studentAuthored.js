import { t } from '../i18n.js';

// Work the student wrote. Staff may only review it (the API refuses anything else):
// no delete, and an edit form with the review fields only.
export const STUDENT_AUTHORED_RECORDS = ['essays', 'achievements', 'researches', 'projects', 'internships', 'activities', 'honors'];
const REVIEW_FIELDS = { essays: ['status', 'counselor_comment'] };

const isStaffOnStudentWork = (user, resource) => STUDENT_AUTHORED_RECORDS.includes(resource) && user?.role !== 'student';

export function canDeleteStudentRecord(user, resource) {
  return !isStaffOnStudentWork(user, resource);
}

// The form fields this user may change on an existing record.
export function editableFields(user, resource, fields) {
  if (!isStaffOnStudentWork(user, resource)) return fields;
  const review = REVIEW_FIELDS[resource] || [];
  return fields.filter(([name]) => review.includes(name));
}

const same = (value, current) => String(value ?? '') === String(current ?? '');

// An edit sends only what changed, so a review never re-sends (and races) the student's text.
export function changedPayload(payload, item) {
  return Object.fromEntries(Object.entries(payload).filter(([name, value]) => !same(value, item[name])));
}

// Server error codes (see the API's CollabError) with a message for each.
const ERROR_MESSAGES = {
  essay_changed: 'This essay changed since you opened it. Reload to see the latest version, then make your edit again.',
  precondition_required: 'Reload this essay before changing it, so newer changes are not overwritten.',
  student_authored: 'Only the student can change their own work. Send it back with a note instead.',
  student_authored_delete: 'Only the student can delete their own work. Send it back with a note instead.',
};

export function recordErrorMessage(error) {
  const message = ERROR_MESSAGES[error?.details?.code];
  return message ? t(message) : error?.message;
}
