import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';

// The per-student collections a Student 360 view shows. One student's records
// are small, so each is loaded whole (?student=<id>) in parallel.
export const STUDENT_RECORD_ENDPOINTS = ['tasks', 'applications', 'documents', 'essays', 'achievements', 'researches', 'projects', 'internships', 'activities', 'honors', 'recommendations', 'roadmap-missions'];

const EMPTY = Object.freeze({});

// The current records stay on screen while a reload runs.
export function useStudentRecords(studentId, enabled = true) {
  const [state, setState] = useState({ studentId: null, records: EMPTY, errors: {}, loading: false });
  const [version, setVersion] = useState(0);
  // Sections asked for that no finished load has fetched yet: a newer reload cancels the
  // older request, so it must fetch them too.
  const pending = useRef(new Set());
  const loadedFor = useRef(null);
  useEffect(() => {
    if (!enabled || !studentId) return undefined;
    const endpoints = loadedFor.current === studentId ? [...pending.current] : STUDENT_RECORD_ENDPOINTS;
    if (!endpoints.length) return undefined;
    // Switching students drops the old student's records, so coming back to them is a full load again.
    if (loadedFor.current !== studentId) loadedFor.current = null;
    let current = true;
    setState((previous) => (previous.studentId === studentId ? { ...previous, loading: true } : { studentId, records: EMPTY, errors: {}, loading: true }));
    const query = `?student=${encodeURIComponent(studentId)}`;
    Promise.allSettled(endpoints.map((endpoint) => api.list(endpoint, query))).then((settled) => {
      if (!current) return;
      loadedFor.current = studentId;
      endpoints.forEach((endpoint) => pending.current.delete(endpoint));
      setState((previous) => {
        const same = previous.studentId === studentId;
        // A section that fails on a reload keeps what it showed before.
        const records = { ...(same ? previous.records : EMPTY) };
        const errors = { ...(same ? previous.errors : {}) };
        settled.forEach((result, index) => {
          const endpoint = endpoints[index];
          if (result.status === 'fulfilled') {
            records[endpoint] = result.value || [];
            delete errors[endpoint];
          } else {
            errors[endpoint] = result.reason?.message || 'Unable to load this section.';
          }
        });
        return { studentId, records, errors, loading: false };
      });
    });
    // A slower response for a previously opened student (or an older reload) must not show here.
    return () => {current = false;};
  }, [studentId, enabled, version]);
  const reload = useCallback((endpoints = STUDENT_RECORD_ENDPOINTS) => {
    endpoints.forEach((endpoint) => pending.current.add(endpoint));
    setVersion((value) => value + 1);
  }, []);
  const shown = state.studentId === studentId ? state : { studentId, records: EMPTY, errors: {}, loading: enabled && Boolean(studentId) };
  return { studentId: shown.studentId, records: shown.records, loading: shown.loading, error: Object.values(shown.errors)[0] || '', reload };
}
