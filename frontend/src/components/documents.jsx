import { useState, useEffect } from 'react';
import { FileText, Clock3, RefreshCw, Eye, ExternalLink, Download, ShieldAlert } from 'lucide-react';
import { t, tx } from '../i18n';
import { Modal, Badge, Empty } from './ui';
import { label } from '../lib/labels';
import { dateText, dateTimeText, formatFileSize } from '../lib/format';
import { api } from '../api';
import { FileTypeIcon, documentAttachment, downloadAttachment, evidenceAttachment, noPreviewText } from './files';

export function GoogleDocsPreview({ previewUrl, title }) {
  const [frameState, setFrameState] = useState('loading');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setFrameState('loading');
    const timer = window.setTimeout(() => setFrameState((current) => current === 'loading' ? 'slow' : current), 12_000);
    return () => window.clearTimeout(timer);
  }, [previewUrl, attempt]);
  if (!previewUrl) return null;
  return <div className="google-doc-preview"><div><FileText size={18} /><span><b>{t("Google Docs preview")}</b><small>{t("The document must allow Viewer access or “Anyone with the link” for the preview to load.")}</small></span></div><section className="embedded-preview-frame">
    {frameState !== 'ready' && <div className={`embedded-preview-state ${frameState}`} role="status"><div className="document-skeleton"><span /><span /><span /><span /></div>{frameState === 'slow' && <div className="embedded-preview-slow"><Clock3 size={20} /><b>{t("The preview is taking longer than expected.")}</b><p>{t("Your connection may be slow. You can retry without closing this record.")}</p><button type="button" className="button quiet small" onClick={() => setAttempt((current) => current + 1)}><RefreshCw size={14} /> {t("Retry preview")}</button></div>}</div>}
    <iframe key={`${previewUrl}-${attempt}`} className={frameState === 'ready' ? "is-ready" : ''} src={previewUrl} title={tx`${title} Google Docs preview`} loading="lazy" referrerPolicy="no-referrer" sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox" onLoad={() => setFrameState('ready')} onError={() => setFrameState('slow')} />
  </section></div>;
}

export function googleDocsTitle(item) {
  return item.title || item.name || item.organization || item.recommender_name || 'Google Docs record';
}

export function GoogleDocsActions({ item, onPreview }) {
  if (!item?.google_docs_url) return null;
  return <>
    {item.google_docs_preview_url && onPreview && <button type="button" className="button quiet small" onClick={onPreview}><Eye size={14} /> {t("Preview")}</button>}
    <a className="button quiet small" href={item.google_docs_url} target="_blank" rel="noreferrer">{t("Open in Google Docs")} <ExternalLink size={14} /></a>
  </>;
}

export function GoogleDocsRecordModal({ item, onClose }) {
  const title = googleDocsTitle(item);
  return <Modal title={title} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><span>{t("Google Docs attachment")}</span><GoogleDocsActions item={item} /></div><GoogleDocsPreview previewUrl={item.google_docs_preview_url} title={title} /></div></Modal>;
}

export function EssayDetailModal({ essay, onClose }) {
  return <Modal title={essay.title} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><div><Badge>{essay.status}</Badge><span>{t("Version")} {essay.version} · {essay.university_name || t("General essay")}</span></div><GoogleDocsActions item={essay} /></div><section><span className="detail-label">{t("Essay prompt")}</span><p>{essay.prompt}</p></section>{essay.google_docs_preview_url ? <GoogleDocsPreview previewUrl={essay.google_docs_preview_url} title={essay.title} /> : <section><span className="detail-label">{t("Current draft")}</span><div className="essay-content-preview">{essay.content || t("No draft content has been added yet.")}</div></section>}{essay.counselor_comment && <section className="counselor-feedback"><span className="detail-label">{t("Counselor feedback")}</span><p>{essay.counselor_comment}</p></section>}{essay.revisions?.length > 0 && <section><span className="detail-label">{t("Revision history")}</span><div className="revision-chips">{essay.revisions.map((revision) => <span key={revision.id}>{t("v")}{revision.version} · {label(revision.status)} · {dateText(revision.created_at)}</span>)}</div></section>}</div></Modal>;
}

