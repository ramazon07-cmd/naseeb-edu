import { useEffect, useState } from 'react';
import { ExternalLink, FileText } from 'lucide-react';
import { t } from '../i18n';
import { essayLabApi } from '../essayLab/essayLabApi';
import { buildPath } from '../lib/routes';
import './documents.css';

export function TaskEssayPicker({ taskId, value, onChange }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ loading: true, essays: [], error: '' });
  useEffect(() => {
    let active = true;
    setState({ loading: true, essays: [], error: '' });
    essayLabApi.listEssays({ trashed: 0 }).then((essays) => {
      if (active) setState({ loading: false, essays, error: '' });
    }).catch((error) => {
      if (active) setState({ loading: false, essays: [], error: error.message });
    });
    return () => { active = false; };
  }, [attempt]);
  const id = `task-essay-${taskId}`;
  const missing = value && !state.essays.some((essay) => String(essay.id) === String(value));
  return <div className="form-wide field task-essay-picker">
    <label className="task-essay-label" htmlFor={id}>{t('Attach an Essay Lab essay (optional)')}</label>
    <select id={id} name="submission_essay" value={value ?? ''} onChange={(event) => onChange(event.target.value)} disabled={state.loading} aria-describedby={`${id}-help`}>
      <option value="">{t('No essay attached')}</option>
      {missing && <option value={value} disabled>{t('Previously attached essay')}</option>}
      {state.essays.map((essay) => <option key={essay.id} value={essay.id}>{essay.title || t('Untitled')}</option>)}
    </select>
    <small className="field-hint" id={`${id}-help`}>{t('Submitting an essay shares it with your counselor for comments. Later saved edits remain visible.')}</small>
    {state.loading && <p role="status">{t('Loading essays…')}</p>}
    {state.error && <p role="alert">{state.error} <button type="button" className="link-button" onClick={() => setAttempt((current) => current + 1)}>{t('Retry')}</button></p>}
    {!state.loading && !state.error && !state.essays.length && <p><a href={buildPath({ page: 'essay_lab' })} target="_blank" rel="noreferrer">{t('Write an essay in Essay Lab')}</a></p>}
  </div>;
}

export function TaskEssayAttachment({ task }) {
  const essay = task.submission_essay_detail;
  if (!essay) return task.submission_essay ? <p role="status">{t('The attached essay is currently unavailable.')}</p> : null;
  const url = buildPath({ page: essay.is_owner ? 'essay_lab' : 'essays', params: { essayId: essay.id } });
  return <section className="task-essay-attachment">
    <FileText size={22} aria-hidden="true" />
    <div><span className="detail-label">{t('Essay Lab submission')}</span><b>{essay.title}</b><small>{t('{n} words', { n: essay.word_count })}</small></div>
    <a className="button quiet small" href={url} target="_blank" rel="noreferrer">{t(essay.is_owner ? 'Open in Essay Lab' : essay.can_comment ? 'Open essay and comment' : 'Read essay')} <ExternalLink size={14} aria-hidden="true" /></a>
  </section>;
}
