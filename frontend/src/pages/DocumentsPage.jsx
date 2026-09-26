import { useRef, useState } from 'react';
import { api } from '../api';
import { t } from '../i18n';
import { Panel, Empty, Modal } from '../components/ui';
import { Plus, CheckCircle2, ShieldCheck, Pencil, UploadCloud, Link2 } from 'lucide-react';
import { Record } from '../components/records';
import { studentName } from '../lib/format';
import { label, ownStudent } from '../lib/labels';
import { GoogleDocsActions, DocumentPreviewModal } from '../components/documents';
import { AttachmentRow, FileField, UploadError, documentAttachment, useFileUpload } from '../components/files';
import { isCounselor } from '../lib/roles';
import { ChoiceCards, Field } from '../components/forms';
import { useRecordList } from '../hooks/useRecordList';
import { LoadMore, PagedListError, StudentPicker, firstPageLoading } from '../components/paged';
import { titleFromFileName, toFormData } from '../lib/fileUpload';
import { documentContentFields } from '../lib/documentFields';

const DOCUMENT_TYPES = ['passport', 'transcript', 'ielts', 'sat', 'cv', 'recommendation', 'essay', 'certificate', 'other'];
const DOCUMENT_STATUSES = ['required', 'uploaded', 'reviewing', 'approved', 'rejected'];

// Staff manage every document they can see; a student edits their own until it is approved.
export function canEditDocument(user, doc) {
  return isCounselor(user) || (user?.role === 'student' && doc.status !== 'approved');
}

export function DocumentsPage({ user, data, query, reload, notify, typeFilter = '', title = 'Documents' }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [previewing, setPreviewing] = useState(null);
  const list = useRecordList({
    user, data, endpoint: 'documents', query,
    filters: { document_type: typeFilter },
    localFilter: typeFilter ? (item) => item.document_type === typeFilter : null,
  });
  const docs = list.items;
  async function approve(doc) {try {await api.update('documents', doc.id, { status: 'approved' });notify(t("Document approved."));reload();} catch (err) {notify(err.message, 'error');}}
  function closeForm() {setOpen(false);setEditing(null);}
  return <><Panel title={title} action={<button className="button primary" onClick={() => setOpen(true)}><Plus size={16} /> {typeFilter === 'certificate' ? t("Add certificate") : t("Add document")}</button>}><div className="record-list">{docs.map((doc) => <Record key={doc.id} title={doc.title} meta={`${doc.student_name || studentName(data, doc.student)} • ${label(doc.document_type)}`} description={doc.counselor_comment} badge={doc.status} attachment={<AttachmentRow attachment={documentAttachment(doc)} onPreview={() => setPreviewing(doc)} notify={notify} />} actions={<><GoogleDocsActions item={doc} onPreview={doc.has_file ? undefined : () => setPreviewing(doc)} />{isCounselor(user) && doc.status !== 'approved' && <button className="button quiet small" onClick={() => approve(doc)}><CheckCircle2 size={15} /> {t("Approve")}</button>}{canEditDocument(user, doc) && <button type="button" className="icon-button" onClick={() => {setEditing(doc);setOpen(true);}} aria-label={t("Edit document")} title={t("Edit document")}><Pencil size={15} /></button>}</>} />)}{firstPageLoading(list) && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}{list.loaded && !docs.length && <Empty />}</div><PagedListError list={list} /><LoadMore list={list} /></Panel>{open && <DocumentForm user={user} data={data} document={editing} defaultType={typeFilter} onClose={closeForm} onSaved={() => {closeForm();reload();}} notify={notify} />}{previewing && <DocumentPreviewModal document={previewing} onClose={() => setPreviewing(null)} notify={notify} />}</>;
}

const SOURCE_OPTIONS = [
  { value: 'file', label: 'Upload a file', description: 'PDF, Word or a photo from your device', icon: UploadCloud },
  { value: 'link', label: 'Google Docs link', description: 'Share a document from Google Docs', icon: Link2 },
];

