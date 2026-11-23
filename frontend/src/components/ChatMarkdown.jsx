import { createElement } from 'react';
import { parseMarkdown } from '../lib/chatMarkdown';

function renderInline(nodes) {
  return nodes.map((node, index) => {
    switch (node.type) {
      case 'strong': return <strong key={index}>{renderInline(node.children)}</strong>;
      case 'em': return <em key={index}>{renderInline(node.children)}</em>;
      case 'code': return <code key={index}>{node.text}</code>;
      case 'link': return <a key={index} href={node.href} target="_blank" rel="noopener noreferrer nofollow">{renderInline(node.children)}</a>;
      default: return node.text;
    }
  });
}

// Renders model text as React elements only (never as HTML).
export function ChatMarkdown({ text }) {
  return <div className="assistant-md">{parseMarkdown(text).map((block, index) => {
    if (block.type === 'code') return <pre key={index}><code>{block.text}</code></pre>;
    if (block.type === 'ul' || block.type === 'ol') {
      return createElement(block.type, { key: index }, block.items.map((item, i) => <li key={i}>{renderInline(item)}</li>));
    }
    return <p key={index}>{renderInline(block.children)}</p>;
  })}</div>;
}
