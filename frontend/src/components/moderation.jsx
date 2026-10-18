import { ShieldAlert } from 'lucide-react';
import { api } from '../api';
import { t } from '../i18n';
import { label } from '../lib/labels';
import { dateTimeText } from '../lib/format';
import { Badge } from './ui';
import { Field } from './forms';

const OPEN_STATUSES = ['pending', 'reviewing'];

// One moderation decision on a reported message; returns the success message.
export async function moderateReport(report, mode, action = 'none', note = '') {
  if (mode === 'review') await api.reviewMessageReport(report.id);
  else if (mode === 'dismiss') await api.dismissMessageReport(report.id, { moderator_note: note });
  else await api.resolveMessageReport(report.id, { action, moderator_note: note });
  return mode === 'review' ? t("Report moved to review.") : mode === 'dismiss' ? t("Report dismissed.") : t("Moderation action applied.");
}

// A reported message with the moderator's choices: the Messages page queue and admin Moderation share it.
export function ModerationCard({ report, note, onNote, saving, onModerate }) {
  return <article className="moderation-card"><header><div><Badge>{report.reason}</Badge>{report.message_is_anonymous && <span className="anonymous-report-badge"><ShieldAlert size={13} /> {t("Anonymous post")}</span>}</div><time>{dateTimeText(report.created_at)}</time></header><blockquote>{report.message_body}</blockquote><div className="moderation-identities"><span>{t("Author")} <b>{report.sender_name}</b></span><span>{t("Reporter")} <b>{report.reporter_name}</b></span><span>{t("Channel")} <b>{report.channel_name}</b></span></div>{report.details && <p className="report-details"><b>{t("Report details:")}</b> {report.details}</p>}{OPEN_STATUSES.includes(report.status) ? <><Field label={t("Moderator note")}><textarea value={note} onChange={(event) => onNote(event.target.value)} maxLength="2000" rows="2" /></Field><footer>{report.status === 'pending' && <button className="button quiet small" disabled={saving} onClick={() => onModerate('review')}>{t("Start review")}</button>}<button className="button quiet small" disabled={saving} onClick={() => onModerate('dismiss')}>{t("Dismiss")}</button><button className="button quiet small" disabled={saving} onClick={() => onModerate('resolve', 'none')}>{t("Resolve only")}</button><button className="button danger small" disabled={saving} onClick={() => onModerate('resolve', 'content_removed')}>{t("Remove content")}</button><button className="button quiet small" disabled={saving} onClick={() => onModerate('resolve', 'muted_24h')}>{t("Mute 24h")}</button><button className="button quiet small" disabled={saving} onClick={() => onModerate('resolve', 'muted_7d')}>{t("Mute 7d")}</button></footer></> : <div className="moderation-result"><Badge>{report.status}</Badge><span>{label(report.action)}{report.reviewed_by_name ? ` · ${report.reviewed_by_name}` : ''}</span>{report.moderator_note && <p>{report.moderator_note}</p>}</div>}</article>;
}
