import test from 'node:test';
import assert from 'node:assert/strict';
import { contactLine, cvDateRange, hasCvContent, linkText, monthYear, parseIsoDate, safeHref } from '../src/lib/cv.js';

test('an ongoing entry reads "2024 - Present"', () => {
  assert.equal(cvDateRange({ start: '2024-09-01', current: true }), '2024 - Present');
  assert.equal(cvDateRange({ start: '2024-09-01', end: '2025-01-01', current: true }), '2024 - Present');
  assert.equal(cvDateRange({ current: true }), 'Present');
});

test('months of one year share the year: "June - December | 2023"', () => {
  assert.equal(cvDateRange({ start: '2023-06-01', end: '2023-12-15' }), 'June - December | 2023');
  assert.equal(cvDateRange({ start: '2023-06-01', end: '2023-06-30' }), 'June 2023');
});

test('ranges over several years spell both ends', () => {
  assert.equal(cvDateRange({ start: '2023-03-01', end: '2024-09-01' }), 'March 2023 - September 2024');
});

test('single dates, open ends and free text', () => {
  assert.equal(cvDateRange({ date: '2025-01-15' }), 'January 2025');
  assert.equal(cvDateRange({ start: '2022-10-01' }), 'October 2022');
  assert.equal(cvDateRange({ end: '2022-10-01' }), 'October 2022');
  assert.equal(cvDateRange({ date_text: ' Class of 2027 ' }), 'Class of 2027');
  assert.equal(cvDateRange({ date_text: 'Grades 9, 10, 11' }), 'Grades 9, 10, 11');
  assert.equal(cvDateRange({}), '');
  assert.equal(cvDateRange(), '');
  assert.equal(cvDateRange({ date: 'not a date', date_text: 'Grade 10' }), 'Grade 10');
});

test('ISO dates parse without time zones shifting the month', () => {
  assert.deepEqual(parseIsoDate('2024-01-01'), { year: 2024, month: 0 });
  assert.equal(parseIsoDate('2024-13-01'), null);
  assert.equal(parseIsoDate(null), null);
  assert.equal(monthYear('2024-12-31'), 'December 2024');
});

test('header lines and links', () => {
  assert.equal(contactLine({ email: 'a@example.com', location: 'Samarkand, Uzbekistan', phone: '+998 90 000 00 00' }), 'a@example.com | Samarkand, Uzbekistan | +998 90 000 00 00');
  assert.equal(contactLine({ email: 'a@example.com', location: '', phone: ' ' }), 'a@example.com');
  assert.equal(linkText('https://www.linkedin.com/in/name/'), 'linkedin.com/in/name');
  assert.equal(safeHref('https://example.com'), 'https://example.com');
  assert.equal(safeHref('javascript:alert(1)'), null);
});

test('an empty CV has nothing to print', () => {
  assert.equal(hasCvContent(null), false);
  assert.equal(hasCvContent({ header: { name: 'A' }, sections: [], additional: [] }), false);
  assert.equal(hasCvContent({ sections: [{ key: 'honors', entries: [{}] }], additional: [] }), true);
  assert.equal(hasCvContent({ sections: [], additional: [{ key: 'skills', value: 'Python' }] }), true);
});