export function DocumentForm({ user, data, document: doc = null, defaultType = '', onClose, onSaved, notify }) {
  const counselor = isCounselor(user);
  const formRef = useRef(null);
  const [source, setSource] = useState(doc?.google_docs_url && !doc?.has_file ? 'link' : 'file');
  const [file, setFile] = useState(null);
  const [fileError, setFileError] = useState('');
  const [linkError, setLinkError] = useState('');
  const [title, setTitle] = useState(doc?.title || '');
  const [status, setStatus] = useState(doc?.status || 'uploaded');
  const upload = useFileUpload();
  const current = doc?.has_file ? { name: doc.file_name, size: doc.file_size, contentType: doc.file_content_type } : null;
  const contentRequired = !counselor || status !== 'required';

  function chooseFile(next) {
    setFile(next);
    setFileError('');
    if (next && !title.trim()) setTitle(titleFromFileName(next.name));
  }

  async function submit(event) {
    event.preventDefault();
    if (upload.uploading) return;
    const values = new FormData(event.currentTarget);
    const link = String(values.get('google_docs_url') || '').trim();
    if (source === 'file' && contentRequired && !file && !current) {
      setFileError(t("Choose a file to upload."));
      return;
    }
    if (source === 'link' && contentRequired && !link) {
      setLinkError(t("Add a Google Docs link."));
      return;
    }
    const fields = { title: title.trim(), document_type: values.get('document_type') || defaultType || 'other' };
    if (counselor) fields.status = status;
    if (!doc) fields.student = counselor ? values.get('student') : ownStudent(data)?.id;
    Object.assign(fields, documentContentFields({ doc, source, file, link }));
    const outcome = await upload.run((options) => api.saveWithFiles('documents', doc?.id, toFormData(fields), options));
    if (outcome.ok) {
      notify(file ? t("File uploaded.") : doc ? t("Document updated.") : status === 'required' && counselor ? t("Document requirement created.") : t("Document link saved."));
      onSaved();
    } else if (outcome.cancelled) {
      notify(t("Upload cancelled."));
    }
  }

  const heading = doc ? t("Edit document") : defaultType === 'certificate' ? t("Add certificate") : t("Add document");
  return <Modal title={heading} onClose={() => {upload.cancel();onClose();}}><form ref={formRef} className="form-grid document-form" onSubmit={submit}>
    {counselor && !doc && <StudentPicker required />}
    <Field label={t("Title")}><input name="title" value={title} onChange={(event) => setTitle(event.target.value)} required /></Field>
    <Field label={t("Type")}><select name="document_type" defaultValue={doc?.document_type || defaultType || 'passport'} disabled={Boolean(defaultType)}>{DOCUMENT_TYPES.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select>{defaultType && <input type="hidden" name="document_type" value={defaultType} />}</Field>
    {counselor && <Field label={t("Status")}><select name="status" value={status} onChange={(event) => setStatus(event.target.value)}>{DOCUMENT_STATUSES.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></Field>}
    <div className="form-wide"><ChoiceCards name="document_source" label={t("How do you want to add it?")} value={source} onChange={(value) => {setSource(value);setFileError('');setLinkError('');upload.clearError();}} options={SOURCE_OPTIONS} /></div>
    {source === 'file' ? <FileField label={t("File")} file={file} onFileChange={chooseFile} current={current} error={fileError} upload={upload} required={contentRequired} /> : <>
      <Field label={t("Google Docs URL")} error={linkError}><input name="google_docs_url" type="url" defaultValue={doc?.google_docs_url || ''} placeholder={t("https://docs.google.com/document/d/.../edit")} onChange={() => setLinkError('')} /></Field>
      {current && <p className="form-wide field-hint">{t("Saving a link removes the uploaded file from this document.")}</p>}
      <div className="form-wide google-doc-sharing-hint"><ShieldCheck size={16} /><span>{t("Set Google Docs sharing to Viewer or “Anyone with the link” to enable the preview.")}</span></div>
    </>}
    <UploadError message={upload.error} onRetry={() => formRef.current?.requestSubmit()} />
    <div className="form-actions"><button type="button" className="button quiet" onClick={() => {upload.cancel();onClose();}}>{t("Cancel")}</button><button className="button primary" disabled={upload.uploading} aria-busy={upload.uploading}>{upload.uploading ? t("Saving…") : t("Save")}</button></div>
  </form></Modal>;
}
