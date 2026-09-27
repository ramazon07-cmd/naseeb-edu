// Putting a newer version of the document into an open editor without losing
// the student's place: only the top-level blocks that differ are replaced, so
// the cursor (in an untouched paragraph) stays where it is, and the change is
// kept out of undo history (the student didn't make it).
import { normalizeDoc, repairDoc } from './docDelta.js'
import { changedRange } from './docMerge.js'

export const REMOTE_META = 'essayRemoteChange'

// The editor's document as the server would store it (null if it can't be read).
export function editorDoc(editor) {
  if (!editor || editor.isDestroyed) return null
  return normalizeDoc(repairDoc(editor.getJSON()))
}

// -> true when the editor changed.
export function applyDocChanges(editor, nextDoc) {
  if (!editor || editor.isDestroyed || !nextDoc) return false
  const current = editorDoc(editor)
  const next = normalizeDoc(nextDoc)
  if (!current || !next) return false
  const { doc } = editor.state
  let range = changedRange(current.content, next.content)
  if (!range) return false
  if (current.content.length !== doc.childCount) range = { from: 0, currentTo: doc.childCount, nextTo: next.content.length }
  let start = 0
  for (let index = 0; index < range.from; index += 1) start += doc.child(index).nodeSize
  let end = start
  for (let index = range.from; index < range.currentTo; index += 1) end += doc.child(index).nodeSize
  const nodes = next.content.slice(range.from, range.nextTo).map((block) => editor.schema.nodeFromJSON(block))
  const tr = editor.state.tr.replaceWith(start, end, nodes)
  tr.setMeta('addToHistory', false).setMeta(REMOTE_META, true)
  editor.view.dispatch(tr)
  return true
}
