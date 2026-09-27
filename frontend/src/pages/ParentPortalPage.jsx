import { initials, label } from '../lib/labels';
import { t, tx, formatPercentLocale, formatNumberLocale } from '../i18n';
import { userStorageKey, USER_STORAGE } from '../userStorage';
import { EMPTY_DATA } from '../lib/emptyData';
import { useState } from 'react';
import { api } from '../api';
import { UsersRound, Check, ShieldCheck, Fingerprint } from 'lucide-react';
import { dateText, dateTimeText, gradeText, joinParts } from '../lib/format';
import { Stat, Record, Detail } from '../components/records';
import { Panel, Empty, Badge } from '../components/ui';
import { nextPriorities } from '../lib/metrics';

export function ParentChildSwitcher({ children, selectedId, onChange }) {
  if (children.length <= 1) return children[0] ? <div className="parent-single-child"><span className="avatar">{initials(children[0].profile.name)}</span><div><b>{children[0].profile.name}</b><small>{children[0].profile.school}</small></div></div> : null;
  return <label className="parent-child-switcher"><span>{t("Viewing child")}</span><select value={selectedId} onChange={(event) => onChange(Number(event.target.value))}>{children.map((child) => <option key={child.profile.id} value={child.profile.id}>{joinParts(child.profile.name, child.profile.school)}</option>)}</select></label>;
}

