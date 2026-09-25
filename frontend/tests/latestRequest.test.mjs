import test from 'node:test';
import assert from 'node:assert/strict';
import { createLatestRequest } from '../src/lib/latestRequest.js';

const later = (value, ms) => new Promise((resolve) => setTimeout(() => resolve(value), ms));

test('a slow response for an earlier student cannot overwrite the current one (M9)', async () => {
  const latest = createLatestRequest();
  let shown = null;
  async function open(id, ms) {
    const isCurrent = latest.start();
    const result = await later(`visibility for ${id}`, ms);
    if (isCurrent()) shown = result;
  }
  await Promise.all([open('A', 30), open('B', 5)]);
  assert.equal(shown, 'visibility for B');
});

test('cancel drops a response that arrives after the view was closed', async () => {
  const latest = createLatestRequest();
  const isCurrent = latest.start();
  latest.cancel();
  assert.equal(isCurrent(), false);
  assert.equal(latest.start()(), true);
});
