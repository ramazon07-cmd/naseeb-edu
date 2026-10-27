import { useLayoutEffect } from 'react';

// Naseeb Edu ships a single light theme. data-theme stays on <html> so the
// token blocks keyed on :root keep resolving, and the saved value from the old
// toggle is ignored.
export function useTheme() {
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = 'light';
    document.documentElement.style.colorScheme = 'light';
    const themeColor = document.getElementById('theme-color');
    if (themeColor) themeColor.content = getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim();
  }, []);
  return 'light';
}
