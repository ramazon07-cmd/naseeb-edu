import { useEffect, useMemo, useRef, useState } from 'react';
import { Calendar, ChevronLeft, MessageCircle, Plus, Search } from 'lucide-react';
import { api } from '../api';
import { t, tp, tx, formatNumberLocale, formatPercentLocale } from '../i18n';
import { CxAccountActions, CxAvatar, CxCard, CxHead, CxPills, CxProgress, CxTabs, CxTag, ReasonTags } from '../components/counselorUi';
import { Field } from '../components/forms';
import { Modal } from '../components/ui';
import { DocumentPreviewModal, EssayDetailModal, TaskSubmissionModal } from '../components/documents';
import { LoadMore, PagedListError } from '../components/paged';
import { PageSkeleton } from '../components/states';
import { TemporaryCredentialModal } from '../components/TemporaryCredentialModal';
import { DownloadCvButton } from '../components/CvDocument';
import { mergeSaved } from '../lib/mergeSaved';
import { RecommendationLetters } from '../components/RecommendationLetters';
import { useStudentRecords } from '../hooks/useStudentRecords';
import { usePagedList } from '../hooks/usePagedList';
import { activityText } from '../lib/activityText';
import { clockText, dateText, dateTimeText, dayLabel, dayMonthText, gradeText, joinParts, localDateKey, relativeDayText } from '../lib/format';
import { fullName, initials, label } from '../lib/labels';
import { createLatestRequest } from '../lib/latestRequest';
import { listText } from '../lib/profileSections';
import { meetingBadgeStatus, meetingStatus, upcomingMeetings } from '../lib/meetings';
import { mergeReviewQueue } from '../lib/reviewQueue';
import { isOnTrack, isQuiet, needsAttention, studentReasons, urgency } from '../lib/studentReasons';
import { BookingForm, MeetingNoteForm } from './BookingsPage';
import { ReviewWorkspace } from './ReviewPage';
import { ParentInviteModal, StudentAssignmentModal, StudentForm } from './StudentsPage';

// A status word's colour: done and confirmed are green, waiting is amber, late or missing red.
const STATUS_TONE = { approved: 'ok', completed: 'ok', confirmed: 'ok', verified: 'ok', submitted: 'warn', uploaded: 'warn', reviewing: 'warn', pending: 'warn', late: 'late', rejected: 'late', required: 'late', expired_unconfirmed: 'quiet' };
const statusTone = (status) => STATUS_TONE[status] || 'quiet';

function DeadlineCell({ deadline }) {
  if (!deadline) return <span className="cx-faint">—</span>;
  const title = deadline.kind === 'application' ? t('{name} application', { name: deadline.title }) : deadline.kind === 'letter' ? t('Recommendation letter') : deadline.title;
  const date = dayMonthText(deadline.due);
  return <span className="cx-deadline-cell"><span>{title}</span><span className="cx-deadline-when">{deadline.late ? t('{date} (late)', { date }) : date}</span></span>;
}

