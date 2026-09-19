import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import { t } from './i18n';
import './student-onboarding.css';

const steps = ['Personal', 'Education', 'Test scores', 'Preferences', 'Honors', 'Activities'];
const countries = ['US', 'UK', 'Canada', 'Turkey', 'Vietnam', 'Hong Kong', 'China'];
// Older records hold spellings this form never offered ('USA', 'Singapore').
// They match no checkbox, so they stay invisible on screen yet are still sent
// on save, and the backend rejects the whole field for a country the student
// cannot see or untick. Map what has an equivalent, drop what does not.
const countryAliases = { USA: 'US', 'United States': 'US', 'United Kingdom': 'UK', GB: 'UK', HK: 'Hong Kong' };
const supportedCountries = (list) => [...new Set(list.map(c => countryAliases[c] || c).filter(c => countries.includes(c)))];
const incomes = ['Under $10,000', '$10,000–$25,000', '$25,000–$50,000', '$50,000–$100,000', '$100,000+'];
const interests = ['Arts', 'Humanities', 'Political science', 'Business', 'Economics', 'Accounting', 'Communications', 'Health and Medicine', 'Public and Social Services', 'Math and Statistics', 'Environmental Science', 'Computer Technologies', 'Science', 'Education', 'Engineering', 'English', 'History', 'Psychology'];
const strengths = ['STEM', 'Liberal Arts', 'Specialized programs', 'Research opportunities', 'No Preference'];
const defaults = { ielts_status: 'not_taken', sat_status: 'not_taken', sat_attempts: 0, subjects: [], interests: [], program_strengths: [], honors: [], activities: [] };
const numeric = ['graduation_year', 'class_size', 'class_rank', 'gpa', 'ielts_score', 'sat_reading', 'sat_math', 'sat_attempts'];

