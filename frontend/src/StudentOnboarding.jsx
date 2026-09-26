import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import { t } from './i18n';
import { USER_STORAGE, userStorageKey } from './userStorage';
import { clearDraft, fieldErrorsFrom, firstStepWithError, loadDraft, saveDraft } from './lib/onboardingDraft';
import { PROFILE_SECTIONS, answersPayload, profileAnswers, supportedCountries, validateSection } from './lib/profileSections';
import { ProfilePhotoField, ProfileSectionFields } from './components/profileFields';

const withoutKeys = (object, keys) => Object.fromEntries(Object.entries(object || {}).filter(([key]) => !keys.includes(key)));
const steps = ['Personal', 'Education', 'Test scores', 'Preferences', 'Honors', 'Activities'];

// First-time onboarding only: afterwards each answer is edited in place in
// the Student Center (components/ProfileSections.jsx).
export default function StudentOnboarding({ userId, onSaved, onSignOut }) {
  const [form, setForm] = useState(null);
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  // A per-user draft so six steps of answers survive a reload or a lost connection.
  const draftKey = userId != null ? userStorageKey(USER_STORAGE.onboardingDraft, userId) : null;
  const storage = () => window.localStorage;
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState(null);
  const ref = useRef(null);
  useEffect(() => {
    let active = true;
    api.studentOnboarding().then(p => {
      if (!active) return;
      setProfile(p);
      const saved = profileAnswers(p);
      const draft = draftKey ? loadDraft(storage(), draftKey) : null;
      if (draft) {
        setForm({ ...saved, ...draft.form, target_countries: supportedCountries(draft.form.target_countries || saved.target_countries) });
        setStep(draft.step);
        setNotice(t('Your unsaved answers were restored.'));
      } else setForm(saved);
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- load once
  function update(key, value) {
    setForm(f => ({ ...f, [key]: value }));
    setFieldErrors(errors => {
      const stale = Object.keys(errors).filter(name => name === key || name.startsWith(`${key}.`));
      return stale.length ? withoutKeys(errors, stale) : errors;
    });
  }
  function navigate(next) {
    if (next > step) {
      const errors = validateSection(PROFILE_SECTIONS[step].key, form);
      if (Object.keys(errors).length) {
        setFieldErrors(f => ({ ...f, ...errors }));
        setError(errors.target_countries ? t('Select at least one country.') : t('Check the highlighted answers.'));
        requestAnimationFrame(() => ref.current?.querySelector('[aria-invalid="true"]')?.focus());
        return;
      }
    }
    if (next < step || ref.current.reportValidity()) {
      setStep(next); setError(''); setNotice('');
      if (draftKey) saveDraft(storage(), draftKey, form, next);
    }
  }
  // noValidate: the browser would otherwise block submit on a native constraint
  // before our plain-language checks run; each step still calls reportValidity.
  async function submit(e) {
    e.preventDefault();
    if (step < 5) { navigate(step + 1); return; }
    if (!ref.current.reportValidity()) return;
    setSaving(true); setError('');
    try {
      const result = await api.saveStudentOnboarding(answersPayload(form));
      if (draftKey) clearDraft(storage(), draftKey);
      setFieldErrors({});
      await onSaved(result.user);
    } catch (e) {
      const errors = fieldErrorsFrom(e.details);
      setFieldErrors(errors);
      const errorStep = firstStepWithError(errors);
      if (errorStep >= 0 && errorStep !== step) setStep(errorStep);
      setError(e.message || t('Check the entries in this section.'));
    }
    finally { setSaving(false); }
  }
  const photo = profile && <ProfilePhotoField profileId={profile.id} hasPhoto={profile.has_photo} initials={`${(form?.first_name || '')[0] || ''}${(form?.last_name || '')[0] || ''}`} onError={setError} />;
  return <main className="student-onboarding"><header><div><span className="onboarding-brand">NASEEB EDU</span><h1>{t('Complete your profile')}</h1><p>{t('Enter your details. Fields marked * are required.')}</p></div>{onSignOut && <button className="button quiet" onClick={onSignOut}>{t('Sign out')}</button>}</header>
    {error && <p className="onboarding-message error" role="alert">{error}</p>}
    {!error && notice && <p className="onboarding-message" role="status">{notice}</p>}
    {!form ? <p>{error ? t('Reload the page to try again.') : t('Loading…')}</p> : <>
      <nav aria-label="Profile steps">{steps.map((name, i) => <button key={name} type="button" aria-current={step === i ? 'step' : undefined} disabled={saving || i > step + 1} onClick={() => navigate(i)}><span>{String(i + 1).padStart(2, '0')}</span>{t(name)}</button>)}</nav>
      <form ref={ref} onSubmit={submit} noValidate><div className="onboarding-section-heading"><h2>{t(steps[step])}</h2><span>{step + 1} / 6</span></div>
        <ProfileSectionFields section={PROFILE_SECTIONS[step].key} form={form} update={update} errors={fieldErrors} idPrefix="onboarding" photo={photo} />
        <footer><button className="button quiet" type="button" disabled={step === 0 || saving} onClick={() => navigate(step - 1)}>{t('Back')}</button><button className="button primary" disabled={saving}>{t(saving ? 'Saving…' : step === 5 ? 'Save profile' : 'Continue')}</button></footer>
      </form></>}
  </main>;
}
