// UI text is sized in rem (respects the browser font size) and never
// below 12px. The landing "product window" illustration (role="img") is exempt.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { isIllustration } from '../scripts/css-type-scale.mjs';

const dir = new URL('../src/', import.meta.url);
const sheets = readdirSync(dir, { recursive: true }).filter((name) => name.endsWith('.css'));

test('no px font sizes and nothing under 12px outside the illustration', () => {
  const problems = [];
  for (const name of sheets) {
    const css = readFileSync(new URL(name, dir), 'utf8');
    for (const [, selector, body] of css.matchAll(/([^{}]*)\{([^{}]*)\}/g)) {
      if (isIllustration(selector)) continue;
      for (const [decl] of body.matchAll(/font(?:-size)?:[^;}]*/g)) {
        const plain = decl.match(/^font-size:\s*(\d+(?:\.\d+)?)(px|rem)\s*$/);
        if (/\d+(?:\.\d+)?px/.test(decl) && !/clamp\(/.test(decl)) problems.push(`${name}: ${selector.trim().slice(0, 60)} { ${decl.trim()} }`);
        if (plain && plain[2] === 'rem' && Number(plain[1]) < 0.75) problems.push(`${name}: ${selector.trim().slice(0, 60)} { ${decl.trim()} } < 12px`);
      }
    }
  }
  assert.deepEqual(problems, []);
});

test('the type scale tokens exist and start at 12px', () => {
  const styles = readFileSync(new URL('styles.css', dir), 'utf8');
  assert.match(styles, /--text-xs: 0?\.75rem;/);
});

test('the counselor type tokens follow the student dashboard scale', () => {
  const styles = readFileSync(new URL('styles.css', dir), 'utf8');
  for (const token of [
    '--cx-fs-meta: var(--text-xs);',
    '--cx-fs-body: var(--text-sm);',
    '--cx-fs-input: 0.9375rem;',
    '--cx-fs-card-title: 0.9375rem;',
    '--cx-fs-topbar: 1.0625rem;',
    '--cx-fs-figure: var(--text-2xl);',
    '--cx-fs-page-title: 1.875rem;',
    '--cx-fs-stat: 2.5rem;',
  ]) assert.ok(styles.includes(token), token);
});