export function TaskSubmissionModal({ task, onClose, notify }) {
  return <Modal title={tx`Task response · ${task.title}`} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><div><Badge>{task.status}</Badge><span>{task.submitted_at ? tx`Submitted ${dateTimeText(task.submitted_at)}` : t("Not submitted yet")}</span></div><div className="detail-actions">{task.has_submission_file && <button className="button quiet" onClick={() => downloadTaskSubmission(task, notify)}><Download size={15} /> {task.submission_file_name || t("Download file")}</button>}{task.submission_url && <a className="button primary" href={task.submission_url} target="_blank" rel="noreferrer">{t("Open submission")} <ExternalLink size={15} /></a>}</div></div><section><span className="detail-label">{t("Assigned task")}</span><p>{task.description || t("No additional instructions.")}</p></section><section><span className="detail-label">{t("Student response")}</span><div className="essay-content-preview">{task.student_response || t("The student has not submitted a written response yet.")}</div></section><GoogleDocsPreview previewUrl={task.submission_preview_url} title={task.title} /></div></Modal>;
}

export function downloadTaskSubmission(task, notify) {
  return downloadAttachment({
    name: task.submission_file_name || t("Submission"),
    download: () => api.downloadTaskSubmission(task.id),
  }, notify);
}

// Renders a private file fetched through `attachment.load()`.
export function FilePreview({ attachment, title }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ loading: true, url: '', contentType: '', error: '' });
  const load = attachment.load;
  useEffect(() => {
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
  }, [attempt]); // eslint-disable-line react-hooks/exhaustive-deps -- one load per opened file and retry

  if (state.loading) return <div className="secure-document-state" role="status"><div className="document-skeleton"><span /><span /><span /><span /></div><p>{t("Secure preview is loading…")}</p></div>;
  if (state.error) return <div className="secure-document-state error" role="alert"><ShieldAlert size={24} /><b>{t("Preview could not be loaded")}</b><p>{state.error}</p><button className="button quiet small" onClick={() => setAttempt((value) => value + 1)}><RefreshCw size={14} /> {t("Retry")}</button></div>;
  if (state.contentType.startsWith('image/')) return <div className="secure-document-preview image"><img src={state.url} alt={title} /></div>;
  // Uploaded files render with no script/same-origin rights. Chrome refuses to
  // show PDFs inside a sandboxed frame, so PDFs (run by the browser's own
  // isolated viewer) are the one exception; the backend also allowlists types.
  const isPdf = state.contentType.split(';')[0].trim() === 'application/pdf';
  return <div className="secure-document-preview"><iframe src={state.url} title={tx`${title} preview`} sandbox={isPdf ? undefined : ''} referrerPolicy="no-referrer" /></div>;
}

function AttachmentBody({ attachment, title }) {
  if (attachment.previewable) return <FilePreview attachment={attachment} title={title} />;
  return <div className="file-no-preview"><FileTypeIcon name={attachment.name} contentType={attachment.contentType} size={28} /><p>{noPreviewText(attachment)}</p></div>;
}

function AttachmentToolbar({ attachment, notify, children }) {
  return <div className="workspace-detail-toolbar"><div className="attachment-summary"><FileTypeIcon name={attachment.name} contentType={attachment.contentType} /><span>{attachment.name} · {formatFileSize(attachment.size)}</span></div><div className="detail-actions"><button className="button quiet" onClick={() => downloadAttachment(attachment, notify)}><Download size={15} /> {t("Download")}</button>{children}</div></div>;
}

export function AttachmentPreviewModal({ title, attachment, onClose, notify }) {
  return <Modal title={title} onClose={onClose}><div className="workspace-detail"><AttachmentToolbar attachment={attachment} notify={notify} /><AttachmentBody attachment={attachment} title={title} /></div></Modal>;
}

export function EvidencePreviewModal({ item, onClose, notify }) {
  return <AttachmentPreviewModal title={tx`Evidence · ${visibilityItemTitle(item)}`} attachment={evidenceAttachment(item)} onClose={onClose} notify={notify} />;
}

export function DocumentPreviewModal({ document: doc, onClose, notify }) {
  const attachment = documentAttachment(doc);
  return <Modal title={doc.title} onClose={onClose}><div className="workspace-detail"><div className="workspace-detail-toolbar"><div><Badge>{doc.status}</Badge><span>{label(doc.document_type)}</span></div><div className="detail-actions"><GoogleDocsActions item={doc} /></div></div>{attachment && <AttachmentToolbar attachment={attachment} notify={notify} />}{doc.counselor_comment && <section><span className="detail-label">{t("Counselor comment")}</span><p>{doc.counselor_comment}</p></section>}{attachment ? <AttachmentBody attachment={attachment} title={doc.title} /> : doc.google_docs_preview_url ? <GoogleDocsPreview previewUrl={doc.google_docs_preview_url} title={doc.title} /> : <Empty text={t("No file or Google Docs link has been added for preview.")} />}</div></Modal>;
}

export function visibilityItemTitle(item) {
  return item.title || item.name || item.organization || item.university_name || item.recommender_name || item.topic || t("Record");
}
