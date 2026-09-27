// Seat usage rows for a school card: [key, used, limit (null = unlimited), over].
const SEATS = [['max_counselors', 'Counselors'], ['max_students', 'Students'], ['max_teachers', 'Teachers']];

export function seatUsage(school) {
  const usage = school?.seat_usage;
  const limits = school?.subscription?.limits || {};
  if (!usage) return [];
  return SEATS.map(([key, title]) => {
    const used = Number(usage[key]) || 0;
    const limit = limits[key] ?? null;
    return { key, title, used, limit, over: limit !== null && used > limit, full: limit !== null && used >= limit };
  });
}

// Date inputs send '' when cleared; the API expects null for an open period.
export function subscriptionPayload(values) {
  const optionalDate = (value) => (String(value || '').trim() || null);
  return {
    plan: values.plan,
    status: values.status,
    period_start: optionalDate(values.period_start),
    period_end: optionalDate(values.period_end),
  };
}
