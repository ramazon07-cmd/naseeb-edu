import { useState, useEffect, useCallback, useRef, useMemo, useLayoutEffect, Fragment } from 'react';
import { api } from '../api';
import { t, tp, tx } from '../i18n';
import { label, fullName, initials } from '../lib/labels';
import { Modal, Empty, Badge } from '../components/ui';
import { Search, Plus, Trash2, ShieldCheck, Flag, ShieldAlert, MessageCircle, UsersRound, Globe2, BookOpen, Bookmark, MessageSquareText, FolderKanban, Pencil, ArrowLeft, Info, X, CheckCircle2, Check, Smile, Send } from 'lucide-react';
import { ChannelListSkeleton, InlineLoadError, StaffStatsSkeleton, MessageListSkeleton } from '../components/states';
import { Field, CheckboxControl, PortalTabs } from '../components/forms';
import { dateTimeText, chatStampText, dateText, clockText } from '../lib/format';
import { isTaskManager } from '../lib/roles';
import { MESSAGE_POLL, nextPollDelay } from '../lib/pollDelay';
import { createPoller } from '../lib/poller';
import { announceNotificationsChanged } from '../lib/notifications';
import { mergeNewestPage, prependOlder, restoredScrollTop, scrollAnchor } from '../lib/messageHistory';
import { createRevalidation } from '../lib/revalidation';
import ChatDetails from '../ChatDetails';
import { CounselorInboxItem, CounselorInboxThread, useCounselorInbox } from '../components/CounselorInbox';
import { COUNSELOR_INBOX } from '../lib/counselorInbox';

