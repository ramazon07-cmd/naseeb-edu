import { useEffect, useState } from 'react';
import { tx, t, tp } from '../i18n';
import { api } from '../api';
import { UserRound, Plus, Pencil, Building2, Fingerprint, Trash2, ShieldAlert, ShieldCheck, Layers, KeyRound, RotateCcw } from 'lucide-react';
import { Panel, Badge, Empty, Modal } from '../components/ui';
import { OneTimePassword, TemporaryCredentialModal } from '../components/TemporaryCredentialModal';
import { Field } from '../components/forms';
import { usePagedList } from '../hooks/usePagedList';
import { LoadMore, PagedListError, SchoolPicker, firstPageLoading } from '../components/paged';
import { canManageWorkspaces, isPlatformAdmin } from '../lib/roles';
import { label } from '../lib/labels';
import { joinParts } from '../lib/format';
import { plansFor, seatUsage, subscriptionPayload } from '../lib/workspacePlan';
import { PlanFacts } from '../components/plans';
import { formFieldErrors } from '../lib/apiErrors';

export function SchoolsPage({ user, data, query = '', reload, notify }) {
  const isAdmin = isPlatformAdmin(user);
  const [status, setStatus] = useState('');
  const [type, setType] = useState('');
  // Admins page through every school; other roles only ever see their own.
  const list = usePagedList('schools', { search: query, filters: { is_active: status, workspace_type: type }, ordering: 'name', pageSize: 50, enabled: isAdmin });
  const schools = isAdmin ? list.items : data.schools;
  const [open, setOpen] = useState('');
  const [editingSchool, setEditingSchool] = useState(null);
  const [transferTarget, setTransferTarget] = useState(null);
  const [credentialTarget, setCredentialTarget] = useState(null);
  const [planTarget, setPlanTarget] = useState(null);
  const [loginTarget, setLoginTarget] = useState(null);
  async function remove(school) {
    if (!window.confirm(tx`Deactivate ${school.name}?`)) return;
    try {await api.remove('schools', school.id);notify(t("School deactivated."));reload();} catch (err) {notify(err.message, 'error');}
  }
  async function reactivate(school) {
    if (!window.confirm(tx`Reactivate ${school.name}? Its users can sign in again.`)) return;
    try {await api.update('schools', school.id, { is_active: true });notify(t("School reactivated."));reload();} catch (err) {notify(err.message, 'error');}
  }
  const canManage = canManageWorkspaces(user);
  const actions = canManage && <div className="panel-actions"><button className="button quiet" onClick={() => setOpen('counselor')}><UserRound size={17} /> {t("Individual counselor")}</button><button className="button primary" onClick={() => setOpen('school')}><Plus size={17} /> {t("Add school")}</button></div>;
  const filtered = Boolean(status || type);
  return <>
    <Panel title={t("Schools & counselor workspaces")} action={actions}>
      {isAdmin && <div className="paged-list-filters">
        <label><span>{t("Status")}</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">{t("All")}</option><option value="true">{t("Active")}</option><option value="false">{t("Inactive")}</option></select></label>
        <label><span>{t("Type")}</span><select value={type} onChange={(event) => setType(event.target.value)}><option value="">{t("All")}</option><option value="school">{t("Organization schools")}</option><option value="individual">{t("Individual workspaces")}</option></select></label>
      </div>}
      <div className="card-grid">{schools.map((school) => <article className={`school-card ${school.workspace_type === 'individual' ? 'individual' : ''}`} key={school.id}>
      <div className="school-number" aria-hidden="true">{school.workspace_type === 'individual' ? <UserRound size={22} /> : <Building2 size={22} />}</div>
      <div><div className="school-card-title"><h3>{school.name}</h3><Badge>{school.workspace_type === 'individual' ? t("Individual workspace") : t("School")}</Badge>{!school.is_active && <Badge tone="urgent">{t("Inactive")}</Badge>}</div><p>{school.workspace_type === 'individual' ? tx`Owner: ${school.owner_counselor_name || t("Not assigned")}` : joinParts(school.contact_email, school.contact_phone) || t("No contact details")}</p><span>{joinParts(tp('{n} student|{n} students', school.students_count || 0, { n: school.students_count || 0 }), school.organization_account_username ? tx`Login: ${school.organization_account_username}` : isAdmin && school.workspace_type === 'school' && t("No school login"))}</span>{isAdmin && <WorkspacePlanSummary school={school} />}</div>
      {isAdmin && <div className="school-card-actions">
        {canManage && school.subscription && <button className="icon-button" onClick={() => setPlanTarget(school)} aria-label={tx`Change plan for ${school.name}`} title={t("Workspace plan")}><Layers size={16} /></button>}
        {canManage && school.workspace_type !== 'individual' && <button className="icon-button" onClick={() => setEditingSchool(school)} aria-label={tx`Edit ${school.name}`}><Pencil size={16} /></button>}
        {canManage && school.workspace_type === 'individual' && school.owner_counselor && <button className="icon-button" onClick={() => setTransferTarget(school)} aria-label={tx`Transfer ${school.owner_counselor_name}`} title={t("Transfer to school")}><Building2 size={16} /></button>}
        {school.organization_account_id && <button className="icon-button" onClick={() => setCredentialTarget({ id: school.organization_account_id, username: school.organization_account_username, full_name: school.name, role: 'organization' })} aria-label={`${t('Reset login')} · ${school.name}`} title={t('Reset login')}><Fingerprint size={16} /></button>}
        {canManage && school.workspace_type === 'school' && !school.organization_account_id && <button className="icon-button" onClick={() => setLoginTarget(school)} aria-label={tx`Add school login for ${school.name}`} title={t("Add school login")}><KeyRound size={16} /></button>}
        {canManage && school.workspace_type !== 'individual' && school.is_active && <button className="icon-button danger" onClick={() => remove(school)} aria-label={tx`Deactivate ${school.name}`}><Trash2 size={16} /></button>}
        {canManage && school.workspace_type !== 'individual' && !school.is_active && <button className="icon-button" onClick={() => reactivate(school)} aria-label={tx`Reactivate ${school.name}`} title={t("Reactivate")}><RotateCcw size={16} /></button>}
      </div>}
    </article>)}{isAdmin && firstPageLoading(list) && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}{(!isAdmin || list.loaded) && !schools.length && <Empty text={filtered ? t("No schools match these filters.") : undefined} />}</div>{isAdmin && <><PagedListError list={list} /><LoadMore list={list} /></>}</Panel>
    {open === 'school' && <SchoolForm onClose={() => setOpen('')} onSaved={() => {setOpen('');reload();}} notify={notify} />}
    {editingSchool && <SchoolForm school={editingSchool} onClose={() => setEditingSchool(null)} onSaved={() => {setEditingSchool(null);reload();}} notify={notify} />}
    {loginTarget && <SchoolLoginForm school={loginTarget} onClose={() => setLoginTarget(null)} onCreated={reload} notify={notify} />}
    {open === 'counselor' && <IndividualCounselorForm onClose={() => setOpen('')} onSaved={() => {setOpen('');reload();}} notify={notify} />}
    {transferTarget && <CounselorTransferForm workspace={transferTarget} onClose={() => setTransferTarget(null)} onSaved={() => {setTransferTarget(null);reload();}} notify={notify} />}
    {credentialTarget && <TemporaryCredentialModal account={credentialTarget} onClose={() => setCredentialTarget(null)} notify={notify} />}
    {planTarget && <WorkspacePlanForm school={planTarget} onClose={() => setPlanTarget(null)} onSaved={() => {setPlanTarget(null);reload();}} notify={notify} />}
  </>;
}

