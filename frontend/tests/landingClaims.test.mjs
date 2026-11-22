// The logged-out pages may only claim what Naseeb AI really does: essay feedback
// that quotes the essay, counselor letter ideas, major explanations and the
// assistant chat. Rankings, matching and the roadmap are rule-based.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { LANDING_TRANSLATIONS } from '../src/translations/landing.js';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const landing = read('../src/LandingPage.jsx');
const html = read('../index.html');
const i18n = read('../src/i18n.js');
const unescape = (value) => value.replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16))).replace(/\\(["'\\])/g, '$1');
const decoded = unescape(landing);

// Every rendered landing string, in English, Uzbek and Russian.
const allCopy = [
  decoded,
  html,
  i18n,
  ...Object.entries(LANDING_TRANSLATIONS).flatMap(([key, values]) => [key, ...values]),
].join('\n');

const OVERCLAIMS = [
  [/retrieval-augmented|\bRAG\b/i, 'retrieval (RAG): the assistant gets no retrieved records'],
  [/machine learning|Машинное обучение|Машинного обучения/i, 'machine learning: there is no trained model'],
  [/labour market|mehnat bozori|рынка труда/i, 'labour-market data: careers.js has none'],
  [/anomaly|keskin o‘zgarishlarni aniqlash|аномали/i, 'anomaly detection'],
  [/rolls back|oldingi to‘g‘ri versiyaga|откатывается/i, 'automatic rollback'],
  [/regression test|regression test to‘plam|регрессион/i, 'AI regression or eval suites'],
  [/low-confidence|ishonch darajasi past|низкой уверенност/i, 'withholding low-confidence results'],
  [/Cites sources|shows the source with every answer|Manba bilan/i, 'assistant citations'],
  [/Calculated by AI|real vaqtda hisoblaydi|ИИ рассчитывает/i, 'AI-calculated roadmap and rankings'],
  [/fully automated/i, 'a fully automated product: counselors review work'],
  [/grammar|grammatical|grammatik|граммати/i, 'grammar scoring', /does not score grammar|grammatikani baholamaydi|не оценивает грамматику/i],
  [/NLP Essay Lab|AI Major Match|Core AI modules|AI grounded in data/, 'old AI module names'],
  [/Essay Coach|Naseeb Coach/, 'old coach name: it is Naseeb AI'],
  [/sun’iy intellektga asoslangan|на основе искусственного интеллекта|AI-powered/i, 'the whole platform presented as AI-based'],
  [/motivation essay|motivatsion insho|мотивационн/i, 'motivation essays: no such essay type'],
];

test('landing copy makes no claim the code does not back', () => {
  const found = [];
  for (const [pattern, why, allowed] of OVERCLAIMS) {
    const text = allowed ? allCopy.replace(new RegExp(allowed.source, 'gi'), '') : allCopy;
    const match = text.match(pattern);
    if (match) found.push(`${JSON.stringify(match[0])}: ${why}`);
  }
  assert.deepEqual(found, []);
});

test('the AI is named Naseeb AI across the landing page and meta tags', () => {
  for (const key of ['Naseeb AI assistant', 'Essay Lab with Naseeb AI', 'Naseeb AI features', 'Naseeb AI stays in bounds', 'With Naseeb AI feedback.']) {
    assert.ok(landing.includes(`"${key}"`), `LandingPage.jsx renders ${key}`);
    const [uz, ru] = LANDING_TRANSLATIONS[key];
    assert.match(uz, /Naseeb AI/, `${key} keeps the name in Uzbek`);
    assert.match(ru, /Naseeb AI/, `${key} keeps the name in Russian`);
  }
  for (const match of html.matchAll(/<meta (?:name|property)="(?:description|og:description|twitter:description)" content="([^"]+)"/g)) {
    assert.match(match[1], /Naseeb AI insho tahlili/);
  }
  assert.equal([...html.matchAll(/Naseeb AI insho tahlili/g)].length, 3);
});

test('every landing string has Uzbek and Russian text, and no key is left over', () => {
  const literals = new Set(
    [...landing.matchAll(/(?:title|description|label|note|question):\s*"((?:\\.|[^"\\])*)"|t\(\s*"((?:\\.|[^"\\])*)"\s*[,)]/g)]
      .map((m) => unescape(m[1] ?? m[2])),
  );
  const answers = [...decoded.matchAll(/answer:\s*\[([\s\S]*?)\]/g)].flatMap((m) => [...m[1].matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((s) => s[1]));
  for (const key of [...literals, ...answers].filter((key) => /[A-Za-z]/.test(key))) {
    if (!/\s/.test(key) && !/^[A-Z]/.test(key)) continue; // icon names and ids
    const values = LANDING_TRANSLATIONS[key];
    if (!values) continue; // shared UI strings live in ui.js
    assert.equal(values.length, 2, key);
    assert.ok(values.every((value) => value.trim()), `${key} has empty text`);
  }
  for (const key of Object.keys(LANDING_TRANSLATIONS)) {
    assert.ok(decoded.includes(`"${key}"`), `unused landing key: ${key}`);
  }
});

test('the layout keeps ten modules, four principles and its ledger figures', () => {
  const section = (name) => decoded.slice(decoded.indexOf(`const ${name} = [`), decoded.indexOf('];', decoded.indexOf(`const ${name} = [`)));
  assert.equal([...section('capabilities').matchAll(/icon:/g)].length, 10);
  assert.equal([...section('aboutPrinciples').matchAll(/title:/g)].length, 4);
  assert.deepEqual([...section('ledger').matchAll(/figure:\s*(\d+)/g)].map((m) => Number(m[1])), [4, 3, 3]);
});
