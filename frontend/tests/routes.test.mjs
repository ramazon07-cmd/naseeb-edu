import test from 'node:test';
import assert from 'node:assert/strict';
import {
  PAGE_PATHS, ROADMAP_TABS, STUDENT_CENTER_TABS, buildPath, roadmapTab, canOpenPage, homePage, openablePage, loginPath, navigationFor, parsePath,
  isPageLocked, lockedPages, publicPageFor, reachablePages, resolveRoute, safeNextPath, withQuery,
} from '../src/lib/routes.js';

const student = { id: 1, role: 'student' };
const counselor = { id: 2, role: 'counselor' };
const teacher = { id: 3, role: 'teacher' };
const parent = { id: 4, role: 'parent' };
const organization = { id: 5, role: 'organization' };
const admin = { id: 6, role: 'admin' };

test('every page has a unique path that parses back to it', () => {
  const paths = Object.values(PAGE_PATHS);
  assert.equal(new Set(paths).size, paths.length);
  for (const [page, path] of Object.entries(PAGE_PATHS)) {
    assert.deepEqual(parsePath(path), { page, params: {} }, path);
    assert.equal(buildPath({ page }), path);
    assert.ok(!path.startsWith('/admin'), 'Django owns /admin/');
  }
});

test('record and tab routes round-trip', () => {
  const routes = [
    [{ page: 'essay_lab', params: { essayId: 42 } }, '/essay-lab/essays/42'],
    [{ page: 'students', params: { studentId: 15 } }, '/students/15'],
    [{ page: 'admin_students', params: { studentId: 7 } }, '/platform/students/7'],
    ...STUDENT_CENTER_TABS.filter((tab) => tab !== 'overview').map((tab) => [{ page: 'student_center', params: { tab } }, `/student-center/${tab}`]),
    [{ page: 'messages', params: { channelId: 9 } }, '/messages/9'],
    [{ page: 'messages', params: { tab: 'counselor' } }, '/messages/counselor'],
    ...ROADMAP_TABS.map((tab) => [{ page: 'roadmap', params: { tab } }, `/roadmap/${tab}`]),
  ];
  for (const [route, path] of routes) {
    assert.equal(buildPath(route), path);
    assert.deepEqual(parsePath(path), route);
  }
  // The default tab has no path segment of its own.
  assert.equal(buildPath({ page: 'student_center', params: { tab: 'overview' } }), '/student-center');
  // Its explicit path still opens the page and canonicalises to the bare one.
  assert.deepEqual(parsePath('/student-center/overview'), { page: 'student_center', params: {} });
  assert.equal(buildPath(resolveRoute(parsePath('/student-center/overview/'), student)), '/student-center');
  assert.equal(safeNextPath('/student-center/overview'), '/student-center/overview');
});

test('trailing and doubled slashes are tolerated; junk is not a page', () => {
  assert.deepEqual(parsePath('/programs/'), { page: 'programs', params: {} });
  assert.deepEqual(parsePath('//essay-lab//essays/9/'), { page: 'essay_lab', params: { essayId: 9 } });
  for (const junk of ['/', '', '/nope', '/essay-lab/essays/0', '/essay-lab/essays/-1', '/essay-lab/essays/abc', '/essay-lab/42',
    '/students/01', '/students/12345678901', '/student-center/secret', '/programs/3', '/dashboard/1']) {
    assert.equal(parsePath(junk), null, junk);
  }
  assert.equal(buildPath({ page: 'essay_lab', params: { essayId: 'x' } }), '/essay-lab');
  assert.equal(buildPath({ page: 'unknown' }), '/dashboard');
});

test('each role reaches its own pages and lands on its home for the rest', () => {
  assert.deepEqual(resolveRoute(parsePath('/essay-lab/essays/42'), student), { page: 'essay_lab', params: { essayId: 42 } });
  assert.deepEqual(resolveRoute(parsePath('/students/15'), student), { page: 'dashboard', params: {} });
  assert.deepEqual(resolveRoute(parsePath('/students/15'), counselor), { page: 'students', params: { studentId: 15 } });
  assert.deepEqual(resolveRoute(parsePath('/essay-lab'), counselor), { page: 'dashboard', params: {} });
  assert.deepEqual(resolveRoute(parsePath('/platform/audit'), counselor), { page: 'dashboard', params: {} });
  assert.deepEqual(resolveRoute(parsePath('/family/tasks'), parent), { page: 'parent_tasks', params: {} });
  assert.deepEqual(resolveRoute(parsePath('/family/tasks'), teacher), { page: 'dashboard', params: {} });
  assert.deepEqual(resolveRoute(parsePath('/programs'), organization), { page: 'dashboard', params: {} });
  assert.deepEqual(resolveRoute(null, student), { page: 'dashboard', params: {} });
  assert.deepEqual(resolveRoute(null, admin), { page: 'admin_dashboard', params: {} });
  // Screen time is open to every role.
  for (const user of [student, counselor, teacher, organization, admin]) assert.ok(reachablePages(user).has('screen_time'));
  assert.equal(reachablePages(null).size, 0);
});

test('product admins follow staff links to their own copy of the page', () => {
  assert.deepEqual(resolveRoute(parsePath('/students/15'), admin), { page: 'admin_students', params: { studentId: 15 } });
  assert.deepEqual(resolveRoute(parsePath('/dashboard'), admin), { page: 'admin_dashboard', params: {} });
  assert.deepEqual(resolveRoute(parsePath('/essay-lab/essays/3'), admin), { page: 'admin_dashboard', params: {} });
  const superuser = { role: 'student', is_superuser: true };
  assert.equal(homePage(superuser), 'admin_dashboard');
  assert.ok(navigationFor(superuser).includes('admin_audit'));
});

