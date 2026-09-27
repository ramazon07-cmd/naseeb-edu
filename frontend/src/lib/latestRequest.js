// Guards against out-of-order responses: only the most recently started
// request may write its result. `start()` returns an `isCurrent()` check;
// `cancel()` invalidates whatever is in flight (e.g. when the view closes).
export function createLatestRequest() {
  let generation = 0;
  return {
    start() {
      const mine = ++generation;
      return () => mine === generation;
    },
    cancel() {
      generation += 1;
    },
  };
}

// Per-key variant for loaders that refresh several resources at once: a
// response is applied only if no newer request for the same key started.
export function createKeyedLatest() {
  const generations = new Map();
  let epoch = 0;
  return {
    start(keys) {
      const tokens = new Map();
      for (const key of keys) {
        const next = (generations.get(key) || 0) + 1;
        generations.set(key, next);
        tokens.set(key, `${epoch}:${next}`);
      }
      return (key) => tokens.get(key) === `${epoch}:${generations.get(key)}`;
    },
    // Invalidates everything in flight (sign-out, user switch).
    cancelAll() {
      epoch += 1;
    },
  };
}
