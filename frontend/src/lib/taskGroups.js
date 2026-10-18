// The counselor's Tasks, grouped by student. A task still owed and past its due
// date reads as late whatever its stored status (as Student 360 shows it).

const OWED = ['todo', 'in_progress', 'late'];

export function taskStatus(task, today) {
  return OWED.includes(task.status) && task.due_date && task.due_date < today ? 'late' : task.status;
}

export const TASK_STATUS_TONE = { todo: 'quiet', in_progress: 'quiet', submitted: 'warn', approved: 'ok', late: 'late' };

const dueKey = (task) => task.due_date || '9999-12-31';

// One group per student, tasks by due date; students with late work come first,
// then those with work to review, then whoever is due soonest.
export function groupTasksByStudent(items, today) {
  const groups = new Map();
  for (const task of items) {
    const group = groups.get(task.student) || { student: task.student, name: task.student_name, tasks: [], late: 0, toReview: 0 };
    group.tasks.push(task);
    if (taskStatus(task, today) === 'late') group.late += 1;
    if (task.status === 'submitted') group.toReview += 1;
    groups.set(task.student, group);
  }
  for (const group of groups.values()) group.tasks.sort((a, b) => dueKey(a).localeCompare(dueKey(b)) || a.id - b.id);
  return [...groups.values()].sort((a, b) => Number(b.late > 0) - Number(a.late > 0)
    || Number(b.toReview > 0) - Number(a.toReview > 0)
    || dueKey(a.tasks[0]).localeCompare(dueKey(b.tasks[0]))
    || String(a.name).localeCompare(String(b.name)));
}