export function MessageChannelForm({ kind, user, onClose, onSaved, notify }) {
  const [contacts, setContacts] = useState([]);
  const [selectedMembers, setSelectedMembers] = useState([]);
  const [memberSearch, setMemberSearch] = useState('');
  const [saving, setSaving] = useState(false);
  const [contactsLoading, setContactsLoading] = useState(true);
  const [contactsError, setContactsError] = useState('');
  const [contactsAttempt, setContactsAttempt] = useState(0);
  const [recipient, setRecipient] = useState('');
  useEffect(() => {
    let active = true;
    setContactsLoading(true);
    setContactsError('');
    api.messageContacts().then((items) => active && setContacts(items || []))
      .catch((err) => active && setContactsError(err.message))
      .finally(() => active && setContactsLoading(false));
    return () => {active = false;};
  }, [contactsAttempt]);

  async function submit(event) {
    event.preventDefault();
    if (saving || kind === 'direct' && !recipient) return;
    setSaving(true);
    const values = new FormData(event.currentTarget);
    try {
      const channel = kind === 'direct' ?
      await api.openDirectChannel(Number(recipient)) :
      await api.create('message-channels', {
        kind,
        name: values.get('name')?.trim(),
        description: values.get('description')?.trim(),
        members: selectedMembers
      });
      notify(kind === 'direct' ? t("Direct conversation opened.") : kind === 'group' ? t("Group created.") : kind === 'community' ? t("Community created.") : t("Discussion created."));
      onSaved(channel);
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  const staffInterface = ['counselor', 'organization'].includes(user.role);
  const normalizedSearch = memberSearch.trim().toLowerCase();
  const visibleContacts = contacts.filter((contact) => !normalizedSearch || `${fullName(contact)} ${contact.role} ${contact.school_name || ''}`.toLowerCase().includes(normalizedSearch));
  function chooseAudience(audience) {
    if (audience === 'clear') {setSelectedMembers([]);return;}
    const matches = contacts.filter((contact) => audience === 'all' || (audience === 'students' ? contact.role === 'student' : contact.role !== 'student'));
    setSelectedMembers(matches.map((contact) => contact.id));
  }
  function toggleMember(contactId) {
    setSelectedMembers((current) => current.includes(contactId) ? current.filter((id) => id !== contactId) : [...current, contactId]);
  }

  const title = kind === 'direct' ? 'Start a direct conversation' : kind === 'discussion' ? 'Start a discussion' : `Create a ${kind}`;
  return <Modal title={t(title)} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    {kind === 'direct' ?
      <div className="direct-picker"><label className="channel-search"><Search size={16} /><input aria-label={t("Search contacts")} placeholder={t("Search contacts")} value={memberSearch} onChange={(event) => setMemberSearch(event.target.value)} /></label><div className="direct-contact-list">{contactsLoading ? <ChannelListSkeleton count={3} /> : contactsError ? <InlineLoadError message={contactsError} onRetry={() => setContactsAttempt((value) => value + 1)} /> : visibleContacts.length ? visibleContacts.map((contact) => <label className="direct-contact" key={contact.id}><input type="radio" name="contact" value={contact.id} checked={recipient === String(contact.id)} onChange={(event) => setRecipient(event.target.value)} /><span className="avatar">{initials(fullName(contact))}</span><span><b>{fullName(contact)}</b><small>{label(contact.role)}{contact.school_name ? ` · ${contact.school_name}` : ''}</small></span></label>) : <Empty text={t("No matching contacts.")} />}</div></div> :
      <><Field label={kind === 'discussion' ? t("Question or topic") : t("Channel name")}><input name="name" required maxLength="160" /></Field><Field label={t("Description")}><textarea name="description" maxLength="2000" /></Field></>}
    {['group', 'community'].includes(kind) && <fieldset className="form-wide member-picker"><legend>{tx`Initial members · ${selectedMembers.length} selected`}</legend><p>{t("Choose contacts to add to this group.")}</p>{staffInterface && <div className="audience-shortcuts"><button type="button" onClick={() => chooseAudience('students')}>{user.role === 'counselor' ? t("Assigned students") : t("School students")}</button><button type="button" onClick={() => chooseAudience('staff')}>{t("School staff")}</button><button type="button" onClick={() => chooseAudience('all')}>{t("All contacts")}</button><button type="button" onClick={() => chooseAudience('clear')}>{t("Clear")}</button></div>}<label className="member-search"><Search size={15} /><input value={memberSearch} onChange={(event) => setMemberSearch(event.target.value)} placeholder={t("Search contacts")} /></label><div>{visibleContacts.map((contact) => <CheckboxControl key={contact.id} name="members" value={contact.id} checked={selectedMembers.includes(contact.id)} onChange={() => toggleMember(contact.id)}>{fullName(contact)} · {label(contact.role)}{contact.school_name ? ` · ${contact.school_name}` : ''}</CheckboxControl>)}</div>{!visibleContacts.length && <small>{t("No matching contacts.")}</small>}</fieldset>}
    {kind === 'discussion' && <div className="alert warning form-wide">{t("Discussions are public. A user must join before posting.")}</div>}
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving || kind === 'direct' && (!recipient || contactsLoading || !!contactsError)} aria-busy={saving}>{saving ? t("Saving…") : t("Continue")}</button></div>
  </form></Modal>;
}

export function ChannelMembersModal({ channel, user, onClose, onChanged, notify }) {
  const [members, setMembers] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [selectedUser, setSelectedUser] = useState('');
  const [selectedRole, setSelectedRole] = useState('member');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [memberItems, contactItems] = await Promise.all([api.channelMembers(channel.id), api.messageContacts()]);
      setMembers(memberItems || []);
      setContacts(contactItems || []);
    } catch (err) {notify(err.message, 'error');}
  }, [channel.id, notify]);

  useEffect(() => {load();}, [load]);
  const memberIds = new Set(members.map((membership) => membership.user));
  const available = contacts.filter((contact) => !memberIds.has(contact.id));

  async function addMember(event) {
    event.preventDefault();
    if (!selectedUser) return;
    setSaving(true);
    try {
      await api.addChannelMember(channel.id, Number(selectedUser), selectedRole);
      setSelectedUser('');
      await load();
      await onChanged();
      notify(t("Channel member added."));
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }

  async function changeRole(membership, role) {
    setSaving(true);
    try {
      await api.addChannelMember(channel.id, membership.user, role);
      await load();
      notify(tx`Member role changed to ${label(role)}.`);
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }

  async function removeMember(membership) {
    setSaving(true);
    try {
      await api.removeChannelMember(channel.id, membership.user);
      await load();
      await onChanged();
      notify(t("Channel member removed."));
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }

  return <Modal title={tx`Manage ${channel.display_name}`} onClose={onClose}><div className="member-manager"><form onSubmit={addMember}><Field label={t("Add a contact")}><select value={selectedUser} onChange={(event) => setSelectedUser(event.target.value)} required><option value="">{t("Select a contact")}</option>{available.map((contact) => <option key={contact.id} value={contact.id}>{fullName(contact)} · {label(contact.role)}</option>)}</select></Field><Field label={t("Channel role")}><select value={selectedRole} onChange={(event) => setSelectedRole(event.target.value)}><option value="member">{t("Member")}</option><option value="moderator">{t("Moderator")}</option></select></Field><button className="button primary" disabled={saving || !selectedUser}><Plus size={16} /> {t("Add")}</button></form><div className="member-manager-list">{members.map((membership) => <article key={membership.id}><span className="avatar">{initials(fullName(membership.user_detail))}</span><div><b>{fullName(membership.user_detail)}</b><small>{label(membership.user_detail?.role)}{membership.user_detail?.school_name ? ` · ${membership.user_detail.school_name}` : ''}</small></div><Badge>{membership.role}</Badge>{membership.role !== 'owner' && membership.user !== user.id && <div>{membership.role === 'member' ? <button type="button" className="button quiet small" disabled={saving} onClick={() => changeRole(membership, 'moderator')}>{t("Make moderator")}</button> : <button type="button" className="button quiet small" disabled={saving} onClick={() => changeRole(membership, 'member')}>{t("Make member")}</button>}<button type="button" className="icon-button danger" disabled={saving} onClick={() => removeMember(membership)} aria-label={tx`Remove ${fullName(membership.user_detail)}`}><Trash2 size={15} /></button></div>}</article>)}</div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Done")}</button></div></div></Modal>;
}

export function ReportMessageModal({ message, onClose, onReported, notify }) {
  const [reason, setReason] = useState('spam');
  const [details, setDetails] = useState('');
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    try {
      await api.reportChannelMessage(message.id, { reason, details: details.trim() });
      notify(t("Report submitted. Moderators will review it confidentially."));
      onReported();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }

  return <Modal title={t("Report this message")} onClose={onClose}><form className="form-grid report-message-form" onSubmit={submit}><div className="report-privacy-note form-wide"><ShieldCheck size={19} /><div><b>{t("Your report is confidential")}</b><p>{t("Only trusted school moderators can see who submitted the report. Other users and the message author cannot see your identity.")}</p></div></div><Field label={t("Reason")}><select value={reason} onChange={(event) => setReason(event.target.value)}><option value="spam">{t("Spam")}</option><option value="harassment">{t("Harassment or bullying")}</option><option value="unsafe">{t("Unsafe content")}</option><option value="privacy">{t("Privacy concern")}</option><option value="misinformation">{t("Misinformation")}</option><option value="other">{t("Other")}</option></select></Field><Field label={t("Additional details (optional)")}><textarea value={details} onChange={(event) => setDetails(event.target.value)} maxLength="2000" rows="4" placeholder={t("Briefly explain the issue to the moderator.")} /></Field><div className="reported-message-preview form-wide"><small>{t("Reported message")}</small><p>{message.body}</p></div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}><Flag size={16} /> {saving ? t("Sending…") : t("Submit report")}</button></div></form></Modal>;
}

export function ModerationQueueModal({ onClose, onChanged, notify }) {
  const [statusFilter, setStatusFilter] = useState('pending');
  const [reports, setReports] = useState([]);
  const [notes, setNotes] = useState({});
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);

  const load = useCallback(async (statusValue = statusFilter) => {
    setLoading(true);
    try {setReports((await api.messageReports(statusValue)) || []);}
    catch (err) {notify(err.message, 'error');} finally
    {setLoading(false);}
  }, [statusFilter, notify]);

  useEffect(() => {load(statusFilter);}, [statusFilter]);

  async function moderate(report, mode, action = 'none') {
    setSavingId(report.id);
    try {
      if (mode === 'review') await api.reviewMessageReport(report.id);else
      if (mode === 'dismiss') await api.dismissMessageReport(report.id, { moderator_note: notes[report.id] || '' });else
      await api.resolveMessageReport(report.id, { action, moderator_note: notes[report.id] || '' });
      notify(mode === 'review' ? t("Report moved to review.") : mode === 'dismiss' ? t("Report dismissed.") : t("Moderation action applied."));
      await load(statusFilter);
      await onChanged();
    } catch (err) {notify(err.message, 'error');} finally {setSavingId(null);}
  }

  const openStatuses = ['pending', 'reviewing'];
  return <Modal title={t("Anonymous moderation queue")} onClose={onClose}><div className="moderation-queue"><PortalTabs active={statusFilter} onChange={setStatusFilter} items={[["pending", "Pending"], ["reviewing", "Reviewing"], ["resolved", "Resolved"], ["dismissed", "Dismissed"]]} /><div className="moderation-list">{loading && <ChannelListSkeleton count={3} />}{!loading && reports.map((report) => <article className="moderation-card" key={report.id}><header><div><Badge>{report.reason}</Badge>{report.message_is_anonymous && <span className="anonymous-report-badge"><ShieldAlert size={13} /> {t("Anonymous post")}</span>}</div><time>{dateTimeText(report.created_at)}</time></header><blockquote>{report.message_body}</blockquote><div className="moderation-identities"><span>{t("Author")} <b>{report.sender_name}</b></span><span>{t("Reporter")} <b>{report.reporter_name}</b></span><span>{t("Channel")} <b>{report.channel_name}</b></span></div>{report.details && <p className="report-details"><b>{t("Report details:")}</b> {report.details}</p>}{openStatuses.includes(report.status) ? <><Field label={t("Moderator note")}><textarea value={notes[report.id] || ''} onChange={(event) => setNotes((current) => ({ ...current, [report.id]: event.target.value }))} maxLength="2000" rows="2" /></Field><footer>{report.status === 'pending' && <button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'review')}>{t("Start review")}</button>}<button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'dismiss')}>{t("Dismiss")}</button><button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'resolve', 'none')}>{t("Resolve only")}</button><button className="button danger small" disabled={savingId === report.id} onClick={() => moderate(report, 'resolve', 'content_removed')}>{t("Remove content")}</button><button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'resolve', 'muted_24h')}>{t("Mute 24h")}</button><button className="button quiet small" disabled={savingId === report.id} onClick={() => moderate(report, 'resolve', 'muted_7d')}>{t("Mute 7d")}</button></footer></> : <div className="moderation-result"><Badge>{report.status}</Badge><span>{label(report.action)}{report.reviewed_by_name ? ` · ${report.reviewed_by_name}` : ''}</span>{report.moderator_note && <p>{report.moderator_note}</p>}</div>}</article>)}{!loading && !reports.length && <Empty text={t("No reports with this status.")} />}</div><div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Done")}</button></div></div></Modal>;
}

