import { forwardRef, memo, useImperativeHandle, useMemo, useRef } from 'react'
import { t } from '../i18n.js'
import { LETTER_MAX_CHARS, mirrorSegments, noteAt } from './letterModel.js'

// A plain textarea over a mirror: the mirror renders the same text (same font, padding and wrapping)
// with the notes' sentences underlined; the textarea on top is transparent, so the caret, selection,
// IME and spell check stay the browser's own. The mirror sets the height and the textarea fills it
// (no inner scrolling), so the page scrolls and nothing needs scroll syncing.
const Mirror = memo(function Mirror({ body, marks, activeId }) {
  const segments = useMemo(() => mirrorSegments(body, marks, activeId), [body, marks, activeId])
  return <div className="lw-mirror" aria-hidden="true" dir="auto">
    {segments.map((segment) => (segment.ids.length
      ? <mark key={segment.from} data-note={segment.ids.join(' ')} className={`lw-hl is-${segment.criterion}${segment.active ? ' is-active' : ''}`}>{segment.text}</mark>
      : <span key={segment.from}>{segment.text}</span>))}
    {/* A trailing newline needs a character to keep the last empty line's height. */}
    {'\n'}&#8203;
  </div>
})

export const LetterSheet = forwardRef(function LetterSheet({ body, onBody, marks, activeId, located, onNoteClick, header, readOnly = false }, ref) {
  const area = useRef(null)
  const wrap = useRef(null)

  useImperativeHandle(ref, () => ({
    selection: () => (area.current ? [area.current.selectionStart, area.current.selectionEnd] : [body.length, body.length]),
    // Puts the caret at `position` (after an insert) once the new text is rendered.
    caretTo: (position) => window.requestAnimationFrame(() => {
      area.current?.focus({ preventScroll: true })
      area.current?.setSelectionRange(position, position)
    }),
    // Selects a sentence and brings it into view.
    reveal: (range, id) => {
      const node = area.current
      if (!node || !range) return
      node.focus({ preventScroll: true })
      node.setSelectionRange(range.from, range.to)
      window.requestAnimationFrame(() => {
        const mark = [...(wrap.current?.querySelectorAll('mark[data-note]') || [])].find((item) => item.dataset.note.split(' ').includes(String(id)))
        mark?.scrollIntoView({ block: 'center', behavior: 'smooth' })
      })
    },
  }), [body.length])

  // A click inside an underlined sentence selects its card.
  const click = (event) => {
    const offset = event.currentTarget.selectionStart
    if (offset !== event.currentTarget.selectionEnd) return
    const id = noteAt(located, offset, activeId)
    if (id) onNoteClick(id)
  }

  return <div className="lw-sheet-wrap" ref={wrap}>
    <article className="lw-sheet">
      {header}
      <div className="lw-text">
        <Mirror body={body} marks={marks} activeId={activeId} />
        <textarea ref={area} className="lw-area" value={body} dir="auto" maxLength={LETTER_MAX_CHARS} readOnly={readOnly} spellCheck
          aria-label={t('Letter')} placeholder={t('Write the letter here. Ideas from the profile appear on the right.')}
          onChange={(event) => onBody(event.target.value)} onClick={click} />
      </div>
    </article>
  </div>
})
