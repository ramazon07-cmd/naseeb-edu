import { useEffect, useRef, useState } from "react";

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";
const SPEED = 18; // Pixels per second, independent of the display's refresh rate.

export default function useStoryMarquee(itemCount) {
  const railRef = useRef(null);
  const regionRef = useRef(null);
  const [paused, setPaused] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [edges, setEdges] = useState({ atStart: true, atEnd: false });

  useEffect(() => {
    const rail = railRef.current;
    const region = regionRef.current;
    if (!rail || !region || itemCount < 2) return undefined;

    const media = window.matchMedia(REDUCED_MOTION);
    const cards = Array.from(rail.children);
    let frame = 0;
    let lastTime = 0;
    let position = rail.scrollLeft;
    let loopWidth = 0;
    let visible = false;
    let hovered = window.matchMedia("(hover: hover)").matches &&
      cards.some((card) => card.matches(":hover"));
    let focused = region.contains(document.activeElement) && document.activeElement.matches(":focus-visible");

    const tick = (time) => {
      if (lastTime) {
        // Clamp elapsed time so returning from a stalled/background tab cannot jump.
        position = (position + Math.min(time - lastTime, 64) * SPEED / 1000) % loopWidth;
        rail.scrollLeft = position;
      }
      lastTime = time;
      frame = window.requestAnimationFrame(tick);
    };

    const syncPlayback = () => {
      const running = !paused && !media.matches && !hovered && !focused &&
        visible && !document.hidden && loopWidth > rail.clientWidth;
      if (running && !frame) {
        position = rail.scrollLeft % loopWidth;
        lastTime = 0;
        frame = window.requestAnimationFrame(tick);
      } else if (!running && frame) {
        window.cancelAnimationFrame(frame);
        frame = 0;
        lastTime = 0;
      }
    };

    const syncEdges = () => {
      const atStart = rail.scrollLeft <= 2;
      const atEnd = rail.scrollWidth - rail.clientWidth - rail.scrollLeft <= 2;
      setEdges((current) => current.atStart === atStart && current.atEnd === atEnd
        ? current : { atStart, atEnd });
    };
    const measure = () => {
      const first = rail.children[0];
      const copy = rail.children[itemCount];
      loopWidth = !media.matches && first && copy ? copy.offsetLeft - first.offsetLeft : 0;
      position = loopWidth > 0 ? rail.scrollLeft % loopWidth : rail.scrollLeft;
      syncEdges();
      syncPlayback();
    };
    const onMotionChange = () => {
      setReducedMotion(media.matches);
      measure();
    };
    const onPointerEnter = (event) => {
      if (event.pointerType === "mouse") { hovered = true; syncPlayback(); }
    };
    const onPointerLeave = () => { hovered = false; syncPlayback(); };
    const onFocus = (event) => {
      focused = event.target.matches(":focus-visible");
      syncPlayback();
    };
    const onBlur = (event) => {
      if (!region.contains(event.relatedTarget)) { focused = false; syncPlayback(); }
    };
    // A swipe, selection or trackpad gesture pauses persistently for reading.
    const onInteraction = () => setPaused(true);
    const onWheel = (event) => {
      if (Math.abs(event.deltaX) > Math.abs(event.deltaY) || event.shiftKey) {
        setPaused(true);
      }
    };

    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      syncPlayback();
    });
    const resizeObserver = new ResizeObserver(measure);
    observer.observe(rail);
    resizeObserver.observe(rail);
    onMotionChange();
    media.addEventListener("change", onMotionChange);
    document.addEventListener("visibilitychange", syncPlayback);
    // Pause only over a story, never over the heading, controls or rail gaps.
    cards.forEach((card) => {
      card.addEventListener("pointerenter", onPointerEnter);
      card.addEventListener("pointerleave", onPointerLeave);
    });
    region.addEventListener("focusin", onFocus);
    region.addEventListener("focusout", onBlur);
    rail.addEventListener("pointerdown", onInteraction, { passive: true });
    rail.addEventListener("wheel", onWheel, { passive: true });
    rail.addEventListener("scroll", syncEdges, { passive: true });

    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      resizeObserver.disconnect();
      media.removeEventListener("change", onMotionChange);
      document.removeEventListener("visibilitychange", syncPlayback);
      cards.forEach((card) => {
        card.removeEventListener("pointerenter", onPointerEnter);
        card.removeEventListener("pointerleave", onPointerLeave);
      });
      region.removeEventListener("focusin", onFocus);
      region.removeEventListener("focusout", onBlur);
      rail.removeEventListener("pointerdown", onInteraction);
      rail.removeEventListener("wheel", onWheel);
      rail.removeEventListener("scroll", syncEdges);
    };
  }, [itemCount, paused]);

  const scrollByCard = (direction) => {
    const rail = railRef.current;
    if (!rail) return;
    setPaused(true);
    const [first, second] = rail.children;
    const step = second ? second.offsetLeft - first.offsetLeft : rail.clientWidth;
    const reduced = window.matchMedia(REDUCED_MOTION).matches;
    const copy = rail.children[itemCount];
    const loopWidth = copy ? copy.offsetLeft - first.offsetLeft : 0;
    const looping = !reduced && loopWidth > rail.clientWidth;
    if (looping && rail.scrollLeft >= loopWidth) rail.scrollLeft %= loopWidth;
    // Land on a whole card even if the belt was stopped between two cards.
    const index = rail.scrollLeft / step;
    const nextIndex = direction > 0 ? Math.floor(index + 0.001) + 1 : Math.ceil(index - 0.001) - 1;
    let target = nextIndex * step;
    if (looping && target < 0) {
      rail.scrollLeft += loopWidth;
      target += loopWidth;
    }
    rail.scrollTo({ left: target, behavior: reduced ? "instant" : "smooth" });
  };

  return { railRef, regionRef, reducedMotion, edges, scrollByCard };
}
