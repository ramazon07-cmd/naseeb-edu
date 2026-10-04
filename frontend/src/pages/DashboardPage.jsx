import { Stat, StudentTable, Record } from '../components/records';
import { t, tx, tp, formatNumberLocale, formatPercentLocale, formatDateLocale } from '../i18n';
import { Panel, Empty, Modal } from '../components/ui';
import { ChevronRight, Plus, ArrowRight, Search } from 'lucide-react';
import { studentName, dateText, clockText, joinParts, programUsageCaption, shortDayText } from '../lib/format';
import { isCounselor } from '../lib/roles';
import CompactDashboard from '../CompactDashboard';
import { ownStudent, label, fullName } from '../lib/labels';
import { useCallback, useState } from 'react';
import { api } from '../api';
import { Field, CheckboxControl } from '../components/forms';
import { usePagedList } from '../hooks/usePagedList';
import { StudentPicker } from '../components/paged';
import { useReviewQueue } from '../hooks/useReviewQueue';
import { REVIEW_SOURCES } from '../lib/reviewQueue';
import { reviewCounts, unreadMessages } from '../lib/counselorCounts';
import { needsAttention, studentReasons } from '../lib/studentReasons';
import { CxAvatar, CxCard, CxHead, CxQueueRow, CxTag, ReasonTags, useCounselorUi } from '../components/counselorUi';
import { MeetingNoteForm } from './BookingsPage';

// The first screen of staff dashboards: a page of students and the nearest
// deadlines, fetched from the server rather than the whole roster.
function useDashboardLists(user) {
  const staff = user.role !== 'student';
  const students = usePagedList('students', { ordering: 'name', pageSize: 10, enabled: staff });
  // Open work only: approved or submitted tasks are not deadlines anyone must act on.
  const tasks = usePagedList('tasks', { ordering: 'due', filters: { open: 'true' }, pageSize: 6, enabled: staff && user.role !== 'organization' });
  return { students, tasks };
}

export function Dashboard({ user, data, stats, reload, notify, setPage, onDirect, resourceStatus, loadResources, retryResources }) {
  if (user.role === 'student') return <StudentDashboard {...{ user, data, setPage, onDirect, resourceStatus, loadResources, retryResources }} />;
  return <StaffDashboard {...{ user, data, stats, reload, notify, setPage }} />;
}

function StaffDashboard({ user, data, stats, reload, notify, setPage }) {
  if (user.role === 'organization') return <OrganizationDashboard {...{ user, data, stats, setPage }} />;
  if (isCounselor(user)) return <CounselorHome {...{ user, data, stats, notify, setPage }} />;
  return <TeacherDashboard {...{ user, data, stats, reload, notify, setPage }} />;
}

function OrganizationDashboard({ user, data, stats, setPage }) {
  const { students } = useDashboardLists(user);
  return <>
    <div className="stat-grid"><Stat label={t("School students")} value={formatNumberLocale(stats?.students_total ?? students.items.length)} note={t("Only students from your school")} /><Stat label={t("Task progress")} value={formatPercentLocale(stats?.average_task_progress ?? 0)} note={t("Weighted completion")} /><Stat label={t("Roadmap progress")} value={formatPercentLocale(stats?.average_roadmap_progress ?? 0)} note={t("Mission completion")} /><Stat label={t("Need attention")} value={formatNumberLocale(stats?.students_at_risk ?? 0)} note={t("Late task or mission")} tone="danger" /></div>
    <Panel title={t("Student progress")} action={<button className="button primary" onClick={() => setPage('students')}>{t("Student profiles")} <ChevronRight size={17} /></button>}><StudentTable data={data} students={students.items} readOnly /></Panel>
  </>;
}

