import { useRef, useState } from 'react';
import { isTaskManager, isCounselor } from '../lib/roles';
import { api } from '../api';
import { tx, t } from '../i18n';
import { Panel, Empty, Modal } from '../components/ui';
import { Plus, Eye, CheckCircle2, Pencil, Trash2, Flag, ShieldCheck } from 'lucide-react';
import { GoogleDocsActions, EssayDetailModal, TaskSubmissionModal, GoogleDocsRecordModal, AttachmentPreviewModal } from '../components/documents';
import { AttachmentRow, FileField, UploadError, evidenceAttachment, recommendationAttachment, useFileUpload } from '../components/files';
import { toFormData } from '../lib/fileUpload';
import { studentName, dateText, dateTimeText, joinParts } from '../lib/format';
import { label, ownStudent } from '../lib/labels';
import { Record } from '../components/records';
import { Field, CheckboxControl } from '../components/forms';
import { useRecordList } from '../hooks/useRecordList';
import { usePagedList } from '../hooks/usePagedList';
import { LoadMore, PagedListError, StudentPicker, firstPageLoading } from '../components/paged';

export const RESOURCE_FIELDS = {
  researches: [
  ['title', 'Research title', 'text', true], ['field', 'Field'], ['role', 'Role'],
  ['summary', 'Summary', 'textarea', true], ['outcome', 'Outcome'], ['start_date', 'Start date', 'date'],
  ['end_date', 'End date', 'date'], ['link', 'Link', 'url'], ['google_docs_url', 'Google Docs URL', 'url']],

  projects: [
  ['title', 'Project title', 'text', true], ['role', 'Role'], ['technologies', 'Technologies'],
  ['description', 'Description', 'textarea', true], ['impact', 'Measurable impact'], ['date', 'Date', 'date'], ['link', 'Link', 'url'],
  ['google_docs_url', 'Google Docs URL', 'url']],

  internships: [
  ['organization', 'Organization', 'text', true], ['position', 'Position', 'text', true], ['supervisor', 'Supervisor'],
  ['description', 'Responsibilities and results', 'textarea'], ['start_date', 'Start date', 'date'], ['end_date', 'End date', 'date'],
  ['is_current', 'Current internship', 'checkbox'], ['google_docs_url', 'Google Docs URL', 'url']],

  activities: [
  ['name', 'Activity name', 'text', true], ['activity_type', 'Type', 'select', true, ['extracurricular', 'volunteering', 'leadership', 'club', 'competition', 'community', 'other']],
  ['role', 'Role'], ['description', 'Description', 'textarea'], ['impact', 'Impact'],
  ['hours_per_week', 'Hours per week', 'number'], ['weeks_per_year', 'Weeks per year', 'number'],
  ['start_date', 'Start date', 'date'], ['end_date', 'End date', 'date'],
  ['google_docs_url', 'Google Docs URL', 'url']],

  honors: [
  ['title', 'Honor title', 'text', true], ['issuer', 'Issuer'], ['level', 'Level', 'select', true, ['school', 'regional', 'national', 'international']],
  ['award_date', 'Award date', 'date'], ['description', 'Description', 'textarea'],
  ['google_docs_url', 'Google Docs URL', 'url']],

  achievements: [
  ['title', 'Achievement title', 'text', true], ['category', 'Category', 'select', true, ['project', 'startup', 'olympiad', 'volunteering', 'leadership', 'research', 'sport', 'art', 'other']],
  ['date', 'Date', 'date'], ['impact', 'Impact'], ['description', 'Description', 'textarea', true],
  ['google_docs_url', 'Google Docs URL', 'url']],

  recommendations: [
  ['recommender_name', 'Recommender name', 'text', true], ['recommender_title', 'Position'], ['recommender_email', 'Email', 'email'],
  ['relationship', 'Relationship'], ['status', 'Status', 'select', true, ['requested', 'drafting', 'submitted', 'approved']],
  ['deadline', 'Deadline', 'date'], ['notes', 'Notes', 'textarea'], ['google_docs_url', 'Google Docs URL', 'url']],

  tasks: [
  ['title', 'Task title', 'text', true], ['description', 'Description', 'textarea'], ['due_date', 'Due date', 'date', true],
  ['priority', 'Priority', 'select', true, ['low', 'medium', 'high', 'urgent']],
  ['status', 'Status', 'select', true, ['todo', 'in_progress', 'submitted', 'late']],
  ['student_response', 'Student response', 'textarea'], ['submission_url', 'Submission or Google Docs URL', 'url']],

  applications: [
  ['university', 'University', 'university', true], ['program', 'Program', 'text', true],
  ['tier', 'Tier', 'select', true, ['dream', 'target', 'safety']],
  ['status', 'Status', 'select', true, ['researching', 'shortlisted', 'applying', 'submitted', 'accepted', 'rejected', 'waitlisted']],
  ['deadline', 'Deadline', 'date'], ['scholarship_deadline', 'Scholarship deadline', 'date'], ['application_portal_url', 'Portal URL', 'url'], ['notes', 'Notes', 'textarea']],

  essays: [
  ['application', 'Application', 'application'], ['title', 'Essay title', 'text', true], ['prompt', 'Prompt', 'textarea', true],
  ['content', 'Draft content', 'textarea'], ['status', 'Status', 'select', true, ['draft', 'reviewing', 'needs_revision', 'approved']],
  ['google_docs_url', 'Google Docs URL', 'url'], ['counselor_comment', 'Counselor comment', 'textarea']]

};

