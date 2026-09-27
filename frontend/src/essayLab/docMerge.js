// Blocks addressed by id: autosave ops v2 and the per-paragraph merge.
//
// Every top-level block carries a stable id (attrs.bid, see docDelta.js
// ensureBids and the editor's BlockIds extension). A save then says which
// blocks changed and what each looked like before (sha256 of its canonical
// JSON), so the server can merge it with changes other people made to other
// paragraphs since (doc.py apply_ops_v2). Only an edit to the same paragraph
// is a conflict.
//
//   {del: bid, base: hash}                 remove the block
//   {set: bid, base: hash, block}          replace the block
//   {ins: block, after: bid | null}        insert after that block (null: first)
//
// mergeBlocks() is the same idea on the client: the editor's text, the version
// it started from and a newer server version -> one document.
// Framework-free: runs in the browser and under plain `node`.

import { blockId, canonicalJson, sha256Ascii } from './docDelta.js'

export const blockHash = (block) => sha256Ascii(canonicalJson(block))

// Ids of the blocks, or null when one is missing or repeated (then v2 can't be used).
export function blockIds(blocks) {
  const ids = []
  const seen = new Set()
  for (const block of blocks || []) {
    const bid = blockId(block)
    if (typeof bid !== 'string' || seen.has(bid)) return null
    seen.add(bid)
    ids.push(bid)
  }
  return ids
}

// Longest increasing subsequence of `values` -> Set of the indexes in it.
function longestIncreasing(values) {
  const tails = []
  const previous = new Array(values.length).fill(-1)
  for (let i = 0; i < values.length; i += 1) {
    let lo = 0
    let hi = tails.length
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (values[tails[mid]] < values[i]) lo = mid + 1
      else hi = mid
    }
    if (lo > 0) previous[i] = tails[lo - 1]
    tails[lo] = i
  }
  const kept = new Set()
  for (let i = tails.length ? tails[tails.length - 1] : -1; i !== -1; i = previous[i]) kept.add(i)
  return kept
}

// Ops v2 turning `base` into `next` (both from prepareDoc), or null when a doc lacks ids.
// Blocks that kept their relative order stay; the others are deleted and inserted again.
export function diffBlocksV2(base, next) {
  const baseIds = blockIds(base.doc.content)
  const nextIds = blockIds(next.doc.content)
  if (!baseIds || !nextIds) return null
  const baseIndex = new Map(baseIds.map((id, index) => [id, index]))
  const common = nextIds.filter((id) => baseIndex.has(id))
  const inOrder = longestIncreasing(common.map((id) => baseIndex.get(id)))
  const kept = new Set(common.filter((_id, index) => inOrder.has(index)))
  const ops = []
  baseIds.forEach((id, index) => {
    if (!kept.has(id)) ops.push({ del: id, base: sha256Ascii(base.blocks[index]) })
  })
  nextIds.forEach((id, index) => {
    if (!kept.has(id)) return
    const before = base.blocks[baseIndex.get(id)]
    if (before !== next.blocks[index]) ops.push({ set: id, base: sha256Ascii(before), block: next.doc.content[index] })
  })
  nextIds.forEach((id, index) => {
    if (!kept.has(id)) ops.push({ ins: next.doc.content[index], after: index ? nextIds[index - 1] : null })
  })
  return ops
}

export class BlockConflict extends Error {
  constructor(bids) {
    super('block conflict')
    this.bids = bids
  }
}

// Mirror of doc.py apply_ops_v2 (tests use it to check both sides agree).
export function applyOpsV2(blocks, ops) {
  const result = [...blocks]
  const conflicts = []
  const find = (bid) => result.findIndex((block) => blockId(block) === bid)
  for (const op of ops) {
    if ('ins' in op) {
      if (find(blockId(op.ins)) !== -1) throw new Error('inserted block needs a new id')
      if (op.after == null) { result.unshift(op.ins); continue }
      const anchor = find(op.after)
      if (anchor === -1) { conflicts.push(op.after); continue }
      result.splice(anchor + 1, 0, op.ins)
      continue
    }
    const bid = 'del' in op ? op.del : op.set
    const index = find(bid)
    if (index === -1 || blockHash(result[index]) !== op.base) { conflicts.push(bid); continue }
    if ('del' in op) result.splice(index, 1)
    else result[index] = op.block
  }
  if (conflicts.length) throw new BlockConflict([...new Set(conflicts)].sort())
  return result
}

