// api.list() loads whole (bounded) collections, so it asks for the largest
// page the API allows (backend core/pagination.py) instead of 25 rows per
// request. The `next` links the API returns keep the page size.
export const LIST_PAGE_SIZE = 100;

// query: '' or '?key=value&...'
export function firstListPath(resource, query = '') {
  const params = new URLSearchParams(query.replace(/^\?/, ''));
  params.set('page_size', String(LIST_PAGE_SIZE));
  return `/${resource}/?${params}`;
}