// Records that carry one private file: the API field and how rows read it back.
export const RECORD_FILES = {
  achievements: { field: 'proof_file', attachment: evidenceAttachment },
  honors: { field: 'proof_file', attachment: evidenceAttachment },
  activities: { field: 'proof_file', attachment: evidenceAttachment },
  recommendations: { field: 'file', attachment: recommendationAttachment },
};

function currentRecordFile(resource, item) {
  const attachment = item && RECORD_FILES[resource]?.attachment(item);
  return attachment ? { name: attachment.name, size: attachment.size, contentType: attachment.contentType } : null;
}

// filters narrow the staff (server-paged) list; localFilter applies the same
// restriction to a student's own in-memory records.
// onAdd moves creation to a shared chooser (see StudentCenterPage): the panel
// then drops its own Add button and offers emptyAction as a link when empty.
export function ResourceSection({ title, resource, data, user, query, reload, notify, canCreate = true, defaultStudentId = null, filters, localFilter = null, onAdd = null, emptyText: emptyTextProp, emptyAction }) {
  // Staff lists hold shared essays only, so an empty list means none were shared.
  const emptyText = emptyTextProp ?? (resource === 'essays' && user?.role !== 'student' ? 'No shared essays yet. Students choose which essays to share.' : undefined);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [viewingEssay, setViewingEssay] = useState(null);
  const [viewingTask, setViewingTask] = useState(null);
  const [viewingGoogleDoc, setViewingGoogleDoc] = useState(null);
  const [viewingFile, setViewingFile] = useState(null);
  const list = useRecordList({ user, data, endpoint: resource, query, filters, localFilter });
  const filtered = list.items;
  const staffControlled = resource === 'tasks';
  const allowCreate = canCreate && (staffControlled ? isTaskManager(user) || user.role === 'student' : isCounselor(user) || user.role === 'student');
  const allowEdit = staffControlled ? isTaskManager(user) || user.role === 'student' : allowCreate;

  async function approve(item) {
    try {
      const result = await api.approveTask(item.id);
      notify(result.xp_awarded ? tx`Task approved. +${result.xp_awarded} XP` : t("Personal task approved. Personal tasks don't earn XP."));
      reload();
    } catch (err) {notify(err.message, 'error');}
  }

  async function remove(item) {
    if (!window.confirm(t("Delete this record?"))) return;
    try {await api.remove(resource, item.id);notify(t("Record deleted."));reload();} catch (err) {notify(err.message, 'error');}
  }
  return <><Panel title={title} action={<div className="panel-actions">{allowCreate && !onAdd && <button className="button quiet" onClick={() => {setEditing(null);setOpen(true);}}><Plus size={16} /> {staffControlled ? user.role === 'student' ? t("Create self-task") : t("Assign task") : t("Add")}</button>}</div>}><div className="record-list">{filtered.map((item) => {
          const lockedAfterApproval = item.status === 'approved';
          const allowDelete = !staffControlled ? allowCreate : isTaskManager(user) || user.role === 'student' && item.is_self_assigned;
          const attachment = RECORD_FILES[resource]?.attachment(item);
          return <RecordRow key={item.id} resource={resource} item={item} data={data} attachment={attachment && <AttachmentRow attachment={attachment} onPreview={() => setViewingFile({ item, attachment })} notify={notify} />} actions={<>{resource === 'tasks' && <button className="button quiet small" onClick={() => setViewingTask(item)}><Eye size={14} /> {t("Response")}</button>}{resource === 'essays' && <button className="button quiet small" onClick={() => setViewingEssay(item)}><Eye size={14} /> {t("Details")}</button>}{resource !== 'essays' && <GoogleDocsActions item={item} onPreview={() => setViewingGoogleDoc(item)} />}{isTaskManager(user) && staffControlled && item.status === 'submitted' && <button className="button quiet small" onClick={() => approve(item)}><CheckCircle2 size={15} /> {t("Approve")}</button>}{allowEdit && !lockedAfterApproval && <button className="icon-button" onClick={() => {setEditing(item);setOpen(true);}} aria-label={tx`Edit ${title}`}><Pencil size={15} /></button>}{allowDelete && <button className="icon-button danger" onClick={() => remove(item)} aria-label={tx`Delete ${title}`}><Trash2 size={15} /></button>}</>} />;
        })}{firstPageLoading(list) && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}{list.loaded && !filtered.length && <Empty text={emptyText} action={allowCreate && onAdd && emptyAction ? <button type="button" className="link-button empty-add" onClick={onAdd}>{emptyAction}</button> : null} />}</div><PagedListError list={list} /><LoadMore list={list} /></Panel>{open && <ResourceForm resource={resource} item={editing} data={data} user={user} defaultStudentId={defaultStudentId} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}{viewingEssay && <EssayDetailModal essay={viewingEssay} onClose={() => setViewingEssay(null)} />}{viewingTask && <TaskSubmissionModal task={viewingTask} onClose={() => setViewingTask(null)} notify={notify} />}{viewingGoogleDoc && <GoogleDocsRecordModal item={viewingGoogleDoc} onClose={() => setViewingGoogleDoc(null)} />}{viewingFile && <AttachmentPreviewModal title={recordTitle(resource, viewingFile.item)} attachment={viewingFile.attachment} onClose={() => setViewingFile(null)} notify={notify} />}</>;
}

