// A small, safe markdown subset for assistant replies. It only builds a plain node tree
// (text, strong, em, code, link, lists, code blocks); the React layer turns nodes into
// elements, so model text is never inserted as HTML.

const SAFE_PROTOCOLS = new Set(['http:', 'https:', 'mailto:']);
const WORD = /[\p{L}\p{N}]/u;

export function safeHref(value) {
  const href = String(value || '').trim();
  if (!href || /[\s<>"'`]/.test(href)) return null;
  try {
    const url = new URL(href);
    return SAFE_PROTOCOLS.has(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function push(nodes, node) {
  const last = nodes[nodes.length - 1];
  if (node.type === 'text' && last && last.type === 'text') last.text += node.text;
  else nodes.push(node);
}

export function parseInline(source) {
  const text = String(source ?? '');
  const nodes = [];
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (ch === '`') {
      const end = text.indexOf('`', i + 1);
      if (end > i + 1) {
        push(nodes, { type: 'code', text: text.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    } else if (ch === '[') {
      const match = /^\[([^\]\n]+)\]\(([^)\s]+)\)/.exec(text.slice(i));
      if (match) {
        const href = safeHref(match[2]);
        if (href) push(nodes, { type: 'link', href, children: parseInline(match[1]) });
        else parseInline(match[1]).forEach((node) => push(nodes, node));
        i += match[0].length;
        continue;
      }
    } else if (ch === '*' && text[i + 1] === '*') {
      const end = text.indexOf('**', i + 2);
      if (end > i + 2) {
        push(nodes, { type: 'strong', children: parseInline(text.slice(i + 2, end)) });
        i = end + 2;
        continue;
      }
    } else if (ch === '*' && text[i + 1] && !/\s/.test(text[i + 1]) && text[i + 1] !== '*') {
      let end = i + 1;
      while ((end = text.indexOf('*', end)) !== -1 && (text[end - 1] === ' ' || text[end + 1] === '*' || text[end - 1] === '*')) end += 1;
      if (end > i + 1) {
        push(nodes, { type: 'em', children: parseInline(text.slice(i + 1, end)) });
        i = end + 1;
        continue;
      }
    } else if (ch === '_' && text[i + 1] && !/\s/.test(text[i + 1]) && !(i > 0 && WORD.test(text[i - 1]))) {
      let end = i + 1;
      while ((end = text.indexOf('_', end)) !== -1 && (text[end - 1] === ' ' || (text[end + 1] && WORD.test(text[end + 1])))) end += 1;
      if (end > i + 1) {
        push(nodes, { type: 'em', children: parseInline(text.slice(i + 1, end)) });
        i = end + 1;
        continue;
      }
    }
    push(nodes, { type: 'text', text: ch });
    i += 1;
  }
  return nodes;
}

const BULLET = /^\s{0,3}[-*•]\s+(.*)$/;
const ORDERED = /^\s{0,3}\d{1,3}[.)]\s+(.*)$/;
const FENCE = /^\s{0,3}```\s*([\w+-]*)\s*$/;

export function parseMarkdown(source) {
  const lines = String(source ?? '').replace(/\r\n?/g, '\n').split('\n');
  const blocks = [];
  let paragraph = [];
  let list = null;

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ type: 'p', children: parseInline(paragraph.join('\n')) });
    paragraph = [];
  };
  const flushList = () => {
    if (list) blocks.push(list);
    list = null;
  };

  for (let n = 0; n < lines.length; n += 1) {
    const line = lines[n];
    const fence = FENCE.exec(line);
    if (fence) {
      flushParagraph();
      flushList();
      const body = [];
      n += 1;
      while (n < lines.length && !FENCE.test(lines[n])) {
        body.push(lines[n]);
        n += 1;
      }
      blocks.push({ type: 'code', lang: fence[1], text: body.join('\n') });
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    const bullet = BULLET.exec(line);
    const ordered = bullet ? null : ORDERED.exec(line);
    const item = bullet || ordered;
    if (item) {
      flushParagraph();
      const kind = bullet ? 'ul' : 'ol';
      if (!list || list.type !== kind) {
        flushList();
        list = { type: kind, items: [] };
      }
      list.items.push(parseInline(item[1]));
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  flushParagraph();
  flushList();
  return blocks;
}
