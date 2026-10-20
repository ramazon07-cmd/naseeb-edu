import test from 'node:test';
import assert from 'node:assert/strict';
import { activePrograms, planNextStep, publishedPlan, webUrl } from '../src/lib/applicationPlan.js';

test('portals accept only absolute web URLs, without embedded credentials', () => {
  assert.equal(webUrl('https://apply.university.test/start'), 'https://apply.university.test/start');
  for (const value of ['javascript:alert(1)', '/apply', 'ftp://university.test', 'https://user:secret@university.test']) assert.equal(webUrl(value), '');
});

test('published defaults belong to the exact active program; a homepage never becomes a portal', () => {
  const university = { website: 'https://university.test', application_deadline: '2027-01-01', programs: [
    { id: 1, name: 'Computer Science', application_url: 'https://apply.university.test/cs', application_deadline: '2027-02-01' },
    { id: 2, name: 'Economics', is_active: false, application_url: 'https://apply.university.test/economics' },
  ] };
  assert.equal(activePrograms(university).length, 1);
  assert.deepEqual(publishedPlan(university, ' computer science '), { deadline: '2027-02-01', scholarship_deadline: '', application_portal_url: 'https://apply.university.test/cs' });
  assert.equal(publishedPlan(university, 'Business, Economics').application_portal_url, '');
  assert.equal(publishedPlan(university, 'Economics').application_portal_url, '');
});

test('a plan points to the actual missing step and preserves submission and decision meaning', () => {
  const plan = { program: 'Computer Science', deadline: '2027-01-01', application_portal_url: 'https://apply.university.test/', status: 'applying' };
  assert.match(planNextStep({ ...plan, program: '' }), /Choose the program/);
  assert.match(planNextStep({ ...plan, deadline: '' }), /save its deadline/);
  assert.match(planNextStep({ ...plan, application_portal_url: '' }), /Find the application portal/);
  assert.match(planNextStep(plan, [{ status: 'needs_revision' }]), /Revise/);
  assert.match(planNextStep(plan), /submit it there, then confirm/);
  assert.match(planNextStep({ status: 'submitted' }), /Track the official portal/);
  assert.match(planNextStep({ status: 'accepted' }), /counselor/);
});
