// Builds NaseebEdu's work-values, work-importance and EQ banks, plus their
// Uzbek/Russian translations, from the Naseeb Mind item banks.
// Usage, from frontend/: node scripts/gen-mind-banks.mjs ../../NaseebMind src
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { pathToFileURL } from 'node:url'

const [mindDir, srcDir] = process.argv.slice(2)
const ctx = {}
vm.createContext(ctx)
for (const f of ['values', 'wil', 'eq']) vm.runInContext(fs.readFileSync(path.join(mindDir, 'assets', f + '.js'), 'utf8'), ctx)
const VAL = vm.runInContext('VALUE_LANGS', ctx)
const WIL = vm.runInContext('WIL_LANGS', ctx)
const EQ = vm.runInContext('EQ_LANGS', ctx)
const EQ_DIMS = vm.runInContext('EQ_DIMS', ctx)

const { CHALLENGE_BANK: bank } = await import(pathToFileURL(path.join(srcDir, 'challenges.js')).href)
const oldValues = bank.find((c) => c.key === 'values')
const oldWil = bank.find((c) => c.key === 'workimportance')

const tr = {}
const add = (en, uz, ru) => {
  if (!en) return
  if (tr[en]) return
  // NaseebEdu writes Uzbek with the turned comma (‘) and apostrophe (’).
  tr[en] = [uz.replace(/ʻ/g, '‘').replace(/ʼ/g, '’'), ru]
}

// Work values: same ten statements, same ids, in the same order.
const values = {
  key: 'values', instrument: 'Work values', licence: 'Written in-house',
  title: 'What matters at work', blurb: 'What you want from your future work.',
  scale: VAL.en.labels, scoring: 'values',
  items: VAL.en.items.map((item, i) => {
    const old = oldValues.items[i]
    if (old.dim !== item.d) throw new Error(`values item ${i}: ${old.dim} != ${item.d}`)
    add(item.t, VAL.uz.items[i].t, VAL.ru.items[i].t)
    return { id: old.id, dim: item.d, text: item.t }
  }),
}
VAL.en.labels.forEach((l, i) => add(l, VAL.uz.labels[i], VAL.ru.labels[i]))
for (const k of Object.keys(VAL.en.names)) add(VAL.en.names[k], VAL.uz.names[k], VAL.ru.names[k])
add(values.title, 'Ishda nima muhim', 'Что важно в работе')
add(values.blurb, 'Kelajakdagi ishingizdan nimalarni kutishingiz.', 'Что вы хотите от своей будущей работы.')

// Work importance: twenty cards, any number per level, ids kept by card letter.
const wilIds = Object.fromEntries(oldWil.items.map((item) => [item.card, item]))
const workimportance = {
  key: 'workimportance', instrument: 'O*NET Work Importance Locator', licence: 'Public domain (US DOL)',
  title: WIL.en.title, blurb: WIL.en.blurb, scale: WIL.en.levels, scoring: 'wil',
  items: WIL.en.cards.map((card, i) => {
    const old = wilIds[card.c]
    if (!old || old.value !== card.v) throw new Error(`wil card ${card.c}`)
    add(card.t, WIL.uz.cards[i].t, WIL.ru.cards[i].t)
    return { id: old.id, card: card.c, value: card.v, section: WIL.en.stem, text: card.t }
  }),
}
WIL.en.levels.forEach((l, i) => add(l, WIL.uz.levels[i], WIL.ru.levels[i]))
for (const k of Object.keys(WIL.en.names)) add(WIL.en.names[k], WIL.uz.names[k], WIL.ru.names[k])
add(WIL.en.stem, WIL.uz.stem, WIL.ru.stem)
add(WIL.en.title, WIL.uz.title, WIL.ru.title)
add(WIL.en.blurb, WIL.uz.blurb, WIL.ru.blurb)

// EQ: WLEIS-16, four items per dimension in order, answered 1..7.
const eq = {
  key: 'eq', instrument: 'WLEIS-16', licence: 'Used with permission',
  title: EQ.en.title, blurb: EQ.en.blurb, scale: EQ.en.labels, scoring: 'eq',
  items: EQ.en.items.map((text, i) => {
    add(text, EQ.uz.items[i], EQ.ru.items[i])
    return { id: 3000 + i, dim: EQ_DIMS[Math.floor(i / 4)], text }
  }),
}
EQ.en.labels.forEach((l, i) => add(l, EQ.uz.labels[i], EQ.ru.labels[i]))
for (const k of EQ_DIMS) add(EQ.en.names[k], EQ.uz.names[k], EQ.ru.names[k])
add(EQ.en.title, EQ.uz.title, EQ.ru.title)
// One line per EQ area for the flipped hub card: the first sentence of the
// result description.
const firstSentence = (text) => text.split(/(?<=\.)\s/)[0]
const eqLead = {}
for (const k of EQ_DIMS) {
  eqLead[k] = firstSentence(EQ.en.result.descriptions[k])
  add(eqLead[k], firstSentence(EQ.uz.result.descriptions[k]), firstSentence(EQ.ru.result.descriptions[k]))
}
add(EQ.en.blurb, EQ.uz.blurb, EQ.ru.blurb)

