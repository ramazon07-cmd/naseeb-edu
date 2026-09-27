// A student notice in the reader's language. The server stores its notices as
// English sentences with the details filled in, so each known sentence is
// matched by kind, its details are lifted out and put into a translated
// template. Anything unrecognised (a new server sentence, a custom notice)
// keeps the server's text.
import { formatDateLocale, t, tp } from '../i18n.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// The server writes meeting times as "29 Sep 2026, 17:42" (school-local time).
const MEETING_TIME = '(\\d{1,2} [A-Z][a-z]{2} \\d{4}, \\d{2}:\\d{2})';
const ISO_DATE = '(\\d{4}-\\d{2}-\\d{2})';

function meetingTime(text) {
  const match = /^(\d{1,2}) ([A-Z][a-z]{2}) (\d{4}), (\d{2}):(\d{2})$/.exec(text);
  const month = match ? MONTHS.indexOf(match[2]) : -1;
  if (month < 0) return text;
  const date = new Date(Number(match[3]), month, Number(match[1]), Number(match[4]), Number(match[5]));
  return formatDateLocale(date, { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// The server's stand-in when a meeting has no participant any more.
const participant = (name) => (name === 'your meeting participant' ? t('your meeting participant') : name);

const MEETING_STATUS = {
  approved: 'Your meeting with {name} on {time} was approved.',
  rejected: 'Your meeting with {name} on {time} was declined.',
  completed: 'Your meeting with {name} on {time} is marked as completed.',
};

// kind -> [[pattern, (match) => translated text], ...]
const MESSAGES = {
  task: [
    [/^(\d+) task\(s\) are past their deadline\.$/, ([, n]) => tp('{n} task is past its deadline.|{n} tasks are past their deadline.', Number(n), { n: Number(n) })],
  ],
  document: [
    [/^(\d+) required document\(s\) still need to be uploaded\.$/, ([, n]) => tp('{n} required document still needs to be uploaded.|{n} required documents still need to be uploaded.', Number(n), { n: Number(n) })],
  ],
  deadline: [
    [new RegExp(`^(.+) deadline is ${ISO_DATE}\\.$`), ([, university, date]) => t('The {university} deadline is {date}.', { university, date: formatDateLocale(date) })],
  ],
  essay: [
    [/^(.+) shared an essay for review\.$/, ([, name]) => t('{name} shared an essay for review.', { name })],
  ],
  meeting: [
    [new RegExp(`^Your meeting with (.+) on ${MEETING_TIME} is now (approved|rejected|completed)\\.$`), ([, name, time, status]) => t(MEETING_STATUS[status], { name: participant(name), time: meetingTime(time) })],
    [new RegExp(`^Your meeting with (.+) on ${MEETING_TIME} was cancelled\\.$`), ([, name, time]) => t('Your meeting with {name} on {time} was cancelled.', { name: participant(name), time: meetingTime(time) })],
    [new RegExp(`^(.+) cancelled the meeting "(.*)" on ${MEETING_TIME}\\.$`), ([, name, topic, time]) => t('{name} cancelled the meeting “{topic}” on {time}.', { name, topic, time: meetingTime(time) })],
    [new RegExp(`^(.+) asked to move "(.*)" to ${MEETING_TIME}\\.$`), ([, name, topic, time]) => t('{name} asked to move “{topic}” to {time}.', { name, topic, time: meetingTime(time) })],
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
