import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { apiOrigin, buildCsp, inlineScriptHashes, renderNginxConf, storageOrigins } from '../scripts/render-nginx-conf.mjs';

const root = new URL('../', import.meta.url);
const template = readFileSync(new URL('nginx.conf', root), 'utf8');
const headers = readFileSync(new URL('nginx-security-headers.conf', root), 'utf8');
const html = readFileSync(new URL('index.html', root), 'utf8');

test('every inline script in index.html is allowed by hash and nothing else inline', () => {
  const hashes = inlineScriptHashes(html);
  const inlineCount = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].length;
  assert.equal(hashes.length, inlineCount);
  const csp = buildCsp(html, 'https://api.naseebedu.com/api');
  for (const hash of hashes) assert.ok(csp.includes(hash));
  assert.ok(!/script-src[^;]*unsafe-inline/.test(csp));
});

test('the CSP allows the API origin, Google Docs, Telegram posts and blob previews', () => {
  const csp = buildCsp(html, 'https://api.naseebedu.com/api');
  assert.match(csp, /connect-src 'self' https:\/\/api\.naseebedu\.com;/);
  assert.match(csp, /frame-src https:\/\/docs\.google\.com blob:/);
  assert.match(csp, /frame-ancestors 'none'/);
  assert.match(csp, /object-src 'none'/);
  assert.equal(apiOrigin('/api'), '');
  assert.equal(apiOrigin('http://127.0.0.1:8000/api'), 'http://127.0.0.1:8000');
});

test('rendered config: gzip, immutable only for hashed assets, no-cache app shell, headers everywhere', () => {
  const conf = renderNginxConf(template, html, 'https://api.naseebedu.com/api');
  assert.ok(!conf.includes('__CSP__'));
  assert.match(conf, /gzip on;/);
  const immutable = [...conf.matchAll(/^\s*location (?:\^~ )?([^{\n]+)\{[^}]*immutable/gm)].map((m) => m[1].trim());
  assert.deepEqual(immutable, ['/assets/']);
  assert.match(conf, /location = \/index\.html \{[^}]*no-cache/);
  const locations = conf.match(/^\s*location [^{\n]+\{[^}]*\}/gm);
  for (const block of locations) assert.ok(block.includes('security-headers.conf'), block);
  for (const header of ['Content-Security-Policy', 'X-Frame-Options', 'X-Content-Type-Options', 'Referrer-Policy', 'Strict-Transport-Security']) {
    assert.ok(headers.includes(header), header);
  }
});

test('private-file bucket origins join connect-src only; bad values fail the build', () => {
  const origins = storageOrigins('https://files.acct.r2.cloudflarestorage.com, https://naseeb.s3.eu-central-1.amazonaws.com/');
  assert.deepEqual(origins, ['https://files.acct.r2.cloudflarestorage.com', 'https://naseeb.s3.eu-central-1.amazonaws.com']);
  const csp = buildCsp(html, 'https://api.naseebedu.com/api', origins);
  assert.match(csp, /connect-src 'self' https:\/\/api\.naseebedu\.com https:\/\/files\.acct\.r2\.cloudflarestorage\.com https:\/\/naseeb\.s3\.eu-central-1\.amazonaws\.com;/);
  assert.match(csp, /img-src 'self' data: blob:;/);
  assert.match(csp, /frame-src https:\/\/docs\.google\.com blob: https:\/\/t\.me;/);
  assert.deepEqual(storageOrigins(''), []);
  assert.deepEqual(storageOrigins(undefined), []);
  for (const bad of ['files.example.com', 'https://files.example.com/private/', "https://x.com; script-src *", 'javascript:alert(1)']) {
    assert.throws(() => storageOrigins(bad), /FILE_STORAGE_ORIGINS/, bad);
  }
  assert.ok(renderNginxConf(template, html, '/api', origins).includes('https://files.acct.r2.cloudflarestorage.com'));
});

test('client routes fall back to the app shell and never collide with static files', async () => {
  const { PAGE_PATHS, LOGIN_PATH, buildPath } = await import('../src/lib/routes.js');
  const conf = renderNginxConf(template, html, '/api');
  const fallback = conf.match(/location \/ \{[^}]*\}/);
  assert.ok(fallback, 'catch-all location');
  assert.match(fallback[0], /try_files \$uri \/index\.html;/);
  assert.match(conf, /location = \/index\.html \{[^}]*no-cache/);
  const staticPattern = conf.match(/location ~\* (\S+) \{/)[1];
  const staticFiles = new RegExp(staticPattern, 'i');
  const publicEntries = new Set(readdirSync(new URL('public/', root)));
  const routes = [...Object.values(PAGE_PATHS), LOGIN_PATH,
    buildPath({ page: 'essay_lab', params: { essayId: 42 } }), buildPath({ page: 'students', params: { studentId: 15 } }),
    buildPath({ page: 'student_center', params: { tab: 'documents' } })];
  for (const route of routes) {
    assert.ok(!route.startsWith('/assets/'), route);
    assert.ok(!staticFiles.test(route), `${route} would be served as a static file`);
    assert.ok(!publicEntries.has(route.split('/')[1]), `${route} shares a name with public/`);
  }
});

test('docker-compose serves the API from the app origin; the production image proxies nothing', () => {
  const conf = renderNginxConf(template, html, '/api');
  assert.match(conf, /include \/etc\/nginx\/snippets\/api-proxy\*\.conf;/, 'optional glob include');
  const proxy = readFileSync(new URL('nginx-api-proxy.compose.conf', root), 'utf8');
  // ^~ so the static-file regex location never takes an /api/...json request.
  assert.match(proxy, /location \^~ \/api\/ \{/);
  assert.match(proxy, /proxy_pass http:\/\/backend:8000;/);
  assert.match(proxy, /proxy_set_header Host \$http_host;/);
  const compose = readFileSync(new URL('../docker-compose.yml', root), 'utf8');
  assert.match(compose, /VITE_API_URL: \/api/);
  assert.match(compose, /nginx-api-proxy\.compose\.conf:\/etc\/nginx\/snippets\/api-proxy\.conf/);
});
