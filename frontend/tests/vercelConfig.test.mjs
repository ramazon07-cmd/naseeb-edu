import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'));

// Vercel serves real files (assets, robots.txt, sitemap.xml) before rewrites,
// so one catch-all is enough for deep links and reloads of app routes.
test('every app route falls back to the single-page app on Vercel', () => {
  const matches = (path) => (config.rewrites || []).some(({ source, destination }) => (
    destination === '/index.html' && new RegExp(`^${source.replace('(.*)', '.*')}$`).test(path)
  ));
  for (const path of ['/login', '/dashboard', '/essay-lab', '/essay-lab/essays/42', '/student-center/documents', '/platform/students/15']) {
    assert.ok(matches(path), path);
  }
});