// One task, assigned to one or several students at once.
function BulkTaskForm({ studentIds, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    const payload = { title: values.get('title'), due_date: values.get('due_date'), priority: values.get('priority') };
    try {
      const results = await Promise.allSettled(studentIds.map((id) => api.create('tasks', { ...payload, student: id })));
      const failed = results.filter((result) => result.status === 'rejected').length;
      notify(failed ? tx`Assigned to ${studentIds.length - failed} of ${studentIds.length} students; ${failed} failed.` : tp('Task assigned to {n} student.|Task assigned to {n} students.', studentIds.length, { n: studentIds.length }), failed ? 'error' : undefined);
      onSaved();
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={tp('Assign task to {n} student|Assign task to {n} students', studentIds.length, { n: studentIds.length })} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <Field label={t("Task title")}><input name="title" required /></Field>
    <Field label={t("Due date")}><input name="due_date" type="date" required /></Field>
    <Field label={t("Priority")}><select name="priority" defaultValue="medium">{['low', 'medium', 'high', 'urgent'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></Field>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Assigning…") : t("Assign task")}</button></div>
  </form></Modal>;
}

// "Students": who is assigned to you, and for each one why they need you.
function CounselorStudentList({ user, data, stats, query, setQuery, students, onOpen, notify, reload }) {
  const [filter, setFilter] = useState('all');
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [assigning, setAssigning] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [adding, setAdding] = useState(false);
  const now = new Date();
  const rows = students.items
    .map((student) => ({ student, reasons: studentReasons(student, now) }))
    .sort((a, b) => urgency(b.reasons) - urgency(a.reasons) || fullName(a.student.user_detail).localeCompare(fullName(b.student.user_detail)));
  const counts = { all: rows.length, need_you: rows.filter(({ reasons }) => needsAttention(reasons)).length, quiet: rows.filter(({ reasons }) => isQuiet(reasons)).length, on_track: rows.filter(({ reasons }) => isOnTrack(reasons)).length };
  const shown = rows.filter(({ reasons }) => (filter === 'need_you' ? needsAttention(reasons) : filter === 'quiet' ? isQuiet(reasons) : filter === 'on_track' ? isOnTrack(reasons) : true));
  const total = stats?.students_total ?? rows.length;
  const needYou = stats?.students_need_you ?? counts.need_you;

  function toggle(id) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function stopSelecting() {
    setSelecting(false);
    setSelected(new Set());
  }

  return <div className="cx-page cx-students">
    <CxHead
      title={t("Students")}
      subtitle={joinParts(tp('{n} student assigned to you|{n} students assigned to you', total, { n: total }), tp('{n} needs you|{n} need you', needYou, { n: needYou }))}
    >
      <label className="cx-search">
        <Search size={16} aria-hidden="true" />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("Search by name…")} aria-label={t("Search by name…")} />
      </label>
      {selecting && <button type="button" className="cx-btn" onClick={stopSelecting}>{t("Cancel")}</button>}
      <button type="button" className="cx-btn primary" disabled={selecting && !selected.size} onClick={() => (selecting ? setAssigning(true) : setSelecting(true))}>
        <Plus size={15} aria-hidden="true" />{selecting ? tp('Assign task to {n} student|Assign task to {n} students', selected.size || 1, { n: selected.size || 1 }) : t("Assign task to several")}
      </button>
    </CxHead>

    <CxPills label={t("Filter students")} active={filter} onChange={setFilter} items={[['all', 'All', counts.all], ['need_you', 'Need you', counts.need_you], ['quiet', 'Quiet for 14+ days', counts.quiet], ['on_track', 'On track', counts.on_track]]} />

    <div className="cx-card cx-table-card">
      {students.loading && !students.items.length ? <PageSkeleton /> : <table className="cx-table">
        <colgroup><col className="c-student" /><col className="c-ready" /><col className="c-road" /><col className="c-why" /><col className="c-next" /><col className="c-last" /></colgroup>
        <thead><tr><th scope="col">{t("Student")}</th><th scope="col">{t("Readiness")}</th><th scope="col">{t("Roadmap")}</th><th scope="col">{t("Why they need you")}</th><th scope="col">{t("Next deadline")}</th><th scope="col">{t("Last active")}</th></tr></thead>
        <tbody>
          {shown.map(({ student, reasons }) => {
            const name = fullName(student.user_detail);
            const quietDays = reasons.find((reason) => reason.key === 'quiet')?.quietDays;
            return <tr key={student.id} className={selecting && selected.has(student.id) ? 'selected' : ''} onClick={() => (selecting ? toggle(student.id) : onOpen(student))}>
              <td>
                <div className="cx-person">
                  {selecting && <input type="checkbox" checked={selected.has(student.id)} onChange={() => toggle(student.id)} onClick={(event) => event.stopPropagation()} aria-label={tx`Select ${name}`} />}
                  <CxAvatar name={name} />
                  <span className="cx-row-copy">
                    <button type="button" className="cx-name-link" onClick={(event) => { event.stopPropagation(); onOpen(student); }}>{name}</button>
                    <small>{joinParts(gradeText(student.grade), student.target_major)}</small>
                  </span>
                </div>
              </td>
              <td data-label={t("Readiness")}><b>{formatPercentLocale(student.progress_percent || 0)}</b><CxProgress value={student.progress_percent} label={t("Readiness")} /></td>
              <td data-label={t("Roadmap")}>{t('{done} of {total} missions', { done: student.level_missions_approved ?? 0, total: student.level_missions_total ?? 0 })}</td>
              <td data-label={t("Why they need you")}>{reasons.length ? <ReasonTags reasons={reasons} /> : <CxTag tone="ok">{t("On track")}</CxTag>}</td>
              <td data-label={t("Next deadline")}><DeadlineCell deadline={student.next_deadline} /></td>
              <td className="cx-muted" data-label={t("Last active")}>{quietDays != null ? tp('{n} day ago|{n} days ago', quietDays, { n: quietDays }) : student.user_detail?.last_login ? relativeDayText(student.user_detail.last_login) : t("Never")}</td>
            </tr>;
          })}
        </tbody>
      </table>}
      {students.loaded && !shown.length && <p className="cx-empty">{t("No students in this view.")}</p>}
    </div>
    {(students.error || students.hasMore) && <div><PagedListError list={students} /><LoadMore list={students} /></div>}
    <p className="cx-footnote">{t("Click a student to open their Student 360.")}</p>
    <CxAccountActions>
      <button type="button" role="menuitem" onClick={() => setConnecting(true)}>{t("Connect students")}</button>
      <button type="button" role="menuitem" onClick={() => setAdding(true)}>{t("Add student")}</button>
    </CxAccountActions>

    {assigning && <BulkTaskForm studentIds={[...selected]} onClose={() => setAssigning(false)} onSaved={() => { setAssigning(false); stopSelecting(); reload(); }} notify={notify} />}
    {connecting && <StudentAssignmentModal user={user} data={data} onClose={() => setConnecting(false)} onSaved={() => { setConnecting(false); reload(); }} notify={notify} />}
    {adding && <StudentForm user={user} data={data} student={null} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); reload(); }} notify={notify} />}
  </div>;
}

