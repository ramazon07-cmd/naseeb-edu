// Public images stay within a size budget, so full-size photos are never
// shipped for 52 px avatars again. Resize with scripts/optimize-images.mjs.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const publicDir = join(root, 'public');
const KB = 1024;
const IMAGE = /\.(png|jpe?g|gif|webp|avif|svg|ico)$/i;
const BUDGETS = [
  [/^brand\/(favicon-|apple-touch-icon)/, 16 * KB],
  [/^landing\/reviews\//, 16 * KB],
  [/^landing\/team\//, 32 * KB],
  [/^landing\/hero-/, 96 * KB],
  [/^brand\//, 96 * KB],
  [/./, 160 * KB],
];
// Known exceptions, each with a reason. Shrink these, never grow the list lightly.
const EXEMPT = {};

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

test('every public image is within its size budget', () => {
  const over = [];
  for (const file of walk(publicDir).filter((f) => IMAGE.test(f))) {
    const rel = relative(publicDir, file).split('\\').join('/');
    if (EXEMPT[rel]) continue;
    const budget = BUDGETS.find(([pattern]) => pattern.test(rel))[1];
    const size = statSync(file).size;
    if (size > budget) over.push(`${rel}: ${Math.round(size / KB)} KB > ${budget / KB} KB`);
  }
  assert.deepEqual(over, [], 'run `node scripts/optimize-images.mjs` or resize these images');
});

test('SVGs are vectors, not wrapped raster images', () => {
  for (const file of walk(publicDir).filter((f) => f.endsWith('.svg'))) {
    const svg = readFileSync(file, 'utf8');
    assert.ok(!/href="data:image\/(png|jpe?g|webp)/.test(svg), `${relative(publicDir, file)} embeds a raster image`);
  }
});
