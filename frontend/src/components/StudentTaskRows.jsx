import { t } from '../i18n';
import { label } from '../lib/labels';
import { daysUntil } from '../lib/college';
import { nextPriorities } from '../lib/metrics';
import { Chip, DateTile, tileParts } from '../design/blue/ui';

// The student's open tasks as one-line rows (date tile, title, status), soonest first. Student views only:
// staff keep ResourceSection. Reads the tasks already in memory; opening or editing a task stays in the full list.
export function StudentTaskRows({ tasks, limit = 5 }) {
  const rows = nextPriorities(tasks || []).slice(0, limit);
  if (!rows.length) return null;
  return <ul className="nb-task-rows" aria-label={t('Next up')}>
    {rows.map((task) => {
      const days = task.due_date ? daysUntil(task.due_date) : null;
      const late = days != null && days < 0;
      return <li key={task.id} className={late ? 'is-late' : undefined}>
        {task.due_date ? <DateTile hot={late} {...tileParts(task.due_date)} /> : <span className="nb-date nb-date-none" aria-hidden="true"><b>–</b></span>}
        <span className="nb-task-row-title">{task.title}</span>
        <Chip variant={late ? 'overdue' : task.status === 'submitted' ? 'warn' : 'default'}>{late ? t('Overdue') : label(task.status)}</Chip>
      </li>;
    })}
  </ul>;
}