// -- Student 360 ---------------------------------------------------------------

const TABS = (student, records, letters) => [
  ['overview', 'Overview'],
  ['review', 'To review', student.to_review_total ?? 0],
  ['roadmap', 'Roadmap'],
  ['documents', 'Documents', (records.documents || []).length],
  ['essays', 'Essays', (records.essays || []).length],
  ['applications', 'Applications', (records.applications || []).length],
  ['letters', 'Recommendations', letters.length],
  ['meetings', 'Meetings'],
  ['notes', 'Private notes'],
];

// What is missing from a profile, in words ("personal story", "an activity").
function missingAnswer(key) {
  const words = {
    photo: t('a photo'), graduation_year: t('graduation year'), guardian: t('guardian contact'), school: t('school details'), gpa: t('GPA'),
    ielts: t('IELTS status'), sat: t('SAT status'), countries: t('target countries'), interests: t('interests'),
    story: t('personal story'), activities: t('an activity'), honors: t('an honor'),
  };
  return words[key] || key;
}

// The reasons the Overview card lists, most urgent first: [{ key, tone, tag, text, action, run }].
function needsYouRows({ student, records, remind, goTo, approveLevel }) {
  const today = localDateKey();
  const rows = [];
  (records.tasks || []).filter((task) => ['todo', 'in_progress', 'late'].includes(task.status) && task.due_date < today).slice(0, 2).forEach((task) => rows.push({
    key: `task-${task.id}`, tone: 'late', tag: t('Late'), text: t('{title} · due {date}', { title: task.title, date: dayMonthText(task.due_date) }), action: t('Remind'), run: () => remind({ topic: 'task', record: task.id }),
  }));
  (records['roadmap-missions'] || []).filter((mission) => ['planned', 'in_progress'].includes(mission.status) && mission.due_date && mission.due_date < today).slice(0, 1).forEach((mission) => rows.push({
    key: `mission-${mission.id}`, tone: 'late', tag: t('Late'), text: t('{title} · due {date}', { title: mission.title, date: dayMonthText(mission.due_date) }), action: t('Remind'), run: () => remind({ topic: 'mission', record: mission.id }),
  }));
  (records.documents || []).filter((doc) => doc.status === 'required').slice(0, 1).forEach((doc) => rows.push({
    key: `doc-${doc.id}`, tone: 'late', tag: t('Missing'), text: t('{title} not uploaded', { title: doc.title }), action: t('Remind'), run: () => remind({ topic: 'document', record: doc.id }),
  }));
  if (student.to_review_total > 0) rows.push({
    key: 'review', tone: 'warn', tag: t('To review'), text: tp('{n} item waiting for you|{n} items waiting for you', student.to_review_total, { n: student.to_review_total }), action: t('Review'), run: () => goTo('review'),
  });
  if (student.level_up_pending) rows.push({
    key: 'level', tone: 'warn', tag: t('Level'), text: t('Ready for level {n}', { n: student.eligible_level }), action: t('Approve level'), run: approveLevel,
  });
  const missing = student.profile_readiness?.missing || [];
  if (missing.length) rows.push({
    key: 'profile', tone: 'quiet', tag: t('Profile'), text: t('Missing: {items}', { items: missing.slice(0, 3).map((item) => missingAnswer(item.key)).join(', ') }), action: t('Remind'), run: () => remind({ topic: 'profile' }),
  });
  return rows;
}