// Hub copy, taken from Naseeb Mind's own string tables (%1/%2 -> named slots).
const strings = (file) => {
  const src = fs.readFileSync(path.join(mindDir, file), 'utf8')
  return (key) => {
    const m = src.match(new RegExp(`^\\s*${key}:\\s*'((?:[^'\\\\]|\\\\.)*)'`, 'm'))
    if (!m) throw new Error(`${file}: ${key}`)
    return m[1].replace(/\\'/g, "'")
  }
}
const uzS = strings('test.html'), ruS = strings('assets/test-ru.js'), enS = strings('assets/test-en.js')
const HUB = ['sideTests', 'pgTestsSub', 'seeResult', 'hubStart', 'hubResume', 'nextEyebrow', 'hubComplete',
  'dashContinueP', 'dashStartP', 'sideMajor', 'dashSeeDirections', 'chReasoning',
  ...['personality', 'interests', 'values', 'school', 'workimportance', 'reasoning', 'eq'].map((k) => 'hubBrief_' + k)]
const slots = (s) => s.replace('%1', '{done}').replace('%2', '{total}')
for (const key of HUB) add(slots(enS(key)), slots(uzS(key)), slots(ruS(key)))
add('How school feels', 'Qaysi fanlar sizga mos', 'Каким ощущается школа')

// Major names, by the taxonomy key both projects share. Keys Naseeb Mind does
// not carry stay in English.
vm.runInContext(fs.readFileSync(path.join(mindDir, 'assets', 'careers-data.js'), 'utf8'), ctx)
const TAX = vm.runInContext('TAXONOMY_NAMES', ctx)
const { NAMES } = await import(pathToFileURL(path.join(srcDir, 'careers.js')).href)
for (const [key, en] of Object.entries(NAMES.majors)) {
  if (TAX.uz.majors[key] && TAX.ru.majors[key]) add(en, TAX.uz.majors[key], TAX.ru.majors[key])
}

// A key another translation file already defines keeps that translation: the
// hub file must never change wording elsewhere in the app.
const escapeRe = (v) => v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const others = ['i18n.js', ...fs.readdirSync(path.join(srcDir, 'translations')).filter((f) => f !== 'assessmentHub.js').map((f) => `translations/${f}`)]
  .map((f) => fs.readFileSync(path.join(srcDir, f), 'utf8'))
for (const key of Object.keys(tr)) {
  const defined = new RegExp(`^\\s*(?:"${escapeRe(key)}"|'${escapeRe(key)}'|${escapeRe(key)})\\s*:`, 'm')
  if (others.some((text) => defined.test(text))) delete tr[key]
}

const json = (v) => JSON.stringify(v, null, 2)
fs.writeFileSync(path.join(srcDir, 'challengeBanksMind.js'),
`// GENERATED by scripts/gen-mind-banks.mjs from the Naseeb Mind item banks
// (assets/values.js, wil.js, eq.js) -- do not edit by hand. Item ids of
// values and work importance are the ones NaseebEdu already stored, matched by
// dimension and card letter.

export const VALUES_CHALLENGE = ${json(values)}

export const WORK_IMPORTANCE_CHALLENGE = ${json(workimportance)}

// WLEIS: Wong & Law (2002). Four unweighted means on the original 1..7 scale.
export const EQ_CHALLENGE = ${json(eq)}

export const EQ_ORDER = ${json(EQ_DIMS)}
export const EQ_NAME = ${json(EQ.en.names)}
export const EQ_LEAD = ${json(eqLead)}
`)

fs.writeFileSync(path.join(srcDir, 'translations', 'assessmentHub.js'),
`// GENERATED by scripts/gen-mind-banks.mjs from the Naseeb Mind string tables
// and item banks -- do not edit by hand. Assessment hub and the three Naseeb
// Mind banks: English key -> [Uzbek (Latin), Russian].
export const ASSESSMENT_HUB_TRANSLATIONS = ${json(tr)}

export function assessmentHubMessages(language) {
  const index = language === 'uz' ? 0 : 1
  return Object.fromEntries(Object.entries(ASSESSMENT_HUB_TRANSLATIONS).map(([key, values]) => [key, values[index]]))
}
`)
console.log('values', values.items.length, 'wil', workimportance.items.length, 'eq', eq.items.length, 'strings', Object.keys(tr).length)
