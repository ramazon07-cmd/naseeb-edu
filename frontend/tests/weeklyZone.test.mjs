import test from 'node:test';
import assert from 'node:assert/strict';
import { convertZone, shiftRange, tashkentToZone, zoneToTashkent } from '../src/lib/weeklyZone.js';

const CHINA = 480;
const TASHKENT = 300;

test('Tashkent is left exactly as it is', () => {
  const hours = { 0: [['09:00', '12:00']], 6: [['22:00', '00:00']] };
  assert.equal(zoneToTashkent(hours, TASHKENT), hours);
  assert.equal(tashkentToZone(hours, TASHKENT), hours);
});

test('China clock to Tashkent: three hours earlier on the same day', () => {
  assert.deepEqual(zoneToTashkent({ 0: [['09:00', '12:00']], 2: [['14:00', '16:30']] }, CHINA), { 0: [['06:00', '09:00']], 2: [['11:00', '13:30']] });
});

test('the owner case: Tashkent 21:00-23:15 is China 00:00-02:15 the next day', () => {
  assert.deepEqual(tashkentToZone({ 0: [['21:00', '23:15']] }, CHINA), { 1: [['00:00', '02:15']] });
  assert.deepEqual(zoneToTashkent({ 1: [['00:00', '02:15']] }, CHINA), { 0: [['21:00', '23:15']] });
});

test('wrapping backwards: China Monday 01:00-02:00 is Tashkent Sunday 22:00-23:00', () => {
  assert.deepEqual(zoneToTashkent({ 0: [['01:00', '02:00']] }, CHINA), { 6: [['22:00', '23:00']] });
});

test('wrapping forwards: Tashkent Sunday 22:00-23:00 is China Monday 01:00-02:00', () => {
  assert.deepEqual(tashkentToZone({ 6: [['22:00', '23:00']] }, CHINA), { 0: [['01:00', '02:00']] });
});

test('a range that straddles midnight after converting is split into two days', () => {
  // China Mon 01:00-05:00 = Tashkent Sun 22:00 - Mon 02:00.
  assert.deepEqual(zoneToTashkent({ 0: [['01:00', '05:00']] }, CHINA), { 6: [['22:00', '00:00']], 0: [['00:00', '02:00']] });
  // China Wed 22:00-00:00 stays inside the day; China Wed 23:00-00:00 too.
  assert.deepEqual(zoneToTashkent({ 2: [['22:00', '00:00']] }, CHINA), { 2: [['19:00', '21:00']] });
  // Tashkent Tue 22:00-00:00 = China Wed 01:00-03:00 (no split); Tashkent Tue 20:00-00:00 = China Tue 23:00-Wed 03:00.
  assert.deepEqual(tashkentToZone({ 1: [['20:00', '00:00']] }, CHINA), { 1: [['23:00', '00:00']], 2: [['00:00', '03:00']] });
});

test('a split range comes back as one range (round trip)', () => {
  const china = { 0: [['01:00', '05:00']], 3: [['09:00', '12:00'], ['13:00', '15:00']], 4: [['23:00', '00:00']] };
  const there = zoneToTashkent(china, CHINA);
  assert.deepEqual(tashkentToZone(there, CHINA), china);
  const tashkent = { 0: [['00:00', '02:00']], 6: [['22:00', '00:00']], 2: [['10:00', '11:00']] };
  assert.deepEqual(zoneToTashkent(tashkentToZone(tashkent, CHINA), CHINA), { 0: [['00:00', '02:00']], 6: [['22:00', '00:00']], 2: [['10:00', '11:00']] });
});

test('separate ranges the owner typed are not merged', () => {
  assert.deepEqual(zoneToTashkent({ 1: [['09:00', '10:00'], ['10:00', '11:00']] }, CHINA), { 1: [['06:00', '07:00'], ['07:00', '08:00']] });
});

test('the week wraps: Sunday late into Monday early', () => {
  assert.deepEqual(zoneToTashkent({ 0: [['00:00', '01:00']], 6: [['23:00', '00:00']] }, CHINA), { 6: [['20:00', '22:00']] });
});

test('switching the zone while editing goes through the right offset', () => {
  assert.deepEqual(convertZone({ 1: [['00:00', '02:15']] }, CHINA, TASHKENT), { 0: [['21:00', '23:15']] });
  assert.deepEqual(convertZone({ 0: [['21:00', '23:15']] }, TASHKENT, CHINA), { 1: [['00:00', '02:15']] });
});

test('invalid or empty input is skipped, not thrown on', () => {
  assert.deepEqual(zoneToTashkent({ 0: [['', '10:00'], ['10:00', '09:00']], 1: [] }, CHINA), {});
  assert.deepEqual(zoneToTashkent(undefined, CHINA), {});
});

test('shiftRange describes one typed range on the other clock', () => {
  assert.deepEqual(shiftRange(0, '01:00', '02:00', TASHKENT - CHINA), [{ day: 6, from: '22:00', to: '23:00' }]);
  assert.deepEqual(shiftRange(0, '01:00', '05:00', TASHKENT - CHINA), [{ day: 0, from: '00:00', to: '02:00' }, { day: 6, from: '22:00', to: '00:00' }].sort((x, y) => x.day - y.day));
});
