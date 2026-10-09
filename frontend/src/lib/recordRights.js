import { t } from '../i18n.js';
import { errorCodeKey } from '../translations/errorCodes.js';

// Records the API annotates for the viewer (essays and portfolio records) carry
// `editable_fields` and `can_delete`; others keep the form's own rules.
export function editableFields(item, fields) {
  return Array.isArray(item?.editable_fields) ? fields.filter(([name]) => item.editable_fields.includes(name)) : fields;
}

export const canDelete = (item, fallback) => (typeof item?.can_delete === 'boolean' ? item.can_delete : fallback);

const same = (value, current) => String(value ?? '') === String(current ?? '');

// An edit sends only what changed, so a review never re-sends (and races) the student's text.
export function changedPayload(payload, item) {
  return Object.fromEntries(Object.entries(payload).filter(([name, value]) => !same(value, item[name])));
}

// The form was built from an older copy of the record.
export const isStaleCopyError = (error) => ['essay_changed', 'precondition_required'].includes(error?.details?.code);

// A coded API error in the reader's language; English (and unknown codes) use the server's message.
export function recordErrorMessage(error) {
  const code = error?.details?.code;
  const key = code ? errorCodeKey(code) : '';
  const translated = key ? t(key) : key;
  return translated && translated !== key ? translated : error?.message;
}