function recordTitle(resource, item) {
  return resource === 'recommendations' ? item.recommender_name : item.title || item.name || t('Record');
}

// A student's own records skip their name; staff lists (which never hold the
// students collection in memory) name the student on every row.
export function RecordRow({ resource, item, data, attachment, actions, showStudent = true }) {
  const own = (data.students || []).some((student) => Number(student.id) === Number(item.student));
  const student = showStudent && !own ? item.student_name || studentName(data, item.student) : '';
  const period = item.start_date ? `${dateText(item.start_date)} – ${item.is_current ? t('Present') : item.end_date ? dateText(item.end_date) : '…'}` : '';
  const map = {
    researches: [item.title, joinParts(student, item.field, item.role), item.summary, item.verified ? 'approved' : 'reviewing'],
    projects: [item.title, joinParts(student, item.role, item.technologies), item.description, item.verified ? 'approved' : 'reviewing'],
    internships: [`${item.position} — ${item.organization}`, joinParts(student, period), item.description, item.verified ? 'approved' : 'reviewing'],
    activities: [item.name, joinParts(student, label(item.activity_type), item.role), item.impact || item.description, item.verified ? 'approved' : 'reviewing'],
    honors: [item.title, joinParts(student, item.issuer, label(item.level)), item.description, item.verified ? 'approved' : 'reviewing'],
    achievements: [item.title, joinParts(student, label(item.category), item.date && dateText(item.date)), item.impact || item.description, item.verified ? 'approved' : 'reviewing'],
    recommendations: [item.recommender_name, joinParts(student, item.recommender_title, item.relationship), item.deadline ? tx`Deadline: ${dateText(item.deadline)}` : '', item.status],
    tasks: [item.title, joinParts(student, item.due_date && tx`Due ${dateText(item.due_date)}`, item.priority && tx`Priority: ${label(item.priority)}`, item.is_self_assigned && t('Personal task'), item.submitted_at && tx`Submitted ${dateText(item.submitted_at)}`), item.student_response || item.description, item.status],
    applications: [item.university_detail?.name || t('University'), `${student} • ${item.program} • ${label(item.tier)}`, tx`Deadline: ${dateText(item.deadline)}`, item.status],
    essays: [item.title, joinParts(student, tx`Version ${item.version}`, item.university_name || t('General essay')), item.counselor_comment || item.prompt, item.status],
    bookings: [item.topic, joinParts(student, dateTimeText(item.starts_at), item.participant_name), item.notes, item.status]
  };
  const [title, meta, description, badge] = map[resource] || [t('Record'), student, '', null];
  return <Record title={title} meta={meta} description={description} badge={badge} attachment={attachment} actions={actions} />;
}

