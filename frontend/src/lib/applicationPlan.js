// A saved plan is preparation; opening a portal never means it was submitted.
export const PLAN_FIELDS = ['program', 'tier', 'deadline', 'scholarship_deadline', 'application_portal_url', 'notes'];

export function webUrl(value) {
  try {
    const url = new URL(String(value || '').trim());
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : '';
  } catch { return ''; }
}

export const activePrograms = (university) => (university?.programs || []).filter((program) => program.is_active !== false);
export const selectedProgram = (university, name) => activePrograms(university).find((program) => program.name.trim().toLowerCase() === String(name || '').trim().toLowerCase());

export function publishedPlan(university, name) {
  const program = selectedProgram(university, name);
  return {
    deadline: program?.application_deadline || university?.application_deadline || '',
    scholarship_deadline: program?.scholarship_deadline || university?.scholarship_deadline || '',
    // A university homepage is a source to research, never a guessed application portal.
    application_portal_url: webUrl(program?.application_url),
  };
}

export function planNextStep(application, essays = []) {
  if (['accepted', 'rejected', 'waitlisted'].includes(application.status)) return 'Your counselor has recorded the admission decision.';
  if (application.status === 'submitted') return 'Track the official portal for updates and share the decision with your counselor.';
  if (!String(application.program || '').trim()) return 'Choose the program you intend to apply to.';
  if (!application.deadline) return 'Check the official application round and save its deadline.';
  if (!webUrl(application.application_portal_url)) return 'Find the application portal on the official university website and save it here.';
  if (essays.some((essay) => essay.status === 'needs_revision')) return 'Revise the essays your counselor returned.';
  if (application.status !== 'applying') return 'Start preparation, then check the requirements in the official portal.';
  return 'Finish the official application, submit it there, then confirm submission here.';
}
