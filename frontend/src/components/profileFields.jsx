import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { t } from '../i18n';
import { COUNTRIES, INCOMES, INTERESTS, STRENGTHS } from '../lib/profileSections';
import { TestScoresFields, errorText } from './testScores';

// The profile questions, one section at a time. Onboarding shows them as
// steps; the Student Center shows one section inside its card.

const HONOR_FIELDS = [['role', 'Role / Honor title'], ['project', 'Project / Organization name'], ['description', 'Description'], ['grade', 'Grade level', ['8', '9', '10', '11', '12', 'Gap year']], ['recognition', 'Level of recognition', ['School', 'State/Regional', 'National', 'International']]];
const ACTIVITY_FIELDS = [['type', 'Activity type', ['Research', 'Competition', 'Internship', 'Summer camp', 'Online course', 'Volunteer', 'Arts', 'Club', 'Sports', 'Other']], ['position', 'Position / Leadership'], ['organization', 'Organization name'], ['description', 'Accomplishments and description'], ['grades', 'Participation grade levels'], ['hours', 'Hours per week', 'number'], ['weeks', 'Weeks per year', 'number']];

// errors: { field: string (server) | [message, ...args] (browser checks) }.
export function ProfileSectionFields({ section, form, update, errors = {}, idPrefix = 'profile', photo = null }) {
  const errorId = (key) => `${idPrefix}-error-${key}`;
  const describe = (key) => (errors[key] ? { 'aria-invalid': true, 'aria-describedby': errorId(key) } : {});
  const fieldError = (key) => (errors[key] ? <small className="onboarding-field-error" id={errorId(key)}>{Array.isArray(errors[key]) ? errorText(errors[key]) : errors[key]}</small> : null);
  const input = (key, label, options = {}) => <label className="onboarding-field" key={key}><span>{t(label)}{options.required && ' *'}</span><input name={key} value={form[key] ?? ''} onChange={(e) => update(key, e.target.value)} {...options} {...describe(key)} />{fieldError(key)}</label>;
  const select = (key, label, values, required = false) => <label className="onboarding-field" key={key}><span>{t(label)}{required && ' *'}</span><select name={key} value={form[key] ?? ''} required={required} onChange={(e) => update(key, e.target.value)} {...describe(key)}><option value="">{t('Select')}</option>{values.map((v) => <option key={Array.isArray(v) ? v[0] : v} value={Array.isArray(v) ? v[0] : v}>{t(Array.isArray(v) ? v[1] : v)}</option>)}</select>{fieldError(key)}</label>;
  const checks = (key, title, values) => <fieldset className="onboarding-choices" {...describe(key)}><legend>{t(title)}</legend>{values.map((value) => <label key={value}><input type="checkbox" checked={(form[key] || []).includes(value)} onChange={(e) => update(key, e.target.checked ? [...(form[key] || []), value] : form[key].filter((v) => v !== value))} />{t(value)}</label>)}{fieldError(key)}</fieldset>;
  const changeRow = (key, i, name, value) => update(key, form[key].map((row, n) => (n === i ? { ...row, [name]: value } : row)));
  const rows = (key, fields) => <div className="onboarding-rows">{(form[key] || []).map((row, i) => <fieldset key={i}><legend>{i + 1}</legend><div className="onboarding-grid">{fields.map(([name, label, choices]) => <label className="onboarding-field" key={name}><span>{t(label)} *</span>{Array.isArray(choices) ? <select required value={row[name] ?? ''} onChange={(e) => changeRow(key, i, name, e.target.value)}><option value="">{t('Select')}</option>{choices.map((c) => <option key={c}>{c}</option>)}</select> : name === 'description' ? <textarea required maxLength={3000} value={row[name] ?? ''} onChange={(e) => changeRow(key, i, name, e.target.value)} /> : <input required type={choices === 'number' ? 'number' : 'text'} min={choices === 'number' ? 0 : undefined} max={name === 'hours' ? 168 : name === 'weeks' ? 52 : undefined} value={row[name] ?? ''} onChange={(e) => changeRow(key, i, name, e.target.value)} />}</label>)}</div><button className="button quiet" type="button" onClick={() => update(key, form[key].filter((_, n) => n !== i))}>{t('Remove')}</button></fieldset>)}{fieldError(key)}<button type="button" className="button secondary" onClick={() => update(key, [...(form[key] || []), {}])} disabled={(form[key] || []).length >= 50}>+ {t('Add entry')}</button></div>;

  if (section === 'personal') return <div className="onboarding-grid">{input('first_name', 'First name', { required: true })}{input('middle_name', 'Middle name')}{input('last_name', 'Last name', { required: true })}{select('gender', 'Gender', ['Male', 'Female', 'Prefer not to say'], true)}{select('grade', 'Current school year', ['8', '9', '10', '11', ['gap', 'Gap year']], true)}{input('graduation_year', 'Graduation year', { type: 'number', min: 2000, max: 2100, required: true })}{select('first_generation', 'First-generation college student?', ['Yes', 'No', 'Not sure'])}{select('family_income', 'Annual family income (USD)', INCOMES, true)}{input('residency_status', 'Residency status')}
    {photo}
    {input('guardian_name', 'Guardian name')}
    {select('guardian_relation', 'Relationship', [['mother', 'Mother'], ['father', 'Father'], ['guardian', 'Guardian']])}
    {input('guardian_contact', 'Guardian contact')}</div>;
  if (section === 'academics') return <div className="onboarding-grid">{input('school_name', 'School name', { required: true })}{input('country', 'Country', { required: true })}{input('state', 'State / Province')}{input('city', 'City', { required: true })}{input('class_size', 'Class size', { type: 'number', min: 1 })}{input('class_rank', 'Class ranking', { type: 'number', min: 1, max: form.class_size || undefined })}{select('gpa_scale', 'GPA scale', ['4', '5', '100'], true)}{input('gpa', 'GPA', { required: true, type: 'number', min: 0, max: Number(form.gpa_scale || 100), step: '.01' })}</div>;
  if (section === 'tests') return <TestScoresFields form={form} update={update} errors={Object.fromEntries(Object.entries(errors).map(([key, value]) => [key, Array.isArray(value) ? value : [value]]))} />;
  if (section === 'goal') return <div className="onboarding-preferences">{checks('target_countries', 'Applying countries * — select one or more', COUNTRIES)}{checks('interests', 'Areas of interest', INTERESTS)}{checks('program_strengths', 'Academic program strength', STRENGTHS)}<label className="onboarding-field"><span>{t('Personal story (optional)')}</span><textarea maxLength={5000} value={form.personal_story || ''} onChange={(e) => update('personal_story', e.target.value)} {...describe('personal_story')} />{fieldError('personal_story')}</label></div>;
  if (section === 'honors') return rows('honors', HONOR_FIELDS);
  if (section === 'activities') return rows('activities', ACTIVITY_FIELDS);
  return null;
}

