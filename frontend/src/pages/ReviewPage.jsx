import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CircleCheck, ExternalLink, FileX, ListChecks, RefreshCw, ShieldAlert } from 'lucide-react';
import '@fontsource-variable/newsreader/wght.css';
import { api } from '../api';
import { TaskEssayAttachment } from '../components/taskEssays';
import { t, tx } from '../i18n';
import { AttachmentRow, documentAttachment, evidenceAttachment, noPreviewText } from '../components/files';
import { CxAvatar, CxHead, CxPills, CxQueueRow, CxTag, useCounselorUi } from '../components/counselorUi';
import { clockText, joinParts } from '../lib/format';
import { inServerZone, serverRelativeDayText } from '../lib/serverTime';
import { useReviewQueue } from '../hooks/useReviewQueue';
import { REVIEW_SOURCE, REVIEW_SOURCES, approveReviewItem, deepLinkStep, linkedReviewItem, parseReviewItemId } from '../lib/reviewQueue';
import { reviewCounts } from '../lib/counselorCounts';
import { createReviewedTodayState, mergeReviewedToday, reviewedTodayRows, settleLocal } from '../lib/reviewedToday';
import { createLatestRequest } from '../lib/latestRequest';
import { canPreviewInBrowser } from '../lib/fileUpload';
import { hasSubmission, opensInTab } from '../lib/reviewSubmission';
import './review.css';

const firstName = (name) => String(name || '').trim().split(/\s+/)[0];

// The words the counselor sees once a kind is approved (the call itself:
// lib/reviewQueue approveReviewItem). The server sends the same notice to the
// student whichever kind it is (see ApproveMixin / SendBackMixin).
const KIND = {
  task: {
    approved: () => t("Task approved."),
  },
  document: {
    approved: () => t("Document approved."),
  },
  roadmap: {
    approved: (result) => (result.xp_awarded ? tx`Mission approved. +${result.xp_awarded} XP` : t("Mission approved.")),
  },
  portfolio: {
    approved: () => t("Portfolio item verified."),
  },
};

function taskAttachment(task) {
  if (!task?.has_submission_file) return null;
  return {
    name: task.submission_file_name || t("Submission"), size: task.submission_file_size, contentType: task.submission_file_content_type,
    previewable: canPreviewInBrowser(task.submission_file_name),
    load: () => api.taskSubmissionFile(task.id), download: () => api.downloadTaskSubmission(task.id),
  };
}

// A private file shown in the panel itself: PDFs in a frame, images inline,
// with "Open in new tab"; other types say why they can only be downloaded.
function InlineFile({ attachment, title, notify }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ loading: true, url: '', contentType: '', error: '' });
  const { load, previewable } = attachment;
  useEffect(() => {
    if (!previewable) return undefined;
    let active = true;
    let objectUrl = '';
    setState({ loading: true, url: '', contentType: '', error: '' });
    load().then((result) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(result.blob);
      setState({ loading: false, url: objectUrl, contentType: result.contentType, error: '' });
    }).catch((error) => {
      if (active) setState({ loading: false, url: '', contentType: '', error: error.message });
    });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [previewable, attempt]); // eslint-disable-line react-hooks/exhaustive-deps -- one load per shown file (keyed by item) and retry

  const type = state.contentType.split(';')[0].trim();
  return <div className="rv-file">
    <AttachmentRow attachment={attachment} notify={notify} />
    {!previewable
      ? <p className="rv-file-note">{noPreviewText(attachment)}</p>
      : state.loading
        ? <div className="secure-document-state" role="status"><div className="document-skeleton"><span /><span /><span /><span /></div><p>{t("Secure preview is loading…")}</p></div>
        : state.error
          ? <div className="secure-document-state error" role="alert"><ShieldAlert size={24} aria-hidden="true" /><b>{t("Preview could not be loaded")}</b><p>{state.error}</p><button type="button" className="button quiet small" onClick={() => setAttempt((value) => value + 1)}><RefreshCw size={14} aria-hidden="true" /> {t("Retry")}</button></div>
          : <>
            {type.startsWith('image/')
              ? <div className="secure-document-preview image"><img src={state.url} alt={title} /></div>
              : <div className="secure-document-preview"><iframe src={state.url} title={tx`${title} preview`} sandbox={type === 'application/pdf' ? undefined : ''} referrerPolicy="no-referrer" /></div>}
            {opensInTab(type) && <a className="cx-link rv-file-open" href={state.url} target="_blank" rel="noreferrer">{t("Open in new tab")} <ExternalLink size={14} aria-hidden="true" /></a>}
          </>}
  </div>;
}

