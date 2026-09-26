// Quick-grid tiles render <Icon/><span><b/><small/></span>: the icon is the
// badge and the span holds the copy, so the span must never get badge sizing.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
const admin = readFileSync(new URL('../src/pages/AdminPages.jsx', import.meta.url), 'utf8');

function rules(selectorPart) {
  return [...css.matchAll(/([^{}]*)\{([^{}]*)\}/g)]
    .filter(([, selector]) => selector.split(',').some((s) => s.trim().endsWith(selectorPart)))
    .map(([, , body]) => body);
}

test('the icon is the badge, not the text span', () => {
  const svg = rules('.quick-grid button > svg').join('');
  assert.match(svg, /width:\s*38px/);
  assert.match(svg, /background:/);
  for (const body of rules('.quick-grid button > span')) {
    assert.doesNotMatch(body, /\b(width|height):\s*38px/);
    assert.doesNotMatch(body, /background:/);
  }
});

test('the tile grid gives the copy a flexible column', () => {
  const [button] = rules('.quick-grid button');
  assert.match(button, /grid-template-columns:\s*38px minmax\(0, 1fr\);/);
});

test('the description is muted and readable', () => {
  const small = rules('.quick-grid small').join('');
  assert.match(small, /color:\s*var\(--muted\)/);
  assert.match(small, /font-size:\s*var\(--text-/);
});

test('admin tiles use the icon + copy markup', () => {
  const grid = admin.match(/className="quick-grid">(.*?)<\/div>/s)[1];
  const tiles = grid.match(/<button [^>]*>.*?<\/button>/gs);
  assert.equal(tiles.length, 4);
  for (const tile of tiles) assert.match(tile, /^<button onClick=\{[^}]*\}><[A-Z]\w* \/><span><b>.*<\/b><small>.*<\/small><\/span><\/button>$/s);
});
