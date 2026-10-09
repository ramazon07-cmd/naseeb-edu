import { useEffect, useId, useState } from 'react';
import { Eye, EyeOff, Pencil, Plus, Search, Trash2 } from 'lucide-react';
import { api } from '../api';
import { formatNumberLocale, t, tp, tx } from '../i18n';
import { Badge, Empty, Modal, Panel } from '../components/ui';
import { CheckboxControl, Field, PortalTabs } from '../components/forms';
import { LoadMore, PagedListError, firstPageLoading } from '../components/paged';
import { invalidatePagedLists, usePagedList } from '../hooks/usePagedList';
import { rankText } from '../lib/college';
import { dateText, joinParts, money } from '../lib/format';
import { label } from '../lib/labels';
import { canManageWorkspaces } from '../lib/roles';
import './catalog-admin.css';

// The shared catalogue students search: universities, their programs,
// scholarships and opportunity programs. Every product admin reads it; ops and
// superadmins edit it (the API enforces both, and audits every save).
//
// Field tuples: [name, label, type = 'text', required = false, choices = [], placeholder].
// 'section' starts a titled group; 'decimal' is a number with decimals;
// 'university' picks a university by search.
const UNIVERSITY_FIELDS = [
  ['', 'Basics', 'section'],
  ['name', 'University name', 'text', true, [], 'e.g. University of Toronto'],
  ['country', 'Country', 'text', true, [], 'e.g. Canada'],
  ['city', 'City', 'text'],
  ['website', 'Website', 'url', false, [], 'https://www.example.edu'],
  ['institution_type', 'Institution type', 'select', true, ['private', 'public']],
  ['campus_setting', 'Campus setting', 'select', false, ['', 'urban', 'suburban', 'rural']],
  ['degree_type', 'Degree type', 'select', true, ['four_year', 'two_year']],
  ['ranking', 'Ranking', 'number'],
  ['ranking_label', 'Published rank', 'text', false, [], 'e.g. 701–710'],
  ['', 'Admissions', 'section'],
  ['acceptance_rate', 'Acceptance rate (%)', 'decimal'],
  ['sat_min', 'SAT minimum', 'number'],
  ['sat_max', 'SAT maximum', 'number'],
  ['act_min', 'ACT minimum', 'number'],
  ['act_max', 'ACT maximum', 'number'],
  ['undergrad_enrollment', 'Undergraduates', 'number'],
  ['student_faculty_ratio', 'Student–faculty ratio', 'text', false, [], 'e.g. 18:1'],
  ['popular_majors', 'Popular majors', 'text', false, [], 'e.g. Computer science, Economics'],
  ['test_optional', 'Test optional', 'checkbox'],
  ['', 'Costs and aid', 'section'],
  ['tuition_usd', 'Tuition (USD per year)', 'number'],
  ['net_price_usd', 'Net price (USD per year)', 'number'],
  ['average_aid_usd', 'Average aid (USD per year)', 'number'],
  ['students_receiving_aid_percent', 'Students receiving aid (%)', 'number'],
  ['offers_need_based_aid', 'Need-based', 'checkbox'],
  ['offers_merit_aid', 'Merit', 'checkbox'],
  ['offers_athletic_aid', 'Athletic', 'checkbox'],
  ['offers_international_aid', 'International aid', 'checkbox'],
  ['need_blind', 'Need-blind', 'checkbox'],
  ['meets_full_need', 'Meets full need', 'checkbox'],
  ['css_profile_required', 'CSS Profile required', 'checkbox'],
  ['fafsa_required', 'FAFSA required', 'checkbox'],
  ['financial_aid_url', 'Financial aid page', 'url'],
  ['aid_application_notes', 'Aid notes', 'textarea'],
  ['', 'Deadlines and sources', 'section'],
  ['application_deadline', 'Application deadline', 'date'],
  ['scholarship_deadline', 'Scholarship deadline', 'date'],
  ['catalog_source_url', 'Source', 'url'],
  ['catalog_verified_at', 'Verified on', 'date'],
  ['notes', 'Notes', 'textarea'],
];

