import { useState } from 'react';
import { ArrowUpRight, Check, Link2 } from 'lucide-react';
import { api } from '../api';
import { t, tp } from '../i18n';
import { dateTimeText } from '../lib/format';
import { label } from '../lib/labels';
import { changedPayload } from '../lib/recordRights';
import { PLAN_FIELDS, activePrograms, planNextStep, publishedPlan, selectedProgram, webUrl } from '../lib/applicationPlan';
import { Field, CheckboxControl } from './forms';
import { Modal } from './ui';
import './applicationPlan.css';

const valuesFor = (record) => Object.fromEntries(PLAN_FIELDS.map((key) => [key, record[key] ?? '']));

export function ApplicationPlan({ application, data, onClose, onSaved, setPage, notify }) {
  const [record, setRecord] = useState(application);
  const [values, setValues] = useState(() => valuesFor(application));
  const [confirmed, setConfirmed] = useState(false);
  const [essayId, setEssayId] = useState('');
  const [linkedIds, setLinkedIds] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const university = record.university_detail || {};
  const programs = activePrograms(university);
  const selected = selectedProgram(university, values.program);
  const published = publishedPlan(university, values.program);
  const portal = webUrl(values.application_portal_url);
  const official = webUrl(university.website);
  const source = webUrl(selected?.source_url) || official;
  const essays = (data.essays || []).filter((essay) => essay.application === record.id || linkedIds.includes(essay.id));
  const available = (data.essays || []).filter((essay) => !essay.application && !linkedIds.includes(essay.id));
  const finalStatus = ['accepted', 'rejected', 'waitlisted', 'submitted'].includes(record.status);
  const documents = (data.documents || []).filter((doc) => doc.has_file || doc.file || doc.has_signed_file);
  const letters = (data.recommendations || []).filter((letter) => letter.status === 'approved');
  const patch = (key, value) => setValues((current) => ({ ...current, [key]: value }));
  const go = (page, params) => { onClose(); setPage(page, params); };

  async function save(event) {
    event.preventDefault();
    if (busy) return;
    const action = event.nativeEvent.submitter?.value || 'save';
    if (action === 'submitted' && !confirmed) return;
    if (values.application_portal_url.trim() && !portal) { setError(t('Enter a valid http or https application portal URL.')); return; }
    setBusy(true); setError('');
    try {
      const payload = changedPayload({ ...values, program: values.program.trim(), deadline: values.deadline || null, scholarship_deadline: values.scholarship_deadline || null }, record);
      if (action !== 'save') payload.status = action;
      const updated = Object.keys(payload).length ? await api.update('applications', record.id, payload) : record;
      setRecord(updated); setValues(valuesFor(updated)); setConfirmed(false);
      notify(t(action === 'submitted' ? 'Submission recorded. Check the official portal for your decision.' : 'Application plan saved.'));
      onSaved?.();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function linkEssay() {
    if (!essayId || busy) return;
    setBusy(true); setError('');
    try {
      const id = Number(essayId);
      await api.update('essays', id, { application: record.id });
      setLinkedIds((current) => [...current, id]); setEssayId('');
      notify(t('Essay linked to this application.')); onSaved?.();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return <Modal title="Application plan" className="application-plan" onClose={onClose}>
    <form className="application-plan-form" onSubmit={save}>
      <header className="application-plan-head"><div><h3>{university.name || t('University')}</h3><p>{[university.city, university.country].filter(Boolean).join(', ')}</p></div><span className="tag">{label(record.status)}</span></header>
      <p className="application-plan-note">{t('Prepare and track your application here. The actual application is submitted on the official application portal.')}</p>
      <section className="application-plan-next" aria-label={t('Next step')}><b>{t('Next step')}</b><p>{t(planNextStep({ ...values, status: record.status }, essays))}</p></section>

      <section className="application-plan-section"><h3>{t('Program and deadlines')}</h3>
        <div className="form-grid">
          <Field label="Program" hint={programs.length ? t('Choose a published program or enter the exact program from the official website.') : t('The catalog has no program list. Enter the program from the official website.')}><input name="program" disabled={busy} list={`application-programs-${record.id}`} value={values.program} onChange={(event) => patch('program', event.target.value)} maxLength={220} required /><datalist id={`application-programs-${record.id}`}>{programs.map((program) => <option key={program.id} value={program.name} />)}</datalist></Field>
          <Field label="Tier"><select name="tier" disabled={busy} value={values.tier} onChange={(event) => patch('tier', event.target.value)}>{['dream', 'target', 'safety'].map((tier) => <option key={tier} value={tier}>{label(tier)}</option>)}</select></Field>
          <Field label="Application deadline"><input name="deadline" disabled={busy} type="date" value={values.deadline} onChange={(event) => patch('deadline', event.target.value)} /></Field>
          <Field label="Scholarship deadline"><input name="scholarship_deadline" disabled={busy} type="date" value={values.scholarship_deadline} onChange={(event) => patch('scholarship_deadline', event.target.value)} /></Field>
        </div>
        <div className="application-plan-links">{Object.values(published).some(Boolean) && <button type="button" className="button quiet small" disabled={busy} onClick={() => setValues((current) => ({ ...current, ...Object.fromEntries(Object.entries(published).filter(([, value]) => value)) }))}>{t('Use published dates and portal')}</button>}{source && <a href={source} target="_blank" rel="noreferrer">{t('Check official requirements')} <ArrowUpRight size={14} aria-hidden="true" /></a>}</div>
        <small>{t('Deadlines can differ by application round. Confirm the dates on the official website.')}</small>
      </section>

      <section className="application-plan-section"><h3>{t('Official application portal')}</h3>
        <Field label="Portal URL"><input type="url" name="application_portal_url" disabled={busy} value={values.application_portal_url} onChange={(event) => patch('application_portal_url', event.target.value)} placeholder="https://…" /></Field>
        <div className="application-plan-links">{portal ? <a className="button primary small" href={portal} target="_blank" rel="noreferrer"><Link2 size={15} aria-hidden="true" />{t('Open application portal')} <ArrowUpRight size={14} aria-hidden="true" /></a> : official ? <a href={official} target="_blank" rel="noreferrer">{t('Find the portal on the official website')} <ArrowUpRight size={14} aria-hidden="true" /></a> : <p>{t('No official portal is listed. Save the link provided by the university.')}</p>}</div>
      </section>

      <section className="application-plan-section"><h3>{t('Essays for this application')}</h3>
        {essays.length ? <ul className="application-plan-essays">{essays.map((essay) => <li key={essay.id}><div><b>{essay.title}</b><small>{label(essay.status)}</small></div><button type="button" className="button quiet small" onClick={() => go('essay_lab', { essayId: essay.id })}>{t('Open essay')}</button></li>)}</ul> : <p>{t('No essays are linked to this application yet.')}</p>}
        {available.length > 0 && <div className="application-plan-link-essay"><Field label="Link an existing essay"><select disabled={busy} value={essayId} onChange={(event) => setEssayId(event.target.value)}><option value="">{t('Choose an essay')}</option>{available.map((essay) => <option key={essay.id} value={essay.id}>{essay.title}</option>)}</select></Field><button type="button" className="button quiet small" disabled={!essayId || busy} onClick={linkEssay}>{t('Link essay')}</button></div>}
        <button type="button" className="link-button" onClick={() => go('essay_lab')}>{t('Write an essay in Essay Lab')}</button>
      </section>

      <section className="application-plan-section"><h3>{t('Supporting documents')}</h3><p>{tp('{n} uploaded document|{n} uploaded documents', documents.length, { n: documents.length })} · {tp('{n} approved recommendation|{n} approved recommendations', letters.length, { n: letters.length })}</p><small>{t('These are your saved materials. Check which documents this university requires and upload them to its portal.')}</small><button type="button" className="link-button" onClick={() => go('student_center')}>{t('Open Student Center')}</button></section>
      <Field label="Preparation notes"><textarea name="notes" disabled={busy} rows={3} value={values.notes} onChange={(event) => patch('notes', event.target.value)} placeholder={t('Record the application round, missing documents and questions for your counselor.')} /></Field>

      {record.status_history?.length > 0 && <details className="application-plan-history"><summary>{t('Status history')}</summary><ol>{record.status_history.map((entry) => <li key={entry.id}><b>{label(entry.status)}</b><time dateTime={entry.created_at}>{dateTimeText(entry.created_at)}</time></li>)}</ol></details>}
      {error && <p className="application-plan-error" role="alert">{error}</p>}
      <footer className="application-plan-actions"><button type="button" className="button quiet" onClick={onClose}>{t('Close')}</button><button name="action" value="save" className="button primary" disabled={busy} aria-busy={busy}>{busy ? t('Saving…') : t('Save plan')}</button>{!finalStatus && record.status !== 'applying' && <button name="action" value="applying" className="button quiet" disabled={busy}>{t('Start preparation')}</button>}</footer>
      {!finalStatus && <section className="application-plan-confirm"><h3>{t('Already submitted through the official portal?')}</h3><CheckboxControl disabled={busy} checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}>{t('I have submitted this application through the official application system.')}</CheckboxControl><button name="action" value="submitted" className="button quiet" disabled={busy || !confirmed}><Check size={15} aria-hidden="true" />{t('Confirm submission')}</button></section>}
    </form>
  </Modal>;
}
