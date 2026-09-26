import { useCallback, useLayoutEffect, useState } from 'react';
import { themeIconFor } from '../components/brand';

export const THEME_KEY = 'naseeb-edu-theme';

export function initialTheme() {
  try {
    const saved = window.localStorage.getItem(THEME_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    // Storage can be unavailable in strict privacy modes; the OS preference still works.
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

// Applies the theme to <html>, the favicon and theme-color before paint.
export function useTheme() {
  const [theme, setTheme] = useState(initialTheme);
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    try { window.localStorage.setItem(THEME_KEY, theme); } catch { /* Keep the active theme for this session. */ }
    const favicon = document.querySelector('link[data-theme-icon]');
    if (favicon) favicon.href = themeIconFor(theme);
    const themeColor = document.getElementById('theme-color');
    if (themeColor) themeColor.content = getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim();
  }, [theme]);
  const toggleTheme = useCallback(() => setTheme((current) => current === 'dark' ? 'light' : 'dark'), []);
  return [theme, toggleTheme];
}
