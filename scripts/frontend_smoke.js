const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8');
const app = fs.readFileSync(path.join(root, 'frontend/src/App.jsx'), 'utf8');
const landingPage = fs.readFileSync(path.join(root, 'frontend/src/LandingPage.jsx'), 'utf8');
const api = fs.readFileSync(path.join(root, 'frontend/src/api.js'), 'utf8');
const packageLock = fs.readFileSync(path.join(root, 'frontend/package-lock.json'), 'utf8');
const styles = fs.readFileSync(path.join(root, 'frontend/src/styles.css'), 'utf8');

if ((landingPage.match(/href=\{BOOK_MEETING_URL\}/g) || []).length !== 1 || !landingPage.includes("t('Book a call')")) throw new Error('Landing page must show one final Book a call action.');
if (landingPage.includes("t('Book a meeting')") || landingPage.includes("t('Talk to our team')")) throw new Error('Duplicate meeting actions remain on the landing page.');
const landingCss = fs.readFileSync(path.join(root, 'frontend/src/landing.css'), 'utf8');
const reachMapCss = fs.readFileSync(path.join(root, 'frontend/src/components/reach-map.css'), 'utf8');

const requiredViews = [
  'dashboard', 'profile', 'academics', 'portfolio', 'activities', 'recommendations',
  'schools', 'students', 'tasks', 'applications', 'documents',
  'certificates', 'essays', 'achievements', 'roadmap', 'program_usage', 'bookings', 'messages', 'support', 'screen_time',
  'parent_progress', 'parent_tasks', 'parent_applications', 'parent_documents', 'parent_meetings',
];
const requiredApiMethods = [
  'login', 'me', 'dashboard', 'list', 'create', 'update', 'remove',
  'quickCreateStudent', 'createSchoolAccount', 'createIndividualCounselor', 'transferCounselor', 'streamAssistant', 'markSupportViewed',
  'trackScreenTime', 'screenTimeSummary',
  'parentPortal', 'inviteParent', 'acceptParentInvite', 'revokeParentLink',
  'messageChannels', 'channelMessages', 'messageContacts', 'openDirectChannel',
  'messagingOverview', 'channelMembers', 'joinChannel', 'markChannelRead',
  'addChannelMember', 'removeChannelMember', 'acceptChannelMessage',
  'reportChannelMessage', 'messageReports', 'reviewMessageReport',
  'dismissMessageReport', 'resolveMessageReport',
  'bookingParticipants', 'approveBooking', 'rejectBooking', 'completeBooking',
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
if (app.includes('07 /')) throw new Error('Legacy numeric page-heading prefix must not be rendered.');
if (!api.includes('function listAll(') || !api.includes('payload.next')) throw new Error('Paginated API traversal is missing.');
if (!app.includes("label={t('Temporary password')}") || !app.includes('minLength="12"') || !app.includes('function ForcedPasswordChange(')) throw new Error('One-time credential and forced password-change UI is missing.');
if (!app.includes('VITE_SHOW_DEMO_ACCOUNTS') || !app.includes('SHOW_DEMO_ACCOUNTS &&')) throw new Error('Demo credentials must be explicitly enabled in development.');
if (!app.includes("teacher: 'Teacher'") || !app.includes('isTaskManager')) throw new Error('Teacher-controlled work UI is missing.');
if (!api.includes('approveRoadmapMission')) throw new Error('Roadmap approval API action is missing.');
if (!api.includes('extendLevelOneRoadmap') || !app.includes('function LevelOneSetupModal(')) throw new Error('Level 1 roadmap extension is missing.');
if (app.includes('Progress %') || app.includes('item.progress_percent') || app.includes("values.get('progress_percent')")) throw new Error('Manual roadmap progress controls must not be rendered.');
if (!app.includes("status: 'submitted', reflection: values.get('reflection')") || !app.includes('Submit mission') || !styles.includes('.mission-submit-status')) throw new Error('Student submit-only roadmap workflow is missing.');
if (!app.includes('<Sparkles size={12} /> {t("Planned")}') || !styles.includes('.mission-status-chip')) throw new Error('Planned mission badge is missing.');
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
if (!app.includes('function GoogleDocsActions(') || !app.includes('function GoogleDocsRecordModal(')) throw new Error('Shared Google Docs record controls are missing.');
for (const resource of ['researches', 'projects', 'internships', 'activities', 'honors', 'recommendations']) {
  const resourceStart = app.indexOf(`${resource}: [`)
  const resourceEnd = app.indexOf('\n  ],', resourceStart)
  if (resourceStart < 0 || !app.slice(resourceStart, resourceEnd).includes("'google_docs_url'")) {
    throw new Error(`Google Docs field missing from ${resource}.`)
  }
}
if (!app.includes('Assigned tasks & responses') || !app.includes('function TaskSubmissionModal(') || !app.includes('College list')) throw new Error('Counselor student workspace is incomplete.');
if (!app.includes('Submission or Google Docs URL') || !app.includes('Google Docs URL')) throw new Error('Task/document Google Docs fields are missing.');
if (!app.includes('function StudentRoadmapPath(') || !app.includes('75 XP') || !styles.includes('.level-roadmap-path')) throw new Error('Level-linked visual roadmap is missing.');
if (!app.includes('function MissionList(') || !app.includes('NEXT MISSION') || !app.includes('Roadmap order') || !styles.includes('.next-mission-callout')) throw new Error('Roadmap mission filters, sorting, or next-mission CTA is missing.');
if (!app.includes('function StudentWorkspaceSelector(') || !styles.includes('.student-workspace-selector')) throw new Error('Counselor student workspace selector is missing.');
if (!app.includes('defaultStudentId={selectedStudentNumericId}') || !app.includes('roadmapMissions: data.roadmapMissions.filter')) throw new Error('Roadmap task/mission assignment is not scoped to the selected student.');
for (const missionState of ['current', 'locked', 'submitted', 'completed', 'upcoming']) {
  if (!app.includes(`${missionState}: [`)) throw new Error(`Roadmap mission state copy missing: ${missionState}`)
}
if (!app.includes('function ProgramUsagePage(') || !app.includes('function ProgramServiceForm(') || !styles.includes('.usage-summary') || !styles.includes('.usage-toolbar')) throw new Error('Enhanced Program Usage or staff service management UI is missing.');
if (!app.includes("['programServices', 'program-services']") || !app.includes('Unlimited service access')) throw new Error('Scoped Program Usage resource or unlimited service state is missing.');
if (!app.includes('data.programServices.filter((item) => item.student === selectedStudentNumericId)')) throw new Error('Program Usage is not scoped to the selected student.');
if (!app.includes('function DashboardDiscoveryCards(') || !app.includes('VITE_PERSONALITY_QUIZ_URL') || !app.includes("setPage('college_search')") || !styles.includes('.dashboard-discovery-card')) throw new Error('Student dashboard discovery cards are missing.');
if (!app.includes('{t("· MISSION")} {Math.min(completed + 1') || !app.includes("state === 'locked'") || !styles.includes('.roadmap-path-row.locked')) throw new Error('Ordered Level 1 prerequisite path is missing.');
if (!app.includes("aria-pressed={post.liked_by_me}") || !app.includes('Each student counts once') || !styles.includes('.community-like-help')) throw new Error('Community like/unlike feedback is missing.');
if (!app.includes('Meet with') || !app.includes('Pending approval') || !app.includes('Mark completed') || !styles.includes('.booking-actions')) throw new Error('Booking participant and approval UI is missing.');
if (!app.includes('participant_name') || !app.includes('participant_role')) throw new Error('Booking participant identity is not displayed.');
if (app.includes("\n  meetings: { label: 'Meetings'") || app.includes("'meetings', 'bookings'")) throw new Error('Legacy meeting notes navigation must be removed.');
if (!app.includes("bookings: { label: 'Meetings'")) throw new Error('Booking workflow must be presented as Meetings.');
if (app.includes('function NotificationCenter(') || app.includes('NotificationsPage') || api.includes('markNotificationRead') || styles.includes('.notification-launcher')) throw new Error('Notification frontend must be removed.');
if (!app.includes('function AssistantCenter(') || !styles.includes('.assistant-launcher') || !styles.includes('.assistant-drawer')) throw new Error('Corner AI assistant is missing.');
if (!app.includes('Role-scoped context only') || !app.includes('History is kept only while this page is open.')) throw new Error('Assistant privacy and retention guidance is missing.');
if (!api.includes("streamRequest('/assistant/chat/'") || !app.includes("['counselor', 'student'].includes(user.role)")) throw new Error('Role-limited streaming assistant connection is missing.');
if (!app.includes('function SupportPage(') || !app.includes('function SupportTicketForm(') || !app.includes('function SupportResponseModal(')) throw new Error('Support ticket frontend workflow is missing.');
if (!app.includes('has_unread_response') || !styles.includes('.nav-badge') || !styles.includes('.support-ticket-card')) throw new Error('In-page support response indicator is missing.');
if (!app.includes("['supportTickets', 'support-tickets']") || !app.includes("user.role === 'admin'")) throw new Error('Support ticket resource or admin queue is missing.');
if (!app.includes('function IndividualCounselorForm(') || !app.includes('function CounselorTransferForm(') || !styles.includes('.school-card.individual')) throw new Error('Individual counselor workspace provisioning or transfer UI is missing.');
if (!app.includes('function ParentPortalPage(') || !app.includes('function ParentChildSwitcher(') || !app.includes('function ParentInviteModal(')) throw new Error('Parent cabinet, child switcher, or invite UI is missing.');
if (!api.includes('parentPortal') || !api.includes('inviteParent') || !api.includes('acceptParentInvite') || !api.includes('revokeParentLink')) throw new Error('Parent consent/linking API client is missing.');
if (!app.includes("user?.role === 'parent'") || !app.includes("activeUser.role === 'parent'") || !styles.includes('.parent-family-hero')) throw new Error('Parent bootstrap, navigation, or responsive design is missing.');
if (!app.includes('This cabinet never shows essays, messages, counselor notes') || !app.includes('FAMILY VIEW · READ ONLY')) throw new Error('Parent privacy and read-only disclosure is missing.');
if (!app.includes('function ScreenTimeTracker(') || !app.includes('function ScreenTimePage(') || !app.includes("document.visibilityState === 'visible'") || !app.includes('60_000')) throw new Error('Active-tab and idle-aware screen time is missing.');
if (!app.includes('SCREEN_TIME_QUEUE_KEY') || !app.includes("window.addEventListener('online'") || !styles.includes('.screen-time-privacy')) throw new Error('Offline retry or screen-time privacy UI is missing.');
if (!app.includes('student.level ?? 1') || !app.includes('student.xp_total ?? 0')) throw new Error('Zero-valued student level and XP must remain visible.');
if (!styles.includes('.sidebar-profile > div { min-width: 0; }') || !styles.includes('overflow-wrap: anywhere')) throw new Error('Long student names are not constrained.');
for (const uzbekFragment of ['Hozircha ma’lumot', 'Missiya yangilandi', 'Uchrashuv so‘rovi', 'Bu bo‘limda', 'Universitetlarni topish']) {
  if (app.includes(uzbekFragment)) throw new Error(`Non-English UI copy remains: ${uzbekFragment}`)
}
if (app.includes('className="palette-row"')) throw new Error('Login palette swatches must not be rendered.');
if (!app.includes("activeUser.role === 'organization'")) throw new Error('Organization data scope is missing.');
if (!app.includes("const THEME_KEY = 'naseeb-edu-theme'")) throw new Error('Persistent theme support is missing.');
if (!app.includes('/brand/naseeb-dark-256.png') || !app.includes('/brand/naseeb-light-256.jpg')) throw new Error('Optimized theme-aware logos are missing.');
if (!app.includes("light: '/brand/icon-light-64.png?v=2'") || !app.includes("dark: '/brand/icon-dark-64.png?v=2'") || !app.includes('favicon.href = themeIconFor(theme)')) throw new Error('The favicon must follow the active app theme.');
if (!html.includes("theme === 'dark' ? '/brand/icon-dark-64.png?v=2' : '/brand/icon-light-64.png?v=2'")) throw new Error('The pre-paint favicon must follow the initial app theme.');
if (!html.includes('rel="preload"') || !html.includes('naseeb-dark-256.png') || !html.includes('naseeb-light-256.jpg')) throw new Error('Theme logos must be preloaded.');
if (!app.includes('login-form-panel') || !styles.includes('.login-form-panel')) throw new Error('Responsive login form panel is missing.');
if (!app.includes('TARGET_COUNTRIES_MAX_LENGTH') || !app.includes('normalizeCountries') || !styles.includes('.student-target-cell')) throw new Error('Target-country validation or overflow protection is missing.');
if (!api.includes('fetchWithTimeout') || !api.includes('REQUEST_TIMEOUT_MS')) throw new Error('Slow-network timeout handling is missing.');
if (!app.includes('Promise.allSettled') || !app.includes('function PageDataBoundary(') || !styles.includes('.page-skeleton')) throw new Error('Partial loading, retry, or skeleton states are missing.');
if (!html.includes('class="app-boot"') || !app.includes('function AppBootLoader(') || !app.includes('bootstrapping')) throw new Error('First-paint and authenticated bootstrap loading states are missing.');
if (styles.includes('fonts.googleapis.com') || styles.includes('@import url(')) throw new Error('Frontend fonts must not depend on a render-blocking remote import.');
if (!styles.includes("font-family: 'Montserrat'") || !html.includes('/fonts/montserrat-latin.woff2')) throw new Error('Self-hosted Montserrat typography is missing.');
if (`${styles}\n${landingCss}\n${reachMapCss}`.includes('Cinzel') || `${styles}\n${landingCss}\n${reachMapCss}`.includes('EB Garamond')) throw new Error('Legacy mixed heading typography must not be reintroduced.');
for (const asset of ['montserrat-latin.woff2', 'montserrat-cyrillic.woff2']) {
  if (!fs.existsSync(path.join(root, 'frontend/public/fonts', asset))) throw new Error(`Font asset missing: ${asset}`);
}
if (!styles.includes('.brand-logo::after') || !styles.includes('.brand-logo::before')) throw new Error('Brand logo needs an instant text fallback while its image loads.');
if (!styles.includes('flex: 0 0 112px !important') || !styles.includes('aspect-ratio: 1')) throw new Error('Login emblem must preserve its circular dimensions.');
if (!app.includes('function ChannelListSkeleton(') || !app.includes('function MessageListSkeleton(') || !app.includes('function StaffStatsSkeleton(')) throw new Error('Messaging shaped skeleton states are missing.');
if (!app.includes('The preview is taking longer than expected.') || !styles.includes('.embedded-preview-state')) throw new Error('Embedded preview slow-loading fallback is missing.');
if (!app.includes('Create self-task') || !app.includes('Self-task · no XP') || !app.includes('item.is_self_assigned')) throw new Error('Student zero-XP self-task UI is missing.');
if (!app.includes('Only students connected to your account are listed.')) throw new Error('Scoped task-assignment guidance is missing.');
if (!styles.includes('--sidebar: #FFFFFF') || !styles.includes('--sidebar: #0E0713')) throw new Error('Theme-aware sidebar colors are missing.');
if (!styles.includes('--accent: #B8A58A') || !styles.includes('--accent: #4A1368')) throw new Error('Light/dark accent palettes are missing.');
if (!styles.includes("--brand-logo-image: url('/brand/naseeb-light-256.jpg')") || !styles.includes("--brand-logo-image: url('/brand/naseeb-dark-256.png')")) throw new Error('Logo must switch instantly through theme tokens.');
if (styles.includes('--nav-active-bg: var(--silver-gradient)')) throw new Error('Dark navigation must not reuse the light silver active state.');
if (styles.includes('--student-accent-token: #C8B99F')) throw new Error('Dark student UI must not reuse the beige light accent.');
if (!app.includes("user.role === 'student' ? 'student-portal' : ''")) throw new Error('Student messaging must inherit the student theme scope.');
if (!styles.includes('.student-portal .message-bubble:not(.mine) footer button')) throw new Error('Student message actions need dark-mode contrast.');
for (const token of [
  '--border-subtle', '--border-strong', '--border-interactive', '--surface-hover',
  '--control-bg', '--control-bg-disabled', '--control-option-bg', '--selected-border',
  '--focus-ring', '--shadow-modal', '--danger-border', '--success-border',
]) {
  if (!styles.includes(token)) throw new Error(`Semantic theme token missing: ${token}`)
}
const componentStyles = styles.split("color-scheme: dark;\n}")[1] || ''
if (/#[0-9a-f]{3,8}|rgba?\(/i.test(componentStyles)) throw new Error('Component-level hardcoded color remains outside the theme token blocks.')
const landingSentinel = '/* == landing tokens end == */'
if (!landingCss.includes(landingSentinel)) throw new Error('landing.css token-block sentinel is missing; the public-page color guard cannot run.')
const landingComponents = landingCss.split(landingSentinel)[1] || "";
if (/#[0-9a-f]{3,8}|rgba?\(/i.test(landingComponents)) throw new Error('Component-level hardcoded color remains in landing.css outside the token blocks.')
const tokenDefinitions = new Set([...styles.matchAll(/--([a-z0-9-]+)\s*:/gi)].map((match) => match[1]))
const tokenReferences = new Set([...styles.matchAll(/var\(--([a-z0-9-]+)/gi)].map((match) => match[1]))
const undefinedTokens = [...tokenReferences].filter((token) => !tokenDefinitions.has(token))
if (undefinedTokens.length) throw new Error(`Undefined CSS variables: ${undefinedTokens.join(', ')}`)
if (!html.includes("localStorage.getItem('naseeb-edu-theme')") || !app.includes('useLayoutEffect')) throw new Error('Pre-paint theme initialization is missing.')
if (!app.includes('function CheckboxControl(') || !app.includes('function ChoiceCards(')) throw new Error('Accessible reusable form controls are missing.')
if (app.includes('program-type-tabs') || app.includes('check-filter')) throw new Error('Legacy program filters are still rendered.')
if ((html.match(/name="theme-color"/g) || []).length !== 1) throw new Error('Exactly one dynamic theme-color meta tag is required.');
if (app.includes('AdmitFlow') || html.includes('AdmitFlow')) throw new Error('Legacy AdmitFlow branding is still rendered.');
for (const asset of ['naseeb-dark-256.png', 'naseeb-light-256.jpg', 'icon-dark-64.png', 'icon-light-64.png']) {
  if (!fs.existsSync(path.join(root, 'frontend/public/brand', asset))) throw new Error(`Brand asset missing: ${asset}`);
}
for (const color of ['#4A1368', '#C0C0C6', '#1A1A1F', '#F2F2F5']) {
  if (!styles.includes(color)) throw new Error(`Palette color missing: ${color}`)
}

console.log('Frontend smoke checks passed.');
