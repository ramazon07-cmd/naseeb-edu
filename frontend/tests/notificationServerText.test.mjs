import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { setLanguage } = await import('../src/i18n.js');
const { notificationMessage, notificationTitle } = await import('../src/lib/notificationText.js');

// Every notice the meeting and Essay Lab views write (views/portal.py, essay_lab/collab_views.py).
const TIME = '02 Oct 2026, 18:00 (Tashkent time)';
const NOTICES = {
  request: { kind: 'meeting', title: 'New meeting request', message: `Ramazon requested "Essay review" on ${TIME}.` },
  booked: { kind: 'meeting', title: 'Meeting confirmed', message: `Madina Counselor booked "Essay review" with you on ${TIME}.` },
  confirmed: { kind: 'meeting', title: 'Meeting confirmed', message: `Your meeting with Madina Counselor on ${TIME} is now confirmed.` },
  approvedOld: { kind: 'meeting', title: 'Meeting approved', message: 'Your meeting with Madina Counselor on 29 Sep 2026, 17:42 is now approved.' },
  cancelled: { kind: 'meeting', title: 'Meeting cancelled', message: `Ramazon cancelled the meeting "Essay review" on ${TIME}.` },
  rescheduleAsked: { kind: 'meeting', title: 'Meeting reschedule requested', message: `Ramazon asked to move "Essay review" to ${TIME}.` },
  ownMove: { kind: 'meeting', title: 'Meeting reschedule requested', message: `You asked to move "Essay review" to ${TIME}. Waiting for Madina Counselor to confirm.` },
  moved: { kind: 'meeting', title: 'Meeting moved', message: `Your meeting with Madina Counselor was moved to ${TIME}.` },
  movedByOther: { kind: 'meeting', title: 'Meeting moved', message: `Aziz Teacher moved "Essay review" with Ramazon to ${TIME}. Please confirm.` },
  comment: { kind: 'essay', title: 'New feedback on your essay', message: 'Madina Counselor left a comment on your essay.' },
  reply: { kind: 'essay', title: 'New feedback on your essay', message: 'Madina Counselor replied to a comment on your essay.' },
  suggestedOne: { kind: 'essay', title: 'New feedback on your essay', message: 'Madina Counselor suggested 1 edit to your essay.' },
  suggestedMany: { kind: 'essay', title: 'New feedback on your essay', message: 'Madina Counselor suggested 5 edits to your essay.' },
  replyToYou: { kind: 'essay', title: 'New reply to your comment', message: 'Ramazon replied to your comment on an essay.' },
  resolved: { kind: 'essay', title: 'Comment resolved', message: 'Ramazon resolved your comment on an essay.' },
  accepted: { kind: 'essay', title: 'Suggestions reviewed', message: 'Ramazon accepted 2 suggestions on an essay.' },
  rejected: { kind: 'essay', title: 'Suggestions reviewed', message: 'Ramazon rejected 1 suggestion on an essay.' },
  both: { kind: 'essay', title: 'Suggestions reviewed', message: 'Ramazon accepted 1 suggestion and rejected 3 suggestions on an essay.' },
};

test('every meeting and essay notice the server writes reads in Uzbek and Russian', () => {
  for (const language of ['uz', 'ru']) {
    setLanguage(language);
    for (const [name, notice] of Object.entries(NOTICES)) {
      const title = notificationTitle(notice);
      const message = notificationMessage(notice);
      assert.notEqual(title, notice.title, `${language} ${name} title`);
      assert.notEqual(message, notice.message, `${language} ${name}`);
      assert.doesNotMatch(message, /[{}|]|Tashkent time|"/, `${language} ${name}: ${message}`);
    }
  }
  setLanguage('uz');
  assert.equal(notificationTitle(NOTICES.request), 'Yangi uchrashuv so‘rovi');
  assert.equal(notificationTitle(NOTICES.confirmed), 'Uchrashuv tasdiqlandi');
  assert.match(notificationMessage(NOTICES.moved), /^Madina Counselor bilan uchrashuvingiz 2-oktabr.*2026.*18:00 \(Toshkent vaqti\) vaqtiga ko‘chirildi\.$/);
  setLanguage('ru');
  assert.equal(notificationMessage(NOTICES.suggestedMany), 'Madina Counselor предложил(а) 5 правок к вашему эссе.');
  assert.match(notificationMessage(NOTICES.both), /: 1, .*: 3\.$/);
  setLanguage('en');
  assert.equal(notificationMessage(NOTICES.suggestedOne), 'Madina Counselor suggested 1 edit to your essay.');
  assert.match(notificationMessage(NOTICES.request), /^Ramazon requested “Essay review” on .*2026.*18:00 \(Tashkent time\)\.$/);
});
