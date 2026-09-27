// The Pages view: sheet geometry, the pagination pass (correct and
// incremental), page-break commands, and the view mode preference.
import test from 'node:test'
import assert from 'node:assert/strict'

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } }

const {
  collapseMargins, contentBottom, contentTop, gapKey, isAfter, pageAt, pageGeometry, paginate, paperWidth, readPageMode, stackHeight, writePageMode,
} = await import('../src/essayLab/pageLayout.js')
const { getSchema } = await import('@tiptap/react')
const { default: StarterKit } = await import('@tiptap/starter-kit')
const { EditorState, TextSelection, NodeSelection } = await import('@tiptap/pm/state')
const { history, undoDepth } = await import('@tiptap/pm/history')
const { appendBlankPage, changedRange, paginationKey, paginationPlugin } = await import('../src/essayLab/pagination.js')
const { EssayDocument, PageBreak } = await import('../src/essayLab/formatting.js')

const A4 = pageGeometry('a4')
const schema = getSchema([EssayDocument, PageBreak, StarterKit.configure({ document: false })])

// A tiny stand-in for the browser's layout: blocks stack with collapsing
// margins; a spacer (a block with height and no margins) stops the collapse;
// a block with `lines` is made of 20px lines and can take gaps between them.
const LINE = 20
function layOut(blocks, gaps) {
  const rows = []
  let bottom = A4.top
  blocks.forEach((block, index) => {
    const spacer = gaps.get(`b${index}`)
    let top
    if (index === 0) top = A4.top + block.mt
    else if (spacer) top = bottom + blocks[index - 1].mb + spacer.height + block.mt
    else top = bottom + collapseMargins(blocks[index - 1].mb, block.mt)
    const lineTops = []
    let inner = 0
    for (let line = 0; line < (block.lines || 0); line += 1) {
      inner += gaps.get(`l${index}:${linePos(index, line)}`)?.height || 0
      lineTops.push(top + line * LINE + inner)
    }
    bottom = top + block.height + inner
    rows.push({ top, bottom, inner, lineTops })
  })
  return rows
}
const linePos = (index, line) => index * 1000 + line

// Runs one pass like the plugin does and returns the merged gaps (by key).
function pass(blocks, gaps, { start = 0, dirtyEnd = blocks.length - 1, pages = 1 } = {}) {
  const rows = layOut(blocks, gaps)
  const seen = new Set()
  const result = paginate({
    count: blocks.length,
    start,
    dirtyEnd,
    geometry: A4,
    measure: (index) => {
      seen.add(index)
      const block = blocks[index]
      return {
        ...rows[index],
        inlineGaps: rows[index].inner,
        pageBreak: Boolean(block.pageBreak),
        spacer: gaps.has(`b${index}`),
        lines: block.lines ? () => Array.from({ length: block.lines }, (_, line) => ({ offset: line * LINE, height: LINE, pos: linePos(index, line) })) : null,
      }
    },
    margins: (index) => ({ top: blocks[index].mt, bottom: blocks[index].mb }),
    previous: new Map([...gaps.values()].map((gap) => [gapKey(gap), gap.page])),
    previousPages: pages,
  })
  const next = [...gaps.values()].filter((gap) => gap.index < start || (result.stop && isAfter(gap, result.stop)))
  next.push(...result.gaps)
  next.sort((a, b) => a.index - b.index || (a.pos ?? -1) - (b.pos ?? -1))
  return { gaps: new Map(next.map((gap) => [gapKey(gap), gap])), spacers: next.filter((gap) => gap.pos == null), pages: result.pages, result, seen }
}

const paragraph = (height) => ({ height, mt: 13.6, mb: 0 })
const firstParagraph = (height) => ({ height, mt: 0, mb: 0 })
const essay = (count, height = 100) => [firstParagraph(height), ...Array.from({ length: count - 1 }, () => paragraph(height))]
const lined = (lines, mt = 13.6) => ({ height: lines * LINE, mt, mb: 0, lines })
const pageBreak = () => ({ height: 1, mt: 0, mb: 0, pageBreak: true })
const TEXT_HEIGHT = contentBottom(A4, 0) - contentTop(A4, 0)

