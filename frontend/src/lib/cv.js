// Formatting for the Harvard-style CV (components/CvDocument.jsx). The CV is
// written in English whatever the interface language: it goes to admissions
// offices abroad. The data comes whitelisted from GET /api/students/me/cv/.

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

export const CV_SECTION_TITLES = {
  education: 'Education',
  experience: 'Experience & Projects',
  leadership: 'Leadership & Activities',
  honors: 'Honors & Awards',
  additional: 'Additional Information',
};

export const CV_ADDITIONAL_LABELS = {
  languages: 'Languages',
  test_scores: 'Test scores',
  skills: 'Skills',
  interests: 'Interests',
};

// "2024-06-01" -> { year: 2024, month: 5 }; anything else -> null.
export function parseIsoDate(value) {
  const match = /^(\d{4})-(\d{2})(?:-\d{2})?$/.exec(String(value || ''));
  if (!match) return null;
  const month = Number(match[2]) - 1;
  return month >= 0 && month < 12 ? { year: Number(match[1]), month } : null;
}

export const monthYear = (value) => {
  const date = parseIsoDate(value);
  return date ? `${MONTHS[date.month]} ${date.year}` : '';
};

// The right-hand date of an entry:
//   ongoing             "2024 - Present"
//   one year            "June - December | 2023" ("June 2023" for one month)
//   several years       "March 2023 - September 2024"
//   one date            "June 2023"
//   no date             the entry's own text ("Class of 2027", "Grades 9, 10, 11")
export function cvDateRange({ start, end, current, date, date_text: dateText } = {}) {
  const single = parseIsoDate(date);
  if (single) return monthYear(date);
  const from = parseIsoDate(start);
  const to = parseIsoDate(end);
  if (current) return from ? `${from.year} - Present` : 'Present';
  if (from && to) {
    if (from.year === to.year) {
      return from.month === to.month ? monthYear(start) : `${MONTHS[from.month]} - ${MONTHS[to.month]} | ${from.year}`;
    }
    return `${monthYear(start)} - ${monthYear(end)}`;
  }
  if (from || to) return monthYear(start || end);
  return String(dateText || '').trim();
}

// "https://www.linkedin.com/in/name/" -> "linkedin.com/in/name": what the page prints.
export function linkText(url) {
  return String(url || '').trim().replace(/^https?:\/\//i, '').replace(/^www\./i, '').replace(/\/+$/, '');
}

// Only http(s) links become anchors; anything else prints as text.
export const safeHref = (url) => (/^https?:\/\//i.test(String(url || '').trim()) ? String(url).trim() : null);

// "email | Samarkand, Uzbekistan | +998 …": the contact line under the name.
export const contactLine = (header = {}) => [header.email, header.location, header.phone].map((part) => String(part || '').trim()).filter(Boolean).join(' | ');

export const hasCvContent = (cv) => Boolean(cv && ((cv.sections || []).some((section) => section.entries?.length) || (cv.additional || []).length));
