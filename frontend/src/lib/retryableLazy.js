// React.lazy() remembers a failed import forever, so after a chunk fails to
// load (offline, or an old tab after a deploy) the page could only be fixed by
// a full reload. lazyWithRetry() components can be re-armed: the chunk error
// boundary calls retryFailedImports(), then renders again, which re-imports.
import { createElement, lazy } from 'react';

const failedImports = new Set();

export function lazyWithRetry(factory, makeLazy = lazy) {
  let current;
  const rearm = () => { current = makeLazy(load); };
  function load() {
    return Promise.resolve().then(factory).catch((error) => {
      failedImports.add(rearm);
      throw error;
    });
  }
  rearm();
  function RetryableLazy(props) {
    return createElement(current, props);
  }
  RetryableLazy.current = () => current;
  return RetryableLazy;
}

// Re-arms every lazy component whose import failed; returns how many.
export function retryFailedImports() {
  const pending = [...failedImports];
  failedImports.clear();
  pending.forEach((rearm) => rearm());
  return pending.length;
}

// Error-boundary state: a new resetKey (the page) clears a previous failure.
export function boundaryStateFor(resetKey, state) {
  if (resetKey === state.resetKey) return null;
  return { failed: false, resetKey };
}
