// /me/ `assistant_enabled` is the backend's answer: the outbound-AI switch is
// on, the role may use the assistant and the school plan includes it.
export function canUseAssistant(user) {
  return Boolean(user?.assistant_enabled);
}

// Why a send failed. 'switched_off' and 'not_in_plan' mean this user cannot use
// the assistant at all (the launcher should go away); the rest are transient.
export function assistantFailureReason(error) {
  if (error?.status === 503 && error?.details?.code === 'assistant_disabled') return 'switched_off';
  if (error?.status === 403 && error?.details?.code === 'feature_not_in_plan') return 'not_in_plan';
  if (error?.status === 429) return 'limit';
  if (error?.status === 503) return 'busy';
  return 'connection';
}

export const UNAVAILABLE_REASONS = new Set(['switched_off', 'not_in_plan']);

// The drawer after a failed send: the empty reply placeholder is dropped and the
// composer is usable again ('ready' when the assistant is gone for good, so no
// retry state lingers; 'error' for a transient failure).
export function failedSend(messages, assistantId, reason) {
  return {
    messages: messages.filter((message) => message.id !== assistantId),
    status: UNAVAILABLE_REASONS.has(reason) ? 'ready' : 'error',
    unavailable: UNAVAILABLE_REASONS.has(reason),
  };
}
