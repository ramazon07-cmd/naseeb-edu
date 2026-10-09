import { useEffect, useRef, useState } from 'react';
import { Download } from 'lucide-react';
import '@fontsource-variable/newsreader';
import { api } from '../api';
import { t, tx } from '../i18n';
import { CARD_HEIGHT, CARD_WIDTH, drawProfileCard } from '../lib/profileCard';
import './profile-card.css';

// The shields --brand-logo-image uses in styles.css: gold on light, midnight on dark.
const LOGOS = { light: '/brand/naseeb-gold-shield.png', dark: '/brand/naseeb-midnight-shield.png' };

// Canvas and PNG use the active theme's palette (profile-card.css).
function readPalette(element) {
  const style = getComputedStyle(element);
  const token = (name) => style.getPropertyValue(name).trim();
  return {
    paper: token('--id-card-paper'), ink: token('--id-card-ink'), label: token('--id-card-label'),
    primary: token('--id-card-primary'), secondary: token('--id-card-secondary'), accent: token('--id-card-accent'), border: token('--id-card-border'),
  };
}

// The private photo as a bitmap: drawn from a fetched blob, it never taints the canvas.
function useStudentPhoto(student) {
  const [photo, setPhoto] = useState(null);
  const id = student?.has_photo ? student.id : null;
  const version = student?.photo_version;
  useEffect(() => {
    let active = true;
    let ownedBitmap;
    if (!id) return undefined;
    api.studentPhoto(id, version)
      .then((result) => createImageBitmap(result.blob))
      .then((bitmap) => {
        if (!active) { bitmap.close(); return; }
        ownedBitmap = bitmap;
        setPhoto({ id, version, bitmap });
      })
      .catch(() => { if (active) setPhoto(null); });
    return () => { active = false; ownedBitmap?.close(); };
  }, [id, version]);
  return photo?.id === id && photo?.version === version ? photo.bitmap : null;
}

function loadLogo(theme) {
  const image = new Image();
  image.src = LOGOS[theme] || LOGOS.light;
  return image.decode().then(() => image);
}

// `card`: profileCardData() for this student, or null until Interests is done.
// `student`: the own student record, for the photo. `children`: the detailed scores.
export function ProfileResultCard({ card, student, children }) {
  const canvasRef = useRef(null);
  const [rendered, setRendered] = useState(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  // CSS hot updates change tokens but cannot repaint existing canvas pixels.
  useEffect(() => {
    if (!import.meta.hot) return undefined;
    const redraw = () => setAttempt((value) => value + 1);
    import.meta.hot.on('vite:afterUpdate', redraw);
    return () => import.meta.hot.off('vite:afterUpdate', redraw);
  }, []);
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'light');
  useEffect(() => {
    const root = document.documentElement;
    const syncTheme = () => setTheme(root.dataset.theme || 'light');
    const observer = new MutationObserver(syncTheme);
    observer.observe(root, { attributes: true, attributeFilter: ['data-theme'] });
    syncTheme();
    return () => observer.disconnect();
  }, []);
  const photo = useStudentPhoto(student);
  const labels = {
    cardTitle: t('Personal profile card'),
    surname: t('Surname'), givenName: t('Given name'),
    code: t('Interest code'), subjects: t('Strongest Subjects'),
    personality: t('Personality'), majors: t('Recommended majors'),
    issued: t('Date of issue'), signature: t('Signature'),
    notTaken: t('Not taken yet'), majorsLocked: t('Unlocks once all four challenges are saved.'),
    disclaimer: t('An education-interest snapshot, not a diagnosis.'),
  };
  // The page re-scores on every render; redraw only when what the card shows changes.
  const drawing = JSON.stringify({ card, labels, theme });
  const ready = rendered?.drawing === drawing && rendered?.photo === photo && rendered?.attempt === attempt;

  useEffect(() => {
    let active = true;
    const canvas = canvasRef.current;
    const { card: shown, labels: copy, theme: shownTheme } = JSON.parse(drawing);
    if (!canvas || !shown) return undefined;
    // A canvas draws only with fonts that have finished loading.
    // Include translated labels, not only a Latin student name: Cyrillic lives
    // in a separate font subset and must be loaded before exporting Russian.
    const fontText = JSON.stringify({ shown, copy });
    const fonts = document.fonts ? ['400 62px "Newsreader Variable"'].map((font) => document.fonts.load(font, fontText)) : [];
    Promise.allSettled([loadLogo(shownTheme), ...fonts]).then(([logo]) => {
      if (!active) return;
      drawProfileCard(canvas, shown, readPalette(canvas), copy, { photo, logo: logo.status === 'fulfilled' ? logo.value : null });
      setRendered({ drawing, photo, attempt });
      setError('');
    }).catch(() => { if (active) setError(t('Could not prepare your card. Please try again.')); });
    return () => { active = false; };
  }, [drawing, photo, attempt]);

  if (!card) return null;

  function download() {
    if (!ready) return;
    setError('');
    try { canvasRef.current?.toBlob((blob) => {
      if (!blob) { setError(t('Could not download your card. Please try again.')); return; }
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'naseeb-edu-profile-card.png';
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, 'image/png');
    } catch { setError(t('Could not download your card. Please try again.')); }
  }

  const code = card.code.map((item) => item.letter).join('');
  return <section className="profile-card-panel" aria-labelledby="profile-card-title">
    <div className="profile-card-frame" aria-busy={!ready}>
      <canvas ref={canvasRef} width={CARD_WIDTH} height={CARD_HEIGHT} role="img" aria-label={tx`Profile card for ${card.name}: interest code ${code}, ${card.code.map((item) => item.name).join(', ')}.`} />
    </div>
    <header className="profile-card-copy">
      <span className="eyebrow">{t('YOUR PROFILE CARD')}</span>
      <h2 id="profile-card-title">{t('Your results on one card')}</h2>
      <p>{t('Save it as an image to share with your family or keep for later. Your IQ & Reasoning result stays off the card.')}</p>
      <button type="button" className="button primary" onClick={download} disabled={!ready} aria-busy={!ready}><Download size={16} aria-hidden="true" /> {t('Download card')}</button>
      {error && <div className="profile-card-error" role="alert"><p>{error}</p>{!ready && <button type="button" className="button quiet" onClick={() => { setError(''); setAttempt((value) => value + 1); }}>{t('Retry')}</button>}</div>}
    </header>
    {children && <div className="profile-card-details">{children}</div>}
  </section>;
}
