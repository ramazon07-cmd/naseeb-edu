import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { EditorContent } from '@tiptap/react'
import { t } from '../i18n.js'
import { pageGeometry, pitch, stackHeight } from './pageLayout.js'
import { paginationKey, relayoutPages, setPageGeometry } from './pagination.js'
import { usePageCount } from './PageControls.jsx'
import './pages.css'

// The sheet the open tab is written on: one continuous sheet (pageless), or
// sheets of paper with "Page N of M" drawn behind the same editor (Pages).
// The editor's DOM stays mounted in the same place in both views.
function EditorPage({ editor, hidden = false, label, paged = false, pageSize = 'a4' }) {
  const frameRef = useRef(null)
  const [zoom, setZoom] = useState(1)
  const pages = usePageCount(editor)
  const geometry = useMemo(() => (paged ? pageGeometry(pageSize) : null), [paged, pageSize])

  // After a switch of view or paper, bring the cursor back into sight once
  // the new layout is on screen. (Runs before the effect below dispatches.)
  const keepCursor = useRef(false)
  const mounted = useRef(false)
  useLayoutEffect(() => {
    if (mounted.current) keepCursor.current = true
    mounted.current = true
  }, [geometry])

  useLayoutEffect(() => { setPageGeometry(editor, geometry) }, [editor, geometry])

  // Like Docs' zoom: in a narrow window the sheets shrink instead of scrolling
  // sideways, so a page always holds the same text.
  useLayoutEffect(() => {
    const column = frameRef.current?.parentElement
    if (!geometry || !column) return undefined
    const fit = () => {
      if (!column.clientWidth) return
      setZoom(Math.min(1, Math.floor((column.clientWidth / geometry.width) * 1000) / 1000))
    }
    fit()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(fit)
    observer?.observe(column)
    return () => observer?.disconnect()
  }, [geometry])

  // Web fonts change line heights when they arrive; a hidden page (history
  // preview) could not be measured, so it is measured again when shown.
  useEffect(() => {
    if (!geometry || !editor) return undefined
    const relayout = () => relayoutPages(editor)
    const fonts = document.fonts
    fonts?.addEventListener?.('loadingdone', relayout)
    return () => fonts?.removeEventListener?.('loadingdone', relayout)
  }, [editor, geometry])
  useEffect(() => { if (geometry && !hidden) relayoutPages(editor) }, [editor, geometry, hidden])

  useEffect(() => {
    if (!editor) return undefined
    let frame = 0
    const onTransaction = ({ transaction }) => {
      const meta = transaction.getMeta(paginationKey)
      if (!keepCursor.current || !meta || !(meta.layout || ('geometry' in meta && !meta.geometry))) return
      keepCursor.current = false
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(() => { if (!editor.isDestroyed) editor.commands.scrollIntoView() })
    }
    editor.on('transaction', onTransaction)
    return () => { editor.off('transaction', onTransaction); window.cancelAnimationFrame(frame) }
  }, [editor])

  const focusEnd = (event) => {
    // Clicking the page margin puts the cursor in the text, like a real document.
    if (event.target === event.currentTarget && editor) { event.preventDefault(); editor.commands.focus('end') }
  }

  const total = geometry ? stackHeight(geometry, pages) : 0
  // The divider's label comes from CSS, so the saved HTML of a page break stays language-neutral.
  const breakLabel = JSON.stringify(t('Page break'))
  return <div ref={frameRef} className={`el-pages-frame${geometry ? '' : ' is-pageless'}`} hidden={hidden}
    style={geometry ? { width: `${geometry.width * zoom}px`, height: `${total * zoom}px`, '--el-break-label': breakLabel } : { '--el-break-label': breakLabel }}>
    <article className={`el-page${geometry ? ' is-paged' : ''}`} hidden={hidden} onMouseDown={focusEnd} aria-label={label} style={geometry ? {
      '--el-page-margin': `${geometry.top}px`, '--el-pages-height': `${total}px`,
      width: `${geometry.width}px`, height: `${total}px`, transform: zoom < 1 ? `scale(${zoom})` : undefined,
    } : undefined}>
      {geometry ? <div className="el-paper-sheets" aria-hidden="true">
        {Array.from({ length: pages }, (_, index) => <div key={index} className="el-paper-sheet" style={{ top: `${index * pitch(geometry)}px`, height: `${geometry.height}px` }}>
          <span className="el-paper-number">{t('Page {n} of {total}', { n: index + 1, total: pages })}</span>
        </div>)}
      </div> : null}
      <EditorContent editor={editor} />
    </article>
  </div>
}

export default memo(EditorPage)