const PROGRAM_FIELDS = [
  ['university', 'University', 'university', true],
  ['name', 'Program name', 'text', true, [], 'e.g. BSc Computer Science'],
  ['canonical_major', 'Major', 'text', true, [], 'e.g. Computer Science'],
  ['teaching_language', 'Teaching language', 'text', true],
  ['duration_years', 'Duration (years)', 'decimal'],
  ['tuition_usd', 'Tuition (USD per year)', 'number'],
  ['estimated_living_cost_usd', 'Living costs (USD per year)', 'number'],
  ['min_gpa', 'Minimum GPA', 'decimal'],
  ['sat_min', 'SAT minimum', 'number'],
  ['ielts_min', 'IELTS minimum', 'decimal'],
  ['toefl_min', 'TOEFL minimum', 'number'],
  ['application_deadline', 'Application deadline', 'date'],
  ['scholarship_deadline', 'Scholarship deadline', 'date'],
  ['application_url', 'Application page', 'url'],
  ['source_url', 'Source', 'url'],
  ['verified_at', 'Verified on', 'date'],
  ['international_students_eligible', 'Open to international students', 'checkbox'],
  ['is_active', 'Shown to students', 'checkbox'],
];

const SCHOLARSHIP_FIELDS = [
  ['title', 'Scholarship name', 'text', true],
  ['provider', 'Provider', 'text', true],
  ['university', 'University', 'university'],
  ['scholarship_type', 'Type', 'select', true, ['merit', 'need_based', 'athletic', 'leadership', 'research', 'diversity', 'full_ride']],
  ['funding_level', 'Funding', 'select', true, ['partial', 'full', 'fixed']],
  ['scope', 'Scope', 'select', true, ['international', 'national']],
  ['amount_usd', 'Amount (USD)', 'number'],
  ['coverage', 'What it covers', 'text', false, [], 'e.g. Full tuition and housing'],
  ['eligible_countries', 'Eligible countries', 'text'],
  ['eligible_grades', 'Eligible grades', 'text', false, [], 'e.g. 11,12'],
  ['min_gpa', 'Minimum GPA', 'decimal'],
  ['min_ielts', 'IELTS minimum', 'decimal'],
  ['min_sat', 'SAT minimum', 'number'],
  ['deadline', 'Deadline', 'date'],
  ['application_url', 'Application page', 'url'],
  ['', 'Required documents', 'section'],
  ['requires_transcript', 'Transcript', 'checkbox'],
  ['requires_essay', 'Essay', 'checkbox'],
  ['requires_recommendation', 'Recommendation', 'checkbox'],
  ['requires_financial_documents', 'Financial documents', 'checkbox'],
  ['requires_cv', 'CV', 'checkbox'],
  ['requires_portfolio', 'Portfolio', 'checkbox'],
  ['', 'Visibility', 'section'],
  ['is_active', 'Shown to students', 'checkbox'],
];

const OPPORTUNITY_FIELDS = [
  ['title', 'Program name', 'text', true],
  ['provider', 'Provider', 'text', true],
  ['program_type', 'Type', 'select', true, ['international', 'national', 'unspecified']],
  ['delivery_mode', 'Format', 'select', true, ['onsite', 'online', 'hybrid', 'unspecified']],
  ['category', 'Category', 'text', true, [], 'e.g. Research'],
  ['country', 'Country', 'text'],
  ['city', 'City', 'text'],
  ['eligible_grades', 'Eligible grades', 'text', false, [], 'e.g. 9,10,11'],
  ['eligible_ages', 'Eligible ages', 'text', false, [], 'e.g. 15–18'],
  ['start_date', 'Start date', 'date'],
  ['end_date', 'End date', 'date'],
  ['deadline', 'Deadline', 'date'],
  ['deadline_text', 'Deadline as published', 'text', false, [], 'e.g. Every year in March'],
  ['application_open_text', 'Applications open', 'text'],
  ['fee_usd', 'Fee (USD)', 'number'],
  ['aid_details', 'Aid details', 'text'],
  ['application_url', 'Application page', 'url'],
  ['source_url', 'Source', 'url'],
  ['description', 'Description', 'textarea'],
  ['requirements', 'Requirements', 'textarea'],
  ['scholarship_available', 'Scholarship available', 'checkbox'],
  ['needs_verification', 'Needs verification', 'checkbox'],
  ['is_active', 'Shown to students', 'checkbox'],
];

