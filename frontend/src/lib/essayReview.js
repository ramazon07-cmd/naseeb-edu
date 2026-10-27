// The counselor's read of a shared Essay Lab essay: where each piece of text sits,
// in the units the server uses (backend/apps/admissions/essay_lab/collab.py).
// Offsets count UTF-16 code units (a JS string's length), a hard line break is
// one unit, and the text blocks inside one top-level block (list items, quotes)
// follow one another with one separator unit between them.

const TEXT_BLOCKS = new Set(['paragraph', 'heading', 'title', 'subtitle']);

export const isTextBlock = (node) => TEXT_BLOCKS.has(node?.type);
export const blockId = (block) => block?.attrs?.bid || '';

const nodeLength = (child) => (child.type === 'text' ? String(child.text || '').length : 1);
export const leafLength = (leaf) => (leaf.content || []).reduce((sum, child) => sum + nodeLength(child), 0);

// The text blocks of one top-level block in reading order, each with its start and end offset.
export function leafSpans(block) {
  const leaves = [];
  const walk = (node) => {
    if (isTextBlock(node)) { leaves.push(node); return; }
    for (const child of node.content || []) walk(child);
  };
  walk(block);
  let position = 0;
  return leaves.map((leaf, index) => {
    if (index) position += 1;
    const start = position;
    position += leafLength(leaf);
    return { leaf, start, end: position };
  });
}

export const blockLength = (block) => leafSpans(block).at(-1)?.end ?? 0;

// The words between two offsets of a block, as the reader sees them (line breaks and separators as a space).
export function textBetween(block, from, to) {
  let out = '';
  for (const { leaf, start } of leafSpans(block)) {
    let position = start;
    for (const child of leaf.content || []) {
      const length = nodeLength(child);
      if (position + length > from && position < to) {
        if (child.type === 'text') out += child.text.slice(Math.max(from - position, 0), Math.max(to - position, 0));
        else out += ' ';
      }
      position += length;
    }
    if (position >= to) break;
    if (position > from && out && !out.endsWith(' ')) out += ' ';
  }
  return out.trim();
}

// What the owner allowed this reader: 'edit' | 'suggest' | 'comment' | 'view'.
export function accessLevel(capabilities = []) {
  if (capabilities.includes('suggest')) return 'suggest';
  if (capabilities.includes('comment')) return 'comment';
  return 'view';
}

const byTime = (a, b) => String(a.created_at).localeCompare(String(b.created_at));

// All comment threads, oldest first; historic resolution never hides a comment.
export function orderedThreads(threads = []) {
  return [...threads].sort(byTime);
}

// Only web and mail links are followed (the same rule as the editor's link mark).
export const safeHref = (href) => (/^(https?:\/\/|mailto:)[^\s<>"]+$/i.test(String(href || '')) ? href : '');

export const ESSAY_STATUS_TONE = { draft: 'quiet', reviewing: 'warn', needs_revision: 'late', approved: 'ok' };
