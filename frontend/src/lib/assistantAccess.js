// /me/ `assistant_enabled` already combines the platform switch, the role and the
// school plan; the role check here also covers a stale cached user.
const ASSISTANT_ROLES = ['counselor', 'student'];

export function canUseAssistant(user) {
  return Boolean(user?.assistant_enabled) && ASSISTANT_ROLES.includes(user.role);
}

// A 503 with this code means the assistant was switched off, not that it is busy.
export function isAssistantSwitchedOff(error) {
  return error?.status === 503 && error?.details?.code === 'assistant_disabled';
}
