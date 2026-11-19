import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check } from 'lucide-react';
import { t } from '../../i18n';
import { markSiteTourSeen } from './tourSeen';
import './tour.css';

const PHONE = 560; // tips dock to the top or bottom edge at or below this width
const DRAWER = 820; // the sidebar is a drawer at or below this width

// Steps in the design's order. `target` is a selector over the real UI (null = centred card);
// `side` steps live in the sidebar, which is a drawer on phones. A step whose target is
// missing (page not offered to this account, widget hidden) is left out.
function tourSteps() {
  return [
    { id: 'welcome', hero: 1, title: t('Welcome to Naseeb Edu'), text: t('A one-minute tour of the places you will use most. You can skip it at any time and replay it from your account menu.') },
    { id: 'kpis', target: '.nb-dash-kpis', page: 'dashboard', title: t('Welcome! Your progress at a glance'), text: t('Open tasks, universities on your list and how far you are on your roadmap. Tap a card to open it.') },
    { id: 'mind', target: '[data-tour="nav-find_personality"]', side: true, title: t('Naseeb Mind'), text: t('Take 7 short free tests to discover the majors that fit you. Not sure what to study? Start here.') },
    { id: 'programs', target: '[data-tour="nav-programs"]', side: true, title: t('Programs'), text: t('150+ competitions, summer schools and scholarships for your grade. Save the ones you like to My List.') },
    { id: 'applications', target: '[data-tour="nav-applications"]', side: true, title: t('Applications'), text: t('Track every university on your list, its stage and deadlines.') },
    { id: 'reading', target: '.nb-reading-toggle', title: t('Reading mode'), text: t('One button: calmer background, larger text and softer colors. Tap it again to go back to normal.') },
    { id: 'account', target: '.nb-account-trigger', side: true, title: t('Your profile menu'), text: t('Support, sign out — and this tour, any time you need it.') },
    { id: 'finish', hero: 2, title: t('You are all set'), text: t('That is everything you need to get going. Replay this tour any time from your account menu.') },
  ];
}

const visible = (element) => {
  if (!element) return null;
  const box = element.getBoundingClientRect();
  return box.width || box.height ? element : null;
};

const reducedMotion = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
const focusables = (root) => [...root.querySelectorAll('button:not([disabled])')];