// remove: 'delete' (nothing may depend on the row) or 'hide' (students saved
// it, so it is switched off and can be shown again).
const TABS = {
  universities: {
    title: 'Universities', endpoint: 'catalog/universities', ordering: 'name', fields: UNIVERSITY_FIELDS, remove: 'delete',
    add: 'Add university', edit: 'Edit university', name: (item) => item.name,
    meta: (item) => joinParts([item.city, item.country].filter(Boolean).join(', '), item.ranking && tx`Rank ${rankText(item)}`, item.net_price_usd != null && tx`Net price ${money(item.net_price_usd)}`, item.application_deadline && tx`Deadline ${dateText(item.application_deadline)}`),
    counts: (item) => joinParts(tp('{n} program|{n} programs', item.programs_count || 0, { n: formatNumberLocale(item.programs_count || 0) }), tp('{n} scholarship|{n} scholarships', item.scholarships_count || 0, { n: formatNumberLocale(item.scholarships_count || 0) }), tp('On {n} student list|On {n} student lists', item.applications_count || 0, { n: formatNumberLocale(item.applications_count || 0) })),
    blocked: (item) => item.applications_count > 0 || item.programs_count > 0 || item.scholarships_count > 0,
  },
  programs: {
    title: 'University programs', endpoint: 'catalog/programs', ordering: 'name', fields: PROGRAM_FIELDS, remove: 'delete',
    add: 'Add program', edit: 'Edit program', name: (item) => item.name,
    meta: (item) => joinParts(item.university_name, item.canonical_major, item.teaching_language, item.application_deadline && tx`Deadline ${dateText(item.application_deadline)}`),
  },
  scholarships: {
    title: 'Scholarships', endpoint: 'catalog/scholarships', ordering: 'title', fields: SCHOLARSHIP_FIELDS, remove: 'hide',
    add: 'Add scholarship', edit: 'Edit scholarship', name: (item) => item.title,
    meta: (item) => joinParts(item.provider, item.university_name || t('Open to any university'), item.amount_usd != null ? money(item.amount_usd) : label(item.funding_level), item.deadline && tx`Deadline ${dateText(item.deadline)}`),
  },
  opportunities: {
    title: 'Opportunity programs', endpoint: 'catalog/opportunity-programs', ordering: 'title', fields: OPPORTUNITY_FIELDS, remove: 'hide',
    add: 'Add opportunity program', edit: 'Edit opportunity program', name: (item) => item.title,
    meta: (item) => joinParts(item.provider, item.category, item.country, item.deadline ? tx`Deadline ${dateText(item.deadline)}` : item.deadline_text),
  },
};

// A new row starts from the model defaults the form shows.
const NEW_ROW = {
  universities: { institution_type: 'private', degree_type: 'four_year' },
  programs: { teaching_language: 'English', international_students_eligible: true, is_active: true },
  scholarships: { funding_level: 'partial', scope: 'international', requires_transcript: true, is_active: true },
  opportunities: { delivery_mode: 'onsite', is_active: true },
};

const NULLABLE = new Set(['number', 'decimal', 'date', 'university']);

function payloadFrom(form, fields) {
  const values = new FormData(form);
  return Object.fromEntries(fields.filter(([name]) => name).map(([name, , type]) => {
    const raw = values.get(name);
    if (type === 'checkbox') return [name, raw === 'on'];
    const value = String(raw ?? '').trim();
    return [name, value === '' && NULLABLE.has(type) ? null : value];
  }));
}

