// An empty value is meaningful only after its request succeeded.
export function resourceDisplayState(status) {
  if (status?.loaded) return status.status === 'error' ? 'stale' : 'ready';
  return status?.status === 'error' ? 'error' : 'loading';
}

// Only pages whose content depends on the profile block on its first failure.
// Account security, messages and the independent tools remain reachable.
const STUDENT_PRIMARY_KEYS = {
  dashboard: ['students'], student_center: ['students'], roadmap: ['students'],
  college_search: ['students', 'applications'], applications: ['students', 'applications'],
};
export const studentPrimaryKeys = (page) => STUDENT_PRIMARY_KEYS[page] || [];
