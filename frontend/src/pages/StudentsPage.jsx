import { useState, useEffect, useRef } from 'react';
import { Panel, Empty, Modal, Badge } from '../components/ui';
import { RecordRow } from './ResourceSection';
import { GoogleDocsActions, GoogleDocsRecordModal, TaskSubmissionModal, EssayDetailModal, DocumentPreviewModal, visibilityItemTitle, EvidencePreviewModal } from '../components/documents';
import { AttachmentRow, documentAttachment } from '../components/files';
import { t, tp, tx, formatPercentLocale, formatNumberLocale } from '../i18n';
import { countTotal } from '../lib/metrics';
import { Record, StudentAvatar, Stat, LevelProgress, ProfileCard, Detail, StudentTable } from '../components/records';
import { dateText, gradeText, joinParts, money } from '../lib/format';
import { label, fullName, initials } from '../lib/labels';
import { Eye, ExternalLink, Fingerprint, UsersRound, ShieldCheck, Search, Plus, LifeBuoy } from 'lucide-react';
import { api } from '../api';
import { Field, CheckboxControl } from '../components/forms';
import { TemporaryCredentialModal } from '../components/TemporaryCredentialModal';
import { SupportViewModal } from '../components/SupportViewModal';
import { TestScoreSummary } from '../components/testScores';
import { PageSkeleton } from '../components/states';
import { createLatestRequest } from '../lib/latestRequest';
import { isCounselor, isPlatformAdmin, isTaskManager } from '../lib/roles';
import { usePagedList } from '../hooks/usePagedList';
import { useStudentRecords } from '../hooks/useStudentRecords';
import { usesPagedLists } from '../lib/workspaceResources';
import { LoadMore, PagedListError } from '../components/paged';

export const STUDENT_RESOURCE_GROUPS = [
['Research', 'researches'], ['Projects', 'projects'], ['Internships', 'internships'],
['Activities', 'activities'], ['Honors', 'honors'], ['Achievements', 'achievements'],
['Recommendation letters', 'recommendations']];

const PROFILE_SUMMARY_RESOURCES = ['activities', 'honors', 'achievements'];

export function studentItems(data, resource, studentId) {
  return (data[resource] || []).filter((item) => Number(item.student) === Number(studentId));
}

export function StudentOverviewList({ title, resource, items, data }) {
  const [viewingGoogleDoc, setViewingGoogleDoc] = useState(null);
  return <><Panel title={title} ><div className="record-list">{items.map((item) => <RecordRow key={item.id} resource={resource} item={item} data={data} showStudent={false} actions={<GoogleDocsActions item={item} onPreview={() => setViewingGoogleDoc(item)} />} />)}{!items.length && <Empty />}</div></Panel>{viewingGoogleDoc && <GoogleDocsRecordModal item={viewingGoogleDoc} onClose={() => setViewingGoogleDoc(null)} />}</>;
}

export function StudentTaskList({ items, onView }) {
  return <Panel title={t("Assigned tasks & responses")} ><div className="record-list">{items.map((task) => <Record key={task.id} title={task.title} meta={joinParts(task.due_date && tx`Due ${dateText(task.due_date)}`, task.priority && tx`Priority: ${label(task.priority)}`, task.submitted_at && tx`Submitted ${dateText(task.submitted_at)}`)} description={task.student_response || task.description} badge={task.status} actions={<button className="button quiet small" onClick={() => onView(task)}><Eye size={14} /> {t("View response")}</button>} />)}{!items.length && <Empty text={t("No assigned tasks found.")} />}</div></Panel>;
}

export function StudentCollegeList({ items }) {
  return <Panel title={t("College list")} ><div className="record-list">{items.map((application) => <Record key={application.id} title={application.university_detail?.name || t("University")} meta={joinParts(application.program, label(application.tier), application.deadline && tx`Deadline: ${dateText(application.deadline)}`)} description={application.notes} badge={application.status} actions={application.application_portal_url && <a className="button quiet small" href={application.application_portal_url} target="_blank" rel="noreferrer">{t("Application portal")} <ExternalLink size={14} /></a>} />)}{!items.length && <Empty text={t("The student has not added any universities to the college list yet.")} />}</div></Panel>;
}

