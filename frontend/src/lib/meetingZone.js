// Meetings are shown in one chosen zone: Tashkent by default (it must stay first: unknown ids fall back
// to it). Only zones WITHOUT daylight saving are listed, so each is a fixed offset; London, Europe or the
// US would need a real zone conversion in weeklyZone.js and BookingsPage first. The choice is the
// viewer's own and is remembered in this browser; the Meetings page and the dashboard both read it here.
export const MEETING_ZONES = [
  { id: 'Asia/Tashkent', label: 'Tashkent time', offset: '+05:00', minutes: 300 },
  { id: 'Europe/Moscow', label: 'Moscow time', offset: '+03:00', minutes: 180 },
  { id: 'Europe/Istanbul', label: 'Istanbul time', offset: '+03:00', minutes: 180 },
  { id: 'Asia/Riyadh', label: 'Saudi Arabia time', offset: '+03:00', minutes: 180 },
  { id: 'Asia/Dubai', label: 'Dubai time', offset: '+04:00', minutes: 240 },
  { id: 'Asia/Bishkek', label: 'Bishkek time', offset: '+06:00', minutes: 360 },
  { id: 'Asia/Ho_Chi_Minh', label: 'Vietnam time (Hanoi)', offset: '+07:00', minutes: 420 },
  { id: 'Asia/Bangkok', label: 'Thailand time', offset: '+07:00', minutes: 420 },
  { id: 'Asia/Shanghai', label: 'China time', offset: '+08:00', minutes: 480 },
  { id: 'Asia/Singapore', label: 'Singapore time', offset: '+08:00', minutes: 480 },
  { id: 'Asia/Kuala_Lumpur', label: 'Malaysia time', offset: '+08:00', minutes: 480 },
  { id: 'Asia/Seoul', label: 'Korea time', offset: '+09:00', minutes: 540 },
  { id: 'Asia/Tokyo', label: 'Japan time', offset: '+09:00', minutes: 540 },
];
export const MEETING_ZONE_KEY = 'naseeb.meetingZone';
export const zoneById = (id) => MEETING_ZONES.find((zone) => zone.id === id) || MEETING_ZONES[0];
export function storedMeetingZoneId() {
  try { return zoneById(window.localStorage.getItem(MEETING_ZONE_KEY)).id; } catch { return MEETING_ZONES[0].id; }
}
