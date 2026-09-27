// Roving focus for a vertical menu: which item a key moves to, or null when the
// key is not a navigation key. Wraps at both ends.
export function nextMenuIndex(key, index, count) {
  if (!count) return null;
  const target = { ArrowDown: index + 1, ArrowUp: index < 0 ? count - 1 : index - 1, Home: 0, End: count - 1 }[key];
  return target === undefined ? null : (target + count) % count;
}
