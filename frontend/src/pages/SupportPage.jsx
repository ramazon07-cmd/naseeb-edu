import { useState } from 'react';
import { api } from '../api';
import { t, tp, tx } from '../i18n';
import { Modal, Badge, Empty } from '../components/ui';
import { Field, PortalTabs } from '../components/forms';
import { label, initials } from '../lib/labels';
import { ShieldCheck, Send, MessageSquareText, Plus, Eye, LifeBuoy, Bell, Clock3, Inbox, CircleHelp as HelpIcon } from 'lucide-react';
import { SupportViewModal } from '../components/SupportViewModal';
import { dateTimeText, dateText, joinParts } from '../lib/format';
import { matchesQuery } from '../lib/searchIndex';
import { isPlatformAdmin } from '../lib/roles';
import { usePagedList } from '../hooks/usePagedList';
import { useSupportCounts } from '../hooks/useSupportCounts';
import { LoadMore, PagedListError, firstPageLoading } from '../components/paged';
import { BlueButton, Chip, EmptyState, GlassCard, PageHeader } from '../design/blue/ui';
import '../design/pages/forms-blue.css';
import '../design/pages/support-blue.css';

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

// Each support answer, oldest first; earlier tickets fall back to their single answer.
// The chip follows the real ticket status; a ticket that is still open falls back to whether the team has replied.
function statusChip(ticket) {
  const replied = repliesOf(ticket).length > 0;
  if (ticket.status === 'closed') return { variant: 'default', text: t('Closed') };
  if (ticket.status === 'resolved') return { variant: 'ok', text: t('Resolved') };
  if (ticket.status === 'in_progress') return { variant: replied ? 'ok' : 'default', text: replied ? t('Answered') : t('In progress') };
  return replied ? { variant: 'ok', text: t('Answered') } : { variant: 'warn', text: t('Waiting for a reply') };
}
const repliesOf = (ticket) => ticket.replies?.length ? ticket.replies : ticket.admin_response ? [{ id: 'latest', body: ticket.admin_response, author_name: ticket.responded_by_name, created_at: ticket.responded_at }] : [];

// The requester's account, opened in the audited read-only support view.
function RequesterAccount({ ticket, onOpenAccount }) {
  return <div className="support-requester"><span className="avatar">{initials(ticket.requester_name)}</span><div><b>{ticket.requester_name}</b><small>{label(ticket.requester_role)}</small></div>{onOpenAccount && <button type="button" className="button quiet small" onClick={() => onOpenAccount({ id: ticket.requester, full_name: ticket.requester_name, role: ticket.requester_role })}><LifeBuoy size={14} /> {t("Open account")}</button>}</div>;
}

