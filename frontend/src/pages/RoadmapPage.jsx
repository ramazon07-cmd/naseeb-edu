import { initials, fullName, label, ownStudent } from '../lib/labels';
import { Search, UsersRound, Clock3, Target, Compass, Star, Lock, Award, CalendarDays, ChevronRight, Filter, ShieldCheck, MessageSquareText, CheckCircle2, Eye, Pencil, Trash2, Plus } from 'lucide-react';
import { t, tp, tx, formatPercentLocale } from '../i18n';
import { isMissionLocked, nextLevel as levelAfter, studentProgress } from '../lib/metrics';
import { roadmapTab } from '../lib/routes';
import { Field, PortalTabs } from '../components/forms';
import { useState } from 'react';
import { isTaskManager } from '../lib/roles';
import { api } from '../api';
import { Modal, Empty, Badge, Panel } from '../components/ui';
import { dateText, gradeText, joinParts } from '../lib/format';
import { ResourceSection } from './ResourceSection';
import { matchesQuery } from '../lib/searchIndex';
import { usePagedList } from '../hooks/usePagedList';
import { useRecordList } from '../hooks/useRecordList';
import { LoadMore, PagedListError, StudentPicker } from '../components/paged';

export function StudentWorkspaceSelector({ value, selected, onChange, metrics = [] }) {
  const [search, setSearch] = useState('');
  const students = usePagedList('students', { search, ordering: 'name', pageSize: 50 });
  const options = selected && !students.items.some((student) => student.id === selected.id) ? [selected, ...students.items] : students.items;
  return <section className="student-workspace-selector">
    <div className="student-workspace-identity"><span className="student-workspace-avatar">{selected ? initials(fullName(selected.user_detail)) : <UsersRound size={20} />}</span><div><span className="eyebrow">{t("STUDENT WORKSPACE")}</span><h3>{selected ? fullName(selected.user_detail) : t("All assigned students")}</h3><p>{selected ? joinParts(selected.school_name || selected.school?.name, gradeText(selected.grade)) : t("Every student connected to your account")}</p></div></div>
    <div className="student-workspace-metrics">{metrics.map(([metricLabel, metricValue]) => <span key={metricLabel}><strong>{metricValue}</strong><small>{metricLabel}</small></span>)}</div>
    <div className="field student-picker"><span>{t("Choose student")}</span><label className="member-search"><Search size={15} /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("Search students")} aria-label={t("Search students")} /></label><select value={value} aria-label={t("Choose student")} onChange={(event) => onChange(event.target.value, options.find((student) => String(student.id) === event.target.value) || null)}><option value="all">{t("All assigned students")}</option>{options.map((student) => <option key={student.id} value={student.id}>{fullName(student.user_detail)}</option>)}</select><small className="field-hint">{t("Assignments and lists follow this selection.")}</small></div>
  </section>;
}