// Upload, replace or remove the profile photo. It saves at once through its
// own endpoint, independent of the answers around it.
export function ProfilePhotoField({ profileId, hasPhoto, initials = '', onChanged = () => {}, onError = () => {} }) {
  const [photoUrl, setPhotoUrl] = useState('');
  const [busy, setBusy] = useState(false);
  // Object URLs pin the photo blob in memory until revoked: revoke the old one
  // on every change and the last one on unmount, and ignore late responses.
  const mounted = useRef(true);
  const photoUrlRef = useRef('');
  useEffect(() => { photoUrlRef.current = photoUrl; }, [photoUrl]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; if (photoUrlRef.current) URL.revokeObjectURL(photoUrlRef.current); }; }, []);
  const replace = (next) => setPhotoUrl((current) => { if (current) URL.revokeObjectURL(current); return next; });
  function load(id) {
    api.studentPhoto(id).then((result) => { if (mounted.current) replace(URL.createObjectURL(result.blob)); }).catch(() => { if (mounted.current) replace(''); });
  }
  useEffect(() => { if (profileId && hasPhoto) load(profileId); }, [profileId]); // eslint-disable-line react-hooks/exhaustive-deps -- load once per profile
  async function choose(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || !profileId) return;
    setBusy(true); onError('');
    try { await api.uploadStudentPhoto(profileId, file); load(profileId); onChanged(); }
    catch (e) { onError(e.message); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function drop() {
    if (!profileId) return;
    setBusy(true);
    try { await api.removeStudentPhoto(profileId); replace(''); onChanged(); }
    catch (e) { onError(e.message); }
    finally { if (mounted.current) setBusy(false); }
  }
  return <div className="onboarding-photo">
    <span className="onboarding-photo-preview">{photoUrl ? <img src={photoUrl} alt={t('Profile photo')} /> : initials.toUpperCase()}</span>
    <div>
      <b>{t('Profile photo')}</b>
      <small>{t('PNG, JPG or WebP · up to 5 MB')}</small>
      <div className="onboarding-photo-actions">
        <label className="button quiet small">{busy ? t('Saving…') : t('Upload photo')}<input type="file" accept=".png,.jpg,.jpeg,.webp" onChange={choose} disabled={busy || !profileId} hidden /></label>
        {photoUrl && <button type="button" className="button quiet small" onClick={drop} disabled={busy}>{t('Remove photo')}</button>}
      </div>
    </div>
  </div>;
}
