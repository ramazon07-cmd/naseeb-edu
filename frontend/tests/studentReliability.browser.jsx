// Open /tests/studentReliability.browser.html on the local Vite server.
// Real components/hooks use deterministic dummy API responses; no live API
// request is permitted. This entry is excluded from the production build.
import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import App from '../src/App';
import { api, request } from '../src/api';
import { setLanguage } from '../src/i18n';
import { THEME_KEY } from '../src/hooks/useTheme';
import { ProgramsPage } from '../src/pages/ProgramsPage';
import { BookingForm, RescheduleForm } from '../src/pages/BookingsPage';
import { NotificationPanel } from '../src/components/NotificationPanel';
import { SnapshotCard } from '../src/components/counselorHome';
import { useWorkspaceData } from '../src/hooks/useWorkspaceData';
import { essayLabApi } from '../src/essayLab/essayLabApi';
import '../src/styles.css';
import '../src/social.css';
import '../src/pages/counselor-home.css';
import '@fontsource-variable/roboto/wght.css';

const fixturePath = location.pathname + location.search;
const params = new URLSearchParams(location.search);
const language = params.get('language') || 'en';
setLanguage('en');
document.documentElement.dataset.theme = params.get('theme') || 'light';
localStorage.setItem(THEME_KEY, document.documentElement.dataset.theme);
localStorage.removeItem('naseeb-dashboard-v1:901');
localStorage.removeItem('naseeb-dashboard-pending-v1:901');
let offset = 0;
const realNow = Date.now;
Date.now = () => realNow() + offset;
const user = { id: 901, role: 'student', username: 'fixture', first_name: 'Fixture', last_name: 'Student', student_profile_complete: true, must_change_password: false, awaiting_confirmation: false, workspace: { read_only: false } };
const profile = { id: 901, user: 901, user_detail: user, level: 1, roadmap_status_counts: {}, roadmap_stars: 0, applications_total: 0, applications_submitted: 0, applications_accepted: 0, achievements_total: 0 };
let tasksBroken = true, savedBroken = true, slotsBroken = true, chatsBroken = true, layoutBroken = false;
let serverLayout = null;
let delayEssayRead = false, releaseEssayRead;
let taskTitle = 'Assigned task', essayRows = [{ id: 1, title: 'Initial essay' }];
let taskSubmission = {};
const calls = [];
const host = { id: 7, first_name: 'Fixture', last_name: 'Counselor', username: 'mentor', role: 'counselor' };
const slot = { id: 71, participant: 7, starts_at: new Date(realNow() + 86400000).toISOString(), duration_minutes: 45, available: true };
const program = { id: 1, title: 'Regression program', provider: 'Fixture school', program_type: 'national', eligible_grades: '10,11', delivery_mode: 'online', category: 'STEM', deadline: '2030-12-01', cost_usd: 0 };
const noop = () => {};
const response = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const unavailable = (detail) => response({ detail }, 403);
const page = (results) => ({ results, count: results.length, next: null });
window.fetch = async (input, options = {}) => {
  const url = new URL(String(input), location.origin);
  if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) throw new Error('Live network request forbidden in this fixture');
  const path = url.pathname.slice(4), method = options.method || 'GET';
  calls.push({ path, method });
  if (path === '/auth/token/' || path === '/auth/token/refresh/') return response({ access: 'fixture.' + btoa(JSON.stringify({ exp: Math.floor(realNow() / 1000) + 86400 })) + '.fixture' });
  if (path === '/users/accounts/me/') return response(user);
  if (path === '/users/accounts/me/dashboard-layout/') {
    if (method === 'PUT') {
      if (layoutBroken) return unavailable('Layout unavailable');
      serverLayout = JSON.parse(options.body).layout;
    }
    return response({ layout: serverLayout });
  }
  if (path === '/students/') return response(page([profile]));
  if (path === '/tasks/1/' && method === 'PATCH') { taskSubmission = JSON.parse(options.body); return response({ id: 1, ...taskSubmission }); }
  if (path === '/tasks/') return tasksBroken ? unavailable('Tasks unavailable') : response(page([{ id: 1, student: 901, title: taskTitle, description: 'Prepare a written response for your counselor.', due_date: '2030-11-01', status: 'todo', priority: 'medium', is_self_assigned: false, ...taskSubmission }]));
  if (path === '/essays/') {
    const snapshot = page(essayRows);
    if (delayEssayRead) { delayEssayRead = false; await new Promise((resolve) => { releaseEssayRead = resolve; }); }
    return response(snapshot);
  }
  if (path === '/essay-lab/essays/' && method === 'POST') { essayRows = [...essayRows, { id: 2, title: 'Created essay' }]; return response(essayRows.at(-1), 201); }
  if (path === '/opportunity-programs/saved/') return savedBroken ? unavailable('Saved list unavailable') : response({ program_ids: [1] });
  if (/^\/opportunity-programs\/1\/save\/$/.test(path)) return response({});
  if (path === '/bookings/participants/') return response([host]);
  if (path === '/bookings/availability/') return slotsBroken ? unavailable('Times unavailable') : response([slot]);
  if (path === '/notifications/summary/') return response({ unread: 0, chats_unread: 0 });
  if (path === '/message-channels/' && url.searchParams.get('unread') === 'true') return chatsBroken ? unavailable('Chats unavailable') : response(page([{ id: 5, display_name: 'Fixture chat', unread_count: 1 }]));
  if (path === '/screen-time/summary/') return response({ today: new Date(realNow()).toISOString().slice(0, 10), own: { today_seconds: 0, period_seconds: 0, daily: [], pages: [] } });
  if (method !== 'GET') return response({});
  return response(page([]));
};