// Three-way merge of top-level blocks by id: `local` (the editor) and `server`
// both started from `base`. A block only one side changed takes that side's
// version; a block both changed differently keeps the local one and is listed
// in `conflicts`. Order follows the server; blocks new on this device go after
// the block they follow here. -> { doc, conflicts } or null when a doc lacks ids.
export function mergeBlocks(base, local, server) {
  const baseBlocks = base?.content || []
  const localBlocks = local?.content || []
  const serverBlocks = server?.content || []
  const baseIds = blockIds(baseBlocks)
  const localIds = blockIds(localBlocks)
  const serverIds = blockIds(serverBlocks)
  if (!baseIds || !localIds || !serverIds) return null
  const json = (blocks, ids) => new Map(ids.map((id, index) => [id, canonicalJson(blocks[index])]))
  const B = json(baseBlocks, baseIds)
  const L = json(localBlocks, localIds)
  const S = json(serverBlocks, serverIds)
  const localById = new Map(localIds.map((id, index) => [id, localBlocks[index]]))
  const conflicts = []
  const content = []
  for (let index = 0; index < serverIds.length; index += 1) {
    const id = serverIds[index]
    const s = S.get(id)
    if (!B.has(id)) { content.push(serverBlocks[index]); continue } // new on the server
    const b = B.get(id)
    if (!L.has(id)) {
      // Deleted here: stays deleted; if the server changed it meanwhile, say so.
      if (s !== b) conflicts.push(id)
      continue
    }
    const l = L.get(id)
    if (l === b || l === s) content.push(l === b ? serverBlocks[index] : localById.get(id))
    else if (s === b) content.push(localById.get(id))
    else {
      // Both changed. When the server only added comment / suggestion marks, they move onto the local text.
      const moved = transplantMarks(baseBlocks[baseIds.indexOf(id)], localById.get(id), serverBlocks[index])
      if (moved) content.push(moved)
      else { conflicts.push(id); content.push(localById.get(id)) }
    }
  }
  // Changed here but deleted on the server: kept (the local edit wins).
  const placed = new Set(content.map(blockId))
  localIds.forEach((id, index) => {
    if (placed.has(id)) return
    const isNew = !B.has(id)
    if (!isNew) {
      if (L.get(id) === B.get(id)) return // deleted on the server, untouched here
      conflicts.push(id)
    }
    let at = 0
    for (let back = index - 1; back >= 0; back -= 1) {
      const anchor = content.findIndex((block) => blockId(block) === localIds[back])
      if (anchor !== -1) { at = anchor + 1; break }
    }
    content.splice(at, 0, localBlocks[index])
    placed.add(id)
  })
  return { doc: { ...server, type: 'doc', content }, conflicts }
}

// The smallest block range to swap to turn `current` into `next` (top-level
// blocks compared by canonical JSON): blocks [from, currentTo) of `current`
// become blocks [from, nextTo) of `next`. Null when they are equal.
export function changedRange(current, next) {
  const a = current.map(canonicalJson)
  const b = next.map(canonicalJson)
  let from = 0
  while (from < a.length && from < b.length && a[from] === b[from]) from += 1
  if (from === a.length && from === b.length) return null
  let endA = a.length
  let endB = b.length
  while (endA > from && endB > from && a[endA - 1] === b[endB - 1]) { endA -= 1; endB -= 1 }
  return { from, currentTo: endA, nextTo: endB }
}

// --- moving feedback marks onto edited text ------------------------------------

const TEXT_BLOCK_TYPES = new Set(['paragraph', 'heading', 'title', 'subtitle'])
const COLLAB = ['comment', 'suggestInsert', 'suggestDelete']
const collabRank = (mark) => COLLAB.indexOf(mark?.type) + 1
const isCollab = (mark) => COLLAB.includes(mark?.type)

