import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { setLanguage, TRANSLATIONS } = await import('../src/i18n.js');
const { notificationMessage, notificationTitle } = await import('../src/lib/notificationText.js');

// Exactly what the server writes (generate_notifications, meeting and essay views).
const SERVER = {
  lateTasks: { kind: 'task', title: 'Late tasks require attention', message: '3 task(s) are past their deadline.' },
  oneTask: { kind: 'task', title: 'Late tasks require attention', message: '1 task(s) are past their deadline.' },
  documents: { kind: 'document', title: 'Required documents are missing', message: '2 required document(s) still need to be uploaded.' },
  deadline: { kind: 'deadline', title: 'University deadline approaching', message: 'Stanford University deadline is 2026-10-01.' },
  essay: { kind: 'essay', title: 'Essay shared with counselor', message: 'Ramazon Ergashev shared an essay for review.' },
  approved: { kind: 'meeting', title: 'Meeting approved', message: 'Your meeting with Madina Counselor on 29 Sep 2026, 17:42 is now approved.' },
  rejected: { kind: 'meeting', title: 'Meeting rejected', message: 'Your meeting with your meeting participant on 01 Oct 2026, 09:00 is now rejected.' },
  completed: { kind: 'meeting', title: 'Meeting completed', message: 'Your meeting with Madina Counselor on 29 Sep 2026, 17:42 is now completed.' },
  cancelledByStaff: { kind: 'meeting', title: 'Meeting cancelled', message: 'Your meeting with Madina Counselor on 29 Sep 2026, 17:42 was cancelled.' },
  cancelledByStudent: { kind: 'meeting', title: 'Meeting cancelled', message: 'Ramazon cancelled the meeting "Essay review" on 29 Sep 2026, 17:42.' },
  reschedule: { kind: 'meeting', title: 'Meeting reschedule requested', message: 'Ramazon asked to move "Essay review" to 2 Oct 2026, 10:30.' },
  remindTask: { kind: 'task', title: 'Your counselor sent a reminder', message: '“Recommendation letter request” is due 2026-07-18.' },
  remindMission: { kind: 'task', title: 'Your counselor sent a reminder', message: '“Research 10 universities” is on your roadmap.' },
  remindDocument: { kind: 'document', title: 'Your counselor sent a reminder', message: 'Please upload “Passport”.' },
  remindProfile: { kind: 'profile_review', title: 'Your counselor sent a reminder', message: 'Please finish your profile so your counselor can plan with you.' },
};

test('known server notices are rewritten in Uzbek and Russian', () => {
  for (const language of ['uz', 'ru']) {
    setLanguage(language);
    for (const [name, notice] of Object.entries(SERVER)) {
      const message = notificationMessage(notice);
      assert.notEqual(message, notice.message, `${language} ${name}`);
      assert.doesNotMatch(message, /[{}]|\(s\)| is now | deadline is /, `${language} ${name}: ${message}`);
      assert.notEqual(notificationTitle(notice), notice.title, `${language} ${name} title`);
    }
  }
  setLanguage('uz');
  assert.equal(notificationMessage(SERVER.lateTasks), '3 ta vazifaning muddati o‘tib ketgan.');
  assert.match(notificationMessage(SERVER.deadline), /^Stanford University uchun topshirish muddati: /);
  assert.match(notificationMessage(SERVER.approved), /^Madina Counselor bilan uchrashuvingiz \(29.*2026.*17:42\) tasdiqlandi\.$/);
  setLanguage('ru');
  assert.equal(notificationMessage(SERVER.oneTask), '1 задача просрочена.');
  assert.equal(notificationMessage(SERVER.lateTasks), '3 задачи просрочены.');
  assert.match(notificationMessage(SERVER.rejected), /^Ваша встреча с участником встречи \(.+\) отклонена\.$/);
  assert.match(notificationMessage(SERVER.reschedule), /«Essay review»/);
});

test('English keeps the details and reads naturally', () => {
  setLanguage('en');
  assert.equal(notificationMessage(SERVER.oneTask), '1 task is past its deadline.');
  assert.equal(notificationMessage(SERVER.documents), '2 required documents still need to be uploaded.');
  assert.equal(notificationMessage(SERVER.essay), 'Ramazon Ergashev shared an essay for review.');
  assert.match(notificationMessage(SERVER.approved), /^Your meeting with Madina Counselor on .*2026.* was approved\.$/);
  assert.equal(notificationTitle(SERVER.approved), 'Meeting approved');
});

test('unknown kinds and sentences fall back to the server text', () => {
  setLanguage('ru');
  const custom = { kind: 'general', title: 'Welcome to Naseeb', message: 'Your counselor added you.' };
  assert.equal(notificationMessage(custom), 'Your counselor added you.');
  assert.equal(notificationTitle(custom), 'Welcome to Naseeb');
  assert.equal(notificationMessage({ kind: 'task', message: 'Recommendation letter request is late.' }), 'Recommendation letter request is late.');
  assert.equal(notificationMessage({ kind: 'meeting', message: 'Your meeting with X on soon is now approved.' }), 'Your meeting with X on soon is now approved.');
  assert.equal(notificationMessage(null), '');
});

test('every notice template has Uzbek and Russian text', () => {
  const source = readFileSync(new URL('../src/lib/notificationText.js', import.meta.url), 'utf8');
  const keys = [...source.matchAll(/'((?:Your meeting with|\{n\}|\{name\}|The \{university\}|your meeting participant)[^']*)'/g)].map((match) => match[1]);
  assert.ok(keys.length >= 10);
  for (const key of keys) for (const language of ['uz', 'ru']) assert.ok(TRANSLATIONS[language][key], `${language}: ${key}`);
});
