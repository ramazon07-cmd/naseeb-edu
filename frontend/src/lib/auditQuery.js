const AUDIT_FILTERS = ['action', 'actor', 'school', 'date_from', 'date_to'];

// The audit list's server filters: only known keys, trimmed, empty ones left out.
export function auditFilters(filters = {}) {
  const result = {};
  for (const key of AUDIT_FILTERS) {
    const value = String(filters[key] ?? '').trim();
    if (value) result[key] = value;
  }
  return result;
}