let root;
const output = document.getElementById('results');
const results = [];
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const waitFor = async (check) => {
  const end = realNow() + 10000;
  while (realNow() < end) { if (check()) return; await new Promise((resolve) => setTimeout(resolve, 25)); }
  throw new Error('Timed out waiting for rendered state');
};
const mount = async (element) => {
  root?.unmount();
  root = createRoot(document.getElementById('root'));
  root.render(element);
  await new Promise((resolve) => setTimeout(resolve, 50));
};
const click = (selector) => {
  const button = document.querySelector(selector);
  assert(button, 'Missing button: ' + selector);
  button.click();
};
async function check(name, run) {
  await run();
  results.push('PASS ' + name);
  output.textContent = results.join('\n');
}
function EssayProbe() {
  const { data, ensureLoaded } = useWorkspaceData(user, noop);
  useEffect(() => { ensureLoaded(user, ['essays']); }, [ensureLoaded]);
  return <section>
    <p id="essay-list">{data.essays.map((essay) => essay.title).join(', ')}</p>
    <button id="create-essay" onClick={() => essayLabApi.createEssay({ title: 'Created essay' })}>Create</button>
    <button id="revisit" onClick={() => ensureLoaded(user, ['essays'])}>Revisit</button>
    <button id="autosave" onClick={() => request('/essay-lab/essays/2/autosave/', { method: 'POST', body: '{}' })}>Autosave</button>
  </section>;
}

function SnapshotPreview() {
  const choices = [{ id: 901, name: 'Aziza Karimova' }, { id: 902, name: 'Muhammadali Abdurahmonov' }];
  const [selected, setSelected] = useState(choices[0]);
  const [opened, setOpened] = useState(null);
  const data = {
    name: selected.name, study_goal: selected.id === 901 ? 'Economics' : 'Computer Science', target_countries: ['US', 'Canada'],
    applications: { total: 3, submitted: 0, accepted: 0 }, achievements: 2, open_tasks: 4,
    priorities: [
      { id: 1, title: 'Recommendation letter request', due: '2026-10-12', late: true },
      { id: 2, title: 'IELTS certificate upload', due: '2026-10-14', late: true },
      { id: 3, title: 'Personal Statement 1 — draft', due: '2026-10-18', late: false },
    ],
  };
  return <main style={{ maxWidth: 760, margin: '32px auto', padding: '0 16px', fontFamily: "'Roboto Variable', sans-serif" }}>
    <SnapshotCard choices={choices} selected={selected} onSelect={setSelected} state={{ data, loading: false, error: '' }} onOpenStudent={setOpened} onRetry={noop} />
    {opened && <p role="status">Opened student {opened}</p>}
  </main>;
}

