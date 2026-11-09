// Selecting students on the counselor's Students list (pages/CounselorStudents.jsx).

// The most students one bulk task may name; the server (BULK_TASK_LIMIT) refuses more.
export const BULK_TASK_LIMIT = 500;
// The server's largest page (core/pagination.py MAX_PAGE_SIZE).
export const SELECT_PAGE_SIZE = 100;

// 'none', 'some' or 'all' of the listed students are ticked.
export function pageSelectionState(pageIds, selected) {
  if (!pageIds.length) return 'none';
  const ticked = pageIds.filter((id) => selected.has(id)).length;
  if (!ticked) return 'none';
  return ticked === pageIds.length ? 'all' : 'some';
}

// The header box: ticks every listed student unless they are all ticked already, then unticks them.
// Students selected on other pages are left as they are.
export function togglePageSelection(selected, pageIds) {
  const next = new Set(selected);
  const clear = pageSelectionState(pageIds, selected) === 'all';
  for (const id of pageIds) {
    if (clear) next.delete(id); else next.add(id);
  }
  return next;
}

// "Select all N": offered once the whole page is ticked and more students match the filters,
// as long as they fit in one bulk assignment. A filter change clears the selection, so the
// selected students are always among the N matches.
export function canSelectAllMatching({ total, pageIds, selected }) {
  return pageIds.length > 0
    && total > pageIds.length
    && total <= BULK_TASK_LIMIT
    && pageSelectionState(pageIds, selected) === 'all'
    && selected.size < total;
}

// Every student id matching the filters, one page after another (never in parallel).
// `fetchPage(page)` resolves to { results, count }; an `aborted()` caller stops early.
export async function collectMatchingIds(fetchPage, { total, pageSize = SELECT_PAGE_SIZE, aborted = () => false }) {
  const ids = [];
  const pages = Math.ceil(Math.min(total, BULK_TASK_LIMIT) / pageSize);
  for (let page = 1; page <= pages; page += 1) {
    const result = await fetchPage(page);
    if (aborted()) return null;
    for (const item of result?.results || []) ids.push(item.id);
  }
  return ids.slice(0, BULK_TASK_LIMIT);
}
