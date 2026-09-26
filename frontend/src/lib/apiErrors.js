// Turns a DRF validation payload into a sentence a person can act on:
// {"target_countries": ["This field is required."], "non_field_errors": [...]}
// -> "Target countries: This field is required. • ..."
const GENERAL_FIELDS = new Set(['non_field_errors', 'detail', '__all__']);

export function humanizeField(field) {
  const text = String(field).replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  if (/^\d+$/.test(text)) return `#${Number(text) + 1}`;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function collect(value, path, out) {
  if (value === null || value === undefined || value === '') return;
  if (Array.isArray(value)) {
    if (value.every((item) => typeof item !== 'object' || item === null)) {
      out.push([path, value.filter((item) => item !== null && item !== '').join(' ')]);
    } else {
      value.forEach((item, index) => collect(item, [...path, String(index)], out));
    }
    return;
  }
  if (typeof value === 'object') {
    for (const [key, nested] of Object.entries(value)) collect(nested, [...path, key], out);
    return;
  }
  out.push([path, String(value)]);
}

export function formatValidationErrors(payload, translate = (text) => text) {
  const out = [];
  collect(payload, [], out);
  return out
    .filter(([, message]) => message)
    .map(([path, message]) => {
      const fields = path.filter((key) => !GENERAL_FIELDS.has(key));
      if (!fields.length) return message;
      return `${fields.map((key) => translate(humanizeField(key))).join(' › ')}: ${message}`;
    })
    .join(' • ');
}

// DRF-style field errors: a list of messages, or an object/list of those
// (nested serializers). Anything else in an error body (code, save_seq, a
// document…) is metadata, not something to show.
function isFieldErrorValue(value) {
  if (Array.isArray(value)) return value.length > 0 && value.every((item) => typeof item === 'string' || isFieldErrorValue(item) || (item && typeof item === 'object' && !Object.keys(item).length));
  if (value && typeof value === 'object') return Object.keys(value).length > 0 && Object.values(value).every(isFieldErrorValue);
  return false;
}

// The message for an error response body. Field errors win over `detail`, so a
// form shows every problem at once instead of only a summary:
//   {"detail": "...", "code": "invalid", "errors": {"email": ["..."]}}
//   {"detail": "...", "email": ["..."], "non_field_errors": ["..."]}
// Without field errors it falls back to `detail`.
export function errorPayloadMessage(payload, translate = (text) => text) {
  if (!payload || typeof payload !== 'object') return '';
  if (Array.isArray(payload)) return formatValidationErrors(payload, translate);
  const source = payload.errors && typeof payload.errors === 'object' ? payload.errors : payload;
  const fields = Object.fromEntries(Object.entries(source).filter(([key, value]) => key !== 'detail' && isFieldErrorValue(value)));
  const listed = formatValidationErrors(fields, translate);
  if (listed) return listed;
  if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail;
  return formatValidationErrors(payload.detail ?? {}, translate);
}
