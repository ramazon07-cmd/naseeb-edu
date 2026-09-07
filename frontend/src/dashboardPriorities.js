// Date-only deadlines are compared as local calendar days, not UTC instants.
export function taskPriorities(tasks, now = new Date()) {
  const today = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
  const rank = { urgent: 0, high: 1, medium: 2, low: 3 };
  const actionable = tasks.filter((task) => !['approved', 'submitted'].includes(task.status));
  actionable.sort((a, b) => {
    const overdueA = a.status === 'late' || Boolean(a.due_date && a.due_date < today);
    const overdueB = b.status === 'late' || Boolean(b.due_date && b.due_date < today);
    return Number(overdueB) - Number(overdueA)
      || (a.due_date || '9999').localeCompare(b.due_date || '9999')
      || (rank[a.priority] ?? 4) - (rank[b.priority] ?? 4)
      || String(a.id).localeCompare(String(b.id));
  });
  return {
    actionable,
    reviewing: tasks.filter((task) => task.status === 'submitted'),
    overdue: actionable.filter((task) => task.status === 'late' || Boolean(task.due_date && task.due_date < today)),
  };
}
