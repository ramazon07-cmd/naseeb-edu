import { useEffect, useId, useRef, useState } from 'react';
import { Download, Eye, File, FileImage, FileText, FileType2, RotateCcw, UploadCloud, X } from 'lucide-react';
import { t, tx } from '../i18n';
import { api } from '../api';
import { formatFileSize } from '../lib/format';
import { MAX_UPLOAD_BYTES, UPLOAD_ACCEPT, canPreviewInBrowser, fileKind, uploadProblem } from '../lib/fileUpload';

const KIND_ICONS = { pdf: FileText, word: FileType2, image: FileImage, file: File };
const MAX_UPLOAD_MB = Math.round(MAX_UPLOAD_BYTES / (1024 * 1024));

export function FileTypeIcon({ name, contentType = '', size = 18 }) {
  const kind = fileKind(name, contentType);
  const Icon = KIND_ICONS[kind];
  return <span className={`file-type-icon ${kind}`} aria-hidden="true"><Icon size={size} /></span>;
}

export function uploadHint() {
  return tx`PDF, Word (.doc, .docx), JPG, PNG, WebP or HEIC · up to ${MAX_UPLOAD_MB} MB`;
}

export function uploadProblemMessage(problem) {
  if (!problem) return '';
  if (problem.code === 'size') return tx`This file is larger than ${MAX_UPLOAD_MB} MB. Choose a smaller file.`;
  if (problem.code === 'empty') return t("The selected file is empty.");
  return t("This file type is not supported. Use PDF, Word (.doc, .docx), JPG, PNG, WebP or HEIC.");
}

function uploadErrorMessage(error) {
  if (error?.status === 413) return tx`This file is larger than ${MAX_UPLOAD_MB} MB. Choose a smaller file.`;
  return error?.message || t("The upload failed. Retry.");
}

