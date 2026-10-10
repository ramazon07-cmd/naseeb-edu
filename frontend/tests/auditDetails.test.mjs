import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { TRANSLATIONS } = await import('../src/i18n.js');
const { AUDIT_ACTIONS, AUDIT_GROUPS } = await import('../src/lib/labels.js');
const { auditDetailLines } = await import('../src/lib/auditDetails.js');

test('metadata reads as labelled lines, with changes and school names', () => {
  const lines = auditDetailLines({
    metadata: {
      reason: 'Login problem', status: { from: 'open', to: 'in_progress' },
      changes: { contact_phone: { from: '', to: '+998' }, is_active: { from: true, to: false } },
      from_school: 3, to_school: 9, staff_tier: 'support',
    },
    school_names: { 3: 'School Three' },
  });
  assert.deepEqual(lines.map(({ label, value }) => [label, value]), [
    ['Reason', 'Login problem'],
    ['Status', 'Open → In progress'],
    ['Contact phone', '— → +998'],
    ['Active', 'Yes → No'],
    ['From school', 'School Three'],
    ['To school', '#9'],
    ['Staff tier', 'Support'],
  ]);
  const plan = auditDetailLines({ metadata: { changes: { status: { from: 'active', to: 'suspended' } } } });
  assert.deepEqual(plan.map(({ label, value }) => [label, value]), [['Status', 'Active → Suspended']]);
  assert.deepEqual(auditDetailLines({ metadata: null }), []);
  assert.deepEqual(auditDetailLines({}), []);
});

test('old and new change shapes all read as from → to', () => {
  const rows = (event) => auditDetailLines(event).map(({ label, value }) => [label, value]);
  assert.deepEqual(rows({ metadata: { changes: { city: ['Toronto', 'Ottawa'], is_active: [true, false] } } }), [
    ['City', 'Toronto → Ottawa'],
    ['Active', 'Yes → No'],
  ]);
  assert.deepEqual(rows({ metadata: { changes: { city: { from: 'Toronto', to: 'Ottawa' }, qs_data: { changed_keys: ['rank', 'region'] } } } }), [
    ['City', 'Toronto → Ottawa'],
    ['Qs data', 'Changed: rank, region'],
  ]);
  assert.deepEqual(rows({ action: 'staff.tier_changed', metadata: { from: 'support', to: 'ops' } }), [['Staff tier', 'Support → Operations']]);
  assert.deepEqual(rows({ action: 'staff.tier_changed', metadata: { changes: { admin_tier: { from: 'support', to: 'ops' } } } }), [['Staff tier', 'Support → Operations']]);
});

// Every action code the backend writes (literal, conditional or Django-admin
// mixin) needs a label, so uz/ru readers never see a raw code.
function backendFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === 'migrations' || name === '__pycache__' ? [] : backendFiles(path);
    return name.endsWith('.py') && !name.startsWith('test') ? [path] : [];
  });
}

test('every audit action the backend writes has a label and a group', () => {
  const apps = fileURLToPath(new URL('../../backend/apps/', import.meta.url));
  const codes = new Set();
  for (const file of backendFiles(apps)) {
    const source = readFileSync(file, 'utf8');
    for (const line of source.split('\n').filter((text) => /audit|action/.test(text))) {
      for (const [, code] of line.matchAll(/['"]([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)['"]/g)) codes.add(code);
    }
    const prefix = source.match(/audit_prefix = '([a-z_]+)'/g) || [];
    for (const match of prefix) {
      const name = match.match(/'([a-z_]+)'/)[1];
      const update = name === 'subscription' ? 'changed' : 'updated';
      for (const verb of ['created', update, 'deleted']) codes.add(`${name}.${verb}`);
    }
  }
  for (const decision of ['approve', 'request_changes']) codes.add(`counselor_roadmap_mission.${decision}`);
  // Module paths and Django labels picked up by the scan are not audit actions.
  const ignored = /^(apps|core|users|admissions|django|rest_framework)\./;
  const actions = [...codes].filter((code) => !ignored.test(code));
  assert.ok(actions.length > 40, `found only ${actions.length} codes`);
  for (const code of actions) {
    assert.ok(AUDIT_ACTIONS[code], `no label for ${code}`);
    assert.ok(AUDIT_GROUPS[code.split('.')[0]], `no group for ${code}`);
  }
});

test('audit labels and groups have Uzbek and Russian text', () => {
  for (const text of [...Object.values(AUDIT_ACTIONS), ...Object.values(AUDIT_GROUPS)]) {
    for (const language of ['uz', 'ru']) assert.ok(TRANSLATIONS[language][text], `${language}: ${text}`);
  }
});