// The guided tour. Mounted by the student shell only, so it can never sit on top of the
// forced password change or the onboarding (those render instead of the shell). It makes
// no requests: it only reads the DOM and local storage.
export function SiteTour({ userId, active, onClose, setPage, openDrawer }) {
  const [index, setIndex] = useState(0);
  const [steps, setSteps] = useState([]);
  const [box, setBox] = useState(null);
  const tipRef = useRef(null);
  const targetRef = useRef(null);
  const returnFocus = useRef(null);
  const closing = useRef(false);

  const finish = useCallback(() => {
    if (closing.current) return;
    closing.current = true;
    markSiteTourSeen(userId);
    openDrawer(false);
    onClose();
    const back = returnFocus.current;
    if (back?.isConnected) requestAnimationFrame(() => back.focus({ preventScroll: true }));
  }, [userId, onClose, openDrawer]);

  // Opening: remember what had focus, go to the dashboard (the first stop), then collect the
  // steps whose targets exist.
  useEffect(() => {
    if (!active) return undefined;
    closing.current = false;
    returnFocus.current = document.activeElement;
    setPage('dashboard');
    setIndex(0);
    let tries = 0;
    let timer = 0;
    const collect = () => {
      const phone = window.innerWidth <= DRAWER;
      const list = tourSteps().filter((step) => {
        if (!step.target) return true;
        if (step.side && phone) return true; // the drawer is closed until the step opens it
        return Boolean(visible(document.querySelector(step.target)));
      });
      // The dashboard may still be loading; give its cards a moment before settling.
      if (!list.some((step) => step.id === 'kpis') && tries++ < 12) { timer = window.setTimeout(collect, 250); return; }
      setSteps(list);
    };
    timer = window.setTimeout(collect, 150);
    return () => { window.clearTimeout(timer); setSteps([]); };
  }, [active, setPage]);

  const step = steps[index];

  const place = useCallback(() => {
    const target = targetRef.current;
    if (!target || !target.isConnected) { setBox(null); return; }
    const rect = target.getBoundingClientRect();
    setBox({ left: rect.left, top: rect.top, width: rect.width, height: rect.height });
  }, []);

  // Show a step: open or close the drawer, find and scroll to the target, measure it.
  useLayoutEffect(() => {
    if (!active || !step) return undefined;
    const phone = window.innerWidth <= DRAWER;
    if (phone) openDrawer(Boolean(step.side));
    targetRef.current = null;
    setBox(null);
    let timers = [];
    if (step.target) {
      const find = () => {
        const element = visible(document.querySelector(step.target));
        if (!element) return;
        targetRef.current = element;
        if (!step.side || !phone) element.scrollIntoView({ block: 'center', behavior: reducedMotion() ? 'auto' : 'smooth' });
        place();
      };
      find();
      timers = [setTimeout(find, 60), setTimeout(find, reducedMotion() ? 0 : 420)];
    }
    return () => timers.forEach(clearTimeout);
  }, [active, step, openDrawer, place]);

  useEffect(() => {
    if (!active || !step) return undefined;
    const on = () => requestAnimationFrame(place);
    window.addEventListener('resize', on);
    window.addEventListener('scroll', on, { passive: true });
    document.addEventListener('scroll', on, { capture: true, passive: true });
    return () => {
      window.removeEventListener('resize', on);
      window.removeEventListener('scroll', on);
      document.removeEventListener('scroll', on, { capture: true });
    };
  }, [active, step, place]);

  const go = useCallback((next) => {
    if (next >= steps.length) { finish(); return; }
    setIndex(Math.max(0, next));
  }, [steps.length, finish]);

  // Keyboard: Esc skips, arrows move, Tab stays inside the card.
  useEffect(() => {
    if (!active || !step) return undefined;
    const keys = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); finish(); return; }
      if (event.key === 'ArrowRight') { event.preventDefault(); go(index + 1); return; }
      if (event.key === 'ArrowLeft') { event.preventDefault(); go(index - 1); return; }
      if (event.key !== 'Tab' || !tipRef.current) return;
      const items = focusables(tipRef.current);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (!tipRef.current.contains(document.activeElement)) { event.preventDefault(); first.focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', keys, true);
    return () => window.removeEventListener('keydown', keys, true);
  }, [active, step, index, go, finish]);

  // Focus the primary button on every step.
  useEffect(() => {
    if (!active || !step) return;
    tipRef.current?.querySelector('[data-tour-next]')?.focus({ preventScroll: true });
  }, [active, step]);

  if (!active || !step) return null;

  const phone = window.innerWidth <= PHONE;
  const real = steps.filter((item) => item.target);
  const number = steps.slice(0, index + 1).filter((item) => item.target).length;
  const last = index === steps.length - 1;
  const centred = !box;
  const pad = 8;
  const spot = box ? { left: box.left - pad, top: box.top - pad, width: box.width + pad * 2, height: box.height + pad * 2 } : null;
  let tipStyle;
  let tipClass = 'ng-tip';
  if (centred) tipClass += ' ng-center';
  else if (phone) tipClass += ` ng-dock${box.top + box.height / 2 > window.innerHeight / 2 ? ' ng-dtop' : ''}`;
  else {
    const width = Math.min(360, window.innerWidth - 32);
    const height = tipRef.current?.offsetHeight || 190;
    const gap = pad + 14;
    let left;
    let top;
    if (box.left + box.width + gap + width <= window.innerWidth - 16 && box.width < window.innerWidth * 0.4) { left = box.left + box.width + gap; top = box.top + box.height / 2 - height / 2; }
    else { left = box.left; top = box.top + box.height + gap + height < window.innerHeight ? box.top + box.height + gap : box.top - gap - height; }
    tipStyle = { width, left: Math.max(16, Math.min(window.innerWidth - width - 16, left)), top: Math.max(16, Math.min(window.innerHeight - height - 16, top)) };
  }
  const nextLabel = step.hero === 1 ? t('Start the tour') : last ? t('Got it') : t('Next');
  const titleId = 'nb-tour-title';
  const textId = 'nb-tour-text';

  return createPortal(<div className={`ng-ov${centred ? ' dim' : ''}`}>
    <div className="ng-spot" style={spot || { opacity: 0 }} aria-hidden="true" />
    <div ref={tipRef} className={tipClass} style={tipStyle} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={textId} aria-live="polite">
      {step.hero && <span className={`ng-hero${step.hero === 2 ? ' ok' : ''}`} aria-hidden="true">{step.hero === 2 ? <Check size={30} /> : <span className="logo-mark" />}</span>}
      {!step.hero && <span className="ng-cnt">{t('{current} of {total}', { current: number, total: real.length })}</span>}
      <h3 id={titleId}>{step.title}</h3>
      <p id={textId}>{step.text}</p>
      {!step.hero && <div className="ng-dots" aria-hidden="true">{real.map((item) => <i key={item.id} className={item.id === step.id ? 'on' : ''} />)}</div>}
      <div className="ng-btns">
        {!last && <button type="button" className="ng-skip" onClick={finish}>{step.hero === 1 ? t('Maybe later') : t('Skip')}</button>}
        {index > 0 && !step.hero && <button type="button" className="ng-btn" onClick={() => go(index - 1)}>{t('Back')}</button>}
        <button type="button" className="ng-btn is-primary" data-tour-next onClick={() => go(index + 1)}>{nextLabel}</button>
      </div>
    </div>
  </div>, document.querySelector('.nb-blue') || document.body);
}
