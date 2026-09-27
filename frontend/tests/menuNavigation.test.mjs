import test from 'node:test';
import assert from 'node:assert/strict';
import { nextMenuIndex } from '../src/lib/menuNavigation.js';

test('arrow keys wrap around the Add menu', () => {
  assert.equal(nextMenuIndex('ArrowDown', 0, 4), 1);
  assert.equal(nextMenuIndex('ArrowDown', 3, 4), 0);
  assert.equal(nextMenuIndex('ArrowUp', 0, 4), 3);
  assert.equal(nextMenuIndex('ArrowUp', -1, 4), 3);
  assert.equal(nextMenuIndex('Home', 2, 4), 0);
  assert.equal(nextMenuIndex('End', 0, 4), 3);
});

test('other keys and empty menus do not move focus', () => {
  assert.equal(nextMenuIndex('Enter', 1, 4), null);
  assert.equal(nextMenuIndex('ArrowDown', 0, 0), null);
});
