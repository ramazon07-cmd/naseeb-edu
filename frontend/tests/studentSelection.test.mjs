import test from 'node:test';
import assert from 'node:assert/strict';
import {
  BULK_TASK_LIMIT, canSelectAllMatching, collectMatchingIds, pageSelectionState, togglePageSelection,
} from '../src/lib/studentSelection.js';

const ids = (n, from = 1) => Array.from({ length: n }, (_, i) => from + i);
const rows = (n, from = 1) => ids(n, from).map((id) => ({ id }));

test('the header box is none, some or all of the listed students', () => {
  assert.equal(pageSelectionState([], new Set([1])), 'none');
  assert.equal(pageSelectionState([1, 2, 3], new Set()), 'none');
  assert.equal(pageSelectionState([1, 2, 3], new Set([2])), 'some');
  assert.equal(pageSelectionState([1, 2, 3], new Set([1, 2, 3, 9])), 'all');
});

test('ticking selects every listed student and ticking again clears only those', () => {
  const page = [1, 2, 3];
  const ticked = togglePageSelection(new Set([9]), page);
  assert.deepEqual([...ticked].sort((a, b) => a - b), [1, 2, 3, 9]);
  const cleared = togglePageSelection(ticked, page);
  assert.deepEqual([...cleared], [9]);
});

test('with only some ticked, the box ticks the rest instead of clearing', () => {
  const next = togglePageSelection(new Set([2]), [1, 2, 3]);
  assert.deepEqual([...next].sort(), [1, 2, 3]);
});

test('the input set is never changed', () => {
  const before = new Set([1]);
  togglePageSelection(before, [1, 2]);
  assert.deepEqual([...before], [1]);
});

test('"select all N" is offered only for a fully ticked page with more matches that fit one assignment', () => {
  const pageIds = ids(25);
  const all = new Set(pageIds);
  assert.equal(canSelectAllMatching({ total: 46, pageIds, selected: all }), true);
  assert.equal(canSelectAllMatching({ total: 25, pageIds, selected: all }), false);
  assert.equal(canSelectAllMatching({ total: 46, pageIds, selected: new Set(ids(10)) }), false);
  assert.equal(canSelectAllMatching({ total: BULK_TASK_LIMIT + 1, pageIds, selected: all }), false);
  assert.equal(canSelectAllMatching({ total: BULK_TASK_LIMIT, pageIds, selected: all }), true);
  assert.equal(canSelectAllMatching({ total: 46, pageIds, selected: new Set(ids(46)) }), false);
  assert.equal(canSelectAllMatching({ total: 5, pageIds: [], selected: new Set() }), false);
});

test('every matching id is collected page by page, in order, one request at a time', async () => {
  const calls = [];
  let running = 0;
  let peak = 0;
  const fetchPage = async (page) => {
    running += 1;
    peak = Math.max(peak, running);
    calls.push(page);
    await new Promise((resolve) => setTimeout(resolve, 1));
    running -= 1;
    return { results: rows(page < 3 ? 100 : 46, (page - 1) * 100 + 1) };
  };
  const result = await collectMatchingIds(fetchPage, { total: 246 });
  assert.deepEqual(calls, [1, 2, 3]);
  assert.equal(peak, 1);
  assert.equal(result.length, 246);
  assert.equal(result[0], 1);
  assert.equal(result[245], 246);
});

test('collecting never goes past the bulk limit', async () => {
  const fetchPage = async (page) => ({ results: rows(100, (page - 1) * 100 + 1) });
  const result = await collectMatchingIds(fetchPage, { total: 900 });
  assert.equal(result.length, BULK_TASK_LIMIT);
});

test('a failed page rejects, and a caller that moved on gets null', async () => {
  await assert.rejects(collectMatchingIds(async () => { throw new Error('offline'); }, { total: 50 }), /offline/);
  const result = await collectMatchingIds(async () => ({ results: [{ id: 1 }] }), { total: 50, aborted: () => true });
  assert.equal(result, null);
});
