import { memo, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Placeholder from '@tiptap/extension-placeholder'
import '@fontsource-variable/newsreader/wght.css'
import '@fontsource-variable/newsreader/wght-italic.css'
import {
  AlertTriangle, ArrowLeft, Check, CloudOff, Eye, History as HistoryIcon, Maximize2, MoreHorizontal, PanelLeft, PenLine, RotateCcw,
  Settings2, Sparkles,
} from 'lucide-react'
import { t, tp } from '../i18n.js'
import { registerBeforeLogout } from '../api.js'
import Toolbar, { CompactToolbar } from './Toolbar.jsx'
import NewEssay from './NewEssay.jsx'
import CoachPanel from './CoachPanel.jsx'
import History, { DocPreview } from './History.jsx'
import { TabsRail, TabsSheet, TabsSheetButton } from './TabsRail.jsx'
import Counter from './Counter.jsx'
import { documentStats, readCounter, writeCounter } from './counts.js'
import { Dialog, Menu } from './ui.jsx'
import EditorPage from './EditorPage.jsx'
import ShareControl from './ShareControl.jsx'
import { PageControls, pageMenuItems, usePageCount, usePageMode } from './PageControls.jsx'
import { Pagination } from './pagination.js'
import {
  CoachHighlights, DashBulletList, EssayShortcuts, FocusBlock, noteRange, setActiveNote, setBlockMode, setCoachNotes,
} from './extensions.js'
import { BlockFormat, EssayDocument, Highlight, PageBreak, Subtitle, TextStyle, Title } from './formatting.js'
import { isAllowedHref } from './docDelta.js'
import { loadFontsIn } from './fonts.js'
import { errorCode, essayLabApi, essayTypeName } from './essayLabApi.js'
import { deriveText, docFromText } from './docText.js'
import { checkpointDate, relativeTime, whenWritten } from './format.js'
import {
  createSessionRegistry, createTabSession, discardLocalDraft, keepLocalDraft, saveProblem, syncTabs, unsavedTabs,
} from './sessions.js'
import { createTabOpener } from './tabsModel.js'

const STATS_DEBOUNCE_MS = 250
const WELCOME_AFTER_MS = 30 * 60 * 1000

function safeStorage() {
  try {
    const storage = window.localStorage
    storage.getItem('naseeb-essay-probe')
    return storage
  } catch {
    return null
  }
}

function readSetting(key, fallback) {
  try {
    const value = window.localStorage.getItem(key)
    return value == null ? fallback : JSON.parse(value)
  } catch {
    return fallback
  }
}

function writeSetting(key, value) {
  try { window.localStorage.setItem(key, JSON.stringify(value)) } catch { /* a per-device convenience only */ }
}

// A remembered per-user choice (view mode, tabs rail…).
function useSetting(key, fallback) {
  const [value, setValue] = useState(() => readSetting(key, fallback))
  const update = useCallback((next) => setValue((current) => {
    const resolved = typeof next === 'function' ? next(current) : next
    writeSetting(key, resolved)
    return resolved
  }), [key])
  return [value, update]
}

function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => typeof window !== 'undefined' && Boolean(window.matchMedia?.(query).matches))
  useEffect(() => {
    const list = window.matchMedia?.(query)
    if (!list) return undefined
    const update = () => setMatches(list.matches)
    update()
    list.addEventListener?.('change', update)
    return () => list.removeEventListener?.('change', update)
  }, [query])
  return matches
}

const tabKey = (userId, essayId) => `naseeb-essay-tab:${userId ?? 'me'}:${essayId}`

// Loads the document (every tab's metadata and the last open tab), then mounts the editor.
export default function EditorScreen(props) {
  const { essayId, onClose, user } = props
  const [state, setState] = useState({ loading: true, error: '', essay: null })

  const load = useCallback(async () => {
    setState({ loading: true, error: '', essay: null })
    try {
      const essay = await essayLabApi.getEssay(essayId, readSetting(tabKey(user?.id, essayId), null) ?? undefined)
      setState({ loading: false, error: '', essay })
    } catch (error) {
      setState({ loading: false, error: error?.message || t('Could not open this essay.'), essay: null, status: error?.status })
    }
  }, [essayId, user?.id])

  useEffect(() => { load() }, [load])

  if (state.loading) return <div className="el-editor-shell is-loading" role="status"><div className="el-page is-skeleton" /><span className="el-sr-only">{t('Opening your essay…')}</span></div>
  if (!state.essay) {
    return <div className="el-editor-shell is-loading">
      <div className="el-alert is-error" role="alert">
        <span>{state.status === 404 ? t('This essay no longer exists.') : state.error}</span>
        {state.status !== 404 && <button type="button" className="el-btn is-small" onClick={load}>{t('Retry')}</button>}
        <button type="button" className="el-btn is-small" onClick={() => onClose()}>{t('Back to my essays')}</button>
      </div>
    </div>
  }
  return <DocumentEditor {...props} initial={state.essay} />
}

function useLatest(value) {
  const ref = useRef(value)
  ref.current = value
  return ref
}

const useSessionState = (session) => useSyncExternalStore(
  useCallback((listener) => (session ? session.subscribe(listener) : () => {}), [session]),
  () => session?.state ?? null,
)

const wideScreen = () => typeof window !== 'undefined' && window.matchMedia?.('(min-width: 1100px)').matches

function summaryOf(detail) {
  const { tabs: _tabs, tab: _tab, ...essay } = detail
  return essay
}

