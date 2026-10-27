import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
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

test('Counselor Roadmap waits for its roadmaps and reports a failed load instead of an empty list (card 23)', () => {
  const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
  assert.match(app, /counselor_roadmap: \['counselorRoadmaps', 'counselorRoadmapTemplates'\]/);
  const keys = ['counselorRoadmaps', 'counselorRoadmapTemplates'];
  const data = { counselorRoadmaps: [], counselorRoadmapTemplates: [] };
  const loading = pageLoadState({ keys, data, stats: null, loading: true, resourceStatus: { counselorRoadmaps: { status: 'loading', error: '' } } });
  assert.equal(loading.initialLoading, true);
  const failed = pageLoadState({ keys, data, stats: null, loading: false, resourceStatus: { counselorRoadmaps: { status: 'error', error: 'Network error' }, counselorRoadmapTemplates: { status: 'success', error: '' } } });
  assert.deepEqual(failed.failedKeys, ['counselorRoadmaps']);
});

test('parent portal: a failed first load blocks the page, a reload keeps it visible (card 48)', () => {
  const keys = ['parentPortal'];
  const data = { parentPortal: { children: [], pending_invitations: [] } };
  const failed = pageLoadState({ keys, data, stats: null, loading: false, primaryKeys: keys, resourceStatus: { parentPortal: { status: 'error', error: 'Server error', loaded: false } } });
  assert.equal(failed.contentBlocked, true);
  const reloading = pageLoadState({ keys, data, stats: null, loading: true, primaryKeys: keys, resourceStatus: { parentPortal: { status: 'loading', error: '', loaded: true } } });
  assert.equal(reloading.hasVisibleData, true);
  assert.equal(reloading.initialLoading, false);
  const first = pageLoadState({ keys, data, stats: null, loading: true, primaryKeys: keys, resourceStatus: { parentPortal: { status: 'loading', error: '', loaded: false } } });
  assert.equal(first.initialLoading, true);
});

test('progressive dashboard opens after its profile while widgets keep loading', () => {
  const base = {
    keys: ['students', 'tasks', 'bookings'], primaryKeys: ['students'],
    data: { students: [{ id: 1 }], tasks: [], bookings: [] },
    stats: null, loading: true, lazy: true, progressive: true,
  };
  const resourceStatus = {
    students: { status: 'success', loaded: true },
    tasks: { status: 'loading', loaded: false },
    bookings: { status: 'loading', loaded: false },
  };
  assert.equal(pageLoadState({ ...base, resourceStatus }).initialLoading, false);
  assert.equal(pageLoadState({ ...base, resourceStatus, progressive: false }).initialLoading, true);
  assert.equal(pageLoadState({ ...base, resourceStatus: { ...resourceStatus, students: { status: 'loading', loaded: false } } }).initialLoading, true);
  const failed = pageLoadState({ ...base, resourceStatus: { ...resourceStatus, students: { status: 'error', loaded: false } } });
  assert.equal(failed.contentBlocked, true);
  assert.deepEqual(failed.failedKeys, ['students']);
});
