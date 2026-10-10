// Seat usage rows for a school card: [key, used, limit (null = unlimited), over].
export const SEATS = [['max_counselors', 'Counselors'], ['max_students', 'Students'], ['max_teachers', 'Teachers']];

// Plan feature flags in display order (backend PLAN_FEATURES).
export const PLAN_FEATURES = [['ai_assistant', 'AI assistant'], ['essay_coach', 'Essay coach'], ['parent_portal', 'Parent portal'], ['reports', 'Reports'], ['organization_accounts', 'School logins']];

// Plans a workspace can be put on: its current plan (even a retired one) and
// the active plans made for its kind of workspace.
export function plansFor(plans, school) {
  const current = school?.subscription?.plan;
  return plans.filter((plan) => plan.code === current || (plan.is_active && plan.workspace_type === school?.workspace_type));
}

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