function ProgressItem({ title, percent, caption }) {
  return <div className="cx-progress-item">
    <div><span>{title}</span><b>{formatPercentLocale(percent || 0)}</b></div>
    <CxProgress value={percent} label={title} />
    <small>{caption}</small>
  </div>;
}

function TestScores({ student }) {
  const sections = ['ielts_listening', 'ielts_reading', 'ielts_writing', 'ielts_speaking'].map((key) => student[key]);
  const band = (value) => formatNumberLocale(value, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const ielts = student.ielts_score != null;
  const sat = student.sat_score != null;
  if (!ielts && !sat) return <p className="cx-empty">{t("No test scores yet.")}</p>;
  return <p className="cx-scores">
    {ielts && <span>IELTS <b>{band(student.ielts_score)}</b>{sections.every((value) => value != null) && ` (${t('L {a} · R {b} · W {c} · S {d}', { a: band(sections[0]), b: band(sections[1]), c: band(sections[2]), d: band(sections[3]) })})`}</span>}
    {sat && <span>SAT <b>{formatNumberLocale(student.sat_score, { useGrouping: false })}</b>{student.sat_superscore === true && ` ${t('superscore')}`}</span>}
  </p>;
}

function Overview({ student, records, meetings, name, notify, reload, goTo }) {
  const activity = usePagedList('activity', { filters: { student: student.id }, pageSize: 5 });
  const [busy, setBusy] = useState(false);
  const next = meetings[0];

  async function remind(payload) {
    setBusy(true);
    try {
      const result = await api.remindStudent(student.id, payload);
      notify(result.sent ? t('Reminder sent to {name}.', { name }) : t('{name} was reminded recently.', { name }));
      activity.reload();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function approveLevel() {
    setBusy(true);
    try {
      const result = await api.approveStudentLevel(student.id);
      notify(tx`Level ${result.level} approved.`);
      reload();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  const rows = needsYouRows({ student, records, remind, goTo, approveLevel });
  const statuses = student.task_status_counts || {};
  const openTasks = (statuses.todo || 0) + (statuses.in_progress || 0) + (statuses.late || 0);
  const missions = student.roadmap_status_counts || {};
  const missionsTotal = Object.values(missions).reduce((sum, value) => sum + value, 0);
  const readiness = student.profile_readiness || { percent: 0, done: 0, total: 0 };

  return <>
    <div className="cx-overview">
      <CxCard title={t("Why {name} needs you", { name })}>
        <div className="cx-reason-list">
          {rows.map((row) => <div key={row.key} className="cx-reason-row">
            <CxTag tone={row.tone}>{row.tag}</CxTag>
            <span>{row.text}</span>
            <button type="button" className="cx-btn" disabled={busy} onClick={row.run}>{row.action}</button>
          </div>)}
          {!rows.length && <p className="cx-empty">{t("Nothing needs your attention right now.")}</p>}
        </div>
      </CxCard>
      <CxCard title={t("Progress")}>
        <div className="cx-progress-list">
          <ProgressItem title={t("Application readiness")} percent={student.progress_percent} caption={t('{done} of {total}: tasks, applications, documents, letters', { done: student.readiness_items_done ?? 0, total: student.readiness_items_total ?? 0 })} />
          <ProgressItem title={t("Roadmap")} percent={student.roadmap_progress_percent} caption={tp('{done} of {n} mission approved|{done} of {n} missions approved', missionsTotal, { done: missions.completed || 0, n: missionsTotal })} />
          <ProgressItem title={t("Tasks")} percent={student.task_progress_percent} caption={joinParts(t('{n} open', { n: openTasks }), student.tasks_overdue > 0 && t('{n} late', { n: student.tasks_overdue }))} />
          <ProgressItem title={t("Profile ready")} percent={readiness.percent} caption={t('{done} of {total} answers', { done: readiness.done, total: readiness.total })} />
        </div>
      </CxCard>
      <CxCard title={t("Recent activity")}>
        <div className="cx-activity">
          {activity.items.map((item) => {
            const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(item.created_at).setHours(0, 0, 0, 0)) / 86400000);
            return <div key={item.id}><span>{days < 7 ? relativeDayText(item.created_at) : dayMonthText(item.created_at)}</span><span>{activityText(item.action)}</span></div>;
          })}
          {activity.loaded && !activity.items.length && <p className="cx-empty">{t("No activity yet.")}</p>}
        </div>
      </CxCard>
    </div>
    <div className="cx-overview-foot">
      <CxCard title={t("Test scores")}><TestScores student={student} /></CxCard>
      <CxCard title={t("Next meeting")}>
        {next
          ? <p className="cx-next-meeting"><span>{joinParts(`${dayLabel(next.starts_at)} ${clockText(next.starts_at)}`, next.topic)}</span>{next.status === 'pending' ? <CxTag tone="warn">{t("Waiting for you")}</CxTag> : <CxTag tone="ok">{t("Confirmed")}</CxTag>}</p>
          : <p className="cx-empty">{t("No upcoming meetings.")}</p>}
      </CxCard>
    </div>
  </>;
}

// One record of a student's tab: a title, a line under it and a status tag.
function RecordRow({ title, meta, status, onClick, children }) {
  const inner = <>
    <span className="cx-row-copy"><b>{title}</b>{meta && <small>{meta}</small>}</span>
    {status && <CxTag tone={statusTone(status)} small>{label(status)}</CxTag>}
    {children}
  </>;
  return onClick
    ? <button type="button" className="cx-row" onClick={onClick}>{inner}</button>
    : <div className="cx-row cx-row-static">{inner}</div>;
}

function RecordCard({ title, empty, children, count }) {
  return <CxCard title={title}>
    <div className="cx-list">{children}{!count && <p className="cx-empty">{empty}</p>}</div>
  </CxCard>;
}

function StudentNotes({ student, notify }) {
  const [adding, setAdding] = useState(false);
  const notes = usePagedList('meetings', { filters: { student: student.id }, pageSize: 20 });
  return <CxCard title={t("Private notes")} action={<button type="button" className="cx-btn" onClick={() => setAdding(true)}><Plus size={15} aria-hidden="true" />{t("Add note")}</button>}>
    <div className="cx-list">
      {notes.items.map((note) => <RecordRow key={note.id} title={note.title} meta={joinParts(dateText(note.meeting_date), note.summary)} />)}
      {notes.loaded && !notes.items.length && <p className="cx-empty">{t("No private notes yet.")}</p>}
    </div>
    <LoadMore list={notes} />
    {adding && <MeetingNoteForm booking={{ student: student.id, topic: '', starts_at: new Date().toISOString() }} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); notes.reload(); }} notify={notify} />}
  </CxCard>;
}

