// The 55 QS subjects grouped by the 5 broad areas, and what a subject rank looks like on screen.
// The list mirrors backend apps/admissions/subjects.py (tests/subjects.test.mjs checks they agree);
// ranks come from the existing College Search and university responses.

export const SUBJECT_AREAS = [
  { code: 'AREA_ART', name: 'Arts & Humanities', subjects: [
    ['ARC01', 'Archaeology'],
    ['ARC02', 'Architecture / Built Environment'],
    ['ART01', 'Art & Design'],
    ['CLA01', 'Classics & Ancient History'],
    ['ENG07', 'English Language & Literature'],
    ['HIS01', 'History'],
    ['HIS02', 'History of Art'],
    ['LIN01', 'Linguistics'],
    ['MOD01', 'Modern Languages'],
    ['MUS01', 'Music'],
    ['PER01', 'Performing Arts'],
    ['PHI01', 'Philosophy'],
    ['THE01', 'Theology, Divinity & Religious Studies']
  ] },
  { code: 'AREA_ENG', name: 'Engineering & Technology', subjects: [
    ['COM02', 'Computer Science & Information Systems'],
    ['DAT01', 'Data Science and Artificial Intelligence'],
    ['ENG01', 'Engineering - Chemical'],
    ['ENG02', 'Engineering - Civil & Structural'],
    ['ENG03', 'Engineering - Electrical & Electronic'],
    ['ENG05', 'Engineering - Mechanical, Aeronautical & Manufacturing'],
    ['ENG06', 'Engineering - Mineral & Mining'],
    ['PET01', 'Petroleum Engineering']
  ] },
  { code: 'AREA_LIF', name: 'Life Sciences & Medicine', subjects: [
    ['AGR01', 'Agriculture & Forestry'],
    ['ANA01', 'Anatomy & Physiology'],
    ['BIO01', 'Biological Sciences'],
    ['DEN01', 'Dentistry'],
    ['MED01', 'Medicine'],
    ['NUR01', 'Nursing'],
    ['PHA01', 'Pharmacy & Pharmacology'],
    ['PSY01', 'Psychology'],
    ['VET01', 'Veterinary Science']
  ] },
  { code: 'AREA_NAT', name: 'Natural Sciences', subjects: [
    ['CHE01', 'Chemistry'],
    ['EAR01', 'Earth & Marine Sciences'],
    ['ENV01', 'Environmental Sciences'],
    ['GEO01', 'Geography'],
    ['GEO02', 'Geology'],
    ['GEO03', 'Geophysics'],
    ['MET01', 'Materials Science'],
    ['MAT01', 'Mathematics'],
    ['PHY01', 'Physics & Astronomy']
  ] },
  { code: 'AREA_SOC', name: 'Social Sciences & Management', subjects: [
    ['ACC01', 'Accounting & Finance'],
    ['ANT01', 'Anthropology'],
    ['BUS01', 'Business & Management Studies'],
    ['COM01', 'Communication & Media Studies'],
    ['DEV01', 'Development Studies'],
    ['ECO01', 'Economics & Econometrics'],
    ['EDU01', 'Education'],
    ['HOS01', 'Hospitality & Leisure Management'],
    ['LAW01', 'Law'],
    ['LIB01', 'Library & Information Management'],
    ['MAR01', 'Marketing'],
    ['POL01', 'Politics & International Studies'],
    ['SOC01', 'Social Policy & Administration'],
    ['SOC03', 'Sociology'],
    ['SPO01', 'Sports-related Subjects'],
    ['STA01', 'Statistics & Operational Research']
  ] }
];

export const SUBJECT_NAMES = Object.fromEntries(SUBJECT_AREAS.flatMap((area) => [[area.code, area.name], ...area.subjects]));

export const subjectName = (code) => SUBJECT_NAMES[code] || code;

export const TOP_SUBJECT_RANK = 10;

// Strongest subjects shown before "Show all".
export const STRONGEST_COUNT = 5;

// "#3" for a plain rank, a tie ("=146") as "#146", and a published range ("201-250") as it is.
export function subjectRankText(rank, label = '') {
  const text = String(label || '').trim();
  if (/^\d+\s*[-–]\s*\d+$/.test(text)) return text;
  if (text.startsWith('=')) return `#${text.slice(1)}`;
  return `#${text || rank}`;
}

// Gold is for the world top 10: a real position, never a range.
export const isTopSubjectRank = (rank, label = '') => Number(rank) <= TOP_SUBJECT_RANK && !/[-–]/.test(String(label || ''));

const byRank = (a, b) => a.rank - b.rank || (b.score ?? -1) - (a.score ?? -1) || a.name.localeCompare(b.name);

// What the university page's "Strongest subjects" shows from the `subjects.items` the detail sends:
// the student's own major subjects pinned first (`mine`), then the best `limit` other subjects, and every
// ranked subject grouped by broad area for "Show all". The broad areas themselves are not counted as
// subjects: their rank heads their group.
export function strongestSubjects(items = [], limit = STRONGEST_COUNT) {
  const pinned = items.filter((item) => item.mine);
  const ranked = items.filter((item) => !item.is_area);
  const top = ranked.filter((item) => !item.mine).sort(byRank).slice(0, limit);
  const groups = SUBJECT_AREAS.map((area) => ({
    code: area.code,
    name: area.name,
    rank: items.find((item) => item.code === area.code) || null,
    items: ranked.filter((item) => item.area === area.code).sort(byRank)
  })).filter((group) => group.items.length || group.rank);
  return { pinned, top, groups, total: ranked.length };
}
