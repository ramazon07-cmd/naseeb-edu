import { useEffect, useState } from 'react';
import { t } from '../i18n';
import { api } from '../api';
import { formatFileSize } from '../lib/format';
import { createBlobUrlCache } from '../lib/blobUrlCache';
import { canPreviewInBrowser } from '../lib/fileUpload';
import { FileTypeIcon } from './files';

// Thumbnails survive the chat's polling re-renders and reopening a chat.
const thumbnails = createBlobUrlCache({ max: 48 });

// A message's private file in the shape the preview modal and download helpers use.
export function messageAttachment(message) {
  const file = message?.attachment_file;
  if (!file || message.deleted_at) return null;
  return {
    name: file.name || t("Attachment"), size: file.size, contentType: file.content_type,
    isImage: Boolean(file.is_image),
    previewable: file.previewable ?? canPreviewInBrowser(file.name),
    load: () => api.messageAttachment(message.id), download: () => api.downloadMessageAttachment(message.id),
  };
}

function Thumbnail({ messageId, attachment }) {
  const [url, setUrl] = useState(() => thumbnails.peek(messageId));
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    thumbnails.load(messageId, () => attachment.load().then((result) => result.blob))
      .then((next) => { if (active) setUrl(next); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [messageId]); // eslint-disable-line react-hooks/exhaustive-deps -- one load per message
  if (failed) return <span className="message-thumb-fallback"><FileTypeIcon name={attachment.name} contentType={attachment.contentType} size={22} /></span>;
  return url ? <img src={url} alt={attachment.name} /> : <span className="message-thumb-loading" aria-hidden="true" />;
}

// A photo shows as a thumbnail; other files as a chip. Both open the secure preview.
export function MessageAttachment({ message, onOpen }) {
  const attachment = messageAttachment(message);
  if (!attachment) return null;
  if (attachment.isImage && attachment.previewable) {
    return <button type="button" className="message-attachment-thumb" onClick={() => onOpen(attachment)} aria-label={`${t("Open photo")}: ${attachment.name}`}><Thumbnail messageId={message.id} attachment={attachment} /></button>;
  }
  return <button type="button" className="message-attachment-chip" onClick={() => onOpen(attachment)}><FileTypeIcon name={attachment.name} contentType={attachment.contentType} size={20} /><span><b title={attachment.name}>{attachment.name}</b><small>{formatFileSize(attachment.size)}</small></span></button>;
}
