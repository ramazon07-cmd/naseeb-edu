import { useEffect, useState } from 'react';
import { CheckCircle2, Clock3, MessageSquare } from 'lucide-react';
import { api } from '../api';
import { t } from '../i18n';
import { dateTimeText } from '../lib/format';
import { createPoller } from '../lib/poller';
import { buildPath } from '../lib/routes';

export default function EssayTaskStatus({ essayId, submittedTask, onComments }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ tasks: [], error: '' });
  useEffect(() => {
    let active = true;
    setState({ tasks: submittedTask ? [submittedTask] : [], error: '' });
    const poller = createPoller({
      min: 30_000,
      revisitMin: 5_000,
      run: async () => {
        try {
          const rows = await api.list('tasks', `?submission_essay=${encodeURIComponent(essayId)}&self_assigned=false`);
          if (active) setState({ tasks: rows.filter((task) => task.submitted_at || ['submitted', 'approved'].includes(task.status)), error: '' });
          return true;
        } catch (error) {
          if (active) setState((current) => ({ ...current, error: error.message }));
          return null;
        }
      },
    });
    poller.start({ immediate: true });
    return () => { active = false; poller.stop(); };
  }, [essayId, submittedTask, attempt]);
  if (!state.tasks.length && !state.error) return null;
  return <div className="el-task-submissions" aria-label={t('Essay task submissions')}>
    <EssayTaskStatusRows tasks={state.tasks} onComments={onComments} />
    {state.error && <p className="el-submission-error" role="alert">{t('Submission status could not be refreshed.')} <button type="button" className="el-btn is-small" onClick={() => setAttempt((current) => current + 1)}>{t('Retry')}</button></p>}
  </div>;
}

export function EssayTaskStatusRows({ tasks, onComments }) {
  return tasks.map((task) => {
    const approved = task.status === 'approved';
    const returned = !approved && task.status !== 'submitted';
    const Icon = approved ? CheckCircle2 : returned ? MessageSquare : Clock3;
    return <div key={task.id} className={`el-task-submission${approved ? ' is-approved' : returned ? ' is-returned' : ''}`} role="status">
      <Icon size={20} aria-hidden="true" />
      <div className="el-task-submission-copy">
        <b>{t(approved ? 'Approved by counselor' : returned ? 'Changes requested — update and resubmit' : 'Awaiting counselor review')}</b>
        <span>{task.title}{task.submitted_at ? ` · ${dateTimeText(task.submitted_at)}` : ''}</span>
      </div>
      {onComments && <button type="button" className="el-btn is-small is-ghost" onClick={onComments}>{t('View comments')}</button>}
      <a className="el-btn is-small is-ghost" href={buildPath({ page: 'tasks' })} target="_blank" rel="noreferrer">{t('View tasks')}</a>
    </div>;
  });
}
