import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { APP_VERSION } from '../src/lib/appVersion.js';

test('VERSION is a single 4-part version line', () => {
  const text = readFileSync(new URL('../VERSION', import.meta.url), 'utf8');
  assert.match(text, /^\d+\.\d+\.\d+\.\d+\n?$/);
});

test('appVersion falls back outside a Vite build', () => {
  assert.equal(APP_VERSION, '0.0.0.0');
});
