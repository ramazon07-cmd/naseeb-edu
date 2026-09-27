import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Pencil } from 'lucide-react';
import { api } from '../api';
import { t, tx, formatPercentLocale } from '../i18n';
import { fieldErrorsFrom } from '../lib/onboardingDraft';
import { answersPayload, listText, profileAnswers, readinessHints, sectionByKey, validateSection } from '../lib/profileSections';
import { gradeText, joinParts } from '../lib/format';
import { label } from '../lib/labels';
import { Detail } from './records';
import { ProfilePhotoField, ProfileSectionFields } from './profileFields';
import { TestScoreSummary } from './testScores';
import { visibilityItemTitle } from './documents';

const list = (values) => (Array.isArray(values) ? values.map((value) => t(value)).join(', ') : values);

// Read view of one section: the same answers its edit form asks for.
function SectionSummary({ section, student }) {
  const answers = student.application_profile || {};
  if (section === 'personal') return <div className="detail-grid">
    <Detail label={t('Name')} value={[student.user_detail?.first_name, answers.middle_name, student.user_detail?.last_name].filter(Boolean).join(' ')} />
    <Detail label={t('Gender')} value={answers.gender && t(answers.gender)} />
    <Detail label={t('Current school year')} value={gradeText(student.grade)} />
    <Detail label={t('Graduation year')} value={answers.graduation_year} />
    <Detail label={t('Annual family income (USD)')} value={answers.family_income && t(answers.family_income)} />
    <Detail label={t('First-generation college student?')} value={answers.first_generation && t(answers.first_generation)} />
    <Detail label={t('Guardian')} value={joinParts(student.guardian_name, student.guardian_relation && label(student.guardian_relation))} />
    <Detail label={t('Guardian contact')} value={student.parent_contact} />
  </div>;
  if (section === 'academics') return <div className="detail-grid">
    <Detail label={t('School')} value={student.school_name} />
    <Detail label={t('Location')} value={joinParts(answers.city, answers.state, answers.country)} />
    <Detail label={t('GPA')} value={student.gpa != null && student.gpa !== '' ? `${Number(student.gpa)}${student.gpa_scale ? ` / ${student.gpa_scale}` : ''}` : null} />
    <Detail label={t('Class ranking')} value={answers.class_rank ? `${answers.class_rank}${answers.class_size ? ` / ${answers.class_size}` : ''}` : null} />
  </div>;
  if (section === 'tests') return <TestScoreSummary student={student} />;
  if (section === 'goal') return <div className="detail-grid">
    <Detail label={t('Applying countries')} value={listText(student.target_countries)} />
    <Detail label={t('Areas of interest')} value={list(answers.interests)} />
    <Detail label={t('Academic program strength')} value={list(answers.program_strengths)} />
    <Detail label={t('Personal story')} value={answers.personal_story} />
  </div>;
  const rows = Array.isArray(answers[section]) ? answers[section] : [];
  if (!rows.length) return <p className="profile-section-empty">{t('Nothing added yet.')}</p>;
  return <ul className="profile-section-rows">{rows.map((row, i) => <li key={i}>
    <b>{section === 'honors' ? joinParts(row.role, row.project) : joinParts(row.position, row.organization)}</b>
    <small>{section === 'honors' ? joinParts(row.recognition && t(row.recognition), row.grade && t(row.grade)) : joinParts(row.type && t(row.type), row.hours != null && row.hours !== '' && tx`${row.hours} h/week`)}</small>
  </li>)}</ul>;
}

function SectionCard({ section, student, editing, locked, onEdit, onClose, reload, notify }) {
  const [form, setForm] = useState(null);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const cardRef = useRef(null);
  const formRef = useRef(null);
  const title = t(section.title);
  // Each edit starts from the saved answers, so Cancel simply drops the copy.
  useEffect(() => {
    if (!editing) { setForm(null); setErrors({}); setError(''); return; }
    setForm(profileAnswers(student));
    requestAnimationFrame(() => {
      cardRef.current?.scrollIntoView?.({ block: 'start', behavior: 'smooth' });
      formRef.current?.querySelector('input, select, textarea')?.focus({ preventScroll: true });
    });
  }, [editing]); // eslint-disable-line react-hooks/exhaustive-deps -- a new edit copies the answers once
  function update(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
    setErrors((current) => {
      const stale = Object.keys(current).filter((name) => name === key || name.startsWith(`${key}.`));
      return stale.length ? Object.fromEntries(Object.entries(current).filter(([name]) => !stale.includes(name))) : current;
    });
  }
  // A group of checkboxes is marked on its fieldset, which cannot take focus.
  const focusError = () => requestAnimationFrame(() => {
    const invalid = formRef.current?.querySelector('[aria-invalid="true"]') || formRef.current?.querySelector('[role="alert"]');
    if (!invalid) return;
    invalid.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
    (invalid.matches('fieldset') ? invalid.querySelector('input') : invalid).focus?.({ preventScroll: true });
  });
  async function save(event) {
    event.preventDefault();
    const found = validateSection(section.key, form);
    if (Object.keys(found).length) { setErrors(found); setError(t('Check the highlighted answers.')); focusError(); return; }
    if (!formRef.current.reportValidity()) return;
    setSaving(true); setError('');
    try {
      await api.updateStudentAnswers(answersPayload(form, section.key));
      notify(tx`${title} saved.`);
      onClose();
      reload();
    } catch (e) {
      setErrors(fieldErrorsFrom(e.details));
      setError(e.message || t('Check the entries in this section.'));
      focusError();
    } finally { setSaving(false); }
  }
  const headingId = `profile-section-${section.key}`;
  return <section ref={cardRef} className={`panel profile-section-card${editing ? ' is-editing' : ''}`} aria-labelledby={headingId} id={`section-${section.key}`}>
    <header>
      <h2 id={headingId}>{title}</h2>
      {!editing && <button type="button" className="button quiet small profile-section-edit" onClick={onEdit} disabled={locked} title={locked ? t('Save or cancel the section you are editing first.') : undefined} aria-label={tx`Edit ${title}`}><Pencil size={15} /> {t('Edit')}</button>}
    </header>
    <div className="panel-body">
      {!editing && <SectionSummary section={section.key} student={student} />}
      {editing && form && <form ref={formRef} className="profile-section-form" onSubmit={save} noValidate>
        {error && <p className="onboarding-message error" role="alert">{error}</p>}
        <ProfileSectionFields section={section.key} form={form} update={update} errors={errors} idPrefix={`section-${section.key}`}
          photo={section.key === 'personal' ? <ProfilePhotoField profileId={student.id} hasPhoto={student.has_photo} initials={`${(form.first_name || '')[0] || ''}${(form.last_name || '')[0] || ''}`} onChanged={reload} onError={setError} /> : null} />
        <footer className="profile-section-actions">
          <button type="button" className="button quiet" onClick={onClose} disabled={saving}>{t('Cancel')}</button>
          <button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t('Saving…') : t('Save')}</button>
        </footer>
      </form>}
    </div>
  </section>;
}

