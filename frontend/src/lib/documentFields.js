// The content part of a document save: what changed between a file and a
// Google Docs link. Only new content is sent, because the server sends a
// student's document back for review whenever its file or link changes.
export function documentContentFields({ doc = null, source, file = null, link = '' }) {
  const fields = {};
  if (source === 'file') {
    if (file) fields.file = file;
    // A new file replaces a link; keeping the stored file keeps the link too.
    if (file && doc?.google_docs_url) fields.google_docs_url = '';
    return fields;
  }
  if (!doc || link !== (doc.google_docs_url || '')) fields.google_docs_url = link;
  if (doc?.has_file) fields.file = null;
  return fields;
}
