import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { attentionRows } = await import('../src/lib/adminAttention.js');

const quiet = {
  support_open: 0, support_in_progress: 0, message_reports_pending: 0,
  attention: { expiring: { count: 0, items: [] }, seats_full: { count: 0, items: [] }, missing_login: { count: 0, items: [] } },
};

test('nothing to do means no rows (the panel says all clear)', () => {
  assert.deepEqual(attentionRows(quiet), []);
  assert.deepEqual(attentionRows(null), []);
});

test('each kind of problem becomes rows that link to where it is fixed', () => {
  const rows = attentionRows({
    ...quiet,
    support_open: 2,
    support_in_progress: 1,
    message_reports_pending: 1,
    attention: {
      expiring: { count: 2, items: [{ id: 1, name: 'Old School', read_only: true }, { id: 2, name: 'Soon School', read_only: false, period_end: '2026-10-20' }] },
      seats_full: { count: 1, items: [{ id: 3, name: 'Full School', seats: { max_counselors: { used: 3, limit: 3 } } }] },
      missing_login: { count: 12, items: [{ id: 4, name: 'No Login School' }] },
    },
  });
  assert.deepEqual(rows.map((row) => [row.kind, row.page, row.title]), [
    ['expiring', 'admin_schools', 'Old School'],
    ['expiring', 'admin_schools', 'Soon School'],
    ['seats', 'admin_schools', 'Full School'],
    ['login', 'admin_schools', 'No Login School'],
    ['login', 'admin_schools', '11 more schools'],
    ['support', 'support', 'Support tickets'],
    ['reports', null, 'Message reports'],
  ]);
  assert.equal(rows[0].meta, 'Read-only workspace');
  assert.match(rows[1].meta, /^Plan ends /);
  assert.equal(rows[2].meta, 'Seats full: Counselors 3/3');
  assert.equal(rows[5].meta, '2 open · 1 in progress');
});
