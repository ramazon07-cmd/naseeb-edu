// Weekly hours are stored on Tashkent's clock ({ '0': [['09:00', '12:00']] }, Monday = 0). A counselor who
// works in another zone edits them on THEIR clock; these helpers convert between the two, shifting a range
// to the neighbouring day when it crosses midnight and splitting it when it straddles one.
// Plain minutes, no Date: neither zone has daylight saving, so a zone is a fixed offset.

export const TASHKENT_MINUTES = 300;
const DAY = 1440;
const WEEK = 7 * DAY;

const minutesOf = (text) => Number(text.slice(0, 2)) * 60 + Number(text.slice(3, 5));
const clockOf = (minutes) => (minutes === DAY ? '00:00' : `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`);
const usable = (range) => Array.isArray(range) && /^\d\d:\d\d/.test(range[0] || '') && /^\d\d:\d\d/.test(range[1] || '');

// The week as spans of minutes since Monday 00:00. A range ending at 00:00 runs to midnight, and spans that
// meet at a midnight join into one (Sun 22:00-24:00 + Mon 00:00-02:00 is one continuous stretch), so a range
// that was split at a midnight comes back as one range.
function weekSpans(hours) {
  const spans = [];
  for (const [day, ranges] of Object.entries(hours || {})) {
    for (const range of ranges || []) {
      if (!usable(range)) continue;
      const start = Number(day) * DAY + minutesOf(range[0]);
      const stop = minutesOf(range[1]);
      const end = Number(day) * DAY + (stop === 0 ? DAY : stop);
      if (end > start) spans.push([start, end]);
    }
  }
  spans.sort((x, y) => x[0] - y[0]);
  const joined = [];
  for (const span of spans) {
    const last = joined.at(-1);
    if (last && span[0] === last[1] && last[1] % DAY === 0) last[1] = span[1];
    else joined.push([...span]);
  }
  // Sunday night into Monday morning.
  if (joined.length > 1 && joined[0][0] === 0 && joined.at(-1)[1] === WEEK) {
    const first = joined.shift();
    joined.at(-1)[1] = WEEK + first[1];
  }
  return joined;
}

// Hours moved by `delta` minutes: later (+) or earlier (-) on the clock. Ranges are cut at every midnight.
export function shiftWeeklyHours(hours, delta) {
  if (!delta) return hours || {};
  const shifted = {};
  for (const [from, to] of weekSpans(hours)) {
    let start = from + delta;
    const end = to + delta;
    while (start < end) {
      const day = Math.floor(start / DAY);
      const cut = Math.min(end, (day + 1) * DAY);
      const key = String(((day % 7) + 7) % 7);
      (shifted[key] ||= []).push([clockOf(start - day * DAY), clockOf(cut - day * DAY)]);
      start = cut;
    }
  }
  for (const ranges of Object.values(shifted)) ranges.sort((x, y) => (x[0] < y[0] ? -1 : 1));
  return shifted;
}

// What the editor sends: hours typed on a clock `zoneMinutes` ahead of UTC, on Tashkent's clock.
export const zoneToTashkent = (hours, zoneMinutes) => shiftWeeklyHours(hours, TASHKENT_MINUTES - zoneMinutes);
// What the editor shows: the saved Tashkent hours on that zone's clock.
export const tashkentToZone = (hours, zoneMinutes) => shiftWeeklyHours(hours, zoneMinutes - TASHKENT_MINUTES);
// Hours typed on one zone's clock, on another's (switching the zone picker while editing).
export const convertZone = (hours, fromMinutes, toMinutes) => shiftWeeklyHours(hours, toMinutes - fromMinutes);

// One range ("Mon 01:00-02:00" typed in the chosen zone) on the other clock: [{ day, from, to }], one entry
// per piece (two when it straddles midnight there).
export function shiftRange(day, from, to, delta) {
  const moved = shiftWeeklyHours({ [day]: [[from, to]] }, delta || 0);
  return Object.entries(moved).flatMap(([key, ranges]) => ranges.map(([start, end]) => ({ day: Number(key), from: start, to: end })))
    .sort((x, y) => x.day - y.day || (x.from < y.from ? -1 : 1));
}
