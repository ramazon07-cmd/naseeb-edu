import { useState } from 'react';
import { api } from '../api';
import { t, tp, tx } from '../i18n';
import { Modal, Badge, Empty } from '../components/ui';
import { Field, PortalTabs } from '../components/forms';
import { label, initials } from '../lib/labels';
import { ShieldCheck, Send, MessageSquareText, Plus, Eye } from 'lucide-react';
import { dateTimeText, dateText, joinParts } from '../lib/format';
import { matchesQuery } from '../lib/searchIndex';
import { isPlatformAdmin } from '../lib/roles';
import { usePagedList } from '../hooks/usePagedList';
import { useSupportCounts } from '../hooks/useSupportCounts';
import { LoadMore, PagedListError, firstPageLoading } from '../components/paged';

export const SUPPORT_CATEGORIES = ['technical', 'account', 'academic', 'application', 'billing', 'other'];

export const SUPPORT_STATUSES = ['open', 'in_progress', 'resolved', 'closed'];

export function SupportTicketForm({ onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.create('support-tickets', {
        category: values.get('category'),
        subject: String(values.get('subject') || '').trim(),
        message: String(values.get('message') || '').trim()
      });
      notify(t("Support request sent."));
      onSaved();
    } catch (error) {
      notify(error.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("New support request")} onClose={onClose}><form className="form-grid support-form" onSubmit={submit}>
    <Field label={t("Category")}><select name="category" defaultValue="technical" required>{SUPPORT_CATEGORIES.map((category) => <option key={category} value={category}>{label(category)}</option>)}</select></Field>
    <Field label={t("Subject")}><input name="subject" maxLength="180" placeholder={t("Briefly describe the issue")} required /></Field>
    <Field label={t("Message")}><textarea name="message" maxLength="5000" rows="7" placeholder={t("What happened, where did it happen, and what did you expect?")} required /></Field>
    <div className="support-privacy-note form-wide"><ShieldCheck size={18} /><span>{t("Do not include passwords, payment details, passport numbers, or other sensitive credentials.")}</span></div>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Sending…") : <><Send size={16} /> {t("Send request")}</>}</button></div>
  </form></Modal>;
}

export function SupportResponseModal({ ticket, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      await api.update('support-tickets', ticket.id, {
        status: values.get('status'),
        admin_response: String(values.get('admin_response') || '').trim()
      });
      notify(t("Support response saved."));
      onSaved();
    } catch (error) {
      notify(error.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={t("Respond to support request")} onClose={onClose}><form className="form-grid support-form" onSubmit={submit}>
    <div className="support-request-preview form-wide"><span><Badge>{ticket.category}</Badge><Badge>{ticket.status}</Badge></span><h3>{ticket.subject}</h3><p>{ticket.message}</p><small>{joinParts(ticket.requester_name, ticket.requester_role && label(ticket.requester_role), dateTimeText(ticket.created_at))}</small></div>
    <Field label={t("Status")}><select name="status" defaultValue={ticket.status}>{SUPPORT_STATUSES.map((status) => <option key={status} value={status}>{label(status)}</option>)}</select></Field>
    <Field label={t("Admin response")}><textarea name="admin_response" defaultValue={ticket.admin_response} maxLength="5000" rows="7" placeholder={t("Write a clear resolution or next step.")} required /></Field>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : <><Send size={16} /> {t("Save response")}</>}</button></div>
  </form></Modal>;
}

export function SupportTicketDetail({ ticket, user, onClose, onRespond }) {
  const admin = isPlatformAdmin(user);
  return <Modal title={ticket.subject} onClose={onClose}><div className="support-ticket-detail">
    <header><div><Badge>{ticket.category}</Badge><Badge>{ticket.status}</Badge>{ticket.has_unread_response && !admin && <Badge tone="unread">{t("New response")}</Badge>}</div><small>{joinParts(tx`Created ${dateTimeText(ticket.created_at)}`, ticket.updated_at && ticket.updated_at !== ticket.created_at && tx`Updated ${dateTimeText(ticket.updated_at)}`)}</small></header>
    {admin && <div className="support-requester"><span className="avatar">{initials(ticket.requester_name)}</span><div><b>{ticket.requester_name}</b><small>{label(ticket.requester_role)}</small></div></div>}
    <section><span className="eyebrow">{t("REQUEST")}</span><p>{ticket.message}</p></section>
    <section className={`support-response ${ticket.admin_response ? 'answered' : ''}`}><span className="eyebrow">{t("SUPPORT RESPONSE")}</span>{ticket.admin_response ? <><p>{ticket.admin_response}</p><small>{joinParts(ticket.responded_by_name || t("Naseeb Edu Support"), dateTimeText(ticket.responded_at))}</small></> : <p className="muted-copy">{t("Support has not responded yet. Return to this page later; a badge will appear in the Support menu when a response is ready.")}</p>}</section>
    <footer><button className="button quiet" onClick={onClose}>{t("Close")}</button>{admin && <button className="button primary" onClick={onRespond}><MessageSquareText size={16} /> {t("Respond")}</button>}</footer>
  </div></Modal>;
}

export function SupportPage({ user, data, query, reload, notify }) {
  const [tab, setTab] = useState('all');
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState(null);
  const [responding, setResponding] = useState(null);
  const [countsVersion, setCountsVersion] = useState(0);
  const admin = isPlatformAdmin(user);
  const search = query.trim().toLowerCase();
  // Admins see every ticket on the platform: paged and counted on the server.
  // Everyone else sees only their own requests, already in memory.
  const queue = usePagedList('support-tickets', { search: query, filters: { status: tab }, ordering: '-updated', enabled: admin });
  const counts = useSupportCounts(admin, countsVersion);
  const own = data.supportTickets;
  const tickets = admin ? queue.items : own.filter((ticket) => (tab === 'all' || ticket.status === tab) && (!search || matchesQuery(ticket, search)));
  const totalCount = admin ? counts.total : own.length;
  const activeCount = admin ? counts.open + counts.inProgress : own.filter((ticket) => ['open', 'in_progress'].includes(ticket.status)).length;
  const unreadCount = own.filter((ticket) => ticket.has_unread_response).length;

  async function openTicket(ticket) {
    setSelected(ticket);
    if (!admin && ticket.has_unread_response) {
      try {
        await api.markSupportViewed(ticket.id);
        setSelected((current) => current?.id === ticket.id ? { ...current, has_unread_response: false, requester_viewed_at: new Date().toISOString() } : current);
        await reload();
      } catch (error) {
        notify(error.message, 'error');
      }
    }
  }

  function saved() {
    setCountsVersion((version) => version + 1);
    setCreating(false);
    setResponding(null);
    setSelected(null);
    reload();
  }

  return <div className="section-stack support-page">
    <section className="support-hero"><div><span className="eyebrow">{t("NASEEB EDU SUPPORT")}</span><h2>{admin ? t("Support requests") : t("Ask the Naseeb team")}</h2><p>{admin ? t("Review requests from students, schools, and counselors in one focused queue.") : t("Tell us what you need, track its progress here, and return when the Naseeb team replies.")}</p></div>{!admin && <button className="button primary" onClick={() => setCreating(true)}><Plus size={17} /> {t("New request")}</button>}</section>
    <div className="support-summary"><article><span>{admin ? t("All requests") : t("My requests")}</span><strong>{totalCount}</strong></article><article><span>{t("Active")}</span><strong>{activeCount}</strong></article><article><span>{admin ? t("Resolved") : t("New responses")}</span><strong>{admin ? counts.resolved : unreadCount}</strong></article></div>
    <section className="support-list"><div className="support-toolbar"><PortalTabs active={tab} onChange={setTab} items={[["all", "All"], ["open", "Open"], ["in_progress", "In progress"], ["resolved", "Resolved"], ["closed", "Closed"]]} /><small>{tp('{n} request|{n} requests', tickets.length, { n: `${tickets.length}${admin && queue.hasMore ? '+' : ''}` })}</small></div>
      <div className="support-ticket-grid">{tickets.map((ticket) => <article className={`support-ticket-card ${ticket.has_unread_response && !admin ? 'has-new-response' : ''}`} key={ticket.id}><div className="support-ticket-copy"><header><div><Badge>{ticket.category}</Badge><Badge>{ticket.status}</Badge>{ticket.has_unread_response && !admin && <Badge tone="unread">{t("New response")}</Badge>}</div><time>{dateText(ticket.updated_at)}</time></header><h3>{ticket.subject}</h3><p>{ticket.message}</p>{admin && <div className="support-requester compact"><span className="avatar">{initials(ticket.requester_name)}</span><div><b>{ticket.requester_name}</b><small>{label(ticket.requester_role)}</small></div></div>}</div><footer><small>{ticket.admin_response ? tx`Answered by ${ticket.responded_by_name || t("Support")}` : t("Awaiting support response")}</small><div><button className="button quiet small" onClick={() => openTicket(ticket)}><Eye size={14} /> {ticket.has_unread_response && !admin ? t("Read response") : t("View")}</button>{admin && <button className="button primary small" onClick={() => setResponding(ticket)}><MessageSquareText size={14} /> {t("Respond")}</button>}</div></footer></article>)}{admin && firstPageLoading(queue) && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}{(!admin || queue.loaded) && !tickets.length && <Empty text={totalCount ? t("No requests match this filter.") : admin ? t("No support requests have been submitted.") : t("You have not sent a support request yet.")} />}</div>
      {admin && <><PagedListError list={queue} /><LoadMore list={queue} /></>}
    </section>
    {creating && <SupportTicketForm onClose={() => setCreating(false)} onSaved={saved} notify={notify} />}
    {selected && <SupportTicketDetail ticket={selected} user={user} onClose={() => setSelected(null)} onRespond={() => {setResponding(selected);setSelected(null);}} />}
    {responding && <SupportResponseModal ticket={responding} onClose={() => setResponding(null)} onSaved={saved} notify={notify} />}
  </div>;
}
