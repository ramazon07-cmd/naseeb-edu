import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { aiCostLine, aiFeatureLabel, aiTokenLine, aiUsageRows } = await import('../src/lib/aiUsage.js');

const usage = (used = 1) => ({ used, limit: 10, school_limit: null, user_limit: null, refused: 0, top_schools: [] });
const FIVE = ['assistant', 'essay_coach', 'recommendation_letter', 'education_match', 'telegram_import'];

test('every feature the backend reports gets a row, in backend order', () => {
  const features = Object.fromEntries(FIVE.map((key) => [key, usage()]));
  const rows = aiUsageRows({ feature_names: FIVE, features });
  assert.deepEqual(rows.map((row) => row.key), FIVE);
  assert.equal(rows[3].title, 'Major explanations');
});

test('a brand-new backend feature shows up with a readable fallback label and no frontend change', () => {
  const rows = aiUsageRows({ feature_names: ['assistant', 'future_thing'], features: { assistant: usage(), future_thing: usage() } });
  assert.deepEqual(rows.map((row) => row.title), ['AI assistant', 'Future thing']);
  assert.equal(aiFeatureLabel('x'), 'X');
});

test('a listed feature with no numbers is skipped instead of crashing', () => {
  const rows = aiUsageRows({ feature_names: FIVE, features: { assistant: usage() } });
  assert.deepEqual(rows.map((row) => row.key), ['assistant']);
  assert.deepEqual(aiUsageRows(null), []);
  assert.deepEqual(aiUsageRows({ features: null, today_from_log: null }), []);
});

test('with the cache down the rows come from the usage log', () => {
  const rows = aiUsageRows({ feature_names: ['assistant'], features: null, today_from_log: { assistant: { used: 3, top_schools: [] } } });
  assert.equal(rows[0].usage, null);
  assert.equal(rows[0].log.used, 3);
});

test('token line shows paid calls, estimated and refunded counts; empty when nothing happened', () => {
  const line = aiTokenLine({ paid_calls: 12, total_tokens: { sum: 3400 }, error_rate: 0.25, estimated_calls: 2, refunded_calls: 1 });
  assert.match(line, /12 paid calls/);
  assert.match(line, /3,400 tokens/);
  assert.match(line, /2 calls with estimated tokens/);
  assert.match(line, /1 refunded call/);
  assert.equal(aiTokenLine({ paid_calls: 0, refunded_calls: 0 }), '');
  assert.equal(aiTokenLine(null), '');
});

test('cost line appears only with an estimate and says it assumes one price', () => {
  assert.equal(aiCostLine(null), '');
  assert.match(aiCostLine({ total_usd: 2.1 }, 30), /\$2\.10.*one price for every model/);
});
