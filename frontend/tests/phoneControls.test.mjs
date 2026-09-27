// Phone layout guards for the shared workspace shell: the assistant launcher
// must not cover dialog buttons, and the header/back icons stay thumb-sized.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

// Declarations of `selector` inside `@media (max-width: <width>px)` blocks.
function mediaRules(width, selector) {
  const found = [];
  for (const match of styles.matchAll(new RegExp(`@media \\(max-width: ${width}px\\) \\{`, 'g'))) {
    let depth = 1;
    let index = match.index + match[0].length;
    const start = index;
    while (depth && index < styles.length) {
      if (styles[index] === '{') depth += 1;
      if (styles[index] === '}') depth -= 1;
      index += 1;
    }
    for (const [, selectors, body] of styles.slice(start, index - 1).matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      if (selectors.split(',').map((part) => part.trim()).includes(selector)) found.push(body);
    }
  }
  return found.join('\n');
}

test('the assistant launcher hides while a dialog is open', () => {
  assert.match(styles, /body:has\(\.modal-backdrop\) \.assistant-launchers \{\s*display: none;/);
});

test('phone header icons and the chat back button are at least 44px', () => {
  for (const selector of ['.top-header .icon-button', '.message-back']) {
    const rules = mediaRules(560, selector);
    assert.match(rules, /width: 44px;/, selector);
    assert.match(rules, /height: 44px;/, selector);
    assert.match(rules, /flex: 0 0 44px;/, selector);
  }
});

test('student phone controls are at least 44px tall, scoped to the student shell', () => {
  const scoped = (selector) => `.app-shell.role-student ${selector}`;
  for (const selector of ['.dashboard-link', '.button', '.button.small', '.portal-tabs button', '.channel-folder', '.chat-new-button', '.sidebar nav button', '.sidebar-account-menu button', '.el-chip', '.el-menu button']) {
    assert.match(mediaRules(560, scoped(selector)), /min-height: 44px;/, selector);
  }
  for (const selector of ['.icon-button', '.el-icon-btn', '.messaging-page .message-send', '.customizer-grip']) {
    const rules = mediaRules(560, scoped(selector));
    assert.match(rules, /width: 44px;/, selector);
    assert.match(rules, /height: 44px;/, selector);
  }
  for (const selector of ['.el-btn', '.el-toggle button', '.top-header .language-selector select']) {
    assert.match(mediaRules(560, scoped(selector)), /height: 44px;/, selector);
  }
});

test('the workspace shell names the signed-in role so phone rules can target students only', () => {
  const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
  assert.match(app, /className=\{`app-shell role-\$\{user\.role\}/);
});
