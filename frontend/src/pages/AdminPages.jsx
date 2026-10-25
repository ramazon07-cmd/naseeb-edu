import { Stat } from '../components/records';
import './school-counselors.css';
import { t, tp, tx, formatNumberLocale, formatPercentLocale } from '../i18n';
import { Panel, Badge, Empty, Modal } from '../components/ui';
import { AlertTriangle, Building2, ChevronRight, ExternalLink, Fingerprint, RefreshCw, UserRound, Compass, ShieldAlert, Plus, Pencil, Trash2, ShieldCheck, LifeBuoy } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { auditActionLabel, auditGroupOptions, fullName, initials, label } from '../lib/labels';
import { auditDetailLines } from '../lib/auditDetails';
import { api } from '../api';
import { CheckboxControl, ChoiceCards, Field, PortalTabs } from '../components/forms';
import { PlanFacts } from '../components/plans';
import { OneTimePassword, TemporaryCredentialModal } from '../components/TemporaryCredentialModal';
import { PLAN_FEATURES } from '../lib/workspacePlan';
import { canManageWorkspaces, isPlatformAdmin, isSuperAdmin } from '../lib/roles';
import { auditFilters } from '../lib/auditQuery';
import { SupportViewModal } from '../components/SupportViewModal';
import { ModerationCard, moderateReport } from '../components/moderation';
import { dateText, dateTimeText, formatFileSize, joinParts } from '../lib/format';
import { attentionRows } from '../lib/adminAttention';
import { InlineLoadError } from '../components/states';
import { FEATURES } from '../lib/features';
import { invalidatePagedLists, usePagedList } from '../hooks/usePagedList';
import { AccountPicker, LoadMore, PagedListError, SchoolPicker, firstPageLoading } from '../components/paged';

const ACTIVE_ORGANIZATION_SCHOOLS = { workspace_type: 'school', is_active: 'true' };
const ACTIVE_COUNSELORS = { role: 'counselor', is_active: 'true' };

export function AdminControlDashboard({ user, stats, setPage }) {
  // One request for every number (/api/admin/summary/), never by loading every school.
  const summary = useAdminRequest(loadSummary);
  const { data } = summary;
  // A skeleton while loading and a dash after a failure: a missing number is never shown as 0.
  const tile = (value) => (data ? formatNumberLocale(value) : summary.error ? '—' : <span className="stat-skeleton" aria-hidden="true" />);
  // Quick links describe only what this staff tier can do on those pages.
  const manage = canManageWorkspaces(user);
  const reviewer = isSuperAdmin(user);
  return <div className="section-stack"><div className="stat-grid" aria-busy={summary.loading}><Stat label={t("Schools")} value={tile(data?.schools_active)} note={t("Active organization workspaces")} /><Stat label={t("Counselors")} value={tile(data?.counselors_active)} note={data ? tx`${data.counselors_inactive} inactive` : undefined} /><Stat label={t("Students")} value={stats?.students_total ?? '—'} note={t("Available in Student 360")} /><article className="stat-card"><span>{t("Roadmap reviews")}</span><strong>{tile(data?.roadmap_missions_submitted)}</strong><small>{FEATURES.counselorRoadmapTemplates ? <button type="button" className="link-button admin-link" onClick={() => setPage('counselor_roadmap')}>{t("Submitted counselor missions")}</button> : t("Submitted counselor missions")}</small></article></div>{summary.error && <InlineLoadError message={summary.error} onRetry={summary.retry} />}<AttentionPanel summary={summary} setPage={setPage} /><AiUsagePanel /><Panel title={t("Platform administration")}><div className="quick-grid"><button onClick={() => setPage('admin_schools')}><Building2 /><span><b>{manage ? t("Manage schools") : t("Schools")}</b><small>{manage ? t("Provision organization accounts") : t("View workspaces and reset school logins")}</small></span></button><button onClick={() => setPage('admin_counselors')}><UserRound /><span><b>{manage ? t("Manage counselors") : t("Counselors")}</b><small>{manage ? t("Create, transfer, or deactivate") : t("View counselor accounts and open support views")}</small></span></button>{FEATURES.counselorRoadmapTemplates && <button onClick={() => setPage('counselor_roadmap')}><Compass /><span><b>{reviewer ? t("Review roadmaps") : t("Counselor roadmaps")}</b><small>{reviewer ? t("Approve submitted milestones") : t("Follow counselor milestones")}</small></span></button>}<button onClick={() => setPage('admin_audit')}><ShieldAlert /><span><b>{t("Open audit log")}</b><small>{t("Trace administration actions")}</small></span></button></div></Panel></div>;
}

function AttentionPanel({ summary, setPage }) {
  const rows = attentionRows(summary.data);
  let body;
  if (summary.error) body = <InlineLoadError message={summary.error} onRetry={summary.retry} />;
  else if (!summary.data) body = <p className="paged-list-loading" role="status">{t("Loading…")}</p>;
  else if (!rows.length) body = <Empty text={t("All clear: nothing needs attention today.")} />;
  else body = <ul className="attention-list">{rows.map((row) => {
    const content = <><AlertTriangle size={17} aria-hidden="true" /><span><b>{row.title}</b>{row.meta && <small>{row.meta}</small>}</span>{row.page && <ChevronRight className="attention-go" size={16} aria-hidden="true" />}</>;
    return <li key={row.key} className={`attention-${row.kind}`}>{row.page ? <button type="button" onClick={() => setPage(row.page)}>{content}</button> : <div>{content}</div>}</li>;
  })}</ul>;
  return <Panel title={t("Needs attention")}>{body}</Panel>;
}

