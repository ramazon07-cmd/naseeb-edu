import { ArrowRight, CircleAlert, ClipboardCheck, ListChecks, MessageSquare, UsersRound } from 'lucide-react';
import { formatDateLocale, formatNumberLocale, formatPercentLocale, t } from '../i18n';
import { HomeCard } from '../components/counselorHome';
import { CxHead } from '../components/counselorUi';
import { PagedListError } from '../components/paged';
import { usePagedList } from '../hooks/usePagedList';
import { unreadConversations } from '../lib/counselorCounts';
import { greetingKey } from '../lib/counselorHome';
import { dateText, joinParts } from '../lib/format';
import { fullName } from '../lib/labels';
import { inServerZone } from '../lib/serverTime';
import { studentReasons } from '../lib/studentReasons';
import { CounselorStudentTable } from '../components/CounselorStudentTable';
import './assistant-home.css';

// The counselor's visual language, using only the assistant's scoped reads.
// Every card opens one of the assistant's four pages; decisions stay with the counselor.
export function AssistantHome({ user, data, stats, setPage }) {
  const students = usePagedList('students', { ordering: 'need_you', pageSize: 10 });
  const tasks = usePagedList('tasks', { ordering: 'due', filters: { open: 'true' }, pageSize: 6 });
  const now = new Date();
  const rows = students.items.map((student) => ({ student, name: fullName(student.user_detail), reasons: studentReasons(student, now) }));
  const cards = [
    { title: 'Assigned students', value: stats?.students_total ?? '—', note: 'Only students connected to your account are listed.', page: 'students', icon: UsersRound, primary: true },
    { title: 'Students who need you', value: stats?.students_at_risk ?? '—', note: 'Late work or missing documents', page: 'students', icon: CircleAlert, hot: stats?.students_at_risk > 0 },
    { title: 'Task progress', value: formatPercentLocale(stats?.average_task_progress ?? 0), note: 'Assigned tasks', page: 'tasks', icon: ClipboardCheck },
    { title: 'Messages', value: unreadConversations(stats, data.messageChannels), note: 'Unread conversations', page: 'messages', icon: MessageSquare },
  ];
  const openStudent = (student) => setPage('students', { studentId: student.id });
  return <div className="cx-page ch-home">
    <CxHead title={<>{t(greetingKey(inServerZone(now).getHours()))}, <b className="ch-name">{user.first_name || user.username}</b></>} subtitle={formatDateLocale(now, { weekday: 'long', day: 'numeric', month: 'long' })} />
    <div className="ch-stats">
      {cards.map(({ title, value, note, page, icon: Icon, primary, hot }) => <button type="button" key={title} className={`ch-stat${primary ? ' primary' : ''}`} onClick={() => setPage(page)}>
        <span className="ch-eyebrow"><Icon size={14} aria-hidden="true" />{t(title)}</span>
        <strong className={`ch-stat-number${hot ? ' hot' : ''}`}>{typeof value === 'number' ? formatNumberLocale(value) : value}</strong>
        <small>{t(note)}</small>
        {primary && <em>{t('View all')} <ArrowRight size={15} aria-hidden="true" /></em>}
      </button>)}
    </div>
    <div className="ch-grid-cards">
      <HomeCard className="ah-students" icon={UsersRound} title={t('Student progress')} action={<button type="button" className="cx-link" onClick={() => setPage('students')}>{t('View all')} <ArrowRight size={14} aria-hidden="true" /></button>}>
        {students.items.length > 0 && <CounselorStudentTable framed={false} rows={rows} onPreview={openStudent} />}
        {students.loading && !students.items.length && <p className="ch-empty" role="status">{t('Loading…')}</p>}
        {students.loaded && !students.items.length && <p className="ch-empty">{t('No students assigned to you yet.')}</p>}
        <PagedListError list={students} />
      </HomeCard>
      <HomeCard icon={ListChecks} title={t('Upcoming deadlines')} footer={<button type="button" className="cx-link" onClick={() => setPage('tasks')}>{t('View all')} <ArrowRight size={14} aria-hidden="true" /></button>}>
        <div className="ch-list">{tasks.items.map((task) => <button type="button" key={task.id} className="ch-row" onClick={() => setPage('tasks')}>
          <span className="cx-row-copy"><b>{task.title}</b><small>{joinParts(task.student_name, task.due_date && dateText(task.due_date))}</small></span>
          <ArrowRight size={14} aria-hidden="true" />
        </button>)}</div>
        {tasks.loading && !tasks.items.length && <p className="ch-empty" role="status">{t('Loading…')}</p>}
        {tasks.loaded && !tasks.items.length && <p className="ch-empty">{t('No task deadlines yet.')}</p>}
        <PagedListError list={tasks} />
      </HomeCard>
    </div>
  </div>;
}
