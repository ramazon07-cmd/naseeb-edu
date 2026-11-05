import { useMemo, useState } from 'react';
import { Pencil, Plus, Search, Trash2 } from 'lucide-react';
import { api } from '../api';
import { t, tp, tx } from '../i18n';
import { CxAvatar, CxPills, CxTag, useCounselorUi } from '../components/counselorUi';
import { DocumentDecision } from '../components/documents';
import { Modal } from '../components/ui';
import { LoadMore, PagedListError, firstPageLoading } from '../components/paged';
import { useRecordList } from '../hooks/useRecordList';
import { invalidatePagedLists } from '../hooks/usePagedList';
import { dateText, joinParts, localDateKey } from '../lib/format';
import { label } from '../lib/labels';
import { editableFields, recordErrorMessage } from '../lib/recordRights';
import { hasSubmission } from '../lib/reviewSubmission';
import { isTaskManager } from '../lib/roles';
import { TASK_STATUS_TONE, groupTasksByStudent, taskStatus } from '../lib/taskGroups';
import { RESOURCE_FIELDS, ResourceForm } from './ResourceSection';
import { Submission } from './ReviewPage';
import './counselor-groups.css';

// [pill label, server filters]. "Open" is work the student still owes (to do, in
// progress, late); a submitted task is waiting on the counselor.
const VIEWS = {
  open: ['Open', { open: 'true' }],
  review: ['Awaiting review', { status: 'submitted' }],
  approved: ['Approved', { status: 'approved' }],
  all: ['All', undefined],
};

function TaskLine({ task, today, user, onOpen, onEdit, onDelete }) {
  const status = taskStatus(task, today);
  const editable = isTaskManager(user) && task.status !== 'approved' && editableFields(task, RESOURCE_FIELDS.tasks).length > 0;
  const detail = joinParts(
    task.due_date && tx`Due ${dateText(task.due_date)}`,
    task.priority && tx`Priority: ${label(task.priority)}`,
    task.is_self_assigned && t('Personal task'),
    task.submitted_at && tx`Submitted ${dateText(task.submitted_at)}`,
  );
  return <div className="cg-line">
    <span className="cx-row-copy"><button type="button" className="cg-open" onClick={() => onOpen(task)}>{task.title}</button>{detail && <small>{detail}</small>}</span>
    <CxTag tone={TASK_STATUS_TONE[status] || 'quiet'}>{label(status)}</CxTag>
    <div className="cg-actions">
      {editable && <button type="button" className="icon-button" onClick={() => onEdit(task)} aria-label={tx`Edit ${task.title}`}><Pencil size={15} /></button>}
      {isTaskManager(user) && <button type="button" className="icon-button danger" onClick={() => onDelete(task)} aria-label={tx`Delete ${task.title}`}><Trash2 size={15} /></button>}
    </div>
  </div>;
}

// One task: what was asked, what the student sent (their words, link or file, shown in
// place) and, while it waits for the counselor, the decision with a note.
function TaskDetailModal({ task, today, canDecide, onDecide, onClose, notify }) {
  const status = taskStatus(task, today);
  const sent = hasSubmission('task', task);
  return <Modal title={task.title} onClose={onClose}><div className="workspace-detail">
    <div className="workspace-detail-toolbar"><div className="cg-detail-meta">
      <CxTag tone={TASK_STATUS_TONE[status] || 'quiet'}>{label(status)}</CxTag>
      <span>{joinParts(task.student_name, task.due_date && tx`Due ${dateText(task.due_date)}`, task.priority && tx`Priority: ${label(task.priority)}`, task.submitted_at && tx`Submitted ${dateText(task.submitted_at)}`)}</span>
    </div></div>
    {task.description && <section><span className="detail-label">{t('Assigned task')}</span><p>{task.description}</p></section>}
    <section>
      {sent ? <Submission item={{ kind: 'task', record: task }} notify={notify} /> : <><span className="detail-label">{t('Student response')}</span><p className="cg-none">{t('The student has not submitted a written response yet.')}</p></>}
    </section>
    {canDecide && task.status === 'submitted' && <DocumentDecision canApprove={canDecide} approvable={sent} onDecide={onDecide} notify={notify} />}
  </div></Modal>;
}

