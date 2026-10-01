// A student's activity feed, in the reader's language. The server writes each
// entry as an English sentence with the details filled in (ActivityLog.action),
// so every known sentence is matched, its details lifted out and put into a
// translated template. Anything unrecognised keeps the server's text.
import { t } from '../i18n.js';

const SENTENCES = [
  [/^Task approved: (.+) \(\+(\d+) XP\)$/, ([, title, xp]) => t('Task approved: {title} (+{xp} XP)', { title, xp: Number(xp) })],
  [/^Self-task approved: (.+) \(no XP\)$/, ([, title]) => t('Self-task approved: {title} (no XP)', { title })],
  [/^Roadmap mission approved: (.+) \(\+(\d+) XP\)$/, ([, title, xp]) => t('Mission approved: {title} (+{xp} XP)', { title, xp: Number(xp) })],
  [/^Document approved: (.+)$/, ([, title]) => t('Document approved: {title}', { title })],
  [/^Achievement approved: (.+)$/, ([, title]) => t('Portfolio item verified: {title}', { title })],
  [/^Task sent back: (.+)$/, ([, title]) => t('Task sent back: {title}', { title })],
  [/^Roadmap mission sent back: (.+)$/, ([, title]) => t('Mission sent back: {title}', { title })],
  [/^Document sent back: (.+)$/, ([, title]) => t('Document sent back: {title}', { title })],
  [/^Achievement sent back: (.+)$/, ([, title]) => t('Portfolio item sent back: {title}', { title })],
  [/^Reminder sent: (.+)$/, ([, subject]) => t('Reminder sent: {subject}', { subject })],
  [/^Level approved: (\d+) → (\d+)$/, ([, from, to]) => t('Level approved: {from} → {to}', { from, to })],
  [/^Student completed their profile$/, () => t('Completed their profile')],
  [/^Essay shared with counselor$/, () => t('Shared an essay with you')],
  [/^Essay no longer shared with counselor$/, () => t('Stopped sharing an essay')],
  [/^Profile section reviewed$/, () => t('Profile section reviewed')],
  [/^Student assigned to counselor: (.+)$/, ([, name]) => t('Assigned to {name}', { name })],
  [/^Student profile created: (.+)$/, ([, name]) => t('Profile created: {name}', { name })],
];

export function activityText(action) {
  const text = String(action ?? '');
  for (const [pattern, render] of SENTENCES) {
    const match = pattern.exec(text);
    if (match) return render(match);
  }
  return text;
}
