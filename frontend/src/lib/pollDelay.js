// An open conversation is polled every 8 s while it is active. Each poll that
// finds nothing new waits 1.5x longer, up to 30 s; a new message, a send or
// refocusing the window goes back to 8 s.
export const MESSAGE_POLL = { min: 8000, max: 30000, factor: 1.5 };

export function nextPollDelay(delay, changed, { min, max, factor } = MESSAGE_POLL) {
  if (changed) return min;
  return Math.min(max, Math.round(delay * factor));
}