// Every block and line sits inside one sheet's text area (a block without
// lines that is taller than a page starts at the top of one), and a block
// after a page break starts a sheet.
function assertPaged(blocks, gaps) {
  const rows = layOut(blocks, gaps)
  rows.forEach((row, index) => {
    const page = pageAt(A4, row.top)
    assert.ok(row.top >= contentTop(A4, page) - 0.6, `block ${index} starts in the top margin`)
    if (row.lineTops.length) {
      for (const lineTop of row.lineTops) {
        const linePage = pageAt(A4, lineTop)
        assert.ok(lineTop >= contentTop(A4, linePage) - 0.6 && lineTop + LINE <= contentBottom(A4, linePage) + 0.6, `a line of block ${index} is off the text area`)
      }
    } else if (row.bottom - row.top > TEXT_HEIGHT) {
      assert.ok(Math.abs(row.top - contentTop(A4, page)) < 0.6, `tall block ${index} starts on a fresh sheet`)
    } else {
      assert.ok(row.bottom <= contentBottom(A4, page) + 0.6, `block ${index} runs past the bottom margin`)
    }
    if (index > 0 && blocks[index - 1].pageBreak) {
      assert.ok(Math.abs(row.top - contentTop(A4, pageAt(A4, rows[index - 1].top) + 1)) < 0.6, `block ${index} follows a page break`)
    }
  })
  return rows
}

test('sheets have the real paper proportions and one-inch margins', () => {
  assert.equal(paperWidth('a4'), 794)
  assert.equal(paperWidth('letter'), 816)
  assert.equal(paperWidth('a3'), 794)
  assert.equal(Math.round(A4.width), 794)
  assert.equal(Math.round(A4.height), 1123)
  assert.equal(Math.round(A4.top), 96)
  const letter = pageGeometry('letter')
  assert.equal(Math.round(letter.width), 816)
  assert.equal(Math.round(letter.height), 1056)
  assert.equal(Math.round(letter.side), 96)
  assert.equal(stackHeight(A4, 3), A4.height * 3 + A4.gap * 2)
})

test('text flows from sheet to sheet and every page is numbered', () => {
  const blocks = essay(40)
  const { gaps, spacers, pages } = pass(blocks, new Map())
  const rows = assertPaged(blocks, gaps)
  assert.ok(spacers.length >= 3)
  assert.equal(pages, pageAt(A4, rows.at(-1).top) + 1)
  // Each spacer moves its block to the top of the next sheet, and only when
  // the block would not have fitted.
  for (const gap of spacers) {
    assert.ok(Math.abs(rows[gap.index].top - contentTop(A4, gap.page)) < 0.6)
    assert.ok(rows[gap.index - 1].bottom + 13.6 + 100 > contentBottom(A4, gap.page - 1))
  }
})

test('a paragraph that crosses the page end is split between its lines', () => {
  const blocks = [lined(40, 0), lined(20), lined(3)]
  const { gaps } = pass(blocks, new Map())
  const rows = assertPaged(blocks, gaps)
  const split = [...gaps.values()].filter((gap) => gap.pos != null)
  assert.equal(split.length, 1)
  assert.equal(split[0].index, 1)
  // The first page is filled up to its last whole line.
  const lastOnPage = rows[1].lineTops.filter((top) => pageAt(A4, top) === 0).at(-1)
  assert.ok(lastOnPage + 2 * LINE > contentBottom(A4, 0))
  // A paragraph longer than a page is split more than once.
  const long = [lined(130, 0)]
  const many = pass(long, new Map())
  assertPaged(long, many.gaps)
  assert.equal(many.gaps.size, 2)
  assert.equal(many.pages, 3)
})

test('a block whose first line does not fit moves whole; so does an empty paragraph', () => {
  const lines = Math.floor(TEXT_HEIGHT / LINE)
  const blocks = [lined(lines, 0), lined(5), firstParagraph(20)]
  const { gaps } = pass(blocks, new Map())
  assertPaged(blocks, gaps)
  assert.deepEqual([...gaps.keys()], ['b1'])
})