export function SupportResponseModal({ ticket, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const replies = repliesOf(ticket);
  async function submit(event) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const reply = String(values.get('reply') || '').trim();
    const status = values.get('status');
    // A new answer is added to the history; changing only the status is fine too.
    if (!reply && status === ticket.status) {
      notify(t("Write a reply or change the status."), 'error');
      return;
    }
    setSaving(true);
    try {
      await api.update('support-tickets', ticket.id, reply ? { status, reply } : { status });
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
    {replies.map((item) => <div className="support-request-preview form-wide" key={item.id}><p>{item.body}</p><small>{joinParts(item.author_name || t("Naseeb Edu Support"), dateTimeText(item.created_at))}</small></div>)}
    <Field label={t("Status")}><select name="status" defaultValue={ticket.status}>{SUPPORT_STATUSES.map((status) => <option key={status} value={status}>{label(status)}</option>)}</select></Field>
    <Field label={t("New reply")}><textarea name="reply" maxLength="5000" rows="7" placeholder={t("Write a clear resolution or next step.")} /></Field>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : <><Send size={16} /> {t("Save response")}</>}</button></div>
  </form></Modal>;
}

export function SupportTicketDetail({ ticket, user, onClose, onRespond, onOpenAccount }) {
  const admin = isPlatformAdmin(user);
  const replies = repliesOf(ticket);
  return <Modal title={ticket.subject} onClose={onClose}><div className="support-ticket-detail">
    <header><div><Badge>{ticket.category}</Badge><Badge>{ticket.status}</Badge>{ticket.has_unread_response && !admin && <Badge tone="unread">{t("New response")}</Badge>}</div><small>{joinParts(tx`Created ${dateTimeText(ticket.created_at)}`, ticket.updated_at && ticket.updated_at !== ticket.created_at && tx`Updated ${dateTimeText(ticket.updated_at)}`)}</small></header>
    {admin && <RequesterAccount ticket={ticket} onOpenAccount={onOpenAccount} />}
    <section><span className="eyebrow">{t("REQUEST")}</span><p>{ticket.message}</p></section>
    {replies.map((item) => <section className="support-response answered" key={item.id}><span className="eyebrow">{t("SUPPORT RESPONSE")}</span><p>{item.body}</p><small>{joinParts(item.author_name || t("Naseeb Edu Support"), dateTimeText(item.created_at))}</small></section>)}
    {!replies.length && <section className="support-response"><span className="eyebrow">{t("SUPPORT RESPONSE")}</span><p className="muted-copy">{t("Support has not responded yet. Return to this page later; a badge will appear in the Support menu when a response is ready.")}</p></section>}
    <footer><button className="button quiet" onClick={onClose}>{t("Close")}</button>{admin && <button className="button primary" onClick={onRespond}><MessageSquareText size={16} /> {t("Respond")}</button>}</footer>
  </div></Modal>;
}

function ClassicSupportPage({ user, data, query, reload, notify, moreTickets = false, loadMoreTickets }) {
  const [tab, setTab] = useState('all');
  const [loadingMore, setLoadingMore] = useState(false);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState(null);
  const [responding, setResponding] = useState(null);
  const [account, setAccount] = useState(null);
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
      {!admin && moreTickets && <div className="paged-list-footer"><button type="button" className="button quiet small" disabled={loadingMore} aria-busy={loadingMore} onClick={() => {setLoadingMore(true);loadMoreTickets().catch((err) => notify(err.message, 'error')).finally(() => setLoadingMore(false));}}>{loadingMore ? t("Loading…") : t("Load more")}</button></div>}
    </section>
    {creating && <SupportTicketForm onClose={() => setCreating(false)} onSaved={saved} notify={notify} />}
    {selected && <SupportTicketDetail ticket={selected} user={user} onClose={() => setSelected(null)} onRespond={() => {setResponding(selected);setSelected(null);}} onOpenAccount={(requester) => {setAccount(requester);setSelected(null);}} />}
    {responding && <SupportResponseModal ticket={responding} onClose={() => setResponding(null)} onSaved={saved} notify={notify} />}
    {account && <SupportViewModal account={account} onClose={() => setAccount(null)} notify={notify} />}
  </div>;
}

export function SupportPage(props) {
  return props.user.role === 'student' ? <StudentSupport {...props} /> : <ClassicSupportPage {...props} />;
}

// The student's page (blue design): own tickets on the left, the open thread or a new-ticket form on the right.
// Same data and requests as the classic page (the tickets already loaded, one create, one "viewed" mark).
function StudentSupport({ data, reload, notify, moreTickets = false, loadMoreTickets }) {
  const tickets = data.supportTickets;
  const [openId, setOpenId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const current = tickets.find((ticket) => ticket.id === openId) || null;
  const unread = tickets.filter((ticket) => ticket.has_unread_response).length;
  const replies = current ? repliesOf(current) : [];

  async function openTicket(ticket) {
    setOpenId(ticket.id);
    if (ticket.has_unread_response) {
      try { await api.markSupportViewed(ticket.id); await reload(); } catch (error) { notify(error.message, 'error'); }
    }
  }
  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const subject = String(values.get('subject') || '').trim();
    const message = String(values.get('message') || '').trim();
    if (!subject || !message) { notify(t('Write a subject and a message.'), 'error'); return; }
    setSaving(true);
    try {
      const created = await api.create('support-tickets', { category: values.get('category'), subject, message });
      notify(t('Support request sent.'));
      form.reset();
      if (created?.id) setOpenId(created.id);
      await reload();
    } catch (error) {
      notify(error.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  const form = <form className="nb-sp-form" onSubmit={submit}>
    <label className="nb-fld"><span>{t('Category')}</span><select name="category" defaultValue="technical" required>{SUPPORT_CATEGORIES.map((category) => <option key={category} value={category}>{label(category)}</option>)}</select></label>
    <label className="nb-fld"><span>{t('Subject')}</span><input name="subject" maxLength="180" autoComplete="off" placeholder={t('Briefly describe the issue')} required /></label>
    <label className="nb-fld"><span>{t('Message')}</span><textarea name="message" maxLength="5000" rows="6" placeholder={t('What happened, where did it happen, and what did you expect?')} required /></label>
    <p className="nb-sp-note"><ShieldCheck size={16} aria-hidden="true" />{t('Do not include passwords, payment details, passport numbers, or other sensitive credentials.')}</p>
    <div className="nb-sp-acts"><BlueButton type="submit" icon={Send} disabled={saving} aria-busy={saving}>{saving ? t('Sending…') : t('Send request')}</BlueButton></div>
  </form>;
  return <div className="nb-sp">
    <PageHeader title={t('Support')} subtitle={t('Help from the Naseeb team.')} actions={tickets.length > 0 && current ? <BlueButton size="sm" icon={Plus} onClick={() => setOpenId(null)}>{t('New request')}</BlueButton> : null} />
    <div className="nb-sp-grid">
      <GlassCard className="nb-sp-list" title={t('Your requests')} icon={Inbox} action={<Chip variant={unread ? 'new' : 'default'} icon={Bell}>{t('{n} unread', { n: unread })}</Chip>}>
        {tickets.length ? <ul className="nb-sp-tickets">{tickets.map((ticket) => <li key={ticket.id}>
          <button type="button" className={ticket.id === openId ? 'is-on' : ''} aria-current={ticket.id === openId ? 'true' : undefined} onClick={() => openTicket(ticket)}>
            <span className="nb-sp-ti" aria-hidden="true"><MessageSquareText size={18} /></span>
            <span className="nb-sp-tt"><b>{ticket.subject}</b><small>{dateText(ticket.updated_at || ticket.created_at)}</small></span>
            {ticket.has_unread_response ? <Chip variant="new">{t('New response')}</Chip> : <Chip variant={statusChip(ticket).variant}>{statusChip(ticket).text}</Chip>}
          </button>
        </li>)}</ul>
          : <EmptyState icon={Inbox} title={t('No requests yet')} text={t('Write to the Naseeb team. The reply arrives here, in the same thread.')} />}
        {moreTickets && <div className="nb-sp-more"><BlueButton variant="ghost" size="sm" disabled={loadingMore} aria-busy={loadingMore} onClick={() => { setLoadingMore(true); loadMoreTickets().catch((err) => notify(err.message, 'error')).finally(() => setLoadingMore(false)); }}>{loadingMore ? t('Loading…') : t('Load more')}</BlueButton></div>}
      </GlassCard>
      <GlassCard tone="solid" className="nb-sp-main" title={current ? current.subject : t('New request')} icon={current ? MessageSquareText : Plus} headingLevel="h2">
        {current ? <div className="nb-sp-thread" aria-live="polite">
          <div className="nb-sp-meta"><Chip variant="default">{label(current.category)}</Chip><Chip variant={statusChip(current).variant} icon={statusChip(current).variant === 'warn' ? Clock3 : undefined}>{statusChip(current).text}</Chip><small>{dateTimeText(current.created_at)}</small></div>
          <div className="nb-sp-msg is-mine"><p>{current.message}</p><time>{dateTimeText(current.created_at)}</time></div>
          {replies.map((item) => <div className="nb-sp-msg" key={item.id}><b>{item.author_name || t('Naseeb Edu Support')}</b><p>{item.body}</p><time>{dateTimeText(item.created_at)}</time></div>)}
          {!replies.length && ['open', 'in_progress'].includes(current.status) && <p className="nb-sp-wait"><Clock3 size={16} aria-hidden="true" />{t('The Naseeb team replies here. New replies show a count next to Support in the menu.')}</p>}
        </div> : form}
      </GlassCard>
    </div>
    <GlassCard className="nb-sp-how" title={t('How support works')} icon={HelpIcon}>
      <ol className="nb-sp-steps">{['You write a request: a subject and a few lines.', 'The reply arrives in the same thread. Your history stays.', 'New replies show a count next to Support in the menu.'].map((text, index) => <li key={text}><b aria-hidden="true">{index + 1}</b><span>{t(text)}</span></li>)}</ol>
    </GlassCard>
  </div>;
}
