// Display helpers shared by the workspace pages.
import { t } from '../i18n.js';

export const LABELS = {
  admin: 'Admin', counselor: 'School Counselor', teacher: 'Teacher', organization: 'Organization School', student: 'Student',
  parent: 'Parent', mother: 'Mother', father: 'Father', guardian: 'Guardian',
  todo: 'To do', in_progress: 'In progress', submitted: 'Submitted', approved: 'Approved', late: 'Late',
  low: 'Low', medium: 'Medium', high: 'High', urgent: 'Urgent', researching: 'Researching',
  shortlisted: 'Shortlisted', applying: 'Applying', accepted: 'Accepted', rejected: 'Rejected',
  waitlisted: 'Waitlisted', dream: 'Dream', target: 'Target', safety: 'Safety', required: 'Required',
  uploaded: 'Uploaded', reviewing: 'Reviewing', draft: 'Draft', needs_revision: 'Needs revision',
  requested: 'Requested', drafting: 'Drafting', extracurricular: 'Extracurricular', volunteering: 'Volunteering',
  leadership: 'Leadership', club: 'Club', competition: 'Competition', community: 'Community service',
  school: 'School', regional: 'Regional', national: 'National', international: 'International',
  project: 'Project', research: 'Research', olympiad: 'Olympiad', startup: 'Startup', sport: 'Sport', art: 'Art',
  planned: 'Planned', completed: 'Completed', active: 'Active', pending: 'Pending', confirmed: 'Confirmed',
  cancelled: 'Cancelled', discussion: 'Discussion', question: 'Q&A', update: 'Update',
  direct: 'Direct', group: 'Group', public: 'Public', private: 'Private', urban: 'Urban', suburban: 'Suburban', rural: 'Rural',
  four_year: '4-year', two_year: '2-year', merit: 'Merit', need_based: 'Need-based', athletic: 'Athletic',
  full_ride: 'Full ride', full: 'Full funding', partial: 'Partial funding', fixed: 'Fixed amount',
  onsite: 'On-site', online: 'Online', hybrid: 'Hybrid', reach: 'Reach',
  academic: 'Academic', preferences: 'Preferences', financial: 'Financial', profile_strength: 'Profile strength',
  harassment: 'Harassment or bullying', unsafe: 'Unsafe content', privacy: 'Privacy concern', misinformation: 'Misinformation',
  open: 'Open', closed: 'Closed', technical: 'Technical', account: 'Account', application: 'Application', billing: 'Billing', other: 'Other',
  resolved: 'Resolved', dismissed: 'Dismissed', none: 'No action', content_removed: 'Content removed',
  muted_24h: 'Muted 24 hours', muted_7d: 'Muted 7 days',
  issued: 'Issued', reissued: 'Reissued', used: 'Used', revoked: 'Revoked', expired: 'Expired', expired_unconfirmed: 'Expired — not confirmed', password_changed: 'Password changed',
  trial: 'Trial', suspended: 'Suspended',
  // Document types
  passport: 'Passport', transcript: 'Transcript', ielts: 'IELTS', sat: 'SAT', cv: 'CV / Résumé',
  recommendation: 'Recommendation letter', essay: 'Essay', certificate: 'Certificate',
  // Messaging, moderation, reviews and roadmaps
  owner: 'Owner', moderator: 'Moderator', member: 'Member', spam: 'Spam', changes_requested: 'Changes requested',
  professional_onboarding: 'Professional onboarding', school_management: 'School management',
  diversity: 'Diversity', unspecified: 'To be confirmed', bachelor: 'Bachelor’s',
  personal_statement: 'Personal statement', supplement: 'Supplement', scholarship: 'Scholarship', free_writing: 'Free writing'
};

// Product audit actions are stable dotted codes; show them as sentences.
export const AUDIT_ACTIONS = {
  'account.created': 'Account created', 'account.deactivated': 'Account deactivated', 'account.moved': 'Account moved to another school',
  'counselor.created': 'Counselor created', 'counselor.created_individual': 'Individual counselor created',
  'counselor.updated': 'Counselor updated', 'counselor.transferred': 'Counselor transferred',
  'counselor_roadmap.assigned': 'Counselor roadmap assigned', 'counselor_roadmap.cancelled': 'Counselor roadmap cancelled',
  'counselor_roadmap_template.created': 'Roadmap template created', 'counselor_roadmap_template.updated': 'Roadmap template updated',
  'counselor_roadmap_mission.approve': 'Counselor mission approved', 'counselor_roadmap_mission.request_changes': 'Changes requested on a counselor mission',
  'credential.issued': 'Temporary password issued', 'organization_account.created': 'Organization login created',
  'parent.invited': 'Parent invited', 'school.created': 'School created', 'school.updated': 'School updated', 'school.deactivated': 'School deactivated',
  'student.moved': 'Student moved to another school', 'student.deactivated': 'Student deactivated', 'student.reactivated': 'Student reactivated',
  'student.counselor_assigned': 'Counselor assigned to student', 'student_360.viewed': 'Student 360 profile viewed',
  'student_visibility.viewed': 'Student 360 profile viewed', 'student_account.viewed': 'Student account viewed',
  'student_photo.viewed': 'Student photo viewed', 'student_xp.viewed': 'Student XP viewed',
  'subscription.changed': 'Workspace plan changed', 'support.profile_viewed': 'Support view opened'
};

export const label = (value) => t(LABELS[value] || value || '—');
// Unknown codes still read as words ("student_360.viewed" -> "Student 360 viewed").
export const auditActionLabel = (code) => {
  if (AUDIT_ACTIONS[code]) return t(AUDIT_ACTIONS[code]);
  const words = String(code || '').replace(/[._]+/g, ' ').trim();
  return words ? words[0].toUpperCase() + words.slice(1) : t('Action');
};
export const fullName = (user) => user?.full_name || [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.username || 'User';
export const initials = (name) => String(name || 'U').split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase();
export const ownStudent = (data) => data.students?.[0];
