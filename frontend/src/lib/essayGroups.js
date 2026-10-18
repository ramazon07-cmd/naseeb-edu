// One block per student, newest work first; students with an essay waiting for the
// counselor come before the rest. Built from the pages loaded so far.
export function groupByStudent(items) {
  const groups = new Map();
  for (const item of items) {
    const group = groups.get(item.student) || { student: item.student, name: item.student_name, essays: [], waiting: false, latest: '' };
    group.essays.push(item);
    group.waiting ||= item.status === 'reviewing';
    if (item.updated_at > group.latest) group.latest = item.updated_at;
    groups.set(item.student, group);
  }
  return [...groups.values()].sort((a, b) => Number(b.waiting) - Number(a.waiting) || b.latest.localeCompare(a.latest));
}
