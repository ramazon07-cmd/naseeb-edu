import test from 'node:test';
import assert from 'node:assert/strict';
import { pageLoadState } from '../src/lib/pageLoadState.js';

const empty = { students: [], tasks: [] };

test('sign-in shows the skeleton until the first workspace load settles', () => {
  const state = pageLoadState({ keys: ['students'], data: empty, stats: null, loading: true, resourceStatus: {} });
  assert.equal(state.initialLoading, true);
});

test('a server-paged page stays mounted while the workspace refreshes after a save', () => {
  // Staff never load `students` into the workspace; only stats refresh.
  const state = pageLoadState({
    keys: ['students'], data: empty, stats: { students_total: 5000 }, loading: true,
    resourceStatus: { dashboard: { status: 'loading', error: '' }, bookings: { status: 'success', error: '' } },
  });
  assert.equal(state.initialLoading, false);
});

test('a page waits for its own in-memory collection on first load', () => {
  const state = pageLoadState({ keys: ['tasks'], data: empty, stats: null, loading: true, resourceStatus: { tasks: { status: 'loading', error: '' } } });
  assert.equal(state.initialLoading, true);
  const loaded = pageLoadState({ keys: ['tasks'], data: { tasks: [{ id: 1 }] }, stats: null, loading: true, resourceStatus: { tasks: { status: 'loading', error: '' } } });
  assert.equal(loaded.initialLoading, false);
  assert.deepEqual(loaded.loadingKeys, ['tasks']);
});

test('failed collections are reported', () => {
  const state = pageLoadState({ keys: ['tasks'], data: empty, stats: null, loading: false, resourceStatus: { tasks: { status: 'error', error: 'x' } } });
  assert.deepEqual(state.failedKeys, ['tasks']);
});
