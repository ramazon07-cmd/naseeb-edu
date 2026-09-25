import { Stat } from '../components/records';
import { t, tx, formatPercentLocale } from '../i18n';
import { Panel, Badge, Empty, Modal } from '../components/ui';
import { Building2, UserRound, Compass, ShieldAlert, Plus, Pencil, Trash2, ShieldCheck, LifeBuoy } from 'lucide-react';
import { useState } from 'react';
import { auditActionLabel, fullName, initials, label } from '../lib/labels';
import { api } from '../api';
import { Field } from '../components/forms';
import { canManageWorkspaces, isPlatformAdmin } from '../lib/roles';
import { auditFilters } from '../lib/auditQuery';
import { SupportViewModal } from '../components/SupportViewModal';
import { dateText, dateTimeText, joinParts } from '../lib/format';
import { matchesQuery } from '../lib/searchIndex';
import { usePagedList } from '../hooks/usePagedList';
import { LoadMore, PagedListError, firstPageLoading } from '../components/paged';

export function AdminControlDashboard({ data, stats, setPage }) {
  const counselors = data.accounts.filter((account) => account.role === 'counselor');
  const activeCounselors = counselors.filter((account) => account.is_active);
  const pendingReviews = data.counselorRoadmaps.flatMap((roadmap) => roadmap.missions || []).filter((mission) => mission.status === 'submitted').length;
  return <div className="section-stack"><div className="stat-grid"><Stat label={t("Schools")} value={data.schools.filter((school) => school.workspace_type === 'school' && school.is_active).length} note={t("Active organization workspaces")} /><Stat label={t("Counselors")} value={activeCounselors.length} note={tx`${counselors.length - activeCounselors.length} inactive`} /><Stat label={t("Students")} value={stats?.students_total ?? '—'} note={t("Available in Student 360")} /><Stat label={t("Roadmap reviews")} value={pendingReviews} note={t("Submitted counselor missions")} /></div><Panel title={t("Platform administration")}><div className="quick-grid"><button onClick={() => setPage('admin_schools')}><Building2 /><span><b>{t("Manage schools")}</b><small>{t("Provision organization accounts")}</small></span></button><button onClick={() => setPage('admin_counselors')}><UserRound /><span><b>{t("Manage counselors")}</b><small>{t("Create, transfer, or deactivate")}</small></span></button><button onClick={() => setPage('counselor_roadmap')}><Compass /><span><b>{t("Review roadmaps")}</b><small>{t("Approve submitted milestones")}</small></span></button><button onClick={() => setPage('admin_audit')}><ShieldAlert /><span><b>{t("Open audit log")}</b><small>{t("Trace administration actions")}</small></span></button></div></Panel></div>;
}

export function AdminCounselorsPage({ user, data, query, reload, notify }) {
  const canManage = canManageWorkspaces(user);
  const [open, setOpen] = useState(false);
  const [transfer, setTransfer] = useState(null);
  const [editing, setEditing] = useState(null);
  const [supportTarget, setSupportTarget] = useState(null);
  const counselors = data.accounts.filter((account) => account.role === 'counselor' && matchesQuery(account, query));
  async function deactivate(account) {
    if (!window.confirm(tx`Deactivate ${fullName(account)}? Their login will stop immediately.`)) return;
    try {await api.deactivateAccount(account.id);notify(t("Counselor deactivated."));reload();} catch (error) {notify(error.message, 'error');}
  }
  return <><Panel title={t("Counselor provisioning")} action={canManage && <button className="button primary" onClick={() => setOpen(true)}><Plus size={16} /> {t("Add counselor")}</button>}><div className="record-list">{counselors.map((account) => <article className="record" key={account.id}><span className="avatar">{initials(fullName(account))}</span><div className="record-main"><h3>{fullName(account)}</h3><p>{joinParts(account.email, account.school_name || t("No school"))}</p><div className="record-meta"><Badge tone={account.is_active ? 'success' : 'danger'}>{account.is_active ? t("Active") : t("Inactive")}</Badge><span>{account.school_workspace_type === 'individual' ? t("Individual workspace") : t("Organization school")}</span></div></div><div className="record-actions"><button className="icon-button" onClick={() => setSupportTarget(account)} title={t("Support view")} aria-label={t("Support view")}><LifeBuoy size={16} /></button>{canManage && <button className="icon-button" onClick={() => setEditing(account)} title={t("Edit counselor")}><Pencil size={16} /></button>}{canManage && account.is_active && account.school_workspace_type !== 'individual' && <button className="button quiet" onClick={() => setTransfer(account)}><Building2 size={15} /> {t("Transfer")}</button>}{canManage && account.is_active && <button className="icon-button danger" onClick={() => deactivate(account)} title={t("Deactivate counselor")}><Trash2 size={16} /></button>}</div></article>)}{!counselors.length && <Empty text={t("No counselors found.")} />}</div></Panel>{open && <CounselorProvisionForm schools={data.schools} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} notify={notify} />}{editing && <CounselorEditForm account={editing} onClose={() => setEditing(null)} onSaved={() => {setEditing(null);reload();}} notify={notify} />}{transfer && <AccountTransferForm account={transfer} schools={data.schools} onClose={() => setTransfer(null)} onSaved={() => {setTransfer(null);reload();}} notify={notify} />}{supportTarget && <SupportViewModal account={supportTarget} onClose={() => setSupportTarget(null)} notify={notify} />}</>;
}