// [add title, edit title] per record type.
const FORM_TITLES = {
  researches: ['Add research', 'Edit research'], projects: ['Add project', 'Edit project'],
  internships: ['Add internship', 'Edit internship'], activities: ['Add activity', 'Edit activity'],
  honors: ['Add honor', 'Edit honor'], achievements: ['Add achievement', 'Edit achievement'],
  recommendations: ['Add recommendation letter', 'Edit recommendation letter'], tasks: ['Assign task', 'Edit task'],
  applications: ['Add application', 'Edit application'], essays: ['Add essay', 'Edit essay'],
};

export function ResourceForm({ resource, item, data, user, defaultStudentId = null, onClose, onSaved, notify, title = null }) {
  const [saving, setSaving] = useState(false);
  const [studentId, setStudentId] = useState(String(item?.student || defaultStudentId || ''));
  const formRef = useRef(null);
  const recordFile = RECORD_FILES[resource];
  const currentFile = currentRecordFile(resource, item);
  const [file, setFile] = useState(null);
  const [removeFile, setRemoveFile] = useState(false);
  const upload = useFileUpload();
  const busy = saving || upload.uploading;
  const allFields = RESOURCE_FIELDS[resource] || [];
  const fields = resource === 'tasks' && user.role === 'student' ?
  allFields.filter(([name]) =>
  !item ?
  ['title', 'description', 'due_date', 'priority'].includes(name) :
  item.is_self_assigned || ['status', 'student_response', 'submission_url'].includes(name)
  ) :
  allFields;
  async function submit(event) {
    event.preventDefault();if (busy) return;setSaving(true);const values = new FormData(event.currentTarget);
    const payload = {};
    for (const [name,, type] of fields) {
      const raw = values.get(name);
      const nullable = ['date', 'number', 'university', 'application'].includes(type);
      payload[name] = type === 'checkbox' ? raw === 'on' : raw === '' && nullable ? null : raw;
    }
    if (!item) payload.student = isTaskManager(user) ? Number(values.get('student')) : ownStudent(data)?.id;
    if (recordFile && (file || removeFile)) {
      setSaving(false);
      payload[recordFile.field] = file || null;
      const outcome = await upload.run((options) => api.saveWithFiles(resource, item?.id, toFormData(payload), options));
      if (outcome.ok) {notify(item ? t("Record updated.") : t("Record created."));onSaved();} else
      if (outcome.cancelled) notify(t("Upload cancelled."));
      return;
    }
    try {
      if (item) await api.update(resource, item.id, payload);else
      await api.create(resource, payload);
      notify(item ? t("Record updated.") : t("Record created."));onSaved();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  function close() {upload.cancel();onClose();}
  const selfTask = resource === 'tasks' && user.role === 'student';
  const [addTitle, editTitle] = selfTask ? ['Add personal task', 'Edit personal task'] : FORM_TITLES[resource] || ['Add', 'Edit'];
  return <Modal title={title || t(item ? editTitle : addTitle)} onClose={close}><form ref={formRef} className="form-grid" onSubmit={submit}>
    {!item && isTaskManager(user) && <StudentPicker required value={studentId} onChange={setStudentId} hint={t("Only students connected to your account are listed.")} />}
    {selfTask && <div className="form-wide self-task-note"><Flag size={18} /><div><b>{t("Personal development task")}</b><p>{t("This task is for your own planning and never awards XP.")}</p></div></div>}
    {fields.map(([name, title, type = 'text', required = false, choices = []]) => <DynamicField key={name} name={name} labelText={title} type={type} required={required} choices={choices} value={item?.[name]} data={data} user={user} studentId={studentId} />)}
    {fields.some(([name]) => name === 'google_docs_url') && <div className="form-wide google-doc-sharing-hint"><ShieldCheck size={16} /><span>{t("Set Google Docs sharing to Viewer or “Anyone with the link” to enable the preview.")}</span></div>}
    {recordFile && <FileField label={recordFile.field === 'file' ? t("Letter file") : t("Evidence file")} file={file} onFileChange={(next) => {setFile(next);if (next) setRemoveFile(false);}} current={currentFile} removingCurrent={removeFile} onRemoveCurrent={() => setRemoveFile(true)} onKeepCurrent={() => setRemoveFile(false)} upload={upload} />}
    <UploadError message={upload.error} onRetry={() => formRef.current?.requestSubmit()} />
    <div className="form-actions"><button type="button" className="button quiet" onClick={close}>{t("Cancel")}</button><button className="button primary" disabled={busy} aria-busy={busy}>{busy ? t("Saving…") : t("Save")}</button></div>
  </form></Modal>;
}

// Staff do not hold every application in memory: offer the chosen student's.
function StudentApplicationSelect({ name, labelText, value, studentId }) {
  const list = usePagedList('applications', { filters: { student: studentId }, pageSize: 100, enabled: Boolean(studentId) });
  return <Field label={t(labelText)} hint={studentId ? '' : t("Select a student first.")}><select name={name} defaultValue={value || ''} key={list.items.length}><option value="">{t('General essay')}</option>{list.items.map((app) => <option key={app.id} value={app.id}>{app.university_detail?.name} — {app.student_name}</option>)}</select></Field>;
}

export function DynamicField({ name, labelText, type, required, choices, value, data, user, studentId = '' }) {
  if (name === 'status' && !isTaskManager(user)) choices = choices.filter((choice) => !['approved', 'late', 'rejected', 'waitlisted', 'accepted', 'needs_revision', 'completed'].includes(choice));
  if (type === 'textarea') return <Field label={t(labelText)}><textarea name={name} defaultValue={value || ''} required={required} /></Field>;
  if (type === 'select') return <Field label={t(labelText)}><select name={name} defaultValue={value || choices[0]} required={required}>{choices.map((choice) => <option key={choice} value={choice}>{label(choice)}</option>)}</select></Field>;
  if (type === 'checkbox') return <CheckboxControl className="form-wide" name={name} defaultChecked={Boolean(value)}>{t(labelText)}</CheckboxControl>;
  if (type === 'university') return <Field label={t(labelText)}><select name={name} defaultValue={value || ''} required={required}><option value="">{t('Select university')}</option>{data.universities.map((uni) => <option key={uni.id} value={uni.id}>{uni.name} — {uni.country}</option>)}</select></Field>;
  if (type === 'application' && isTaskManager(user)) return <StudentApplicationSelect name={name} labelText={labelText} value={value} studentId={studentId} />;
  if (type === 'application') return <Field label={t(labelText)}><select name={name} defaultValue={value || ''}><option value="">{t('General essay')}</option>{data.applications.map((app) => <option key={app.id} value={app.id}>{app.university_detail?.name} — {studentName(data, app.student)}</option>)}</select></Field>;
  return <Field label={t(labelText)}><input name={name} type={type} defaultValue={value ?? ''} required={required} /></Field>;
}