// A single student, as the "Counselor Dashboard" design's Student 360.
function CounselorStudent360({ student, user, data, onBack, onDirect, notify, reload, setPage }) {
  const [tab, setTab] = useState('overview');
  const [booking, setBooking] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [credential, setCredential] = useState(false);
  const [invite, setInvite] = useState(false);
  const [document, setDocument] = useState(null);
  const [essay, setEssay] = useState(null);
  const [task, setTask] = useState(null);
  const [noteFor, setNoteFor] = useState(null);
  const loaded = useStudentRecords(student.id, true);
  const records = loaded.records;
  // Letters saved here show over the loaded list until a refresh brings them (or newer).
  const [savedLetters, setSavedLetters] = useState({ studentId: null, items: [] });
  const ownSaved = savedLetters.studentId === student.id ? savedLetters.items : [];
  const letters = mergeSaved(records.recommendations || [], ownSaved);
  const letterSaved = (saved) => setSavedLetters({
    studentId: student.id,
    items: [saved, ...ownSaved.filter((item) => item.id !== saved.id)],
  });
  const name = fullName(student.user_detail);
  const meetings = (data.bookings || []).filter((item) => Number(item.student) === Number(student.id));
  const upcoming = upcomingMeetings(meetings);
  const now = new Date();
  const reviewItems = useMemo(() => {
    const named = (items) => items.map((item) => ({ ...item, student_name: item.student_name || name }));
    return mergeReviewQueue({
      tasks: named((records.tasks || []).filter((item) => item.status === 'submitted')),
      documents: named((records.documents || []).filter((item) => ['uploaded', 'reviewing'].includes(item.status))),
      roadmapMissions: named((records['roadmap-missions'] || []).filter((item) => item.status === 'submitted')),
      achievements: named((records.achievements || []).filter((item) => !item.verified && !item.counselor_comment)),
    });
  }, [records, name]);
  const readiness = student.profile_readiness || { percent: 0, missing: [] };
  const meta = joinParts(gradeText(student.grade), student.school_name, student.target_major, listText(student.target_countries));
  const tabs = TABS(student, records, letters);

  return <div className="cx-page cx-student-360">
    <div className="cx-s360-top">
      <button type="button" className="cx-back" onClick={onBack}><ChevronLeft size={16} aria-hidden="true" /><b>{t("Students")}</b></button>
      <span className="cx-crumb">/ {name}</span>
      <div className="cx-s360-actions">
        <DownloadCvButton studentId={student.id} className="cx-btn" notify={notify} />
        <button type="button" className="cx-btn" onClick={() => onDirect(student.user_detail?.id)}><MessageCircle size={15} aria-hidden="true" />{t("Message")}</button>
        <button type="button" className="cx-btn" onClick={() => setBooking(true)}><Calendar size={15} aria-hidden="true" />{t("Book meeting")}</button>
        <button type="button" className="cx-btn primary" onClick={() => setAssigning(true)}><Plus size={15} aria-hidden="true" />{t("Assign task")}</button>
      </div>
    </div>

    <section className="cx-hero">
      <span className="cx-hero-disc" aria-hidden="true">{initials(name)}</span>
      <div className="cx-hero-copy"><span>{t("STUDENT 360°")}</span><h1>{name}</h1><p>{meta}</p></div>
      <dl className="cx-hero-stats">
        <div><dt>{formatPercentLocale(student.progress_percent || 0)}</dt><dd>{t("Application readiness")}</dd><dd>{tp('{done} of {n} item finished|{done} of {n} items finished', student.readiness_items_total ?? 0, { done: student.readiness_items_done ?? 0, n: student.readiness_items_total ?? 0 })}</dd></div>
        <div><dt>{formatPercentLocale(readiness.percent)}</dt><dd>{t("Profile ready")}</dd><dd>{tp('{n} answer missing|{n} answers missing', readiness.missing.length, { n: readiness.missing.length })}</dd></div>
        <div><dt>{tx`Level ${student.level ?? 1}`}</dt><dd>{tp('{xp} XP · {n} star|{xp} XP · {n} stars', student.roadmap_stars ?? 0, { xp: student.xp_total ?? 0, n: student.roadmap_stars ?? 0 })}</dd></div>
      </dl>
    </section>

    <CxTabs items={tabs} active={tab} onChange={setTab} label={t("Student sections")} />
    {loaded.error && <div className="alert error" role="alert">{loaded.error}</div>}

    {tab === 'overview' && <>
      <Overview student={student} records={records} meetings={upcoming} name={student.user_detail?.first_name || name} notify={notify} reload={reload} goTo={setTab} />
    </>}
    <CxAccountActions>
      <button type="button" role="menuitem" onClick={() => setCredential(true)}>{t("Reset login")}</button>
      <button type="button" role="menuitem" onClick={() => setInvite(true)}>{t("Invite parent")}</button>
    </CxAccountActions>
    {tab === 'review' && <ReviewWorkspace items={reviewItems} loaded={!loaded.loading} notify={notify} reload={reload} setPage={setPage} studentLink={false} emptyText={t("Nothing from this student is waiting for review.")} />}
    {tab === 'roadmap' && <div className="cx-two">
      <RecordCard title={t("Roadmap missions")} count={(records['roadmap-missions'] || []).length} empty={t("No roadmap missions assigned yet.")}>
        {(records['roadmap-missions'] || []).map((mission) => <RecordRow key={mission.id} title={mission.title} meta={joinParts(tx`Level ${mission.level}`, mission.due_date && tx`Due ${dateText(mission.due_date)}`)} status={mission.status} />)}
      </RecordCard>
      <RecordCard title={t("Tasks")} count={(records.tasks || []).length} empty={t("No assigned tasks found.")}>
        {(records.tasks || []).map((item) => <RecordRow key={item.id} title={item.title} meta={joinParts(item.due_date && tx`Due ${dateText(item.due_date)}`, label(item.priority))} status={item.status === 'todo' && item.due_date < localDateKey() ? 'late' : item.status} onClick={item.status === 'submitted' || item.status === 'approved' ? () => setTask(item) : undefined} />)}
      </RecordCard>
    </div>}
    {tab === 'documents' && <RecordCard title={t("Documents")} count={(records.documents || []).length} empty={t("No documents yet.")}>
      {(records.documents || []).map((doc) => <RecordRow key={doc.id} title={doc.title} meta={joinParts(label(doc.document_type), doc.counselor_comment)} status={doc.status} onClick={doc.has_file || doc.google_docs_url ? () => setDocument(doc) : undefined} />)}
    </RecordCard>}
    {tab === 'essays' && <RecordCard title={t("Essays")} count={(records.essays || []).length} empty={t("This student hasn’t shared any essays yet.")}>
      {(records.essays || []).map((item) => <RecordRow key={item.id} title={item.title} meta={joinParts(tx`Version ${item.version}`, item.university_name || t("General essay"))} status={item.status} onClick={() => setEssay(item)} />)}
    </RecordCard>}
    {tab === 'applications' && <RecordCard title={t("Applications")} count={(records.applications || []).length} empty={t("The student has not added any universities to the college list yet.")}>
      {(records.applications || []).map((item) => <RecordRow key={item.id} title={item.university_detail?.name || t("University")} meta={joinParts(item.program, label(item.tier), item.deadline && tx`Deadline: ${dateText(item.deadline)}`)} status={item.status} />)}
    </RecordCard>}
    {tab === 'letters' && <RecommendationLetters student={student} user={user} letters={letters} loading={loaded.loading} notify={notify} onSaved={letterSaved} />}
    {tab === 'meetings' && <RecordCard title={t("Meetings")} count={meetings.length} empty={t("No meetings scheduled.")}>
      {meetings.map((item) => <RecordRow key={item.id} title={item.topic} meta={joinParts(dateTimeText(item.starts_at), item.duration_minutes > 0 && tx`${item.duration_minutes} min`)} status={meetingBadgeStatus(meetingStatus(item, now, { student: false }))}>
        <button type="button" className="cx-btn" onClick={() => setNoteFor(item)}>{t("Notes")}</button>
      </RecordRow>)}
    </RecordCard>}
    {tab === 'notes' && <StudentNotes student={student} notify={notify} />}

    {booking && <BookingForm staff defaultStudentId={student.id} onClose={() => setBooking(false)} onSaved={() => { setBooking(false); reload(); }} notify={notify} />}
    {assigning && <BulkTaskForm studentIds={[student.id]} onClose={() => setAssigning(false)} onSaved={() => { setAssigning(false); reload(); }} notify={notify} />}
    {credential && <TemporaryCredentialModal account={student.user_detail} onClose={() => setCredential(false)} notify={notify} />}
    {invite && <ParentInviteModal student={student} onClose={() => setInvite(false)} notify={notify} />}
    {document && <DocumentPreviewModal document={document} onClose={() => setDocument(null)} notify={notify} />}
    {essay && <EssayDetailModal essay={essay} onClose={() => setEssay(null)} />}
    {task && <TaskSubmissionModal task={task} onClose={() => setTask(null)} notify={notify} />}
    {noteFor && <MeetingNoteForm booking={noteFor} onClose={() => setNoteFor(null)} onSaved={() => setNoteFor(null)} notify={notify} />}
  </div>;
}

