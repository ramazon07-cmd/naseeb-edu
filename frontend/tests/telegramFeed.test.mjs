import test from 'node:test';
import assert from 'node:assert/strict';
import { createHeightMemory, mergeTelegramPosts, skeletonShape, telegramEmbedUrl } from '../src/lib/telegramFeed.js';

test('latest post is last, with numeric chronological ordering', () => {
  assert.deepEqual(mergeTelegramPosts([], ['naseeb_edu/151', 'naseeb_edu/9', 'naseeb_edu/132']), ['naseeb_edu/9', 'naseeb_edu/132', 'naseeb_edu/151']);
});

test('older pages prepend without duplicates or dropping current posts', () => {
  const current = ['naseeb_edu/132', 'naseeb_edu/151'];
  assert.deepEqual(mergeTelegramPosts(current, ['naseeb_edu/132', 'naseeb_edu/110']), ['naseeb_edu/110', 'naseeb_edu/132', 'naseeb_edu/151']);
  assert.deepEqual(current, ['naseeb_edu/132', 'naseeb_edu/151']);
});

test('only safe fixed-channel post identifiers reach embed URLs', () => {
  assert.deepEqual(mergeTelegramPosts([], ['other/1', 'naseeb_edu/0', 'naseeb_edu/1?dark=1', null, {}, 'naseeb_edu/12']), ['naseeb_edu/12']);
});

test('embed URL explicitly forces the selected theme', () => {
  assert.match(telegramEmbedUrl('naseeb_edu/151', false), /&dark=0$/);
  assert.match(telegramEmbedUrl('naseeb_edu/151', true), /&dark=1&dark_color=9CCBDD$/);
});

const memoryStorage = () => {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) };
};

test('a measured height is remembered per post and per width bucket', () => {
  const heights = createHeightMemory(memoryStorage());
  heights.set('naseeb_edu/151', 520, 864.4);
  assert.equal(heights.get('naseeb_edu/151', 515), 864);
  assert.equal(heights.get('naseeb_edu/151', 340), undefined);
  assert.equal(heights.get('naseeb_edu/150', 520), undefined);
});

test('heights outlive the component, and only the newest are kept', () => {
  const storage = memoryStorage();
  const first = createHeightMemory(storage, 3);
  [1, 2, 3, 4].forEach((id) => first.set(`naseeb_edu/${id}`, 520, 100 + id));
  const second = createHeightMemory(storage, 3);
  assert.equal(second.get('naseeb_edu/1', 520), undefined);
  assert.equal(second.get('naseeb_edu/4', 520), 104);
});

test('blocked or corrupt storage only costs the hint', () => {
  const blocked = { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } };
  const heights = createHeightMemory(blocked);
  heights.set('naseeb_edu/9', 520, 300);
  assert.equal(heights.get('naseeb_edu/9', 520), 300);
  assert.equal(createHeightMemory({ getItem: () => '{not json', setItem() {} }).get('naseeb_edu/9', 520), undefined);
});

test('a skeleton follows the height of its post and is the same every time', () => {
  assert.equal(skeletonShape('naseeb_edu/151', 160).lines.length, 3);
  const tall = skeletonShape('naseeb_edu/151', 900);
  assert.ok(tall.lines.length > 20 && tall.lines.length <= 30);
  assert.ok(tall.lines.every((width) => width >= 44 && width <= 96));
  assert.deepEqual(skeletonShape('naseeb_edu/151', 900), tall);
  assert.deepEqual([150, 151, 152].map((id) => skeletonShape(`naseeb_edu/${id}`, 300).media), [true, false, false]);
});