// The open document: header, formatting toolbar, tabs rail and the open tab.
function DocumentEditor({ initial, user, folders, notify, initialFocus, initialPanel, fresh, onClose }) {
  const storage = useMemo(safeStorage, [])
  const userId = user?.id ?? 'me'
  const [essay, setEssay] = useState(() => summaryOf(initial))
  const [tabs, setTabs] = useState(initial.tabs)
  const [activeId, setActiveId] = useState(initial.tab.id)
  const [editor, setEditor] = useState(null)
  const [panel, setPanel] = useState(() => initialPanel || (initial.essay_type !== 'free_writing' && wideScreen() ? 'coach' : null))
  const [focusMode, setFocusMode] = useState(Boolean(initialFocus))
  const [railOpen, setRailOpen] = useSetting(`naseeb-essay-tabs-rail:${userId}`, true)
  const [counter, setCounter] = useState(readCounter)
  const [live, setLive] = useState(() => ({ tab: initial.tab.id, ...deriveText(initial.tab.doc) }))
  const [outline, setOutline] = useState([])
  const [coach, setCoach] = useState({ count: 0, checked: false })
  const [dialog, setDialog] = useState(null)
  const [tabsSheet, setTabsSheet] = useState(false)
  const [busy, setBusy] = useState(false)
  const [switching, setSwitching] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const [leaving, setLeaving] = useState(null) // 'saving' | { ids } of tabs that did not save
  const phone = useMediaQuery('(max-width: 820px)')
  const pageMode = usePageMode(userId, phone)
  const pageTotal = usePageCount(editor)
  const essayRef = useLatest(essay)
  const shellRef = useRef(null)

  // Phones: keep the compact toolbar above the on-screen keyboard.
  useEffect(() => {
    const viewport = window.visualViewport
    if (!phone || !viewport) return undefined
    const update = () => {
      const covered = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop)
      shellRef.current?.style.setProperty('--el-keyboard', `${Math.round(covered)}px`)
    }
    viewport.addEventListener('resize', update)
    viewport.addEventListener('scroll', update)
    update()
    return () => {
      viewport.removeEventListener('resize', update)
      viewport.removeEventListener('scroll', update)
    }
  }, [phone])

  const onSaved = useCallback((tabId, response) => {
    setTabs((list) => list.map((tab) => (tab.id === tabId ? {
      ...tab,
      word_count: response.word_count ?? tab.word_count,
      char_count: response.char_count ?? tab.char_count,
      char_count_no_spaces: response.char_count_no_spaces ?? tab.char_count_no_spaces,
      save_seq: response.save_seq ?? tab.save_seq,
    } : tab)))
    setEssay((current) => ({
      ...current,
      word_count: response.document_word_count ?? current.word_count,
      last_edited_at: response.saved_at || current.last_edited_at,
    }))
  }, [])
  // One save session per tab opened in this visit (see sessions.js).
  const [sessions] = useState(() => createSessionRegistry((tab, { adoptLegacyDraft }) => createTabSession({
    essayId: essayRef.current.id,
    tab,
    userId,
    storage,
    send: (payload, options) => essayLabApi.autosave(essayRef.current.id, payload, options),
    adoptLegacyDraft,
    isOnline: () => navigator.onLine !== false,
    onSaved,
  })))
  const [initialSession] = useState(() => sessions.open(initial.tab))
  // Null while no live tab is open (the open tab was just deleted).
  const session = sessions.get(activeId) ?? null
  const sessionState = useSessionState(session)
  useSyncExternalStore(sessions.subscribe, sessions.version)
  const unsaved = unsavedTabs(sessions.all())

  useEffect(() => { writeSetting(tabKey(userId, essay.id), activeId) }, [userId, essay.id, activeId])

  // A tab in the background that stops saving (conflict, rejected text) says
  // so once; the open tab shows its own banner.
  const reported = useRef(new Map())
  const tabsForNames = useLatest(tabs)
  const unsavedRef = useLatest(unsaved)
  const problemKey = unsaved.map((item) => `${item.id}:${item.problem}`).join(',')
  useEffect(() => {
    const now = new Map(unsavedRef.current.map((item) => [item.id, item.problem]))
    for (const [id, problem] of now) {
      if (reported.current.get(id) === problem || id === activeId || (problem !== 'conflict' && problem !== 'rejected')) continue
      const name = tabsForNames.current.find((tab) => tab.id === id)?.title || t('Tab')
      notify(t('“{name}” couldn’t be saved. Open the tab to fix it.', { name }), 'error')
    }
    reported.current = now
  }, [problemKey, activeId, notify, tabsForNames, unsavedRef])

  // Sync on page hide, when the connection comes back and before sign-out; stop on leave.
  useEffect(() => {
    const all = () => sessions.all()
    for (const item of all()) item.queue.reopen()
    const onVisibility = () => { if (document.visibilityState === 'hidden') for (const item of all()) item.queue.hide() }
    const onPageHide = () => { for (const item of all()) item.queue.hide() }
    const onOnline = () => { for (const item of all()) item.queue.retryNow() }
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('pagehide', onPageHide)
    window.addEventListener('online', onOnline)
    const unregister = registerBeforeLogout({
      save: () => Promise.all(all().map((item) => item.queue.syncBeforeLogout())).then((results) => results.every(Boolean)),
      forget: () => { for (const item of all()) item.queue.forget() },
    })
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('pagehide', onPageHide)
      window.removeEventListener('online', onOnline)
      unregister()
      for (const item of all()) item.queue.close()
    }
  }, [sessions])

  // Lock the page behind the full-screen editor.
  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previous }
  }, [])

  // --- tabs ------------------------------------------------------------------
  const activeRef = useLatest(activeId)
  const notifyRef = useLatest(notify)
  const [openTab] = useState(() => createTabOpener({
    isOpen: (id) => id === activeRef.current,
    hasSession: (id) => sessions.has(id),
    fetchTab: (id) => essayLabApi.getTab(essayRef.current.id, id),
    openSession: (tab) => sessions.open(tab),
    setLoading: setSwitching,
    show: (id) => {
      setOutline([])
      setActiveId(id)
    },
    fail: (error) => notifyRef.current(error?.message || t('Could not open that tab.'), 'error'),
  }))

  const withBusy = async (action, failure) => {
    setBusy(true)
    try { return await action() } catch (error) { notify(error?.message || t(failure), 'error'); return null } finally { setBusy(false) }
  }

  const addTab = (parent) => withBusy(async () => {
    const response = await essayLabApi.createTab(essay.id, { title: t('Tab {n}', { n: tabs.length + 1 }), parent: parent ?? null })
    setTabs(response.tabs)
    await openTab(response.tab.id, response.tab)
  }, 'Could not add a tab.')

  const renameTab = (tab, title) => withBusy(async () => {
    setTabs((list) => list.map((item) => (item.id === tab.id ? { ...item, title } : item)))
    try {
      await essayLabApi.renameTab(essay.id, tab.id, title)
    } catch (error) {
      setTabs((list) => list.map((item) => (item.id === tab.id ? { ...item, title: tab.title } : item)))
      throw error
    }
  }, 'Could not rename the tab.')

  const duplicateTab = (tab) => withBusy(async () => {
    // Copy what is on the screen, not an older saved version.
    await sessions.get(tab.id)?.queue.flushAndWait().catch(() => {})
    const response = await essayLabApi.duplicateTab(essay.id, tab.id)
    setTabs(response.tabs)
    await openTab(response.tab.id, response.tab)
  }, 'Could not duplicate the tab.')

  const reorderTabs = (parent, ids) => withBusy(async () => {
    const previous = tabs
    setTabs((list) => list.map((item) => ((item.parent ?? null) === parent && ids.includes(item.id) ? { ...item, position: ids.indexOf(item.id) } : item)))
    try {
      setTabs((await essayLabApi.orderTabs(essay.id, parent, ids)).tabs)
    } catch (error) {
      setTabs(previous)
      throw error
    }
  }, 'Could not move the tab.')

  const deleteTab = (tab) => withBusy(async () => {
    const doomed = new Set([tab.id, ...tabs.filter((item) => item.parent === tab.id).map((item) => item.id)])
    const response = await essayLabApi.deleteTab(essay.id, tab.id)
    // Their text is gone on the server: stop saving it and drop local drafts.
    // The deleted tab's editor unmounts on the next render, even if opening
    // another tab fails.
    for (const id of doomed) sessions.remove(id)
    setTabs(response.tabs)
    setEssay((current) => ({ ...current, word_count: response.word_count ?? current.word_count }))
    notify(t('Tab deleted.'))
    if (doomed.has(activeId)) await openTab(response.tabs[0].id)
  }, 'Could not delete the tab.')

  const jumpToHeading = useCallback((item) => {
    if (!editor) return
    const pos = Math.min(item.pos + 1, editor.state.doc.content.size)
    editor.commands.setTextSelection(pos)
    editor.view.focus()
    window.requestAnimationFrame(() => scrollToPos(editor, document.querySelector('.el-canvas'), pos, 0.2))
  }, [editor])

  // --- document settings ----------------------------------------------------
  const saveTitle = async (value) => {
    const title = value.trim().slice(0, 220)
    if (!title || title === essayRef.current.title) return
    setEssay((current) => ({ ...current, title }))
    try {
      const saved = await essayLabApi.updateEssay(essayRef.current.id, { title })
      setEssay((current) => ({ ...current, ...saved }))
    } catch (err) {
      notify(err?.message || t('Could not rename.'), 'error')
    }
  }

  // Saves every tab before leaving; if one can't be saved, the student decides.
  const leave = async () => {
    if (leaving === 'saving') return
    setLeaving('saving')
    const ids = await syncTabs(sessions.all())
    if (ids.length) { setLeaving({ ids }); return }
    onClose({ ...essayRef.current })
  }

  const changeCounter = (next) => { setCounter(next); writeCounter(next) }

  const activeTab = tabs.find((tab) => tab.id === activeId) || tabs[0]
  const titleOf = (id) => tabs.find((tab) => tab.id === id)?.title || t('Tab')
  const stats = documentStats(tabs, activeId, live)
  const unsynced = Boolean(sessionState?.unsynced)
  // No formatting while an unsynced draft waits for a choice or an old version is previewed.
  const locked = unsynced || previewing
  const typeName = t(essayTypeName(essay.essay_type))
  const counterEl = <Counter setting={counter} onChange={changeCounter} tab={stats.tab} document={stats.document}
    pages={pageMode.paged && !focusMode ? pageTotal : 0} limit={essay.word_limit} multipleTabs={tabs.length > 1} />
  // Another tab failing to save outranks the open tab's state: say so and offer a jump.
  const elsewhere = unsaved.filter((item) => item.id !== activeId)
  const saveBadge = elsewhere.length
    ? <UnsavedTabsBadge count={unsaved.length} name={titleOf(elsewhere[0].id)} onOpen={() => openTab(elsewhere[0].id)} compact={phone} />
    : <SaveBadge state={sessionState} onRetry={() => session?.queue.retryNow()} compact={phone} iconOnly={phone} />
  const coachLabel = panel === 'coach' ? t('Hide coach') : coach.checked ? t('Coach') : t('Check depth')
  const coachIdeas = panel !== 'coach' && coach.count > 0 ? (coach.count === 1 ? t('1 idea') : tp('{n} ideas', coach.count, { n: coach.count })) : null
  const moreItems = [
    phone && { label: t('Just write (focus mode)'), icon: <Maximize2 size={15} />, onSelect: () => setFocusMode(true) },
    phone && { label: t('Version history'), icon: <HistoryIcon size={15} />, onSelect: () => setPanel('history') },
    { label: t('Essay details'), icon: <Settings2 size={15} />, onSelect: () => setDialog('details') },
    ...(phone ? pageMenuItems(editor, locked) : []),
  ]

  return <div ref={shellRef} className={`el-editor-shell${focusMode ? ' is-focus' : ''}${panel === 'coach' ? ' is-coach-open' : ''}${railOpen && !phone ? ' has-rail' : ''}`}>
    <header className="el-editor-head">
      <button type="button" className="el-icon-btn" aria-label={t('Back to my essays')} title={t('Back to my essays')} onClick={leave}
        disabled={leaving === 'saving'} aria-busy={leaving === 'saving'}><ArrowLeft size={20} /></button>
      {!phone && <button type="button" className={`el-icon-btn${railOpen ? ' is-on' : ''}`} aria-pressed={railOpen} aria-label={t('Show tabs & outlines')}
        title={t('Show tabs & outlines')} onClick={() => setRailOpen((open) => !open)}><PanelLeft size={19} /></button>}
      {phone
        ? <TabsSheetButton tabs={tabs} activeId={activeId} onOpenSheet={() => setTabsSheet(true)} />
        : <div className="el-head-title">
          <span className="el-head-type">
            {essay.university_name ? `${typeName} · ${essay.university_name}` : typeName}
          </span>
          <TitleInput value={essay.title} onSave={saveTitle} />
        </div>}
      <div className="el-head-status">{saveBadge}</div>
      <div className="el-head-actions">
        <ShareControl essay={essay} notify={notify} onSaved={(saved) => setEssay((current) => ({ ...current, ...saved }))} />
        {!phone && counterEl}
        {!phone && <PageControls editor={editor} mode={pageMode.mode} onModeChange={pageMode.setMode} essay={essay} notify={notify} disabled={locked}
          onEssayChange={(changes) => setEssay((current) => ({ ...current, ...changes }))} />}
        {!phone && <button type="button" className="el-icon-btn" aria-label={t('Just write')} title={t('Just write')} onClick={() => setFocusMode(true)}><Maximize2 size={18} /></button>}
        {!phone && <button type="button" className={`el-icon-btn${panel === 'history' ? ' is-on' : ''}`} aria-label={t('Version history')} title={t('Version history')}
          aria-pressed={panel === 'history'} onClick={() => setPanel((current) => (current === 'history' ? null : 'history'))}><HistoryIcon size={19} /></button>}
        <button type="button" className={`el-btn${panel === 'coach' ? '' : ' is-primary'} el-coach-toggle`} aria-pressed={panel === 'coach'}
          aria-label={coachIdeas ? `${coachLabel}, ${coachIdeas}` : coachLabel} title={coachLabel}
          onClick={() => setPanel((current) => (current === 'coach' ? null : 'coach'))}>
          <Sparkles size={16} aria-hidden="true" /><span className="el-hide-md" aria-hidden="true">{coachLabel}</span>
          {coachIdeas && <span className="el-pill-count" aria-hidden="true">{coach.count}</span>}
        </button>
        <Menu label={t('More options')} icon={<MoreHorizontal size={20} />} items={moreItems} />
      </div>
    </header>

    {!phone && <div className="el-toolbar-bar"><Toolbar editor={editor} disabled={locked} /></div>}

    <div className="el-editor-body">
      {railOpen && !phone && !focusMode && <TabsRail tabs={tabs} activeId={activeId} outline={outline} busy={busy} onOpen={openTab} onAdd={addTab} onRename={renameTab}
        onDuplicate={duplicateTab} onReorder={reorderTabs} onDelete={deleteTab} onOutline={jumpToHeading} />}
      {switching != null
        ? <div className="el-canvas"><div className="el-column"><div className="el-page is-skeleton" role="status"><span className="el-sr-only">{t('Opening the tab…')}</span></div></div></div>
        : !session
          ? <div className="el-canvas"><div className="el-column"><div className="el-alert is-error" role="alert">
            <span>{t('Could not open that tab.')}</span>
            <button type="button" className="el-btn is-small" onClick={() => openTab(activeTab.id)}>{t('Retry')}</button>
          </div></div></div>
          : <TabEditor key={session.id} session={session} essay={essay} tabTitle={activeTab?.title} tabWords={stats.tab.words} user={user} notify={notify}
          focusMode={focusMode} setFocusMode={setFocusMode} panel={panel} setPanel={setPanel} paged={pageMode.paged}
          welcomeBack={session === initialSession && !fresh} fresh={session === initialSession && fresh}
          onEditor={setEditor} onStats={setLive} onOutline={setOutline} onCoach={setCoach} onPreview={setPreviewing} onEditDetails={() => setDialog('details')} />}
    </div>

    {phone && !focusMode && <CompactToolbar editor={editor} disabled={locked} count={counterEl} />}

    {focusMode && <FocusChrome title={tabs.length > 1 && activeTab ? `${essay.title} · ${activeTab.title}` : essay.title} words={stats.tab.words}
      onExit={() => setFocusMode(false)} save={elsewhere.length ? saveBadge : <SaveBadge state={sessionState} onRetry={() => session?.queue.retryNow()} compact />} />}

    {tabsSheet && <TabsSheet tabs={tabs} activeId={activeId} outline={outline} busy={busy} onOpen={openTab} onAdd={addTab} onRename={renameTab}
      onDuplicate={duplicateTab} onReorder={reorderTabs} onDelete={deleteTab} onOutline={jumpToHeading} onClose={() => setTabsSheet(false)} />}

    {leaving && leaving !== 'saving' && <Dialog title={t('Some tabs aren’t saved')} onClose={() => setLeaving(null)} footer={<>
      <button type="button" className="el-btn" data-autofocus onClick={() => setLeaving(null)}>{t('Stay')}</button>
      <button type="button" className="el-btn is-danger-solid" onClick={() => onClose({ ...essayRef.current })}>{t('Leave anyway')}</button>
    </>}>
      <p className="el-dialog-text">{t('Couldn’t save {names}. The text is kept on this device and is saved the next time you open this essay here.', {
        names: leaving.ids.map((id) => `“${titleOf(id)}”`).join(', '),
      })}</p>
    </Dialog>}

    {dialog === 'details' && <NewEssay folders={folders} essay={essay} notify={notify} onClose={() => setDialog(null)}
      onSaved={(saved) => { setDialog(null); setEssay((current) => ({ ...current, ...saved })) }} />}
  </div>
}

