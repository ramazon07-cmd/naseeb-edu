import test from 'node:test';
import assert from 'node:assert/strict';
import { USER_SESSION_STORAGE, USER_STORAGE, clearUserSessionStorage, clearUserStorage, dropLegacySharedKeys, userStorageKey } from '../src/userStorage.js';

function memoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return { getItem: (k) => (map.has(k) ? map.get(k) : null), setItem: (k, v) => map.set(k, String(v)), removeItem: (k) => map.delete(k), map };
}

test('keys are scoped per user and refuse a missing id', () => {
  assert.equal(userStorageKey(USER_STORAGE.assessment, 7), 'naseeb-find-personality-v1:7');
  assert.notEqual(userStorageKey(USER_STORAGE.screenTime, 7), userStorageKey(USER_STORAGE.screenTime, 8));
  assert.throws(() => userStorageKey(USER_STORAGE.assessment, undefined));
  assert.throws(() => userStorageKey(USER_STORAGE.assessment, null));
});

test('sign-out clears only the signed-out user and keeps unrelated preferences', () => {
  const storage = memoryStorage({
    [userStorageKey(USER_STORAGE.assessment, 1)]: '{"q1":3}',
    [userStorageKey(USER_STORAGE.screenTime, 1)]: '[]',
    [userStorageKey(USER_STORAGE.parentChild, 1)]: '4',
    [userStorageKey(USER_STORAGE.assessment, 2)]: '{"q1":5}',
    'naseeb-edu-theme': 'dark',
  });
  clearUserStorage(storage, 1);
  assert.deepEqual([...storage.map.keys()].sort(), ['naseeb-edu-theme', 'naseeb-find-personality-v1:2']);
});

test('legacy shared keys are dropped and broken storage is tolerated', () => {
  const storage = memoryStorage({ 'naseeb-find-personality-v1': '{}', 'naseeb-screen-time-pending-v1': '[]', 'naseeb-find-personality-v1:3': '{}' });
  dropLegacySharedKeys(storage);
  assert.deepEqual([...storage.map.keys()], ['naseeb-find-personality-v1:3']);
  assert.doesNotThrow(() => dropLegacySharedKeys(() => { throw new Error('SecurityError'); }));
  assert.doesNotThrow(() => clearUserStorage(() => { throw new Error('SecurityError'); }, 1));
});

test('the open Essay Lab essay is per user and cleared on sign-out', () => {
  const storage = memoryStorage({
    [userStorageKey(USER_SESSION_STORAGE.essayLabOpen, 1)]: '{"id":5}',
    [userStorageKey(USER_SESSION_STORAGE.essayLabOpen, 2)]: '{"id":6}',
    [USER_SESSION_STORAGE.essayLabOpen]: '{"id":7}',
  });
  clearUserSessionStorage(storage, 1);
  assert.deepEqual([...storage.map.keys()], [userStorageKey(USER_SESSION_STORAGE.essayLabOpen, 2)]);
});