export function AdminCounselorsPage({ user, query, reload, notify }) {
  const canManage = canManageWorkspaces(user);
  const [open, setOpen] = useState(false);
  const [transfer, setTransfer] = useState(null);
  const [editing, setEditing] = useState(null);
  const [supportTarget, setSupportTarget] = useState(null);
  const [credentialTarget, setCredentialTarget] = useState(null);
  const [handover, setHandover] = useState(null);
  // Paged and searched on the server; the roster is never loaded whole.
  const list = usePagedList('users/accounts', { search: query, filters: { role: 'counselor' }, ordering: 'name', pageSize: 50 });
  const counselors = list.items;
  async function deactivate(account) {
    if (!window.confirm(tx`Deactivate ${fullName(account)}? Their login will stop immediately.`)) return;
    try {await api.deactivateAccount(account.id);notify(t("Counselor deactivated."));reload();} catch (error) {
      // Their active students must go somewhere first; the server says how many.
      if (error.status === 409 && error.details?.code === 'counselor_has_students') setHandover({ account, students: Number(error.details.students) || 0 });
      else notify(error.message, 'error');
    }
  }
  return <><Panel title={t("Counselor provisioning")} action={canManage && <button className="button primary" onClick={() => setOpen(true)}><Plus size={16} /> {t("Add counselor")}</button>}><div className="record-list" aria-busy={list.loading}>{counselors.map((account) => <article className="record" key={account.id}><span className="avatar">{initials(fullName(account))}</span><div className="record-main"><h3>{fullName(account)}</h3><p>{joinParts(account.email, account.school_name || t("No school"))}</p><div className="record-meta"><Badge tone={account.is_active ? 'success' : 'danger'}>{account.is_active ? t("Active") : t("Inactive")}</Badge><span>{account.school_workspace_type === 'individual' ? t("Individual workspace") : t("Organization school")}</span></div></div><div className="record-actions"><button className="icon-button" onClick={() => setSupportTarget(account)} title={t("Support view")} aria-label={t("Support view")}><LifeBuoy size={16} /></button>{account.is_active && <button className="icon-button" onClick={() => setCredentialTarget(account)} title={t("Reset login")} aria-label={t("Reset login")}><Fingerprint size={16} /></button>}{canManage && <button className="icon-button" onClick={() => setEditing(account)} title={t("Edit counselor")}><Pencil size={16} /></button>}{canManage && account.is_active && account.school_workspace_type !== 'individual' && <button className="button quiet" onClick={() => setTransfer(account)}><Building2 size={15} /> {t("Transfer")}</button>}{canManage && account.is_active && <button className="icon-button danger" onClick={() => deactivate(account)} title={t("Deactivate counselor")}><Trash2 size={16} /></button>}</div></article>)}{firstPageLoading(list) && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}{list.loaded && !counselors.length && <Empty text={t("No counselors found.")} />}</div><PagedListError list={list} /><LoadMore list={list} /></Panel>{open && <CounselorProvisionForm onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}{editing && <CounselorEditForm account={editing} onClose={() => setEditing(null)} onSaved={() => {setEditing(null);reload();}} notify={notify} />}{transfer && <AccountTransferForm account={transfer} onClose={() => setTransfer(null)} onSaved={() => {setTransfer(null);reload();}} notify={notify} />}{supportTarget && <SupportViewModal account={supportTarget} onClose={() => setSupportTarget(null)} notify={notify} />}{credentialTarget && <TemporaryCredentialModal account={credentialTarget} onClose={() => setCredentialTarget(null)} notify={notify} />}{handover && <CounselorHandoverModal {...handover} notify={notify} onClose={() => setHandover(null)} onDone={() => {setHandover(null);list.reload();reload();}} />}</>;
}

const HANDOVER_OPTIONS = [
  { value: 'reassign', label: 'Reassign to another counselor', description: 'An active counselor of the same school takes them over.', icon: UserRound },
  { value: 'unassign', label: 'Leave them unassigned', description: 'They wait under “No counselor assigned” in Student 360.', icon: AlertTriangle },
];

// Deactivating a counselor who still has active students: say where those students go.
function CounselorHandoverModal({ account, students, changes, notify, onClose, onDone }) {
  const [choice, setChoice] = useState('reassign');
  const [target, setTarget] = useState('');
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    try {
      const handover = choice === 'reassign' ? { students: 'reassign', reassign_to: Number(target) } : { students: 'unassign' };
      if (changes) await api.update('users/accounts', account.id, { ...changes, ...handover });
      else await api.deactivateAccount(account.id, handover);
      notify(t("Counselor deactivated."));
      onDone();
    } catch (error) {notify(error.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={t("Deactivate counselor")} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <p className="form-wide">{tp('{n} active student is assigned to {name}.|{n} active students are assigned to {name}.', students, { n: formatNumberLocale(students), name: fullName(account) })}</p>
    <div className="form-wide"><ChoiceCards name="handover" label={t("Students")} value={choice} onChange={setChoice} options={HANDOVER_OPTIONS} /></div>
    {choice === 'reassign' && <AccountPicker name="reassign_to" label="Counselor" required value={target} onChange={setTarget} filters={{ ...ACTIVE_COUNSELORS, school: account.school }} />}
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || (choice === 'reassign' && (!target || Number(target) === account.id))} aria-busy={saving}>{t("Deactivate")}</button></div>
  </form></Modal>;
}

export function CounselorEditForm({ account, schoolManaged = false, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [handover, setHandover] = useState(null);
  const [accessEnabled, setAccessEnabled] = useState(account.is_active);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    const changes = { first_name: values.get('first_name'), last_name: values.get('last_name'), ...(!schoolManaged ? { email: values.get('email') } : {}), phone: values.get('phone'), is_active: accessEnabled };
    try {
      await api.update('users/accounts', account.id, changes);
      notify(t("Counselor updated."));
      onSaved();
    } catch (error) {
      if (error.status === 409 && error.details?.code === 'counselor_has_students') setHandover({ students: Number(error.details.students) || 0, changes });
      else notify(error.message, 'error');
    } finally {setSaving(false);}
  }
  if (handover) return <CounselorHandoverModal account={account} {...handover} notify={notify} onClose={() => setHandover(null)} onDone={onSaved} />;
  return <Modal title={t("Edit counselor")} className="counselor-modal" onClose={onClose}>
    <form className="form-grid" onSubmit={submit}>
      <Field label={t("First name")}><input name="first_name" defaultValue={account.first_name} placeholder={t("e.g. Dilnoza")} required /></Field>
      <Field label={t("Last name")}><input name="last_name" defaultValue={account.last_name} placeholder={t("e.g. Karimova")} /></Field>
      <Field label={t("Phone")}><input name="phone" type="tel" defaultValue={account.phone} placeholder={t("e.g. +998 90 123 45 67")} /></Field>
      <Field label={t("Email")}><input name="email" type="email" defaultValue={account.email} readOnly={schoolManaged} required /></Field>
      <div className="counselor-access form-wide">
        <div><b>{t("Allow platform access")}</b><p>{accessEnabled ? t("The counselor can sign in and work with students.") : t("Sign-in will be blocked. The counselor's records are kept.")}</p><small>{t("Changes apply when you save.")}</small></div>
        <button type="button" className="counselor-access-switch" role="switch" aria-checked={accessEnabled} aria-label={t("Allow platform access")} onClick={() => setAccessEnabled(!accessEnabled)} />
      </div>
      <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : t("Save")}</button></div>
    </form>
  </Modal>;
}