// One tab's editor: Tiptap, banners and the Coach / history panels.
function TabEditor({ session, essay, tabTitle, tabWords, user, notify, focusMode, setFocusMode, panel, setPanel, paged, welcomeBack, fresh,
  onEditor, onStats, onOutline, onCoach, onPreview, onEditDetails }) {
  const state = useSessionState(session)
  const [check, setCheck] = useState(null)
  const [checkStatus, setCheckStatus] = useState({ loading: false, error: null })
  const [anchored, setAnchored] = useState(() => new Set())
  const [activeNoteId, setActiveNoteId] = useState(null)
  const [dismissed, setDismissed] = useState(() => new Set())
  const [historyVersion, setHistoryVersion] = useState(0)
  const [preview, setPreview] = useState(null) // { checkpoint, doc }
  const [welcome, setWelcome] = useState(null)
  const activeNoteIdRef = useLatest(activeNoteId)
  const welcomeRef = useLatest(welcome)
  const focusModeRef = useLatest(focusMode)
  const unsyncedRef = useLatest(state.unsynced)
  const statsTimer = useRef(null)
  const canvasRef = useRef(null)
  const editorRef = useRef(null)
  const { queue } = session

  const report = useCallback((current) => {
    const derived = deriveText(current.getJSON())
    onStats({ tab: session.id, ...derived })
    const headings = []
    current.state.doc.forEach((node, offset) => {
      const kind = node.type.name === 'heading' ? `h${node.attrs.level}` : node.type.name === 'title' ? 'title' : null
      const text = kind && node.textContent.trim()
      if (text) headings.push({ pos: offset, kind, text: text.slice(0, 80) })
    })
    onOutline(headings)
    loadFontsIn(current.state.doc)
  }, [onOutline, onStats, session.id])

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        document: false,
        heading: { levels: [1, 2, 3] },
        bulletList: false,
        code: false,
        codeBlock: false,
        horizontalRule: false,
        underline: false,
        link: { openOnClick: false, autolink: true, defaultProtocol: 'https', isAllowedUri: (url) => isAllowedHref(url) },
      }),
      EssayDocument,
      Title,
      Subtitle,
      PageBreak,
      Pagination,
      TextStyle,
      Highlight,
      BlockFormat,
      DashBulletList,
      Underline,
      Placeholder.configure({ placeholder: () => t('Start writing. Everything saves as you go.') }),
      EssayShortcuts.configure({
        onSave: () => queue.flush('manual'),
        onEscape: () => {
          if (!focusModeRef.current) return false
          setFocusMode(false)
          return true
        },
      }),
      FocusBlock,
      CoachHighlights.configure({
        onAnchorsChange: (ids) => setAnchored(ids),
        onNoteClick: (id) => { setActiveNoteId(id); setPanel('coach') },
      }),
    ],
    content: session.doc || docFromText(''),
    editable: !state.unsynced,
    immediatelyRender: true,
    shouldRerenderOnTransaction: false,
    editorProps: {
      attributes: { class: 'el-prose', spellcheck: 'true', 'aria-label': t('Essay text'), 'aria-multiline': 'true', role: 'textbox' },
      scrollThreshold: { top: 80, bottom: 140, left: 0, right: 0 },
      scrollMargin: { top: 80, bottom: 160, left: 0, right: 0 },
    },
    onUpdate: ({ editor: current }) => {
      if (unsyncedRef.current) return
      queue.change()
      if (welcomeRef.current) setWelcome(null)
      window.clearTimeout(statsTimer.current)
      statsTimer.current = window.setTimeout(() => report(current), STATS_DEBOUNCE_MS)
    },
    onBlur: () => queue.flush('blur'),
  })
  editorRef.current = editor

  useEffect(() => {
    if (!editor) return undefined
    session.attach(editor)
    onEditor(editor)
    report(editor)
    return () => {
      window.clearTimeout(statsTimer.current)
      onEditor(null)
      session.detach(editor)
    }
  }, [editor, session, onEditor, report])

  // The live editor is hidden during a history preview: nothing may change it
  // then (toolbar, page menu or shortcuts), or it would autosave.
  const editable = !state.unsynced && !preview
  useEffect(() => { if (editor && editor.isEditable !== editable) editor.setEditable(editable, false) }, [editor, editable])
  useEffect(() => { onPreview(Boolean(preview)) }, [preview, onPreview])
  useEffect(() => () => onPreview(false), [onPreview])

  // --- Coach (reads this tab) ------------------------------------------------
  useEffect(() => {
    let alive = true
    essayLabApi.latestDepthCheck(essay.id, session.id).then((latest) => {
      if (!alive || !latest?.result) return
      setCheck(latest)
      setDismissed(readDismissed(latest.id))
    }, () => {})
    return () => { alive = false }
  }, [essay.id, session.id])

  useEffect(() => {
    if (!editor) return
    const notes = (check?.result?.notes || []).filter((note) => note?.id && note.quote && !dismissed.has(note.id))
    setCoachNotes(editor, notes, activeNoteIdRef.current)
  }, [editor, check, dismissed, activeNoteIdRef])

  useEffect(() => { if (editor) setActiveNote(editor, activeNoteId) }, [editor, activeNoteId])

  const coachCount = (check?.result?.notes || []).filter((note) => anchored.has(note.id) && !dismissed.has(note.id)).length
  useEffect(() => { onCoach({ count: coachCount, checked: Boolean(check) }) }, [coachCount, check, onCoach])

  const runCheck = useCallback(async () => {
    setCheckStatus({ loading: true, error: null })
    setPanel('coach')
    try {
      let result
      for (let attempt = 0; attempt < 2 && !result; attempt += 1) {
        const seq = await queue.flushAndWait()
        try {
          result = await essayLabApi.depthCheck(essay.id, session.id, seq)
        } catch (error) {
          // "stale": a save landed in between (another tab, or a follow-up) — save and retry once.
          if (error?.status !== 409 || attempt === 1) throw error
        }
      }
      setCheck(result)
      setDismissed(readDismissed(result.id))
      setActiveNoteId(null)
      setCheckStatus({ loading: false, error: null })
      setHistoryVersion((value) => value + 1) // the check made a checkpoint
    } catch (error) {
      setCheckStatus({ loading: false, error: { code: errorCode(error) || (error?.status === 409 ? 'stale' : null), message: error?.message } })
    }
  }, [queue, essay.id, session.id, setPanel])

  const selectNote = useCallback((note) => setActiveNoteId(note?.id ?? null), [])

  const jumpToNote = useCallback((note) => {
    const current = editorRef.current
    const range = noteRange(current, note.id)
    setActiveNoteId(note.id)
    if (!current || !range) return
    current.commands.setTextSelection(range)
    current.view.focus()
    window.requestAnimationFrame(() => scrollToPos(current, canvasRef.current, range.from))
  }, [])

  const dismissNote = useCallback((note) => {
    setDismissed((previous) => {
      const next = new Set(previous)
      next.add(note.id)
      if (check?.id) writeDismissed(check.id, next)
      return next
    })
    setActiveNoteId((current) => (current === note.id ? null : current))
  }, [check])

  const closePanel = useCallback(() => setPanel(null), [setPanel])

  const replaceDoc = useCallback((doc, seq) => {
    const current = editorRef.current
    if (!current) return
    current.commands.setContent(doc || docFromText(''), { emitUpdate: false })
    queue.acceptServer(seq, doc)
    session.set({ conflict: null })
    report(current)
  }, [queue, session, report])

  // --- History ---------------------------------------------------------------
  const previewCheckpoint = useCallback(async (checkpoint) => {
    if (!checkpoint) { setPreview(null); return }
    try {
      const detail = await essayLabApi.checkpoint(essay.id, checkpoint.id)
      setPreview({ checkpoint: { ...checkpoint, ...detail }, doc: detail.doc })
      canvasRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (error) {
      notify(error?.message || t('Could not open that version.'), 'error')
    }
  }, [essay.id, notify])

  const restoreCheckpoint = useCallback(async (checkpoint) => {
    if (unsyncedRef.current) { notify(t('First choose which version to keep: yours from this device or the saved one.'), 'error'); return }
    try {
      let seq = await queue.flushAndWait()
      let detail
      try {
        detail = await essayLabApi.restoreCheckpoint(essay.id, checkpoint.id, seq)
      } catch (error) {
        // Someone saved in between; the server keeps the current text as a
        // "restore" checkpoint first, so restoring on top of it loses nothing.
        if (error?.status !== 409 || !Number.isInteger(error.details?.save_seq)) throw error
        seq = error.details.save_seq
        detail = await essayLabApi.restoreCheckpoint(essay.id, checkpoint.id, seq)
      }
      replaceDoc(detail.doc, detail.save_seq)
      session.applySaved({ ...detail, saved_at: detail.last_edited_at })
      setPreview(null)
      setHistoryVersion((value) => value + 1)
      notify(t('Restored the version from {when}. Your previous text is kept in the history.', { when: checkpointDate(checkpoint.created_at) }))
    } catch (error) {
      notify(error?.message || t('Could not restore that version.'), 'error')
    }
  }, [queue, essay.id, replaceDoc, notify, unsyncedRef, session])

  const flushBeforeName = useCallback(() => queue.flushAndWait(), [queue])
  const closeHistory = useCallback(() => { setPanel(null); setPreview(null) }, [setPanel])

  const keepMine = () => {
    const doc = state.unsynced?.doc
    if (!editor || !doc) return
    editor.commands.setContent(doc, { emitUpdate: false })
    keepLocalDraft(session)
    report(editor)
  }

  const keepMineOnConflict = () => {
    const seq = state.conflict?.save_seq
    const serverDoc = state.conflict?.doc
    session.set({ conflict: null })
    if (Number.isInteger(seq)) queue.keepMine(seq, serverDoc)
    else essayLabApi.getTab(essay.id, session.id).then((fresh) => queue.keepMine(fresh.save_seq, fresh.doc), (error) => session.set({ error }))
  }

  const loadLatest = async () => {
    const details = state.conflict
    session.set({ conflict: null })
    try {
      if (details?.doc && Number.isInteger(details.save_seq)) replaceDoc(details.doc, details.save_seq)
      else {
        const fresh = await essayLabApi.getTab(essay.id, session.id)
        replaceDoc(fresh.doc, fresh.save_seq)
      }
    } catch (error) {
      session.set({ conflict: details })
      notify(error?.message || t('Could not load the latest version.'), 'error')
    }
  }

  // Put the cursor back where the student left this tab ("welcome back" on a fresh open).
  const restored = useRef(false)
  useEffect(() => {
    if (!editor || restored.current) return
    restored.current = true
    const size = editor.state.doc.content.size
    const cursor = session.cursor
    if (fresh || cursor == null) {
      editor.commands.focus(fresh ? 'start' : 'end', { scrollIntoView: true })
      return
    }
    const pos = Math.max(1, Math.min(cursor, size - 1))
    try { editor.commands.setTextSelection(pos) } catch { /* the doc changed shape */ }
    editor.view.focus()
    window.requestAnimationFrame(() => scrollToPos(editor, canvasRef.current, pos))
    const lastEdited = Date.parse(state.savedAt || '')
    if (welcomeBack && Number.isFinite(lastEdited) && Date.now() - lastEdited > WELCOME_AFTER_MS) {
      setWelcome({ paragraph: paragraphNumber(editor.state.doc, pos), when: whenWritten(state.savedAt) })
      setBlockMode(editor, { flash: true })
    }
  }, [editor, fresh, session, state.savedAt, welcomeBack])

  // Focus mode: dim everything but the current paragraph; Esc leaves.
  useEffect(() => {
    if (!editor) return undefined
    setBlockMode(editor, { focus: focusMode })
    if (!focusMode) return undefined
    editor.commands.focus()
    const onKey = (event) => { if (event.key === 'Escape') setFocusMode(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [editor, focusMode, setFocusMode])

  const { error: saveError, status: saveStatus } = state
  return <>
    <div className="el-canvas" ref={canvasRef}>
      <div className="el-column">
        {state.unsynced && <div className="el-banner is-warn" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>{t('You have unsynced changes from this device ({when}).', { when: relativeTime(state.unsynced.updated_at) })} {t('Choose one to keep writing.')}</span>
          <button type="button" className="el-btn is-small is-primary" onClick={keepMine}>{t('Keep mine')}</button>
          <button type="button" className="el-btn is-small" onClick={() => discardLocalDraft(session)}>{t('Use saved version')}</button>
        </div>}
        {state.conflict && <div className="el-banner is-warn" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>{t('This essay was changed in another tab or device. Your text is safe here and has not been overwritten.')}</span>
          <button type="button" className="el-btn is-small is-primary" onClick={keepMineOnConflict}>{t('Keep mine')}</button>
          <button type="button" className="el-btn is-small" onClick={loadLatest}>{t('Load latest')}</button>
        </div>}
        {saveProblem(state) === 'rejected' && <div className="el-banner is-warn" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>{t(SAVE_ERRORS[saveError.details?.code] || saveError.message || 'Couldn’t save your latest changes.')}</span>
        </div>}
        {saveStatus === 'expired' && <div className="el-banner is-warn" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>{t('Your session expired. Sign in again to save — your writing is kept on this device.')}</span>
        </div>}
        {state.storageWarning && <div className="el-banner is-info" role="status">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>{t('This browser’s storage is full, so changes are only saved when you are online.')}</span>
          <button type="button" className="el-btn is-small" onClick={() => session.set({ storageWarning: false })}>{t('OK')}</button>
        </div>}
        {welcome && <div className="el-welcome" role="status">
          <PenLine size={20} aria-hidden="true" />
          <div>
            <strong>{user?.first_name ? t('Welcome back, {name}. Everything is here.', { name: user.first_name }) : t('Welcome back. Everything is here.')}</strong>
            <span>{t('You were writing paragraph {n} {when}. Your cursor is where you left it.', { n: welcome.paragraph, when: welcome.when })}</span>
          </div>
          <button type="button" className="el-btn is-small is-light" onClick={() => { setWelcome(null); editor?.commands.focus() }}>{t('Keep writing')}</button>
        </div>}

        {essay.essay_type !== 'free_writing' && <PromptCard essay={essay} onEdit={onEditDetails} />}

        {preview && <div className="el-banner is-preview" role="status">
          <Eye size={18} aria-hidden="true" />
          <span>{tp('Previewing the version from {when} · {n} words. Nothing changes until you restore it.', preview.checkpoint.word_count ?? 0, { when: checkpointDate(preview.checkpoint.created_at), n: preview.checkpoint.word_count ?? 0 })}</span>
          <button type="button" className="el-btn is-small is-primary" onClick={() => restoreCheckpoint(preview.checkpoint)}><RotateCcw size={14} aria-hidden="true" />{t('Restore this version')}</button>
          <button type="button" className="el-btn is-small" onClick={() => setPreview(null)}>{t('Back to current')}</button>
        </div>}
        {preview && <article className="el-page is-preview"><DocPreview doc={preview.doc} /></article>}

        <EditorPage editor={editor} hidden={Boolean(preview)} label={tabTitle} paged={paged && !focusMode} pageSize={essay.page_size} />
      </div>
    </div>
    {panel === 'history' && !focusMode && <History essayId={essay.id} tabId={session.id} version={historyVersion} words={tabWords}
      savedAt={state.savedAt} previewId={preview?.checkpoint.id ?? null}
      onPreview={previewCheckpoint} onRestore={restoreCheckpoint} onBeforeName={flushBeforeName} onClose={closeHistory} />}
    {panel === 'coach' && !focusMode && <CoachPanel check={check} status={checkStatus} anchored={anchored} activeId={activeNoteId} dismissed={dismissed}
      words={tabWords}
      onCheck={runCheck} onSelect={selectNote} onJump={jumpToNote} onDismiss={dismissNote} onClose={closePanel} />}
  </>
}

const DISMISSED_PREFIX = 'naseeb-essay-coach-dismissed:'

function readDismissed(checkId) {
  if (!checkId) return new Set()
  try { return new Set(JSON.parse(localStorage.getItem(DISMISSED_PREFIX + checkId) || '[]')) } catch { return new Set() }
}

function writeDismissed(checkId, ids) {
  try { localStorage.setItem(DISMISSED_PREFIX + checkId, JSON.stringify([...ids])) } catch { /* per-device convenience only */ }
}

function paragraphNumber(doc, pos) {
  let index = 0
  let found = 0
  doc.forEach((node, offset) => {
    if (node.isBlock) index += 1
    if (!found && pos >= offset && pos <= offset + node.nodeSize) found = index
  })
  return found || index
}

const SAVE_ERRORS = {
  doc_too_large: 'This essay is too long to save online (over 256 KB). Your text is kept on this device.',
  invalid_doc: 'Some formatting in this essay can’t be saved. Try “Clear formatting” on pasted text.',
}

export function scrollToPos(editor, container, pos, ratio = 1 / 2.6) {
  if (!editor || !container) return
  try {
    const coords = editor.view.coordsAtPos(pos)
    const box = container.getBoundingClientRect()
    const target = container.scrollTop + coords.top - box.top - box.height * ratio
    container.scrollTo({ top: Math.max(0, target), behavior: 'smooth' })
  } catch { /* position not rendered */ }
}

const TitleInput = memo(function TitleInput({ value, onSave }) {
  const [draft, setDraft] = useState(value)
  useEffect(() => { setDraft(value) }, [value])
  return <input className="el-title-input" aria-label={t('Essay title')} value={draft} maxLength={220}
    onChange={(event) => setDraft(event.target.value)}
    onBlur={() => { if (draft.trim()) onSave(draft); else setDraft(value) }}
    onKeyDown={(event) => {
      if (event.key === 'Enter') event.currentTarget.blur()
      if (event.key === 'Escape') { setDraft(value); event.currentTarget.blur() }
    }} />
})

function PromptCard({ essay, onEdit }) {
  if (!essay.prompt) {
    return <div className="el-prompt is-empty"><span>{t('No question yet.')}</span><button type="button" className="el-link" onClick={onEdit}>{t('Add the question')}</button></div>
  }
  return <details className="el-prompt">
    <summary><span className="el-prompt-summary">{essay.prompt}</span><button type="button" className="el-link" onClick={(event) => { event.preventDefault(); onEdit() }}>{t('Edit question')}</button></summary>
    <p>{essay.prompt}</p>
  </details>
}

function FocusChrome({ title, words, onExit, save }) {
  const [start] = useState(() => ({ at: Date.now(), words }))
  const [, tick] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => tick((value) => value + 1), 30_000)
    return () => window.clearInterval(timer)
  }, [])
  const minutes = Math.max(0, Math.round((Date.now() - start.at) / 60_000))
  const added = words - start.words
  return <>
    <div className="el-focus-top">
      <span>{title}</span>
      <button type="button" className="el-focus-exit" onClick={onExit}>{t('Exit focus')} <kbd>Esc</kbd></button>
    </div>
    <div className="el-focus-pill" aria-live="off">
      <span><strong>{words}</strong> {words === 1 ? t('word') : tp('words', words)}</span>
      <span className="el-sep" aria-hidden="true" />
      <span>{added >= 0 ? t('+{n} this session', { n: added }) : t('{n} this session', { n: added })}</span>
      <span className="el-sep" aria-hidden="true" />
      <span>{t('{n} min', { n: minutes })}</span>
      <span className="el-sep" aria-hidden="true" />
      {save}
    </div>
  </>
}

