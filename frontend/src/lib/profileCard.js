// Editorial assessment card. The preview and PNG share the same renderer.
// Reasoning scores remain private and are never included in the shared card.
import { RIASEC_NAME, RIASEC_ORDER, SUBJECT_NAME, TRAIT_LABEL, TRAIT_ORDER } from '../challenges.js';
import { formatNumberLocale, t } from '../i18n.js';

// ID-1 card proportions (85.6 × 54 mm).
export const CARD_WIDTH = 1600;
export const CARD_HEIGHT = 1010;

const SANS = "'Helvetica Neue', system-ui, sans-serif";
const SERIF = "'Newsreader Variable', Georgia, serif";
const PAD = 64;
const RIGHT = CARD_WIDTH - PAD;

const score = (value) => formatNumberLocale(value, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
// Printed the way ID cards print dates (DD.MM.YYYY), whatever the language.
const issueDate = (date) => [date.getDate(), date.getMonth() + 1].map((part) => String(part).padStart(2, '0')).concat(date.getFullYear()).join('.');

// `results`: [challenge, result | null] pairs as the page scores them.
// `majors`: the shortlist the page ranks, or null while recommendations are locked.
export function profileCardData({ results, majors, firstName = '', lastName = '', date = new Date() }) {
  const scored = Object.fromEntries(results.filter(([, result]) => result).map(([challenge, result]) => [challenge.scoring, result]));
  if (!scored.riasec) return null;
  const { means, code } = scored.riasec;
  return {
    name: [firstName, lastName].filter(Boolean).join(' '),
    firstName,
    lastName,
    date: issueDate(date),
    code: code.map((letter) => ({ letter, name: t(RIASEC_NAME[letter]) })),
    interests: RIASEC_ORDER.map((letter) => ({ letter, value: means[letter], top: code.includes(letter) })),
    traits: scored.bigfive ? TRAIT_ORDER.map((trait) => ({ label: t(TRAIT_LABEL[trait]), value: scored.bigfive[trait], text: score(scored.bigfive[trait]) })) : null,
    subjects: scored.subjects ? scored.subjects.ranked.slice(0, 3).map((subject) => t(SUBJECT_NAME[subject])) : null,
    majors: majors ? majors.slice(0, 3).map((major) => t(major)) : null,
  };
}

// Lines of `text` that fit `maxWidth` as the context measures them; a line
// that still does not fit (one long word, or text past `maxLines`) ends in "…".
export function wrapLines(ctx, text, maxWidth, maxLines = Infinity) {
  const lines = [];
  for (const word of String(text || '').split(/\s+/).filter(Boolean)) {
    const next = lines.length ? `${lines.at(-1)} ${word}` : word;
    if (lines.length && ctx.measureText(next).width <= maxWidth) lines[lines.length - 1] = next;
    else lines.push(word);
  }
  const kept = lines.slice(0, maxLines);
  return kept.map((line, index) => {
    const cut = index === kept.length - 1 && lines.length > kept.length;
    if (!cut && ctx.measureText(line).width <= maxWidth) return line;
    let shorter = line;
    while (shorter && ctx.measureText(`${shorter}…`).width > maxWidth) shorter = shorter.slice(0, -1);
    return `${shorter.trimEnd()}…`;
  });
}

function setFont(ctx, weight, size, family, spacing = '0px') {
  ctx.font = `${weight} ${size}px ${family}`;
  // Older browsers without canvas letter-spacing just draw it tighter.
  if ('letterSpacing' in ctx) ctx.letterSpacing = spacing;
}

function roundedRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.roundRect(x, y, width, height, radius);
}

// One line at the largest of `sizes` that fits `maxWidth`, else the smallest with "…".
function fitText(ctx, text, x, y, maxWidth, weight, sizes, family, spacing = '0px') {
  for (const size of sizes) {
    setFont(ctx, weight, size, family, spacing);
    if (ctx.measureText(text).width <= maxWidth) {
      ctx.fillText(text, x, y);
      return;
    }
  }
  ctx.fillText(wrapLines(ctx, text, maxWidth, 1)[0] || '', x, y);
}

function divider(ctx, x, y, width, palette) {
  ctx.save();
  ctx.strokeStyle = palette.border;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + width, y);
  ctx.stroke();
  ctx.restore();
}