test('a page break starts a new sheet, and two in a row leave a blank page', () => {
  const blocks = [firstParagraph(60), pageBreak(), paragraph(60), pageBreak(), pageBreak(), paragraph(60)]
  const { gaps, pages } = pass(blocks, new Map())
  const rows = assertPaged(blocks, gaps)
  assert.deepEqual([0, 2, 5].map((index) => pageAt(A4, rows[index].top)), [0, 1, 3])
  assert.equal(pages, 4)
  // A document ending with a page break shows the (empty) page after it.
  assert.equal(pass(blocks.slice(0, 2), new Map()).pages, 2)
})

test('a block taller than a page without lines starts a sheet and the next block goes after it', () => {
  const blocks = [firstParagraph(800), paragraph(1500), paragraph(60)]
  const { gaps } = pass(blocks, new Map())
  const rows = assertPaged(blocks, gaps)
  assert.equal(pageAt(A4, rows[1].top), 1)
  assert.equal(pageAt(A4, rows[2].top), 2)
})

test('gaps from an earlier pass are replaced, not stacked', () => {
  const blocks = [lined(12, 0), ...Array.from({ length: 30 }, (_, index) => lined(3 + (index % 7)))]
  const first = pass(blocks, new Map())
  assertPaged(blocks, first.gaps)
  const again = pass(blocks, first.gaps)
  assert.deepEqual([...again.gaps], [...first.gaps])
  // A paragraph before the first break shrinks: everything after moves up.
  const shrunk = blocks.map((block, index) => (index === 2 ? lined(1) : block))
  const next = pass(shrunk, first.gaps, { start: 2, dirtyEnd: 2 })
  assertPaged(shrunk, next.gaps)
  assert.deepEqual([...next.gaps.keys()], [...pass(shrunk, new Map()).gaps.keys()])
})

test('typing in a 20-page essay only measures from the edited block to the next unchanged gap', () => {
  const blocks = [lined(8, 0), ...Array.from({ length: 219 }, (_, index) => lined(2 + (index % 9)))]
  const full = pass(blocks, new Map())
  assertPaged(blocks, full.gaps)
  assert.ok(full.pages >= 20, `pages: ${full.pages}`)
  const edited = 150
  // Same height (a few letters within a line): converges at the next gap.
  const typing = pass(blocks, full.gaps, { start: edited, dirtyEnd: edited, pages: full.pages })
  assert.ok(typing.result.stop)
  assert.ok(typing.seen.size <= 20, `measured ${typing.seen.size} blocks`)
  assert.ok(Math.min(...typing.seen) >= edited - 1)
  assert.deepEqual([...typing.gaps], [...full.gaps])
  assert.equal(typing.pages, full.pages)

  // A new line: later gaps move, and the result matches a full pass.
  const taller = blocks.map((block, index) => (index === edited ? lined(block.lines + 1) : block))
  const grown = pass(taller, full.gaps, { start: edited, dirtyEnd: edited, pages: full.pages })
  assert.ok(Math.min(...grown.seen) >= edited - 1)
  assertPaged(taller, grown.gaps)
  const reference = pass(taller, new Map())
  assert.deepEqual([...grown.gaps.keys()], [...reference.gaps.keys()])
  assert.equal(grown.pages, reference.pages)
})

test('add blank page appends a break and an empty paragraph, and Backspace removes a break', async () => {
  const { joinBackward, deleteSelection } = await import('@tiptap/pm/commands')
  const doc = schema.nodeFromJSON({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Text' }] }] })
  let state = EditorState.create({ doc, schema, selection: TextSelection.create(doc, 1) })
  state = state.apply(appendBlankPage(state.tr))
  assert.deepEqual(state.doc.toJSON().content, [
    { type: 'paragraph', content: [{ type: 'text', text: 'Text' }] }, { type: 'pageBreak' }, { type: 'paragraph' },
  ])
  assert.equal(state.selection.$head.index(0), 2)

  const withText = schema.nodeFromJSON({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'A' }] }, { type: 'pageBreak' }, { type: 'paragraph', content: [{ type: 'text', text: 'B' }] }] })
  let back = EditorState.create({ doc: withText, schema, selection: TextSelection.create(withText, 5) })
  assert.ok(joinBackward(back, (tr) => { back = back.apply(tr) }))
  assert.deepEqual(back.doc.toJSON().content.map((node) => node.type), ['paragraph', 'paragraph'])

  // A selected break deletes like any node.
  let selected = EditorState.create({ doc: withText, schema, selection: NodeSelection.create(withText, 3) })
  assert.ok(deleteSelection(selected, (tr) => { selected = selected.apply(tr) }))
  assert.equal(selected.doc.childCount, 2)
})