export default function StudentOnboarding({ onSaved, onSignOut, onPhotoChanged = () => {} }) {
  const [form, setForm] = useState(null);
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [profileId, setProfileId] = useState(null);
  const [photoUrl, setPhotoUrl] = useState('');
  const [photoBusy, setPhotoBusy] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    let active = true;
    api.studentOnboarding().then(p => {
      if (active) { setProfileId(p.id); if (p.has_photo) loadPhoto(p.id); const saved = { ...defaults, guardian_name: p.guardian_name || '', guardian_relation: p.guardian_relation || '', guardian_contact: p.parent_contact || '', first_name: p.user_detail.first_name, last_name: p.user_detail.last_name, grade: p.grade, school_name: p.school_name, gpa: p.gpa ?? '', ielts_score: p.ielts_score ?? '', target_countries: p.target_countries, ...p.application_profile };
        saved.target_countries = supportedCountries(Array.isArray(saved.target_countries) ? saved.target_countries : (saved.target_countries || '').split(',').map(c => c.trim()).filter(Boolean));
        saved.sat_status = p.application_profile?.sat_status || (saved.sat_reading || saved.sat_math ? 'taken' : 'not_taken');
        setForm(saved); }
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);
  function update(key, value) { setForm(f => ({ ...f, [key]: value })); }
  function loadPhoto(id) {
    api.studentPhoto(id).then(result => setPhotoUrl(current => {
      if (current) URL.revokeObjectURL(current);
      return URL.createObjectURL(result.blob);
    })).catch(() => setPhotoUrl(''));
  }
  async function choosePhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || !profileId) return;
    setPhotoBusy(true); setError('');
    try { await api.uploadStudentPhoto(profileId, file); loadPhoto(profileId); onPhotoChanged(); }
    catch (e) { setError(e.details?.photo || e.message); }
    finally { setPhotoBusy(false); }
  }
  async function dropPhoto() {
    if (!profileId) return;
    setPhotoBusy(true);
    try { await api.removeStudentPhoto(profileId); setPhotoUrl(current => { if (current) URL.revokeObjectURL(current); return ''; }); onPhotoChanged(); }
    catch (e) { setError(e.message); }
    finally { setPhotoBusy(false); }
  }
  const input = (key, label, options = {}) => <label className="onboarding-field" key={key}><span>{t(label)}{options.required && ' *'}</span><input name={key} value={form[key] ?? ''} onChange={e => update(key, e.target.value)} {...options} /></label>;
  const select = (key, label, values, required = false) => <label className="onboarding-field" key={key}><span>{t(label)}{required && ' *'}</span><select name={key} value={form[key] ?? ''} required={required} onChange={e => update(key, e.target.value)}><option value="">{t('Select')}</option>{values.map(v => <option key={Array.isArray(v) ? v[0] : v} value={Array.isArray(v) ? v[0] : v}>{t(Array.isArray(v) ? v[1] : v)}</option>)}</select></label>;
  const checks = (key, title, values) => <fieldset className="onboarding-choices"><legend>{t(title)}</legend>{values.map(value => <label key={value}><input type="checkbox" checked={(form[key] || []).includes(value)} onChange={e => update(key, e.target.checked ? [...(form[key] || []), value] : form[key].filter(v => v !== value))} />{t(value)}</label>)}</fieldset>;
  function rows(key, fields, empty) {
    return <div className="onboarding-rows">{(form[key] || []).map((row, i) => <fieldset key={i}><legend>{i + 1}</legend><div className="onboarding-grid">{fields.map(([name, label, choices]) => <label className="onboarding-field" key={name}><span>{t(label)} *</span>{Array.isArray(choices) ? <select required value={row[name] ?? ''} onChange={e => changeRow(key, i, name, e.target.value)}><option value="">{t('Select')}</option>{choices.map(c => <option key={c}>{c}</option>)}</select> : name === 'description' ? <textarea required maxLength={3000} value={row[name] ?? ''} onChange={e => changeRow(key, i, name, e.target.value)} /> : <input required type={choices === 'number' ? 'number' : 'text'} min={choices === 'number' ? (name === 'score' ? 1 : 0) : undefined} max={name === 'hours' ? 168 : name === 'weeks' ? 52 : name === 'score' ? (row.type === 'AP' ? 5 : 7) : undefined} value={row[name] ?? ''} onChange={e => changeRow(key, i, name, e.target.value)} />}</label>)}</div><button className="button quiet" type="button" onClick={() => update(key, form[key].filter((_, n) => n !== i))}>{t('Remove')}</button></fieldset>)}<button type="button" className="button secondary" onClick={() => update(key, [...(form[key] || []), { ...empty }])} disabled={(form[key] || []).length >= 50}>+ {t('Add entry')}</button></div>;
  }
  function changeRow(key, i, name, value) { update(key, form[key].map((row, n) => n === i ? { ...row, [name]: value } : row)); }
  function navigate(next) {
    if (next > step && step === 3 && !form.target_countries.length) { setError(t('Select at least one country.')); return; }
    if (next < step || ref.current.reportValidity()) { setStep(next); setError(''); }
  }
  async function submit(e) {
    e.preventDefault();
    if (step < 5) { navigate(step + 1); return; }
    setSaving(true); setError('');
    try {
      const payload = { ...form, target_countries: form.target_countries.join(', ') };
      numeric.forEach(key => { payload[key] = form[key] === '' || form[key] == null ? null : Number(form[key]); });
      payload.sat_attempts = payload.sat_attempts ?? 0;
      if (form.sat_status !== 'taken') { payload.sat_reading = null; payload.sat_math = null; payload.sat_attempts = 0; }
      const result = await api.saveStudentOnboarding(payload);
      await onSaved(result.user);
      if (!onSignOut) setError(t('Profile saved.'));
    } catch (e) { setError(e.details ? Object.entries(e.details).map(([field, messages]) => `${field.replaceAll('_', ' ')}: ${Array.isArray(messages) ? messages.filter(m => typeof m === 'string').join(' ') || t('Check the entries in this section.') : String(messages)}`).join(' · ') : e.message); }
    finally { setSaving(false); }
  }
  return <main className="student-onboarding"><header><div><span className="onboarding-brand">NASEEB EDU</span><h1>{t(onSignOut ? 'Complete your profile' : 'My profile')}</h1><p>{t('Enter your details. Fields marked * are required.')}</p></div>{onSignOut && <button className="button quiet" onClick={onSignOut}>{t('Sign out')}</button>}</header>
    {error && <p className="onboarding-message" role="status">{error}</p>}
    {!form ? <p>{error ? t('Reload the page to try again.') : t('Loading…')}</p> : <>
      <nav aria-label="Profile steps">{steps.map((name, i) => <button key={name} type="button" aria-current={step === i ? 'step' : undefined} disabled={saving || i > step + 1} onClick={() => navigate(i)}><span>{String(i + 1).padStart(2, '0')}</span>{t(name)}</button>)}</nav>
      <form ref={ref} onSubmit={submit}><div className="onboarding-section-heading"><h2>{t(steps[step])}</h2><span>{step + 1} / 6</span></div>
        {step === 0 && <div className="onboarding-grid">{input('first_name', 'First name', { required: true })}{input('middle_name', 'Middle name')}{input('last_name', 'Last name', { required: true })}{select('gender', 'Gender', ['Male', 'Female', 'Prefer not to say'], true)}{select('grade', 'Current school year', ['8', '9', '10', '11', ['gap', 'Gap year']], true)}{input('graduation_year', 'Graduation year', { type: 'number', min: 2000, max: 2100, required: true })}{select('first_generation', 'First-generation college student?', ['Yes', 'No', 'Not sure'])}{select('family_income', 'Annual family income (USD)', incomes, true)}{input('residency_status', 'Residency status')}
          <div className="onboarding-photo">
            <span className="onboarding-photo-preview">{photoUrl ? <img src={photoUrl} alt={t('Profile photo')} /> : `${(form.first_name || '')[0] || ''}${(form.last_name || '')[0] || ''}`.toUpperCase()}</span>
            <div>
              <b>{t('Profile photo')}</b>
              <small>{t('PNG, JPG or WebP · up to 5 MB')}</small>
              <div className="onboarding-photo-actions">
                <label className="button quiet small">{photoBusy ? t('Saving…') : t('Upload photo')}<input type="file" accept=".png,.jpg,.jpeg,.webp" onChange={choosePhoto} disabled={photoBusy || !profileId} hidden /></label>
                {photoUrl && <button type="button" className="button quiet small" onClick={dropPhoto} disabled={photoBusy}>{t('Remove photo')}</button>}
              </div>
            </div>
          </div>
          {input('guardian_name', 'Guardian name')}
          {select('guardian_relation', 'Relationship', [['mother', 'Mother'], ['father', 'Father'], ['guardian', 'Guardian']])}
          {input('guardian_contact', 'Guardian contact')}</div>}
        {step === 1 && <div className="onboarding-grid">{input('school_name', 'School name', { required: true })}{input('country', 'Country', { required: true })}{input('state', 'State / Province')}{input('city', 'City', { required: true })}{input('class_size', 'Class size', { type: 'number', min: 1 })}{input('class_rank', 'Class ranking', { type: 'number', min: 1, max: form.class_size || undefined })}{select('gpa_scale', 'GPA scale', ['4', '5', '100'], true)}{input('gpa', 'GPA', { required: true, type: 'number', min: 0, max: Number(form.gpa_scale || 100), step: '.01' })}</div>}
        {step === 2 && <div className="onboarding-tests"><section><h3>01 · IELTS</h3><div className="onboarding-grid">{select('ielts_status', 'Status', [['not_taken', 'Not taken'], ['planning', 'Planning'], ['scheduled', 'Scheduled'], ['taken', 'Score available'], ['not_required', 'Not required']], true)}{form.ielts_status === 'taken' && input('ielts_score', 'Overall score', { required: true, type: 'number', min: 0, max: 9, step: '.5' })}</div></section><section><h3>02 · SAT ({t('optional')})</h3><div className="onboarding-grid">{select('sat_status', 'SAT status', [['not_taken', 'Not taken'], ['planning', 'Planning'], ['scheduled', 'Scheduled'], ['taken', 'Score available'], ['not_required', 'Not required']])}{form.sat_status === 'taken' && <>{input('sat_reading', 'Reading and Writing', { type: 'number', min: 200, max: 800, required: true })}{input('sat_math', 'Math', { type: 'number', min: 200, max: 800, required: true })}{input('sat_attempts', 'Number of attempts', { type: 'number', min: 0, max: 100 })}</>}</div></section><section><h3>03 · AP / IB</h3>{rows('subjects', [['type', 'Exam', ['AP', 'IB']], ['subject', 'Subject'], ['score', 'Score', 'number']], { type: 'AP' })}</section></div>}
        {step === 3 && <div className="onboarding-preferences">{checks('target_countries', 'Applying countries * — select one or more', countries)}{checks('interests', 'Areas of interest', interests)}{checks('program_strengths', 'Academic program strength', strengths)}<label className="onboarding-field"><span>{t('Personal story (optional)')}</span><textarea maxLength={5000} value={form.personal_story || ''} onChange={e => update('personal_story', e.target.value)} /></label></div>}
        {step === 4 && rows('honors', [['role', 'Role / Honor title'], ['project', 'Project / Organization name'], ['description', 'Description'], ['grade', 'Grade level', ['8', '9', '10', '11', '12', 'Gap year']], ['recognition', 'Level of recognition', ['School', 'State/Regional', 'National', 'International']]], {})}
        {step === 5 && rows('activities', [['type', 'Activity type', ['Research', 'Competition', 'Internship', 'Summer camp', 'Online course', 'Volunteer', 'Arts', 'Club', 'Sports', 'Other']], ['position', 'Position / Leadership'], ['organization', 'Organization name'], ['description', 'Accomplishments and description'], ['grades', 'Participation grade levels'], ['hours', 'Hours per week', 'number'], ['weeks', 'Weeks per year', 'number']], {})}
        <footer><button className="button quiet" type="button" disabled={step === 0 || saving} onClick={() => navigate(step - 1)}>{t('Back')}</button><button className="button primary" disabled={saving}>{t(saving ? 'Saving…' : step === 5 ? 'Save profile' : 'Continue')}</button></footer>
      </form></>}
  </main>;
}
