// What a page shows while workspace collections load: a skeleton only until
// the page's own data (or, on sign-in, anything at all) has arrived. Pages
// whose lists are server-paged track their own loading, so a later workspace
// refresh (after a save) must not unmount them and lose their state.
//
// `lazy` (students, who fetch a page's collections when it first opens): the
// skeleton stays until every one of the page's keys has arrived or failed, so
// the page never flashes "nothing here yet" for a list that is still on its
// way; a background refresh of an already-loaded key keeps the page shown.
export function pageLoadState({ keys, data, stats, loading, resourceStatus, lazy = false }) {
  const tracked = keys.filter((key) => resourceStatus[key]);
  const loadingKeys = tracked.filter((key) => resourceStatus[key].status === 'loading');
  const failedKeys = tracked.filter((key) => resourceStatus[key].status === 'error');
  const hasVisibleData = keys.some((key) => key === 'dashboard' ? Boolean(stats) : Boolean(data[key]?.length));
  if (lazy) {
    const firstLoadKeys = keys.filter((key) => !resourceStatus[key] || (resourceStatus[key].status === 'loading' && !resourceStatus[key].loaded));
    return { loadingKeys, failedKeys, hasVisibleData, initialLoading: firstLoadKeys.length > 0 };
  }
  const firstLoad = loading && Object.keys(resourceStatus).length === 0;
  const initialLoading = (loadingKeys.length > 0 || firstLoad) && !hasVisibleData;
  return { loadingKeys, failedKeys, hasVisibleData, initialLoading };
}
