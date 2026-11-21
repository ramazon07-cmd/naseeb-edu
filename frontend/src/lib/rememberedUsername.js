// "Remember me" keeps the username (never the password) on this browser. The key lives here so every
// way a session ends (sign-out, expiry, revoked or forced logout) can clear it, not only the sign-out button.
export const REMEMBER_KEY = 'naseeb-edu-remember-username-v1';
export const rememberedUsername = () => {
  try { return window.localStorage.getItem(REMEMBER_KEY) || ''; } catch { return ''; }
};
export const forgetRememberedUsername = () => {
  try { window.localStorage.removeItem(REMEMBER_KEY); } catch { /* A convenience only. */ }
};
export const rememberUsername = (username) => {
  try {
    if (username) window.localStorage.setItem(REMEMBER_KEY, username);
    else window.localStorage.removeItem(REMEMBER_KEY);
  } catch { /* A convenience only. */ }
};
