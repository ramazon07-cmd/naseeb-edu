import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { setLanguage } = await import('../src/i18n.js');
const { FIT_REASON_TEMPLATES } = await import('../src/translations/fitReasons.js');
const { fitReasonText } = await import('../src/lib/fitReasons.js');

// One server item per code, with the params score_university sends and its English text.
const ITEMS = {
  sat_above_range: [{ score: 1500 }, 'SAT 1500 meets or exceeds the catalog range'],
  sat_in_range: [{ score: 1300, min: 1200, max: 1400 }, 'SAT 1300 fits the 1200–1400 catalog range'],
  sat_near_minimum: [{ points: 50, min: 1200 }, 'SAT is 50 points below the catalog minimum'],
  sat_below_minimum: [{ min: 1200 }, 'Raise SAT toward at least 1200'],
  act_above_range: [{ score: 34 }, 'ACT 34 meets or exceeds the catalog range'],
  act_in_range: [{ score: 31, min: 30, max: 33 }, 'ACT 31 fits the 30–33 catalog range'],
  act_near_minimum: [{ points: 1, min: 30 }, 'ACT is 1 points below the catalog minimum'],
  act_below_minimum: [{ min: 30 }, 'Raise ACT toward at least 30'],
  tests_optional: [{}, 'SAT and ACT are optional at this university'],
  tests_required: [{}, 'This university expects an SAT or ACT score'],
  test_score_missing: [{}, 'Add an SAT or ACT score to compare with admitted students'],
  test_range_missing_for: [{ test: 'ACT' }, 'The ACT range is not listed in the catalog'],
  test_range_missing: [{}, 'SAT and ACT ranges are not listed in the catalog'],
  english_strong: [{ test: 'IELTS', score: 7.5 }, 'IELTS 7.5 is a strong language score'],
  english_suitable: [{ test: 'TOEFL', score: 90 }, 'TOEFL 90 is suitable for many programs'],
  english_check: [{ test: 'PTE', score: 40 }, 'Verify the English test requirement on the official program page'],
  english_missing: [{}, 'Add an English test score (IELTS, TOEFL, Duolingo, PTE or Cambridge)'],
  country_match: [{ country: 'Canada' }, 'Canada is one of your target countries'],
  major_match: [{ major: 'Computer Science' }, 'Computer Science matches an available field of study'],
  major_check: [{}, 'Check the exact program requirements for your selected major'],
  cost_within_budget: [{ cost: 18000, budget: 20000 }, 'Estimated cost of attendance for international students is within your budget'],
  cost_above_budget: [{ cost: 25000, budget: 20000 }, 'Estimated cost of attendance for international students is above your budget'],
  cost_far_above_budget: [{ cost: 85960, budget: 20000 }, 'Estimated cost of attendance for international students is significantly above your budget'],
  cost_missing: [{}, 'Estimated cost of attendance for international students is not available in the catalog'],
  net_after_aid_within_budget: [{ cost: 15000, budget: 20000 }, 'Estimated net price after aid is within your budget'],
  net_after_aid_above_budget: [{ cost: 25000, budget: 20000 }, 'Estimated net price after aid is above your budget'],
  net_after_aid_far_above_budget: [{ cost: 90000, budget: 20000 }, 'Estimated net price after aid is significantly above your budget'],
  aid_available: [{}, 'A suitable type of financial aid is available'],
  aid_not_offered: [{}, 'The catalog lists no international, merit or need-based aid at this university'],
  aid_unknown: [{}, 'Financial aid details are not listed in the catalog'],
};
const item = (code) => ({ code, params: ITEMS[code][0], text: ITEMS[code][1] });

test('every code has an item here and a template in each language', () => {
  assert.deepEqual(Object.keys(ITEMS).sort(), Object.keys(FIT_REASON_TEMPLATES).sort());
  for (const [code, templates] of Object.entries(FIT_REASON_TEMPLATES)) {
    assert.deepEqual(Object.keys(templates).sort(), ['en', 'ru', 'uz'], code);
    const names = (text) => [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
    for (const language of ['uz', 'ru']) assert.deepEqual(names(templates[language]), names(templates.en), `${code} ${language}`);
    for (const name of names(templates.en)) assert.ok(name in ITEMS[code][0], `${code} uses {${name}}`);
  }
});

test('English matches the server text for every code', () => {
  setLanguage('en');
  for (const code of Object.keys(ITEMS)) assert.equal(fitReasonText(item(code)), ITEMS[code][1], code);
});

test('Uzbek and Russian translate every code and fill every param', () => {
  for (const language of ['uz', 'ru']) {
    setLanguage(language);
    for (const code of Object.keys(ITEMS)) {
      const text = fitReasonText(item(code));
      assert.notEqual(text, ITEMS[code][1], `${language} ${code}`);
      assert.doesNotMatch(text, /[{}]|fit_reason\./, `${language} ${code}: ${text}`);
    }
  }
  setLanguage('ru');
  assert.equal(fitReasonText(item('english_strong')), 'IELTS 7,5 — сильный языковой результат');
  assert.equal(fitReasonText(item('sat_in_range')), 'SAT 1300 входит в диапазон каталога 1200–1400');
  setLanguage('uz');
  assert.equal(fitReasonText(item('test_range_missing_for')), 'Katalogda ACT oralig‘i ko‘rsatilmagan');
  setLanguage('en');
});

test('falls back to the server text, then to an old plain-string payload', () => {
  setLanguage('ru');
  assert.equal(fitReasonText({ code: 'brand_new_code', params: {}, text: 'A newer server reason' }), 'A newer server reason');
  assert.equal(fitReasonText('SAT 1450 meets or exceeds the catalog range'), 'SAT 1450 meets or exceeds the catalog range');
  assert.equal(fitReasonText({ code: 'brand_new_code' }), '');
  setLanguage('en');
});
