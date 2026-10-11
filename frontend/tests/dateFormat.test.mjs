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


// Chromium without Uzbek locale data: weekdays come back in English, months as "M10".
test('Uzbek weekdays are spelled out when the browser has no Uzbek names', () => {
  const RealFormat = Intl.DateTimeFormat;
  Intl.DateTimeFormat = function (_locale, options) {
    return new RealFormat('en-GB', options);
  };
  try {
    setLanguage('uz');
    const monday = new Date(2026, 9, 12);
    assert.equal(formatDateLocale(monday, { weekday: 'short' }), 'Dush');
    assert.equal(formatDateLocale(monday, { weekday: 'narrow' }), 'D');
    assert.equal(formatDateLocale(monday, { weekday: 'long', day: 'numeric', month: 'long' }), 'dushanba, 12-oktabr');
    assert.equal(formatDateLocale(new Date(2026, 9, 11), { weekday: 'long' }), 'yakshanba');
  } finally {
    Intl.DateTimeFormat = RealFormat;
  }
});

test('Uzbek and Russian weekdays use the browser names when it has them', () => {
  const monday = new Date(2026, 9, 12);
  setLanguage('uz');
  assert.equal(formatDateLocale(monday, { weekday: 'long', day: 'numeric', month: 'long' }), 'dushanba, 12-oktabr');
  setLanguage('ru');
  assert.equal(formatDateLocale(monday, { weekday: 'short' }), 'пн');
  setLanguage('en');
});