test('page layout is view-only: no doc change, no undo step, no spacer in the saved JSON', async () => {
  const doc = schema.nodeFromJSON({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'One' }] }, { type: 'paragraph', content: [{ type: 'text', text: 'Two' }] }] })
  let state = EditorState.create({ doc, schema, plugins: [history(), paginationPlugin()] })
  const saved = JSON.stringify(state.doc.toJSON())
  state = state.apply(state.tr.setMeta(paginationKey, { geometry: A4 }).setMeta('addToHistory', false))
  assert.deepEqual(paginationKey.getState(state).dirty, { from: 0, to: state.doc.content.size })
  state = state.apply(state.tr.setMeta(paginationKey, { layout: { decorations: paginationKey.getState(state).decorations, pages: 3, stats: null } }).setMeta('addToHistory', false))
  assert.equal(paginationKey.getState(state).pages, 3)
  assert.equal(paginationKey.getState(state).dirty, null)
  assert.equal(JSON.stringify(state.doc.toJSON()), saved)
  assert.equal(undoDepth(state), 0)

  // Typing marks only the edited block dirty, and asks for the cursor to stay in view.
  state = state.apply(state.tr.insertText('!', 9).scrollIntoView())
  assert.deepEqual(paginationKey.getState(state).dirty, { from: 9, to: 10 })
  assert.equal(paginationKey.getState(state).scroll, true)

  // Gaps inside edited blocks are dropped before measuring; block gaps stay.
  const { Decoration, DecorationSet } = await import('@tiptap/pm/view')
  const decorations = DecorationSet.create(state.doc, [
    Decoration.widget(5, () => null, { gap: { index: 1, height: 10, page: 1 } }),
    Decoration.widget(8, () => null, { gap: { index: 1, pos: 8, height: 10, page: 1 } }),
  ])
  state = state.apply(state.tr.setMeta(paginationKey, { layout: { decorations, pages: 2, stats: null } }))
  assert.equal(paginationKey.getState(state).scroll, false)
  state = state.apply(state.tr.setMeta(paginationKey, { strip: { from: 5, to: 11 } }))
  assert.deepEqual(paginationKey.getState(state).decorations.find().map((item) => item.from), [5])
  // Pageless drops everything.
  state = state.apply(state.tr.setMeta(paginationKey, { geometry: null }))
  assert.equal(paginationKey.getState(state).geometry, null)
  assert.equal(paginationKey.getState(state).pages, 1)
})

test('the changed range covers text, structure and mark edits, and nothing for selection moves', () => {
  const doc = schema.nodeFromJSON({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Hello' }] }, { type: 'paragraph', content: [{ type: 'text', text: 'There' }] }] })
  const state = EditorState.create({ doc, schema })
  assert.deepEqual(changedRange(state.tr.insertText('x', 3)), { from: 3, to: 4 })
  assert.deepEqual(changedRange(state.tr.addMark(8, 11, schema.marks.bold.create())), { from: 8, to: 11 })
  assert.equal(changedRange(state.tr.setSelection(TextSelection.create(doc, 2))), null)
  const split = changedRange(state.tr.split(3))
  assert.ok(split.from <= 3 && split.to >= 5)
})

test('the view mode is remembered per user and survives broken storage', () => {
  const values = new Map()
  const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
  assert.equal(readPageMode(storage, 7), 'pages')
  writePageMode(storage, 7, 'pageless')
  assert.equal(readPageMode(storage, 7), 'pageless')
  assert.equal(readPageMode(storage, 8), 'pages')
  values.set('naseeb-essay-page-mode:9', 'sideways')
  assert.equal(readPageMode(storage, 9), 'pages')
  const broken = { getItem() { throw new Error('denied') }, setItem() { throw new Error('denied') } }
  assert.equal(readPageMode(broken, 7), 'pages')
  assert.doesNotThrow(() => writePageMode(broken, 7, 'pageless'))
  assert.equal(readPageMode(null, 7), 'pages')
})