// The counselor's Tasks: one card per student with their tasks as lines, narrowed by
// state and searchable by title or student. The "Awaiting review" count is the Review
// queue's task total.
export function CounselorTasksPage({ user, data, reload, notify }) {
  const { stats } = useCounselorUi();
  const [view, setView] = useState('open');
  const [search, setSearch] = useState('');
  const [viewing, setViewing] = useState(null);
  const [form, setForm] = useState(null);
  const list = useRecordList({ user, data, endpoint: 'tasks', query: search, filters: VIEWS[view][1], ordering: 'due' });
  const today = localDateKey();
  const groups = useMemo(() => groupTasksByStudent(list.items, today), [list.items, today]);
  const submitted = stats?.review?.tasks ?? stats?.task_by_status?.find((row) => row.status === 'submitted')?.count;
  const pills = Object.entries(VIEWS).map(([key, [pill]]) => [key, pill, key === 'review' ? submitted : undefined]);

  function refresh() {
    invalidatePagedLists(['tasks']);
    list.reload();
    reload?.();
  }

  // Throws on failure, so the decision form shows the error and stays open.
  async function decide(action, note) {
    if (action === 'sendBack') {
      await api.sendBack('tasks', viewing.id, note);
      notify(t('Sent back to the student.'));
    } else {
      await api.approveTask(viewing.id, note);
      notify(t("Task approved."));
    }
    setViewing(null);
    refresh();
  }

  async function remove(task) {
    if (!window.confirm(t("Delete this record?"))) return;
    try {
      await api.remove('tasks', task.id);
      notify(t("Record deleted."));
      refresh();
    } catch (err) { notify(recordErrorMessage(err), 'error'); }
  }

  return <div className="section-stack">
    <div className="cx-list-bar">
      <CxPills label={t('Filter tasks')} active={view} onChange={setView} items={pills} />
      <div className="cg-actions">
        <label className="cx-search">
          <Search size={16} aria-hidden="true" />
          <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('Search tasks…')} aria-label={t('Search tasks…')} autoComplete="off" />
        </label>
        {isTaskManager(user) && <button type="button" className="cx-btn primary" onClick={() => setForm({ item: null })}><Plus size={15} aria-hidden="true" />{t("Assign task")}</button>}
      </div>
    </div>
    <div className="cg-groups">
      {groups.map((group) => <section key={group.student} className="cg-group" aria-label={group.name}>
        <header className="cg-head">
          <CxAvatar name={group.name} />
          <b>{group.name}</b>
          <small>{joinParts(tp('{n} task|{n} tasks', group.tasks.length, { n: group.tasks.length }), group.late > 0 && tp('{n} late|{n} late', group.late, { n: group.late }))}</small>
        </header>
        {group.tasks.map((task) => <TaskLine key={task.id} {...{ task, today, user }} onOpen={setViewing} onEdit={(item) => setForm({ item })} onDelete={remove} />)}
      </section>)}
      {firstPageLoading(list) && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}
      {list.loaded && !groups.length && <p className="cx-empty">{t(search.trim() ? 'No tasks match your search.' : 'No tasks in this view.')}</p>}
    </div>
    <PagedListError list={list} />
    <LoadMore list={list} />
    {viewing && <TaskDetailModal task={viewing} today={today} canDecide={isTaskManager(user)} onDecide={decide} onClose={() => setViewing(null)} notify={notify} />}
    {form && <ResourceForm resource="tasks" item={form.item} data={data} user={user} onClose={() => setForm(null)} onSaved={() => { setForm(null); refresh(); }} notify={notify} />}
  </div>;
}