// Upload state for one form: progress, cancel and a readable error.
// run(send) calls send({ onProgress, signal }) and resolves
// { ok, result } | { ok: false, cancelled } | { ok: false, error }.
export function useFileUpload() {
  const [state, setState] = useState({ uploading: false, progress: 0, error: '' });
  const controller = useRef(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function run(send) {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setState({ uploading: true, progress: 0, error: '' });
    try {
      const result = await send({
        signal: current.signal,
        onProgress: (progress) => setState((value) => value.uploading ? { ...value, progress } : value),
      });
      setState({ uploading: false, progress: 100, error: '' });
      return { ok: true, result };
    } catch (error) {
      if (error?.name === 'AbortError') {
        setState({ uploading: false, progress: 0, error: '' });
        return { ok: false, cancelled: true };
      }
      setState({ uploading: false, progress: 0, error: uploadErrorMessage(error) });
      return { ok: false, error };
    } finally {
      if (controller.current === current) controller.current = null;
    }
  }
  return {
    ...state,
    run,
    cancel: () => controller.current?.abort(),
    clearError: () => setState((value) => value.error ? { ...value, error: '' } : value),
  };
}

// Pick one private file: drag and drop or the system picker (camera and photo
// library on phones). `current` is the stored file ({ name, size, contentType })
// that a new choice replaces; `onRemoveCurrent`, when given, lets the user
// detach it without choosing another.
export function FileField({ label, file, onFileChange, current = null, removingCurrent = false, onRemoveCurrent, onKeepCurrent, error = '', upload = null, required = false }) {
  const inputId = useId();
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [problem, setProblem] = useState('');
  const uploading = Boolean(upload?.uploading);
  const message = problem || error;

  function choose(files) {
    const next = files?.[0];
    if (!next) return;
    const found = uploadProblem(next);
    if (found) {
      setProblem(uploadProblemMessage(found));
      onFileChange(null);
    } else {
      setProblem('');
      onFileChange(next);
    }
    upload?.clearError();
    if (inputRef.current) inputRef.current.value = '';
  }

  function drop(event) {
    event.preventDefault();
    setDragging(false);
    if (!uploading) choose(event.dataTransfer?.files);
  }

  const shown = file ? { name: file.name, size: file.size, contentType: file.type } : current && !removingCurrent ? current : null;
  const status = file && current ? tx`Replaces ${current.name}` : file ? t("Ready to upload") : removingCurrent ? '' : t("Current file");

  return <div className={`file-field form-wide ${message ? 'is-error' : ''}`.trim()}>
    <span className="file-field-label" id={`${inputId}-label`}>{label}{required && <span aria-hidden="true"> *</span>}</span>
    {shown && <div className="file-chip">
      <FileTypeIcon name={shown.name} contentType={shown.contentType} size={20} />
      <div className="file-chip-text"><b title={shown.name}>{shown.name}</b><small>{formatFileSize(shown.size)} · {status}</small></div>
      {!uploading && file && <button type="button" className="icon-button" onClick={() => {onFileChange(null);setProblem('');}} aria-label={t("Remove selected file")}><X size={16} /></button>}
      {!uploading && !file && onRemoveCurrent && <button type="button" className="icon-button danger" onClick={onRemoveCurrent} aria-label={t("Remove file")}><X size={16} /></button>}
    </div>}
    {removingCurrent && !file && current && <div className="file-chip is-removed"><FileTypeIcon name={current.name} contentType={current.contentType} size={20} /><div className="file-chip-text"><b title={current.name}>{current.name}</b><small>{t("Will be removed when you save")}</small></div><button type="button" className="button quiet small" onClick={onKeepCurrent}><RotateCcw size={14} /> {t("Keep file")}</button></div>}
    {uploading ? <div className="file-progress" role="status">
      <div className="file-progress-head"><span>{t("Uploading…")}</span><b>{upload.progress}%</b></div>
      <div className="file-progress-track" role="progressbar" aria-labelledby={`${inputId}-label`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={upload.progress}><span style={{ width: `${upload.progress}%` }} /></div>
      <button type="button" className="button quiet" onClick={upload.cancel}><X size={15} /> {t("Cancel upload")}</button>
    </div> : <div
      className={`file-drop ${dragging ? 'is-dragging' : ''}`.trim()}
      onDragEnter={(event) => {event.preventDefault();setDragging(true);}}
      onDragOver={(event) => {event.preventDefault();event.dataTransfer.dropEffect = 'copy';}}
      onDragLeave={(event) => {if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false);}}
      onDrop={drop}>
      <UploadCloud size={24} aria-hidden="true" />
      <span className="file-drop-text">{shown ? t("Drop another file here to replace it, or") : t("Drag a file here, or")}</span>
      <button type="button" className="button quiet file-drop-button" onClick={() => inputRef.current?.click()} aria-describedby={message ? `${hintId} ${errorId}` : hintId}>{shown ? t("Choose another file") : t("Choose file")}</button>
      <small id={hintId}>{uploadHint()}</small>
      <input ref={inputRef} id={inputId} className="file-input" type="file" accept={UPLOAD_ACCEPT} tabIndex={-1} aria-hidden="true" onChange={(event) => choose(event.target.files)} />
    </div>}
    {message && <p className="field-error" id={errorId} role="alert">{message}</p>}
  </div>;
}

// Error box under a form with a retry that re-submits it.
export function UploadError({ message, onRetry }) {
  if (!message) return null;
  return <div className="upload-error form-wide" role="alert"><span>{message}</span>{onRetry && <button type="button" className="button quiet small" onClick={onRetry}><RotateCcw size={14} /> {t("Retry")}</button>}</div>;
}

// A stored private file, described once so rows, previews and downloads
// treat documents, evidence and letters alike.
export function documentAttachment(doc) {
  if (!doc?.has_file) return null;
  return {
    name: doc.file_name || t("Document"), size: doc.file_size, contentType: doc.file_content_type,
    previewable: doc.file_previewable ?? canPreviewInBrowser(doc.file_name),
    load: () => api.documentFile(doc.id), download: () => api.downloadDocument(doc.id),
  };
}

export function evidenceAttachment(item) {
  if (!item?.has_proof_file) return null;
  return {
    name: item.proof_file_name || t("Evidence"), size: item.proof_file_size, contentType: item.proof_file_content_type,
    previewable: item.proof_file_previewable ?? canPreviewInBrowser(item.proof_file_name),
    load: () => api.evidenceFile(item.proof_resource, item.id), download: () => api.downloadEvidence(item.proof_resource, item.id),
  };
}

export function recommendationAttachment(item) {
  if (!item?.has_file) return null;
  return {
    name: item.file_name || t("Recommendation letter"), size: item.file_size, contentType: item.file_content_type,
    previewable: item.file_previewable ?? canPreviewInBrowser(item.file_name),
    load: () => api.recommendationFile(item.id), download: () => api.downloadRecommendationFile(item.id),
  };
}

export async function downloadAttachment(attachment, notify) {
  try {
    const result = await attachment.download();
    const url = URL.createObjectURL(result.blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = attachment.name || result.fileName || 'file';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
  } catch (error) {
    notify?.(error.message, 'error');
  }
}

// Icon, name and size of an attached file with Preview and Download.
export function AttachmentRow({ attachment, onPreview, notify }) {
  const [downloading, setDownloading] = useState(false);
  if (!attachment) return null;
  async function download() {
    setDownloading(true);
    try {await downloadAttachment(attachment, notify);} finally {setDownloading(false);}
  }
  return <div className="attachment-row">
    <FileTypeIcon name={attachment.name} contentType={attachment.contentType} size={20} />
    <div className="attachment-text"><b title={attachment.name}>{attachment.name}</b><small>{formatFileSize(attachment.size)}</small></div>
    <div className="attachment-actions">
      {onPreview && <button type="button" className="button quiet small" onClick={onPreview}><Eye size={14} /> {t("Preview")}</button>}
      <button type="button" className="button quiet small" onClick={download} disabled={downloading} aria-busy={downloading}><Download size={14} /> {t("Download")}</button>
    </div>
  </div>;
}

// Shown in place of a preview for files the browser cannot render.
export function noPreviewText(attachment) {
  const kind = fileKind(attachment?.name, attachment?.contentType);
  if (kind === 'word') return t("Word files can’t be previewed in the browser. Download the file to open it in Word, Google Docs or another editor.");
  if (kind === 'image') return t("This photo format can’t be previewed in every browser. Download the file to view it.");
  return t("This file type can’t be previewed in the browser. Download it to open it in the appropriate application.");
}