// The student's interest hexagon with its six letters, inside the seal.
function interestShape(ctx, interests, cx, cy, radius, palette) {
  const point = (index, scale) => {
    const angle = (Math.PI * 2 * index) / interests.length - Math.PI / 2;
    return [cx + Math.cos(angle) * radius * scale, cy + Math.sin(angle) * radius * scale];
  };
  const path = (scale) => {
    ctx.beginPath();
    interests.forEach((item, index) => ctx.lineTo(...point(index, typeof scale === 'function' ? scale(item) : scale)));
    ctx.closePath();
  };
  ctx.save();
  ctx.strokeStyle = palette.ink;
  ctx.lineWidth = 1.5;
  ctx.globalAlpha = 0.22;
  for (const ring of [0.5, 1]) { path(ring); ctx.stroke(); }
  // 1..5 onto 0..1, as the page's polygon does, so the centre means "lowest".
  path((item) => Math.max(0, Math.min(1, (item.value - 1) / 4)));
  ctx.globalAlpha = 0.32;
  ctx.fillStyle = palette.accent;
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.strokeStyle = palette.primary;
  ctx.lineWidth = 3;
  ctx.lineJoin = 'round';
  ctx.stroke();
  setFont(ctx, 800, 18, SANS);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  interests.forEach((item, index) => {
    ctx.fillStyle = item.top ? palette.primary : palette.label;
    ctx.fillText(item.letter, ...point(index, 1.3));
  });
  ctx.restore();
}

function header(ctx, card, palette, labels, logo) {
  if (logo) {
    // Contain the shield in its 58×54 slot: the light and dark shields have different shapes.
    const scale = Math.min(58 / logo.width, 54 / logo.height);
    const [width, height] = [logo.width * scale, logo.height * scale];
    ctx.drawImage(logo, PAD + (58 - width) / 2, 52 + (54 - height) / 2, width, height);
  }
  ctx.fillStyle = palette.label;
  fitText(ctx, 'NASEEB EDU', PAD + 78, 88, 760, 600, [26], SANS, '3px');
  ctx.fillStyle = palette.primary;
  fitText(ctx, labels.cardTitle, PAD, 174, 1130, 400, [62, 54, 46], SERIF);
  interestShape(ctx, card.interests, 1434, 116, 58, palette);
  divider(ctx, PAD, 208, RIGHT - PAD, palette);
}

function initialsOf(card) {
  return [card.firstName, card.lastName].filter(Boolean).map((part) => part.trim()[0]).join('').toLocaleUpperCase() || 'N';
}

function portrait(ctx, card, palette, labels, photo) {
  const [x, y, width, height] = [PAD, 236, 330, 420];
  ctx.save();
  roundedRect(ctx, x, y, width, height, 12);
  ctx.clip();
  if (photo) {
    // Cover the frame and keep the face: centred across, top-weighted down.
    const scale = Math.max(width / photo.width, height / photo.height);
    const [drawWidth, drawHeight] = [photo.width * scale, photo.height * scale];
    ctx.drawImage(photo, x + (width - drawWidth) / 2, y + (height - drawHeight) / 3, drawWidth, drawHeight);
  } else {
    ctx.globalAlpha = 0.14;
    ctx.fillStyle = palette.secondary;
    ctx.fillRect(x, y, width, height);
    ctx.globalAlpha = 1;
    ctx.fillStyle = palette.primary;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    setFont(ctx, 400, 132, SERIF);
    ctx.fillText(initialsOf(card), x + width / 2, y + height / 2);
  }
  ctx.restore();
  ctx.save();
  roundedRect(ctx, x, y, width, height, 12);
  ctx.globalAlpha = 0.18;
  ctx.strokeStyle = palette.ink;
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.restore();

  ctx.fillStyle = palette.label;
  fitText(ctx, labels.signature, x, 704, width, 500, [21, 18], SANS);
  ctx.fillStyle = palette.ink;
  fitText(ctx, card.name, x, 757, width, 'italic 400', [40, 34, 28], SERIF);

}

// A small localized label over the value in capitals.
function field(ctx, label, value, x, y, width, palette, { sizes = [40, 34, 28], color = palette.ink } = {}) {
  ctx.fillStyle = palette.label;
  fitText(ctx, label, x, y, width, 500, [21, 18], SANS);
  ctx.fillStyle = color;
  fitText(ctx, String(value || '—'), x, y + 44, width, 500, sizes, SANS);
}

// Up to `maxLines` lines of text; returns the baseline below the last one.
function textLines(ctx, text, x, y, width, size, maxLines, palette) {
  setFont(ctx, 500, size, SANS);
  ctx.fillStyle = palette.ink;
  const lines = wrapLines(ctx, text, width, maxLines);
  lines.forEach((line, index) => ctx.fillText(line, x, y + index * (size + 8)));
  return y + lines.length * (size + 8);
}