// Today: counselor and teacher, once teacher gets its own "Today's queue" (S3.7).
function TeacherDashboard({ user, data, stats, reload, notify, setPage }) {
  const { students, tasks } = useDashboardLists(user);
  return <>
    <div className="stat-grid"><Stat label={t("Students")} value={formatNumberLocale(stats?.students_total ?? students.items.length)} /><Stat label={t("Task progress")} value={formatPercentLocale(stats?.average_task_progress ?? 0)} /><Stat label={t("Roadmap progress")} value={formatPercentLocale(stats?.average_roadmap_progress ?? 0)} /><Stat label={t("Need attention")} value={formatNumberLocale(stats?.students_at_risk ?? 0)} tone="danger" /></div>
    <div className="split-grid wide-left"><Panel title={t("Student progress")} action={<button className="button quiet" onClick={() => setPage('students')}>{t("View all")} <ChevronRight size={16} /></button>}><StudentTable data={data} students={students.items} readOnly /></Panel><div className="section-stack"><Panel title={t("Upcoming deadlines")}>{tasks.items.map((task) => <Record key={task.id} title={task.title} meta={joinParts(task.student_name || studentName(data, task.student), task.due_date && tx`Due ${dateText(task.due_date)}`)} badge={task.status} />)}{tasks.loaded && !tasks.items.length && <Empty text={t("No task deadlines yet.")} />}</Panel>{isCounselor(user) && <ProgramUsageSummary {...{ user, data, reload, notify }} />}</div></div>
  </>;
}

// "Today's queue" (product vision S3.4.2), laid out as the Counselor Dashboard
// design's Home: four numbers, then what needs the counselor, today and this
// week. See lib/counselorCounts.js for where each number comes from.
const firstName = (name) => String(name || '').trim().split(/\s+/)[0];

