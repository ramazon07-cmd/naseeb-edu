// Why the chat list shows an empty note: 'search' (nothing matches), 'none'
// (no channels), or '' when there is something to show. The unsearched
// Private tab always lists Saved Messages (the channel or its placeholder),
// so it is never empty.
export function channelListEmpty(tab, search, channelCount) {
  if (channelCount > 0) return '';
  if (search) return 'search';
  return tab === 'direct' ? '' : 'none';
}

// A refreshed first page of folder `kind` merged into the loaded chats. Rows on
// the page replace their old copies; other folders are untouched. With
// `keepLoaded` (the same folder and search as the rows already listed), chats
// loaded from later pages stay after it instead of vanishing. `fetched`: chats
// fetched on their own (the open one, when it is not on page 1), updated or
// added; `gone`: ids that no longer exist for this user, removed.
export function mergeChannelPage(current, kind, page, { keepLoaded = false, fetched = [], gone = [] } = {}) {
  const onPage = new Set(page.map((channel) => channel.id));
  const drop = new Set(gone);
  const fresh = new Map(fetched.filter((channel) => channel.kind === kind && !onPage.has(channel.id)).map((channel) => [channel.id, channel]));
  const later = keepLoaded ? current.filter((item) => item.kind === kind && !onPage.has(item.id)).map((item) => fresh.get(item.id) || item) : [];
  const laterIds = new Set(later.map((item) => item.id));
  return [
    ...current.filter((item) => item.kind !== kind),
    ...page,
    ...later,
    ...[...fresh.values()].filter((channel) => !laterIds.has(channel.id)),
  ].filter((item) => !drop.has(item.id));
}