export const CHANNEL_TABS = [["direct", "Private"], ["group", "Groups"], ["discussion", "Discussions"]];

export const CHANNEL_SPACES = {
  direct: { icon: MessageCircle, placeholder: 'Write a message…', note: 'No messages yet. Say hello.' },
  group: { icon: UsersRound, placeholder: 'Message your group…', description: 'Plan, share and make progress with your group.', note: 'No messages yet. Start your group off.' },
  community: { icon: Globe2, placeholder: 'Share with the community…', description: 'Share a useful resource or an experience with your community.', note: 'Nothing posted here yet.' },
  discussion: { icon: BookOpen, placeholder: 'Add to the discussion…', description: 'Ask a clear question. Reply to a message to add your answer.', note: 'No answers yet. Reply to open the thread.' },
};

export const channelTabLabel = (tab) => t(Object.fromEntries(CHANNEL_TABS)[tab] || tab);

// Consecutive ids must not land on neighbouring hues, or a short list comes
// out in one colour family.
export const CHANNEL_TINTS = [0, 3, 1, 4, 2, 5];

export const channelTint = (id) => CHANNEL_TINTS[(id || 0) % CHANNEL_TINTS.length];

export function MessagesPage({ user, data, notify, initialChannel, channelId, openInbox, onChannelOpened }) {
  const [tab, setTab] = useState(initialChannel?.kind || 'direct');
  const [moreFolders, setMoreFolders] = useState(false);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [openingSaved, setOpeningSaved] = useState(false);
  const [channels, setChannels] = useState(() => initialChannel ? [initialChannel, ...(data.messageChannels || []).filter((channel) => channel.id !== initialChannel.id)] : data.messageChannels || []);
  const [activeId, setActiveId] = useState(initialChannel?.id || null);
  const [messages, setMessages] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [sendError, setSendError] = useState('');
  const [anonymous, setAnonymous] = useState(false);
  const [replyTo, setReplyTo] = useState(null);
  const [search, setSearch] = useState('');
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [channelError, setChannelError] = useState('');
  const [messageError, setMessageError] = useState('');
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [membersOpen, setMembersOpen] = useState(false);
  const [reportingMessage, setReportingMessage] = useState(null);
  const [moderationOpen, setModerationOpen] = useState(false);
  const [overview, setOverview] = useState(null);
  const [overviewError, setOverviewError] = useState('');
  // Students' earlier counselor messages, shown as a read-only thread.
  const inbox = useCounselorInbox(user.role === 'student');
  // Older history is a student-portal feature; staff keep the newest page.
  const olderEnabled = user.role === 'student';
  const messageListRef = useRef(null);
  const composerRef = useRef(null);
  const channelRequest = useRef(0);
  const messageRequest = useRef(0);
  const sendLock = useRef(false);
  const lastLoad = useRef(0);
  const lastSnapshot = useRef('');
  const revalidation = useRef(null);
  if (!revalidation.current) revalidation.current = createRevalidation();
  const poller = useRef(null);
  const lastReadMessage = useRef(null);
  const activeChannelRef = useRef(null);
  const stickToBottom = useRef(true);
  const [hasOlder, setHasOlder] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const olderLoaded = useRef(false);
  const olderRequest = useRef(false);
  const keepScroll = useRef(null);

  const visibleChannels = channels.filter((channel) => channel.kind === tab).sort((a, b) => Number(b.is_saved_messages) - Number(a.is_saved_messages) || new Date(b.last_message_at || b.created_at) - new Date(a.last_message_at || a.created_at));
  const activeChannel = activeId === 'list' ? null : visibleChannels.find((channel) => channel.id === activeId) || null;
  const inboxOpen = activeId === COUNSELOR_INBOX && tab === 'direct' && inbox.items.length > 0;
  const body = drafts[activeChannel?.id] || '';
  const setBody = (value) => setDrafts((current) => ({ ...current, [activeChannel.id]: value }));
  const space = activeChannel?.is_saved_messages ? { icon: Bookmark, placeholder: 'Write a note…', note: 'Keep notes, links and ideas here. Only you are a member.' } : CHANNEL_SPACES[tab];
  const SpaceIcon = space.icon;
  const newChannelLabel = tab === 'direct' ? t("New message") : tab === 'discussion' ? t("New discussion") : t("New channel");
  // Unread per folder: the bootstrap list covers every kind, the live list keeps
  // the folder you are in exact.
  const folderUnread = useMemo(() => {
    const merged = new Map((data.messageChannels || []).map((channel) => [channel.id, channel]));
    channels.forEach((channel) => merged.set(channel.id, channel));
    const counts = {};
    merged.forEach((channel) => {if (channel.unread_count > 0) counts[channel.kind] = (counts[channel.kind] || 0) + channel.unread_count;});
    return counts;
  }, [data.messageChannels, channels]);
  useLayoutEffect(() => {
    activeChannelRef.current = activeChannel?.id;
    messageRequest.current += 1;
    stickToBottom.current = true;
    lastReadMessage.current = null;
    olderLoaded.current = false;
    keepScroll.current = null;
    setHasOlder(false);
    setMessages([]);
    setSendError('');
    setReplyTo(null);
    setAnonymous(false);
    setEmojiOpen(false);
    if (composerRef.current) composerRef.current.style.height = 'auto';
  }, [activeChannel?.id]);
  useLayoutEffect(() => {
    channelRequest.current += 1;
    return () => { channelRequest.current += 1; };
  }, [tab, search]);
  useEffect(() => () => { messageRequest.current += 1; activeChannelRef.current = null; }, []);
  const staffInterface = ['counselor', 'organization'].includes(user.role);
  const moderationEnabled = isTaskManager(user) || user.role === 'organization';
  const canCreate = tab === 'direct' || tab === 'discussion' || isTaskManager(user) || user.role === 'organization';
  const canAccept = activeChannel?.kind === 'discussion' && (isTaskManager(user) || ['owner', 'moderator'].includes(activeChannel?.my_role));
  const canManageMembers = activeChannel?.kind !== 'direct' && activeChannel?.is_member && (isTaskManager(user) || user.role === 'organization' || ['owner', 'moderator'].includes(activeChannel?.my_role));

  const refreshOverview = useCallback(async () => {
    if (!moderationEnabled && !staffInterface) return null;
    setOverviewError('');
    try {
      const nextOverview = await api.messagingOverview();
      setOverview(nextOverview);
      return nextOverview;
    } catch (err) {
      notify(err.message, 'error');
      setOverviewError(err.message);
      return null;
    }
  }, [moderationEnabled, staffInterface, notify]);

  const refreshChannels = useCallback(async (kind = tab, term = search, preferredId = activeId) => {
    const requestId = ++channelRequest.current;
    setLoadingChannels(true);
    setChannelError('');
    try {
      const items = await api.messageChannels(kind, term);
      if (requestId !== channelRequest.current) return [];
      // Keep the other folders: dropping them loses the unread counts behind
      // their tabs, and a folder you just read would light up again.
      setChannels((current) => [...current.filter((item) => item.kind !== kind), ...(items || [])]);
      setActiveId((current) => {
        if (current === 'list' && preferredId === 'list') return 'list';
        if (current === COUNSELOR_INBOX && kind === 'direct') return current;
        if (items.some((item) => item.id === preferredId)) return preferredId;
        if (items.some((item) => item.id === current)) return current;
        return null;
      });
      return items || [];
    } catch (err) {
      if (requestId !== channelRequest.current) return [];
      setChannelError(err.message);
      return [];
    } finally {
      if (requestId === channelRequest.current) setLoadingChannels(false);
    }
  }, [tab, search, activeId, notify]);

  // Resolves to true when the conversation changed since the last load, false
  // when it didn't, and null when loading failed.
  const loadMessages = useCallback(async (channel, quiet = false) => {
    const requestId = ++messageRequest.current;
    if (!channel?.is_member) {revalidation.current.reset();setMessages([]);setMessageError('');setLoadingMessages(false);return false;}
    if (!quiet) setLoadingMessages(true);
    lastLoad.current = Date.now();
    try {
      // Background polls revalidate against the last load (304 = nothing changed).
      const result = await api.channelMessagesSince(channel.id, revalidation.current.etagFor(channel.id, quiet));
      if (requestId !== messageRequest.current || activeChannelRef.current !== channel.id) return false;
      if (result.notModified) {setMessageError('');return false;}
      revalidation.current.remember(channel.id, result.etag);
      const items = result.data?.results ?? result.data ?? [];
      const snapshot = `${channel.id}:${JSON.stringify(items)}`;
      const changed = snapshot !== lastSnapshot.current;
      lastSnapshot.current = snapshot;
      // Once older pages are loaded their own "next" decides; the newest
      // page's link only says whether anything precedes it.
      if (!olderLoaded.current) setHasOlder(olderEnabled && Boolean(result.data?.next));
      setMessages((current) => {
        const page = [...items].reverse();
        const next = olderEnabled ? mergeNewestPage(current, page) : page;
        return JSON.stringify(current) === JSON.stringify(next) ? current : next;
      });
      setMessageError('');
      // One read receipt per new message, not one per refresh: the poll and the
      // focus listener both land here, and a receipt is a write.
      const newest = items?.[0]?.id ?? null;
      if (newest !== lastReadMessage.current) {
        lastReadMessage.current = newest;
        // A failed read receipt must never hide successfully loaded messages.
        api.markChannelRead(channel.id).then(() => {
          setChannels((current) => current.map((item) => item.id === channel.id ? { ...item, unread_count: 0 } : item));
          announceNotificationsChanged();
        }).catch(() => {});
      }
      return changed;
    } catch (err) {
      if (requestId === messageRequest.current && activeChannelRef.current === channel.id) setMessageError(err.message);
      return null;
    } finally {
      if (requestId === messageRequest.current) setLoadingMessages(false);
    }
  }, [olderEnabled]);

  useEffect(() => {
    const timer = window.setTimeout(() => refreshChannels(tab, search, activeId), 220);
    return () => window.clearTimeout(timer);
  }, [tab, search]);

  useEffect(() => {refreshOverview();}, [refreshOverview]);

  // A link to one chat (/messages/9, e.g. from the notification bell): open
  // it, then drop the id from the URL so picking another chat is not undone
  // by a refresh.
  useEffect(() => {
    if (!channelId) return undefined;
    let active = true;
    const known = channels.find((item) => item.id === channelId) || (data.messageChannels || []).find((item) => item.id === channelId);
    (known ? Promise.resolve(known) : api.retrieve('message-channels', channelId)).then((channel) => {
      if (!active || !channel) return;
      setTab(channel.kind);
      setSearch('');
      setChannels((current) => [channel, ...current.filter((item) => item.id !== channel.id)]);
      setActiveId(channel.id);
    }).catch((err) => {if (active) notify(err.message, 'error');})
      .finally(() => {if (active) onChannelOpened?.();});
    return () => {active = false;};
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per linked chat, not on every list change
  }, [channelId]);

  useEffect(() => {
    if (!openInbox) return;
    setTab('direct');
    setSearch('');
    setActiveId(COUNSELOR_INBOX);
    onChannelOpened?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per link to the inbox
  }, [openInbox]);

  async function continueWithCounselor(counselorId) {
    try { await channelSaved(await api.openDirectChannel(counselorId)); }
    catch (err) { notify(err.message, 'error'); }
  }

  // Polls the open conversation while the tab is visible (paused when hidden,
  // refreshed at once when it is shown again); failures back off with jitter.
  useEffect(() => {
    const loop = createPoller({
      run: () => (sendLock.current ? false : loadMessages(activeChannel, true)),
      min: MESSAGE_POLL.min,
      max: MESSAGE_POLL.max,
      nextDelay: nextPollDelay,
    });
    poller.current = loop;
    const onFocus = () => {
      // Refocusing the window a few times in a row is not a reason to refetch.
      if (Date.now() - lastLoad.current < 3000) return;
      loop.poke();
    };
    loadMessages(activeChannel);
    loop.start();
    window.addEventListener('focus', onFocus);
    return () => {loop.stop();if (poller.current === loop) poller.current = null;window.removeEventListener('focus', onFocus);messageRequest.current += 1;};
  }, [activeChannel?.id, activeChannel?.is_member, loadMessages]);

  useLayoutEffect(() => {
    const list = messageListRef.current;
    if (!list) return;
    if (keepScroll.current != null) {
      // Older messages went in above: keep the same message under the reader.
      list.scrollTop = restoredScrollTop(list, keepScroll.current);
      keepScroll.current = null;
    } else if (stickToBottom.current) list.scrollTop = list.scrollHeight;
  }, [messages, loadingMessages]);

  async function loadOlder() {
    const channel = activeChannel;
    const oldest = messages[0];
    if (olderRequest.current || !channel?.is_member || !oldest) return;
    olderRequest.current = true;
    setLoadingOlder(true);
    try {
      const page = await api.channelMessagesBefore(channel.id, oldest.id);
      if (activeChannelRef.current !== channel.id) return;
      olderLoaded.current = true;
      keepScroll.current = scrollAnchor(messageListRef.current);
      setMessages((current) => prependOlder(current, [...(page?.results || [])].reverse()));
      setHasOlder(Boolean(page?.next));
    } catch (err) {
      if (activeChannelRef.current === channel.id) notify(err.message, 'error');
    } finally {
      olderRequest.current = false;
      setLoadingOlder(false);
    }
  }

  async function send(event) {
    event.preventDefault();
    if (sendLock.current || !activeChannel?.is_member || !body.trim()) return;
    const channel = activeChannel;
    sendLock.current = true;
    setSaving(true);
    setSendError('');
    try {
      const sent = await api.create('channel-messages', {
        channel: channel.id,
        body: body.trim(),
        is_anonymous: ['community', 'discussion'].includes(channel.kind) && anonymous,
        ...(replyTo?.channel === channel.id ? { parent: replyTo.id } : {})
      });
      setDrafts((current) => ({ ...current, [channel.id]: '' }));
      poller.current?.reset();
      if (activeChannelRef.current === channel.id) {
        messageRequest.current += 1;
        setLoadingMessages(false);
        setMessageError('');
        stickToBottom.current = true;
        setMessages((current) => [...current.filter((item) => item.id !== sent.id), sent]);
        setReplyTo(null);
        if (composerRef.current) {composerRef.current.style.height = 'auto';composerRef.current.focus();}
      }
      setChannels((current) => current.map((item) => item.id === channel.id ? { ...item, last_message: { body: sent.body, created_at: sent.created_at, sender_name: sent.sender_name }, last_message_at: sent.created_at } : item));
    } catch (err) {
      if (activeChannelRef.current === channel.id) setSendError(err.message);
      else notify(err.message, 'error');
    } finally {
      sendLock.current = false;
      setSaving(false);
    }
  }

  async function join() {
    try {
      await api.joinChannel(activeChannel.id);
      const items = await refreshChannels(tab, search, activeChannel.id);
      const joined = items.find((item) => item.id === activeChannel.id);
      if (joined) await loadMessages(joined);
      await refreshOverview();
      notify(t("You joined the channel."));
    } catch (err) {notify(err.message, 'error');}
  }

  async function leave() {
    try {
      await api.leaveChannel(activeChannel.id);
      setMessages([]);
      await refreshChannels(tab, search, null);
      await refreshOverview();
      notify(t("You left the channel."));
    } catch (err) {notify(err.message, 'error');}
  }

  async function accept(message) {
    try {
      const accepted = await api.acceptChannelMessage(message.id);
      setMessages((current) => current.map((item) => ({ ...item, is_accepted_answer: item.id === accepted.id })));
      notify(t("Reply marked as the accepted answer."));
    } catch (err) {notify(err.message, 'error');}
  }

  async function openSavedMessages() {
    if (openingSaved) return;
    setOpeningSaved(true);
    try { await channelSaved(await api.savedMessages()); }
    catch (err) { notify(err.message, 'error'); }
    finally { setOpeningSaved(false); }
  }

  async function channelSaved(channel) {
    setOpen(false);
    setTab(channel.kind);
    setSearch('');
    setChannels((current) => [channel, ...current.filter((item) => item.id !== channel.id)]);
    setActiveId(channel.id);
    await refreshOverview();
  }

  return <div className={`messaging-page section-stack kind-${tab} ${user.role === 'student' ? 'student-portal' : ''}`}>
    {staffInterface && <section className="staff-messaging-overview"><div className="staff-messaging-copy"><span><MessageCircle size={22} /></span><div><small>{user.role === 'counselor' ? t("COUNSELOR INBOX") : t("SCHOOL COMMUNICATIONS")}</small><h2>{user.role === 'counselor' ? t("Student and school conversations") : t("Keep your school connected")}</h2><p>{user.role === 'counselor' ? t("Message assigned students, coordinate with school staff and moderate shared channels.") : t("Contact your students, teachers and assigned counselors from one secure inbox.")}</p></div></div>{overview ? <div className="staff-messaging-stats"><div><strong>{overview.unread_total || 0}</strong><span>{t("Unread")}</span></div><div><strong>{overview.students_total || 0}</strong><span>{user.role === 'counselor' ? t("Assigned students") : t("School students")}</span></div><div><strong>{overview.channel_counts?.direct || 0}</strong><span>{t("Direct chats")}</span></div><div><strong>{(overview.channel_counts?.group || 0) + (overview.channel_counts?.community || 0)}</strong><span>{t("Managed spaces")}</span></div><div className={overview.pending_reports ? "attention" : ''}><strong>{overview.pending_reports || 0}</strong><span>{t("Open reports")}</span></div></div> : overviewError ? <InlineLoadError message={overviewError} onRetry={refreshOverview} /> : <StaffStatsSkeleton />}<div className="staff-messaging-actions"><button className="button primary" onClick={() => {setTab('direct');setActiveId(null);setOpen(true);}}><MessageCircle size={16} /> {t("Message a student")}</button><button className="button quiet" onClick={() => {setTab('group');setActiveId(null);setOpen(true);}}><UsersRound size={16} /> {t("Create group")}</button><button className="button quiet" onClick={() => setModerationOpen(true)}><ShieldAlert size={16} /> {t("Moderation queue")}{overview?.pending_reports ? ` · ${overview.pending_reports}` : ''}</button></div></section>}
    <div className={`messages-shell ${activeChannel || inboxOpen ? 'has-active-channel' : ''} ${activeChannel && detailsOpen ? 'has-details' : ''}`}>
      <aside className="channel-sidebar">
        <header className="chat-sidebar-header">
          <span className="chat-brand-icon"><MessageSquareText size={23} /></span>
          <div><h2>{t("Chat")}</h2><p>{Object.values(folderUnread).some(Boolean) ? t("Unread conversations") : t("All caught up")}</p></div>
          <button type="button" className="chat-new-button" onClick={() => {setTab(staffInterface || isTaskManager(user) ? 'group' : 'direct');setOpen(true);}}><Plus size={15} />{staffInterface || isTaskManager(user) ? t("New group") : t("New message")}</button>
        </header>
        <div className="channel-folders" role="tablist" aria-label={t("Messages")}>{CHANNEL_TABS.filter(([kind]) => moreFolders || ['direct', 'group', tab].includes(kind)).map(([kind, title]) => <button key={kind} type="button" role="tab" aria-selected={tab === kind} className={`channel-folder folder-${kind} ${tab === kind ? 'active' : ''}`} onClick={() => {setTab(kind);setActiveId(null);setSearch('');}}>{t(title)}{folderUnread[kind] ? <em className="folder-count" aria-label={tx`${folderUnread[kind]} unread`}>{folderUnread[kind] > 99 ? '99+' : folderUnread[kind]}</em> : null}</button>)}<button type="button" className="channel-folder channel-more-folders" aria-expanded={moreFolders} aria-label={t("More folders")} title={t("More folders")} onClick={() => setMoreFolders(!moreFolders)}><FolderKanban size={17} /></button>{moderationEnabled && !staffInterface && <button type="button" className="channel-folder channel-moderation" onClick={() => setModerationOpen(true)} aria-label={t("Moderation")} title={t("Moderation")}><ShieldAlert size={16} />{overview?.pending_reports ? <em>{overview.pending_reports}</em> : null}</button>}</div>
        <label className="channel-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("Search chats…")} aria-label={tx`Search ${channelTabLabel(tab)} channels`} /></label>
        <div className="channel-list" aria-busy={loadingChannels}>{tab === 'direct' && !search && !visibleChannels.some((channel) => channel.is_saved_messages) && <button type="button" className="channel-item saved-messages" disabled={openingSaved} onClick={openSavedMessages}><span className="avatar saved-avatar"><Bookmark size={23} /></span><span className="channel-item-copy"><b>{t("Saved Messages")}</b><small>{openingSaved ? t("Opening…") : t("Your notes and links")}</small></span></button>}{tab === 'direct' && !search && <CounselorInboxItem inbox={inbox} user={user} active={inboxOpen} onOpen={() => setActiveId(COUNSELOR_INBOX)} />}{loadingChannels ? <ChannelListSkeleton /> : channelError ? <InlineLoadError message={channelError} onRetry={() => refreshChannels(tab, search, activeId)} /> : <>{visibleChannels.map((channel) => <button type="button" key={channel.id} className={`channel-item ${activeChannel?.id === channel.id ? 'active' : ''} ${channel.unread_count > 0 ? 'unread' : ''} ${channel.is_saved_messages ? 'saved-messages' : ''}`} aria-current={activeChannel?.id === channel.id ? 'true' : undefined} onClick={() => setActiveId(channel.id)}><span className={`avatar ${channel.is_saved_messages ? 'saved-avatar' : `tint-${channelTint(channel.id)}`}`}>{channel.is_saved_messages ? <Bookmark size={23} /> : tab === 'direct' ? initials(channel.display_name) : <SpaceIcon size={20} />}</span><span className="channel-item-copy"><span className="channel-item-top"><b>{channel.is_saved_messages ? t("Saved Messages") : channel.display_name}</b>{channel.last_message?.created_at && <time>{chatStampText(channel.last_message.created_at)}</time>}</span><span className="channel-item-bottom"><small>{channel.last_message?.body || (channel.is_saved_messages ? t("Your notes and links") : tab === 'direct' ? t("No messages yet") : channel.description || tp('{n} member|{n} members', channel.members_count, { n: channel.members_count }))}</small>{channel.unread_count > 0 && <strong aria-label={tx`${channel.unread_count} unread`}>{channel.unread_count > 99 ? '99+' : channel.unread_count}</strong>}</span></span></button>)}{!visibleChannels.length && <div className="channel-list-empty"><SpaceIcon size={26} /><p>{search ? t("No conversation matches your search.") : t("No conversations here yet.")}</p></div>}</>}</div>
        {canCreate && <button type="button" className="channel-compose" onClick={() => setOpen(true)} aria-label={newChannelLabel} title={newChannelLabel}><Pencil size={19} /></button>}
      </aside>
      {inboxOpen ? <CounselorInboxThread inbox={inbox} user={user} onBack={() => setActiveId('list')} onClose={() => setActiveId(null)} onContinue={continueWithCounselor} /> : activeChannel ? <section className="message-thread"><header><div><button type="button" className="icon-button message-back" onClick={() => setActiveId('list')} aria-label={t("Back to conversations")}><ArrowLeft size={18} /></button><span className={`avatar ${activeChannel.is_saved_messages ? 'saved-avatar' : `tint-${channelTint(activeChannel.id)}`}`}>{activeChannel.is_saved_messages ? <Bookmark size={23} /> : tab === 'direct' ? initials(activeChannel.display_name) : <SpaceIcon size={22} />}</span><div><b>{activeChannel.is_saved_messages ? t("Saved Messages") : activeChannel.display_name}</b><small>{activeChannel.is_saved_messages ? t("Your personal notebook") : activeChannel.kind === 'direct' ? t("Direct conversation") : tp('{n} member|{n} members', activeChannel.members_count, { n: activeChannel.members_count })}</small></div></div><div className="channel-actions"><button type="button" className="icon-button" onClick={() => setDetailsOpen(!detailsOpen)} aria-label={t("Contact info")} title={t("Contact info")} aria-expanded={detailsOpen}><Info size={19} /></button><button type="button" className="icon-button close-chat" onClick={() => setActiveId(null)} aria-label={t("Close chat")} title={t("Close chat")}><X size={18} /></button>{canManageMembers && <button className="button quiet small" onClick={() => setMembersOpen(true)}><UsersRound size={15} /> {t("Manage members")}</button>}{activeChannel.is_public && !activeChannel.is_member && <button className="button primary small" onClick={join}>{t("Join")}</button>}{activeChannel.is_member && activeChannel.kind !== 'direct' && activeChannel.my_role !== 'owner' && <button className="button quiet small" onClick={leave}>{t("Leave")}</button>}</div></header>
        {activeChannel.is_member ? <><div className="message-list" ref={messageListRef} onScroll={(event) => {const list = event.currentTarget;stickToBottom.current = list.scrollHeight - list.scrollTop - list.clientHeight < 90;if (list.scrollTop < 60 && hasOlder && !loadingMessages) loadOlder();}} aria-busy={loadingMessages}>{activeChannel.kind !== 'direct' && <div className="channel-context"><SpaceIcon size={24} /><div><b>{activeChannel.display_name}</b><p>{activeChannel.description || t(space.description)}</p></div></div>}{messageError && <InlineLoadError message={messageError} onRetry={() => loadMessages(activeChannel)} />}{loadingMessages ? <MessageListSkeleton /> : <>{hasOlder && messages.length > 0 && <div className="message-older"><button type="button" className="button quiet small" onClick={loadOlder} disabled={loadingOlder} aria-busy={loadingOlder}>{loadingOlder ? t("Loading…") : t("Load older messages")}</button></div>}{messages.map((message, index) => {
              const mine = message.sender_id === user.id;
              const previous = messages[index - 1];
              const newDay = !previous || new Date(previous.created_at).toDateString() !== new Date(message.created_at).toDateString();
              const sameAuthor = !newDay && previous && message.sender_id != null && previous.sender_id === message.sender_id && previous.is_anonymous === message.is_anonymous && !message.parent;
              const showSender = ['community', 'discussion'].includes(activeChannel.kind) || activeChannel.kind === 'group' && !sameAuthor;
              const showAvatar = activeChannel.kind !== 'direct' && !mine;
              return <Fragment key={message.id}>{newDay && <div className="message-day"><span>{dateText(message.created_at)}</span></div>}{showAvatar && <span className={`message-avatar avatar ${sameAuthor ? 'is-hidden' : ''}`}>{initials(message.is_anonymous ? '?' : message.sender_name)}</span>}<article id={`message-${message.id}`} className={`message-bubble sender-${(message.sender_id || 0) % 6} ${mine ? 'mine' : ''} ${message.parent ? 'reply' : ''} ${message.is_accepted_answer ? 'accepted' : ''} ${sameAuthor ? 'stacked' : ''}`}>{message.parent_preview && <button type="button" className="parent-preview" onClick={() => document.getElementById(`message-${message.parent}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}>{t("Reply to:")} {message.parent_preview.body}</button>}<div className={showSender || message.is_accepted_answer ? '' : 'is-hidden'}>{showSender && <b>{message.sender_name}{message.is_anonymous ? ` ${t("· Anonymous")}` : ''}</b>}{message.is_accepted_answer && <span className="accepted-label"><CheckCircle2 size={13} /> {t("Accepted answer")}</span>}</div><p>{message.deleted_at ? t("Message deleted") : message.body}<time>{clockText(message.created_at)}{message.is_edited ? ` ${t("· edited")}` : ''}{mine && <Check size={12} aria-label={t("Sent")} />}</time></p><footer>{!message.deleted_at && <button type="button" onClick={() => setReplyTo(message)}>{t("Reply")}</button>}{!mine && !message.deleted_at && <button type="button" disabled={message.is_reported_by_me} onClick={() => setReportingMessage(message)}><Flag size={11} /> {message.is_reported_by_me ? t("Reported") : t("Report")}</button>}{canAccept && message.parent && !message.deleted_at && !message.is_accepted_answer && <button type="button" onClick={() => accept(message)}>{t("Accept answer")}</button>}</footer></article></Fragment>;})}{!messages.length && <div className="thread-empty"><SpaceIcon size={26} /><p>{t(space.note)}</p></div>}</>}</div><form className="message-compose" onSubmit={send}><div className="composer-field"><button type="button" className="emoji-toggle icon-button" disabled={saving} aria-label={t("Choose emoji")} aria-expanded={emojiOpen} onClick={() => setEmojiOpen(!emojiOpen)}><Smile size={22} /></button>{emojiOpen && <div className="emoji-picker" role="group" aria-label={t("Choose emoji")}>{['😊', '👍', '❤️', '🎉', '🙌', '✅', '👋', '💡', '📚', '🚀', '🤝', '✨'].map((emoji) => <button key={emoji} type="button" aria-label={emoji} onClick={() => {setBody(body + emoji);setEmojiOpen(false);composerRef.current?.focus();}}>{emoji}</button>)}</div>}{sendError && <p className="compose-error" role="alert">{sendError}</p>}{replyTo && <div className="replying-to"><span>{t("Replying to")} <b>{replyTo.sender_name}</b></span><button type="button" className="icon-button" onClick={() => setReplyTo(null)} aria-label={t("Cancel reply")}><X size={15} /></button></div>}<textarea ref={composerRef} aria-label={t(space.placeholder)} readOnly={saving} value={body} onChange={(event) => {setBody(event.target.value);event.target.style.height = 'auto';event.target.style.height = `${Math.min(132, event.target.scrollHeight)}px`;}} onKeyDown={(event) => {if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {event.preventDefault();send(event);}}} placeholder={t(space.placeholder)} rows="1" />{['community', 'discussion'].includes(activeChannel.kind) && <CheckboxControl className="compact anonymous-toggle" checked={anonymous} onChange={(event) => setAnonymous(event.target.checked)}>{t("Post anonymously")}</CheckboxControl>}<small className="compose-hint">{saving ? t("Sending…") : t("Enter to send · Shift + Enter for a new line")}</small></div><button type="submit" className="message-send" disabled={saving || !body.trim()} aria-busy={saving} aria-label={saving ? t("Sending…") : t("Send")} title={t("Send")}><Send size={18} /></button></form></> : <div className="message-join-state"><UsersRound size={42} /><h3>{activeChannel.display_name}</h3><p>{activeChannel.description || t("Join this channel to read and send messages.")}</p><button className="button primary" onClick={join}>{t("Join channel")}</button></div>}
      </section> : <section className="message-empty-state"><UsersRound size={44} strokeWidth={1.5} /><h3>{t("Select a chat")}</h3></section>}
      {activeChannel && detailsOpen && <ChatDetails key={activeChannel.id} channel={activeChannel} messages={messages} onClose={() => setDetailsOpen(false)} />}
    </div>
    {open && <MessageChannelForm kind={tab} user={user} onClose={() => setOpen(false)} onSaved={channelSaved} notify={notify} />}
    {membersOpen && activeChannel && <ChannelMembersModal channel={activeChannel} user={user} onClose={() => setMembersOpen(false)} onChanged={async () => {await refreshChannels(tab, search, activeChannel.id);await refreshOverview();}} notify={notify} />}
    {reportingMessage && <ReportMessageModal message={reportingMessage} onClose={() => setReportingMessage(null)} onReported={async () => {setMessages((current) => current.map((item) => item.id === reportingMessage.id ? { ...item, is_reported_by_me: true } : item));setReportingMessage(null);await refreshOverview();}} notify={notify} />}
    {moderationOpen && moderationEnabled && <ModerationQueueModal onClose={() => setModerationOpen(false)} onChanged={refreshOverview} notify={notify} />}
  </div>;
}
