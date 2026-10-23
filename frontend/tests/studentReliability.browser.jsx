// Open /tests/studentReliability.browser.html on the local Vite server.
// Real components/hooks use deterministic dummy API responses; no live API
// request is permitted. This entry is excluded from the production build.
import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import App from '../src/App';
import { CollegeSearchPage } from '../src/pages/CollegeSearchPage';
import { ApplicationsPortalPage } from '../src/pages/ApplicationsPortalPage';
import { ApplicationPlan } from '../src/components/ApplicationPlan';
import { CounselorEssayReview } from '../src/pages/CounselorEssayReview';
import CommentsPanel from '../src/essayLab/CommentsPanel';
import SubmitToTask from '../src/essayLab/SubmitToTask';
import EssayTaskStatus, { EssayTaskStatusRows } from '../src/essayLab/EssayTaskStatus';
import { TaskEssayAttachment } from '../src/components/taskEssays';
import { ResourceForm } from '../src/pages/ResourceSection';
import { IeltsFields, SatFields, TestScoreSummary } from '../src/components/testScores';
import { testScoresPayload, validateTestScores } from '../src/lib/testScores';
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
import '../src/essayLab/essayLab.css';
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
const submittedEssay = { id: 71, title: 'My application essay', word_count: 340, shared_with_counselor: true, shared_at: '2026-10-20T10:00:00Z', counselor_access: 'comment', can_comment: true, is_owner: true };
let reviewApproved = false, reviewHistory = false;
const historicalThread = { id: 10, kind: 'thread', tab: 1, status: 'resolved', anchored: true, quote: 'My application essay', comments: [{ id: 2, body: 'Historical feedback remains visible.', author_name: 'Fixture Counselor' }] };
const reviewThread = { id: 9, kind: 'thread', tab: 1, status: 'open', quote: 'My application essay', anchored: true, author_name: 'Fixture Counselor', created_at: '2026-10-20T12:10:00Z', comments: [{ id: 1, body: 'Explain how this experience changed your plans.', by_me: true, author_name: 'Fixture Counselor', created_at: '2026-10-20T12:10:00Z' }] };
const reviewFixture = () => ({ id: 71, title: submittedEssay.title, status: reviewApproved ? 'approved' : 'reviewing', capabilities: reviewApproved ? ['view'] : ['view', 'comment'], student_name: 'Fixture Student', tabs: [{ id: 1, title: 'Personal statement', word_count: 340 }], tab: { id: 1, doc: { type: 'doc', content: [{ type: 'paragraph', attrs: { bid: 'p1' }, content: [{ type: 'text', text: 'My application essay' }] }] } }, threads: reviewHistory ? [reviewThread, historicalThread] : [reviewThread], suggestions: [] });
const collegeUniversity = { id: 11, name: 'Riverstone University', city: 'Riverton', country: 'Testland', website: 'https://university.test/', qs_data: {}, programs: [{ id: 3, name: 'Computer Science', canonical_major: 'Computer Science', application_deadline: '2027-01-01', scholarship_deadline: '2026-12-01', application_url: 'https://apply.university.test/cs', source_url: 'https://university.test/computer-science' }] };
const collegeData = { students: [profile], applications: [], essays: [], documents: [], recommendations: [], scholarships: [] };
let collegeResearchReady = false;
const incompleteResearch = { ready: false, profile_snapshot: {}, questions: [{ field: 'target_major', label: 'Target major', type: 'text', placeholder: 'Computer Science' }] };
const freshApplication = () => ({ id: 8, student: 901, university: 11, university_detail: collegeUniversity, program: 'Computer Science', tier: 'target', status: 'shortlisted', deadline: null, scholarship_deadline: null, application_portal_url: '', notes: '', status_history: [] });
let plannedApplication = freshApplication();
const applicationWrites = [], essayLinks = [];
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
  if (path === '/college-research/') return response(collegeResearchReady ? { ready: true, questions: [], profile_snapshot: { gpa: 4, sat_score: 1500, ielts_score: 7, target_major: 'Computer Science', budget_usd: 2000 } } : incompleteResearch);
  if (path === '/college-search/') return response({ results: [collegeUniversity], count: 1, next: null });
  if (path === '/universities/11/') return response(collegeUniversity);
  if (path === '/applications/8/' && method === 'PATCH') {
    const payload = JSON.parse(options.body);
    applicationWrites.push(payload);
    const history = payload.status && payload.status !== plannedApplication.status ? [{ id: applicationWrites.length, status: payload.status, created_at: new Date().toISOString() }, ...plannedApplication.status_history] : plannedApplication.status_history;
    plannedApplication = { ...plannedApplication, ...payload, status_history: history };
    return response(plannedApplication);
  }
  if (path === '/essays/71/' && method === 'PATCH') { const payload = JSON.parse(options.body); essayLinks.push(payload); return response({ ...submittedEssay, ...payload }); }
  if (path === '/tasks/1/' && method === 'PATCH') { taskSubmission = JSON.parse(options.body); if (taskSubmission.submission_essay) taskSubmission.submission_essay_detail = submittedEssay; if (taskSubmission.status === 'submitted') taskSubmission.submitted_at = '2026-10-20T10:00:00Z'; return response({ id: 1, ...taskSubmission }); }
  if (path === '/tasks/') return tasksBroken ? unavailable('Tasks unavailable') : response(page([{ id: 1, student: 901, title: taskTitle, description: 'Prepare a written response for your counselor.', due_date: '2030-11-01', status: 'todo', priority: 'medium', is_self_assigned: false, ...taskSubmission }, { id: 2, student: 901, title: 'My personal revision plan', due_date: '2030-11-02', priority: 'low', status: 'todo', is_self_assigned: true }].filter((task) => !url.searchParams.has('submission_essay') || String(task.submission_essay) === url.searchParams.get('submission_essay'))));
  if (path === '/essay-lab/review/essays/71/') return response(reviewFixture());
  if (path === '/essays/71/') return response({ id: 71, title: submittedEssay.title, status: reviewApproved ? 'approved' : 'reviewing', version: 1 });
  if (path === '/essays/') {
    const snapshot = page(essayRows);
    if (delayEssayRead) { delayEssayRead = false; await new Promise((resolve) => { releaseEssayRead = resolve; }); }
    return response(snapshot);
  }
  if (path === '/essay-lab/essays/' && method === 'GET') return response([submittedEssay]);
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
function CollegeProfileProbe({ initialId = null }) {
  const [universityId, setUniversityId] = useState(initialId);
  return <div id="college-profile-scroll" style={{ height: 420, overflow: 'auto' }}><CollegeSearchPage data={collegeData} query="" universityId={universityId} reload={noop} notify={noop} setPage={(_page, route) => setUniversityId(route?.universityId ?? null)} /></div>;
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

function EssaySubmissionProbe({ beforeSubmit, onSubmitted }) {
  const [task, setTask] = useState(null);
  return <div className="essay-lab">
    <SubmitToTask essay={submittedEssay} beforeSubmit={beforeSubmit} onSubmitted={(saved) => { setTask(saved); onSubmitted(saved); }} notify={noop} />
    <EssayTaskStatus essayId={submittedEssay.id} submittedTask={task} />
  </div>;
}

function IeltsProbe() {
  const [form, setForm] = useState({ ielts_status: 'taken', ielts_listening: '8.5', ielts_reading: '7.5', ielts_writing: '6', ielts_speaking: '5.5', ielts_score: '7', ielts_test_date: '2026-03-14', ielts_attempts: '2' });
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const payload = testScoresPayload(form);
  return <main style={{ maxWidth: 1100, margin: '24px auto', padding: 24 }}>
    <IeltsFields form={form} update={update} />
    <TestScoreSummary student={payload} />
    <output id="ielts-errors">{Object.keys(validateTestScores(form)).join(',')}</output>
  </main>;
}

function SatProbe({ initialDate = '' }) {
  const [form, setForm] = useState({ sat_status: 'taken', sat_reading: '800', sat_math: '670', sat_attempts: '1', sat_test_date: initialDate });
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const payload = testScoresPayload(form);
  return <main className="student-onboarding">
    <form onSubmit={(event) => event.preventDefault()}>
      <div className="onboarding-tests"><SatFields form={form} update={update} /></div>
      <output id="sat-payload" hidden>{JSON.stringify(payload)}</output>
    </form>
  </main>;
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
  if (params.get('preview-only') === '1') {
    setLanguage(language);
    output.hidden = true;
    if (params.get('preview') === 'sat-mobile') {
      await mount(<iframe title="SAT mobile preview" src="/tests/studentReliability.browser.html?preview=sat&preview-only=1&language=uz" style={{ display: 'block', width: 390, maxWidth: '100%', height: 1000, border: 0, margin: '0 auto' }} />);
    } else {
      await mount(<SatProbe initialDate={params.get('legacy') === '1' ? '2026-09-19' : ''} />);
    }
    return;
  }
  await api.login('fixture', 'fixture-password');
  await check('IELTS distinguishes full retakes and One Skill Retake, recomputes bands and clears hidden metadata', async () => {
    await mount(<IeltsProbe />);
    const choose = async (name, value) => {
      const control = document.querySelector(`select[name="${name}"]`);
      assert(control, 'Missing IELTS question: ' + name);
      control.value = value;
      control.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise((resolve) => requestAnimationFrame(resolve));
    };
    await choose('ielts_result_type', 'one_skill_retake');
    assert(document.querySelector('input[name="ielts_retake_date"]'), 'Retake date is missing');
    await choose('ielts_retake_skill', 'speaking');
    await choose('ielts_speaking', '7.5');
    assert(document.querySelector('select[name="ielts_score"]').value === '7.5', 'Overall does not follow the updated section');
    assert(document.querySelector('.test-score-note')?.textContent.includes('Speaking'), 'Summary hides the retaken skill');
    await choose('ielts_result_type', 'full_retake');
    assert(!document.querySelector('select[name="ielts_retake_skill"]'), 'Full test asks for a retaken skill');
    assert(!document.querySelector('#ielts-errors').textContent, 'Full retake has unexpected errors');
    await choose('ielts_result_type', 'one_skill_retake');
    assert(document.querySelector('select[name="ielts_retake_skill"]').value === '', 'Hidden skill leaked into another retake');
  });

  await check('SAT uses official past/future options and preserves saved special-session dates', async () => {
    const choose = async (name, value) => {
      const control = document.querySelector(`select[name="${name}"]`);
      assert(control, 'Missing SAT question: ' + name);
      control.value = value;
      control.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise((resolve) => requestAnimationFrame(resolve));
    };
    const options = () => [...document.querySelectorAll('select[name="sat_test_date"] option')].map((option) => option.value);
    const payload = () => JSON.parse(document.querySelector('#sat-payload').textContent);
    await mount(<SatProbe />);
    assert(options().includes('2026-09-12'), 'Actual September administration missing');
    assert(!options().includes('2026-09-19'), 'Arbitrary September date is offered');
    assert(!options().includes('2026-11-07'), 'Future test offered for an existing score');
    assert(!document.querySelector('input[type="date"]'), 'Arbitrary calendar is the default');
    const dateControl = document.querySelector('select[name="sat_test_date"]');
    const attemptsControl = document.querySelector('input[name="sat_attempts"]');
    assert(dateControl.offsetHeight === attemptsControl.offsetHeight && dateControl.offsetHeight >= 46, 'SAT date lost the form control styling');
    await choose('sat_test_date', '2026-09-12');
    assert(payload().sat_test_date === '2026-09-12' && document.querySelector('.test-score-total b').textContent === '1470', 'Selected date/score not saved to payload');
    await choose('sat_status', 'scheduled');
    assert(!options().includes('2026-09-12') && options().includes('2026-11-07'), 'Booking options are not future administrations');
    assert(document.querySelector('input[name="sat_test_date_custom"]').value === '2026-09-12', 'Changing status silently rewrote the saved date');
    await choose('sat_test_date', '2026-11-07');
    assert(payload().sat_test_date === '2026-11-07', 'Booking payload dropped the selected date');
    assert(!document.querySelector('input[type="date"]'), 'Custom calendar stayed after selecting an official date');
    await mount(<SatProbe initialDate="2026-09-19" />);
    assert(document.querySelector('select[name="sat_test_date"]').value === 'other', 'Saved exception has no explicit fallback');
    assert(document.querySelector('input[name="sat_test_date_custom"]').value === '2026-09-19', 'Saved nonstandard date changed');
    assert(payload().sat_test_date === '2026-09-19', 'Saved exception not preserved in payload');
    assert(document.querySelector('input[name="sat_test_date_custom"]').closest('.sat-date-question'), 'Custom date breaks out of its form column');
    if (window.innerWidth > 820) {
      const dateTop = document.querySelector('select[name="sat_test_date"]').getBoundingClientRect().top;
      const attemptsTop = document.querySelector('input[name="sat_attempts"]').getBoundingClientRect().top;
      assert(Math.abs(dateTop - attemptsTop) < 1, 'Custom date pushes the attempts field out of alignment');
    }
    await choose('sat_test_date', '2026-09-12');
    assert(!document.querySelector('input[type="date"]'), 'Cannot switch from a special session to an official date');
  });

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
    const submit = [...document.querySelectorAll('.record-list button')].find((button) => button.textContent.includes('Submit response'));
    assert(submit, 'Assigned task has no submit action');
    const panels = [...document.querySelectorAll('.panel')];
    const assignedPanel = panels.find((panel) => panel.querySelector('h2')?.textContent === 'Assigned tasks');
    const personalPanel = panels.find((panel) => panel.querySelector('h2')?.textContent === 'My personal tasks');
    assert(assignedPanel?.textContent.includes(taskTitle) && !assignedPanel.textContent.includes('My personal revision plan'), 'Assigned panel mixes personal tasks');
    assert(personalPanel?.textContent.includes('My personal revision plan') && !personalPanel.textContent.includes(taskTitle), 'Personal panel mixes counselor tasks');
    assert(!assignedPanel.querySelector('.icon-button'), 'Assigned task exposes student edit or delete controls');
    submit.click();
    await waitFor(() => document.querySelector('textarea[name="student_response"]'));
    assert(!document.querySelector('form')?.textContent.includes('Personal development task'), 'Counselor task was described as a personal task');
    const answer = document.querySelector('textarea[name="student_response"]');
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(answer, 'Here is my completed assignment.');
    answer.dispatchEvent(new Event('input', { bubbles: true }));
    assert(!document.querySelector('select[name="status"]'), 'Student can control an assigned task status');
    answer.form.requestSubmit();
    await waitFor(() => taskSubmission.status === 'submitted');
    assert(taskSubmission.student_response === 'Here is my completed assignment.', 'Response text was not submitted');
    assert(!('title' in taskSubmission) && !('student' in taskSubmission), 'Student changed counselor-owned assignment fields');
    await waitFor(() => document.querySelector('.record-list')?.textContent.includes('Here is my completed assignment.'));
  });
  await check('An Essay Lab essay submits to an assigned task only after all tabs save; counselors can open it for comments', async () => {
    taskSubmission = {};
    let canSave = false, submitted = null;
    await mount(<EssaySubmissionProbe beforeSubmit={async () => canSave} onSubmitted={(task) => { submitted = task; }} />);
    click('[aria-label="Submit essay to a task"]');
    await waitFor(() => document.querySelector('select[name="task"]'));
    const picker = document.querySelector('select[name="task"]');
    assert(!picker.textContent.includes('My personal revision plan'), 'Personal tasks appear as counselor assignments');
    picker.value = '1';
    picker.dispatchEvent(new Event('change', { bubbles: true }));
    await new Promise((resolve) => requestAnimationFrame(resolve));
    picker.form.requestSubmit();
    await waitFor(() => document.querySelector('[role="alert"]')?.textContent.includes('Save all essay tabs'));
    assert(!taskSubmission.submission_essay, 'Unsaved essay was submitted');
    canSave = true;
    picker.form.requestSubmit();
    await waitFor(() => submitted?.submission_essay === 71);
    assert(submitted.status === 'submitted', 'Essay-only response was not submitted');
    await waitFor(() => document.querySelector('.el-submission-success'));
    assert(document.querySelector('.el-submission-success').textContent.includes(taskTitle), 'Success confirmation does not name the task');
    assert(document.querySelector('.el-submission-success').textContent.includes('Awaiting counselor review'), 'Success confirmation does not explain what happens next');
    click('.el-dialog-foot button');
    await waitFor(() => !document.querySelector('[role="dialog"]'));
    assert(document.querySelector('.el-task-submission')?.textContent.includes('Awaiting counselor review'), 'Persistent submission status is missing');
    await mount(<EssayTaskStatus essayId={71} />);
    await waitFor(() => document.querySelector('.el-task-submission'));
    assert(document.querySelector('.el-task-submission').textContent.includes(taskTitle), 'Reload lost the submitted task');
    taskSubmission.status = 'approved';
    await mount(<EssayTaskStatus essayId={71} />);
    await waitFor(() => document.querySelector('.el-task-submission')?.textContent.includes('Approved by counselor'));

    await mount(<TaskEssayAttachment task={{ ...submitted, submission_essay_detail: { ...submittedEssay, is_owner: false } }} />);
    const link = document.querySelector('a');
    assert(link?.textContent.includes('Open essay and comment'), 'Counselor has no essay comment entry point');
    assert(link.getAttribute('href') === '/essays/71', 'Counselor is sent to the student-only editor');
  });
  await check('Task response accepts an Essay Lab essay without requiring an external URL or written answer', async () => {
    taskSubmission = {};
    let saved = false;
    await mount(<ResourceForm resource="tasks" item={{ id: 1, student: 901, title: taskTitle, status: 'todo', is_self_assigned: false }} user={user} data={{ students: [profile] }} notify={noop} onClose={noop} onSaved={() => { saved = true; }} />);
    await waitFor(() => document.querySelector('select[name="submission_essay"] option[value="71"]'));
    const picker = document.querySelector('select[name="submission_essay"]');
    picker.value = '71';
    picker.dispatchEvent(new Event('change', { bubbles: true }));
    await new Promise((resolve) => requestAnimationFrame(resolve));
    picker.form.requestSubmit();
    await waitFor(() => saved);
    assert(taskSubmission.submission_essay === 71 && taskSubmission.status === 'submitted', 'Task form dropped the attached essay');
    assert(!taskSubmission.submission_url && !taskSubmission.student_response, 'Essay-only response needs unrelated fields');
    assert(!document.querySelector('select[name="status"]'), 'Attachment flow lets a student manage the assignment');
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
  await check('Complete profile closes the tier picker and focuses the research form from results and university details', async () => {
    for (const origin of ['results', 'university', 'university-link']) {
      await mount(<CollegeProfileProbe initialId={origin === 'results' ? null : 11} />);
      await waitFor(() => origin === 'results' ? document.querySelector('.uni-action button') : document.querySelector('.fit-missing button'));
      if (origin === 'university-link') click('.fit-missing button');
      else {
        click(origin === 'results' ? '.uni-action button' : '.university-actions button.primary');
        await waitFor(() => document.querySelector('.tier-picker .link-button'));
        click('.tier-picker .link-button');
      }
      await waitFor(() => !document.querySelector('[role="dialog"]') && document.activeElement === document.querySelector('.research-question-grid input'));
      const field = document.activeElement.getBoundingClientRect(), scroller = document.querySelector('#college-profile-scroll').getBoundingClientRect();
      assert(field.top >= scroller.top && field.bottom <= scroller.bottom, 'Profile field remains outside the workspace scroll viewport');
    }
  });
  await check('College Search has no budget field or personal budget filter, including previously saved budgets', async () => {
    collegeResearchReady = true;
    await mount(<CollegeProfileProbe />);
    await waitFor(() => document.querySelector('.profile-strip'));
    assert(!document.querySelector('.profile-strip').textContent.includes('Budget'), 'Saved budget still appears in the profile strip');
    click('.college-filters-toggle');
    await waitFor(() => document.querySelector('#college-advanced-filters'));
    assert(!document.querySelector('#college-advanced-filters').textContent.includes('Within budget'), 'Personal budget filter remains');
    assert(!document.querySelector('input[name="budget_usd"]'), 'Budget is still requested');
    collegeResearchReady = false;
  });
  await check('Application plans save separately, link essays, open real portals and require explicit submission confirmation', async () => {
    plannedApplication = freshApplication(); applicationWrites.length = 0; essayLinks.length = 0;
    const data = { ...collegeData, applications: [plannedApplication], essays: [{ ...submittedEssay, application: null, status: 'draft' }] };
    await mount(<ApplicationPlan application={plannedApplication} data={data} onClose={noop} onSaved={noop} setPage={noop} notify={noop} />);
    assert(document.querySelector('button[value="submitted"]').disabled, 'Submission is available without confirmation');
    [...document.querySelectorAll('.application-plan-links button')].find((button) => button.textContent === 'Use published dates and portal').click();
    await waitFor(() => document.querySelector('input[name="deadline"]').value === '2027-01-01');
    assert(document.querySelector('a[href="https://apply.university.test/cs"]'), 'Published application portal is not actionable');
    assert(plannedApplication.status === 'shortlisted', 'Looking up a portal marked the application submitted');
    click('button[value="save"]');
    await waitFor(() => applicationWrites.length === 1 && !document.querySelector('button[value="save"]').disabled);
    assert(plannedApplication.status === 'shortlisted' && !applicationWrites[0].status, 'Saving a plan changed the submission status');
    const picker = document.querySelector('.application-plan-link-essay select');
    picker.value = '71'; picker.dispatchEvent(new Event('change', { bubbles: true }));
    await new Promise((resolve) => requestAnimationFrame(resolve));
    click('.application-plan-link-essay button');
    await waitFor(() => essayLinks.length === 1 && document.querySelector('.application-plan-essays'));
    assert(essayLinks[0].application === 8, 'Essay did not link to this application');
    click('button[value="applying"]');
    await waitFor(() => plannedApplication.status === 'applying' && !document.querySelector('button[value="save"]').disabled);
    click('.application-plan-confirm input');
    await waitFor(() => !document.querySelector('button[value="submitted"]').disabled);
    click('button[value="submitted"]');
    await waitFor(() => plannedApplication.status === 'submitted' && !document.querySelector('.application-plan-confirm'));
    assert(document.querySelector('.application-plan-history').textContent.includes('Submitted'), 'Submission has no recorded history');
    const writes = applicationWrites.length;
    await mount(<ApplicationsPortalPage data={{ ...data, applications: [freshApplication()] }} query="" reload={noop} notify={noop} setPage={noop} />);
    click('.card-menu > button');
    await waitFor(() => document.querySelector('.card-menu-list button'));
    [...document.querySelectorAll('.card-menu-list button')].find((button) => button.textContent === 'Submitted').click();
    await waitFor(() => document.querySelector('.application-plan-confirm'));
    assert(applicationWrites.length === writes && document.querySelector('button[value="submitted"]').disabled, 'Board status move bypassed confirmation');
  });
  await check('Both roles show historical comments together, use Add comment, and have no resolve or reopen workflow', async () => {
    reviewApproved = false;
    reviewHistory = true;
    await mount(<CounselorEssayReview essayId={71} notify={noop} onBack={noop} />);
    await waitFor(() => document.querySelectorAll('.cer-thread').length === 2);
    assert(document.querySelector('.cer-side').textContent.includes(historicalThread.comments[0].body), 'Previously resolved counselor feedback is hidden');
    assert(!document.querySelector('.cer-resolved, .cer-thread.is-resolved'), 'Counselor still groups resolved comments');
    const actions = [...document.querySelectorAll('.cer-thread-actions button')];
    assert(actions.length === 2 && actions.every((button) => button.textContent === 'Add comment'), 'Counselor still has Reply, Resolve or Reopen');
    await mount(<div className="essay-lab"><CommentsPanel items={[reviewThread, historicalThread]} loaded acceptAll={[]} onSelect={noop} onClose={noop} onReply={async () => true} /></div>);
    const buttons = [...document.querySelectorAll('.el-fb-actions button')];
    assert(buttons.length === 2 && buttons.every((button) => button.textContent === 'Add comment'), 'Student still has Reply, Resolve or Reopen');
    assert(!document.querySelector('.el-fb-toggle, .is-resolved'), 'Student still hides historically resolved feedback');
    buttons[1].click();
    await waitFor(() => document.querySelector('.el-fb-reply'));
    assert(document.querySelector('.el-fb-reply textarea').getAttribute('placeholder') === 'Write your comment', 'Comment form still uses reply wording');
    reviewHistory = false;
  });
  await check('Approved essays retain comments but hide all feedback controls for counselor and student', async () => {
    reviewApproved = false;
    await mount(<CounselorEssayReview essayId={71} notify={noop} onBack={noop} />);
    await waitFor(() => document.querySelector('.cer-thread-actions'));
    click('.cer-thread-actions button');
    await waitFor(() => document.querySelector('.cer-reply'));
    reviewApproved = true;
    // Remount represents a fresh open of an approved essay.
    await mount(<CounselorEssayReview essayId={71} notify={noop} onBack={noop} />);
    await waitFor(() => document.querySelector('.cer-approved'));
    assert(document.querySelector('.cer-comment-row')?.textContent.includes(reviewThread.comments[0].body), 'Approval hid previous feedback');
    assert(!document.querySelector('.cer-compose, .cer-thread-actions, .cer-reply, .cer-decide textarea'), 'Approved essay still accepts feedback');
    assert(![...document.querySelectorAll('h2')].some((node) => node.textContent === 'Your feedback'), 'Approved essay still shows feedback composer');
    const panel = (readOnly) => <div className="essay-lab"><CommentsPanel readOnly={readOnly} items={[reviewThread]} loaded acceptAll={[]} onSelect={noop} onClose={noop} onReply={noop} /></div>;
    await mount(panel(false));
    click('.el-fb-actions button');
    await waitFor(() => document.querySelector('.el-fb-reply'));
    root.render(panel(true));
    await waitFor(() => !document.querySelector('.el-fb-reply'));
    assert(!document.querySelector('.el-fb-actions'), 'Student can still reply or resolve approved feedback');
    assert(document.querySelector('.el-fb-body')?.textContent === reviewThread.comments[0].body, 'Student lost feedback history');
  });
  // Keep the selected real component visible for viewport/theme checks.
  setLanguage(language);
  if (params.get('preview') === 'snapshot') {
    await mount(<SnapshotPreview />);
  } else if (params.get('preview') === 'dashboard') {
    tasksBroken = true;
    await mount(<App />);
    await waitFor(() => document.querySelector('.dashboard-tile-tasks [role="alert"]'));
  } else if (params.get('preview') === 'ielts') {
    await mount(<IeltsProbe />);
  } else if (params.get('preview') === 'sat') {
    await mount(<SatProbe initialDate={params.get('legacy') === '1' ? '2026-09-19' : ''} />);
  } else if (params.get('preview') === 'submission-success') {
    taskSubmission = {};
    await mount(<EssaySubmissionProbe beforeSubmit={async () => true} onSubmitted={noop} />);
  } else if (params.get('preview') === 'submission-status') {
    await mount(<div className="essay-lab" style={{ maxWidth: 1100, margin: '40px auto' }}><EssayTaskStatusRows tasks={[{ id: 1, title: 'Personal statement — birinchi qoralama', status: 'submitted', submitted_at: '2026-10-20T10:00:00Z' }]} onComments={noop} /></div>);
  } else if (params.get('preview') === 'task-essay') {
    await mount(<div style={{ maxWidth: 900, margin: '40px auto', padding: 24 }}><h2>Essay Lab → Task</h2><TaskEssayAttachment task={{ submission_essay: 71, submission_essay_detail: { ...submittedEssay, is_owner: false } }} /></div>);
  } else if (params.get('preview') === 'task-form') {
    await mount(<ResourceForm resource="tasks" item={{ id: 1, student: 901, title: 'Finish PS', status: 'todo', is_self_assigned: false }} user={user} data={{ students: [profile] }} notify={noop} onClose={noop} onSaved={noop} />);
    await waitFor(() => document.querySelector('select[name="submission_essay"] option[value="71"]'));
  } else if (params.get('preview') === 'application-plan') {
    await mount(<ApplicationPlan application={freshApplication()} data={{ ...collegeData, essays: [{ ...submittedEssay, application: null, status: 'draft' }] }} onClose={noop} onSaved={noop} setPage={noop} notify={noop} />);
  } else if (params.get('preview') === 'college-profile') {
    collegeResearchReady = params.get('ready') === '1';
    await mount(<CollegeProfileProbe />);
  } else if (params.get('preview') === 'student-comments') {
    const thread = { ...reviewThread, comments: [{ ...reviewThread.comments[0], by_me: false, author_name: 'Firdaus Jurayev', created_at: new Date().toISOString() }] };
    await mount(<div className="essay-lab" style={{ display: 'flex', justifyContent: 'center', height: 520, maxWidth: 400, margin: '24px auto' }}><CommentsPanel readOnly={params.get('approved') === '1'} items={[thread]} activeKey="thread:9" loaded acceptAll={[]} onSelect={noop} onClose={noop} onReply={async () => true} /></div>);
  } else if (params.get('preview') === 'essay-review') {
    reviewApproved = params.get('approved') === '1';
    await mount(<div className="app-shell cx-shell" style={{ display: 'block', padding: 24 }}><CounselorEssayReview essayId={71} notify={noop} onBack={noop} /></div>);
    await waitFor(() => document.querySelector('.cer-comment-row'));
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
