import { memo, useCallback, useEffect, useState } from 'react'
import { FilePlus2, FileText, Settings2 } from 'lucide-react'
import { t } from '../i18n.js'
import { Dialog, Menu } from './ui.jsx'
import { essayLabApi } from './essayLabApi.js'
import { normalizePageSize, readPageMode, writePageMode } from './pageLayout.js'
import { pageCount } from './pagination.js'
import './pages.css'

function safeStorage() {
  try { return window.localStorage } catch { return null }
}

// The student's view choice (per user, this device). Phones always write pageless.
export function usePageMode(userId, phone) {
  const [mode, setModeState] = useState(() => readPageMode(safeStorage(), userId))
  const setMode = useCallback((next) => {
    setModeState(next)
    writePageMode(safeStorage(), userId, next)
  }, [userId])
  return { mode, setMode, paged: mode === 'pages' && !phone }
}

// Sheets in the open tab's Pages view (1 in pageless view).
export function usePageCount(editor) {
  const [pages, setPages] = useState(() => pageCount(editor))
  useEffect(() => {
    if (!editor) return undefined
    const update = () => setPages(pageCount(editor))
    update()
    editor.on('transaction', update)
    return () => editor.off('transaction', update)
  }, [editor])
  return pages
}

// Header controls: Pages / Pageless, a blank page and page setup (desktop).
export const PageControls = memo(function PageControls({ editor, mode, onModeChange, essay, onEssayChange, notify, disabled = false }) {
  const [setupOpen, setSetupOpen] = useState(false)
  const choose = (next) => {
    if (next === mode) return
    onModeChange(next)
    editor?.view.focus()
  }
  return <div className="el-page-controls">
    <div className="el-page-mode" role="group" aria-label={t('Page layout')}>
      {[['pages', t('Pages')], ['pageless', t('Pageless')]].map(([value, text]) => <button key={value} type="button" aria-pressed={mode === value}
        className={mode === value ? 'is-on' : ''} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(value)}>{text}</button>)}
    </div>
    <Menu label={t('Page options')} icon={<FileText size={19} />} items={[
      { label: t('Add blank page'), icon: <FilePlus2 size={15} />, disabled, onSelect: () => editor?.chain().focus().addBlankPage().run() },
      { divider: true },
      { label: t('Page setup…'), icon: <Settings2 size={15} />, onSelect: () => setSetupOpen(true) },
    ]} />
    {setupOpen && <PageSetup essay={essay} notify={notify} onClose={() => setSetupOpen(false)}
      onSaved={(saved) => { setSetupOpen(false); onEssayChange(saved) }} />}
  </div>
})

// Items for the phone "More options" menu (phones always write pageless).
export function pageMenuItems(editor, disabled = false) {
  return [{ label: t('Add blank page'), icon: <FilePlus2 size={15} />, disabled, onSelect: () => editor?.chain().focus().addBlankPage().run() }]
}

const PAPER_CHOICES = [
  { id: 'a4', name: 'A4', hint: '210 × 297 mm' },
  { id: 'letter', name: 'US Letter', hint: '8.5 × 11 in' },
]

// Paper size, stored with the document.
export function PageSetup({ essay, onClose, onSaved, notify }) {
  const [size, setSize] = useState(normalizePageSize(essay.page_size))
  const [saving, setSaving] = useState(false)
  const submit = async (event) => {
    event.preventDefault()
    if (size === normalizePageSize(essay.page_size)) { onClose(); return }
    setSaving(true)
    try {
      const saved = await essayLabApi.updateEssay(essay.id, { page_size: size })
      onSaved({ page_size: saved?.page_size || size })
    } catch (error) {
      setSaving(false)
      notify?.(error?.message || t('Could not change the page setup.'), 'error')
    }
  }
  return <Dialog title={t('Page setup')} onClose={onClose} className="el-page-setup" footer={<>
    <button type="button" className="el-btn" onClick={onClose}>{t('Cancel')}</button>
    <button type="submit" form="el-page-setup" className="el-btn is-primary" disabled={saving} aria-busy={saving}>{t('Apply')}</button>
  </>}>
    <form id="el-page-setup" className="el-form" onSubmit={submit}>
      <fieldset className="el-field">
        <legend className="el-label">{t('Paper size')}</legend>
        <div className="el-radio-list">
          {PAPER_CHOICES.map((choice) => <label key={choice.id} className={`el-radio${size === choice.id ? ' is-on' : ''}`}>
            <input type="radio" name="el-paper" checked={size === choice.id} onChange={() => setSize(choice.id)} data-autofocus={size === choice.id ? '' : undefined} />
            <span>{choice.id === 'a4' ? choice.name : t('US Letter')} <span className="el-page-setup-hint">{choice.hint}</span></span>
          </label>)}
        </div>
      </fieldset>
      <p className="el-page-setup-note">{t('Applies to this document in the Pages view, on every device.')}</p>
    </form>
  </Dialog>
}
