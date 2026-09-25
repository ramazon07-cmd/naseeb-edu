// Fonts a student can pick in the Essay Lab. The list is fixed (the server
// rejects anything else, see doc.py FONT_FAMILIES). System fonts come with a
// fallback stack; web fonts are self-hosted (the CSP allows only 'self') and
// their CSS is fetched the first time a document uses them.
import { FONT_FAMILIES } from './docDelta.js'

export const DEFAULT_FONT = 'Newsreader'

const STACKS = {
  Arial: "Arial, 'Helvetica Neue', Helvetica, 'Liberation Sans', sans-serif",
  'Times New Roman': "'Times New Roman', Times, 'Liberation Serif', serif",
  Georgia: "Georgia, 'DejaVu Serif', serif",
  'Courier New': "'Courier New', Courier, 'Liberation Mono', monospace",
  Verdana: "Verdana, Geneva, 'DejaVu Sans', sans-serif",
  Newsreader: "'Newsreader Variable', Newsreader, Georgia, serif",
  Montserrat: 'Montserrat, system-ui, sans-serif',
  Merriweather: "'Merriweather Variable', Merriweather, Georgia, serif",
  Lora: "'Lora Variable', Lora, Georgia, serif",
  Roboto: "'Roboto Variable', Roboto, Arial, sans-serif",
}

export const FONTS = FONT_FAMILIES.map((name) => ({ name, stack: STACKS[name] }))

export const fontStack = (name) => STACKS[name] || null

// Newsreader is the page font, so the editor chunk imports it directly.
const LAZY = {
  Merriweather: () => import('@fontsource-variable/merriweather/wght.css'),
  Lora: () => Promise.all([import('@fontsource-variable/lora/wght.css'), import('@fontsource-variable/lora/wght-italic.css')]),
  Roboto: () => Promise.all([import('@fontsource-variable/roboto/wght.css'), import('@fontsource-variable/roboto/wght-italic.css')]),
}
const requested = new Set()

export function loadFont(name) {
  if (!LAZY[name] || requested.has(name)) return
  requested.add(name)
  LAZY[name]().catch(() => requested.delete(name))
}

const allRequested = () => Object.keys(LAZY).every((name) => requested.has(name))

// Loads the web fonts a ProseMirror doc (node) uses. Stops walking once every
// lazy font is requested, so later calls cost nothing.
export function loadFontsIn(doc) {
  if (!doc || allRequested()) return
  doc.descendants((node) => {
    if (!node.isText) return true
    for (const mark of node.marks) {
      if (mark.type.name === 'textStyle' && mark.attrs.fontFamily) loadFont(mark.attrs.fontFamily)
    }
    return false
  })
}

// Same for a JSON doc (history previews).
export function loadFontsInJson(node) {
  if (!node || allRequested()) return
  for (const mark of node.marks || []) {
    if (mark?.type === 'textStyle' && mark.attrs?.fontFamily) loadFont(mark.attrs.fontFamily)
  }
  for (const child of node.content || []) loadFontsInJson(child)
}