function note(ctx, text, x, y, width, palette) {
  setFont(ctx, 500, 22, SANS);
  ctx.fillStyle = palette.label;
  wrapLines(ctx, text, width, 2).forEach((line, index) => ctx.fillText(line, x, y + index * 30));
}

// Fixed layout on the 1600×1010 card; `labels` is its copy in the reader's
// language, `art` the decoded photo and logo (either may be missing).
export function drawProfileCard(canvas, card, palette, labels, art = {}) {
  canvas.width = CARD_WIDTH;
  canvas.height = CARD_HEIGHT;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, CARD_WIDTH, CARD_HEIGHT);
  ctx.save();
  roundedRect(ctx, 0, 0, CARD_WIDTH, CARD_HEIGHT, 24);
  ctx.clip();
  ctx.fillStyle = palette.paper;
  ctx.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);
  header(ctx, card, palette, labels, art.logo);
  portrait(ctx, card, palette, labels, art.photo);

  // Middle column: who, the code, subjects and the date.
  const middle = 440;
  const middleWidth = 500;
  field(ctx, labels.surname, card.lastName, middle, 266, middleWidth, palette);
  field(ctx, labels.givenName, card.firstName, middle, 356, middleWidth, palette);
  ctx.fillStyle = palette.label;
  fitText(ctx, labels.code, middle, 446, middleWidth, 500, [21, 18], SANS);
  ctx.fillStyle = palette.primary;
  setFont(ctx, 500, 52, SANS, '4px');
  ctx.fillText(card.code.map((item) => item.letter).join(''), middle, 502);
  setFont(ctx, 400, 24, SANS);
  ctx.fillStyle = palette.ink;
  wrapLines(ctx, card.code.map((item) => item.name).join(' · '), middleWidth, 2).forEach((line, index) => ctx.fillText(line, middle, 538 + index * 28));
  ctx.fillStyle = palette.label;
  fitText(ctx, labels.subjects, middle, 616, middleWidth, 500, [21, 18], SANS);
  if (card.subjects) textLines(ctx, card.subjects.join(' · '), middle, 658, middleWidth, 30, 2, palette);
  else note(ctx, labels.notTaken, middle, 654, middleWidth, palette);
  field(ctx, labels.issued, card.date, middle, 750, middleWidth, palette, { sizes: [36] });

  // Right column: personality bars, then the majors.
  const right = 1010;
  const rightWidth = RIGHT - right;
  ctx.fillStyle = palette.label;
  fitText(ctx, labels.personality, right, 266, rightWidth, 500, [21, 18], SANS);
  if (card.traits) {
    card.traits.forEach((trait, index) => {
      const row = 306 + index * 50;
      ctx.fillStyle = palette.ink;
      fitText(ctx, trait.label, right, row, rightWidth - 70, 500, [24, 21], SANS);
      setFont(ctx, 500, 22, SANS);
      ctx.textAlign = 'right';
      ctx.fillText(trait.text, RIGHT, row);
      ctx.textAlign = 'left';
      roundedRect(ctx, right, row + 10, rightWidth, 8, 4);
      ctx.save();
      ctx.globalAlpha = 0.1;
      ctx.fillStyle = palette.ink;
      ctx.fill();
      ctx.restore();
      roundedRect(ctx, right, row + 10, Math.max(8, rightWidth * Math.max(0, Math.min(1, (trait.value - 1) / 4))), 8, 4);
      ctx.fillStyle = palette.secondary;
      ctx.fill();
    });
  } else {
    note(ctx, labels.notTaken, right, 304, rightWidth, palette);
  }
  ctx.fillStyle = palette.label;
  fitText(ctx, labels.majors, right, 576, rightWidth, 500, [21, 18], SANS);
  if (card.majors) {
    card.majors.forEach((major, index) => {
      ctx.fillStyle = palette.ink;
      fitText(ctx, major, right, 628 + index * 52, rightWidth, 400, [38, 32, 26], SERIF);
    });
  } else {
    note(ctx, labels.majorsLocked, right, 616, rightWidth, palette);
  }

  divider(ctx, PAD, 878, RIGHT - PAD, palette);
  ctx.fillStyle = palette.label;
  fitText(ctx, labels.disclaimer, PAD, 932, RIGHT - PAD, 400, [23, 20], SANS);
  ctx.restore();
}
