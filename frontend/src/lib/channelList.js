// Why the chat list shows an empty note: 'search' (nothing matches), 'none'
// (no channels), or '' when there is something to show. The unsearched
// Private tab always lists Saved Messages (the channel or its placeholder),
// so it is never empty.
export function channelListEmpty(tab, search, channelCount) {
  if (channelCount > 0) return '';
  if (search) return 'search';
  return tab === 'direct' ? '' : 'none';
}
