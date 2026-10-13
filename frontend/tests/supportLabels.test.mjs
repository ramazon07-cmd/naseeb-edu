// Support queue and support view: ticket codes and field labels must read in uz and ru (card 40).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { TRANSLATIONS } = await import('../src/i18n.js');
const { LABELS } = await import('../src/lib/labels.js');

const modal = readFileSync(new URL('../src/components/SupportViewModal.jsx', import.meta.url), 'utf8');
const detailLabels = [...modal.matchAll(/<Detail label="([^"]+)"/g)].map((match) => match[1]);
// SupportTicket.Category and SupportTicket.Status values; Badge shows them through label().
const ticketCodes = ['technical', 'account', 'academic', 'application', 'billing', 'other', 'open', 'in_progress', 'resolved', 'closed'];

test('support view field labels have Uzbek and Russian text', () => {
  assert.ok(detailLabels.length >= 9);
  for (const key of detailLabels) for (const language of ['uz', 'ru']) assert.ok(TRANSLATIONS[language][key], `${language}: ${key}`);
});

test('support ticket category and status codes are labelled and translated', () => {
  for (const code of ticketCodes) {
    assert.ok(LABELS[code], `no label for ${code}`);
    for (const language of ['uz', 'ru']) assert.ok(TRANSLATIONS[language][LABELS[code]], `${language}: ${code}`);
  }
});