function CounselorHome({ user, data, stats, notify, setPage }) {
  const { openSearch } = useCounselorUi();
  const queue = useReviewQueue();
  const students = usePagedList('students', { ordering: 'name', pageSize: 50 });
  const [noteFor, setNoteFor] = useState(null);
  const now = new Date();
  const name = user.first_name || user.username;
  const review = reviewCounts(stats);
  const { messages: unread, conversations } = unreadMessages(data.messageChannels);
  const todayKey = now.toDateString();
  const todayMeetings = data.bookings
    .filter((item) => ['pending', 'approved'].includes(item.status) && new Date(item.starts_at).toDateString() === todayKey)
    .sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at));
  const nextMeeting = todayMeetings.find((item) => new Date(item.starts_at) > now);
  const breakdown = joinParts(...REVIEW_SOURCES.filter(({ kind }) => review[kind] > 0).map(({ kind, countPattern }) => tp(countPattern, review[kind], { n: review[kind] })));
  const needYou = students.items
    .map((student) => ({ student, reasons: studentReasons(student, now) }))
    .filter(({ reasons }) => needsAttention(reasons))
    .sort((a, b) => b.reasons.filter((reason) => reason.tone === 'danger').length - a.reasons.filter((reason) => reason.tone === 'danger').length)
    .slice(0, 5);
  const deadlines = stats?.deadlines || [];
  const hour = now.getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  return <div className="cx-page cx-home">
    <CxHead
      title={`${t(greeting)}, ${name}`}
      subtitle={<><span className="cx-home-date">{formatDateLocale(now, { weekday: 'long', day: 'numeric', month: 'long' })} · </span>{joinParts(
        tp('{n} thing to review|{n} things to review', review.total, { n: review.total }),
        tp('{n} meeting today|{n} meetings today', todayMeetings.length, { n: todayMeetings.length }),
      )}</>}
    >
      <button type="button" className="cx-search" onClick={openSearch}><Search size={16} aria-hidden="true" />{t("Search students and work…")}</button>
    </CxHead>

    <div className="cx-stats">
      <button type="button" className="cx-stat dark" onClick={() => setPage('review')}>
        <span>{t("To review")}</span>
        <strong>{formatNumberLocale(review.total)}</strong>
        <small>{breakdown || t("Nothing waiting right now")}</small>
        <em>{t("Start reviewing")}<ArrowRight size={15} aria-hidden="true" /></em>
      </button>
      <button type="button" className="cx-stat" onClick={() => setPage('students')}>
        <span><i className="cx-label-long">{t("Students who need you")}</i><i className="cx-label-short">{t("Need you")}</i></span>
        <strong className={stats?.students_need_you ? 'num hot' : 'num'}>{formatNumberLocale(stats?.students_need_you ?? 0)}</strong>
        <small>{t("Late work or missing documents")}</small>
      </button>
      <button type="button" className="cx-stat" onClick={() => setPage('bookings')}>
        <span>{t("Today")}</span>
        <strong className="cx-stat-value"><span>{formatNumberLocale(todayMeetings.length)}</span><span className="cx-stat-unit">{tp('meeting|meetings', todayMeetings.length)}</span></strong>
        <small>{nextMeeting ? tx`Next at ${clockText(nextMeeting.starts_at)} · ${firstName(nextMeeting.student_name || studentName(data, nextMeeting.student))}` : t("No meetings today")}</small>
      </button>
      <button type="button" className="cx-stat" onClick={() => setPage('messages')}>
        <span>{t("Messages")}</span>
        <strong className="cx-stat-value"><span>{formatNumberLocale(unread)}</span><span className="cx-stat-unit">{t("Unread")}</span></strong>
        <small>{conversations ? tp('From {n} student|From {n} students', conversations, { n: conversations }) : t("You're all caught up")}</small>
      </button>
    </div>

    <div className="cx-home-grid">
      <CxCard title={t("Needs your review")} hint={t("oldest first")} className="cx-queue">
        <div className="cx-list">
          {queue.items.slice(0, 8).map((item) => <CxQueueRow key={item.id} item={item} onClick={() => setPage('review')} />)}
          {queue.loaded && !queue.items.length && <p className="cx-empty">{t("Nothing is waiting for your review.")}</p>}
        </div>
      </CxCard>
      <div className="cx-home-side">
        <CxCard title={t("Students who need you")}>
          <div className="cx-plain-list">
            {needYou.map(({ student, reasons }) => <button type="button" key={student.id} className="cx-person-row" onClick={() => setPage('students', { studentId: student.id })}>
              <CxAvatar name={fullName(student.user_detail)} />
              <span className="cx-row-copy"><b>{fullName(student.user_detail)}</b><ReasonTags reasons={reasons.filter((reason) => reason.tone === 'danger')} /></span>
            </button>)}
            {students.loaded && !needYou.length && <p className="cx-empty">{t("Nobody needs you right now.")}</p>}
          </div>
        </CxCard>
        <CxCard title={t("Today")}>
          <div className="cx-plain-list">
            {todayMeetings.map((meeting) => <div key={meeting.id} className="cx-meeting-row">
              <b className="cx-time">{clockText(meeting.starts_at)}</b>
              <span className="cx-row-copy">
                <b>{joinParts(meeting.student_name || studentName(data, meeting.student), meeting.topic)}</b>
                <small>{meeting.status === 'pending' ? <CxTag tone="warn" small>{t("Waiting for you")}</CxTag> : joinParts(t("Confirmed"), meeting.duration_minutes > 0 && tx`${meeting.duration_minutes} min`)}</small>
              </span>
              {meeting.status === 'approved' && <button type="button" className="cx-btn" onClick={() => setNoteFor(meeting)}>{t("Notes")}</button>}
            </div>)}
            {!todayMeetings.length && <p className="cx-empty">{t("No meetings today")}</p>}
          </div>
        </CxCard>
        <CxCard title={t("Deadlines this week")}>
          <div className="cx-plain-list">
            {deadlines.map((item) => <div key={item.id} className="cx-deadline-row">
              <span>{joinParts(deadlineLabel(item), item.student_name)}</span>
              {item.late ? <CxTag tone="late" small>{t("Late")}</CxTag> : <small>{shortDayText(item.due)}</small>}
            </div>)}
            {!deadlines.length && <p className="cx-empty">{t("No deadlines this week.")}</p>}
          </div>
        </CxCard>
      </div>
    </div>
    {noteFor && <MeetingNoteForm booking={noteFor} onClose={() => setNoteFor(null)} onSaved={() => setNoteFor(null)} notify={notify} />}
  </div>;
}

// A deadline's name: the task's own title, or what the application / letter is.
function deadlineLabel(item) {
  if (item.kind === 'application') return t('{name} application', { name: item.title });
  if (item.kind === 'letter') return t('Recommendation letter');
  return item.title;
}

export function StudentDashboard({ user, data, setPage, onDirect, resourceStatus, loadResources, retryResources }) {
  const loadPrograms = useCallback(() => loadResources(['opportunityPrograms']), [loadResources]);
  const retryPrograms = useCallback(() => retryResources(['opportunityPrograms']), [retryResources]);
  return <CompactDashboard key={user.id} user={user} student={ownStudent(data)} data={data} setPage={setPage} onDirect={onDirect} Modal={Modal} programUsage={<ProgramUsageSummary user={user} data={data} />}
    programsStatus={resourceStatus?.opportunityPrograms} loadPrograms={loadPrograms} retryPrograms={retryPrograms} />;
}