function NoProof() {
  return <div className="rv-none" role="status"><FileX size={20} aria-hidden="true" /><span><b>{t("No proof attached")}</b><small>{t("You can still approve it if you checked it another way.")}</small></span></div>;
}

function NothingAttached() {
  return <div className="rv-none" role="status"><FileX size={20} aria-hidden="true" /><span><b>{t("No file attached yet")}</b><small>{t("There is nothing to approve until the student adds it. You can send it back with a note.")}</small></span></div>;
}

const ExternalUrl = ({ url }) => <p className="cx-quote-link"><a href={url} target="_blank" rel="noreferrer">{url} <ExternalLink size={13} aria-hidden="true" /></a></p>;

// What the student sent: the words they wrote, and the file or link itself.
export function Submission({ item, notify }) {
  const record = item.record;
  if (item.kind === 'task') {
    const file = taskAttachment(record);
    return <>
      <div className="rv-body">
        {record.student_response
          ? <p className="cx-quote">{t("Student response")}: “{record.student_response}”</p>
          : <p className="cx-quote cx-quote-muted">{t("No written response.")}</p>}
        {record.submission_url && <ExternalUrl url={record.submission_url} />}
      </div>
      <TaskEssayAttachment task={record} />
      {file && <InlineFile key={item.id} attachment={file} title={record.title} notify={notify} />}
      {!hasSubmission('task', record) && <NothingAttached />}
    </>;
  }
  if (item.kind === 'roadmap') {
    return <div className="rv-body">
      {record.reflection
        ? <p className="cx-quote">{t("Student reflection")}: “{record.reflection}”</p>
        : <p className="cx-quote cx-quote-muted">{t("No written reflection.")}</p>}
      {record.google_docs_url && <ExternalUrl url={record.google_docs_url} />}
    </div>;
  }
  if (item.kind === 'document') {
    const file = documentAttachment(record);
    if (file) return <InlineFile key={item.id} attachment={file} title={record.title} notify={notify} />;
    if (record.google_docs_url) return <div className="rv-body"><ExternalUrl url={record.google_docs_url} /></div>;
    return <NothingAttached />;
  }
  const proof = evidenceAttachment(record);
  return <>
    <div className="rv-body">
      <p className="cx-quote">{record.description}</p>
      {record.impact && <p className="cx-quote cx-quote-muted">{t("Impact")}: {record.impact}</p>}
    </div>
    {proof ? <InlineFile key={item.id} attachment={proof} title={record.title} notify={notify} /> : <NoProof />}
  </>;
}