test('pages a role cannot open are refused before navigating', () => {
  // Parents have no screen-time page, so the dashboard shortcut stays hidden.
  assert.equal(canOpenPage('screen_time', parent), false);
  for (const user of [student, counselor, teacher, organization, admin]) assert.equal(canOpenPage('screen_time', user), true);
  assert.equal(canOpenPage('essay_lab', counselor), false);
  assert.equal(canOpenPage('essay_lab', student), true);
  assert.equal(canOpenPage('dashboard', null), false);
  assert.equal(openablePage('students', admin), 'admin_students');
  assert.equal(openablePage('essay_lab', admin), null);
});

test('every navigation entry has a path', () => {
  for (const user of [student, counselor, teacher, parent, organization, admin]) {
    for (const page of navigationFor(user)) assert.ok(PAGE_PATHS[page], `${user.role}: ${page}`);
  }
});

test('the post-login destination is limited to workspace paths on this site', () => {
  assert.equal(safeNextPath('/essay-lab/essays/42'), '/essay-lab/essays/42');
  assert.equal(safeNextPath('/programs?type=national&q=math'), '/programs?type=national&q=math');
  assert.equal(safeNextPath('/programs/'), '/programs');
  for (const bad of [null, '', 'programs', '//evil.example/programs', '/\\evil.example', 'https://evil.example/dashboard', '/nope', '/login', '/', 'javascript:alert(1)']) {
    assert.equal(safeNextPath(bad), null, String(bad));
  }
  assert.equal(loginPath('/essay-lab/essays/42'), '/login?next=%2Fessay-lab%2Fessays%2F42');
  assert.equal(loginPath('/nope'), '/login');
  assert.equal(new URLSearchParams(loginPath('/programs?type=national').split('?')[1]).get('next'), '/programs?type=national');
});

test('public pages: landing, /login and the old #/login link', () => {
  assert.equal(publicPageFor('/'), 'landing');
  assert.equal(publicPageFor('/', '#journey'), 'landing');
  assert.equal(publicPageFor('/', '#/login'), 'login');
  assert.equal(publicPageFor('/login'), 'login');
  assert.equal(publicPageFor('/login/'), 'login');
  assert.equal(publicPageFor('/dashboard'), null);
});

test('query updates keep foreign keys and drop defaults', () => {
  assert.equal(withQuery('?lang=ru', { type: 'national', q: '  math ' }), '?lang=ru&type=national&q=math');
  assert.equal(withQuery('?type=national&lang=ru', { type: 'all' }, { type: 'all' }), '?lang=ru');
  assert.equal(withQuery('', { open: false }, { open: true }), '?open=0');
  assert.equal(withQuery('?open=0', { open: true }, { open: true }), '');
  assert.equal(withQuery('?aid=1', { aid: false }, { aid: false }), '');
  assert.equal(withQuery('', { q: '' }), '');
});

test('the store is shown locked to students and cannot be opened', () => {
  assert.ok(navigationFor(student).includes('store'), 'still listed in the sidebar');
  assert.equal(isPageLocked('store', student), true);
  assert.equal(canOpenPage('store', student), false);
  assert.equal(openablePage('store', student), null);
  assert.deepEqual(resolveRoute(parsePath('/store'), student), { page: 'dashboard', params: {} });
  assert.equal(buildPath(resolveRoute(parsePath('/store/'), student)), '/dashboard');
  assert.ok(!reachablePages(student).has('store'));
  // Staff and product admins are unaffected.
  for (const user of [counselor, teacher, parent, organization, admin, { id: 9, role: 'student', is_superuser: true }]) {
    assert.equal(isPageLocked('store', user), false);
    assert.equal(lockedPages(user).size, 0);
  }
  assert.equal(lockedPages(null).size, 0);
});

test('roadmap tabs: links open the requested tab, unknown ones the role default', () => {
  assert.equal(buildPath({ page: 'roadmap', params: { tab: 'tasks' } }), '/roadmap/tasks');
  assert.deepEqual(resolveRoute(parsePath('/roadmap/tasks'), student), { page: 'roadmap', params: { tab: 'tasks' } });
  assert.equal(roadmapTab('tasks', false), 'tasks');
  assert.equal(roadmapTab(undefined, false), 'path');
  assert.equal(roadmapTab('missions', false), 'path');
  assert.equal(roadmapTab(undefined, true), 'missions');
  assert.equal(roadmapTab('path', true), 'missions');
  assert.equal(roadmapTab('timeline', true), 'timeline');
  assert.equal(parsePath('/roadmap/secret'), null);
});

test('profile answers are edited on Student Center cards; /profile leads there', () => {
  assert.deepEqual(resolveRoute(parsePath('/profile'), student), { page: 'student_center', params: {} });
  assert.equal(buildPath(resolveRoute(parsePath('/profile'), student)), '/student-center');
  assert.deepEqual(resolveRoute(parsePath('/profile'), counselor), { page: 'dashboard', params: {} });
  assert.ok(!reachablePages(student).has('profile'));
  assert.equal(buildPath({ page: 'student_center', params: { edit: 'goal' } }), '/student-center?edit=goal');
  assert.equal(buildPath({ page: 'student_center', params: { edit: 'goal', tab: 'documents' } }), '/student-center?edit=goal');
  assert.equal(buildPath({ page: 'student_center', params: { edit: 'nope' } }), '/student-center');
});
