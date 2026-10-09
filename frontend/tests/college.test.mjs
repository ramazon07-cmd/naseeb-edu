import test from 'node:test';
import assert from 'node:assert/strict';
import { BAND_TIERS, DEFAULT_COLLEGE_FILTERS, afterAidText, collegeFilterChips, priceFilterNotes, priceInfo, tierPickerState } from '../src/lib/college.js';
import { money } from '../src/lib/format.js';

test('an unknown admission band maps to no tier, never "target"', () => {
  assert.deepEqual(BAND_TIERS, { reach: 'dream', target: 'target', safety: 'safety' });
  assert.equal(BAND_TIERS[null], undefined);
  assert.equal(BAND_TIERS[undefined], undefined);
});

test('a US university shows the cost the server sends, with US students\' after-aid average only as a second line', () => {
  const mit = { market: 'us', cost: 85960, cost_label: 'international_cost', after_aid_usd: null, net_price_usd: 20111 };
  assert.deepEqual(priceInfo(mit), { label: 'Estimated cost for international students', international: true, amount: 85960, afterAid: null, cost: 85960 });
  const princeton = { market: 'us', cost: 86000, cost_label: 'international_cost', after_aid_usd: 6128, net_price_usd: 6128 };
  assert.deepEqual(priceInfo(princeton), { label: 'Estimated cost for international students', international: true, amount: 86000, afterAid: 6128, cost: 86000 });
  assert.equal(afterAidText(6128), `${money(6128)}: US students' average after aid; international aid varies`);
  assert.equal(priceInfo({ market: 'us', cost: null, cost_label: 'international_cost', after_aid_usd: null }).amount, null);
});

test('a university outside the US shows its net price', () => {
  assert.deepEqual(priceInfo({ market: 'canada', cost: 30000, cost_label: 'net_price', after_aid_usd: null }), { label: 'Net price', international: false, amount: 30000, afterAid: null, cost: 30000 });
});

test('the tier picker waits for the research profile before asking to complete it', () => {
  assert.equal(tierPickerState({ research: null, loading: true, error: '' }), 'loading');
  assert.equal(tierPickerState({ research: { ready: true }, loading: true, error: '' }), 'loading');
  assert.equal(tierPickerState({ research: null, loading: false, error: 'Network down' }), 'error');
  assert.equal(tierPickerState({ research: { ready: false }, loading: false, error: '' }), 'incomplete');
  assert.equal(tierPickerState({ research: { ready: true }, loading: false, error: '' }), 'no_data');
});

test('"Within budget" without a budget asks for one instead of showing $0', () => {
  assert.deepEqual(priceFilterNotes('budget', 0, 0), { budgetMissing: true, unpriced: '' });
  assert.deepEqual(priceFilterNotes('budget', null, 0).budgetMissing, true);
  assert.deepEqual(priceFilterNotes('budget', 30000, 0).budgetMissing, false);
  assert.deepEqual(priceFilterNotes('25000', 0, 0).budgetMissing, false);
  const [chip] = collegeFilterChips({ ...DEFAULT_COLLEGE_FILTERS, price: 'budget' }, () => {}, 0);
  assert.equal(chip.text, 'Within budget');
});

test('a price filter tells how many universities have no published price', () => {
  assert.equal(priceFilterNotes('40000', 30000, 3).unpriced, '3 universities have no published price');
  assert.equal(priceFilterNotes('budget', 30000, 1).unpriced, '1 university has no published price');
  assert.equal(priceFilterNotes('40000', 30000, 0).unpriced, '');
  assert.equal(priceFilterNotes('all', 30000, 3).unpriced, '');
});
