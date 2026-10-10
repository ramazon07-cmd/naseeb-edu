// The loaded list with the copies saved on this page laid over it: a saved copy
// wins only while it is newer than the loaded one, so a refresh that brings the
// same or a later version takes over. Rows saved here but not loaded yet lead.
export function mergeSaved(loaded, saved) {
  const time = (item) => Date.parse(item?.updated_at || '') || 0;
  const savedById = new Map(saved.map((item) => [item.id, item]));
  const loadedIds = new Set(loaded.map((item) => item.id));
  const merged = loaded.map((item) => {
    const copy = savedById.get(item.id);
    return copy && time(copy) > time(item) ? copy : item;
  });
  return [...saved.filter((item) => !loadedIds.has(item.id)), ...merged];
}
