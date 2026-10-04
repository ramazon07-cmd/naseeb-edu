// Fixed-channel IDs only, chronological order: the newest post belongs at bottom.
export function mergeTelegramPosts(current, incoming) {
  return [...new Set([...current, ...incoming].filter((post) => typeof post === 'string' && /^naseeb_edu\/[1-9][0-9]{0,11}$/.test(post)))]
    .sort((a, b) => Number(a.split('/')[1]) - Number(b.split('/')[1]));
}

export function telegramEmbedUrl(post, dark) {
  const mode = dark ? '1' : '0';
  return `https://t.me/${post}?embed=1&userpic=false&color=5D8EA3&dark=${mode}${dark ? '&dark_color=9CCBDD' : ''}`;
}

// Sizes the embeds reported, kept for the session: a post shown again starts at
// its real height, so nothing below it jumps when its frame loads. Only a hint.
export const DEFAULT_POST_HEIGHT = 300;
export const MAX_POST_HEIGHT = 20000;
const HEIGHTS_KEY = 'naseeb-telegram-heights-v1';

// Posts are at most 520px wide; narrower screens wrap the text differently.
export const postHeightKey = (post, width) => `${post}@${Math.round(Math.min(Number(width) || 520, 520) / 20) * 20}`;

export function createHeightMemory(storage, limit = 300) {
  let known = null;
  const entries = () => {
    if (known) return known;
    try { known = new Map(JSON.parse(storage?.getItem(HEIGHTS_KEY)).filter(([key, value]) => typeof key === 'string' && value > 0)); } catch { known = new Map(); }
    return known;
  };
  return {
    get: (post, width) => entries().get(postHeightKey(post, width)),
    set(post, width, height) {
      const map = entries();
      const key = postHeightKey(post, width);
      map.delete(key);
      map.set(key, Math.round(height));
      while (map.size > limit) map.delete(map.keys().next().value);
      try { storage?.setItem(HEIGHTS_KEY, JSON.stringify([...map])); } catch { /* storage blocked or full */ }
    },
  };
}

// The outline of a post that has not loaded: lines sized to the height it will
// have, with a media block for every third post. The same post always looks the same.
const LINE_WIDTHS = [96, 88, 92, 74, 90, 82, 94, 68];
export function skeletonShape(post, height) {
  const id = Number(post.split('/')[1]) || 0;
  const media = id % 3 === 0;
  const room = height - 104 - (media ? 148 : 0);
  const count = Math.max(3, Math.min(30, Math.floor(room / 21)));
  const lines = Array.from({ length: count }, (_, index) => LINE_WIDTHS[(index + id) % LINE_WIDTHS.length]);
  lines[count - 1] = 44 + (id % 4) * 8;
  return { media, lines };
}