export function ParentPortalPage({ page, user, data, reload, notify }) {
  const PARENT_CHILD_KEY = userStorageKey(USER_STORAGE.parentChild, user.id);
  const portal = data.parentPortal || EMPTY_DATA.parentPortal;
  const children = portal.children || [];
  const [preferredId, setPreferredId] = useState(() => {
    try {return Number(localStorage.getItem(PARENT_CHILD_KEY)) || null;} catch {return null;}
  });
  const child = children.find((item) => item.profile.id === preferredId) || children[0];

  function chooseChild(id) {
    setPreferredId(id);
    try {localStorage.setItem(PARENT_CHILD_KEY, String(id));} catch {/* Selection remains available for this session. */}
  }
  async function acceptInvite(invitation) {
    try {await api.acceptParentInvite(invitation.id);notify(tx`${invitation.student_name} is now connected.`);reload();} catch (err) {notify(err.message, 'error');}
  }
  async function revokeAccess() {
    if (!child || !window.confirm(tx`Disconnect parent access to ${child.profile.name}?`)) return;
    try {await api.revokeParentLink(child.link_id);notify(t("Parent access disconnected."));reload();} catch (err) {notify(err.message, 'error');}
  }

  const invitations = portal.pending_invitations || [];
  if (!child) return <div className="parent-empty-workspace"><section><UsersRound size={42} /><span className="eyebrow">{t("PARENT WORKSPACE")}</span><h2>{t("Your family workspace is ready")}</h2><p>{t("A child appears here only after you accept an invitation from their assigned counselor or Naseeb Edu admin.")}</p></section>{invitations.map((invitation) => <article key={invitation.id}><div><b>{invitation.student_name}</b><small>{joinParts(invitation.relationship_display, tx`Invited ${dateText(invitation.invited_at)}`)}</small></div><button className="button primary" onClick={() => acceptInvite(invitation)}><Check size={16} /> {t("Accept invitation")}</button></article>)}{!invitations.length && <div className="screen-time-privacy"><ShieldCheck size={18} /><p>{t("No pending invitation. Ask the student’s assigned counselor to invite your parent account.")}</p></div>}</div>;

  const profile = child.profile;
  const openTasks = nextPriorities(child.tasks);
  const activeApplications = child.applications.filter((item) => !['accepted', 'rejected'].includes(item.status));
  const upcomingMeetings = child.meetings.filter((item) => new Date(item.starts_at) >= new Date() && !['rejected', 'completed'].includes(item.status));
  const header = <section className="parent-family-hero"><div><span className="eyebrow">{t("FAMILY VIEW · READ ONLY")}</span><h2>{profile.name}</h2><p>{joinParts(profile.school, gradeText(profile.grade), tx`Counselor: ${profile.counselor_name || t("Not assigned")}`)}</p></div><ParentChildSwitcher children={children} selectedId={profile.id} onChange={chooseChild} /></section>;
  const invitationsPanel = invitations.length > 0 && <section className="parent-invitations"><div><b>{t("New child invitation")}</b><p>{t("Accepting grants the exact read-only sections selected by the counselor.")}</p></div>{invitations.map((invitation) => <button key={invitation.id} className="button primary" onClick={() => acceptInvite(invitation)}><Check size={16} /> {t("Accept")} {invitation.student_name}</button>)}</section>;

  let content;
  if (page === 'dashboard') content = <>
    <div className="stat-grid parent-stat-grid"><Stat label={t("Overall progress")} value={formatPercentLocale(profile.journey_progress_percent)} note={t("Tasks and roadmap combined")} /><Stat label={t("Open tasks")} value={formatNumberLocale(openTasks.length)} note={openTasks.filter((item) => item.is_overdue).length ? t("Deadline needs attention") : t("No overdue work")} /><Stat label={t("Active applications")} value={child.permissions.applications ? formatNumberLocale(activeApplications.length) : '—'} note={child.permissions.applications ? t("Permission granted") : t("Not shared")} /><Stat label={t("Upcoming meetings")} value={child.permissions.meetings ? formatNumberLocale(upcomingMeetings.length) : '—'} note={child.permissions.meetings ? t("Permission granted") : t("Not shared")} /></div>
    <div className="split-grid wide-left"><Panel title={t("Next priorities")}><div className="record-list">{openTasks.slice(0, 5).map((task) => <Record key={task.id} title={task.title} meta={joinParts(task.due_date && tx`Due ${dateText(task.due_date)}`, task.priority && tx`Priority: ${label(task.priority)}`)} badge={task.status} />)}{!openTasks.length && <Empty text={t("No open tasks for this child.")} />}</div></Panel><Panel title={t("Family access")}><div className="parent-access-list">{[['Progress & tasks', true], ['Applications', child.permissions.applications], ['Documents', child.permissions.documents], ['Meetings', child.permissions.meetings]].map(([title, allowed]) => <div key={title}><span>{t(title)}</span><b className={allowed ? "allowed" : ''}>{allowed ? t("Visible") : t("Hidden")}</b></div>)}</div><button className="button quiet small parent-revoke" onClick={revokeAccess}>{t("Disconnect access")}</button></Panel></div>
  </>;else
  if (page === 'parent_progress') content = <><div className="stat-grid parent-stat-grid"><Stat label={t("Level")} value={formatNumberLocale(profile.level ?? 1)} note={tx`${formatNumberLocale(profile.xp_total ?? 0)} XP earned`} /><Stat label={t("Task progress")} value={formatPercentLocale(profile.task_progress_percent)} /><Stat label={t("Roadmap progress")} value={formatPercentLocale(profile.roadmap_progress_percent)} /><Stat label={t("Overall progress")} value={formatPercentLocale(profile.journey_progress_percent)} /></div><div className="split-grid"><Panel title={t("Academic snapshot")}><div className="detail-grid"><Detail label={t("GPA")} value={profile.gpa} /><Detail label={t("IELTS")} value={profile.ielts_score} /><Detail label={t("SAT")} value={profile.sat_score} /><Detail label={t("Target major")} value={profile.target_major} /><Detail label={t("Target countries")} value={profile.target_countries} /><Detail label={t("Next level")} value={profile.next_level_xp ? tx`${formatNumberLocale(profile.xp_total ?? 0)} / ${formatNumberLocale(profile.next_level_xp)} XP` : null} /></div></Panel><Panel title={t("Progress by area")}><div className="parent-progress-list">{[['Tasks', profile.task_progress_percent], ['Roadmap', profile.roadmap_progress_percent], ['Overall', profile.journey_progress_percent]].map(([title, value]) => <div key={title}><span><b>{t(title)}</b><small>{formatPercentLocale(value)}</small></span><div className="progress wide"><i style={{ width: `${value}%` }} /></div></div>)}</div></Panel></div></>;else
  if (page === 'parent_tasks') content = <Panel title={t("Assigned tasks")}><div className="parent-record-grid">{child.tasks.map((task) => <article key={task.id}><div><Badge>{task.status}</Badge>{task.is_self_assigned && <small>{t("Personal task")}</small>}</div><h3>{task.title}</h3><p>{joinParts(task.due_date && tx`Due ${dateText(task.due_date)}`, task.priority && tx`Priority: ${label(task.priority)}`)}</p>{task.is_overdue && <span className="risk-note">{t("Deadline passed")}</span>}</article>)}{!child.tasks.length && <Empty text={t("No assigned tasks yet.")} />}</div></Panel>;else
  if (page === 'parent_applications') content = child.permissions.applications ? <Panel title={t("University applications")}><div className="parent-record-grid">{child.applications.map((application) => <article key={application.id}><div><Badge>{application.status}</Badge><small>{label(application.tier)}</small></div><h3>{application.university}</h3><p>{joinParts(application.program, application.country)}</p>{application.deadline && <span>{tx`Deadline: ${dateText(application.deadline)}`}</span>}</article>)}{!child.applications.length && <Empty text={t("No university applications have been added.")} />}</div></Panel> : <ParentHiddenSection title={t("Applications")} />;else
  if (page === 'parent_documents') content = child.permissions.documents ? <Panel title={t("Document checklist")}><div className="parent-record-grid">{child.documents.map((doc) => <article key={doc.id}><div><Badge>{doc.status}</Badge><small>{label(doc.document_type)}</small></div><h3>{doc.title}</h3>{doc.updated_at && <p>{tx`Updated ${dateText(doc.updated_at)}`}</p>}</article>)}{!child.documents.length && <Empty text={t("No document checklist items yet.")} />}</div></Panel> : <ParentHiddenSection title={t("Documents")} />;else
  content = child.permissions.meetings ? <Panel title={t("Counselor meetings")}><div className="parent-record-grid">{child.meetings.map((meeting) => <article key={meeting.id}><div><Badge>{meeting.status}</Badge>{meeting.duration_minutes > 0 && <small>{tx`${meeting.duration_minutes} min`}</small>}</div><h3>{meeting.topic}</h3><p>{dateTimeText(meeting.starts_at)}</p><span>{joinParts(meeting.participant_name || t("Staff member"), meeting.participant_role && label(meeting.participant_role))}</span></article>)}{!child.meetings.length && <Empty text={t("No meetings are visible yet.")} />}</div></Panel> : <ParentHiddenSection title={t("Meetings")} />;

  return <div className="section-stack parent-portal">{header}{invitationsPanel}{content}<div className="screen-time-privacy"><ShieldCheck size={18} /><p><b>{t("Private by default.")}</b> {t("This cabinet never shows essays, messages, counselor notes, task responses, document files, passwords, or application portal credentials. All shared information is read-only.")}</p></div></div>;
}

export function ParentHiddenSection({ title }) {
  return <section className="parent-hidden-section"><Fingerprint size={36} /><h2>{tx`${title}: not shared`}</h2><p>{t("The counselor did not enable this section for the current parent-child connection.")}</p></section>;
}