async function run() {
  await api.login('fixture', 'fixture-password');
  await check('Dashboard failure is an error, never completed work; Retry recovers', async () => {
    await mount(<App />);
    await waitFor(() => document.querySelector('.dashboard-tile-tasks [role="alert"]'));
    assert(!document.querySelector('.dashboard-tile-tasks').textContent.includes('All tasks are complete.'), 'Failed tasks shown as complete');
    tasksBroken = false;
    click('.dashboard-tile-tasks [role="alert"] button');
    await waitFor(() => document.querySelector('.dashboard-tile-tasks').textContent.includes('Assigned task'));
  });
  await check('Student focus refresh sees a counselor change and is throttled', async () => {
    taskTitle = 'Updated by counselor';
    offset += 61000;
    window.dispatchEvent(new Event('focus'));
    await waitFor(() => document.querySelector('.dashboard-tile-tasks').textContent.includes(taskTitle));
    const count = calls.filter((call) => call.path === '/tasks/').length;
    window.dispatchEvent(new Event('focus'));
    await new Promise((resolve) => setTimeout(resolve, 100));
    assert(calls.filter((call) => call.path === '/tasks/').length === count, 'Repeated focus caused duplicate reads');
  });
  await check('Dashboard pending layout retries when online returns without reverting the chosen widgets', async () => {
    layoutBroken = true;
    click('.dashboard-heading-actions button');
    await waitFor(() => document.querySelector('.dashboard-customize-modal'));
    click('[data-widget-id="programs"] [aria-label="Hide widget: Programs"]');
    await waitFor(() => document.querySelector('[data-widget-column="hidden"] [data-widget-id="programs"]'));
    click('.dashboard-customize-modal footer .button.primary');
    await waitFor(() => document.querySelector('.compact-dashboard > p[role="status"]'));
    assert(!document.querySelector('.dashboard-tile-programs'), 'Failed save reverted the local choice');
    layoutBroken = false;
    await new Promise((resolve) => setTimeout(resolve, 50));
    window.dispatchEvent(new Event('online'));
    await waitFor(() => !document.querySelector('.compact-dashboard > p[role="status"]'));
    assert(serverLayout?.hidden.includes('programs'), 'Pending layout was not uploaded');
    assert(!document.querySelector('.dashboard-tile-programs'), 'Retry changed the chosen widgets');
  });
  await check('Tasks opens directly with Roadmap locked and sends the student response', async () => {
    history.replaceState({}, '', '/tasks');
    await mount(<App />);
    await waitFor(() => document.querySelector('.record-list')?.textContent.includes(taskTitle));
    assert(document.querySelector('.sidebar [aria-label="Roadmap — Coming soon"]')?.disabled, 'Roadmap was unlocked');
    click('.record-list [aria-label="Edit Tasks"]');
    await waitFor(() => document.querySelector('textarea[name="student_response"]'));
    assert(!document.querySelector('.self-task-note'), 'Counselor task was described as a personal task');
    const answer = document.querySelector('textarea[name="student_response"]');
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(answer, 'Here is my completed assignment.');
    answer.dispatchEvent(new Event('input', { bubbles: true }));
    const status = document.querySelector('select[name="status"]');
    status.value = 'submitted';
    status.dispatchEvent(new Event('change', { bubbles: true }));
    answer.form.requestSubmit();
    await waitFor(() => taskSubmission.status === 'submitted');
    assert(taskSubmission.student_response === 'Here is my completed assignment.', 'Response text was not submitted');
    assert(!('title' in taskSubmission) && !('student' in taskSubmission), 'Student changed counselor-owned assignment fields');
    await waitFor(() => document.querySelector('.record-list')?.textContent.includes('Here is my completed assignment.'));
  });
  await check('Essay Lab create invalidates real workspace state; text autosave stays local', async () => {
    await mount(<EssayProbe />);
    await waitFor(() => document.getElementById('essay-list').textContent.includes('Initial essay'));
    click('#create-essay');
    await waitFor(() => calls.some((call) => call.path === '/essay-lab/essays/' && call.method === 'POST'));
    click('#revisit');
    await waitFor(() => document.getElementById('essay-list').textContent.includes('Created essay'));
    const count = calls.filter((call) => call.path === '/essays/').length;
    click('#autosave');
    await waitFor(() => calls.some((call) => call.path.includes('/autosave/')));
    click('#revisit');
    await new Promise((resolve) => setTimeout(resolve, 100));
    assert(calls.filter((call) => call.path === '/essays/').length === count, 'Autosave refetched workspace essays');
  });
  await check('Essay write during a pending read automatically revalidates after the old response', async () => {
    essayRows = [{ id: 1, title: 'Initial essay' }];
    delayEssayRead = true; releaseEssayRead = null;
    await mount(<EssayProbe />);
    await waitFor(() => releaseEssayRead);
    const creates = calls.filter((call) => call.path === '/essay-lab/essays/' && call.method === 'POST').length;
    click('#create-essay');
    await waitFor(() => calls.filter((call) => call.path === '/essay-lab/essays/' && call.method === 'POST').length > creates);
    await new Promise((resolve) => setTimeout(resolve, 50));
    releaseEssayRead();
    await waitFor(() => document.getElementById('essay-list').textContent.includes('Created essay'));
  });
  await check('My List first-load failure blocks incorrect writes; Retry restores DELETE', async () => {
    await mount(<ProgramsPage data={{ opportunityPrograms: [program] }} query="" search="" navigate={noop} notify={noop} />);
    await waitFor(() => document.querySelector('.program-main [role="alert"]'));
    assert(document.querySelector('[aria-label="Add to My List"]').disabled, 'Unknown saved state allowed a write');
    document.querySelector('.catalog-list-controls button').click();
    await waitFor(() => document.querySelector('.program-results-bar').textContent.includes('My List'));
    assert(!document.querySelector('.program-main').textContent.includes('No saved programs match'), 'Failed saved list shown as empty');
    savedBroken = false;
    click('.program-main [role="alert"] button');
    await waitFor(() => document.querySelector('[aria-label="In My List"]'));
    click('[aria-label="In My List"]');
    await waitFor(() => calls.some((call) => call.path === '/opportunity-programs/1/save/' && call.method === 'DELETE'));
  });
  await check('Booking keeps valid staff when availability fails and retries times', async () => {
    await mount(<BookingForm notify={noop} onClose={noop} onSaved={noop} />);
    await waitFor(() => document.querySelector('.booking-cal-main [role="alert"]'));
    assert(document.querySelector('.booking-cal-side').textContent.includes('Fixture Counselor'), 'Successful staff response lost');
    assert(!document.querySelector('.booking-cal-side').textContent.includes('No available times'), 'Failed availability shown as zero free slots');
    assert(!document.querySelector('.booking-cal-main').textContent.includes("hasn't published"), 'Failed times shown as no published slots');
    slotsBroken = false;
    click('.booking-cal-main [role="alert"] button');
    await waitFor(() => document.querySelector('.booking-cal-time'));
  });
  await check('Reschedule failure has Retry instead of a no-times message', async () => {
    slotsBroken = true;
    await mount(<RescheduleForm booking={{ id: 3, participant: 7, starts_at: new Date(realNow()).toISOString(), availability_slot: 1 }} notify={noop} onClose={noop} onSaved={noop} />);
    await waitFor(() => document.querySelector('.modal [role="alert"]'));
    slotsBroken = false;
    click('.modal [role="alert"] button');
    await waitFor(() => document.querySelector('.booking-cal-time'));
  });
  await check('Unread chat failure is visible and Retry works with unchanged summary', async () => {
    await mount(<NotificationPanel user={user} data={{ messageChannels: [] }} summary={{ unread: 0, chats_unread: 1 }} onOpen={noop} notify={noop} />);
    await waitFor(() => document.querySelector('.notification-panel [role="alert"]'));
    assert(!document.querySelector('.notification-panel').textContent.includes('All caught up'), 'Failed chats shown as all read');
    chatsBroken = false;
    click('.notification-panel [role="alert"] button');
    await waitFor(() => document.querySelector('.notification-panel').textContent.includes('Fixture chat'));
  });
  // Keep the selected real component visible for viewport/theme checks.
  setLanguage(language);
  if (params.get('preview') === 'snapshot') {
    await mount(<SnapshotPreview />);
  } else if (params.get('preview') === 'dashboard') {
    tasksBroken = true;
    await mount(<App />);
    await waitFor(() => document.querySelector('.dashboard-tile-tasks [role="alert"]'));
  } else if (params.get('preview') === 'tasks') {
    history.replaceState({}, '', '/tasks');
    await mount(<App />);
    await waitFor(() => document.querySelector('.record-list')?.textContent.includes(taskTitle));
  } else if (params.get('preview') === 'booking') {
    slotsBroken = true;
    await mount(<BookingForm notify={noop} onClose={noop} onSaved={noop} />);
    await waitFor(() => document.querySelector('.booking-cal-main [role="alert"]'));
  } else if (params.get('preview') === 'notifications') {
    chatsBroken = true;
    await mount(<NotificationPanel user={user} data={{ messageChannels: [] }} summary={{ unread: 0, chats_unread: 1 }} onOpen={noop} notify={noop} />);
    await waitFor(() => document.querySelector('.notification-panel [role="alert"]'));
  } else {
    await mount(<ProgramsPage data={{ opportunityPrograms: [program] }} query="" search="" navigate={noop} notify={noop} />);
    await waitFor(() => !document.querySelector('.program-main [role="alert"]'));
  }
  output.textContent = results.join('\n') + '\nALL BROWSER CHECKS PASSED';
  Date.now = realNow;
  api.forgetSession();
  history.replaceState(null, '', fixturePath);
  document.title = 'Student reliability regression checks';
}
run().catch((error) => { Date.now = realNow; api.forgetSession(); history.replaceState(null, '', fixturePath); output.textContent = results.join('\n') + '\nFAIL ' + error.message; });
