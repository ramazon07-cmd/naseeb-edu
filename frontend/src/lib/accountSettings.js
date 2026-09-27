// Account settings helpers, framework-free so they are unit tested.

// Messages the account endpoints write in English; the page shows them in the
// user's language. Password-rule messages come from Django already localized.
export const ACCOUNT_ERROR_MESSAGES = [
  'Your current password is incorrect.',
  'This email address is already used by another account.',
  'Choose a password different from your current password.',
  'Passwords do not match.',
];

// DRF field errors ({"email": ["..."]}) -> {email: "..."}; `form` holds a
// message with no field. Known messages are translated with `translate`.
export function accountFieldErrors(details, fallback = '', translate = (text) => text) {
  const known = new Set(ACCOUNT_ERROR_MESSAGES);
  const errors = {};
  if (details && typeof details === 'object' && !Array.isArray(details)) {
    for (const [field, messages] of Object.entries(details)) {
      const list = (Array.isArray(messages) ? messages : [messages]).filter((item) => typeof item === 'string' && item);
      if (!list.length || field === 'code') continue;
      errors[field === 'detail' || field === 'non_field_errors' ? 'form' : field] = list.map((item) => (known.has(item) ? translate(item) : item)).join(' ');
    }
  }
  if (!Object.keys(errors).length && fallback) errors.form = fallback;
  return errors;
}

