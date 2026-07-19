const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8');
const app = fs.readFileSync(path.join(root, 'frontend/src/App.jsx'), 'utf8');
const api = fs.readFileSync(path.join(root, 'frontend/src/api.js'), 'utf8');
const packageLock = fs.readFileSync(path.join(root, 'frontend/package-lock.json'), 'utf8');
const styles = fs.readFileSync(path.join(root, 'frontend/src/styles.css'), 'utf8');

const requiredViews = [
  'dashboard', 'profile', 'academics', 'portfolio', 'activities', 'recommendations',
  'notifications', 'schools', 'students', 'tasks', 'applications', 'documents',
  'certificates', 'essays', 'achievements', 'meetings', 'messages',
];
const requiredApiMethods = [
  'login', 'me', 'dashboard', 'list', 'create', 'update', 'remove',
  'quickCreateStudent', 'createSchoolAccount', 'markNotificationRead',
  'messageChannels', 'channelMessages', 'messageContacts', 'openDirectChannel',
  'messagingOverview', 'channelMembers', 'joinChannel', 'markChannelRead',
  'addChannelMember', 'removeChannelMember', 'acceptChannelMessage',
  'reportChannelMessage', 'messageReports', 'reviewMessageReport',
  'dismissMessageReport', 'resolveMessageReport',
];