// The counselor's Students page: the list, or one student's 360 when the URL names one
// (/students/15), so a reload, a bookmark or Back reopens the same profile.
export function CounselorStudentsPage({ user, data, stats, query, setQuery, reload, notify, studentId = null, onStudent, onDirect, setPage }) {
  const students = usePagedList('students', { search: query, ordering: 'name', pageSize: 50 });
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  const listed = useRef([]);
  listed.current = students.items;
  // Opening student B while A's record is still loading must never show A's.
  const request = useRef(createLatestRequest()).current;
  useEffect(() => {
    setError('');
    if (!studentId) {
      request.cancel();
      setSelected(null);
      return;
    }
    const isCurrent = request.start();
    setSelected(listed.current.find((item) => item.id === studentId) || null);
    api.retrieve('students', studentId).then(
      (student) => { if (isCurrent()) setSelected(student); },
      (failure) => { if (isCurrent()) setError(failure.status === 404 ? t("Student profile not found.") : failure.message); },
    );
  }, [studentId, request]);

  if (studentId && error) return <div className="cx-page"><button type="button" className="cx-back" onClick={() => onStudent(null)}><ChevronLeft size={16} aria-hidden="true" /><b>{t("Students")}</b></button><div className="alert error" role="alert">{error}</div></div>;
  if (studentId && selected?.id !== studentId) return <PageSkeleton />;
  if (studentId) return <CounselorStudent360 student={selected} {...{ user, data, onDirect, notify, reload, setPage }} onBack={() => onStudent(null)} />;
  return <CounselorStudentList {...{ user, data, stats, query, setQuery, students, notify, reload }} onOpen={(student) => onStudent(student.id)} />;
}
