// Paging rules of the counselor's Students list (pages/CounselorStudents.jsx).

export const pageCount = (count, pageSize) => Math.max(1, Math.ceil((count || 0) / pageSize));

// The page to move to once a page request has settled, or null to stay.
// A 404 is the server's "Invalid page" (students left the filter, or Back from
// a profile to a page that no longer exists): go to the last page the filter's
// total (from /students/summary/) still has, or page 1 when that is unknown.
// Any other failure stays put, so the error and its Retry show.
export function pageAfterLoad({ page, pageSize, count, status, error, total }) {
  if (error) {
    if (status !== 404 || page <= 1) return null;
    const last = Number.isFinite(total) ? pageCount(total, pageSize) : 1;
    return Math.min(page - 1, last);
  }
  const last = pageCount(count, pageSize);
  return page > last ? last : null;
}

// The failed request's state: its own key (so it is not "stale") and no rows
// from an earlier page under a pager that no longer matches them.
export function failedPage(key, failure) {
  return { key, items: [], count: 0, loading: false, error: failure?.message || 'Request failed.', status: failure?.status || 0 };
}
