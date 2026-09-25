import test from 'node:test';
import assert from 'node:assert/strict';
import { UNTRACKED_ENDPOINTS, createMutationTracker, endpointOf, planReload } from '../src/lib/reloadPlan.js';
import { createKeyedLatest } from '../src/lib/latestRequest.js';

const RESOURCES = [['students', 'students'], ['tasks', 'tasks'], ['roadmapMissions', 'roadmap-missions'], ['accounts', 'users/accounts'], ['messageChannels', 'message-channels']];

test('endpoints are taken from the first path segment', () => {
  assert.equal(endpointOf('/tasks/12/approve/'), 'tasks');
  assert.equal(endpointOf('/roadmap-missions/extend-level-one/?x=1'), 'roadmap-missions');
  assert.equal(endpointOf('/users/accounts/5/deactivate/'), 'users/accounts');
});

test('a save reloads only the written resources plus derived keys (M4)', () => {
  const tracker = createMutationTracker();
  tracker.note('/tasks/12/approve/');
  tracker.note('/tasks/');
  assert.deepEqual(planReload(tracker.take(), RESOURCES, ['dashboard', 'students']).sort(), ['dashboard', 'students', 'tasks']);
  assert.deepEqual(tracker.take(), []);
});

test('telemetry writes are not treated as data changes', () => {
  const tracker = createMutationTracker(['screen-time', 'assistant']);
  tracker.note('/screen-time/track/');
  tracker.note('/assistant/chat/');
  assert.deepEqual(tracker.take(), []);
});

test('Essay Lab autosaves and edits never trigger a workspace reload', () => {
  const tracker = createMutationTracker(UNTRACKED_ENDPOINTS);
  tracker.note('/essay-lab/essays/4/autosave/');
  tracker.note('/essay-lab/folders/order/');
  tracker.note('/essay-lab/essays/4/depth-check/');
  assert.deepEqual(tracker.take(), []);
  tracker.note('/essay-lab/essays/4/autosave/');
  tracker.note('/tasks/12/');
  // A later save elsewhere reloads only what it touched, not everything.
  assert.deepEqual(planReload(tracker.take(), RESOURCES, ['dashboard']).sort(), ['dashboard', 'tasks']);
});

test('unknown writes or no recorded write fall back to a full reload', () => {
  assert.equal(planReload([], RESOURCES), null);
  assert.equal(planReload(['assistant'], RESOURCES), null);
});

test('only the newest response per key is applied', () => {
  const latest = createKeyedLatest();
  const first = latest.start(['tasks', 'students']);
  const second = latest.start(['tasks']);
  assert.equal(first('tasks'), false);
  assert.equal(first('students'), true);
  assert.equal(second('tasks'), true);
  latest.cancelAll();
  assert.equal(second('tasks'), false);
  assert.equal(first('students'), false);
});
