import assert from 'node:assert/strict';
import fs from 'node:fs';
import { t, tx, setLanguage } from '../frontend/src/i18n.js';
const source = fs.readFileSync(new URL('../frontend/src/translations/ui.js', import.meta.url), 'utf8');
const block = source.split('// Student portal labels and built-in catalog content.')[1].split('// Landing — footer navigation')[0];
const keys = [...block.matchAll(/^\s*("(?:[^"\\]|\\.)*"):/gm)].map(match => JSON.parse(match[1]));
for (const language of ['uz', 'ru']) {
  setLanguage(language);
  for (const key of keys) {
    assert.notEqual(t(key), key, `${language}: untranslated ${key}`);
    if (language === 'ru') assert.match(t(key), /[А-Яа-яЁё]/, key);
  }
  assert.ok(!tx`Search ${t('Direct')}`.includes('Direct'));
  assert.ok(!t('Meeting with {name}', { name: 'Madina' }).includes('{name}'));
  assert.equal(t('My original student message'), 'My original student message');
}
// The same welcome key must respond immediately to language changes.
const welcome = 'I can help you plan tasks, understand your roadmap, and prepare application work. I cannot change your account data.';
setLanguage('uz'); const uz = t(welcome);
setLanguage('ru'); assert.notEqual(t(welcome), uz);
setLanguage('en'); assert.equal(t(welcome), welcome);
console.log(`Portal localization passed: ${keys.length} keys in Uzbek and Russian, live language switching, interpolation, and original-content fallback.`);