// Text of a plain text block (a hard break counts as one character), or null for anything else.
function flatText(block) {
  if (!block || !TEXT_BLOCK_TYPES.has(block.type)) return null
  let text = ''
  for (const node of block.content || []) {
    if (node.type === 'text') text += node.text
    else if (node.type === 'hardBreak') text += '\n'
    else return null
  }
  return text
}

const withoutCollab = (block) => joinText({
  ...block,
  content: (block.content || []).map((node) => {
    if (node.type !== 'text' || !node.marks?.some(isCollab)) return node
    const marks = node.marks.filter((mark) => !isCollab(mark))
    const { marks: _marks, ...rest } = node
    return marks.length ? { ...rest, marks } : rest
  }),
})

// Neighbouring text with the same marks is one node (as the editor keeps it).
function joinText(block) {
  const joined = []
  for (const node of block.content || []) {
    const last = joined[joined.length - 1]
    if (last && last.type === 'text' && node.type === 'text' && canonicalJson(last.marks || null) === canonicalJson(node.marks || null)) {
      joined[joined.length - 1] = { ...last, text: last.text + node.text }
    } else joined.push(node)
  }
  return { ...block, content: joined }
}

// [{ from, to, mark }] of the collaboration marks in a text block.
function collabRanges(block) {
  const ranges = []
  let at = 0
  for (const node of block.content || []) {
    const length = node.type === 'text' ? node.text.length : 1
    for (const mark of node.marks || []) if (isCollab(mark)) ranges.push({ from: at, to: at + length, mark })
    at += length
  }
  return ranges
}

function addMark(block, from, to, mark) {
  const content = []
  let at = 0
  for (const node of block.content || []) {
    const length = node.type === 'text' ? node.text.length : 1
    const start = at
    at += length
    if (node.type !== 'text' || at <= from || start >= to) { content.push(node); continue }
    const cutFrom = Math.max(from, start) - start
    const cutTo = Math.min(to, at) - start
    const piece = (text, marks) => (marks?.length ? { ...node, text, marks } : (({ marks: _m, ...rest }) => ({ ...rest, text }))(node))
    if (cutFrom > 0) content.push(piece(node.text.slice(0, cutFrom), node.marks))
    const key = (item) => (item.type === 'comment' ? `comment:${item.attrs?.id}` : item.type)
    const marks = [...(node.marks || []).filter((item) => key(item) !== key(mark)), mark]
      .map((item, order) => ({ item, order }))
      .sort((a, b) => collabRank(a.item) - collabRank(b.item) || a.order - b.order)
      .map(({ item }) => item)
    content.push(piece(node.text.slice(cutFrom, cutTo), marks))
    if (cutTo < length) content.push(piece(node.text.slice(cutTo), node.marks))
  }
  return joinText({ ...block, content })
}

// When the server's version of a block is the base plus comment / suggestion
// marks only (a counselor commented on the paragraph the student is editing),
// the local block with those marks moved onto the edited text. Null when the
// server changed anything else (then the paragraph is a real conflict).
export function transplantMarks(base, local, server) {
  const baseText = flatText(base)
  const localText = flatText(local)
  if (baseText == null || localText == null || flatText(server) !== baseText) return null
  if (canonicalJson(withoutCollab(server)) !== canonicalJson(withoutCollab(base))) return null
  const known = new Set(collabRanges(base).map((range) => canonicalJson(range.mark)))
  const added = collabRanges(server).filter((range) => !known.has(canonicalJson(range.mark)))
  // Map base offsets onto the local text through the common prefix and suffix.
  let prefix = 0
  while (prefix < baseText.length && prefix < localText.length && baseText[prefix] === localText[prefix]) prefix += 1
  let suffix = 0
  while (suffix < baseText.length - prefix && suffix < localText.length - prefix
    && baseText[baseText.length - 1 - suffix] === localText[localText.length - 1 - suffix]) suffix += 1
  const map = (offset) => {
    if (offset <= prefix) return offset
    if (offset >= baseText.length - suffix) return offset + localText.length - baseText.length
    return null // inside the rewritten part
  }
  let result = local
  for (const range of added) {
    const from = map(range.from)
    const to = map(range.to)
    if (from == null || to == null || to <= from) continue
    result = addMark(result, from, to, range.mark)
  }
  return result
}