export function MissionForm({ mission, user, data, defaultStudentId = null, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const manager = isTaskManager(user);
  const studentSubmitted = !manager && mission?.status === 'submitted';
  async function submit(event) {
    event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);
    const payload = manager ?
    { title: values.get('title'), category: values.get('category'), description: values.get('description'), due_date: values.get('due_date') || null, status: values.get('status') } :
    { status: 'submitted', reflection: values.get('reflection'), google_docs_url: values.get('google_docs_url') || '' };
    if (manager && !mission) payload.student = Number(values.get('student'));
    try {mission ? await api.update('roadmap-missions', mission.id, payload) : await api.create('roadmap-missions', payload);notify(manager ? mission ? t("Mission updated.") : t("Mission created.") : t("Mission submitted for approval."));onSaved();} catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  const statuses = ['planned', 'in_progress', 'submitted'];
  return <Modal title={manager ? mission ? t("Edit roadmap mission") : t("Assign roadmap mission") : studentSubmitted ? t("Mission submitted") : t("Submit roadmap mission")} onClose={onClose}><form className="form-grid" onSubmit={submit}>{manager && !mission && <StudentPicker required value={defaultStudentId || ''} hint={t("The currently selected student is preselected.")} />}{manager && <><Field label={t("Mission title")}><input name="title" defaultValue={mission?.title || ''} required /></Field><Field label={t("Category")}><input name="category" defaultValue={mission?.category || ''} placeholder={t("Applications, Essays...")} /></Field><Field label={t("Due date")}><input name="due_date" type="date" defaultValue={mission?.due_date || ''} /></Field><Field label={t("Status")}><select name="status" defaultValue={mission?.status || 'planned'}>{statuses.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></Field></>}{!manager && <div className={`form-wide mission-submit-status ${studentSubmitted ? 'submitted' : 'planned'}`}>{studentSubmitted ? <Clock3 size={21} /> : <Target size={21} />}<div><b>{studentSubmitted ? t("Submitted") : t("Planned mission")}</b><p>{studentSubmitted ? t("Your work is awaiting teacher or counselor approval.") : t("Complete the mission, write your reflection, then submit it for approval.")}</p></div></div>}{manager ? <Field label={t("Description")}><textarea name="description" defaultValue={mission?.description || ''} /></Field> : <><Field label={t("Reflection")}><textarea name="reflection" defaultValue={mission?.reflection || ''} placeholder={t("What did you learn while completing this mission?")} readOnly={studentSubmitted} /></Field><Field label={t("Google Docs URL")} hint={t("Add a note, a link, or both.")}><input name="google_docs_url" type="url" defaultValue={mission?.google_docs_url || ''} placeholder={t("https://docs.google.com/document/d/.../edit")} readOnly={studentSubmitted} /></Field></>}<div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{studentSubmitted ? t("Close") : t("Cancel")}</button>{!studentSubmitted && <button className="button primary" disabled={saving} aria-busy={saving}>{saving ? manager ? t("Saving…") : t("Submitting…") : manager ? t("Save") : t("Submit mission")}</button>}</div></form></Modal>;
}

export function LevelOneSetupModal({ defaultStudentId = null, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      const result = await api.extendLevelOneRoadmap(Number(values.get('student')));
      notify(result.created_count ? tx`${result.created_count} Level 1 missions added.` : t("Level 1 is already up to date."));
      onSaved();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("Extend Level 1 roadmap")} onClose={onClose}><form className="form-grid" onSubmit={submit}><StudentPicker required value={defaultStudentId || ''} /><div className="form-wide roadmap-setup-note"><Compass size={19} /><div><b>{t("8-step Level 1 path")}</b><p>{t("Missing missions will be added in the correct order. Existing statuses, reflections and approvals stay unchanged.")}</p></div></div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Extending…") : t("Extend Level 1")}</button></div></form></Modal>;
}

export function StudentRoadmapPath({ student, missions, onOpen }) {
  const level = student?.level ?? 1;
  const orderedMissions = [...missions].sort((a, b) => (a.level || 1) - (b.level || 1) || (a.sequence || 1) - (b.sequence || 1) || a.id - b.id);
  const currentLevelMissions = orderedMissions.filter((item) => (item.level || 1) === level);
  // Keep an assigned roadmap visible when leveling has moved ahead of the
  // available mission template (production currently has a Level 1 path).
  const levelMissions = currentLevelMissions.length ? currentLevelMissions : orderedMissions;
  const numbers = studentProgress(student);
  const activeIndex = levelMissions.findIndex((item) => item.status !== 'completed');
  const currentIndex = activeIndex === -1 ? Math.max(0, levelMissions.length - 1) : activeIndex;
  const nextLevel = levelAfter(student);
  const isLocked = (item) => isMissionLocked(item, orderedMissions);
  function missionState(item, index) {
    if (item.status === 'completed') return 'complete';
    if (item.status === 'submitted') return 'approval';
    if (isLocked(item)) return 'locked';
    if (item.status === 'in_progress' || index === currentIndex) return 'current';
    return 'upcoming';
  }
  const percent = numbers.roadmapPercent;
  // Matches the steps shown: this level's, or every mission when the level has none.
  const levelLeft = numbers.levelTotal ? Math.max(0, numbers.levelTotal - numbers.levelApproved) : Math.max(0, numbers.missionsTotal - numbers.missionsApproved);
  return <section className="roadmap-track">
    <header className="roadmap-progress-card">
      <span className="eyebrow">{t("YOUR PROGRESS")}</span>
      <h2>{tx`Level ${level}`}</h2>
      {student?.level_up_pending && <p>{tx`Level ${student.eligible_level} is waiting for staff approval.`}</p>}
      <div className="roadmap-star-count"><Star size={19} /><strong>{numbers.missionsApproved}</strong><small>{tp('star earned|stars earned', numbers.missionsApproved)}</small></div>
      <div className="roadmap-progress-meter">
        <span>{tp('Roadmap: {done} of {n} mission approved|Roadmap: {done} of {n} missions approved', numbers.missionsTotal, { done: numbers.missionsApproved, n: numbers.missionsTotal })}</span>
        <b aria-label={t('Roadmap progress')}>{formatPercentLocale(percent)}</b>
        <div className="progress"><span style={{ width: `${percent}%` }} /></div>
        {numbers.levelTotal > 0 && <small>{t('This level: {done} of {n}', { done: numbers.levelApproved, n: numbers.levelTotal })}</small>}
      </div>
    </header>
    {levelMissions.length ? <ol className="roadmap-steps">{levelMissions.map((item, index) => {
        const state = missionState(item, index);
        const done = state === 'complete' || state === 'locked';
        return <li className={`roadmap-step ${state}`} key={item.id}>
        <span className="roadmap-step-badge" aria-hidden="true">{state === 'complete' ? <Star size={16} /> : state === 'locked' ? <Lock size={15} /> : state === 'approval' ? <Clock3 size={16} /> : item.sequence || index + 1}</span>
        {/* aria-disabled (not disabled) keeps completed/locked steps in the tab order so keyboard and screen-reader users can still read them. */}
        <button type="button" className="roadmap-step-card" onClick={() => {if (!done) onOpen(item);}} aria-disabled={done || undefined} aria-label={`${t(item.title)}, ${state === 'locked' ? t("locked") : label(item.status)}`}>
          <span>{t(item.category) || t("Roadmap")}</span>
          <h3>{t(item.title)}</h3>
          <p>{state === 'complete' ? t("Approved") : state === 'approval' ? t("Awaiting approval") : state === 'locked' ? t("Locked") : state === 'current' ? t("Next up") : item.due_date ? tx`Due ${dateText(item.due_date)}` : t("Upcoming")}</p>
        </button>
      </li>;
      })}<li className="roadmap-step checkpoint">
        <span className="roadmap-step-badge" aria-hidden="true"><Award size={17} /></span>
        <div className="roadmap-step-card"><span>{t("NEXT CHECKPOINT")}</span><h3>{tx`Level ${nextLevel}`}</h3><p>{student?.level_up_pending ? t("Ready for staff approval") : tp('{n} mission left|{n} missions left', levelLeft, { n: levelLeft })}</p></div>
      </li></ol> : <Empty text={t("Your counselor has not assigned any roadmap missions yet.")} />}
  </section>;
}

export function roadmapMissionState(item, missions) {
  if (item.status === 'completed') return 'completed';
  if (item.status === 'submitted') return 'submitted';
  if (isMissionLocked(item, missions)) return 'locked';
  const siblings = missions.
  filter((candidate) => candidate.student === item.student && (candidate.level || 1) === (item.level || 1)).
  sort((a, b) => (a.sequence || 1) - (b.sequence || 1));
  const firstActionable = siblings.find((candidate) => !['completed', 'submitted'].includes(candidate.status) && !isMissionLocked(candidate, missions));
  if (item.status === 'in_progress' || firstActionable?.id === item.id) return 'current';
  return 'upcoming';
}

export const MISSION_STATE_COPY = {
  current: ['Current', 'Ready to continue'],
  locked: ['Locked', 'Complete the prerequisite first'],
  submitted: ['Submitted', 'Awaiting staff approval'],
  completed: ['Completed', 'Approved and XP awarded'],
  upcoming: ['Upcoming', 'Queued in your roadmap']
};

export function MissionList({ user, data, query, onOpen, onApprove, onRemove }) {
  const manager = isTaskManager(user);
  const [filter, setFilter] = useState('all');
  const [sort, setSort] = useState('sequence');
  const missions = data.roadmapMissions.map((item) => ({
    ...item,
    displayState: roadmapMissionState(item, data.roadmapMissions)
  }));
  const normalizedQuery = query.trim().toLowerCase();
  const visible = missions.
  filter((item) => filter === 'all' || item.displayState === filter).
  filter((item) => !normalizedQuery || matchesQuery(item, normalizedQuery)).
  sort((a, b) => {
    if (sort === 'deadline') return String(a.due_date || '9999').localeCompare(String(b.due_date || '9999'));
    if (sort === 'status') return a.displayState.localeCompare(b.displayState);
    return (a.level || 1) - (b.level || 1) || (a.sequence || 1) - (b.sequence || 1);
  });
  const nextMission = !manager ? missions.find((item) => item.displayState === 'current') : null;

  return <div className="mission-list-shell">
    {nextMission && <section className="next-mission-callout"><div><span className="eyebrow">{t("NEXT MISSION")}</span><h3>{t(nextMission.title)}</h3><p>{t(nextMission.description) || t("Continue this mission and submit a reflection when you are ready.")}</p></div><div><span><CalendarDays size={15} /> {nextMission.due_date ? dateText(nextMission.due_date) : t("No deadline")}</span><span><Star size={15} /> {tx`${nextMission.xp_reward ?? 75} XP after approval`}</span><button className="button primary" onClick={() => onOpen(nextMission)}>{t("Continue mission")} <ChevronRight size={16} /></button></div></section>}
    <div className="mission-list-toolbar"><PortalTabs active={filter} onChange={setFilter} items={[["all", "All"], ["current", "Current"], ["locked", "Locked"], ["submitted", "Submitted"], ["completed", "Completed"], ["upcoming", "Upcoming"]]} /><label><Filter size={15} /><span>{t("Sort")}</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option value="sequence">{t("Roadmap order")}</option><option value="deadline">{t("Deadline")}</option><option value="status">{t("Status")}</option></select></label></div>
    <div className="mission-grid">{visible.map((item) => {
        const [stateLabel, stateDescription] = MISSION_STATE_COPY[item.displayState];
        const canOpen = item.displayState !== 'locked';
        return <article className={`mission-card mission-${item.displayState}`} key={item.id}>
        <div className="mission-top"><span>{joinParts(tx`Level ${item.level || 1}`, tx`Step ${item.sequence || 1}`, item.category && t(item.category))}</span><Badge tone={item.displayState}>{stateLabel}</Badge></div>
        <h3>{t(item.title)}</h3><p>{t(item.description) || t("No description provided.")}</p>
        {manager && <small className="mission-owner">{joinParts(item.student_name, item.assigned_by_name && tx`Assigned by ${item.assigned_by_name}`)}</small>}
        <div className="mission-details"><span><CalendarDays size={14} /><b>{t("Deadline")}</b>{item.due_date ? dateText(item.due_date) : t("No deadline")}</span><span><Star size={14} /><b>{t("Reward")}</b>{tx`${item.xp_reward ?? 75} XP`}</span><span><ShieldCheck size={14} /><b>{t("Prerequisite")}</b>{t(item.prerequisite_title) || (item.prerequisite_sequence ? tx`Step ${item.prerequisite_sequence}` : t("None"))}</span><span><MessageSquareText size={14} /><b>{t("Reflection")}</b>{item.reflection ? t("Added") : t("Not written")}</span></div>
        <div className="mission-approval"><span className={`mission-state-dot ${item.displayState}`} /> <b>{stateLabel}</b><small>{stateDescription}</small></div>
        <footer><small>{item.reflection ? `${item.reflection.slice(0, 72)}${item.reflection.length > 72 ? '…' : ''}` : t("Reflection will appear here after submission.")}</small><div>{manager && item.status === 'submitted' && <button className="button quiet small" onClick={() => onApprove(item)}><CheckCircle2 size={15} /> {t("Approve")}</button>}{canOpen && item.status !== 'completed' && <button className="button quiet small" onClick={() => onOpen(item)}>{!manager && item.status === 'submitted' ? <Eye size={15} /> : <Pencil size={15} />} {!manager && item.status === 'submitted' ? t("View") : manager ? t("Edit") : t("Open")}</button>}{manager && <button className="icon-button danger" onClick={() => onRemove(item)} aria-label={tx`Delete ${t(item.title)}`}><Trash2 size={15} /></button>}</div></footer>
      </article>;
      })}{!visible.length && <Empty text={data.roadmapMissions.length ? t("No missions match this filter.") : t("No missions have been assigned yet.")} />}</div>
  </div>;
}

export function RoadmapPage({ user, data, query, reload, notify, tab: requestedTab, onTab }) {
  const manager = isTaskManager(user);
  // The tab lives in the URL (/roadmap/tasks) so links can open it directly.
  const [localTab, setLocalTab] = useState(requestedTab);
  const tab = roadmapTab(onTab ? requestedTab : localTab, manager);
  const setTab = onTab || setLocalTab;
  const [selectedStudentId, setSelectedStudentId] = useState('all');
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(false);
  const [setupOpen, setSetupOpen] = useState(false);
  const student = ownStudent(data);
  const selectedStudentNumericId = manager && selectedStudentId !== 'all' ? Number(selectedStudentId) : null;
  // Staff read missions and tasks from the server, one student or one page at
  // a time; students use their own records already in memory.
  const studentFilter = selectedStudentNumericId ? { student: selectedStudentNumericId } : {};
  const missionList = useRecordList({ user, data, endpoint: 'roadmap-missions', dataKey: 'roadmapMissions', query: manager ? query : '', filters: studentFilter, ordering: 'sequence', pageSize: selectedStudentNumericId ? 100 : 25, enabled: manager });
  const taskList = useRecordList({ user, data, endpoint: 'tasks', filters: studentFilter, ordering: 'due', pageSize: selectedStudentNumericId ? 100 : 25, enabled: manager });
  const scopedData = manager ? { ...data, tasks: taskList.items, roadmapMissions: missionList.items } : data;
  const countText = (list) => `${list.items.length}${list.hasMore ? '+' : ''}`;
  const selectedName = selectedStudent ? fullName(selectedStudent.user_detail) : '';
  function chooseStudent(id, studentRecord) {setSelectedStudentId(id);setSelectedStudent(id === 'all' ? null : studentRecord);}
  async function remove(item) {if (!window.confirm(t("Delete this mission?"))) return;try {await api.remove('roadmap-missions', item.id);notify(t("Mission deleted."));reload();} catch (err) {notify(err.message, 'error');}}
  async function approve(item) {try {const result = await api.approveRoadmapMission(item.id);notify(tx`Roadmap mission approved. +${result.xp_awarded || 0} XP`);reload();} catch (err) {notify(err.message, 'error');}}
  const timeline = [
  ...scopedData.tasks.map((item) => ({ id: `task-${item.id}`, title: item.title, date: item.due_date, status: item.status, kind: t('Task'), student: item.student_name })),
  ...scopedData.roadmapMissions.map((item) => ({ id: `mission-${item.id}`, title: item.title, date: item.due_date, status: item.status, kind: t('Mission'), student: item.student_name }))].
  filter((item) => item.date).sort((a, b) => new Date(a.date) - new Date(b.date));
  return <div className="section-stack student-portal">
    {manager && <section className="portal-hero roadmap-hero"><div><span className="eyebrow">{t("STUDENT ROADMAPS")}</span><h2>{t("Roadmap")}</h2><p>{t("Assign missions, review student submissions, and approve the work that earns XP.")}</p></div><div className="roadmap-hero-actions"><button className="button light" onClick={() => setSetupOpen(true)}><Compass size={17} /> {t("Extend Level 1")}</button><button className="button light" onClick={() => {setEditing(null);setOpen(true);}}><Plus size={17} /> {t("Assign mission")}</button></div></section>}
    {manager && <StudentWorkspaceSelector value={selectedStudentId} selected={selectedStudent} onChange={chooseStudent} metrics={[[t("Missions"), countText(missionList)], [t("Tasks"), countText(taskList)], [t("Awaiting approval"), `${scopedData.roadmapMissions.filter((item) => item.status === 'submitted').length + scopedData.tasks.filter((item) => item.status === 'submitted').length}${missionList.hasMore || taskList.hasMore ? '+' : ''}`]]} />}
    {manager && <PortalTabs active={tab} onChange={setTab} items={[["missions", "Missions"], ["tasks", "Tasks"], ["timeline", "Timeline"], ["reflections", "Reflections"]]} />}
    {!manager && <PortalTabs active={tab} onChange={setTab} items={[["path", "Level path"], ["tasks", "Tasks"]]} />}
    {!manager && tab === 'path' && <StudentRoadmapPath student={student} missions={data.roadmapMissions} onOpen={(item) => {setEditing(item);setOpen(true);}} />}
    {!manager && tab === 'tasks' && <ResourceSection title={t("Tasks")} resource="tasks" data={scopedData} user={user} query={query} reload={reload} notify={notify} />}
    {manager && tab === 'tasks' && <ResourceSection title={selectedName ? tx`Tasks · ${selectedName}` : t("All tasks")} resource="tasks" data={data} user={user} query={query} reload={reload} notify={notify} defaultStudentId={selectedStudentNumericId} filters={studentFilter} />}
    {manager && tab === 'missions' && <><MissionList user={user} data={scopedData} query="" onOpen={(item) => {setEditing(item);setOpen(true);}} onApprove={approve} onRemove={remove} /><PagedListError list={missionList} /><LoadMore list={missionList} /></>}
    {manager && tab === 'timeline' && <Panel title={selectedName ? tx`Timeline · ${selectedName}` : t("Timeline for all students")}><div className="timeline-list">{timeline.map((item) => <div key={item.id}><span className="timeline-dot" /><time>{dateText(item.date)}</time><div><b>{t(item.title)}</b><small>{joinParts(item.kind, !selectedName && item.student)}</small></div><Badge>{item.status}</Badge></div>)}{!timeline.length && <Empty text={t("No dated tasks or missions for this student.")} />}</div></Panel>}
    {manager && tab === 'reflections' && <div className="reflection-grid">{scopedData.roadmapMissions.map((item) => <article key={item.id}><MessageSquareText size={20} /><div><span>{t(item.category) || t("Mission")}</span><h3>{t(item.title)}</h3>{manager && <small>{item.student_name}</small>}<p>{item.reflection || t("No reflection has been written for this mission yet.")}</p></div>{!manager && item.status !== 'completed' && <button className="button quiet small" onClick={() => {setEditing(item);setOpen(true);}}>{item.status === 'submitted' ? t("View submission") : t("Write reflection")}</button>}</article>)}{!scopedData.roadmapMissions.length && <Empty text={t("No roadmap reflections for this student.")} />}</div>}
    {open && <MissionForm mission={editing} user={user} data={data} defaultStudentId={selectedStudentNumericId} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}
    {setupOpen && <LevelOneSetupModal defaultStudentId={selectedStudentNumericId} onClose={() => setSetupOpen(false)} onSaved={() => {setSetupOpen(false);reload();}} notify={notify} />}
  </div>;
}
