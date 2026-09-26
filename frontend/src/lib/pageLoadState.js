// What a page shows while workspace collections load: a skeleton only until
// the page's own data (or, on sign-in, anything at all) has arrived. Pages
// whose lists are server-paged track their own loading, so a later workspace
// refresh (after a save) must not unmount them and lose their state.
export function pageLoadState({ keys, data, stats, loading, resourceStatus }) {
  const tracked = keys.filter((key) => resourceStatus[key]);
  const loadingKeys = tracked.filter((key) => resourceStatus[key].status === 'loading');
  const failedKeys = tracked.filter((key) => resourceStatus[key].status === 'error');
  const hasVisibleData = keys.some((key) => key === 'dashboard' ? Boolean(stats) : Boolean(data[key]?.length));
  const firstLoad = loading && Object.keys(resourceStatus).length === 0;
  const initialLoading = (loadingKeys.length > 0 || firstLoad) && !hasVisibleData;
  return { loadingKeys, failedKeys, hasVisibleData, initialLoading };
}
