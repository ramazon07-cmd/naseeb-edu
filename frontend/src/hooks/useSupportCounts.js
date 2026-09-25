import { useEffect, useState } from 'react';
import { api } from '../api';

const ZERO = Object.freeze({ total: 0, open: 0, inProgress: 0, resolved: 0 });

// Header figures for the admin support queue: four one-row count requests
// instead of loading every ticket. `refreshKey` changes after saves.
export function useSupportCounts(enabled, refreshKey) {
  const [counts, setCounts] = useState(ZERO);
  useEffect(() => {
    if (!enabled) return undefined;
    let current = true;
    Promise.all([
      api.count('support-tickets'),
      api.count('support-tickets', '?status=open'),
      api.count('support-tickets', '?status=in_progress'),
      api.count('support-tickets', '?status=resolved'),
    ]).then(([total, open, inProgress, resolved]) => {
      if (current) setCounts({ total, open, inProgress, resolved });
    }).catch(() => {/* the queue itself shows load errors */});
    return () => {current = false;};
  }, [enabled, refreshKey]);
  return enabled ? counts : ZERO;
}