for (const view of requiredViews) {
  if (!app.includes(`${view}:`)) throw new Error(`Missing page metadata: ${view}`);
}
for (const method of requiredApiMethods) {
  if (!api.includes(method)) throw new Error(`Missing API client capability: ${method}`);
}
if (!html.includes('id="root"')) throw new Error('React root is missing.');
if (!packageLock.includes('naseeb-edu-frontend')) throw new Error('npm lockfile is missing or invalid.');
if (!app.includes('function StudentOverview(')) throw new Error('Student 360 profile is missing.');
if (!api.includes('function listAll(') || !api.includes('payload.next')) throw new Error('Paginated API traversal is missing.');
if (!app.includes('Initial password') || !app.includes('minLength="12"')) throw new Error('Strong initial student password input is missing.');
if (!app.includes('VITE_SHOW_DEMO_ACCOUNTS') || !app.includes('SHOW_DEMO_ACCOUNTS &&')) throw new Error('Demo credentials must be explicitly enabled in development.');
if (!app.includes("teacher: 'Teacher'") || !app.includes('isTaskManager')) throw new Error('Teacher-controlled work UI is missing.');
if (!api.includes('approveRoadmapMission')) throw new Error('Roadmap approval API action is missing.');
if (!app.includes('function LevelProgress(') || !api.includes('approveStudentLevel')) throw new Error('XP and teacher-approved leveling UI is missing.');
for (const channelTab of ['Direct', 'Group', 'Community', 'Discussions']) {
  if (!app.includes(`\"${channelTab}\"`)) throw new Error(`Messaging tab missing: ${channelTab}`)
}
if (!app.includes('Post anonymously') || !app.includes('Accept answer')) throw new Error('Anonymous discussions or accepted-answer controls are missing.');
if (!app.includes('COUNSELOR INBOX') || !app.includes('SCHOOL COMMUNICATIONS') || !app.includes('function ChannelMembersModal(')) throw new Error('Counselor and school messaging interfaces are missing.');
if (!app.includes('Assigned students') || !app.includes('School students') || !app.includes('Manage members')) throw new Error('Staff messaging audience and member controls are missing.');
if (!app.includes('function ReportMessageModal(') || !app.includes('function ModerationQueueModal(')) throw new Error('Anonymous report and moderation interfaces are missing.');
if (!app.includes('Your report is confidential') || !app.includes('Mute 24h') || !app.includes('Remove content')) throw new Error('Moderation privacy notice or actions are missing.');
if (!app.includes('function EssayDetailModal(') || !app.includes('function GoogleDocsPreview(')) throw new Error('Google Docs essay detail preview is missing.');
if (!app.includes('Assigned tasks & responses') || !app.includes('function TaskSubmissionModal(') || !app.includes('College list')) throw new Error('Counselor student workspace is incomplete.');
if (!app.includes('Submission or Google Docs URL') || !app.includes('Google Docs URL')) throw new Error('Task/document Google Docs fields are missing.');
if (!app.includes('function StudentRoadmapPath(') || !app.includes('75 XP') || !styles.includes('.level-roadmap-path')) throw new Error('Level-linked visual roadmap is missing.');
if (!app.includes('function NotificationCenter(') || !styles.includes('.notification-launcher') || !styles.includes('.notification-drawer')) throw new Error('Corner notification center is missing.');
for (const uzbekFragment of ['Hozircha ma’lumot', 'Missiya yangilandi', 'Uchrashuv so‘rovi', 'Bu bo‘limda', 'Universitetlarni topish']) {
  if (app.includes(uzbekFragment)) throw new Error(`Non-English UI copy remains: ${uzbekFragment}`)
}
if (app.includes('className="palette-row"')) throw new Error('Login palette swatches must not be rendered.');
if (!app.includes("activeUser.role === 'organization'")) throw new Error('Organization data scope is missing.');
if (!app.includes("const THEME_KEY = 'naseeb-edu-theme'")) throw new Error('Persistent theme support is missing.');
if (!app.includes('/brand/naseeb-dark.png') || !app.includes('/brand/naseeb-light.jpg')) throw new Error('Theme-aware logos are missing.');
if (!styles.includes('--sidebar: #FFFCF7') || !styles.includes('--sidebar: #0E0713')) throw new Error('Theme-aware sidebar colors are missing.');
if (!styles.includes('--accent: #B8A58A') || !styles.includes('--accent: #4A1368')) throw new Error('Light/dark accent palettes are missing.');
for (const token of [
  '--border-subtle', '--border-strong', '--border-interactive', '--surface-hover',
  '--control-bg', '--control-bg-disabled', '--control-option-bg', '--selected-border',
  '--focus-ring', '--shadow-modal', '--danger-border', '--success-border',
]) {
  if (!styles.includes(token)) throw new Error(`Semantic theme token missing: ${token}`)
}
const componentStyles = styles.split("color-scheme: dark;\n}")[1] || ''
if (/#[0-9a-f]{3,8}|rgba?\(/i.test(componentStyles)) throw new Error('Component-level hardcoded color remains outside the theme token blocks.')
const tokenDefinitions = new Set([...styles.matchAll(/--([a-z0-9-]+)\s*:/gi)].map((match) => match[1]))
const tokenReferences = new Set([...styles.matchAll(/var\(--([a-z0-9-]+)/gi)].map((match) => match[1]))
const undefinedTokens = [...tokenReferences].filter((token) => !tokenDefinitions.has(token))
if (undefinedTokens.length) throw new Error(`Undefined CSS variables: ${undefinedTokens.join(', ')}`)
if (!html.includes("localStorage.getItem('naseeb-edu-theme')") || !app.includes('useLayoutEffect')) throw new Error('Pre-paint theme initialization is missing.')
if (!app.includes('function CheckboxControl(') || !app.includes('function ChoiceCards(')) throw new Error('Accessible reusable form controls are missing.')
if (app.includes('program-type-tabs') || app.includes('check-filter')) throw new Error('Legacy program filters are still rendered.')
if ((html.match(/name="theme-color"/g) || []).length !== 1) throw new Error('Exactly one dynamic theme-color meta tag is required.');
if (app.includes('AdmitFlow') || html.includes('AdmitFlow')) throw new Error('Legacy AdmitFlow branding is still rendered.');
for (const asset of ['naseeb-dark.png', 'naseeb-light.jpg']) {
  if (!fs.existsSync(path.join(root, 'frontend/public/brand', asset))) throw new Error(`Brand asset missing: ${asset}`);
}
for (const color of ['#4A1368', '#C0C0C6', '#1A1A1F', '#F2F2F5']) {
  if (!styles.includes(color)) throw new Error(`Palette color missing: ${color}`)
}

console.log('Frontend smoke checks passed.');
