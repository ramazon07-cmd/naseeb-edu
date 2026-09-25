// Every literal UI string passed to t('...'), tp('...') or tx`...` must exist in the
// Uzbek and Russian dictionaries (English is the source text).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { TRANSLATIONS } = await import('../src/i18n.js');

const src = fileURLToPath(new URL('../src/', import.meta.url));
const files = (function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return name === 'translations' ? [] : walk(full);
    return /\.(jsx?|mjs)$/.test(name) ? [full] : [];
  });
})(src);

const unescape = (value) => value.replace(/\\(['"`\\])/g, '$1').replace(/\\n/g, '\n');

export function collectKeys(source) {
  const keys = [];
  for (const match of source.matchAll(/(?<![\w.$])tp?\(\s*(['"])((?:\\.|(?!\1)[^\\])*)\1\s*[,)]/g)) keys.push(unescape(match[2]));
  for (const match of source.matchAll(/(?<![\w.$])tx`((?:\\.|[^`\\])*)`/g)) {
    let index = 0;
    keys.push(unescape(match[1].replace(/\$\{(?:[^{}]|\{[^{}]*\})*\}/g, () => `{${index++}}`)));
  }
  return keys.map((key) => key.replace(/\s+/g, ' ').trim()).filter((key) => /[A-Za-z]/.test(key));
}

test('every literal t()/tx key has Uzbek and Russian text', () => {
  const missing = new Map();
  for (const file of files) {
    for (const key of collectKeys(readFileSync(file, 'utf8'))) {
      for (const language of ['uz', 'ru']) {
        if (!TRANSLATIONS[language][key]) {
          const where = relative(src, file);
          missing.set(`${language}: ${JSON.stringify(key)}`, where);
        }
      }
    }
  }
  assert.deepEqual([...missing].map(([k, where]) => `${k} (${where})`), []);
});