// The queue on the left, the selected item and the counselor's decision on the
// right. Shared by the Review page and a student's own "To review" tab; the
// caller remounts it (key) when the list it shows changes.
//
// `initialItem` (Home's /review?item=kind-id) opens that item only: when it is
// not on a loaded page it is fetched on its own, and when it no longer waits
// for review a notice says so and nothing is selected. `onLinkDone` runs once
// the link is used up (decided, or gone) so a reload does not reopen it.
// `onDecided(item, 'approved' | 'sent_back')` runs after a decision is saved;
// `aside` sits under the list (Review's "Reviewed today"). `total`: the server's
// count of everything waiting (the list holds loaded pages only), else the list's length.
export function ReviewWorkspace({ items: allItems, loaded, notify, reload, setPage, studentLink = true, emptyText, footer = null, initialItem = null, onLinkDone, onDecided, aside = null, total = null }) {
  const [selectedId, setSelectedId] = useState(initialItem);
  // status: pending → found | fetching → fetched | gone | failed; dismissed once the user picks another item.
  const [link, setLink] = useState(() => (initialItem ? { id: initialItem, status: 'pending', item: null, error: '' } : null));
  const [note, setNote] = useState('');
  const noteField = useRef(null);
  const detailPanel = useRef(null);
  const [saving, setSaving] = useState(false);
  // Items decided here leave the list at once; the reload that confirms it may come later.
  const [decided, setDecided] = useState(() => new Set());
  // The linked item fetched on its own stays at the top, whatever else is
  // selected, until it is decided or a loaded page brings it.
  const [pinned, setPinned] = useState(null);
  const pinnedListed = Boolean(pinned) && allItems.some((item) => item.id === pinned.id);
  const items = useMemo(() => {
    const linked = pinned && !pinnedListed ? [pinned] : [];
    return [...linked, ...allItems].filter((item) => !decided.has(item.id));
  }, [pinned, pinnedListed, allItems, decided]);
  useEffect(() => {
    if (pinnedListed) setPinned(null);
  }, [pinnedListed]);
  // While a link is unresolved or gone nothing else is selected for the user.
  const linkHolds = Boolean(link) && ['pending', 'fetching', 'gone', 'failed'].includes(link.status);
  const selected = items.find((item) => item.id === selectedId) || (linkHolds ? null : items[0]) || null;
  const selectedIndex = selected ? items.findIndex((item) => item.id === selected.id) : -1;
  const xp = selected?.kind === 'roadmap' ? selected.record.xp_reward || 0 : 0;
  const approvable = Boolean(selected) && hasSubmission(selected.kind, selected.record);
  // Once the list no longer holds a decided item, forget it: a resubmission must show again.
  useEffect(() => {
    setDecided((current) => {
      const present = new Set(allItems.map((item) => item.id));
      const kept = [...current].filter((id) => present.has(id));
      return kept.length === current.size ? current : new Set(kept);
    });
  }, [allItems]);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    if (link?.status !== 'pending') return;
    const step = deepLinkStep(link.id, allItems, loaded);
    if (step === 'found') { setLink((current) => ({ ...current, status: 'found' })); return; }
    if (step === 'gone') { setLink((current) => ({ ...current, status: 'gone' })); onLinkDone?.(); return; }
    if (step !== 'fetch') return;
    const { kind, recordId } = parseReviewItemId(link.id);
    setLink((current) => ({ ...current, status: 'fetching' }));
    api.retrieve(REVIEW_SOURCE[kind].endpoint, recordId).then((record) => {
      if (!mounted.current) return;
      const item = linkedReviewItem(link.id, record);
      setLink((current) => ({ ...current, status: item ? 'fetched' : 'gone', item }));
      if (item) setPinned(item);
      else onLinkDone?.();
    }).catch((err) => {
      if (!mounted.current) return;
      const gone = err?.status === 404;
      setLink((current) => ({ ...current, status: gone ? 'gone' : 'failed', error: gone ? '' : err?.message || '' }));
      if (gone) onLinkDone?.();
    });
  }, [link, allItems, loaded, onLinkDone]);

  // The detail card scrolls on its own on wide screens; a new item opens at its top.
  useEffect(() => {
    detailPanel.current?.scrollTo?.(0, 0);
  }, [selected?.id]);

  function select(item) {
    setSelectedId(item.id);
    setNote('');
    if (link && link.status !== 'dismissed') setLink((current) => ({ ...current, status: 'dismissed' }));
  }

  // "Skip for now": the next item, wrapping to the first; nothing is decided.
  function skip() {
    if (!selected || items.length < 2) return;
    select(items[(selectedIndex + 1) % items.length]);
  }

  // The item and note are read when the decision is made (the click),
  // and one decision runs at a time, whatever the render state says.
  const deciding = useRef(false);
  async function decide(action) {
    if (!selected || deciding.current) return;
    const text = note.trim();
    if (action === 'approve' && !hasSubmission(selected.kind, selected.record)) return;
    if (action === 'sendBack' && !text) {
      notify(t("Add a note explaining what needs to change."), 'error');
      noteField.current?.focus();
      return;
    }
    const current = selected;
    deciding.current = true;
    setSaving(true);
    try {
      if (action === 'sendBack') {
        await api.sendBack(current.endpoint, current.recordId, text);
        notify(t("Sent back to the student."));
      } else {
        notify(KIND[current.kind].approved(await approveReviewItem(api, current.kind, current.recordId, text)));
      }
      const index = items.findIndex((item) => item.id === current.id);
      const next = items[index + 1] || items[index - 1] || null;
      setDecided((ids) => new Set(ids).add(current.id));
      if (pinned?.id === current.id) setPinned(null);
      setSelectedId(next?.id ?? null);
      setNote('');
      if (link && current.id === link.id) {
        setLink((state) => ({ ...state, status: 'dismissed' }));
        onLinkDone?.();
      }
      onDecided?.(current, action === 'sendBack' ? 'sent_back' : 'approved');
      reload?.();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      deciding.current = false;
      if (mounted.current) setSaving(false);
    }
  }

  return <div className="rv-workspace">
    <div className="rv-column">
      <section className="rv-card rv-queue" aria-labelledby="rv-queue-title">
        <header className="rv-wh"><ListChecks size={17} aria-hidden="true" /><span id="rv-queue-title">{t("Needs your review")}</span><em>{t("oldest first")}</em></header>
        <div className="cx-list rv-list">
          {items.map((item) => <CxQueueRow key={item.id} item={item} active={selected?.id === item.id} onClick={() => select(item)} />)}
          {!loaded && !items.length && <div role="status" aria-label={t("Loading…")}>{[0, 1, 2, 3, 4].map((index) => <span key={index} className="skeleton-line" aria-hidden="true" />)}</div>}
          {loaded && !items.length && <p className="rv-empty">{emptyText || t("Nothing is waiting for your review.")}</p>}
        </div>
        {footer}
      </section>
      {aside}
    </div>
    <section ref={detailPanel} className="rv-card rv-detail" aria-label={t("Details")}>
      {!selected && (link?.status === 'pending' || link?.status === 'fetching'
        ? <p className="rv-empty" role="status">{t("Opening…")}</p>
        : link?.status === 'gone' ? <p className="rv-empty" role="status">{t("That item was already reviewed.")}</p>
          : link?.status === 'failed' ? <p className="rv-empty" role="alert">{joinParts(t("That item could not be opened."), link.error)}</p>
            : <p className="rv-empty">{t("Select something from the list to review it.")}</p>)}
      {selected && <>
        <div className="rv-top">
          <span className="rv-step">{t("{i} of {n}", { i: selectedIndex + 1, n: Math.max(total ?? 0, items.length) })}</span>
          <CxTag tone={selected.kind} small>{t(selected.label)}</CxTag>
        </div>
        <div className="rv-who">
          <CxAvatar name={selected.studentName} className="rv-avatar" />
          <span className="rv-who-copy"><b>{selected.studentName}</b><small>{t(selected.when, { when: serverRelativeDayText(selected.at).toLowerCase() })}</small></span>
          {studentLink && <button type="button" className="rv-link" onClick={() => setPage('students', { studentId: selected.studentId })}>{t("Open Student 360")}</button>}
        </div>
        <h2 className="rv-title">{selected.title}</h2>
        <Submission item={selected} notify={notify} />
        <div className="rv-decide">
          <label className="rv-field">
            <span>{t("Note to {name} (optional for approve, required to send back)", { name: firstName(selected.studentName) })}</span>
            <textarea ref={noteField} value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} placeholder={t("e.g. “Great start — add one concrete example in paragraph 2.”")} />
          </label>
          <div className="rv-acts">
            <button type="button" className="rv-btn line" disabled={saving} onClick={() => decide('sendBack')}>{t("Send back with note")}</button>
            {items.length > 1 && <button type="button" className="rv-later" disabled={saving} onClick={skip}>{t("Skip for now")}</button>}
            <button type="button" className="rv-btn" disabled={saving || !approvable} aria-busy={saving} onClick={() => decide('approve')}>{xp > 0 ? t("Approve (+{xp} XP)", { xp }) : t("Approve")}</button>
          </div>
        </div>
      </>}
    </section>
  </div>;
}

