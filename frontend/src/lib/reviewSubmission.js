// What a review item actually carries from the student. Review shows it and
// keeps Approve off when nothing was sent: a document with no file or link, a
// task with no answer, file or link. An achievement without proof stays approvable:
// counselors often verify awards some other way.
export function hasSubmission(kind, record) {
  if (!record) return false;
  if (kind === 'document') return Boolean(record.has_file || record.google_docs_url);
  if (kind === 'task') return Boolean(String(record.student_response || '').trim() || record.has_submission_file || record.submission_url || (record.submission_essay_detail && Number(record.submission_essay_detail.word_count) > 0));
  return true;
}

// The status a counselor should read. A document marked uploaded or reviewing
// with no file or link attached has not really been sent (the API refuses to
// save one, but older rows exist), so it reads as required, as the Overview says.
export function documentStatus(doc) {
  return ['uploaded', 'reviewing'].includes(doc.status) && !hasSubmission('document', doc) ? 'required' : doc.status;
}

// Only files the browser shows as themselves (no script) may open in a new tab
// from a same-origin blob URL.
export function opensInTab(contentType = '') {
  const type = String(contentType).split(';')[0].trim().toLowerCase();
  return type === 'application/pdf' || ['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(type);
}
