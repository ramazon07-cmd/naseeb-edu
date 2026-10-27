import { useEffect, useState } from 'react';
import { CheckCircle2, ClipboardCheck } from 'lucide-react';
import { api } from '../api';
import { t } from '../i18n';
import { dateText } from '../lib/format';
import { Dialog } from './ui';
import { buildPath } from '../lib/routes';

export default function SubmitToTask({ essay, beforeSubmit, onSubmitted, notify, disabled = false }) {
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState(null);
  return <>
    <button type="button" className="el-btn is-ghost" disabled={disabled} title={t('Submit essay to a task')} aria-label={t('Submit essay to a task')} onClick={() => setOpen(true)}>
      <ClipboardCheck size={17} aria-hidden="true" /><span className="el-hide-md">{t('Submit to task')}</span>
    </button>
    {open && <TaskDialog essay={essay} beforeSubmit={beforeSubmit} onSubmitted={(task) => { setConfirmation(task); onSubmitted?.(task); }} notify={notify} onClose={() => setOpen(false)} />}
    {confirmation && <Dialog title={t('Essay submitted successfully')} onClose={() => setConfirmation(null)} footer={<>
      <button type="button" className="el-btn" onClick={() => setConfirmation(null)}>{t('Continue writing')}</button>
      <a className="el-btn is-primary" href={buildPath({ page: 'tasks' })} target="_blank" rel="noreferrer">{t('View tasks')}</a>
    </>}>
      <div className="el-submission-success" role="status">
        <CheckCircle2 size={32} aria-hidden="true" />
        <b>{confirmation.title}</b>
        <span className="el-badge is-info">{t('Awaiting counselor review')}</span>
        <p>{t('Your counselor can now read this essay and leave comments. Find their feedback in Comments.')}</p>
      </div>
    </Dialog>}
  </>;
}

function TaskDialog({ essay, beforeSubmit, onSubmitted, notify, onClose }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ loading: true, tasks: [], error: '' });
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setState({ loading: true, tasks: [], error: '' });
    api.list('tasks', '?self_assigned=false&open=true').then((rows) => {
      const tasks = rows.filter((task) => !task.is_self_assigned && ['todo', 'in_progress', 'late'].includes(task.status));
      if (active) setState({ loading: false, tasks, error: '' });
    }).catch((failure) => {
      if (active) setState({ loading: false, tasks: [], error: failure.message });
    });
    return () => { active = false; };
  }, [attempt]);
  async function submit(event) {
    event.preventDefault();
    if (busy || !selected) return;
    setBusy(true);
    setError('');
    try {
      if (beforeSubmit && await beforeSubmit() === false) {
        setError(t('Save all essay tabs before submitting. Resolve any save errors and try again.'));
        return;
      }
      const task = await api.update('tasks', Number(selected), { submission_essay: essay.id, status: 'submitted' });
      notify(t('Essay submitted. Your counselor can now comment on it.'));
      onSubmitted?.({ ...state.tasks.find((item) => String(item.id) === selected), ...task });
      onClose();
    } catch (failure) {
      setError(failure.message);
    } finally { setBusy(false); }
  }
  return <Dialog title={t('Submit essay to a task')} onClose={() => { if (!busy) onClose(); }}>
    <form className="el-form" onSubmit={submit}>
      <p className="el-dialog-text"><b>{essay.title}</b></p>
      <p className="el-dialog-text">{t('Submitting an essay shares it with your counselor for comments. Later saved edits remain visible.')}</p>
      {state.loading ? <p role="status">{t('Loading tasks…')}</p> : state.error ? <p role="alert">{state.error} <button type="button" className="el-btn is-small" onClick={() => setAttempt((current) => current + 1)}>{t('Retry')}</button></p> : state.tasks.length ? <label className="el-field">
        <span className="el-label">{t('Choose an assigned task')}</span>
        <select className="el-input" name="task" required value={selected} disabled={busy} onChange={(event) => setSelected(event.target.value)}>
          <option value="">{t('Select')}</option>
          {state.tasks.map((task) => <option key={task.id} value={task.id}>{task.title} · {dateText(task.due_date)}</option>)}
        </select>
      </label> : <p role="status">{t('No open assigned tasks. Submitted and approved tasks are not listed.')}</p>}
      {error && <p className="el-alert is-error" role="alert">{error}</p>}
      <div className="el-dialog-actions">
        <button type="button" className="el-btn" disabled={busy} onClick={onClose}>{t('Cancel')}</button>
        <button type="submit" className="el-btn is-primary" disabled={busy || state.loading || !state.tasks.some((task) => String(task.id) === selected)} aria-busy={busy}>{t(busy ? 'Submitting…' : 'Submit essay')}</button>
      </div>
    </form>
  </Dialog>;
}
