// One-off codemod (kept for reference): rewrites px font sizes in src/*.css
// to the rem type scale and lifts anything below 12px to --text-xs.
// The landing "product window" is a role="img" illustration of the app and
// keeps its miniature scale.
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = fileURLToPath(new URL('../src/', import.meta.url))
export const TYPE_TOKENS = { 12: '--text-xs', 13: '--text-sm', 14: '--text-md', 16: '--text-base', 18: '--text-lg', 20: '--text-xl', 24: '--text-2xl', 32: '--text-3xl' }
export const MIN_PX = 12
export const isIllustration = (selector) => /landing-preview|landing-product/.test(selector)

const rem = (px) => `${+(px / 16).toFixed(4)}rem`.replace(/^0\./, '.')
function size(px, floor) {
  const value = floor && px < MIN_PX ? MIN_PX : px
  return TYPE_TOKENS[value] ? `var(${TYPE_TOKENS[value]})` : rem(value)
}

export function convertDeclarations(body, floor = true) {
  return body
    .replace(/(font-size:\s*)(\d+(?:\.\d+)?)px(?=\s*(?:;|$|!|\}))/g, (_, prop, px) => prop + size(Number(px), floor))
    .replace(/(font-size:\s*clamp\()([^;]*)/g, (_, head, rest) => head + rest.replace(/(\d+(?:\.\d+)?)px/g, (__, px) => rem(Number(px))))
    .replace(/(font:\s*(?:\d{3}\s+|italic\s+|normal\s+)*)(\d+(?:\.\d+)?)px(?=[\s/])/g, (_, head, px) => head + size(Number(px), floor))
    .replace(/(--lp-t-[a-z]+:\s*)(\d+(?:\.\d+)?)px/g, (_, head, px) => head + size(Number(px), floor))
    .replace(/(--lp-t-[a-z]+:\s*clamp\()([^;]*)/g, (_, head, rest) => head + rest.replace(/(\d+(?:\.\d+)?)px/g, (__, px) => rem(Number(px))))
}

export function convertCss(css) {
  return css.replace(/([^{}]*)\{([^{}]*)\}/g, (whole, selector, body) =>
    isIllustration(selector) ? whole : `${selector}{${convertDeclarations(body)}}`)
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  for (const name of readdirSync(SRC).filter((file) => file.endsWith('.css'))) {
    const path = join(SRC, name)
    const before = readFileSync(path, 'utf8')
    const after = convertCss(before)
    if (after !== before) { writeFileSync(path, after); console.log('updated', name) }
  }
}
