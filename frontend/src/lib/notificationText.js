// A student notice in the reader's language. The server stores its notices as
// English sentences with the details filled in, so each known sentence is
// matched by kind, its details are lifted out and put into a translated
// template. Anything unrecognised (a new server sentence, a custom notice)
// keeps the server's text.
import { formatDateLocale, t, tp } from '../i18n.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// The server writes meeting times as "29 Sep 2026, 17:42 (Tashkent time)"
// (school-local time); notices written before the zone was added lack it.
const MEETING_TIME = '(\\d{1,2} [A-Z][a-z]{2} \\d{4}, \\d{2}:\\d{2}(?: \\(Tashkent time\\))?)';
const ISO_DATE = '(\\d{4}-\\d{2}-\\d{2})';

function meetingTime(text) {
  const match = /^(\d{1,2}) ([A-Z][a-z]{2}) (\d{4}), (\d{2}):(\d{2})( \(Tashkent time\))?$/.exec(text);
  const month = match ? MONTHS.indexOf(match[2]) : -1;
  if (month < 0) return text;
  const date = new Date(Number(match[3]), month, Number(match[1]), Number(match[4]), Number(match[5]));
  const time = formatDateLocale(date, { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  return match[6] ? t('{time} (Tashkent time)', { time }) : time;
}

// The server's stand-in when a meeting has no participant any more.
const participant = (name) => (name === 'your meeting participant' ? t('your meeting participant') : name);

const MEETING_STATUS = {
  approved: 'Your meeting with {name} on {time} was approved.',
  confirmed: 'Your meeting with {name} on {time} was confirmed.',
  rejected: 'Your meeting with {name} on {time} was declined.',
  completed: 'Your meeting with {name} on {time} is marked as completed.',
};

// kind -> [[pattern, (match) => translated text], ...]
const MESSAGES = {
  task: [
    [/^(\d+) task\(s\) are past their deadline\.$/, ([, n]) => tp('{n} task is past its deadline.|{n} tasks are past their deadline.', Number(n), { n: Number(n) })],
    // A counselor's reminder (send_reminder in services.py).
    [new RegExp(`^“(.+)” is due ${ISO_DATE}\\.$`), ([, title, date]) => t('“{title}” is due {date}.', { title, date: formatDateLocale(date) })],
    [/^“(.+)” is on your roadmap\.$/, ([, title]) => t('“{title}” is on your roadmap.', { title })],
  ],
  document: [
    [/^(\d+) required document\(s\) still need to be uploaded\.$/, ([, n]) => tp('{n} required document still needs to be uploaded.|{n} required documents still need to be uploaded.', Number(n), { n: Number(n) })],
    [/^Please upload “(.+)”\.$/, ([, title]) => t('Please upload “{title}”.', { title })],
  ],
  profile_review: [
    [/^Please finish your profile so your counselor can plan with you\.$/, () => t('Please finish your profile so your counselor can plan with you.')],
  ],
  deadline: [
    [new RegExp(`^(.+) deadline is ${ISO_DATE}\\.$`), ([, university, date]) => t('The {university} deadline is {date}.', { university, date: formatDateLocale(date) })],
  ],
  essay: [
    [/^(.+) shared an essay for review\.$/, ([, name]) => t('{name} shared an essay for review.', { name })],
    // Essay Lab feedback (essay_lab/collab_views.py).
    [/^(.+) left a comment on your essay\.$/, ([, name]) => t('{name} left a comment on your essay.', { name })],
    [/^(.+) replied to a comment on your essay\.$/, ([, name]) => t('{name} replied to a comment on your essay.', { name })],
    [/^(.+) suggested (\d+) edits? to your essay\.$/, ([, name, n]) => tp('{name} suggested {n} edit to your essay.|{name} suggested {n} edits to your essay.', Number(n), { name, n: Number(n) })],
    [/^(.+) replied to your comment on an essay\.$/, ([, name]) => t('{name} replied to your comment on an essay.', { name })],
    [/^(.+) resolved your comment on an essay\.$/, ([, name]) => t('{name} resolved your comment on an essay.', { name })],
    [/^(.+) accepted (\d+) suggestions? and rejected (\d+) suggestions? on an essay\.$/, ([, name, yes, no]) => t('{name} accepted {yes} and rejected {no} of your suggestions on an essay.', { name, yes: Number(yes), no: Number(no) })],
    [/^(.+) accepted (\d+) suggestions? on an essay\.$/, ([, name, n]) => tp('{name} accepted {n} suggestion on an essay.|{name} accepted {n} suggestions on an essay.', Number(n), { name, n: Number(n) })],
    [/^(.+) rejected (\d+) suggestions? on an essay\.$/, ([, name, n]) => tp('{name} rejected {n} suggestion on an essay.|{name} rejected {n} suggestions on an essay.', Number(n), { name, n: Number(n) })],
  ],
  meeting: [
    [new RegExp(`^Your meeting with (.+) on ${MEETING_TIME} is now (approved|confirmed|rejected|completed)\\.$`), ([, name, time, status]) => t(MEETING_STATUS[status], { name: participant(name), time: meetingTime(time) })],
    [new RegExp(`^Your meeting with (.+) on ${MEETING_TIME} was cancelled\\.$`), ([, name, time]) => t('Your meeting with {name} on {time} was cancelled.', { name: participant(name), time: meetingTime(time) })],
    [new RegExp(`^(.+) cancelled the meeting "(.*)" on ${MEETING_TIME}\\.$`), ([, name, topic, time]) => t('{name} cancelled the meeting “{topic}” on {time}.', { name, topic, time: meetingTime(time) })],
    [new RegExp(`^You asked to move "(.*)" to ${MEETING_TIME}\\. Waiting for (.+) to confirm\\.$`), ([, topic, time, name]) => t('You asked to move “{topic}” to {time}. Waiting for {name} to confirm.', { topic, time: meetingTime(time), name })],
    [new RegExp(`^(.+) asked to move "(.*)" to ${MEETING_TIME}\\.$`), ([, name, topic, time]) => t('{name} asked to move “{topic}” to {time}.', { name, topic, time: meetingTime(time) })],
    [new RegExp(`^Your meeting with (.+) was moved to ${MEETING_TIME}\\.$`), ([, name, time]) => t('Your meeting with {name} was moved to {time}.', { name: participant(name), time: meetingTime(time) })],
    [new RegExp(`^(.+) moved "(.*)" with (.+) to ${MEETING_TIME}\\. Please confirm\\.$`), ([, name, topic, student, time]) => t('{name} moved “{topic}” with {student} to {time}. Please confirm.', { name, topic, student, time: meetingTime(time) })],
    [new RegExp(`^(.+) booked "(.*)" with you on ${MEETING_TIME}\\.$`), ([, name, topic, time]) => t('{name} booked “{topic}” with you on {time}.', { name, topic, time: meetingTime(time) })],
    [new RegExp(`^(.+) requested "(.*)" on ${MEETING_TIME}\\.$`), ([, name, topic, time]) => t('{name} requested “{topic}” on {time}.', { name, topic, time: meetingTime(time) })],
  ],
};

export function notificationMessage(notification) {
  const text = String(notification?.message ?? '');
  for (const [pattern, render] of MESSAGES[notification?.kind] || []) {
    const match = pattern.exec(text);
    if (match) return render(match);
  }
  return text;
}

// Titles are fixed sentences; t() falls back to the server's text.
export const notificationTitle = (notification) => t(String(notification?.title ?? ''));
