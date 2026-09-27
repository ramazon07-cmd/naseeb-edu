import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CHALLENGES } from '../src/challenges.js';

const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');

test('the navigation challenge count matches the question banks it no longer imports', () => {
  const count = Number(app.match(/ASSESSMENT_CHALLENGE_COUNT = (\d+)/)[1]);
  assert.equal(count, CHALLENGES.length);
});

test('heavy and role-specific modules stay out of the main bundle', () => {
  for (const module of ['./challenges', './careers', './LandingPage', './StudentOnboarding', './pages/ProfileAssessmentPage']) {
    const escaped = module.replace(/[./]/g, (c) => `\\${c}`);
    assert.ok(!new RegExp(`^import[^;]*from\\s*['"]${escaped}['"]`, 'm').test(app), `${module} must be imported lazily`);
  }
  assert.match(app, /lazy(?:WithRetry)?\(\(\) => import\('\.\/LandingPage'\)\)/);
  assert.match(app, /lazy(?:WithRetry)?\(\(\) => import\('\.\/pages\/ProfileAssessmentPage'\)\)/);
});
