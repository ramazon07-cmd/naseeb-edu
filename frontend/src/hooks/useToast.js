import { useCallback, useEffect, useRef, useState } from 'react';

// One toast at a time; a newer toast restarts the timer instead of being
// hidden early by an older one, and the timer is cleared on unmount.
export function useToast(duration = 3500) {
  const [toast, setToast] = useState(null);
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const notify = useCallback((message, type = 'success') => {
    setToast({ message, type });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), duration);
  }, [duration]);
  return [toast, notify];
}
