// Meetings are shown in one chosen zone: Tashkent by default, or China for people there.
// Neither has daylight saving, so each is a fixed offset. The choice is the viewer's own and is
// remembered in this browser; the Meetings page and the dashboard both read it from here.
export const MEETING_ZONES = [
  { id: 'Asia/Tashkent', label: 'Tashkent time', offset: '+05:00', minutes: 300 },
  { id: 'Asia/Shanghai', label: 'China time', offset: '+08:00', minutes: 480 },
];
export const MEETING_ZONE_KEY = 'naseeb.meetingZone';
export const zoneById = (id) => MEETING_ZONES.find((zone) => zone.id === id) || MEETING_ZONES[0];
export function storedMeetingZoneId() {
  try { return zoneById(window.localStorage.getItem(MEETING_ZONE_KEY)).id; } catch { return MEETING_ZONES[0].id; }
}
