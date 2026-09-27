import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { countTotal, isMissionLocked, nextLevel, nextPriorities, studentProgress, SUBMITTED_APPLICATION_STATUSES } = await import('../src/lib/metrics.js');
const { setLanguage, tp } = await import('../src/i18n.js');

const task = (id, status, due_date, priority = 'medium') => ({ id, status, due_date, priority });

test('next priorities: open work only, earliest deadline, then most urgent, then oldest', () => {
  const tasks = [
    task(1, 'todo', '2026-10-05', 'low'),
    task(2, 'submitted', '2026-09-01', 'urgent'),
    task(3, 'approved', '2026-09-01', 'urgent'),
    task(4, 'late', '2026-09-20', 'high'),
    task(5, 'todo', '2026-10-05', 'urgent'),
    task(6, 'in_progress', '2026-10-05', 'urgent'),
    task(7, 'todo', null, 'urgent'),
  ];
  assert.deepEqual(nextPriorities(tasks).map((item) => item.id), [4, 5, 6, 1, 7]);
});

test('a decided application still counts as submitted', () => {
  for (const status of ['submitted', 'accepted', 'rejected', 'waitlisted']) assert.ok(SUBMITTED_APPLICATION_STATUSES.includes(status));
  assert.ok(!SUBMITTED_APPLICATION_STATUSES.includes('applying'));
});

test('count totals and the next level (capped at 100, pending level first)', () => {
  assert.equal(countTotal({ todo: 2, approved: 1, late: 0 }), 3);
  assert.equal(countTotal(undefined), 0);
  assert.equal(nextLevel({ level: 1 }), 2);
  assert.equal(nextLevel({ level: 60 }), 61);
  assert.equal(nextLevel({ level: 100 }), 100);
  assert.equal(nextLevel({ level: 2, level_up_pending: true, eligible_level: 4 }), 4);
});

test('a mission is locked by its prerequisite status even when that mission is on another page', () => {
  assert.equal(isMissionLocked({ prerequisite: 9, prerequisite_status: 'submitted' }, []), true);
  assert.equal(isMissionLocked({ prerequisite: 9, prerequisite_status: 'completed' }, []), false);
  assert.equal(isMissionLocked({ prerequisite: 9 }, [{ id: 9, status: 'planned' }]), true);
  assert.equal(isMissionLocked({ prerequisite: null }, []), false);
});

test('English counts are pluralized', () => {
  setLanguage('en');
  const key = '{n} open task|{n} open tasks';
  assert.equal(tp(key, 1, { n: 1 }), '1 open task');
  assert.equal(tp(key, 3, { n: 3 }), '3 open tasks');
  assert.equal(tp(key, 0, { n: 0 }), '0 open tasks');
  setLanguage('ru');
  assert.equal(tp(key, 3, { n: 3 }), '3 открытых задания');
  assert.equal(tp(key, 5, { n: 5 }), '5 открытых заданий');
  setLanguage('en');
});

test('every backend status and document type has a label', () => {
  // labels.js imports i18n without an extension (Vite style), so read its keys as text.
  const source = readFileSync(new URL('../src/lib/labels.js', import.meta.url), 'utf8');
  const LABELS = Object.fromEntries([...source.matchAll(/\b(\w+): '/g)].map((match) => [match[1], true]));
  const values = [
    'todo', 'in_progress', 'submitted', 'approved', 'late',
    'planned', 'completed', 'changes_requested',
    'researching', 'shortlisted', 'applying', 'accepted', 'rejected', 'waitlisted',
    'required', 'uploaded', 'reviewing', 'requested', 'drafting', 'draft', 'needs_revision',
    'passport', 'transcript', 'ielts', 'sat', 'cv', 'recommendation', 'essay', 'certificate', 'other',
  ];
  assert.deepEqual(values.filter((value) => !LABELS[value]), []);
});

test('student progress numbers come from the API fields, each with its own meaning', () => {
  const student = {
    journey_progress_percent: 45, roadmap_progress_percent: 35, roadmap_stars: 7,
    roadmap_status_counts: { planned: 10, in_progress: 2, submitted: 1, completed: 7 },
    level_missions_approved: 2, level_missions_total: 5,
    applications_total: 6, applications_submitted: 3, applications_accepted: 1, achievements_total: 4,
  };
  assert.deepEqual(studentProgress(student), {
    overallPercent: 45, roadmapPercent: 35, missionsApproved: 7, missionsTotal: 20, levelApproved: 2, levelTotal: 5,
    applicationsTotal: 6, applicationsSubmitted: 3, applicationsAccepted: 1, achievementsTotal: 4,
  });
  const empty = studentProgress(null);
  assert.equal(empty.roadmapPercent, 0);
  assert.equal(empty.missionsTotal, 0);
  assert.equal(studentProgress({ roadmap_progress_percent: 140 }).roadmapPercent, 100);
});

test('the dashboard shows roadmap progress on the Roadmap tile and deep-links tasks', () => {
  const source = readFileSync(new URL('../src/CompactDashboard.jsx', import.meta.url), 'utf8');
  assert.match(source, /const progress = numbers\.roadmapPercent;/);
  assert.doesNotMatch(source, /data\.applications\.(filter|length)/);
  assert.doesNotMatch(source, /data\.(achievements|honors)\.length/);
  assert.doesNotMatch(source, /setPage\('roadmap'\)/);
  assert.match(source, /setPage\('roadmap', \{ tab: 'tasks' \}\)/);
  const roadmap = readFileSync(new URL('../src/pages/RoadmapPage.jsx', import.meta.url), 'utf8');
  assert.doesNotMatch(roadmap, /Math\.round\(completed/);
});
