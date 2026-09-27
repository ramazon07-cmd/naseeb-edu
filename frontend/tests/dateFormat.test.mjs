import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { formatDateLocale, parseDateValue, setLanguage } = await import('../src/i18n.js');

// Run with TZ west of UTC (e.g. TZ=America/Los_Angeles) to see the old off-by-one.
test('a calendar date is shown on its own day in every time zone', () => {
  setLanguage('en');
  assert.match(formatDateLocale('2026-09-25'), /^25\b/);
  const date = parseDateValue('2026-09-25');
  assert.deepEqual([date.getFullYear(), date.getMonth(), date.getDate()], [2026, 8, 25]);
  assert.equal(parseDateValue('2026-09-25T10:00:00Z').toISOString(), '2026-09-25T10:00:00.000Z');
});