// Universities are searched on the server: the catalogue is too long for one <select>.
function UniversityPicker({ name, labelText, required, value, selectedLabel }) {
  const [search, setSearch] = useState('');
  const [current, setCurrent] = useState(value ? String(value) : '');
  const [currentLabel, setCurrentLabel] = useState(selectedLabel || '');
  const labelId = useId();
  const list = usePagedList('catalog/universities', { search, ordering: 'name', pageSize: 50 });
  const options = list.items.map((item) => ({ id: String(item.id), text: joinParts(item.name, item.country) }));
  // The chosen university stays selectable while a search hides it.
  if (current && !options.some((option) => option.id === current)) options.unshift({ id: current, text: currentLabel || t('Selected university') });
  return <div className="field catalog-picker">
    <span id={labelId}>{t(labelText)}</span>
    <label className="member-search"><Search size={15} aria-hidden="true" /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('Search universities')} aria-label={t('Search universities')} /></label>
    <select name={name} value={current} onChange={(event) => { setCurrent(event.target.value); setCurrentLabel(event.target.selectedOptions[0]?.textContent || ''); }} required={required} aria-labelledby={labelId} aria-busy={list.loading}>
      <option value="">{required ? t('Select university') : t('Open to any university')}</option>
      {options.map((option) => <option key={option.id} value={option.id}>{option.text}</option>)}
    </select>
    {list.hasMore && <small className="field-hint">{t('Type a name to find more universities.')}</small>}
    {list.error && <small className="field-error">{list.error}</small>}
  </div>;
}

function CatalogField({ field, item }) {
  const [name, title, type = 'text', required = false, choices = [], placeholder = ''] = field;
  const value = item?.[name];
  const hint = placeholder ? t(placeholder) : undefined;
  if (type === 'university') return <UniversityPicker name={name} labelText={title} required={required} value={value} selectedLabel={item?.university_name} />;
  if (type === 'textarea') return <Field label={title}><textarea name={name} defaultValue={value ?? ''} required={required} placeholder={hint} /></Field>;
  if (type === 'select') return <Field label={title}><select name={name} defaultValue={value ?? choices[0]} required={required}>{choices.map((choice) => <option key={choice} value={choice}>{label(choice)}</option>)}</select></Field>;
  const inputType = type === 'decimal' ? 'number' : type;
  return <Field label={title}><input name={name} type={inputType} step={type === 'decimal' ? 'any' : undefined} min={['number', 'decimal'].includes(type) ? 0 : undefined} defaultValue={value ?? ''} required={required} placeholder={hint} /></Field>;
}

// Splits the field list into titled groups; checkboxes in a group share one grid.
function fieldGroups(fields) {
  const groups = [];
  for (const field of fields) {
    if (field[2] === 'section' || !groups.length) groups.push({ title: field[2] === 'section' ? field[1] : '', fields: [], checks: [] });
    if (field[2] !== 'section') groups.at(-1)[field[2] === 'checkbox' ? 'checks' : 'fields'].push(field);
  }
  return groups;
}

function CatalogForm({ tabKey, item, onClose, onSaved, notify }) {
  const tab = TABS[tabKey];
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const row = item || NEW_ROW[tabKey];
  async function submit(event) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError('');
    const payload = payloadFrom(event.currentTarget, tab.fields);
    try {
      const saved = item ? await api.update(tab.endpoint, item.id, payload) : await api.create(tab.endpoint, payload);
      notify(item ? tx`${tab.name(saved)} saved.` : tx`${tab.name(saved)} added.`);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t(item ? tab.edit : tab.add)} onClose={() => { if (!saving) onClose(); }} className="catalog-form-modal">
    <form className="catalog-form" onSubmit={submit}>
      {fieldGroups(tab.fields).map((group, index) => <fieldset className="catalog-form-group" key={group.title || index}>
        {group.title && <legend>{t(group.title)}</legend>}
        {group.fields.length > 0 && <div className="form-grid">{group.fields.map((field) => <CatalogField key={field[0]} field={field} item={row} />)}</div>}
        {group.checks.length > 0 && <div className="catalog-form-checks">{group.checks.map(([name, title]) => <CheckboxControl key={name} name={name} defaultChecked={Boolean(row?.[name])}>{t(title)}</CheckboxControl>)}</div>}
      </fieldset>)}
      <div className="catalog-form-footer">
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="form-actions">
          <button type="button" className="button quiet" disabled={saving} onClick={onClose}>{t('Cancel')}</button>
          <button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t('Saving…') : t('Save')}</button>
        </div>
      </div>
    </form>
  </Modal>;
}

