// Only web URLs are navigable. Deleted messages never contribute shared items.
// Files sent in the chat come first in their message: photos under Media,
// PDFs and Word documents under Files.
export function collectSharedItems(messages) {
  const seen = new Set();
  return messages.flatMap((message) => {
    if (message.deleted_at) return [];
    const file = message.attachment_file;
    const attached = file ? [{key: `attachment-${message.id}`, name: file.name, size: file.size, kind: file.is_image ? 'media' : 'files', messageId: message.id, attachment: true}] : [];
    return [...attached, ...(message.body?.match(/https?:\/\/[^\s<>"']+/gi) || []).flatMap((raw) => {
      try {
        const url = new URL(raw.replace(/[.,;:!?)}\]]+$/, ''));
        if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || seen.has(url.href)) return [];
        seen.add(url.href);
        const extension = url.pathname.split('.').pop().toLowerCase();
        const kind = /^(png|jpe?g|gif|webp|avif|mp4|webm|mov)$/.test(extension) ? 'media' : /^(pdf|docx?|xlsx?|pptx?|txt|csv|zip)$/.test(extension) ? 'files' : 'links';
        return [{key: url.href, url: url.href, host: url.hostname, name: decodeURIComponent(url.pathname.split('/').pop()) || url.hostname, kind, messageId: message.id}];
      } catch { return []; }
    })];
  });
}
