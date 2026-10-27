// Official SAT Weekend administrations. Never derive test dates from a weekday rule:
// September administrations started in 2025, and published dates can change.
// Verified 2026-10-20. Recheck these sources when College Board confirms a new cycle.
export const SAT_DATE_SOURCES = [
  'https://international.collegeboard.org/media/pdf/2024%20Sep_Annual%20Intl%20School%20Webinar_Final%20for%20Sharing.pdf',
  'https://satsuite.collegeboard.org/k12-educators/educator-experience/comparing-sat-weekend-school-day',
  'https://satsuite.collegeboard.org/media/pdf/sat-international-test-dates-flyer.pdf',
];
export const SAT_CALENDAR_URL = 'https://satsuite.collegeboard.org/sat/dates-deadlines';

export const SAT_WEEKEND_DATES = Object.freeze([
  '2024-08-24', '2024-10-05', '2024-11-02', '2024-12-07',
  '2025-03-08', '2025-05-03', '2025-06-07', '2025-08-23',
  '2025-09-13', '2025-10-04', '2025-11-08', '2025-12-06',
  '2026-03-14', '2026-05-02', '2026-06-06', '2026-08-22',
  '2026-09-12', '2026-10-03', '2026-11-07', '2026-12-05',
  '2027-03-06', '2027-05-01', '2027-06-05',
]);

// The form supplies today's local ISO date, avoiding UTC offsets at midnight.
export function satTestDates(status, today) {
  if (status === 'taken') return SAT_WEEKEND_DATES.filter((date) => date <= today).reverse();
  if (status === 'planning' || status === 'scheduled') return SAT_WEEKEND_DATES.filter((date) => date >= today);
  return [];
}
