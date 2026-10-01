import { useState } from 'react';
import '@fontsource-variable/newsreader/wght.css';
import { api } from '../api';
import { t, tx } from '../i18n';
import { AttachmentRow, documentAttachment, evidenceAttachment } from '../components/files';
import { DocumentPreviewModal, EvidencePreviewModal, TaskSubmissionModal } from '../components/documents';
import { CxAvatar, CxHead, CxPills, CxQueueRow, useCounselorUi } from '../components/counselorUi';
import { joinParts, relativeDayText } from '../lib/format';
import { useReviewQueue } from '../hooks/useReviewQueue';
import { REVIEW_SOURCES } from '../lib/reviewQueue';
import { reviewCounts } from '../lib/counselorCounts';

const firstName = (name) => String(name || '').trim().split(/\s+/)[0];

// What each kind of submitted work needs: how it is approved, and the words
// the counselor sees afterwards. The server sends the same notice to the
// student whichever kind it is (see ApproveMixin / SendBackMixin).
const KIND = {
  task: {
    approve: (item, note) => api.approveTask(item.recordId, note),
    approved: (result) => (result.xp_awarded ? tx`Task approved. +${result.xp_awarded} XP` : t("Task approved.")),
  },
  document: {
    approve: (item, note) => api.approveRecord('documents', item.recordId, note),
    approved: () => t("Document approved."),
  },
  roadmap: {
    approve: (item, note) => api.approveRoadmapMission(item.recordId, note),
    approved: (result) => (result.xp_awarded ? tx`Mission approved. +${result.xp_awarded} XP` : t("Mission approved.")),
  },
  portfolio: {
    approve: (item, note) => api.approveRecord('achievements', item.recordId, note),
    approved: () => t("Portfolio item verified."),
  },
};

// What the student sent, in the serif of the design: the words they wrote, and
// whatever file or link came with them.
function Submission({ item, notify, onPreview, onOpenTask }) {
  const record = item.record;
  if (item.kind === 'task') {
    return <>
      {record.student_response
        ? <p className="cx-quote">{t("Student response")}: “{record.student_response}”</p>
        : <p className="cx-quote cx-quote-muted">{t("No written response.")}</p>}
      {record.submission_url && <p className="cx-quote-link"><a href={record.submission_url} target="_blank" rel="noreferrer">{record.submission_url}</a></p>}
      {(record.has_submission_file || record.submission_url) && <button type="button" className="cx-btn" onClick={() => onOpenTask(record)}>{t("View full submission")}</button>}
    </>;
  }
  if (item.kind === 'roadmap') {
    return <>
      {record.reflection
        ? <p className="cx-quote">{t("Student reflection")}: “{record.reflection}”</p>
        : <p className="cx-quote cx-quote-muted">{t("No written reflection.")}</p>}
      {record.google_docs_url && <p className="cx-quote-link"><a href={record.google_docs_url} target="_blank" rel="noreferrer">{record.google_docs_url}</a></p>}
    </>;
  }
  if (item.kind === 'document') {
    return <>
      <p className="cx-quote">{record.title}</p>
      {record.has_file
        ? <AttachmentRow attachment={documentAttachment(record)} onPreview={() => onPreview(item)} notify={notify} />
        : record.google_docs_url && <p className="cx-quote-link"><a href={record.google_docs_url} target="_blank" rel="noreferrer">{record.google_docs_url}</a></p>}
    </>;
  }
  return <>
    <p className="cx-quote">{record.description}</p>
    {record.impact && <p className="cx-quote cx-quote-muted">{t("Impact")}: {record.impact}</p>}
    {record.has_proof_file && <AttachmentRow attachment={evidenceAttachment(record)} onPreview={() => onPreview(item)} notify={notify} />}
  </>;
}

