// Work the student wrote: only the student may delete it (the API refuses staff). Staff send it back instead.
export const STUDENT_AUTHORED_RECORDS = ['essays', 'achievements', 'researches', 'projects', 'internships', 'activities', 'honors'];

export function canDeleteStudentRecord(user, resource) {
  return !STUDENT_AUTHORED_RECORDS.includes(resource) || user?.role === 'student';
}
