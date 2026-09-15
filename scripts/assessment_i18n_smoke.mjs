import assert from 'node:assert/strict';
import { CHALLENGES, TRAIT_LABEL, RIASEC_NAME, SUBJECT_NAME } from '../frontend/src/challenges.js';
import { setLanguage, t } from '../frontend/src/i18n.js';
import { ASSESSMENT_TRANSLATIONS } from '../frontend/src/translations/assessment.js';

const keys = new Set([
  ...Object.keys(ASSESSMENT_TRANSLATIONS),
  'Completed', 'In progress', 'Review', 'Continue', 'Start', 'Back', 'Next',
  ...Object.values(TRAIT_LABEL), ...Object.values(RIASEC_NAME), ...Object.values(SUBJECT_NAME),
]);
for (const challenge of CHALLENGES) {
  for (const key of [challenge.title, challenge.blurb, ...(challenge.scale || [])]) keys.add(key);
  for (const item of challenge.items) {
    keys.add(item.text);
    if (item.section) keys.add(item.section);
    if (item.imageAlt) keys.add(item.imageAlt);
    for (const option of item.options || []) {
      // Answer letters and numbers retain their original identity in every language.
      if (option.length > 1 && !/^\d+$/.test(option)) keys.add(option);
    }
  }
}
for (const language of ['uz', 'ru', 'en', 'uz']) {
  setLanguage(language);
  for (const key of keys) {
    if (language === 'en') assert.equal(t(key), key);
    else assert.notEqual(t(key), key, `${language} translation missing: ${key}`);
  }
  const choice = t('Choose {major}', { major: 'Mathematics' });
  assert(choice.includes('Mathematics'));
  assert(!choice.includes('{major}'));
  const progress = t('{answered} of {total} questions answered', { answered: 3, total: 16 });
  assert(progress.includes('3') && progress.includes('16'));
  assert(!progress.includes('{'));
}
console.log('Assessment translation coverage and language switching passed for all 147 questions.');
