

// One section, printed on its own: the browser writes the PDF, so no records
// leave the device and no PDF dependency enters the build.
export function exportNodePdf(node) {
  if (!node) return;
  const root = document.documentElement;
  const previous = root.getAttribute('data-theme');
  let restored = false;
  let fallbackTimer;
  const restore = () => {
    if (restored) return;
    restored = true;
    window.clearTimeout(fallbackTimer);
    window.removeEventListener('afterprint', restore);
    document.body.classList.remove('printing-scope');
    node.classList.remove('print-target');
    if (previous) root.setAttribute('data-theme', previous);else
    root.removeAttribute('data-theme');
  };
  document.body.classList.add('printing-scope');
  node.classList.add('print-target');
  root.setAttribute('data-theme', 'light');
  window.addEventListener('afterprint', restore);
  // Keep print() inside the click event so browsers that require a user
  // gesture do not block it. Cleanup waits for the print lifecycle event.
  fallbackTimer = window.setTimeout(restore, 60_000);
  try { window.print(); } catch { restore(); }
}