const KIND_LABEL = Object.fromEntries(REVIEW_SOURCES.map(({ kind, label }) => [kind, label]));

// What this counselor approved or sent back today (Tashkent), newest first.
// Decisions made on this page show at once and give way to the server's rows.
function useReviewedToday() {
  const [state, setState] = useState({ rows: [], loaded: false, error: '' });
  const [local, setLocal] = useState([]);
  const [{ latest, tracker }] = useState(() => ({ latest: createLatestRequest(), tracker: createReviewedTodayState() }));
  const load = useCallback(() => {
    const isCurrent = latest.start();
    const mark = tracker.mark();
    return api.reviewedToday().then((data) => {
      if (!isCurrent()) return;
      setState({ rows: reviewedTodayRows(data), loaded: true, error: '' });
      setLocal((current) => settleLocal(current, mark));
    }).catch((err) => {
      if (isCurrent()) setState((current) => ({ ...current, loaded: true, error: err?.message || '' }));
    });
  }, [latest, tracker]);
  useEffect(() => {
    load();
    return () => latest.cancel();
  }, [load, latest]);
  const add = useCallback((item, decision) => {
    setLocal((current) => [...current, tracker.local(item, decision)]);
    load();
  }, [load, tracker]);
  const rows = useMemo(() => mergeReviewedToday(state.rows, local), [state.rows, local]);
  return { rows, loaded: state.loaded, error: state.error, retry: load, add };
}

