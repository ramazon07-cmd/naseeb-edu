import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { setLanguage } = await import('../src/i18n.js');
const { inServerZone, serverDateKey, serverRelativeDayText } = await import('../src/lib/serverTime.js');

// 2026-10-10 20:30 UTC is already 01:30 on 11 October in Tashkent (UTC+5).
const LATE_EVENING_UTC = '2026-10-10T20:30:00Z';

test('timestamps take the Tashkent day and hour, whatever the browser zone', () => {
  const shifted = inServerZone(LATE_EVENING_UTC);
  assert.deepEqual([shifted.getFullYear(), shifted.getMonth(), shifted.getDate(), shifted.getHours(), shifted.getMinutes()], [2026, 9, 11, 1, 30]);
  assert.equal(serverDateKey(LATE_EVENING_UTC), '2026-10-11');
  assert.equal(serverDateKey('2026-10-10T18:59:59Z'), '2026-10-10');
});

test('calendar dates and empty values pass through', () => {
  assert.equal(inServerZone('2026-10-11'), '2026-10-11');
  assert.equal(serverDateKey('2026-10-11'), '2026-10-11');
  assert.equal(inServerZone(null), null);
  assert.equal(inServerZone('not a date'), 'not a date');
});

test('relative days count from Tashkent today', () => {
  setLanguage('en');
  const now = new Date('2026-10-11T03:00:00Z'); // 08:00 in Tashkent
  assert.equal(serverRelativeDayText(LATE_EVENING_UTC, now), 'Today', 'the same Tashkent day, though the UTC date differs');
  assert.equal(serverRelativeDayText('2026-10-10T10:00:00Z', now), 'Yesterday');
  assert.equal(serverRelativeDayText('2026-10-08T10:00:00Z', now), '3 days ago');
  assert.equal(serverRelativeDayText('', now), '');
});