export function WorkspacePlanSummary({ school }) {
  const subscription = school.subscription;
  if (!subscription) return null;
  return <div className="workspace-plan">
    <div className="workspace-plan-badges"><Badge tone="reviewing">{subscription.plan_name}</Badge>{subscription.status !== 'active' && <Badge tone={subscription.status === 'trial' ? 'open' : 'urgent'}>{label(subscription.status)}</Badge>}{subscription.read_only && <Badge tone="urgent">{t("Read-only")}</Badge>}</div>
    <div className="seat-usage">{seatUsage(school).map((row) => <span key={row.key} className={row.over ? 'over' : row.full ? 'full' : ''}>{t(row.title)} <b>{row.used}/{row.limit ?? '∞'}</b></span>)}</div>
  </div>;
}

export function WorkspacePlanForm({ school, onClose, onSaved, notify }) {
  const [plans, setPlans] = useState([]);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});
  useEffect(() => {
    let active = true;
    api.plans().then((items) => {if (active) setPlans(items || []);}).catch((err) => notify(err.message, 'error'));
    return () => {active = false;};
  }, [notify]);
  const subscription = school.subscription;
  const [planCode, setPlanCode] = useState(subscription.plan);
  const choices = plansFor(plans, school);
  async function submit(event) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget).entries());
    if (['suspended', 'expired'].includes(values.status) && !window.confirm(tx`Make ${school.name} read-only? Its users keep read access only.`)) return;
    setSaving(true);setErrors({});
    try {
      await api.updateSubscription(school.id, subscriptionPayload(values));
      notify(t("Workspace plan updated."));
      onSaved();
    } catch (err) {setErrors(formFieldErrors(err.details));notify(err.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={tx`Workspace plan · ${school.name}`} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <Field label={t("Workspace plan")} error={errors.plan}><select name="plan" value={planCode} onChange={(event) => setPlanCode(event.target.value)} required>{choices.map((plan) => <option key={plan.code} value={plan.code}>{plan.is_active ? plan.name : tx`${plan.name} (retired)`}</option>)}{!choices.length && <option value={subscription.plan}>{subscription.plan_name}</option>}</select></Field>
    <Field label={t("Subscription status")} error={errors.status}><select name="status" defaultValue={subscription.status}>{['trial', 'active', 'suspended', 'expired'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></Field>
    <Field label={t("Period start")} error={errors.period_start}><input name="period_start" type="date" defaultValue={subscription.period_start || ''} /></Field>
    <Field label={t("Period end")} error={errors.period_end}><input name="period_end" type="date" defaultValue={subscription.period_end || ''} /></Field>
    <PlanFacts plan={choices.find((plan) => plan.code === planCode)} />
    <p className="form-note form-wide"><ShieldAlert size={16} /> {t("Suspended or expired workspaces, and workspaces past their period end, become read-only. Lowering a limit never removes accounts; it only blocks new ones.")}</p>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : t("Save")}</button></div>
  </form></Modal>;
}

export function CounselorTransferForm({ workspace, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    try {
      const school = Number(new FormData(event.currentTarget).get('school'));
      await api.transferCounselor(workspace.owner_counselor, school);
      notify(t("Counselor transferred. The private workspace is now inactive."));
      onSaved();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={tx`Transfer ${workspace.owner_counselor_name}`} onClose={onClose}><form className="form-grid" onSubmit={submit}><SchoolPicker label="Organization school" required filters={{ workspace_type: 'school', is_active: 'true' }} /><p className="form-note form-wide"><ShieldAlert size={16} /> {t("Every student assigned to this counselor must already belong to the selected school. The transfer is blocked otherwise.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{saving ? t("Transferring…") : t("Transfer counselor")}</button></div></form></Modal>;
}

export function IndividualCounselorForm({ onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.createIndividualCounselor(Object.fromEntries(values.entries()));
      notify(t("Individual counselor and private workspace created."));
      onSaved();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={t("Add individual counselor")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("First name")}><input name="first_name" placeholder={t("e.g. Dilnoza")} required /></Field><Field label={t("Last name")}><input name="last_name" placeholder={t("e.g. Karimova")} /></Field><Field label={t("Username")}><input name="username" placeholder={t("e.g. d.karimova")} autoComplete="off" required /></Field><Field label={t("Email")}><input name="email" type="email" placeholder={t("e.g. name@example.com")} required /></Field><Field label={t("Phone")}><input name="phone" placeholder={t("e.g. +998 90 123 45 67")} /></Field><Field label={t("Position")}><input name="position" placeholder={t("Independent counselor")} /></Field><Field label={t("Temporary password")}><input name="password" type="password" minLength="8" autoComplete="new-password" required /></Field><p className="form-note form-wide"><ShieldCheck size={16} /> {t("A clearly labeled private workspace is created automatically. An admin can later transfer this counselor to an organization school after their students are reassigned.")}</p><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Creating…") : t("Create counselor")}</button></div></form></Modal>;
}

export function SchoolForm({ school = null, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState(null);
  const [errors, setErrors] = useState({});
  async function submit(event) {
    event.preventDefault();setSaving(true);setErrors({});const values = new FormData(event.currentTarget);
    try {
      // No is_active: saving an edit must never reactivate a school; Reactivate does that.
      const payload = { name: values.get('name'), code: values.get('code'), contact_email: values.get('contact_email'), contact_phone: values.get('contact_phone') };
      if (school) {await api.update('schools', school.id, payload);notify(t("School updated."));onSaved();return;}
      // One request: the school and its login are created together or not at all.
      const result = await api.create('schools', { ...payload, account: { username: values.get('username'), email: values.get('account_email'), password: values.get('password'), first_name: values.get('name'), last_name: 'Organization' } });
      notify(t("School and organization account created."));
      if (result.account?.temporary_password) setCreated(result.account);else onSaved();
    } catch (err) {setErrors(formFieldErrors(err.details, 'account'));notify(err.message, 'error');} finally {setSaving(false);}
  }
  if (created) return <Modal title={t("School login created")} onClose={onSaved}><SchoolLoginResult login={created} onClose={onSaved} notify={notify} /></Modal>;
  return <Modal title={school ? t("Edit school") : t("Add organization school")} onClose={onClose}><form className="form-grid" onSubmit={submit}><Field label={t("School name")} error={errors.name}><input name="name" defaultValue={school?.name || ''} placeholder={t("e.g. School No. 21")} required /></Field><Field label={t("Unique code")} error={errors.code}><input name="code" defaultValue={school?.code || ''} placeholder={t("e.g. school-21")} required /></Field><Field label={t("Contact email")} error={errors.contact_email}><input name="contact_email" type="email" defaultValue={school?.contact_email || ''} placeholder={t("e.g. name@example.com")} /></Field><Field label={t("Contact phone")} error={errors.contact_phone}><input name="contact_phone" defaultValue={school?.contact_phone || ''} placeholder={t("e.g. +998 90 123 45 67")} /></Field>{!school && <><Field label={t("Login username")} error={errors.account_username}><input name="username" placeholder={t("e.g. school21")} required /></Field><Field label={t("Login email")} error={errors.account_email}><input name="account_email" type="email" placeholder={t("e.g. name@example.com")} required /></Field><Field label={t('Temporary password')} error={errors.account_password} hint={t('Leave empty to generate a one-time password. It is shown once.')}><input name="password" type="password" minLength="8" autoComplete="new-password" /></Field></>}<div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t('Cancel')}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : school ? t("Save") : t("Create school")}</button></div></form></Modal>;
}

// Adds the organization login a school is missing; the server generates its first password.
export function SchoolLoginForm({ school, onClose, onCreated, notify }) {
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);
  const [errors, setErrors] = useState({});
  async function submit(event) {
    event.preventDefault();setSaving(true);setErrors({});const values = new FormData(event.currentTarget);
    try {
      setResult(await api.createSchoolAccount(school.id, { username: values.get('username'), email: values.get('email'), first_name: school.name, last_name: 'Organization' }));
      onCreated();
    } catch (err) {setErrors(formFieldErrors(err.details, 'account'));notify(err.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={tx`School login · ${school.name}`} onClose={onClose}>{result ? <SchoolLoginResult login={result} onClose={onClose} notify={notify} /> : <form className="form-grid" onSubmit={submit} autoComplete="off">
    <Field label={t("Login username")} error={errors.username}><input name="username" placeholder={t("e.g. school21")} autoComplete="off" required /></Field>
    <Field label={t("Login email")} error={errors.email}><input name="email" type="email" placeholder={t("e.g. name@example.com")} autoComplete="off" required /></Field>
    <p className="form-note form-wide"><ShieldCheck size={16} /> {t("A one-time password is generated and shown once. The school changes it at first sign-in.")}</p>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t('Cancel')}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Creating…") : t("Create login")}</button></div>
  </form>}</Modal>;
}

function SchoolLoginResult({ login, onClose, notify }) {
  return <div className="credential-modal credential-result">
    <div className="credential-account"><Fingerprint size={21} /><div><b>{login.username}</b><small>{login.email}</small></div></div>
    <OneTimePassword password={login.temporary_password} expiresAt={login.credential?.expires_at} notify={notify} />
    <div className="form-actions"><button type="button" className="button primary" onClick={onClose}>{t('Close')}</button></div>
  </div>;
}
