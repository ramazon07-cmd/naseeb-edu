// SVG <image> does not share HTML <img>'s widely supported native lazy loading.
// Warm the six shared story emblems together before their rail enters view.
// Observing individual emblems would be clipped by the horizontal scroll area
// and could leave an emblem unloaded until its card was already visible.
export function deferSvgImages(root, Observer = globalThis.IntersectionObserver) {
  const pending = [...root.querySelectorAll('image[data-deferred-href]')]
    .filter((image) => !image.hasAttribute('href'));
  const load = () => {
    pending.forEach((image) => {
      image.setAttribute('href', image.getAttribute('data-deferred-href'));
    });
    pending.length = 0;
  };

  if (!Observer) {
    load();
    return () => {};
  }

  const observer = new Observer((entries) => {
    if (!entries.some((entry) => entry.isIntersecting)) return;
    load();
    observer.disconnect();
  }, { rootMargin: '800px 0px', threshold: 0 });

  if (pending.length) observer.observe(root);
  return () => observer.disconnect();
}
