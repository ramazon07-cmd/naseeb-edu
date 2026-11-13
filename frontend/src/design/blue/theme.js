import { useCallback, useSyncExternalStore } from 'react';

// Appearance of the blue (student) design: one of three looks plus the
// Reading mode switch. A per-browser convenience, so it lives in localStorage
// (never per account) and works without it.
export const BLUE_THEME_KEY = 'naseeb-edu-blue-theme-v1';
export const BLUE_MODES = ['light', 'tinted', 'night'];

const DEFAULT = { mode: 'light', reading: false };
const listeners = new Set();
let state = read();

function read() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(BLUE_THEME_KEY) || 'null');
    if (saved && BLUE_MODES.includes(saved.mode)) return { mode: saved.mode, reading: saved.reading === true };
  } catch { /* storage unavailable or corrupt: use the default */ }
  return DEFAULT;
}

function write(next) {
  state = next;
  try { window.localStorage.setItem(BLUE_THEME_KEY, JSON.stringify(next)); } catch { /* not persisted */ }
  listeners.forEach((listener) => listener());
}

const subscribe = (listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
const snapshot = () => state;

export const isDarkMode = (mode) => mode !== 'light';

// { mode, reading, setMode, setReading, toggleDark }
export function useBlueTheme() {
  const current = useSyncExternalStore(subscribe, snapshot, () => DEFAULT);
  const setMode = useCallback((mode) => { if (BLUE_MODES.includes(mode)) write({ ...state, mode }); }, []);
  const setReading = useCallback((reading) => write({ ...state, reading: Boolean(reading) }), []);
  // The sign-in page's single moon button: light <-> the dark look last used.
  const toggleDark = useCallback(() => write({ ...state, mode: state.mode === 'light' ? 'tinted' : 'light' }), []);
  return { ...current, setMode, setReading, toggleDark };
}
