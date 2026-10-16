import test from 'node:test';
import assert from 'node:assert/strict';
import { attentionItems, weekDeadlines, weekOf } from '../src/lib/studentQuickLook.js';

test('a week runs Monday to Sunday', () => {
  assert.deepEqual(weekOf('2026-10-11'), ['2026-10-05', '2026-10-11']);
  assert.deepEqual(weekOf('2026-10-12'), ['2026-10-12', '2026-10-18']);
  assert.deepEqual(weekOf('2026-12-30'), ['2026-12-28', '2027-01-03']);
});

const records = {
  tasks: [
    { id: 1, title: 'Late essay', status: 'todo', due_date: '2026-10-06' },
    { id: 2, title: 'Done', status: 'approved', due_date: '2026-10-06' },
    { id: 3, title: 'Sent', status: 'submitted', due_date: '2026-10-01' },
    { id: 4, title: 'Thursday', status: 'in_progress', due_date: '2026-10-09' },
    { id: 5, title: 'Next week', status: 'todo', due_date: '2026-10-13' },
  ],
  'roadmap-missions': [
    { id: 7, title: 'Old mission', status: 'planned', due_date: '2026-09-01' },
    { id: 8, title: 'Waiting', status: 'submitted', due_date: null },
  ],
  documents: [
    { id: 9, title: 'Passport', status: 'required' },
    { id: 10, title: 'Transcript', status: 'uploaded', has_file: true },
    { id: 18, title: 'Visa', status: 'reviewing', has_file: false, google_docs_url: '' },
    { id: 11, title: 'CV', status: 'approved' },
  ],
  applications: [
    { id: 12, status: 'planning', deadline: '2026-10-10', university_detail: { name: 'HKU' } },
    { id: 13, status: 'submitted', deadline: '2026-10-10', university_detail: { name: 'Sent U' } },
  ],
  recommendations: [{ id: 14, status: 'drafting', deadline: '2026-10-08', recommender_name: 'Ms Lee' }],
  achievements: [
    { id: 15, title: 'Olympiad', verified: false, counselor_comment: '' },
    { id: 16, title: 'Sent back', verified: false, counselor_comment: 'Add a certificate' },
    { id: 17, title: 'Verified', verified: true, counselor_comment: '' },
  ],
};

test('what needs attention: late work, missing documents, then work to review', () => {
  assert.deepEqual(attentionItems(records, '2026-10-08').map((item) => [item.kind, item.title]), [
    ['late_task', 'Late essay'], ['missing_document', 'Passport'], ['missing_document', 'Visa'],
    ['review', 'Sent'], ['review', 'Waiting'], ['review', 'Transcript'], ['review', 'Olympiad'],
  ]);
  assert.deepEqual(attentionItems({}, '2026-10-08'), []);
});

test('deadlines this week: open dated work of this Monday to Sunday, soonest first', () => {
  assert.deepEqual(weekDeadlines(records, '2026-10-08').map((item) => [item.kind, item.title, item.due, item.late]), [
    ['task', 'Late essay', '2026-10-06', true],
    ['letter', 'Ms Lee', '2026-10-08', false],
    ['task', 'Thursday', '2026-10-09', false],
    ['application', 'HKU', '2026-10-10', false],
  ]);
});
