// "Seen" flag of the first-visit site tour: one frontend-only key per account.
// It is not part of USER_STORAGE on purpose: that set is wiped at sign-out, and the
// tour must not come back every time the same student signs in again.
export const SITE_TOUR_KEY = 'naseeb-site-tour-v1';

const keyFor = (userId) => `${SITE_TOUR_KEY}:${userId}`;

export function siteTourSeen(userId) {
  if (userId === undefined || userId === null || userId === '') return true;
  try { return localStorage.getItem(keyFor(userId)) === '1'; } catch { return true; }
}

export function markSiteTourSeen(userId) {
  if (userId === undefined || userId === null || userId === '') return;
  try { localStorage.setItem(keyFor(userId), '1'); } catch { /* A private window just sees the tour again. */ }
}
