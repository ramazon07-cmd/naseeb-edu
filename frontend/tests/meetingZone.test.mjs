import test from 'node:test';
import assert from 'node:assert/strict';
import { MEETING_ZONES, zoneById } from '../src/lib/meetingZone.js';
import { tashkentToZone, zoneToTashkent } from '../src/lib/weeklyZone.js';

const offsetOn = (zone, day) => new Intl.DateTimeFormat('en', { timeZone: zone, timeZoneName: 'longOffset' })
  .formatToParts(new Date(day)).find((part) => part.type === 'timeZoneName').value;

test('every meeting zone is a fixed offset all year, matching its offset and minutes', () => {
  for (const zone of MEETING_ZONES) {
    assert.equal(offsetOn(zone.id, '2026-01-15T12:00:00Z'), `GMT${zone.offset}`, zone.id);
    assert.equal(offsetOn(zone.id, '2026-07-15T12:00:00Z'), `GMT${zone.offset}`, zone.id);
    assert.equal(zone.minutes, Number(zone.offset.slice(1, 3)) * 60 + Number(zone.offset.slice(4, 6)), zone.id);
  }
});

test('Tashkent stays the fallback for an unknown or missing zone', () => {
  assert.equal(MEETING_ZONES[0].id, 'Asia/Tashkent');
  assert.equal(zoneById('Europe/London').id, 'Asia/Tashkent');
  assert.equal(zoneById('Asia/Ho_Chi_Minh').minutes, 420);
});

test('a zone west of Tashkent: Moscow Monday 22:00-23:30 is Tashkent Tuesday 00:00-01:30', () => {
  assert.deepEqual(zoneToTashkent({ 0: [['22:00', '23:30']] }, 180), { 1: [['00:00', '01:30']] });
  assert.deepEqual(tashkentToZone({ 1: [['00:00', '01:30']] }, 180), { 0: [['22:00', '23:30']] });
});
