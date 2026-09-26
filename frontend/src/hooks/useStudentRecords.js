import { useEffect, useState } from 'react';
import { api } from '../api';

// The per-student collections a Student 360 view shows. One student's records
// are small, so each is loaded whole (?student=<id>) in parallel.
export const STUDENT_RECORD_ENDPOINTS = ['tasks', 'applications', 'documents', 'essays', 'achievements', 'researches', 'projects', 'internships', 'activities', 'honors', 'recommendations'];

const EMPTY = Object.freeze({});

export function useStudentRecords(studentId, enabled = true) {
  const [state, setState] = useState({ studentId: null, records: EMPTY, loading: false, error: '' });
  useEffect(() => {
    if (!enabled || !studentId) return undefined;
    let current = true;
    setState({ studentId, records: EMPTY, loading: true, error: '' });
    const query = `?student=${encodeURIComponent(studentId)}`;
    Promise.allSettled(STUDENT_RECORD_ENDPOINTS.map((endpoint) => api.list(endpoint, query))).then((settled) => {
      if (!current) return;
      const records = {};
      let error = '';
      settled.forEach((result, index) => {
        if (result.status === 'fulfilled') records[STUDENT_RECORD_ENDPOINTS[index]] = result.value || [];
        else error ||= result.reason?.message || 'Unable to load this section.';
      });
      setState({ studentId, records, loading: false, error });
    });
    // A slower response for a previously opened student must not show here.
    return () => {current = false;};
  }, [studentId, enabled]);
  return state.studentId === studentId ? state : { studentId, records: EMPTY, loading: enabled && Boolean(studentId), error: '' };
}
