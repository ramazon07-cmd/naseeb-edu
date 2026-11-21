import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { SUBJECT_AREAS, SUBJECT_NAMES, isTopSubjectRank, strongestSubjects, subjectRankText } = await import('../src/lib/subjects.js');
const { collegeSearchQuery, collegeSorts } = await import('../src/lib/college.js');

const item = (code, name, area, rank, score, extra = {}) => ({ code, name, area, is_area: code.startsWith('AREA_'), rank, rank_label: '', score, mine: false, ...extra });

test('a rank reads #3, a tie loses its sign and a published range stays as it is', () => {
  assert.equal(subjectRankText(3, ''), '#3');
  assert.equal(subjectRankText(146, '=146'), '#146');
  assert.equal(subjectRankText(201, '201-250'), '201-250');
  assert.equal(subjectRankText(1001, '1001-1200'), '1001-1200');
  assert.equal(subjectRankText(12), '#12');
});

test('gold is only for a real top-10 position', () => {
  assert.equal(isTopSubjectRank(1), true);
  assert.equal(isTopSubjectRank(10, ''), true);
  assert.equal(isTopSubjectRank(11), false);
  assert.equal(isTopSubjectRank(4, '=4'), true);
  assert.equal(isTopSubjectRank(1, '1-10'), false);
});

test('the picker list holds the 55 subjects under the 5 broad areas, as the backend defines them', () => {
  assert.equal(SUBJECT_AREAS.length, 5);
  assert.equal(SUBJECT_AREAS.reduce((sum, area) => sum + area.subjects.length, 0), 55);
  const source = readFileSync(new URL('../../backend/apps/admissions/subjects.py', import.meta.url), 'utf8');
  const table = source.split('AREAS =')[0];
  const backend = Object.fromEntries([...table.matchAll(/^ {4}'([A-Z_0-9]+)': \(('[^']*'|"[^"]*"), '([A-Z_0-9]+)'\)/gm)].map(([, code, name, area]) => [code, [name.slice(1, -1), area]]));
  assert.equal(Object.keys(backend).length, 60);
  for (const area of SUBJECT_AREAS) {
    assert.deepEqual(backend[area.code], [area.name, area.code]);
    for (const [code, name] of area.subjects) assert.deepEqual(backend[code], [name, area.code], code);
  }
  assert.equal(Object.keys(SUBJECT_NAMES).length, 60);
});

const NYU = [
  item('PHI01', 'Philosophy', 'AREA_ART', 1, 100),
  item('COM02', 'Computer Science & Information Systems', 'AREA_ENG', 22, 90, { mine: true }),
  item('LAW01', 'Law', 'AREA_SOC', 7, 97),
  item('PER01', 'Performing Arts', 'AREA_ART', 8, 96),
  item('COM01', 'Communication & Media Studies', 'AREA_SOC', 10, 95),
  item('ACC01', 'Accounting & Finance', 'AREA_SOC', 11, 94),
  item('MAT01', 'Mathematics', 'AREA_NAT', 14, 80),
  item('AREA_ENG', 'Engineering & Technology', 'AREA_ENG', 30, 70),
  item('AREA_SOC', 'Social Sciences & Management', 'AREA_SOC', 5, 99)
];

test('the major is pinned first, then the best five other subjects by rank', () => {
  const view = strongestSubjects(NYU);
  assert.deepEqual(view.pinned.map((row) => row.code), ['COM02']);
  assert.deepEqual(view.top.map((row) => row.code), ['PHI01', 'LAW01', 'PER01', 'COM01', 'ACC01']);
  assert.equal(view.total, 7);
});

test('the full list groups the ranked subjects by area, best first, with the area rank on top', () => {
  const { groups } = strongestSubjects(NYU);
  assert.deepEqual(groups.map((group) => group.code), ['AREA_ART', 'AREA_ENG', 'AREA_NAT', 'AREA_SOC']);
  assert.deepEqual(groups[0].items.map((row) => row.code), ['PHI01', 'PER01']);
  assert.deepEqual(groups[3].items.map((row) => row.code), ['LAW01', 'COM01', 'ACC01']);
  assert.equal(groups[1].rank.rank, 30);
  assert.equal(groups[0].rank, null);
  assert.equal(groups.every((group) => group.items.every((row) => !row.is_area)), true);
});

test('a university without subjects or a major gives empty parts', () => {
  assert.deepEqual(strongestSubjects([]), { pinned: [], top: [], groups: [], total: 0 });
  assert.deepEqual(strongestSubjects(undefined).pinned, []);
  const view = strongestSubjects(NYU.map((row) => ({ ...row, mine: false })));
  assert.deepEqual(view.pinned, []);
  assert.equal(view.top[0].code, 'PHI01');
});

test('two pinned major subjects stay in the order given', () => {
  const view = strongestSubjects(NYU.map((row) => ({ ...row, mine: ['LAW01', 'COM02'].includes(row.code) })).sort((a, b) => (a.code === 'LAW01' ? -1 : b.code === 'LAW01' ? 1 : 0)));
  assert.deepEqual(view.pinned.map((row) => row.code), ['LAW01', 'COM02']);
  assert.equal(view.top.some((row) => row.code === 'LAW01'), false);
});

test('the search query carries the subject only when one is picked', () => {
  assert.equal(new URLSearchParams(collegeSearchQuery({})).has('subject'), false);
  const picked = new URLSearchParams(collegeSearchQuery({ subject: 'COM02', sort: 'subject' }));
  assert.equal(picked.get('subject'), 'COM02');
  assert.equal(picked.get('sort'), 'subject');
  assert.equal(picked.has('subject_only'), false);
  const only = new URLSearchParams(collegeSearchQuery({ subject: 'COM02', subjectOnly: true }));
  assert.equal(only.get('subject_only'), 'true');
  const stale = new URLSearchParams(collegeSearchQuery({ sort: 'subject', subjectOnly: true }));
  assert.equal(stale.get('sort'), 'ranking');
  assert.equal(stale.has('subject_only'), false);
});

test('"Best in subject" is offered only with a subject', () => {
  assert.equal(collegeSorts('').some(([value]) => value === 'subject'), false);
  assert.equal(collegeSorts('COM02').some(([value]) => value === 'subject'), true);
});
