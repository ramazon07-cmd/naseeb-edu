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

test('/api is never answered with the app shell on Vercel', () => {
  const matches = (path) => (config.rewrites || []).some(({ source }) => new RegExp(`^${source}$`).test(path));
  for (const path of ['/api/auth/token/refresh/', '/api/users/accounts/me/']) assert.ok(!matches(path), path);
  assert.ok(matches('/apiary'), 'only the /api/ prefix is excluded');
});

test('the Vercel middleware proxies /api to NASEEB_API_ORIGIN, path and query kept', async () => {
  const { default: middleware, config: matcher } = await import('../middleware.js');
  assert.deepEqual(matcher, { matcher: '/api/:path*' });
  const request = new Request('https://naseeb-edu-demo.vercel.app/api/auth/token/refresh/?x=1', { method: 'POST' });
  const response = middleware(request, { NASEEB_API_ORIGIN: 'https://naseeb-api.onrender.com/' });
  assert.equal(response.headers.get('x-middleware-rewrite'), 'https://naseeb-api.onrender.com/api/auth/token/refresh/?x=1');
});

test('without NASEEB_API_ORIGIN the middleware fails loudly with JSON, not index.html', async () => {
  const { default: middleware } = await import('../middleware.js');
  for (const env of [{}, { NASEEB_API_ORIGIN: 'naseeb-api.onrender.com' }, { NASEEB_API_ORIGIN: 'https://x.com/api' }]) {
    const response = middleware(new Request('https://app.example/api/users/accounts/me/'), env);
    assert.equal(response.status, 502, JSON.stringify(env));
    assert.equal((await response.json()).code, 'api_proxy_unconfigured');
    assert.equal(response.headers.get('x-middleware-rewrite'), null);
  }
});

test('a Vercel build with a relative API URL and no NASEEB_API_ORIGIN fails', async () => {
  const { checkBuildApiConfig } = await import('../scripts/api-config.mjs');
  assert.throws(() => checkBuildApiConfig({ VERCEL: '1' }), /NASEEB_API_ORIGIN is not set/);
  assert.throws(() => checkBuildApiConfig({ VERCEL: '1', NASEEB_API_ORIGIN: 'https://api.example.com/api' }), /no path/);
  assert.deepEqual(checkBuildApiConfig({ VERCEL: '1', NASEEB_API_ORIGIN: 'https://api.example.com' }),
    { mode: 'vercel-proxy', apiUrl: '/api', upstream: 'https://api.example.com' });
  assert.equal(checkBuildApiConfig({ VERCEL: '1', VITE_API_URL: 'https://api.example.com/api' }).mode, 'direct');
  assert.equal(checkBuildApiConfig({}).mode, 'proxy', 'local builds use the vite/nginx proxy');
});