// A counselor's verification is the only review state these records have:
// verified reads as Approved, anything else is still waiting for them.
function RecordStatus({ verified }) {
  return verified
    ? <span className="profile-status is-verified"><CheckCircle2 size={14} aria-hidden="true" /> {t('Approved')}</span>
    : <span className="profile-status is-waiting">{t('Waiting for counselor')}</span>;
}

function RecordsCard({ items, onOpen }) {
  const approved = items.filter((item) => item.verified).length;
  return <section className="panel profile-section-card" aria-labelledby="profile-section-records">
    <header>
      <h2 id="profile-section-records">{t('Activities & honors')}</h2>
      {items.length > 0 && <span className="profile-section-count">{tx`${approved} of ${items.length} approved`}</span>}
    </header>
    <div className="panel-body">
      {items.length ? <ul className="profile-section-rows">{items.slice(0, 5).map((item) => <li key={`${item.kind}-${item.id}`}>
        <b>{visibilityItemTitle(item)}</b><RecordStatus verified={item.verified} />
      </li>)}</ul> : <p className="profile-section-empty">{t('Nothing added yet.')}</p>}
      <button type="button" className="button quiet profile-section-open" onClick={onOpen}>{t('Open Activities & honors')}</button>
    </div>
  </section>;
}

export function ProfileReadiness({ student, onEdit }) {
  const readiness = student.profile_readiness;
  if (!readiness) return null;
  const value = Math.max(0, Math.min(100, Number(readiness.percent) || 0));
  const hints = readinessHints(readiness);
  const counselor = student.counselor_name ? tx`Counselor: ${student.counselor_name}` : null;
  return <section className="profile-readiness" aria-labelledby="profile-readiness-title">
    <div className="profile-readiness-head">
      <div className="profile-readiness-name"><h2 id="profile-readiness-title">{t('Profile ready')}</h2><p>{joinParts(gradeText(student.grade), counselor)}</p></div>
      <strong className="profile-readiness-value">{formatPercentLocale(value)}</strong>
    </div>
    <div className="progress wide" role="progressbar" aria-labelledby="profile-readiness-title" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${value}%` }} /></div>
    <p className="profile-readiness-hint">{hints.length
      ? <>{t('To raise it:')} {hints.map((hint, i) => <button key={hint.key} type="button" className="text-button" onClick={() => onEdit(hint.section)}>{t(hint.text)}{i < hints.length - 1 ? ',' : '.'}</button>)}</>
      : t('Every profile question is answered.')}</p>
  </section>;
}

export const PROFILE_SECTION_KEYS = ['personal', 'goal', 'academics', 'tests', 'honors', 'activities'];

// The student's own profile, edited where it is read: every card has its own
// Edit that turns it into that section's questions and saves only them.
export function ProfileSections({ student, data, reload, notify, sections = PROFILE_SECTION_KEYS, editSection = null, onEditDone = () => {}, onOpenRecords = null, showReadiness = true }) {
  const [editing, setEditing] = useState(() => (sections.includes(editSection) ? editSection : null));
  useEffect(() => { if (editSection && sections.includes(editSection)) setEditing(editSection); }, [editSection]); // eslint-disable-line react-hooks/exhaustive-deps -- follow deep links only
  if (!student) return null;
  const close = () => { setEditing(null); onEditDone(); };
  const records = onOpenRecords ? ['activities', 'honors', 'achievements'].flatMap((kind) => (data?.[kind] || []).filter((item) => Number(item.student) === Number(student.id)).map((item) => ({ ...item, kind }))) : [];
  return <div className="profile-sections">
    {showReadiness && <ProfileReadiness student={student} onEdit={(key) => { if (!editing && sections.includes(key)) setEditing(key); }} />}
    <div className="profile-section-grid">
      {sections.map((key) => <SectionCard key={key} section={sectionByKey(key)} student={student} editing={editing === key} locked={editing != null && editing !== key}
        onEdit={() => setEditing(key)} onClose={close} reload={reload} notify={notify} />)}
      {onOpenRecords && <RecordsCard items={records} onOpen={onOpenRecords} />}
    </div>
    {onOpenRecords && records.length > 0 && <p className="profile-status-legend"><b>{t('What the labels mean')}</b>
      <span><RecordStatus verified /> {t('your counselor checked it')}</span>
      <span><RecordStatus verified={false} /> {t('sent, not checked yet. Editing an approved entry sends it back for checking.')}</span>
    </p>}
  </div>;
}
