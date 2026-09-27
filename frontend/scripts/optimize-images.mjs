// Resizes and recompresses the images in public/ to the size they are shown
// at (2x for retina). Safe to re-run: an image already at or below its target
// is only rewritten when that saves more than 10%.
//   node scripts/optimize-images.mjs
// tests/imageBudget.test.mjs fails CI when a public image grows past budget.
import { existsSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const PUBLIC = join(dirname(fileURLToPath(import.meta.url)), '..', 'public')
const IVORY = '#f7f7f7'

async function write(path, pipeline) {
  const buffer = await pipeline.toBuffer()
  const target = join(PUBLIC, path)
  const before = existsSync(target) ? statSync(target).size : 0
  // Re-running must not keep re-encoding (and degrading) finished files.
  if (before && buffer.length > before * 0.9) return
  writeFileSync(target, buffer)
  console.log(`${path.padEnd(58)} ${String(Math.round(before / 1024)).padStart(6)} KB -> ${String(Math.round(buffer.length / 1024)).padStart(4)} KB`)
}

const src = (path) => sharp(readFileSync(join(PUBLIC, path)), { limitInputPixels: false })
const png = (image) => image.png({ compressionLevel: 9, palette: true, quality: 90, effort: 10 })
const jpeg = (image, quality = 80) => image.jpeg({ quality, mozjpeg: true })
const webp = (image, quality = 78) => image.webp({ quality, effort: 6 })
// Keep the aspect ratio so the CSS object-position crops stay identical.
const shortSide = (image, size) => image.resize({ width: size, height: size, fit: 'outside', withoutEnlargement: true })

// Hero: responsive WebP set; the PNG masters are no longer shipped.
export const HERO_WIDTHS = [640, 960, 1448]
for (const [variant, master] of [['light', 'naseeb-student-application-hero-light.png'], ['cool', 'naseeb-student-application-hero-cool.png']]) {
  if (!existsSync(join(PUBLIC, 'landing', master))) continue
  for (const width of HERO_WIDTHS) {
    await write(`landing/hero-${variant}-${width}.webp`, webp(src(`landing/${master}`).resize({ width, withoutEnlargement: true }), 74))
  }
}

// Social preview (og:image) — 1200 px is what the platforms display.
await write('landing/naseeb-student-application-hero.jpg', jpeg(src('landing/naseeb-student-application-hero.jpg').resize({ width: 1200, withoutEnlargement: true }), 78))

// Logos: shown at 34-44 px (CSS background), 192 px covers 4x screens.
await write('brand/naseeb-gold-shield.png', png(src('brand/naseeb-gold-shield.png').resize({ width: 192, height: 192, fit: 'inside' })))
if (existsSync(join(PUBLIC, 'brand/naseeb-midnight-shield.svg'))) {
  // A 2.3 MB raster wrapped in an SVG; render it once to a real small PNG.
  await write('brand/naseeb-midnight-shield.png', png(sharp(readFileSync(join(PUBLIC, 'brand/naseeb-midnight-shield.svg')), { density: 24 }).resize({ width: 192, height: 192, fit: 'inside' })))
}
// brand/icon-192.png and icon-512.png (web manifest) were rendered once from the
// original 1312 px shield master in git history (ba8d504); do not upscale the 192 px logo.
// Favicons (32 px, per theme) and the iOS home-screen icon (opaque, 180 px).
await write('brand/favicon-light-32.png', png(src('brand/naseeb-gold-shield.png').resize({ width: 32, height: 32, fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })))
await write('brand/favicon-dark-32.png', png(src('brand/naseeb-midnight-shield.png').resize({ width: 32, height: 32, fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })))
await write('brand/apple-touch-icon.png', png(sharp({ create: { width: 180, height: 180, channels: 4, background: IVORY } })
  .composite([{ input: await src('brand/naseeb-gold-shield.png').resize({ width: 140, height: 140, fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } }).toBuffer(), gravity: 'center' }])))

await write('brand/naseeb-mind-logo.png', png(src('brand/naseeb-mind-logo.png').resize({ width: 64, height: 96, fit: 'inside' })))
await write('brand/assistant-bird.png', png(src('brand/assistant-bird.png').resize({ width: 128, height: 192, fit: 'inside', withoutEnlargement: true })))
await write('brand/login-mountains.jpg', jpeg(src('brand/login-mountains.jpg'), 72))

// Review portraits: 52 px circles -> 112 px short side.
for (const name of ['amirali', 'dilshod', 'diyorbek', 'muhammadrizo', 'nurbek', 'saidakmal']) {
  await write(`landing/reviews/${name}.jpg`, jpeg(shortSide(src(`landing/reviews/${name}.jpg`).rotate(), 112), 82))
}
// Team portraits: 168 px squares -> 336 px.
for (const name of ['asadbek', 'firdavs', 'humoyun', 'sevinchkhon', 'shakhriyor']) {
  await write(`landing/team/${name}.jpg`, jpeg(shortSide(src(`landing/team/${name}.jpg`).rotate(), 336), 80))
}
// Placement logos render in a 232x88 slot at most.
for (const name of ['universities/hit.png', 'universities/debrecen-lockup.png', 'universities/gettysburg-color.png', 'universities/hkmu.png', 'universities/lingnan.png', 'universities/lynn.png', 'programs/flex.png', 'programs/lumiere-wordmark.png']) {
  await write(`landing/${name}`, png(src(`landing/${name}`).resize({ width: 464, height: 176, fit: 'inside', withoutEnlargement: true })))
}
await write('landing/programs/nsp.jpg', jpeg(src('landing/programs/nsp.jpg').resize({ width: 464, height: 176, fit: 'inside', withoutEnlargement: true }), 82))