// The queue on the left, the selected item and the counselor's decision on the
// right. Shared by the Review page and a student's own "To review" tab; the
// caller remounts it (key) when the list it shows changes.
export function ReviewWorkspace({ items, loaded, notify, reload, setPage, studentLink = true, emptyText }) {
  const [selectedId, setSelectedId] = useState(null);
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(null);
  const [openTask, setOpenTask] = useState(null);
  const selected = items.find((item) => item.id === selectedId) || items[0] || null;
  const xp = selected?.record?.xp_reward || 0;

  function select(item) {
    setSelectedId(item.id);
    setNote('');
  }

  async function decide(action) {
    if (!selected) return;
    const text = note.trim();
    if (action === 'sendBack' && !text) {
      notify(t("Add a note explaining what needs to change."), 'error');
      return;
    }
    setSaving(true);
    try {
      if (action === 'sendBack') {
        await api.sendBack(selected.endpoint, selected.recordId, text);
        notify(t("Sent back to the student."));
      } else {
        notify(KIND[selected.kind].approved(await KIND[selected.kind].approve(selected, text)));
      }
      setSelectedId(null);
      setNote('');
      reload?.();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  return <div className="cx-review">
    <section className="cx-card cx-review-list" aria-label={t("Review")}>
      <div className="cx-list">
        {items.map((item) => <CxQueueRow key={item.id} item={item} active={selected?.id === item.id} onClick={() => select(item)} />)}
        {loaded && !items.length && <p className="cx-empty">{emptyText || t("Nothing is waiting for your review.")}</p>}
      </div>
    </section>
    <section className="cx-card cx-review-detail" aria-label={t("Details")}>
      {!selected && <p className="cx-empty">{t("Select something from the list to review it.")}</p>}
      {selected && <>
        <div className="cx-review-head">
          <CxAvatar name={selected.studentName} />
          <span className="cx-row-copy"><b>{selected.title}</b><small>{joinParts(selected.studentName, t(selected.when, { when: relativeDayText(selected.at).toLowerCase() }))}</small></span>
          {studentLink && <button type="button" className="cx-link" onClick={() => setPage('students', { studentId: selected.studentId })}>{t("Open Student 360")}</button>}
        </div>
        <div className="cx-review-body"><Submission item={selected} notify={notify} onPreview={setPreviewing} onOpenTask={setOpenTask} /></div>
        <label className="cx-field">
          <span>{t("Note to {name} (optional for approve, required to send back)", { name: firstName(selected.studentName) })}</span>
          <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} placeholder={t("e.g. “Great start — add one concrete example in paragraph 2.”")} />
        </label>
        <div className="cx-review-actions">
          <button type="button" className="cx-btn lg" disabled={saving} onClick={() => decide('sendBack')}>{t("Send back with note")}</button>
          <button type="button" className="cx-btn lg primary" disabled={saving} aria-busy={saving} onClick={() => decide('approve')}>{xp > 0 ? t("Approve (+{xp} XP)", { xp }) : t("Approve")}</button>
        </div>
      </>}
    </section>
    {previewing?.kind === 'document' && <DocumentPreviewModal document={previewing.record} onClose={() => setPreviewing(null)} notify={notify} />}
    {previewing?.kind === 'portfolio' && <EvidencePreviewModal item={previewing.record} onClose={() => setPreviewing(null)} notify={notify} />}
    {openTask && <TaskSubmissionModal task={openTask} onClose={() => setOpenTask(null)} notify={notify} />}
  </div>;
}

// "Everything students sent you, in one place".
export function ReviewPage({ setPage, notify, reload }) {
  const { stats } = useCounselorUi();
  const queue = useReviewQueue();
  const [filter, setFilter] = useState('all');
  const totals = reviewCounts(stats);
  const items = filter === 'all' ? queue.items : queue.items.filter((item) => item.kind === filter);
  const pills = [['all', 'All', totals.total], ...REVIEW_SOURCES.map(({ kind, pill }) => [kind, pill, totals[kind]])];

  return <div className="cx-page cx-review-page">
    <CxHead title={t("Review")} subtitle={t("Everything students sent you, in one place · oldest first")}>
      <CxPills items={pills} active={filter} onChange={setFilter} label={t("Filter by kind")} />
    </CxHead>
    <ReviewWorkspace key={filter} items={items} loaded={queue.loaded} notify={notify} reload={reload} setPage={setPage} />
  </div>;
}
