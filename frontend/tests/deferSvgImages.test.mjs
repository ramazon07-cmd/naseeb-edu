import assert from 'node:assert/strict';
import test from 'node:test';
import { deferSvgImages } from '../src/deferSvgImages.js';

function fixture() {
  const images = ['/landing/universities/hku.svg', '/landing/universities/vinuni.png'].map((src) => {
    const attributes = new Map([['data-deferred-href', src]]);
    return {
      parentElement: {},
      hasAttribute: (key) => attributes.has(key),
      getAttribute: (key) => attributes.get(key),
      setAttribute: (key, value) => attributes.set(key, value),
    };
  });
  const root = { querySelectorAll: () => images };
  let instance;
  class Observer {
    observed = new Set();
    disconnected = false;
    constructor(callback, options) {
      this.callback = callback;
      this.options = options;
      instance = this;
    }
    observe(node) { this.observed.add(node); }
    unobserve(node) { this.observed.delete(node); }
    disconnect() { this.disconnected = true; }
  }
  return { root, images, Observer, observer: () => instance };
}

test('keeps below-the-fold SVG URLs inactive and reserves a prefetch margin', () => {
  const f = fixture();
  deferSvgImages(f.root, f.Observer);
  assert.equal(f.observer().observed.size, 1);
  assert.ok(f.observer().observed.has(f.root));
  assert.deepEqual(f.observer().options, { rootMargin: '800px 0px', threshold: 0 });
  f.observer().callback([{ target: f.root, isIntersecting: false }]);
  assert.ok(f.images.every((image) => !image.hasAttribute('href')));
});

test('warms all approaching story emblems once, keeping the original shared URLs', () => {
  const f = fixture();
  deferSvgImages(f.root, f.Observer);
  const entry = { target: f.root, isIntersecting: true };
  f.observer().callback([entry]);
  assert.equal(f.images[0].getAttribute('href'), f.images[0].getAttribute('data-deferred-href'));
  assert.equal(f.images[1].getAttribute('href'), f.images[1].getAttribute('data-deferred-href'));
  assert.equal(f.observer().disconnected, true);
  assert.doesNotThrow(() => f.observer().callback([entry]));
});

test('disconnects on unmount and skips previously loaded images on remount', () => {
  const f = fixture();
  f.images[0].setAttribute('href', f.images[0].getAttribute('data-deferred-href'));
  const cleanup = deferSvgImages(f.root, f.Observer);
  assert.equal(f.observer().observed.size, 1);
  cleanup();
  assert.equal(f.observer().disconnected, true);
});

test('falls back to visible artwork without IntersectionObserver', () => {
  const f = fixture();
  const cleanup = deferSvgImages(f.root, null);
  assert.ok(f.images.every((image) => image.getAttribute('href') === image.getAttribute('data-deferred-href')));
  assert.doesNotThrow(cleanup);
});