export function CounselorProvisionForm({ schoolManaged = false, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
      if (!schoolManaged) payload.school = Number(payload.school);
      await api.createCounselor(payload);
      notify(t("Counselor account created."));
      onSaved();
    } catch (error) {
      setError(error.message);
    } finally { setSaving(false); }
  }
  return <Modal title={t("Add school counselor")} className="counselor-modal" onClose={onClose}>
    <form className="form-grid counselor-create-form" onSubmit={submit} autoComplete="off">
      <p className="counselor-form-intro form-wide">{t("Create a login for your counselor. They will set their own password at first sign-in.")}</p>
      <Field label={t("First name")}><input name="first_name" placeholder={t("e.g. Dilnoza")} required maxLength={150} /></Field>
      <Field label={t("Last name")}><input name="last_name" placeholder={t("e.g. Karimova")} maxLength={150} /></Field>
      <Field label={t("Username")}><input name="username" placeholder={t("e.g. d.karimova")} autoComplete="off" autoCapitalize="none" spellCheck={false} required maxLength={150} /></Field>
      <Field label={t("Email")}><input name="email" type="email" placeholder={t("e.g. name@example.com")} autoComplete="off" autoCapitalize="none" spellCheck={false} required /></Field>
      {!schoolManaged && <div className="form-wide"><SchoolPicker label="Organization school" required filters={ACTIVE_ORGANIZATION_SCHOOLS} /></div>}
      <div className="form-wide counselor-password-field"><Field label={t("Temporary password")} hint={t("Share this password privately with the counselor.")}><input name="password" type="password" minLength={8} autoComplete="new-password" required /></Field></div>
      {error && <p className="counselor-form-error form-wide" role="alert">{error}</p>}
      <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Creating…") : t("Create counselor")}</button></div>
    </form>
  </Modal>;
}