// Another tab couldn't save: jump to it.
function UnsavedTabsBadge({ count, name, onOpen, compact }) {
  const label = count === 1 ? t('1 tab not saved') : tp('{n} tabs not saved', count, { n: count })
  return <span className="el-save-wrap" role="status" aria-live="polite">
    <button type="button" className="el-save is-error el-save-jump" title={t('Open “{name}”', { name })} onClick={onOpen}>
      <AlertTriangle size={15} aria-hidden="true" /><span className="el-save-text">{compact ? t('Not saved') : label}</span>
    </button>
  </span>
}

// "Saving…", "Saved", "Offline — saved on this device", "Couldn't save · Retry".
// iconOnly (phone header): "Saving…" and "Saved" show only their icon, so the
// tab name keeps the room; problems always show their text.
const SaveBadge = memo(function SaveBadge({ state, onRetry, compact = false, iconOnly = false }) {
  const status = state?.status
  const savedAt = state?.savedAt
  const storageOk = !state?.storageWarning
  const [, tick] = useState(0)
  useEffect(() => {
    if (status !== 'saved') return undefined
    const timer = window.setInterval(() => tick((value) => value + 1), 30_000)
    return () => window.clearInterval(timer)
  }, [status])
  const text = (value, quiet = false) => <span className={quiet && iconOnly ? 'el-sr-only' : 'el-save-text'}>{value}</span>
  let content
  if (status === 'saving' || status === 'pending') {
    content = <span className="el-save is-saving"><span className="el-save-dot" aria-hidden="true" />{text(t('Saving…'), true)}</span>
  } else if (status === 'offline') {
    content = <span className="el-save is-offline"><CloudOff size={15} aria-hidden="true" />{text(storageOk ? t('Offline — saved on this device') : t('Offline — not saved yet'))}</span>
  } else if (status === 'error') {
    content = <span className="el-save is-error"><AlertTriangle size={15} aria-hidden="true" />{text(t('Couldn\'t save'))}<span aria-hidden="true">·</span><button type="button" className="el-save-retry" onClick={onRetry}>{t('Retry')}</button></span>
  } else if (status === 'expired') {
    content = <span className="el-save is-error"><AlertTriangle size={15} aria-hidden="true" />{text(t('Not saved'))}</span>
  } else if (status === 'conflict') {
    content = <span className="el-save is-error"><AlertTriangle size={15} aria-hidden="true" />{text(t('Couldn\'t save'))}</span>
  } else {
    const when = relativeTime(savedAt)
    content = <span className="el-save is-saved" title={when ? t('Saved · {when}', { when }) : undefined}><Check size={15} aria-hidden="true" />
      {text(compact || !when ? t('Saved') : t('Saved · {when}', { when }), true)}</span>
  }
  return <span className="el-save-wrap" role="status" aria-live="polite">{content}</span>
})