// Staff see only the essays a student chose to share.
export const NO_SHARED_ESSAYS = 'This student hasn’t shared any essays yet.';

export function StudentEssayList({ items, onView }) {
  return <Panel title={t("Essays & Google Docs")} ><div className="record-list">{items.map((essay) => <Record key={essay.id} title={essay.title} meta={joinParts(tx`Version ${essay.version}`, essay.university_name || t("General essay"))} description={essay.counselor_comment || essay.prompt} badge={essay.status} actions={<><button className="button quiet small" onClick={() => onView(essay)}><Eye size={14} /> {t("Essay details")}</button><GoogleDocsActions item={essay} /></>} />)}{!items.length && <Empty text={NO_SHARED_ESSAYS} />}</div></Panel>;
}

export function StudentDocumentList({ title, items, onPreview, notify }) {
  return <Panel title={title} ><div className="record-list">{items.map((doc) => <Record key={doc.id} title={doc.title} meta={label(doc.document_type)} description={doc.counselor_comment} badge={doc.status} attachment={<AttachmentRow attachment={documentAttachment(doc)} onPreview={() => onPreview(doc)} notify={notify} />} actions={<GoogleDocsActions item={doc} onPreview={doc.has_file ? undefined : () => onPreview(doc)} />} />)}{!items.length && <Empty />}</div></Panel>;
}