export function CounselorEditForm({ account, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);try {await api.update('users/accounts', account.id, { first_name: values.get('first_name'), last_name: values.get('last_name'), email: values.get('email'), phone: values.get('phone'), position: values.get('position'), is_active: values.get('is_active') === 'true' });notify(t("Counselor updated."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  return <Modal title={t("Edit counselor")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("First name")}><input name="first_name" defaultValue={account.first_name} required /></Field><Field label={t("Last name")}><input name="last_name" defaultValue={account.last_name} /></Field><Field label={t("Email")}><input name="email" type="email" defaultValue={account.email} required /></Field><Field label={t("Phone")}><input name="phone" defaultValue={account.phone} /></Field><Field label={t("Position")}><input name="position" defaultValue={account.position} /></Field><Field label={t("Status")}><select name="is_active" defaultValue={String(account.is_active)}><option value="true">{t("Active")}</option><option value="false">{t("Inactive")}</option></select></Field><p className="form-note form-wide">{t("Reactivation is blocked when the school's plan has no free counselor seat.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{saving ? t("Saving…") : t("Save")}</button></div></form></Modal>;
}

export function CounselorProvisionForm({ schools, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();setSaving(true);try {const payload = Object.fromEntries(new FormData(event.currentTarget).entries());payload.school = Number(payload.school);await api.createCounselor(payload);notify(t("Counselor account created."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  const organizationSchools = schools.filter((school) => school.workspace_type === 'school' && school.is_active);
  return <Modal title={t("Add school counselor")} onClose={onClose}><form className="form-grid" onSubmit={submit} autoComplete="off"><Field label={t("First name")}><input name="first_name" required /></Field><Field label={t("Last name")}><input name="last_name" /></Field><Field label={t("Username")}><input name="username" autoComplete="off" required /></Field><Field label={t("Email")}><input name="email" type="email" autoComplete="off" required /></Field><Field label={t("Organization school")}><select name="school" required><option value="">{t("Select a school")}</option>{organizationSchools.map((school) => <option value={school.id} key={school.id}>{school.name}</option>)}</select></Field><Field label={t("Position")}><input name="position" /></Field><Field label={t("Temporary password")}><input name="password" type="password" minLength="8" autoComplete="new-password" required /></Field><p className="form-note form-wide"><ShieldCheck size={16} /> {t("Each school's plan sets how many active counselors it can have.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{saving ? t("Creating…") : t("Create counselor")}</button></div></form></Modal>;
}

export function AccountTransferForm({ account, schools, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();if (!window.confirm(t("Confirm counselor transfer?"))) return;setSaving(true);try {await api.transferCounselor(account.id, Number(new FormData(event.currentTarget).get('school')));notify(t("Counselor transferred."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  return <Modal title={t("Transfer counselor")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Organization school")}><select name="school" required defaultValue=""><option value="" disabled>{t("Select a school")}</option>{schools.filter((school) => school.workspace_type === 'school' && school.is_active && school.id !== account.school).map((school) => <option key={school.id} value={school.id}>{school.name}</option>)}</select></Field><p className="form-note form-wide">{t("Transfer is blocked until assigned students belong to the destination school and a counselor slot is available.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{t("Transfer")}</button></div></form></Modal>;
}

export function CounselorRoadmapPage({ user, data, reload, notify }) {
  const [templateOpen, setTemplateOpen] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [selfAssignOpen, setSelfAssignOpen] = useState(false);
  async function submitMission(roadmap, mission) {const note = window.prompt(t("Add a completion note"), mission.counselor_note || '');if (!note?.trim()) return;try {await api.submitCounselorMission(roadmap.id, mission.id, note);notify(t("Mission submitted for review."));reload();} catch (error) {notify(error.message, 'error');}}
  async function review(roadmap, mission, decision) {let feedback = '';if (decision === 'request_changes') {feedback = window.prompt(t("Explain the requested changes"), '') || '';if (!feedback.trim()) return;}if (!window.confirm(decision === 'approve' ? t("Approve this mission?") : t("Request changes for this mission?"))) return;try {await api.reviewCounselorMission(roadmap.id, mission.id, decision, feedback);notify(decision === 'approve' ? t("Mission approved.") : t("Changes requested."));reload();} catch (error) {notify(error.message, 'error');}}
  const templates = data.counselorRoadmapTemplates.filter((template) => template.is_active);
  const admin = isPlatformAdmin(user);
  const actions = admin ? <div className="panel-actions"><button className="button quiet" onClick={() => setTemplateOpen(true)}><Plus size={16} /> {t("New template")}</button><button className="button primary" onClick={() => setAssignOpen(true)}><Compass size={16} /> {t("Assign roadmap")}</button></div> : <button className="button primary" onClick={() => setSelfAssignOpen(true)}><Compass size={16} /> {t("Start my roadmap")}</button>;
  const emptyText = user.role === 'counselor' ? t("Create your own roadmap or begin from an active template.") : t("No counselor roadmaps assigned yet.");
  return <><Panel title={admin ? t("Counselor roadmap control") : t("My professional roadmap")} action={actions}><div className="record-list">{data.counselorRoadmaps.map((roadmap) => <article className="roadmap-admin-card" key={roadmap.id}><header><div><span className="eyebrow">{label(roadmap.kind)}</span><h3>{roadmap.title}</h3><p>{joinParts(roadmap.counselor_name, roadmap.school_name)}</p></div><div className="roadmap-progress"><b>{formatPercentLocale(roadmap.progress_percent)}</b><Badge tone={roadmap.status === 'completed' ? 'success' : ''}>{label(roadmap.status)}</Badge></div></header><div className="roadmap-admin-missions">{roadmap.missions.map((mission) => <div key={mission.id}><span className={`status-dot ${mission.status}`} /><div><b>{mission.sequence}. {mission.title}</b><small>{joinParts(label(mission.status), mission.due_date && tx`Due ${dateText(mission.due_date)}`)}</small>{mission.counselor_note && <p>{mission.counselor_note}</p>}{mission.admin_feedback && <p className="form-note">{mission.admin_feedback}</p>}</div><div>{user.role === 'counselor' && mission.status !== 'approved' && <button className="button quiet" onClick={() => submitMission(roadmap, mission)}>{t("Submit")}</button>}{admin && mission.status === 'submitted' && <><button className="button quiet" onClick={() => review(roadmap, mission, 'request_changes')}>{t("Request changes")}</button><button className="button primary" onClick={() => review(roadmap, mission, 'approve')}>{t("Approve")}</button></>}</div></div>)}</div></article>)}{!data.counselorRoadmaps.length && <Empty text={emptyText} />}</div></Panel>{templateOpen && <RoadmapTemplateForm onClose={() => setTemplateOpen(false)} onSaved={() => {setTemplateOpen(false);reload();}} notify={notify} />}{assignOpen && <RoadmapAssignForm data={data} onClose={() => setAssignOpen(false)} onSaved={() => {setAssignOpen(false);reload();}} notify={notify} />}{selfAssignOpen && <RoadmapSelfAssignForm templates={templates} onClose={() => setSelfAssignOpen(false)} onSaved={() => {setSelfAssignOpen(false);reload();}} notify={notify} />}</>;
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
  return <Modal title={t("Start my roadmap")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field className="form-wide" label={t("Roadmap source")}><select name="template" value={templateId} onChange={(event) => setTemplateId(event.target.value)}><option value="">{t("Create my own roadmap")}</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.name} · {label(template.kind)}</option>)}</select></Field><Field className="form-wide" label={templateId ? t("Custom title (optional)") : t("Roadmap title")}><input name="title" required={!templateId} /></Field>{!templateId && <><Field label={t("Roadmap type")}><select name="kind"><option value="professional_onboarding">{t("Professional onboarding")}</option><option value="school_management">{t("School management")}</option></select></Field><Field className="form-wide" label={t("Missions, one per line")}><textarea name="missions" rows="6" required /></Field></>}<p className="form-note form-wide"><Compass size={16} /> {t("You can start one active roadmap for each roadmap type.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{saving ? t("Starting…") : t("Start roadmap")}</button></div></form></Modal>;
}

export function RoadmapTemplateForm({ onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);const missions = String(values.get('missions')).split('\n').map((title) => title.trim()).filter(Boolean).map((title, index) => ({ title, description: '', sequence: index + 1, due_days: (index + 1) * 7, is_required: true }));try {await api.create('counselor-roadmap-templates', { name: values.get('name'), description: values.get('description'), kind: values.get('kind'), is_active: true, missions });notify(t("Roadmap template created."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  return <Modal title={t("New counselor roadmap template")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Template name")}><input name="name" required /></Field><Field label={t("Roadmap type")}><select name="kind"><option value="professional_onboarding">{t("Professional onboarding")}</option><option value="school_management">{t("School management")}</option></select></Field><Field className="form-wide" label={t("Description")}><textarea name="description" /></Field><Field className="form-wide" label={t("Missions, one per line")}><textarea name="missions" required rows="6" /></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{t("Create template")}</button></div></form></Modal>;
}

export function RoadmapAssignForm({ data, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {event.preventDefault();setSaving(true);const values = new FormData(event.currentTarget);try {await api.create('counselor-roadmaps', { counselor: Number(values.get('counselor')), template: Number(values.get('template')), title: values.get('title') });notify(t("Roadmap assigned."));onSaved();} catch (error) {notify(error.message, 'error');} finally {setSaving(false);}}
  return <Modal title={t("Assign counselor roadmap")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("Counselor")}><select name="counselor" required><option value="">{t("Select a counselor")}</option>{data.accounts.filter((account) => account.role === 'counselor' && account.is_active).map((account) => <option key={account.id} value={account.id}>{fullName(account)} · {account.school_name}</option>)}</select></Field><Field label={t("Template")}><select name="template" required><option value="">{t("Select a template")}</option>{data.counselorRoadmapTemplates.filter((template) => template.is_active).map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}</select></Field><Field className="form-wide" label={t("Custom title (optional)")}><input name="title" /></Field><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{t("Assign roadmap")}</button></div></form></Modal>;
}

const EMPTY_AUDIT_FILTERS = { action: '', actor: '', school: '', date_from: '', date_to: '' };

// The audit log is filtered and paged on the server; it is never loaded whole.
export function AdminAuditPage({ data, query }) {
  const [filters, setFilters] = useState(EMPTY_AUDIT_FILTERS);
  const list = usePagedList('users/audit-events', { search: query, filters: auditFilters(filters), ordering: '-created', pageSize: 50 });
  // Only counselors are preloaded; product staff are a short, separate list.
  const staff = usePagedList('users/accounts', { filters: { role: 'admin' }, pageSize: 100 });
  const events = list.items;
  function change(key, value) {setFilters((current) => ({ ...current, [key]: value }));}
  const actors = [...staff.items, ...data.accounts.filter((account) => account.role === 'counselor')];
  const filterBar = <div className="audit-filters">
    <Field label={t("Action")}><input value={filters.action} onChange={(event) => change('action', event.target.value)} placeholder="student_360" /></Field>
    <Field label={t("Actor")}><select value={filters.actor} onChange={(event) => change('actor', event.target.value)}><option value="">{t("Everyone")}</option>{actors.map((account) => <option key={account.id} value={account.id}>{fullName(account)} · {label(account.role)}</option>)}</select></Field>
    <Field label={t("School")}><select value={filters.school} onChange={(event) => change('school', event.target.value)}><option value="">{t("All schools")}</option>{data.schools.map((school) => <option key={school.id} value={school.id}>{school.name}</option>)}</select></Field>
    <Field label={t("From")}><input type="date" value={filters.date_from} onChange={(event) => change('date_from', event.target.value)} /></Field>
    <Field label={t("To")}><input type="date" value={filters.date_to} onChange={(event) => change('date_to', event.target.value)} /></Field>
  </div>;
  return <Panel title={t("Product administration audit")}>{filterBar}<div className="record-list audit-list" aria-busy={list.loading}>{events.map((event) => <article className="record" key={event.id}><ShieldCheck size={20} /><div className="record-main"><h3>{auditActionLabel(event.action)}</h3><p>{event.target_label || event.target_type}</p><div className="record-meta"><span>{event.actor_name || t("System")}</span>{event.school_name && <span>{event.school_name}</span>}<span>{dateTimeText(event.created_at)}</span></div></div></article>)}{firstPageLoading(list) && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}{list.loaded && !events.length && <Empty text={t("No audit events found.")} />}</div><PagedListError list={list} /><LoadMore list={list} /></Panel>;
}
