import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseInline, parseMarkdown, safeHref } from '../src/lib/chatMarkdown.js';

test('bold, italic and inline code', () => {
  assert.deepEqual(parseInline('a **b** *c* _d_ `e`').map((n) => n.type), ['text', 'strong', 'text', 'em', 'text', 'em', 'text', 'code']);
  const [strong] = parseInline('**Essay Lab**');
  assert.equal(strong.children[0].text, 'Essay Lab');
});

test('unclosed markers and snake_case stay literal', () => {
  assert.deepEqual(parseInline('**open'), [{ type: 'text', text: '**open' }]);
  assert.deepEqual(parseInline('my_var_name'), [{ type: 'text', text: 'my_var_name' }]);
  assert.deepEqual(parseInline('2 * 3 * 4'), [{ type: 'text', text: '2 * 3 * 4' }]);
});

test('lists and fenced code blocks', () => {
  const blocks = parseMarkdown('Intro\n\n- one\n- **two**\n\n1. a\n2. b\n\n```js\nlet x = *1*\n```');
  assert.deepEqual(blocks.map((b) => b.type), ['p', 'ul', 'ol', 'code']);
  assert.equal(blocks[1].items.length, 2);
  assert.equal(blocks[3].text, 'let x = *1*');
  assert.equal(parseMarkdown('```\nunfinished')[0].type, 'code');
});

test('only http, https and mailto links are kept', () => {
  assert.equal(safeHref('https://naseeb.edu/x'), 'https://naseeb.edu/x');
  assert.equal(safeHref('javascript:alert(1)'), null);
  assert.equal(safeHref('data:text/html,x'), null);
  const [link] = parseInline('[go](https://example.com)');
  assert.equal(link.type, 'link');
  const unsafe = parseInline('[go](javascript:alert(1))');
  assert.ok(unsafe.every((n) => n.type !== 'link'));
});

test('raw html stays plain text and the component never injects HTML', () => {
  const [node] = parseInline('<img src=x onerror=alert(1)>');
  assert.equal(node.type, 'text');
  const source = readFileSync(new URL('../src/components/ChatMarkdown.jsx', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /dangerouslySetInnerHTML|innerHTML/);
  assert.match(source, /noopener/);
});