export function ParentInviteModal({ student, onClose, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    const payload = {
      student: student.id,
      email: values.get('email'),
      first_name: values.get('first_name'),
      last_name: values.get('last_name'),
      relationship: values.get('relationship'),
      can_view_applications: values.get('can_view_applications') === 'on',
      can_view_documents: values.get('can_view_documents') === 'on',
      can_view_meetings: values.get('can_view_meetings') === 'on',
      password: values.get('password')
    };
    try {
      const result = await api.inviteParent(payload);
      notify(tx`Invitation recorded. The parent signs in with ${result.email} to accept it.`);
      onClose();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={tx`Invite parent · ${fullName(student.user_detail)}`} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Parent first name")}><input name="first_name" /></Field><Field label={t("Parent last name")}><input name="last_name" /></Field><Field label={t("Parent email")}><input name="email" type="email" required /></Field><Field label={t("Relationship")}><select name="relationship" defaultValue="guardian"><option value="mother">{t("Mother")}</option><option value="father">{t("Father")}</option><option value="guardian">{t("Guardian")}</option><option value="other">{t("Other")}</option></select></Field><Field label={t("Temporary password")} hint={t("Used only if this email has no parent account yet; an existing parent keeps their own password.")}><input name="password" type="password" minLength="8" autoComplete="new-password" required /></Field><div className="parent-permission-fields form-wide"><span>{t("Shared read-only sections")}</span><CheckboxControl name="can_view_applications" defaultChecked>{t("Applications")}</CheckboxControl><CheckboxControl name="can_view_documents" defaultChecked>{t("Document status")}</CheckboxControl><CheckboxControl name="can_view_meetings" defaultChecked>{t("Meetings")}</CheckboxControl></div><p className="form-note form-wide"><Fingerprint size={16} /> {t("The invitation starts as pending. No child data is shown until the parent signs in and accepts it. Essays, messages, counselor notes, responses, files, and credentials are never included.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Creating invitation…") : t("Invite parent")}</button></div></form></Modal>;
}

// `profile`: the student's own editable profile cards, shown instead of the
// read-only profile panels; activities, honors and achievements are then
// summarised there too.
export function StudentOverview({ student, data: workspaceData, onBack, user, notify, profile = null }) {
  const [selectedTask, setSelectedTask] = useState(null);
  const [selectedEssay, setSelectedEssay] = useState(null);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [parentInviteOpen, setParentInviteOpen] = useState(false);
  const [credentialOpen, setCredentialOpen] = useState(false);
  // Staff do not hold every student's records in memory: load this student's.
  const remote = usesPagedLists(user);
  const studentRecords = useStudentRecords(student?.id, remote);
  const data = remote ? { ...workspaceData, ...studentRecords.records } : workspaceData;
  if (!student) return <Empty text={t("Student profile not found.")} />;
  const documents = studentItems(data, 'documents', student.id);
  const certificates = documents.filter((item) => item.document_type === 'certificate');
  const regularDocuments = documents.filter((item) => item.document_type !== 'certificate');
  const tasks = studentItems(data, 'tasks', student.id);
  const applications = studentItems(data, 'applications', student.id);
  const essays = studentItems(data, 'essays', student.id);

  return <div className="section-stack student-overview">
    <section className="student-overview-hero">
      <div className="student-overview-title">{onBack && <button className="button quiet student-overview-back" onClick={onBack}>{t("← Students")}</button>}<div className="profile-identity"><StudentAvatar student={student} className="large" /><div><span className="eyebrow">{t("STUDENT 360° PROFILE")}</span><h2>{fullName(student.user_detail)}</h2><p>{joinParts(student.user_detail?.email, student.school_name || t("No school assigned"))}</p></div></div></div>
      <div className="student-overview-actions">{(isCounselor(user) || user?.role === 'organization') && <button className="button quiet" onClick={() => setCredentialOpen(true)}><Fingerprint size={16} /> {t('Reset login')}</button>}{isCounselor(user) && <button className="button quiet" onClick={() => setParentInviteOpen(true)}><UsersRound size={16} /> {t("Invite parent")}</button>}</div>
      <div className="overview-progress"><strong>{formatPercentLocale(student.progress_percent || 0)}</strong><span>{t("Application readiness")}</span><div className="progress wide"><span style={{ width: `${student.progress_percent || 0}%` }} /></div><small>{tp('{done} of {n} item finished|{done} of {n} items finished', student.readiness_items_total ?? 0, { done: student.readiness_items_done ?? 0, n: student.readiness_items_total ?? 0 })}</small></div>
    </section>
    {profile}
    <div className="stat-grid"><Stat label={t("Level")} value={formatNumberLocale(student.level ?? 1)} note={student.level_up_pending ? tx`Level ${student.eligible_level} approval pending` : (student.level ?? 1) > 1 ? t("Approved by staff") : t("Starting level")} /><Stat label={t("Stars")} value={formatNumberLocale(student.roadmap_stars ?? 0)} note={t("One per approved roadmap mission")} /><Stat label={t("Assigned tasks")} value={formatNumberLocale(countTotal(student.task_status_counts))} /><Stat label={t("Applications")} value={formatNumberLocale(applications.length)} /></div>
    <LevelProgress student={student} />
    {studentRecords.loading && <div className="data-state refreshing" role="status"><span>{t("Loading this student’s records…")}</span></div>}
    {studentRecords.error && <div className="alert error" role="alert">{studentRecords.error}</div>}
    {!profile && <>
      <div className="split-grid wide-left"><ProfileCard student={student} /><Panel title={t("Contact & planning")} ><div className="detail-grid"><Detail label={t("Phone")} value={student.user_detail?.phone} /><Detail label={t("Parent contact")} value={student.parent_contact} /><Detail label={t("Budget")} value={student.budget_usd == null ? null : money(student.budget_usd)} /><Detail label={t("Target countries")} value={student.target_countries} /><Detail label={t("Scholarship")} value={student.scholarship_needed ? t("Needed") : t("Not needed")} /><Detail label={t("Counselor")} value={student.counselor_name} /></div>{student.notes && <div className="student-notes"><span>{t("Internal notes")}</span><p>{student.notes}</p></div>}</Panel></div>
      <Panel title={t("Guardian")} ><div className="detail-grid"><Detail label={t("Guardian name")} value={student.guardian_name} /><Detail label={t("Relationship")} value={student.guardian_relation ? label(student.guardian_relation) : ''} /><Detail label={t("Contact")} value={student.parent_contact} /></div></Panel>
    </>}
    <div className="overview-grid student-workspace-grid"><StudentTaskList items={tasks} onView={setSelectedTask} /><StudentCollegeList items={applications} /><StudentEssayList items={essays} onView={setSelectedEssay} /><StudentDocumentList title={t("Documents")} items={regularDocuments} onPreview={setSelectedDocument} notify={notify} /></div>
    <div className="overview-grid">
      {STUDENT_RESOURCE_GROUPS.filter(([, resource]) => !profile || !PROFILE_SUMMARY_RESOURCES.includes(resource)).map(([title, resource]) => <StudentOverviewList key={resource} title={title} resource={resource} items={studentItems(data, resource, student.id)} data={data} />)}
      <StudentDocumentList title={t("Certificates")} items={certificates} onPreview={setSelectedDocument} notify={notify} />
    </div>
    {selectedTask && <TaskSubmissionModal task={selectedTask} onClose={() => setSelectedTask(null)} notify={notify} />}
    {selectedEssay && <EssayDetailModal essay={selectedEssay} onClose={() => setSelectedEssay(null)} />}
    {selectedDocument && <DocumentPreviewModal document={selectedDocument} onClose={() => setSelectedDocument(null)} notify={notify} />}
    {parentInviteOpen && <ParentInviteModal student={student} onClose={() => setParentInviteOpen(false)} notify={notify} />}
    {credentialOpen && <TemporaryCredentialModal account={student.user_detail} onClose={() => setCredentialOpen(false)} notify={notify} />}
  </div>;
}

export const VISIBILITY_POLICY_LABELS = {
  identity_and_contact: 'Identity & contact', academic_profile: 'Academic profile', progress_and_xp: 'Progress & XP',
  task_metadata_and_status: 'Task metadata & status', roadmap_metadata_and_status: 'Roadmap metadata & status',
  application_metadata_and_status: 'Application metadata & status', document_metadata_and_secure_file: 'Document metadata & secure file',
  essay_metadata_and_status: 'Essay metadata & status', recommendation_metadata_and_status: 'Recommendation metadata & status',
  portfolio_and_activities: 'Portfolio & activities', meeting_schedule_and_status: 'Meeting schedule & status', program_usage: 'Program usage',
  private_messages: 'Private messages', message_moderation_reports: 'Moderation reports', credentials_and_password_state: 'Credentials & password state',
  internal_counselor_notes: 'Internal counselor notes', meeting_notes: 'Meeting notes', application_portal_credentials: 'Application portal credentials',
  unshared_essays: 'Essays the student has not shared', essay_draft_content_and_feedback: 'Essay draft content & feedback', recommendation_files_and_private_notes: 'Recommendation files & private notes',
  task_submission_content: 'Task submission content', roadmap_reflections: 'Roadmap reflections', screen_time_detail: 'Screen time detail', support_tickets: 'Support tickets',
};

export function visibilityPolicyLabel(item) {
  return t(VISIBILITY_POLICY_LABELS[item] || item.replaceAll('_', ' '));
}

export function VisibilitySection({ title, items = [], onDocument, onEvidence, emptyText }) {
  return <Panel title={title}><div className="visibility-records">{items.slice(0, 8).map((item) => <article key={`${item.proof_resource || 'record'}-${item.id}`}><div><b>{visibilityItemTitle(item)}</b><small>{label(item.status || item.category || item.document_type || item.activity_type || item.level || '')}</small></div><div className="panel-actions">{onDocument && (item.has_file || item.google_docs_preview_url) && <button className="button quiet" onClick={() => onDocument(item)}><Eye size={15} /> {t("Preview")}</button>}{onEvidence && item.has_proof_file && <button className="button quiet" onClick={() => onEvidence(item)}><ShieldCheck size={15} /> {t("Evidence")}</button>}</div></article>)}{!items.length && <Empty text={emptyText} />}</div></Panel>;
}

export function SchoolStudent360({ visibility, student, loading, error, onBack, user, notify }) {
  const [credentialOpen, setCredentialOpen] = useState(false);
  const [supportOpen, setSupportOpen] = useState(false);
  const [document, setDocument] = useState(null);
  const [evidence, setEvidence] = useState(null);
  if (loading) return <PageSkeleton />;
  if (error) return <div className="section-stack"><button className="button quiet back-button" onClick={onBack}>{t("← Students")}</button><div className="alert error">{error}</div></div>;
  if (!visibility) return <Empty text={t("Student visibility data is unavailable.")} />;
  const profile = visibility.student;
  const identity = profile.user || student.user_detail;
  const included = visibility.policy?.included || [];
  const excluded = visibility.policy?.excluded || [];
  const portfolio = [...visibility.achievements, ...visibility.researches, ...visibility.projects, ...visibility.internships, ...visibility.activities, ...visibility.honors];
  return <div className="section-stack school-student-360"><section className="student-overview-hero"><div className="student-overview-title"><button className="button quiet" onClick={onBack}>{t("← Students")}</button><div className="profile-identity"><span className="avatar large">{initials(fullName(identity))}</span><div><span className="eyebrow">{t("PRIVACY-SAFE STUDENT 360")}</span><h2>{fullName(identity)}</h2><p>{joinParts(identity.email, profile.school_name)}</p></div></div><div className="panel-actions">{isPlatformAdmin(user) && <button className="button quiet" onClick={() => setSupportOpen(true)}><LifeBuoy size={16} /> {t("Support view")}</button>}<button className="button quiet" onClick={() => setCredentialOpen(true)}><Fingerprint size={16} /> {t("Reset login")}</button></div></div><div className="overview-progress"><strong>{formatPercentLocale(profile.journey_progress_percent || 0)}</strong><span>{t("Overall progress")}</span><div className="progress wide"><span style={{ width: `${profile.journey_progress_percent || 0}%` }} /></div></div></section><section className="visibility-policy"><div><ShieldCheck size={22} /><div><span className="eyebrow">{t("DATA VISIBILITY POLICY")}</span><h3>{visibility.policy.access_scope === 'global' ? t("Global admin scope") : t("Own-school scope")}</h3><p>{t("Admissions data is read-only here. Sensitive communication, credentials, and internal notes require a separate authorized workflow.")}</p></div></div><Badge tone="success">{t("Read only")}</Badge><details><summary>{t("What is visible")}</summary><div className="visibility-tags included">{included.map((item) => <span key={item}>{visibilityPolicyLabel(item)}</span>)}</div></details><details><summary>{t("What is protected")}</summary><div className="visibility-tags protected">{excluded.map((item) => <span key={item}>{visibilityPolicyLabel(item)}</span>)}</div></details></section><div className="stat-grid"><Stat label={t("Level")} value={formatNumberLocale(profile.level ?? 1)} note={tx`${formatNumberLocale(profile.xp_total ?? 0)} XP`} /><Stat label={t("Tasks")} value={formatNumberLocale(visibility.tasks.length)} note={tx`${formatPercentLocale(profile.task_progress_percent || 0)} complete`} /><Stat label={t("Roadmap missions")} value={formatNumberLocale(visibility.roadmap.length)} note={tx`${formatPercentLocale(profile.roadmap_progress_percent || 0)} complete`} /><Stat label={t("Applications")} value={formatNumberLocale(visibility.applications.length)} /></div><div className="split-grid"><Panel title={t("Academic & planning")}><div className="detail-grid"><Detail label={t("Grade")} value={gradeText(profile.grade)} /><Detail label={t("GPA")} value={profile.gpa} /><Detail label={t("Target major")} value={profile.target_major} /><Detail label={t("Target countries")} value={profile.target_countries} /><Detail label={t("Parent contact")} value={profile.parent_contact} /><Detail label={t("Counselor")} value={profile.counselor_name} /></div><h3 className="test-score-heading">{t("Test scores")}</h3><TestScoreSummary student={profile} /></Panel><VisibilitySection title={t("Meetings")} items={visibility.meetings} /></div><div className="overview-grid"><VisibilitySection title={t("Tasks")} items={visibility.tasks} /><VisibilitySection title={t("Roadmap")} items={visibility.roadmap} /><VisibilitySection title={t("Applications")} items={visibility.applications} /><VisibilitySection title={t("Documents")} items={visibility.documents} onDocument={setDocument} /><VisibilitySection title={t("Essays")} items={visibility.essays} emptyText={NO_SHARED_ESSAYS} /><VisibilitySection title={t("Recommendations")} items={visibility.recommendations} /><VisibilitySection title={t("Portfolio & activities")} items={portfolio} onEvidence={setEvidence} /><VisibilitySection title={t("Program usage")} items={visibility.program_usage} /></div>{credentialOpen && <TemporaryCredentialModal account={{ ...identity, role: 'student' }} onClose={() => setCredentialOpen(false)} notify={notify} />}{supportOpen && <SupportViewModal account={identity} onClose={() => setSupportOpen(false)} notify={notify} />}{document && <DocumentPreviewModal document={document} onClose={() => setDocument(null)} notify={notify} />}{evidence && <EvidencePreviewModal item={evidence} onClose={() => setEvidence(null)} notify={notify} />}</div>;
}

export function StudentAssignmentModal({ user, data, onClose, onSaved, notify }) {
  const admin = isPlatformAdmin(user);
  const counselors = (data.accounts || []).filter((account) => account.role === 'counselor' && account.is_active && account.school);
  const [counselorId, setCounselorId] = useState(admin ? '' : String(user.id));
  const [candidates, setCandidates] = useState([]);
  const [selected, setSelected] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(!admin);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {setSelected([]);}, [admin, counselorId]);
  useEffect(() => {
    if (admin && !counselorId) {
      setCandidates([]);
      setLoading(false);
      return undefined;
    }
    // The server searches the whole school; wait for typing to pause and
    // cancel the previous request.
    const controller = new AbortController();
    setLoading(true);
    setError('');
    const timer = window.setTimeout(() => {
      api.studentAssignmentCandidates(admin ? counselorId : null, search, controller.signal).
      then((items) => {if (!controller.signal.aborted) setCandidates(items || []);}).
      catch((requestError) => {if (!controller.signal.aborted && requestError?.name !== 'AbortError') setError(requestError.message);}).
      finally(() => {if (!controller.signal.aborted) setLoading(false);});
    }, search.trim() ? 300 : 0);
    return () => {window.clearTimeout(timer);controller.abort();};
  }, [admin, counselorId, search]);

  const visible = candidates;
  const target = admin ? counselors.find((account) => String(account.id) === String(counselorId)) : user;
  const targetRoleLabel = label(target?.role || user.role);
  const toggle = (studentId) => setSelected((current) => current.includes(studentId) ? current.filter((id) => id !== studentId) : [...current, studentId]);

  async function submit(event) {
    event.preventDefault();
    if (!selected.length) {setError(t("Select at least one student."));return;}
    setSaving(true);
    setError('');
    try {
      await api.assignCounselorStudents({ counselor: Number(counselorId), students: selected });
      notify(t("Students connected."));
      onSaved();
    } catch (requestError) {setError(requestError.message);} finally {setSaving(false);}
  }

  return <Modal title={admin ? t("Assign counselor") : t("Connect students")} onClose={onClose}><form className="student-assignment-form" onSubmit={submit}>
    {admin && <Field label={t("Counselor")}><select value={counselorId} onChange={(event) => setCounselorId(event.target.value)} required><option value="">{t("Select a counselor")}</option>{counselors.map((account) => <option key={account.id} value={account.id}>{fullName(account)} · {account.school_name}</option>)}</select></Field>}
    <p className="form-note form-wide"><ShieldCheck size={16} />{admin ? t("Admins can reassign students only to an active counselor from the same school.") : t("You can connect only unassigned students from your own school.")}</p>
    {target && <div className="assignment-target form-wide"><span className="avatar">{initials(fullName(target))}</span><div><b>{fullName(target)}</b><small>{target.school_name || targetRoleLabel}</small></div><Badge>{`${formatNumberLocale(candidates.length)} ${t("available")}`}</Badge></div>}
    {(counselorId || !admin) && <fieldset className="member-picker assignment-picker form-wide"><legend>{formatNumberLocale(selected.length)} {t("selected")}</legend><div className="assignment-tools"><label className="member-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("Search students")} /></label><div className="audience-shortcuts"><button type="button" onClick={() => setSelected(visible.map((student) => student.id))}>{t("Select all")}</button><button type="button" onClick={() => setSelected([])}>{t("Clear")}</button></div></div><div className="assignment-candidate-list">{visible.map((student) => <CheckboxControl key={student.id} checked={selected.includes(student.id)} onChange={() => toggle(student.id)}><span className="assignment-candidate-copy"><b>{fullName(student.user_detail)}</b><small>{joinParts(student.user_detail?.email, gradeText(student.grade))}</small></span><Badge>{student.counselor_name ? t("Reassign") : t("Unassigned")}</Badge></CheckboxControl>)}</div>{loading && <small>{t("Loading students…")}</small>}{!loading && !visible.length && <small>{admin && !counselorId ? t("Select a counselor first.") : t("No students are available for assignment in this school.")}</small>}</fieldset>}
    {error && <div className="alert error form-wide">{error}</div>}
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || loading || !selected.length} aria-busy={saving}>{saving ? t("Connecting…") : t("Connect selected students")}</button></div>
  </form></Modal>;
}

// The open student is part of the URL (/students/15), so a reload, a bookmark
// or back/forward reopens the same profile.
export function StudentsPage({ user, data, query, reload, notify, studentId = null, onStudent = () => {} }) {
  const [school, setSchool] = useState('');
  const [grade, setGrade] = useState('');
  const students = usePagedList('students', { search: query, filters: { school, grade }, ordering: 'name', pageSize: 50 });
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(false);
  const [assignmentOpen, setAssignmentOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [selectedError, setSelectedError] = useState('');
  const [visibility, setVisibility] = useState(null);
  const [visibilityLoading, setVisibilityLoading] = useState(false);
  const [visibilityError, setVisibilityError] = useState('');
  const schoolView = isPlatformAdmin(user) || user.role === 'organization';
  // Rows already on screen open without another request.
  const listed = useRef([]);
  listed.current = [...students.items, ...data.students];

  // Opening student B while A's data is still loading must never show A's data.
  const studentRequest = useRef(createLatestRequest()).current;
  useEffect(() => {
    setVisibility(null);
    setVisibilityError('');
    setSelectedError('');
    if (!studentId) {
      studentRequest.cancel();
      setSelected(null);
      setVisibilityLoading(false);
      return;
    }
    const isCurrent = studentRequest.start();
    const known = listed.current.find((item) => item.id === studentId) || null;
    setSelected(known);
    setVisibilityLoading(schoolView);
    if (schoolView) {
      api.studentDataVisibility(studentId).then(
        (result) => {if (isCurrent()) setVisibility(result);},
        (error) => {if (isCurrent()) setVisibilityError(error.message);},
      ).finally(() => {if (isCurrent()) setVisibilityLoading(false);});
    } else if (!known) {
      api.retrieve('students', studentId).then(
        (student) => {if (isCurrent()) setSelected(student);},
        (error) => {if (isCurrent()) setSelectedError(error.status === 404 ? t("Student profile not found.") : error.message);},
      );
    }
  }, [studentId, schoolView, studentRequest]);
  const openStudent = (student) => onStudent(student.id);
  const closeStudent = () => onStudent(null);

  async function deactivate(student) {
    if (!window.confirm(tx`Deactivate ${fullName(student.user_detail)}? They can no longer sign in. Their data is kept.`)) return;
    try {await api.remove('students', student.id);notify(t("Student deactivated."));reload();} catch (err) {notify(err.message, 'error');}
  }

  async function approveLevel(student) {
    try {
      const result = await api.approveStudentLevel(student.id);
      notify(tx`Level ${result.level} approved.`);
      reload();
    } catch (err) {notify(err.message, 'error');}
  }

  if (studentId && schoolView) return <SchoolStudent360 visibility={visibility} student={selected || { id: studentId }} loading={visibilityLoading || (!visibility && !visibilityError)} error={visibilityError} onBack={closeStudent} user={user} notify={notify} />;
  if (studentId && selectedError) return <div className="section-stack"><button className="button quiet back-button" onClick={closeStudent}>{t("← Students")}</button><div className="alert error" role="alert">{selectedError}</div></div>;
  if (studentId && selected?.id !== studentId) return <PageSkeleton />;
  if (studentId) return <StudentOverview student={students.items.find((item) => item.id === studentId) || selected} data={data} onBack={closeStudent} user={user} notify={notify} />;

  const actions = user.role !== 'teacher' && <div className="panel-actions">{isCounselor(user) && <button className="button quiet" onClick={() => setAssignmentOpen(true)}><UsersRound size={17} /> {isPlatformAdmin(user) ? t("Assign counselor") : t("Connect students")}</button>}<button className="button primary" onClick={() => {setEditing(null);setOpen(true);}}><Plus size={17} /> {t("Add student")}</button></div>;
  return <>
    <Panel title={t("Students")} action={actions}>
      <div className="paged-list-filters">
        {isPlatformAdmin(user) && <label><span>{t("School")}</span><select value={school} onChange={(event) => setSchool(event.target.value)}><option value="">{t("All schools")}</option>{data.schools.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        <label><span>{t("Grade")}</span><select value={grade} onChange={(event) => setGrade(event.target.value)}><option value="">{t("All grades")}</option>{['8', '9', '10', '11', 'gap'].map((value) => <option key={value} value={value}>{value === 'gap' ? t("Gap year") : value}</option>)}</select></label>
      </div>
      {students.loading && !students.items.length ? <PageSkeleton /> : <StudentTable data={data} students={students.items} onView={openStudent} onApproveLevel={isTaskManager(user) ? approveLevel : undefined} onEdit={user.role !== 'teacher' ? (student) => {setEditing(student);setOpen(true);} : undefined} onDeactivate={isPlatformAdmin(user) ? deactivate : undefined} />}
      <PagedListError list={students} />
      <LoadMore list={students} />
    </Panel>
    {open && <StudentForm user={user} data={data} student={editing} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}
    {assignmentOpen && <StudentAssignmentModal user={user} data={data} onClose={() => setAssignmentOpen(false)} onSaved={() => {setAssignmentOpen(false);reload();}} notify={notify} />}
  </>;
}

export function StudentForm({ user, data, student, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault(); setSaving(true);
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try {
      if (student) await api.update('students', student.id, { notes: values.notes });
      else await api.quickCreateStudent(values);
      onSaved();
    } catch (error) { notify(error.message, 'error'); }
    finally { setSaving(false); }
  }
  return <Modal title={student ? t('Student notes') : t('Add student account')} onClose={onClose}>
    <form className="form-grid student-access-form" onSubmit={submit}>
      {student ? <Field label={t('Notes')}><textarea name="notes" defaultValue={student.notes} /></Field> : <>
        <Field label={t('Student name')}><input name="name" required autoComplete="off" /></Field>
        <Field label={t('Email')}><input name="email" type="email" /></Field>
        <Field label={t('Temporary password')} hint={t('Use at least 8 characters.')}><input name="password" type="password" minLength={8} required autoComplete="new-password" /></Field>
        {isPlatformAdmin(user) && <Field label={t('School')}><select name="school" required defaultValue=""><option value="">{t('Select school')}</option>{data.schools.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>}
        <p className="form-wide">{t('The student completes their profile after signing in.')}</p>
      </>}
      <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t('Cancel')}</button><button className="button primary" disabled={saving}>{saving ? t('Saving…') : t(student ? 'Save' : 'Create login')}</button></div>
    </form>
  </Modal>;
}
