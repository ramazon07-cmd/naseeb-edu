// An audit event's metadata as readable "label: value" lines for the audit log.
import { t } from '../i18n.js';
import { label } from './labels.js';

const SCHOOL_KEYS = ['school', 'from_school', 'to_school'];
// Values that are stable codes with a LABELS entry (statuses, tiers, roles, sanctions).
const CODED_KEYS = ['status', 'staff_tier', 'role', 'sanction', 'category', 'access', 'section', 'workspace_type'];
const KEY_LABELS = {
  reason: 'Reason', status: 'Status', staff_tier: 'Staff tier', role: 'Role', sanction: 'Sanction', category: 'Category',
  school: 'School', from_school: 'From school', to_school: 'To school', source: 'Source', channel: 'Channel',
  reports_closed: 'Reports closed', name: 'Name', code: 'Code', contact_email: 'Contact email', contact_phone: 'Contact phone',
  is_active: 'Active', plan: 'Plan', period_start: 'Period start', period_end: 'Period end', description: 'Description',
  max_counselors: 'Counselor limit', max_students: 'Student limit', max_teachers: 'Teacher limit', features: 'Features',
  workspace_type: 'Workspace type', admin_tier: 'Staff tier', email: 'Email', username: 'Username',
};

const keyLabel = (key) => (KEY_LABELS[key] ? t(KEY_LABELS[key]) : String(key).replace(/_/g, ' ').replace(/^./, (first) => first.toUpperCase()));
const isChange = (value) => Boolean(value) && typeof value === 'object' && !Array.isArray(value) && 'from' in value && 'to' in value;

function valueText(key, value, names) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? t('Yes') : t('No');
  if (SCHOOL_KEYS.includes(key)) return names[String(value)] || `#${value}`;
  if (CODED_KEYS.includes(key)) return label(String(value));
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}

export function auditDetailLines(event) {
  const metadata = event?.metadata && typeof event.metadata === 'object' && !Array.isArray(event.metadata) ? event.metadata : {};
  const names = event?.school_names || {};
  const lines = [];
  for (const [key, value] of Object.entries(metadata)) {
    if (key === 'changes' && value && typeof value === 'object') {
      for (const [field, change] of Object.entries(value)) {
        lines.push({ key: `changes.${field}`, label: keyLabel(field), value: isChange(change) ? `${valueText(field, change.from, names)} → ${valueText(field, change.to, names)}` : valueText(field, change, names) });
      }
    } else if (isChange(value)) {
      lines.push({ key, label: keyLabel(key), value: `${valueText(key, value.from, names)} → ${valueText(key, value.to, names)}` });
    } else {
      lines.push({ key, label: keyLabel(key), value: valueText(key, value, names) });
    }
  }
  return lines;
}
