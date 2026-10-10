// The "Needs attention" rows on Admin Control, from /api/admin/summary/.
// Each row names what needs action today and the page where it is handled.
import { t, tp, tx } from '../i18n.js';
import { dateText } from './format.js';
import { SEATS } from './workspacePlan.js';

const seatText = (seats = {}) => SEATS.filter(([key]) => seats[key])
  .map(([key, title]) => `${t(title)} ${seats[key].used}/${seats[key].limit}`).join(' · ');

function schoolRows(group, kind, meta) {
  if (!group?.count) return [];
  const rows = group.items.map((item) => ({ key: `${kind}-${item.id}`, kind, page: 'admin_schools', title: item.name, meta: meta(item) }));
  const more = group.count - group.items.length;
  if (more > 0) rows.push({ key: `${kind}-more`, kind, page: 'admin_schools', title: tp('{n} more school|{n} more schools', more, { n: more }), meta: '' });
  return rows;
}

export function attentionRows(summary) {
  if (!summary) return [];
  const attention = summary.attention || {};
  const rows = [
    ...schoolRows(attention.expiring, 'expiring', (item) => (item.read_only ? t('Read-only workspace') : tx`Plan ends ${dateText(item.period_end)}`)),
    ...schoolRows(attention.seats_full, 'seats', (item) => tx`Seats full: ${seatText(item.seats)}`),
    ...schoolRows(attention.missing_login, 'login', () => t('No school login')),
  ];
  const tickets = (summary.support_open || 0) + (summary.support_in_progress || 0);
  if (tickets) rows.push({ key: 'support', kind: 'support', page: 'support', title: t('Support tickets'), meta: tx`${summary.support_open || 0} open · ${summary.support_in_progress || 0} in progress` });
  // No admin page lists reports yet, so this row informs without a link.
  if (summary.message_reports_pending) rows.push({ key: 'reports', kind: 'reports', page: null, title: t('Message reports'), meta: tp('{n} waiting for a moderator|{n} waiting for a moderator', summary.message_reports_pending, { n: summary.message_reports_pending }) });
  return rows;
}