function ReviewedToday({ today }) {
  return <section className="rv-card rv-today" aria-labelledby="rv-today-title">
    <header className="rv-wh"><CircleCheck size={17} aria-hidden="true" /><span id="rv-today-title">{t("Reviewed today")}</span></header>
    {today.error && !today.rows.length
      ? <div className="rv-empty rv-today-error" role="alert"><span>{joinParts(t("Today's reviews could not be loaded."), today.error)}</span><button type="button" className="rv-later" onClick={today.retry}><RefreshCw size={14} aria-hidden="true" /> {t("Retry")}</button></div>
      : !today.loaded && !today.rows.length
        ? <div role="status" aria-label={t("Loading…")}><span className="skeleton-line" aria-hidden="true" /></div>
        : !today.rows.length
          ? <p className="rv-empty">{t("Nothing reviewed yet today.")}</p>
          : <ul className="rv-today-list">
            {today.rows.map((row) => <li key={row.id} className={`rv-today-row${row.pending ? ' pending' : ''}`}>
              <CxAvatar name={row.student_name} />
              <span className="cx-row-copy"><b>{row.title}</b><small>{joinParts(row.student_name, KIND_LABEL[row.kind] && t(KIND_LABEL[row.kind]), clockText(inServerZone(row.at)))}</small></span>
              <CxTag tone={row.decision === 'approved' ? 'ok' : 'warn'} small>{row.decision === 'approved' ? t("Approved") : t("Sent back")}</CxTag>
            </li>)}
          </ul>}
  </section>;
}

// Documents, tasks and portfolio waiting for the counselor.
export function ReviewPage({ setPage, notify, reload, initialItem = null, onLinkDone }) {
  const { stats } = useCounselorUi();
  const queue = useReviewQueue();
  const today = useReviewedToday();
  const [filter, setFilter] = useState('all');
  const totals = reviewCounts(stats);
  // Counts only once the stats carry them: "All 0" while loading reads as an empty queue.
  const counted = Boolean(stats?.review);
  const items = useMemo(() => (filter === 'all' ? queue.items : queue.items.filter((item) => item.kind === filter)), [filter, queue.items]);
  const pills = [['all', 'All', counted ? totals.total : undefined], ...REVIEW_SOURCES.map(({ kind, pill }) => [kind, pill, counted ? totals[kind] : undefined])];
  // Each kind pages on its own; "load more" asks for the next page of the kinds on screen.
  const more = REVIEW_SOURCES.filter(({ kind, listKey }) => (filter === 'all' || filter === kind) && queue.lists[listKey].hasMore);
  const footer = more.length > 0 && <div className="paged-list-footer rv-more">
    {more.map(({ kind, listKey, pill }) => {
      const list = queue.lists[listKey];
      return <button key={kind} type="button" className="rv-later" onClick={list.loadMore} disabled={list.loadingMore} aria-busy={list.loadingMore}>
        {list.loadingMore ? t("Loading…") : more.length > 1 ? t("Load more: {kind}", { kind: t(pill) }) : t("Load more")}
      </button>;
    })}
  </div>;

  return <div className="cx-page cx-review-page rv-page">
    <CxHead title={t("Review queue")} subtitle={t("Documents, tasks and portfolio waiting for you")} />
    <div className="rv-tabs"><CxPills items={pills} active={filter} onChange={setFilter} label={t("Filter by kind")} /></div>
    {queue.error && <div className="data-state error" role="alert"><div><b>{t("Some information could not be loaded")}</b><p>{queue.error}</p></div><button type="button" className="button quiet small" onClick={queue.retry}><RefreshCw size={14} /> {t("Retry")}</button></div>}
    <ReviewWorkspace key={filter} items={items} loaded={queue.loaded} notify={notify} reload={reload} setPage={setPage} footer={footer} initialItem={filter === 'all' ? initialItem : null} onLinkDone={onLinkDone} onDecided={today.add} aside={<ReviewedToday today={today} />} total={counted ? totals[filter === 'all' ? 'total' : filter] : null} />
  </div>;
}