export function AccountTransferForm({ account, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();const school = Number(new FormData(event.currentTarget).get('school'));if (school === account.school) {notify(t("Choose a school other than the counselor's current one."), 'error');return;}if (!window.confirm(t("Confirm counselor transfer?"))) return;setSaving(true);try {await api.transferCounselor(account.id, school);notify(t("Counselor transferred."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  return <Modal title={t("Transfer counselor")} onClose={onClose}><form className="form-grid" onSubmit={submit}><SchoolPicker label="Organization school" required filters={ACTIVE_ORGANIZATION_SCHOOLS} /><p className="form-note form-wide">{t("Transfer is blocked until assigned students belong to the destination school and a counselor slot is available.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{t("Transfer")}</button></div></form></Modal>;
}

export function CounselorRoadmapPage({ user, data, reload, notify }) {
  const [templateOpen, setTemplateOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [assignOpen, setAssignOpen] = useState(false);
  const [selfAssignOpen, setSelfAssignOpen] = useState(false);
  const [missionAction, setMissionAction] = useState(null);
  const [tab, setTab] = useState('queue');
  const [togglingId, setTogglingId] = useState(null);
  const templates = data.counselorRoadmapTemplates.filter((template) => template.is_active);
  const admin = isPlatformAdmin(user);
  // Templates, assignments and reviews are super-admin writes on the API.
  const canControl = admin && isSuperAdmin(user);
  async function toggleTemplate(template) {
    setTogglingId(template.id);
    try {await api.update('counselor-roadmap-templates', template.id, { is_active: !template.is_active });notify(template.is_active ? t("Template deactivated.") : t("Template reactivated."));reload();} catch (error) {notify(error.message, 'error');} finally {setTogglingId(null);}
  }
  function missionDone() {
    setMissionAction(null);
    invalidatePagedLists([REVIEW_QUEUE]);
    reload();
  }
  const actions = admin ? canControl && <div className="panel-actions"><button className="button quiet" onClick={() => setTemplateOpen(true)}><Plus size={16} /> {t("New template")}</button><button className="button primary" onClick={() => setAssignOpen(true)}><Compass size={16} /> {t("Assign roadmap")}</button></div> : <button className="button primary" onClick={() => setSelfAssignOpen(true)}><Compass size={16} /> {t("Start my roadmap")}</button>;
  const emptyText = user.role === 'counselor' ? t("Create your own roadmap or begin from an active template.") : t("No counselor roadmaps assigned yet.");
  const roadmapsList = <div className="record-list">{data.counselorRoadmaps.map((roadmap) => <article className="roadmap-admin-card" key={roadmap.id}><header><div><span className="eyebrow">{label(roadmap.kind)}</span><h3>{roadmap.title}</h3><p>{joinParts(roadmap.counselor_name, roadmap.school_name)}</p></div><div className="roadmap-progress"><b>{formatPercentLocale(roadmap.progress_percent)}</b><Badge tone={roadmap.status === 'completed' ? 'success' : ''}>{label(roadmap.status)}</Badge></div></header><div className="roadmap-admin-missions">{roadmap.missions.map((mission) => <div key={mission.id}><span className={`status-dot ${mission.status}`} /><div><b>{mission.sequence}. {mission.title}</b><small>{joinParts(label(mission.status), mission.due_date && tx`Due ${dateText(mission.due_date)}`)}</small>{mission.counselor_note && <p>{mission.counselor_note}</p>}{mission.admin_feedback && <p className="form-note">{mission.admin_feedback}</p>}</div><div>{user.role === 'counselor' && mission.status !== 'approved' && <button className="button quiet" onClick={() => setMissionAction({ roadmapId: roadmap.id, mission, decision: 'submit' })}>{t("Submit")}</button>}{canControl && mission.status === 'submitted' && <><button className="button quiet" onClick={() => setMissionAction({ roadmapId: roadmap.id, mission, decision: 'request_changes' })}>{t("Request changes")}</button><button className="button primary" onClick={() => setMissionAction({ roadmapId: roadmap.id, mission, decision: 'approve' })}>{t("Approve")}</button></>}</div></div>)}</div></article>)}{!data.counselorRoadmaps.length && <Empty text={emptyText} />}</div>;
  const adminContent = <><div className="roadmap-control-tabs"><PortalTabs active={tab} onChange={setTab} items={[['queue', 'Waiting for review'], ['roadmaps', 'All roadmaps'], ['templates', 'Templates']]} /></div>{tab === 'queue' ? <MissionReviewQueue canControl={canControl} onReview={(mission, decision) => setMissionAction({ roadmapId: mission.roadmap, mission, decision })} /> : tab === 'templates' ? <RoadmapTemplateList templates={data.counselorRoadmapTemplates} canControl={canControl} busyId={togglingId} onEdit={setEditingTemplate} onToggle={toggleTemplate} /> : roadmapsList}</>;
  return <><Panel title={admin ? t("Counselor roadmap control") : t("My professional roadmap")} action={actions}>{admin && !canControl && <p className="form-note staff-tier-note"><ShieldCheck size={16} /> {t("Only super admins can create templates, assign roadmaps and review missions.")}</p>}{admin ? adminContent : roadmapsList}</Panel>{(templateOpen || editingTemplate) && <RoadmapTemplateForm template={editingTemplate} onClose={() => {setTemplateOpen(false);setEditingTemplate(null);}} onSaved={() => {setTemplateOpen(false);setEditingTemplate(null);reload();}} notify={notify} />}{assignOpen && <RoadmapAssignForm data={data} onClose={() => setAssignOpen(false)} onSaved={() => {setAssignOpen(false);reload();}} notify={notify} />}{selfAssignOpen && <RoadmapSelfAssignForm templates={templates} onClose={() => setSelfAssignOpen(false)} onSaved={() => {setSelfAssignOpen(false);reload();}} notify={notify} />}{missionAction && <MissionActionModal {...missionAction} onClose={() => setMissionAction(null)} onDone={missionDone} notify={notify} />}</>;
}

const REVIEW_QUEUE = 'counselor-roadmaps/review-queue';

const REPORT_STATUSES = [['pending', 'Pending'], ['reviewing', 'Reviewing'], ['resolved', 'Resolved'], ['dismissed', 'Dismissed']];

// Reported messages from every school, a page at a time. Only the reported message is
// shown, never the rest of the chat; a moderator never decides on their own message.
export function AdminModerationPage({ notify }) {
  const [status, setStatus] = useState('pending');
  const [school, setSchool] = useState('');
  const [notes, setNotes] = useState({});
  const [savingId, setSavingId] = useState(null);
  const list = usePagedList('message-reports', { filters: { status, school }, pageSize: 25 });
  async function moderate(report, mode, action) {
    setSavingId(report.id);
    try {notify(await moderateReport(report, mode, action, notes[report.id] || ''));list.reload();} catch (error) {notify(error.message, 'error');} finally {setSavingId(null);}
  }
  return <Panel title={t("Moderation")}><div className="moderation-queue"><div className="roadmap-control-tabs"><PortalTabs active={status} onChange={setStatus} items={REPORT_STATUSES} /></div><div className="paged-list-filters"><SchoolPicker label="School" value={school} onChange={setSchool} emptyOption={t("All schools")} /></div><div className="moderation-list" aria-busy={list.loading}>{list.items.map((report) => <ModerationCard key={report.id} report={report} note={notes[report.id] || ''} onNote={(value) => setNotes((current) => ({ ...current, [report.id]: value }))} saving={savingId === report.id} onModerate={(mode, action) => moderate(report, mode, action)} />)}{firstPageLoading(list) && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}{list.loaded && !list.items.length && <Empty text={t("No reports with this status.")} />}</div><PagedListError list={list} /><LoadMore list={list} /></div></Panel>;
}

// Submitted counselor missions, oldest first, a page at a time (the Admin Control tile opens here).
function MissionReviewQueue({ canControl, onReview }) {
  const [school, setSchool] = useState('');
  const [counselor, setCounselor] = useState('');
  const list = usePagedList(REVIEW_QUEUE, { filters: { school, counselor }, pageSize: 25 });
  return <>
    <div className="paged-list-filters"><SchoolPicker label="School" value={school} onChange={setSchool} emptyOption={t("All schools")} /><AccountPicker label="Counselor" value={counselor} onChange={setCounselor} emptyOption={t("Any counselor")} filters={ACTIVE_COUNSELORS} /></div>
    <div className="record-list" aria-busy={list.loading}>{list.items.map((mission) => <article className="record roadmap-queue-row" key={mission.id}><div className="record-main"><h3>{mission.title}</h3><p>{joinParts(mission.counselor_name, mission.school_name, mission.roadmap_title)}</p>{mission.submitted_at && <small>{tx`Submitted ${dateText(mission.submitted_at)}`}</small>}{mission.counselor_note && <p>{mission.counselor_note}</p>}</div>{canControl && <div className="record-actions"><button className="button quiet" onClick={() => onReview(mission, 'request_changes')}>{t("Request changes")}</button><button className="button primary" onClick={() => onReview(mission, 'approve')}>{t("Approve")}</button></div>}</article>)}{firstPageLoading(list) && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}{list.loaded && !list.items.length && <Empty text={t("No missions waiting for review")} />}</div>
    <PagedListError list={list} /><LoadMore list={list} />
  </>;
}

function RoadmapTemplateList({ templates, canControl, busyId, onEdit, onToggle }) {
  return <div className="record-list">{templates.map((template) => <article className="record" key={template.id}><div className="record-main"><h3>{template.name}</h3><p>{joinParts(label(template.kind), tp('{n} mission|{n} missions', template.missions.length, { n: formatNumberLocale(template.missions.length) }))}</p><div className="record-meta"><Badge tone={template.is_active ? 'success' : 'muted'}>{template.is_active ? t("Active") : t("Inactive")}</Badge></div></div>{canControl && <div className="record-actions"><button className="icon-button" onClick={() => onEdit(template)} title={t("Edit template")} aria-label={tx`Edit ${template.name}`}><Pencil size={16} /></button><button className="button quiet" disabled={busyId === template.id} aria-busy={busyId === template.id} onClick={() => onToggle(template)}>{template.is_active ? t("Deactivate") : t("Reactivate")}</button></div>}</article>)}{!templates.length && <Empty text={t("No roadmap templates yet.")} />}</div>;
}

// One in-app dialog for a counselor's submission and an admin's review (no browser prompts).
const MISSION_ACTIONS = {
  submit: { title: 'Submit mission', field: 'Add a completion note', button: 'Submit', done: 'Mission submitted for review.', required: true },
  approve: { title: 'Approve mission', field: 'Feedback for the counselor', button: 'Approve', done: 'Mission approved.', required: false },
  request_changes: { title: 'Request changes', field: 'Explain the requested changes', button: 'Request changes', done: 'Changes requested.', required: true },
};

function MissionActionModal({ roadmapId, mission, decision, onClose, onDone, notify }) {
  const copy = MISSION_ACTIONS[decision];
  const [text, setText] = useState(decision === 'submit' ? mission.counselor_note || '' : '');
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    try {
      if (decision === 'submit') await api.submitCounselorMission(roadmapId, mission.id, text.trim());
      else await api.reviewCounselorMission(roadmapId, mission.id, decision, text.trim());
      notify(t(copy.done));
      onDone();
    } catch (error) {notify(error.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={t(copy.title)} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <p className="form-wide"><b>{mission.title}</b></p>
    <Field className="form-wide" label={t(copy.field)}><textarea value={text} onChange={(event) => setText(event.target.value)} required={copy.required} rows="4" /></Field>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || (copy.required && !text.trim())} aria-busy={saving}>{t(copy.button)}</button></div>
  </form></Modal>;
}

export function RoadmapSelfAssignForm({ templates, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [templateId, setTemplateId] = useState('');
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      const payload = templateId ? {
        template: Number(templateId),
        title: values.get('title'),
      } : {
        title: values.get('title'),
        kind: values.get('kind'),
        missions: String(values.get('missions')).split('\n').map((title) => title.trim()).filter(Boolean).map((title) => ({ title })),
      };
      await api.create('counselor-roadmaps', payload);
      notify(t("Roadmap started."));
      onSaved();
    } catch (error) {
      notify(error.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("Start my roadmap")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field className="form-wide" label={t("Roadmap source")}><select name="template" value={templateId} onChange={(event) => setTemplateId(event.target.value)}><option value="">{t("Create my own roadmap")}</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.name} · {label(template.kind)}</option>)}</select></Field><Field className="form-wide" label={templateId ? t("Custom title (optional)") : t("Roadmap title")}><input name="title" placeholder={t("e.g. New counselor onboarding")} required={!templateId} /></Field>{!templateId && <><Field label={t("Roadmap type")}><select name="kind"><option value="professional_onboarding">{t("Professional onboarding")}</option><option value="school_management">{t("School management")}</option></select></Field><Field className="form-wide" label={t("Missions, one per line")}><textarea name="missions" rows="6" placeholder={t("e.g. Complete your counselor profile")} required /></Field></>}<p className="form-note form-wide"><Compass size={16} /> {t("You can start one active roadmap for each roadmap type.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{saving ? t("Starting…") : t("Start roadmap")}</button></div></form></Modal>;
}

// `template`: edit it; a mission whose title stays keeps its description, due days and required flag.
export function RoadmapTemplateForm({ template = null, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);const kept = Object.fromEntries((template?.missions || []).map((mission) => [mission.title, mission]));const missions = String(values.get('missions')).split('\n').map((title) => title.trim()).filter(Boolean).map((title, index) => ({ title, description: kept[title]?.description || '', sequence: index + 1, due_days: kept[title]?.due_days ?? (index + 1) * 7, is_required: kept[title]?.is_required ?? true }));const payload = { name: values.get('name'), description: values.get('description'), kind: values.get('kind'), missions };try {if (template) await api.update('counselor-roadmap-templates', template.id, payload);else await api.create('counselor-roadmap-templates', { ...payload, is_active: true });notify(template ? t("Roadmap template updated.") : t("Roadmap template created."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  return <Modal title={template ? t("Edit template") : t("New counselor roadmap template")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Template name")}><input name="name" defaultValue={template?.name} placeholder={t("e.g. New counselor onboarding")} required /></Field><Field label={t("Roadmap type")}><select name="kind" defaultValue={template?.kind}><option value="professional_onboarding">{t("Professional onboarding")}</option><option value="school_management">{t("School management")}</option></select></Field><Field className="form-wide" label={t("Description")}><textarea name="description" defaultValue={template?.description} placeholder={t("e.g. A four-week plan for counselors joining a school")} /></Field><Field className="form-wide" label={t("Missions, one per line")}><textarea name="missions" defaultValue={template?.missions.map((mission) => mission.title).join('\n')} placeholder={t("e.g. Complete your counselor profile")} required rows="6" /></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{template ? t("Save template") : t("Create template")}</button></div></form></Modal>;
}

export function RoadmapAssignForm({ data, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);try {await api.create('counselor-roadmaps', { counselor: Number(values.get('counselor')), template: Number(values.get('template')), title: values.get('title') });notify(t("Roadmap assigned."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  return <Modal title={t("Assign counselor roadmap")} onClose={onClose}><form className="form-grid" onSubmit={submit}><AccountPicker name="counselor" label="Counselor" required filters={ACTIVE_COUNSELORS} /><Field label={t("Template")}><select name="template" required><option value="">{t("Select a template")}</option>{data.counselorRoadmapTemplates.filter((template) => template.is_active).map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}</select></Field><Field className="form-wide" label={t("Custom title (optional)")}><input name="title" placeholder={t("e.g. Autumn onboarding plan")} /></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{t("Assign roadmap")}</button></div></form></Modal>;
}

const EMPTY_AUDIT_FILTERS = { action: '', actor: '', school: '', date_from: '', date_to: '' };

// The audit log is filtered and paged on the server; it is never loaded whole.
export function AdminAuditPage({ query }) {
  const [filters, setFilters] = useState(EMPTY_AUDIT_FILTERS);
  const list = usePagedList('users/audit-events', { search: query, filters: auditFilters(filters), ordering: '-created', pageSize: 50 });
  const events = list.items;
  function change(key, value) {setFilters((current) => ({ ...current, [key]: value }));}
  const filterBar = <div className="audit-filters">
    <Field label={t("Action")}><select value={filters.action} onChange={(event) => change('action', event.target.value)}><option value="">{t("All actions")}</option>{auditGroupOptions().map(([prefix, title]) => <option key={prefix} value={prefix}>{title}</option>)}</select></Field>
    <AccountPicker label="Actor" value={filters.actor} onChange={(value) => change('actor', value)} emptyOption={t("Everyone")} />
    <SchoolPicker label="School" value={filters.school} onChange={(value) => change('school', value)} emptyOption={t("All schools")} />
    <Field label={t("From")}><input type="date" value={filters.date_from} onChange={(event) => change('date_from', event.target.value)} /></Field>
    <Field label={t("To")}><input type="date" value={filters.date_to} onChange={(event) => change('date_to', event.target.value)} /></Field>
  </div>;
  return <Panel title={t("Product administration audit")}>{filterBar}<div className="record-list audit-list" aria-busy={list.loading}>{events.map((event) => <AuditRecord key={event.id} event={event} />)}{firstPageLoading(list) && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}{list.loaded && !events.length && <Empty text={t("No audit events found.")} />}</div><PagedListError list={list} /><LoadMore list={list} /></Panel>;
}

function AuditRecord({ event }) {
  const details = auditDetailLines(event);
  return <article className="record">
    <ShieldCheck size={20} />
    <div className="record-main">
      <h3>{auditActionLabel(event.action)}</h3>
      <p>{event.target_label || event.target_type}</p>
      <div className="record-meta"><span>{event.actor_name || t("System")}</span>{event.school_name && <span>{event.school_name}</span>}<span>{dateTimeText(event.created_at)}</span></div>
      {details.length > 0 && <details className="audit-details"><summary>{t("Details")}</summary><dl>{details.map((line) => <div key={line.key}><dt>{line.label}</dt><dd>{line.value}</dd></div>)}</dl></details>}
    </div>
  </article>;
}

const AI_FEATURES = [['assistant', 'AI assistant'], ['essay_coach', 'Essay coach'], ['recommendation_letter', 'Letter suggestions']];

// Paid AI calls today against the daily caps (#39); counters only, no student content.
function AiUsagePanel() {
  const usage = useAdminRequest(loadAiUsage);
  let body;
  if (usage.error) body = <InlineLoadError message={usage.error} onRetry={usage.retry} />;
  else if (!usage.data) body = <p className="paged-list-loading" role="status">{t("Loading…")}</p>;
  else if (!usage.data.cache_available) body = <p className="form-note"><AlertTriangle size={16} /> {t("Usage unavailable: the cache is down, so today's counts cannot be read.")}</p>;
  else body = <div className="ai-usage">{AI_FEATURES.map(([key, title]) => <AiUsageRow key={key} title={title} usage={usage.data.features[key]} />)}{usage.data.fallback_active && <p className="form-note"><AlertTriangle size={16} /> {t("The cache was unreachable earlier today; calls ran on each server's small fallback allowance.")}</p>}</div>;
  return <Panel title={t("AI usage today")}>{body}</Panel>;
}

function AiUsageRow({ title, usage }) {
  const share = usage.limit ? Math.min(100, Math.round((usage.used / usage.limit) * 100)) : null;
  const warn = share !== null && share >= 80;
  const caption = usage.limit === 0 ? t("Turned off: the daily cap is 0.") : usage.limit ? tx`${formatNumberLocale(usage.used)} of ${formatNumberLocale(usage.limit)} calls` : tx`${formatNumberLocale(usage.used)} calls, no daily cap`;
  return <div className={`ai-usage-row ${warn ? 'warn' : ''}`}>
    <div className="ai-usage-head"><b>{t(title)}</b><span>{caption}</span></div>
    {share !== null && <div className="ai-usage-bar" role="progressbar" aria-label={t(title)} aria-valuemin={0} aria-valuemax={100} aria-valuenow={share}><span style={{ width: `${share}%` }} /></div>}
    {(warn || usage.refused > 0) && <small>{joinParts(warn && t("80% or more of today's cap is used."), usage.refused > 0 && tp('{n} call refused at a cap|{n} calls refused at a cap', usage.refused, { n: usage.refused }))}</small>}
    {usage.top_schools.length > 0 && <small>{t("Busiest schools")}: {usage.top_schools.map((row) => `${row.name} (${formatNumberLocale(row.used)})`).join(', ')}</small>}
  </div>;
}

const loadSummary = () => api.adminSummary();
const loadAiUsage = () => api.adminAiUsage();
const loadPlans = () => api.plans();

// One admin request with loading, error and retry; the data stays on screen while it refreshes.
function useAdminRequest(load) {
  const [state, setState] = useState({ data: null, error: '', loading: true });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, error: '', loading: true }));
    load().then(
      (data) => {if (active) setState({ data, error: '', loading: false });},
      (error) => {if (active) setState({ data: null, error: error.message, loading: false });},
    );
    return () => {active = false;};
  }, [load, attempt]);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return { ...state, retry };
}

const PLAN_LIMIT_FIELDS = [['max_counselors', 'Counselor limit'], ['max_students', 'Student limit'], ['max_teachers', 'Teacher limit']];

// Plans: every staff tier reads them; super admins create, edit and retire (#34).
export function AdminPlansPage({ user, notify }) {
  const plans = useAdminRequest(loadPlans);
  const canEdit = isSuperAdmin(user);
  const [editing, setEditing] = useState(null);
  async function setActive(plan, active) {
    if (!active && !window.confirm(tx`Retire ${plan.name}? Workspaces on it keep it, but it can no longer be chosen.`)) return;
    try {await api.update('users/plans', plan.id, { is_active: active });notify(active ? t("Plan available again.") : t("Plan retired."));plans.retry();} catch (error) {notify(error.message, 'error');}
  }
  const list = plans.data || [];
  return <><Panel title={t("Plans")} action={canEdit && <button className="button primary" onClick={() => setEditing({})}><Plus size={16} /> {t("New plan")}</button>}>
    {!canEdit && <p className="form-note staff-tier-note"><ShieldCheck size={16} /> {t("Only super admins can create, edit or retire plans.")}</p>}
    {plans.error && <InlineLoadError message={plans.error} onRetry={plans.retry} />}
    {!plans.data && !plans.error && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}
    <div className="card-grid">{list.map((plan) => <article className="plan-card" key={plan.id}>
      <header><div><h3>{plan.name}</h3><small>{plan.code}</small></div><div className="workspace-plan-badges"><Badge>{plan.workspace_type === 'individual' ? t("Individual workspaces") : t("Organization schools")}</Badge>{!plan.is_active && <Badge tone="urgent">{t("Retired")}</Badge>}</div></header>
      {plan.description && <p>{plan.description}</p>}
      <PlanFacts plan={plan} />
      <footer><small>{tp('{n} workspace on this plan|{n} workspaces on this plan', plan.workspaces_count || 0, { n: plan.workspaces_count || 0 })}</small>{canEdit && <div className="record-actions"><button className="icon-button" onClick={() => setEditing(plan)} aria-label={tx`Edit ${plan.name}`} title={t("Edit")}><Pencil size={16} /></button>{plan.is_active ? <button className="button quiet small" onClick={() => setActive(plan, false)}>{t("Retire")}</button> : <button className="button quiet small" onClick={() => setActive(plan, true)}>{t("Make available")}</button>}</div>}</footer>
    </article>)}{plans.data && !list.length && <Empty text={t("No plans yet.")} />}</div>
  </Panel>{editing && <PlanForm plan={editing.id ? editing : null} onClose={() => setEditing(null)} onSaved={() => {setEditing(null);plans.retry();}} notify={notify} />}</>;
}

const limitValue = (value) => (String(value ?? '').trim() === '' ? null : Number(value));

function PlanForm({ plan, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [overLimit, setOverLimit] = useState(null);
  async function submit(event) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const limits = Object.fromEntries(PLAN_LIMIT_FIELDS.map(([key]) => [key, limitValue(values.get(key))]));
    const features = Object.fromEntries(PLAN_FEATURES.map(([key]) => [key, values.get(`feature_${key}`) === 'on']));
    const payload = { name: values.get('name'), description: values.get('description'), ...limits, features };
    setSaving(true);
    try {
      // Before lowering a limit on a plan in use, list the workspaces already over it (nobody is removed).
      const lowered = plan && plan.workspaces_count > 0 && PLAN_LIMIT_FIELDS.some(([key]) => limits[key] !== null && (plan[key] === null || limits[key] < plan[key]));
      if (lowered && overLimit === null) {
        const asked = Object.fromEntries(Object.entries(limits).filter(([, value]) => value !== null));
        const impact = await api.planImpact(plan.id, asked);
        if (impact.over_limit.length) {setOverLimit(impact.over_limit);return;}
      }
      if (plan) await api.update('users/plans', plan.id, payload);
      else await api.create('users/plans', { ...payload, code: values.get('code'), workspace_type: values.get('workspace_type') });
      notify(plan ? t("Plan updated.") : t("Plan created."));
      onSaved();
    } catch (error) {notify(error.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={plan ? tx`Edit plan · ${plan.name}` : t("New plan")} onClose={onClose}><form className="form-grid" onSubmit={submit} onChange={() => overLimit && setOverLimit(null)}>
    <Field label={t("Plan name")}><input name="name" defaultValue={plan?.name || ''} placeholder={t("e.g. School Plus")} required /></Field>
    {plan ? <Field label={t("Code")}><input value={plan.code} disabled /></Field> : <Field label={t("Code")} hint={t("Lowercase letters, numbers and dashes. It cannot be changed later.")}><input name="code" pattern="[a-z0-9\-]+" placeholder={t("e.g. school-plus")} required /></Field>}
    {!plan && <Field label={t("Workspace type")} hint={t("It cannot be changed later.")}><select name="workspace_type" defaultValue="school"><option value="school">{t("Organization schools")}</option><option value="individual">{t("Individual workspaces")}</option></select></Field>}
    <Field label={t("Description")}><input name="description" defaultValue={plan?.description || ''} placeholder={t("e.g. For schools with up to six counselors")} /></Field>
    {PLAN_LIMIT_FIELDS.map(([key, title]) => <Field key={key} label={t(title)} hint={t("Leave empty for no limit.")}><input name={key} type="number" min="0" defaultValue={plan?.[key] ?? ''} /></Field>)}
    <div className="plan-feature-fields form-wide" role="group" aria-label={t("Features")}><span aria-hidden="true">{t("Features")}</span>{PLAN_FEATURES.map(([key, title]) => <CheckboxControl key={key} name={`feature_${key}`} defaultChecked={plan ? Boolean(plan.features?.[key]) : true}>{t(title)}</CheckboxControl>)}</div>
    {plan?.workspaces_count > 0 && <p className="form-note form-wide"><ShieldAlert size={16} /> {tp('{n} workspace uses this plan. Lowering a limit never removes accounts; it only blocks new ones.|{n} workspaces use this plan. Lowering a limit never removes accounts; it only blocks new ones.', plan.workspaces_count, { n: plan.workspaces_count })}</p>}
    {overLimit && <div className="alert form-wide" role="alert"><b>{t("These workspaces are already over the new limits:")}</b><ul>{overLimit.map((row) => <li key={row.id}>{row.name}: {Object.entries(row.seats).map(([key, seat]) => `${t(PLAN_LIMIT_FIELDS.find(([field]) => field === key)?.[1] || key)} ${seat.used}/${seat.limit}`).join(' · ')}</li>)}</ul><small>{t("Their accounts stay; they cannot add more until they are under the limit.")}</small></div>}
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : overLimit ? t("Save anyway") : t("Save")}</button></div>
  </form></Modal>;
}

const STAFF_TIERS = [
  ['support', 'Reads everything, resets logins, answers support tickets and opens support views.'],
  ['ops', 'Support, plus schools, workspace plans, counselor and student accounts.'],
  ['superadmin', 'Everything, including staff accounts, plans and counselor roadmap reviews.'],
];
const tierPowers = (tier) => t(STAFF_TIERS.find(([value]) => value === tier)?.[1] || '');

// Product staff and their access tiers; super admins only (#35).
export function AdminStaffPage({ user, query, notify, reload }) {
  const list = usePagedList('users/accounts', { search: query, filters: { role: 'admin' }, ordering: 'name', pageSize: 50 });
  const [adding, setAdding] = useState(false);
  const [tierTarget, setTierTarget] = useState(null);
  const [credentialTarget, setCredentialTarget] = useState(null);
  async function deactivate(account) {
    if (!window.confirm(tx`Deactivate ${fullName(account)}? They lose ${label(account.staff_tier)} access and are signed out.`)) return;
    try {await api.deactivateAccount(account.id);notify(t("Staff account deactivated."));reload();} catch (error) {notify(error.message, 'error');}
  }
  return <><Panel title={t("Product staff")} action={<button className="button primary" onClick={() => setAdding(true)}><Plus size={16} /> {t("Add staff")}</button>}>
    <div className="record-list staff-roster" aria-busy={list.loading}>{list.items.map((account) => <article className="record" key={account.id}><span className="avatar">{initials(fullName(account))}</span><div className="record-main"><h3>{fullName(account)}</h3><p>{joinParts(account.email, account.username)}</p><div className="record-meta"><Badge tone="reviewing">{label(account.staff_tier)}</Badge><Badge tone={account.is_active ? 'success' : 'urgent'}>{account.is_active ? t("Active") : t("Inactive")}</Badge><span>{account.last_login ? tx`Last sign-in ${dateTimeText(account.last_login)}` : t("Never signed in")}</span></div></div>{account.id !== user.id && account.is_active && <div className="record-actions"><button className="icon-button" onClick={() => setCredentialTarget(account)} title={t("Reset login")} aria-label={t("Reset login")}><Fingerprint size={16} /></button>{!account.is_superuser && <><button className="button quiet small" onClick={() => setTierTarget(account)}>{t("Change tier")}</button><button className="icon-button danger" onClick={() => deactivate(account)} aria-label={tx`Deactivate ${fullName(account)}`} title={t("Deactivate")}><Trash2 size={16} /></button></>}</div>}</article>)}{firstPageLoading(list) && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}{list.loaded && !list.items.length && <Empty text={t("No staff accounts found.")} />}</div>
    <PagedListError list={list} /><LoadMore list={list} />
  </Panel>{adding && <StaffForm onClose={() => setAdding(false)} onCreated={reload} notify={notify} />}{tierTarget && <StaffTierForm account={tierTarget} onClose={() => setTierTarget(null)} onSaved={() => {setTierTarget(null);reload();}} notify={notify} />}{credentialTarget && <TemporaryCredentialModal account={credentialTarget} onClose={() => setCredentialTarget(null)} notify={notify} />}</>;
}

function TierChoice({ value, onChange }) {
  return <Field label={t("Access tier")} hint={tierPowers(value)}><select name="admin_tier" value={value} onChange={(event) => onChange(event.target.value)}>{STAFF_TIERS.map(([tier]) => <option key={tier} value={tier}>{label(tier)}</option>)}</select></Field>;
}

function StaffForm({ onClose, onCreated, notify }) {
  const [saving, setSaving] = useState(false);
  const [tier, setTier] = useState('support');
  const [result, setResult] = useState(null);
  async function submit(event) {
    event.preventDefault();setSaving(true);
    const values = Object.fromEntries(new FormData(event.currentTarget).entries());
    try {setResult(await api.createStaff(values));onCreated();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={t("Add staff")} onClose={onClose}>{result ? <div className="credential-modal credential-result"><div className="credential-account"><Fingerprint size={21} /><div><b>{result.user.username}</b><small>{joinParts(result.user.email, label(result.user.staff_tier))}</small></div></div><OneTimePassword password={result.temporary_password} expiresAt={result.credential?.expires_at} notify={notify} /><div className="form-actions"><button type="button" className="button primary" onClick={onClose}>{t("Close")}</button></div></div> : <form className="form-grid" onSubmit={submit} autoComplete="off">
    <Field label={t("First name")}><input name="first_name" placeholder={t("e.g. Dilnoza")} required /></Field>
    <Field label={t("Last name")}><input name="last_name" placeholder={t("e.g. Karimova")} /></Field>
    <Field label={t("Username")}><input name="username" placeholder={t("e.g. d.karimova")} autoComplete="off" required /></Field>
    <Field label={t("Email")}><input name="email" type="email" placeholder={t("e.g. name@example.com")} autoComplete="off" required /></Field>
    <TierChoice value={tier} onChange={setTier} />
    <p className="form-note form-wide"><ShieldCheck size={16} /> {t("A one-time password is generated and shown once. They change it at first sign-in.")}</p>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Creating…") : t("Add staff")}</button></div>
  </form>}</Modal>;
}

function StaffTierForm({ account, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [tier, setTier] = useState(account.staff_tier || 'support');
  async function submit(event) {
    event.preventDefault();
    if (tier === account.staff_tier) {onClose();return;}
    setSaving(true);
    try {await api.update('users/accounts', account.id, { admin_tier: tier });notify(t("Access tier changed."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={tx`Access tier · ${fullName(account)}`} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <TierChoice value={tier} onChange={setTier} />
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : t("Save")}</button></div>
  </form></Modal>;
}

const JOB_LABELS = { generate_notifications: 'Daily notifications', purge_screen_time: 'Screen-time cleanup', flush_expired_tokens: 'Expired sign-in cleanup' };
const STORAGE_LABELS = { documents: 'Documents', task_submissions: 'Task submissions', message_attachments: 'Message attachments', activity_evidence: 'Activity evidence', recommendation_letters: 'Recommendation letters' };
const JOB_RESULT_TONES = { ok: 'success', failed: 'urgent', skipped: 'reviewing' };

// Readiness, scheduled jobs, storage and error tracking; ops tier and above (#40).
export function AdminHealthPage() {
  // Storage totals are cached on the server; its own "Check again" asks for a recount.
  const recountStorage = useRef(false);
  const loadHealth = useCallback(() => {
    const refreshStorage = recountStorage.current;
    recountStorage.current = false;
    return api.adminHealth({ refreshStorage });
  }, []);
  const health = useAdminRequest(loadHealth);
  const checkStorage = () => {recountStorage.current = true; health.retry();};
  const { data } = health;
  if (health.error) return <Panel title={t("Platform health")}><InlineLoadError message={health.error} onRetry={health.retry} /></Panel>;
  if (!data) return <Panel title={t("Platform health")}><p className="paged-list-loading" role="status">{t("Loading…")}</p></Panel>;
  const { readiness } = data;
  return <div className="section-stack">
    <Panel title={t("Readiness")} action={<button type="button" className="button quiet small" onClick={health.retry} aria-busy={health.loading}><RefreshCw size={14} /> {t("Check again")}</button>}><div className="record-meta"><Badge tone={readiness.status === 'ok' ? 'success' : 'urgent'}>{readiness.status === 'ok' ? t("Ready") : readiness.status === 'degraded' ? t("Degraded") : t("Unavailable")}</Badge><span>{t("Database")}: {readiness.database === 'ok' ? t("OK") : t("Not answering")}</span><span>{t("Cache")}: {readiness.cache === 'ok' ? t("OK") : t("Not answering")}</span></div></Panel>
    <Panel title={t("Scheduled jobs")}><div className="record-list">{data.jobs.map((job) => <article className={`record health-job ${job.overdue ? 'overdue' : ''}`} key={job.name}><div className="record-main"><h3>{t(JOB_LABELS[job.name] || job.name)}</h3><div className="record-meta">{job.last_run ? <><Badge tone={JOB_RESULT_TONES[job.last_run.result]}>{t(JOB_RESULT_LABELS[job.last_run.result])}</Badge><span>{dateTimeText(job.last_run.started_at)}</span><span>{tx`${formatNumberLocale(job.last_run.duration_seconds)} s`}</span>{job.last_run.processed !== null && <span>{tx`${formatNumberLocale(job.last_run.processed)} processed`}</span>}{job.last_run.error && <span>{job.last_run.error}</span>}</> : <span>{t("No run recorded yet")}</span>}{job.last_run && job.last_run.result !== 'ok' && job.last_success_at && <span>{tx`Last success ${dateTimeText(job.last_success_at)}`}</span>}{job.skipped_recently > 0 && <span>{tx`${formatNumberLocale(job.skipped_recently)} skipped: already running`}</span>}{job.overdue && <Badge tone="urgent">{t("No successful run in the last 26 hours")}</Badge>}</div></div></article>)}</div></Panel>
    <Panel title={t("File storage")} action={<button type="button" className="button quiet small" onClick={checkStorage} aria-busy={health.loading}><RefreshCw size={14} /> {t("Check again")}</button>}>{data.storage_checked_at && <p className="form-note">{tx`Counted ${dateTimeText(data.storage_checked_at)}; recounted at most once a minute.`}</p>}<div className="table-wrap"><table><thead><tr><th>{t("Kind")}</th><th>{t("Files")}</th><th>{t("Size")}</th></tr></thead><tbody>{data.storage.map((row) => <tr key={row.category}><td>{t(STORAGE_LABELS[row.category] || row.category)}</td><td>{formatNumberLocale(row.files)}</td><td>{formatFileSize(row.bytes)}</td></tr>)}</tbody></table></div><p className="form-note"><ShieldCheck size={16} /> {t("Sizes come from the uploads' saved sizes; profile photos and avatars are not counted.")}</p></Panel>
    <Panel title={t("Error tracking")}><div className="record-meta"><Badge tone={data.error_tracking.enabled ? 'success' : 'reviewing'}>{data.error_tracking.enabled ? t("On") : t("Off")}</Badge>{data.error_tracking.url ? <a href={data.error_tracking.url} target="_blank" rel="noreferrer">{t("Open the error tracker")} <ExternalLink size={14} /></a> : <span>{t("No error tracker link is configured.")}</span>}</div></Panel>
  </div>;
}

const JOB_RESULT_LABELS = { ok: 'Finished', failed: 'Failed', skipped: 'Skipped: already running' };
