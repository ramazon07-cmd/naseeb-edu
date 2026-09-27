import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const landing = readFileSync(new URL('../src/LandingPage.jsx', import.meta.url), 'utf8');
const bootstrap = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function boot({ saved, systemDark = false, storageBlocked = false, lang = 'en', tokens = {}, hash = '', search = '' }) {
  const hero = { removed: false, setAttribute(name, value) { this[name] = value; }, remove() { this.removed = true; } };
  const appended = [];
  const documentElement = { dataset: {}, style: {} };
  runInNewContext(bootstrap, {
    document: {
      documentElement,
      head: { appendChild: (node) => appended.push(node) },
      createElement: () => ({}),
      getElementById: () => ({}),
      querySelector: (selector) => selector === 'link[data-theme-hero]' ? hero : {},
    },
    location: { hash, search },
    URLSearchParams,
    localStorage: { getItem: (key) => {
      if (storageBlocked) throw new Error('Storage unavailable');
      if (key === 'naseeb-edu-theme') return saved;
      if (key === 'naseeb-edu-language-v1') return lang;
      return tokens[key] ?? null;
    } },
    navigator: { language: 'en-US' },
    matchMedia: () => ({ matches: systemDark }),
  });
  if (hero.removed) return { preloaded: false, theme: documentElement.dataset.theme, fonts: appended.map((n) => n.href) };
  return { href: hero.href, srcset: hero.imagesrcset, theme: documentElement.dataset.theme, fonts: appended.map((n) => n.href) };
}

const heroSet = (variant) => [640, 960, 1448].map((w) => `/landing/hero-${variant}-${w}.webp ${w}w`).join(', ');

test('only the hero has an image preload and it matches the active theme', () => {
  const imagePreloads = html.match(/<link\b[^>]*rel="preload"[^>]*as="image"[^>]*>/g);
  assert.equal(imagePreloads.length, 1);
  assert.match(imagePreloads[0], /fetchpriority="high"/);
  const sizes = imagePreloads[0].match(/imagesizes="([^"]+)"/)[1];
  assert.ok(landing.includes(`HERO_SIZES = "${sizes}"`), 'preload sizes must match the JSX sizes');
  assert.ok(landing.includes('const HERO_WIDTHS = [640, 960, 1448]'), 'preload widths must match the JSX srcset');
  for (const [theme, variant] of Object.entries({ light: 'light', dark: 'cool' })) {
    assert.deepEqual(boot({ saved: theme }), { href: `/landing/hero-${variant}-1448.webp`, srcset: heroSet(variant), theme, fonts: [] });
  }
});

test('the hero is preloaded for system-dark and storage-disabled visitors', () => {
  assert.equal(boot({ systemDark: true }).srcset, heroSet('cool'));
  assert.deepEqual(boot({ storageBlocked: true }), {
    href: '/landing/hero-light-1448.webp', srcset: heroSet('light'), theme: 'light', fonts: [],
  });
});

test('signed-in users and the login route skip the hero preload', () => {
  assert.equal(boot({ saved: 'light', tokens: { 'naseeb-refresh-token': 'x' } }).preloaded, false);
  assert.equal(boot({ saved: 'light', tokens: { 'admitflow-access-token': 'x' } }).preloaded, false);
  assert.equal(boot({ saved: 'dark', hash: '#/login' }).preloaded, false);
});

test('Russian also preloads the Cyrillic font subset', () => {
  assert.deepEqual(boot({ saved: 'light', lang: 'ru' }).fonts, ['/fonts/montserrat-cyrillic.woff2']);
  assert.deepEqual(boot({ saved: 'light', lang: 'uz' }).fonts, []);
});

test('the hero stays eager/high; the other HTML images are lazy/async with dimensions', () => {
  const images = landing.match(/<img\b[\s\S]*?\/>/g);
  assert.equal(images.length, 4, 'audit new image render sites if this count changes');
  assert.match(images[0], /loading="eager"/);
  assert.match(images[0], /fetchPriority="high"/);
  assert.equal((landing.match(/fetchPriority="high"/g) || []).length, 1);
  images.slice(1).forEach((img) => {
    assert.match(img, /loading="lazy"/);
    assert.match(img, /decoding="async"/);
  });
  images.forEach((img) => {
    assert.match(img, /width="\d+"/);
    assert.match(img, /height="\d+"/);
  });
});

test('?lang= in the URL wins over the stored language (hreflang alternates)', () => {
  assert.deepEqual(boot({ saved: 'light', lang: 'en', search: '?lang=ru' }).fonts, ['/fonts/montserrat-cyrillic.woff2']);
});
