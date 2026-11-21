// The student's pinned rows at the top of Messages, in this order: the Naseeb Edu
// Telegram channel, their assigned counselor, then Saved Messages and the rest.
// `counselor` is /users/accounts/me/'s `counselor` ({ id, full_name, direct_channel_id }) or null.

const normalize = (value) => String(value || '').trim().toLowerCase();

// The listed chat with the counselor: the known direct channel id, else a direct
// chat (not Saved Messages) named after them, e.g. one the counselor opened after
// this page loaded.
export function findCounselorChannel(channels, counselor, channelId = counselor?.direct_channel_id) {
  if (!counselor) return null;
  const byId = channelId != null ? channels.find((channel) => channel.id === channelId) : null;
  if (byId) return byId;
  const name = normalize(counselor.full_name);
  return channels.find((channel) => channel.kind === 'direct' && !channel.is_saved_messages && name && normalize(channel.display_name) === name) || null;
}

// Whether a pinned row survives the search box (an empty search keeps it).
export const pinnedMatches = (search, ...names) => {
  const term = normalize(search);
  return !term || names.some((name) => normalize(name).includes(term));
};

export const TELEGRAM_SEARCH_NAMES = ['naseeb edu', 'telegram', 'naseeb_edu'];

// The pinned rows to draw for a student, top to bottom. Telegram shows in All and
// Groups, the counselor in All and Private; parents and staff get none.
export function pinnedRows({ role, tab, search = '', counselor = null }) {
  if (role !== 'student') return [];
  const rows = [];
  if (['all', 'group'].includes(tab) && pinnedMatches(search, ...TELEGRAM_SEARCH_NAMES)) rows.push('telegram');
  if (counselor && ['all', 'direct'].includes(tab) && pinnedMatches(search, counselor.full_name)) rows.push('counselor');
  return rows;
}

// The list under the pinned rows: the counselor's chat moves up into its pinned row.
export const withoutPinned = (channels, pinned) => (pinned ? channels.filter((channel) => channel.id !== pinned.id) : channels);
