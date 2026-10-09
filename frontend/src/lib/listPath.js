// api.list() loads whole (bounded) collections, so it asks for the largest
// page the API allows (backend core/pagination.py) instead of 25 rows per
// request. The `next` links the API returns keep the page size.
export const LIST_PAGE_SIZE = 100;
// The university catalogue (~1,500 slim rows) allows larger pages (CatalogPagination).
export const PAGE_SIZES = { universities: 500 };

// query: '' or '?key=value&...'
export function firstListPath(resource, query = '') {
  const params = new URLSearchParams(query.replace(/^\?/, ''));
  params.set('page_size', String(PAGE_SIZES[resource] || LIST_PAGE_SIZE));
  return `/${resource}/?${params}`;
}
