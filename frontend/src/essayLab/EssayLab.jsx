import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { t } from '../i18n.js'
import Library from './Library.jsx'
import NewEssay from './NewEssay.jsx'
import { essayLabApi } from './essayLabApi.js'
import { lazyWithRetry } from '../lib/retryableLazy.js'
import './essayLab.css'

// The editor (Tiptap + ProseMirror) is its own chunk; the library preloads it
// when the browser is idle so opening an essay feels instant.
const loadEditor = () => import('./Editor.jsx')
const EditorScreen = lazyWithRetry(loadEditor)

// The open essay is part of the URL (/essay-lab/essays/42): it survives a
// reload, a reopened tab and back/forward. Someone else's essay id gets the
// editor's normal 404, since the API only returns the signed-in student's.
export default function EssayLab({ user, notify = () => {}, essayId = null, onEssay = () => {} }) {
  // Options that only apply right after opening (panel, focus, a new essay).
  const [openOptions, setOpenOptions] = useState(null)
  const view = essayId ? { name: 'editor', id: essayId, ...(openOptions?.id === essayId ? openOptions : {}) } : { name: 'library' }
  const [essays, setEssays] = useState([])
  const [folders, setFolders] = useState([])
  const [status, setStatus] = useState({ loading: true, error: '' })
  const [newEssay, setNewEssay] = useState(null) // null | { folder }
  const loadedOnce = useRef(false)

  const refresh = useCallback(async () => {
    setStatus((current) => ({ loading: !loadedOnce.current || current.loading, error: '' }))
    try {
      const [essayList, folderList] = await Promise.all([essayLabApi.listEssays({ trashed: 0 }), essayLabApi.folders()])
      setEssays(Array.isArray(essayList) ? essayList : [])
      setFolders(Array.isArray(folderList) ? folderList : [])
      loadedOnce.current = true
      setStatus({ loading: false, error: '' })
    } catch (error) {
      setStatus({ loading: false, error: error?.message || t('Unable to load your essays.') })
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // Back in the library, by the back button or browser history: reload the list.
  const previousEssay = useRef(essayId)
  useEffect(() => {
    if (previousEssay.current && !essayId) {
      setOpenOptions(null)
      refresh()
    }
    previousEssay.current = essayId
  }, [essayId, refresh])

  useEffect(() => {
    if (view.name !== 'library') return undefined
    const idle = window.requestIdleCallback || ((fn) => window.setTimeout(fn, 1200))
    const cancel = window.cancelIdleCallback || window.clearTimeout
    const handle = idle(() => { loadEditor().catch(() => {}) })
    return () => cancel(handle)
  }, [view.name])

  const openEssay = useCallback((id, options = {}) => {
    setOpenOptions({ ...options, id })
    onEssay(id)
  }, [onEssay])

  const closeEditor = useCallback((summary) => {
    if (summary?.id) setEssays((list) => list.map((item) => (item.id === summary.id ? { ...item, ...summary } : item)))
    onEssay(null)
  }, [onEssay])

  const created = useCallback((essay) => {
    setNewEssay(null)
    setEssays((list) => [essay, ...list.filter((item) => item.id !== essay.id)])
    openEssay(essay.id, { fresh: true })
  }, [openEssay])

  return <div className="essay-lab">
    {view.name === 'editor'
      ? <Suspense fallback={<div className="el-editor-loading" role="status">{t('Opening your essay…')}</div>}>
        <EditorScreen key={view.id} essayId={view.id} user={user} folders={folders} notify={notify}
          initialPanel={view.panel} initialFocus={view.focus} fresh={view.fresh}
          onClose={closeEditor} onFoldersChanged={setFolders} />
      </Suspense>
      : <Library user={user} essays={essays} folders={folders} loading={status.loading} error={status.error}
        setEssays={setEssays} setFolders={setFolders} refresh={refresh} notify={notify}
        onOpen={openEssay} onNew={(folder = null) => setNewEssay({ folder })} />}
    {newEssay && <NewEssay folders={folders} defaultFolder={newEssay.folder} onClose={() => setNewEssay(null)} onCreated={created} notify={notify} />}
  </div>
}
