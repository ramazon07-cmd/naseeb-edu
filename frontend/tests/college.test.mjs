import test from 'node:test';
import assert from 'node:assert/strict';
import { BAND_TIERS, afterAidText, priceInfo } from '../src/lib/college.js';
import { money } from '../src/lib/format.js';

test('an unknown admission band maps to no tier, never "target"', () => {
  assert.deepEqual(BAND_TIERS, { reach: 'dream', target: 'target', safety: 'safety' });
  assert.equal(BAND_TIERS[null], undefined);
  assert.equal(BAND_TIERS[undefined], undefined);
});

test('a US university is priced at its international cost, with the net price only after international aid', () => {
  const mit = { market: 'us', country: 'United States', intl_cost_usd: 85960, net_price_usd: 20111, offers_international_aid: true };
  assert.deepEqual(priceInfo(mit), { label: 'Estimated cost for international students', amount: 85960, afterAid: 20111, cost: 20111 });
  assert.equal(afterAidText(20111), `${money(20111)} after aid`);
  assert.deepEqual(priceInfo({ ...mit, offers_international_aid: false }), { label: 'Estimated cost for international students', amount: 85960, afterAid: null, cost: 85960 });
  assert.deepEqual(priceInfo({ ...mit, intl_cost_usd: null, offers_international_aid: false }).amount, null);
});

test('a university outside the US keeps its net price', () => {
  assert.deepEqual(priceInfo({ market: 'canada', intl_cost_usd: null, net_price_usd: 30000, offers_international_aid: true }), { label: 'Net price', amount: 30000, afterAid: null, cost: 30000 });
});
