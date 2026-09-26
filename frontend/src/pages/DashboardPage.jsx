import { Stat, StudentTable, Record } from '../components/records';
import { t, tx, formatNumberLocale, formatPercentLocale } from '../i18n';
import { Panel, Empty, Modal } from '../components/ui';
import { ChevronRight, Plus } from 'lucide-react';
import { studentName, dateText, joinParts, programUsageCaption } from '../lib/format';
import { isCounselor } from '../lib/roles';
import CompactDashboard from '../CompactDashboard';
import { ownStudent, label } from '../lib/labels';
import { useState } from 'react';
import { api } from '../api';
import { Field, CheckboxControl } from '../components/forms';
import { usePagedList } from '../hooks/usePagedList';
import { StudentPicker } from '../components/paged';

// The first screen of staff dashboards: a page of students and the nearest
// deadlines, fetched from the server rather than the whole roster.
function useDashboardLists(user) {
  const staff = user.role !== 'student';
  const students = usePagedList('students', { ordering: 'name', pageSize: 10, enabled: staff });
  // Open work only: approved or submitted tasks are not deadlines anyone must act on.
  const tasks = usePagedList('tasks', { ordering: 'due', filters: { open: 'true' }, pageSize: 6, enabled: staff && user.role !== 'organization' });
  return { students, tasks };
}

export function Dashboard({ user, data, stats, reload, notify, setPage, onDirect }) {
  if (user.role === 'student') return <StudentDashboard user={user} data={data} stats={stats} setPage={setPage} onDirect={onDirect} />;
  return <StaffDashboard {...{ user, data, stats, reload, notify, setPage }} />;
}

function StaffDashboard({ user, data, stats, reload, notify, setPage }) {
  const { students, tasks } = useDashboardLists(user);
  if (user.role === 'organization') return <>
    <div className="stat-grid"><Stat label={t("School students")} value={formatNumberLocale(stats?.students_total ?? students.items.length)} note={t("Only students from your school")} /><Stat label={t("Task progress")} value={formatPercentLocale(stats?.average_task_progress ?? 0)} note={t("Weighted completion")} /><Stat label={t("Roadmap progress")} value={formatPercentLocale(stats?.average_roadmap_progress ?? 0)} note={t("Mission completion")} /><Stat label={t("Need attention")} value={formatNumberLocale(stats?.students_at_risk ?? 0)} note={t("Late task or mission")} tone="danger" /></div>
    <Panel title={t("Student progress")} action={<button className="button primary" onClick={() => setPage('students')}>{t("Student profiles")} <ChevronRight size={17} /></button>}><StudentTable data={data} students={students.items} readOnly /></Panel>
  </>;
  return <>
    <div className="stat-grid"><Stat label={t("Students")} value={formatNumberLocale(stats?.students_total ?? students.items.length)} /><Stat label={t("Task progress")} value={formatPercentLocale(stats?.average_task_progress ?? 0)} /><Stat label={t("Roadmap progress")} value={formatPercentLocale(stats?.average_roadmap_progress ?? 0)} /><Stat label={t("Need attention")} value={formatNumberLocale(stats?.students_at_risk ?? 0)} tone="danger" /></div>
    <div className="split-grid wide-left"><Panel title={t("Student progress")} action={<button className="button quiet" onClick={() => setPage('students')}>{t("View all")} <ChevronRight size={16} /></button>}><StudentTable data={data} students={students.items} readOnly /></Panel><div className="section-stack"><Panel title={t("Upcoming deadlines")}>{tasks.items.map((task) => <Record key={task.id} title={task.title} meta={joinParts(task.student_name || studentName(data, task.student), task.due_date && tx`Due ${dateText(task.due_date)}`)} badge={task.status} />)}{tasks.loaded && !tasks.items.length && <Empty text={t("No task deadlines yet.")} />}</Panel>{isCounselor(user) && <ProgramUsageSummary {...{ user, data, reload, notify }} />}</div></div>
  </>;
}

export function StudentDashboard({ user, data, setPage, onDirect }) {
  return <CompactDashboard key={user.id} user={user} student={ownStudent(data)} data={data} setPage={setPage} onDirect={onDirect} Modal={Modal} programUsage={<ProgramUsageSummary user={user} data={data} />} />;
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