export function ProgramServiceForm({ service, user, data, defaultStudentId = null, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [unlimited, setUnlimited] = useState(Boolean(service?.unlimited));
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    const payload = {
      student: service?.student || Number(values.get('student')),
      name: values.get('name'),
      category: values.get('category'),
      status: values.get('status'),
      unlimited,
      total_hours: unlimited ? null : Number(values.get('total_hours')),
      used_hours: Number(values.get('used_hours') || 0),
      mentor: user.role === 'counselor' ? user.id : service?.mentor || null
    };
    try {
      if (service) await api.update('program-services', service.id, payload);else
      await api.create('program-services', payload);
      notify(service ? t("Program service updated.") : t("Program service assigned."));
      onSaved();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={service ? t("Edit program service") : t("Assign program service")} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <StudentPicker required value={service?.student || defaultStudentId || ''} selectedLabel={service?.student_name} disabled={Boolean(service)} hint={t("The currently selected student is preselected.")} />
    <Field label={t("Service name")}><input name="name" defaultValue={service?.name || ''} required /></Field>
    <Field label={t("Category")}><input name="category" defaultValue={service?.category || ''} placeholder={t("Essay, mentorship, admissions…")} /></Field>
    <Field label={t("Status")}><select name="status" defaultValue={service?.status || 'active'}>{['active', 'pending', 'completed'].map((status) => <option value={status} key={status}>{label(status)}</option>)}</select></Field>
    <Field label={t("Allocated hours")}><input name="total_hours" type="number" min="0.5" step="0.5" defaultValue={service?.total_hours || ''} required={!unlimited} disabled={unlimited} /></Field>
    <Field label={t("Used hours")}><input name="used_hours" type="number" min="0" step="0.5" defaultValue={service?.used_hours || 0} /></Field>
    <CheckboxControl className="form-wide" checked={unlimited} onChange={(event) => setUnlimited(event.target.checked)}>{t("Unlimited service access")}</CheckboxControl>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{saving ? t("Saving…") : t("Save service")}</button></div>
  </form></Modal>;
}

export function ProgramUsageSummary({ user, data, reload, notify }) {
  const manager = isCounselor(user);
  const [open, setOpen] = useState(false);
  const services = data.programServices;
  const finite = services.filter((item) => !item.unlimited);
  const total = finite.reduce((sum, item) => sum + Number(item.total_hours || 0), 0);
  const used = finite.reduce((sum, item) => sum + Number(item.used_hours || 0), 0);
  const remaining = Math.max(total - used, 0);
  const unlimited = services.filter((item) => item.unlimited).length;
  const share = total ? Math.round(remaining / total * 100) : 100;
  const hours = (value) => `${formatNumberLocale(value, { maximumFractionDigits: 1 })} ${t("h")}`;
  const visible = [...services].sort((a, b) => (a.status === 'active' ? 0 : 1) - (b.status === 'active' ? 0 : 1)).slice(0, 4);
  if (!manager && !services.length) return null;
  return <Panel title={t("Program usage")} action={manager ? <button className="button quiet small" onClick={() => setOpen(true)}><Plus size={14} /> {t("Assign service")}</button> : null}>
    <div className="usage-headline">
      <div className="usage-ring" style={{ '--progress': `${share}%` }} role="img" aria-label={total ? tx`${formatPercentLocale(share)} of hours remaining` : t("Unlimited access")}><strong>{total ? formatPercentLocale(share) : '\u221e'}</strong></div>
      <div className="usage-headline-copy">
        <strong>{total ? hours(remaining) : '\u221e'}</strong>
        <span>{total ? t("Remaining") : t("Unlimited access")}</span>
        <small>{programUsageCaption({ total, used, unlimited, hours })}</small>
      </div>
    </div>
    <div className="record-list usage-service-list">{visible.map((service) => <article className="record" key={service.id}><div className="record-main">
      <div><b>{service.name}</b><small>{manager && service.student_name ? `${service.student_name} \u00b7 ` : ''}{service.mentor_name || t("Mentor pending")}</small></div>
      <span className={`usage-service-value${service.unlimited ? ' is-unlimited' : ''}`}>{service.unlimited ? '\u221e' : hours(service.remaining_hours ?? 0)}</span>
    </div></article>)}{!visible.length && <Empty text={t("No program services have been assigned yet.")} />}</div>
    {open && <ProgramServiceForm user={user} data={data} notify={notify} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} />}
  </Panel>;
}
