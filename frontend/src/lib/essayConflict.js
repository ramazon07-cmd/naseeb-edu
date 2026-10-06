import { t } from '../i18n.js';

export const ESSAY_CHANGED_MESSAGE = 'This essay changed since you opened it. Reload to see the latest version, then make your edit again.';

// The essay form sends the updated_at it was built from; 409 means the student (or someone else) saved since.
export function essaySaveError(resource, error) {
  if (resource === 'essays' && error?.status === 409) return t(ESSAY_CHANGED_MESSAGE);
  return error?.message;
}
