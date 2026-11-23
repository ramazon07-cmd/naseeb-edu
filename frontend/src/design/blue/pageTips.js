import { t } from '../../i18n.js';

// First-visit page tips: frontend only, per account, no requests.
//   naseeb-page-tips-v1:<userId>      JSON { "<page key>": 1 } pages whose tips were shown
//   naseeb-page-tips-off-v1:<userId>  "1" when the student turned the tips off
export const PAGE_TIPS_KEY = 'naseeb-page-tips-v1';
export const PAGE_TIPS_OFF_KEY = 'naseeb-page-tips-off-v1';

const read = (key) => { try { return localStorage.getItem(key); } catch { return null; } };
const write = (key, value) => { try { localStorage.setItem(key, value); } catch { /* Tips just come back next visit. */ } };

export function pageTipsOff(userId) { return read(`${PAGE_TIPS_OFF_KEY}:${userId}`) === '1'; }
export function setPageTipsOff(userId, off) {
  if (off) write(`${PAGE_TIPS_OFF_KEY}:${userId}`, '1');
  else { try { localStorage.removeItem(`${PAGE_TIPS_OFF_KEY}:${userId}`); } catch { /* ignore */ } }
}
function seenMap(userId) {
  try { const value = JSON.parse(read(`${PAGE_TIPS_KEY}:${userId}`) || '{}'); return value && typeof value === 'object' ? value : {}; } catch { return {}; }
}
// Also kept in memory for this page load, so storage that refuses writes does not replay the tips.
const seenNow = new Set();
export function pageTipsSeen(userId, page) { return seenNow.has(`${userId}:${page}`) || seenMap(userId)[page] === 1; }
export function markPageTipsSeen(userId, page) { seenNow.add(`${userId}:${page}`); write(`${PAGE_TIPS_KEY}:${userId}`, JSON.stringify({ ...seenMap(userId), [page]: 1 })); }

// Tips per page key. `target` may list several selectors; a tip whose target is not on screen is
// left out. The locked Roadmap is not covered. Meetings and Essay Lab targets come from their own pages; a tip whose target is absent is dropped.
export function pageTips(page) {
  const list = {
    find_personality: [
      { id: 'hdr', target: '.nb-mf-hdr', title: t('Your profile'), text: t('Each test fills one part of this profile. The bar shows how many of the 7 tests are done.') },
      { id: 'sheet', target: '.nb-mf-sheet', title: t('What we know so far'), text: t('Finished tests show your results here. The others ask the question they will answer.') },
      { id: 'maj', target: '.nb-mf-maj, .nb-mf-deck', title: t('Your 3 majors'), text: t('After all 7 tests, these cards turn over and show the majors that fit you best.') },
    ],
    student_center: [
      { id: 'id', target: '.nb-id-card', title: t('Your student profile'), text: t('How ready your profile and applications are. Your counselor sees the same picture.') },
      { id: 'tabs', target: '[role="tablist"]', title: t('Fill in each section'), text: t('Academics, portfolio, activities and documents. Press the pencil on a card to edit it.') },
    ],
    tasks: [
      { id: 'list', target: '.nb-tasks, .nb-task-count', title: t('Your tasks'), text: t('Tasks from your counselor with due dates. Red means late — start with those.') },
    ],
    messages: [
      { id: 'chats', target: '.channel-sidebar', title: t('Your chats'), text: t('Private chats with your counselor and school, plus groups. Saved Messages is your personal notepad.') },
      { id: 'thread', target: '.message-thread', title: t('Write a message'), text: t('Type here and attach files with the paperclip.') },
    ],
    programs: [
      { id: 'feat', target: '.nb-prog-featured-main', title: t('Next deadline'), text: t('The program closing soonest. Open the official site or save it to your list.') },
      { id: 'bar', target: '.program-search, .nb-prog-kpis', title: t('Find the right program'), text: t('Filter by type, grade, format and category, or show only programs with scholarships.') },
    ],
    applications: [
      { id: 'filter', target: '.nb-filter-wrap', title: t('Filter and sort'), text: t('Show only dream, target or safety schools, switch between list and board, and sort by deadline.') },
    ],
    college_search: [
      { id: 'match', target: '.nb-college-match-profile', title: t('Matched to you'), text: t('Universities are matched to your SAT, GPA, IELTS, major and budget. Update your profile to improve the matches.') },
      { id: 'bal', target: '.nb-list-balance', title: t('Balance your list'), text: t('Aim for about 2 Dream, 3 Target and 2 Safety universities. Tap a type to see only those.') },
    ],
    bookings: [
      { id: 'book', target: '#meetings-book, .nb-meet-inline', title: t('Book a meeting'), text: t('Pick who, how long and a free time, then send. Your counselor confirms it.') },
      { id: 'kpis', target: '.nb-kpi-row, .nb-kpis', title: t('Your meetings'), text: t('Upcoming and past meetings and the time you have spent with your team.') },
    ],
    essay_lab: [
      { id: 'lib', target: '.el-library, .el-page', title: t('All your essays'), text: t('Drafts, essays shared with your counselor and approved ones. Everything saves automatically.') },
      { id: 'folders', target: '.el-folders', title: t('Folders'), text: t('Group your essays in folders to keep each application together.') },
    ],
    notifications: [
      { id: 'list', target: '.nb-notif-card, .nb-notif', title: t('Everything new in one place'), text: t('Click an alert to jump to the meeting, essay or deadline it is about. Use Mark all as read when you are done.') },
    ],
    screen_time: [
      { id: 'chart', target: '.nb-st-chart', title: t('Your time in the portal'), text: t('Tap a bar to see that day. Only the time spent on each page is counted, never what you type.') },
    ],
    support: [
      { id: 'how', target: '.nb-sp-how, .nb-sp-tickets', title: t('Ask the Naseeb team'), text: t('Write a new request and follow the answer here. Your tickets stay in this list.') },
    ],
    account_settings: [
      { id: 'sec', target: '.nb-ac-sec, .nb-ac-prof', title: t('Your account'), text: t('Change your password and see who can view your data.') },
    ],
  };
  return list[page] || null;
}
