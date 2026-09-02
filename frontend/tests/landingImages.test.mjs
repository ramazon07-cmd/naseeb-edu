import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const landing = readFileSync(new URL('../src/LandingPage.jsx', import.meta.url), 'utf8');
const bootstrap = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function boot({ saved, systemDark = false, storageBlocked = false }) {
  const hero = {};
  const documentElement = { dataset: {}, style: {} };
  runInNewContext(bootstrap, {
    document: {
      documentElement,
      getElementById: () => ({}),
      querySelector: (selector) => selector === 'link[data-theme-hero]' ? hero : {},
    },
    localStorage: { getItem: (key) => {
      if (storageBlocked) throw new Error('Storage unavailable');
      return key === 'naseeb-edu-theme' ? saved : 'en';
    } },
    navigator: { language: 'en-US' },
    matchMedia: () => ({ matches: systemDark }),
  });
  return { href: hero.href, theme: documentElement.dataset.theme };
}

test('only the hero has an image preload and it matches the active theme', () => {
  const imagePreloads = html.match(/<link\b[^>]*rel="preload"[^>]*as="image"[^>]*>/g);
  assert.equal(imagePreloads.length, 1);
  assert.match(imagePreloads[0], /fetchpriority="high"/);
  for (const theme of ['light', 'dark']) {
    const href = `/landing/naseeb-student-application-hero-${theme}.png`;
    assert.deepEqual(boot({ saved: theme }), { href, theme });
    assert.ok(landing.includes(href), 'preload must match the JSX image URL');
  }
});

test('the hero is preloaded for system-dark and storage-disabled visitors', () => {
  assert.equal(boot({ systemDark: true }).href, '/landing/naseeb-student-application-hero-dark.png');
  assert.deepEqual(boot({ storageBlocked: true }), {
    href: '/landing/naseeb-student-application-hero-light.png', theme: 'light',
  });
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