function CatalogRow({ tab, item, canManage, busy, onEdit, onRemove, onToggle }) {
  const name = tab.name(item);
  const hidden = item.is_active === false;
  const blocked = tab.blocked?.(item);
  return <article className={`catalog-row ${hidden ? 'is-hidden' : ''}`.trim()}>
    <div className="catalog-row-copy">
      <h3>{name}{hidden && <Badge tone="muted">{t('Hidden')}</Badge>}</h3>
      <p>{tab.meta(item) || '—'}</p>
      {tab.counts && <small>{tab.counts(item)}</small>}
    </div>
    {canManage && <div className="catalog-row-actions">
      <button type="button" className="icon-button" onClick={onEdit} aria-label={tx`Edit ${name}`} title={t('Edit')}><Pencil size={16} /></button>
      {tab.remove === 'hide'
        ? <button type="button" className="icon-button" onClick={onToggle} disabled={busy} aria-busy={busy} aria-label={hidden ? tx`Show ${name} to students` : tx`Hide ${name} from students`} title={hidden ? t('Show to students') : t('Hide from students')}>{hidden ? <Eye size={16} /> : <EyeOff size={16} />}</button>
        : <button type="button" className="icon-button danger" onClick={onRemove} disabled={busy || blocked} aria-busy={busy} aria-label={tx`Delete ${name}`} title={blocked ? t('Linked records use this university. Edit it instead.') : t('Delete')}><Trash2 size={16} /></button>}
    </div>}
  </article>;
}

export function CatalogAdminPage({ user, query = '', notify }) {
  const [tabKey, setTabKey] = useState('universities');
  const [search, setSearch] = useState(query);
  const [editing, setEditing] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const tab = TABS[tabKey];
  const canManage = canManageWorkspaces(user);
  const list = usePagedList(tab.endpoint, { search, ordering: tab.ordering, pageSize: 50 });
  useEffect(() => { setSearch(query); }, [query]);
  const refresh = () => invalidatePagedLists(Object.values(TABS).map((entry) => entry.endpoint));

  async function run(item, work, message) {
    setBusyId(item.id);
    try {
      await work();
      notify(message);
      refresh();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setBusyId(null);
    }
  }
  const remove = (item) => window.confirm(tx`Delete ${tab.name(item)}? This cannot be undone.`)
    && run(item, () => api.remove(tab.endpoint, item.id), tx`${tab.name(item)} deleted.`);
  const toggle = (item) => run(item, () => api.update(tab.endpoint, item.id, { is_active: !item.is_active }),
    item.is_active ? tx`${tab.name(item)} is hidden from students.` : tx`${tab.name(item)} is shown to students.`);

  const add = canManage && <button type="button" className="button primary" onClick={() => setEditing({ tabKey, item: null })}><Plus size={16} aria-hidden="true" /> {t(tab.add)}</button>;
  return <>
    <div className="catalog-tabs"><PortalTabs active={tabKey} onChange={(key) => { setTabKey(key); setEditing(null); setSearch(''); }} items={Object.entries(TABS).map(([key, value]) => [key, value.title])} /></div>
    <Panel title={t(tab.title)} action={add} className="catalog-admin">
      <div className="catalog-toolbar"><label className="member-search catalog-search"><Search size={15} aria-hidden="true" /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('Search the catalog')} aria-label={t('Search the catalog')} /></label><span className="catalog-count" aria-live="polite">{list.loaded && tp('{n} loaded record|{n} loaded records', list.items.length, { n: formatNumberLocale(list.items.length) })}</span></div>
      {!canManage && <p className="catalog-readonly">{t('You can view the catalog. Operations staff edit it.')}</p>}
      <div className="catalog-list" aria-busy={list.loading}>
        {list.items.map((item) => <CatalogRow key={item.id} tab={tab} item={item} canManage={canManage} busy={busyId === item.id} onEdit={() => setEditing({ tabKey, item })} onRemove={() => remove(item)} onToggle={() => toggle(item)} />)}
        {firstPageLoading(list) && <p className="paged-list-loading" role="status">{t('Loading…')}</p>}
        {list.loaded && !list.items.length && <Empty text={search ? t('Nothing in the catalog matches this search.') : t('This part of the catalog is empty.')} />}
      </div>
      <PagedListError list={list} />
      <LoadMore list={list} />
    </Panel>
    {editing && <CatalogForm tabKey={editing.tabKey} item={editing.item} notify={notify} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); }} />}
  </>;
}
