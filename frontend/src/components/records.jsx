import { t, tp, formatNumberLocale, tx, formatPercentLocale } from '../i18n';
import { testScoreCaption } from '../lib/format';
import { Star, CheckCircle2, Eye, Pencil, UserX } from 'lucide-react';
import { Badge, Panel, Empty } from './ui';
import { fullName, initials } from '../lib/labels';
import { useState, useEffect } from 'react';
import { api } from '../api';
import { createBlobUrlCache } from '../lib/blobUrlCache';
import { TestScoreSummary } from './testScores';

export function LevelProgress({ student }) {
  if (!student) return null;
  const stars = student.roadmap_stars ?? 0;
  const roadmapPercent = student.roadmap_progress_percent ?? 0;
  return <section className="roadmap-progress-card">
    <span className="eyebrow">{t("YOUR LEVEL")}</span>
    <h2>{t("Level")} {formatNumberLocale(student.level ?? 1)}</h2>
    {student.level_up_pending && <p>{tx`Level ${student.eligible_level} is waiting for staff approval.`}</p>}
    <div className="roadmap-star-count"><Star size={19} /><strong>{formatNumberLocale(stars)}</strong><small>{tp('star earned|stars earned', stars)}</small></div>
    <div className="roadmap-progress-meter">
      <span>{t("Roadmap missions approved")}</span>
      <b>{formatPercentLocale(roadmapPercent)}</b>
      <div className="progress"><span style={{ width: `${roadmapPercent}%` }} /></div>
    </div>
  </section>;
}

export function Stat({ label: title, value, note, tone = '' }) {
  return <article className={`stat-card ${tone}`}><span>{t(title)}</span><strong>{value}</strong>{note && <small>{t(note)}</small>}</article>;
}

export function Record({ title, meta, description, badge, attachment, actions }) {
  return <article className="record"><div className="record-main"><div><b>{title}</b>{meta && <small>{meta}</small>}</div>{badge && <Badge>{badge}</Badge>}</div>{description && <p>{description}</p>}{attachment}{actions && <div className="record-actions">{actions}</div>}</article>;
}

export function ProfileCard({ student }) {
  if (!student) return <Panel title={t("Profile")}><Empty text={t("Student profile not found.")} /></Panel>;
  return <Panel title={t("Profile overview")} className="profile-card" ><div className="profile-identity"><StudentAvatar student={student} className="large" /><div><h3>{fullName(student.user_detail)}</h3><p>{student.user_detail?.email}</p></div></div><div className="detail-grid"><Detail label={t("School")} value={student.school_name} /><Detail label={t("Grade")} value={student.grade === 'gap' ? t("Gap year") : student.grade ? tx`Grade ${student.grade}` : null} /><Detail label={t("Counselor")} value={student.counselor_name} /><Detail label={t("Major")} value={student.target_major} /><Detail label={t("GPA")} value={student.gpa} /><Detail label={t("Countries")} value={student.target_countries} /><Detail label={t("Scholarship")} value={student.scholarship_needed ? t("Needed") : t("Not needed")} /></div><h3 className="test-score-heading">{t("Test scores")}</h3><TestScoreSummary student={student} /></Panel>;
}

// Shared by every avatar on screen; entries are keyed by photo version, so an
// upload shows up at once and unchanged photos are never refetched.
const studentPhotos = createBlobUrlCache({ max: 64 });

export function StudentAvatar({ student, className = '' }) {
  const version = student?.photo_version || student?.updated_at || '';
  const key = student?.id && student.has_photo ? `${student.id}:${version}` : '';
  const [photo, setPhoto] = useState(() => ({ key, src: key ? studentPhotos.peek(key) : '' }));
  useEffect(() => {
    if (!key) return;
    let active = true;
    studentPhotos.load(key, () => api.studentPhoto(student.id, student.photo_version).then((result) => result.blob)).
    then((src) => {if (active) setPhoto({ key, src });}).
    catch(() => {if (active) setPhoto({ key, src: '' });});
    return () => {active = false;};
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps -- key covers id and version
  const src = !key ? '' : photo.key === key ? photo.src : studentPhotos.peek(key);
  const name = fullName(student?.user_detail);
  return <span className={`avatar ${src ? 'has-photo' : ''} ${className}`.trim()}>{src ? <img src={src} alt={name} /> : initials(name)}</span>;
}

export function Detail({ label: title, value }) {
  const empty = value == null || value === '' || (typeof value === 'string' && !value.trim());
  return <div className={`detail ${empty ? 'is-empty' : ''}`.trim()}><span>{t(title)}</span><b>{empty ? t("Not provided") : value}</b></div>;
}

// Students are never deleted: the row action deactivates (data is kept).
// `students`: rows already searched on the server (staff lists); otherwise
// the in-memory students are filtered by `query`.
export function StudentTable({ data, students = null, onView, onEdit, onDeactivate, onApproveLevel, readOnly = false, query = '' }) {
  const rows = students ?? data.students.filter((student) => fullName(student.user_detail).toLowerCase().includes(query.toLowerCase()));
  if (!rows.length) return <Empty text={t("No students found.")} />;
  const hasActions = Boolean(onView || onApproveLevel || !readOnly && (onEdit || onDeactivate));
  return <div className="table-wrap"><table><thead><tr><th>{t("Student")}</th><th>{t("School")}</th><th>{t("Target")}</th><th>{t("Scores")}</th><th>{t("Level")}</th><th>{t("Progress")}</th>{hasActions && <th />}</tr></thead><tbody>{rows.map((student) => <tr key={student.id} className={onView ? "clickable-row" : ''} onDoubleClick={() => onView?.(student)}><td><div className="person"><span className="avatar">{initials(fullName(student.user_detail))}</span><div><b>{fullName(student.user_detail)}</b><small>{student.user_detail?.email}</small>{student.is_at_risk && <span className="risk-note">{t("Needs attention")}</span>}</div></div></td><td>{student.school_name || '—'}</td><td className="student-target-cell"><b>{student.target_major || '—'}</b><small>{student.target_countries || '—'}</small></td><td>{student.gpa || testScoreCaption(student) ? <>{student.gpa ? `${t("GPA")} ${student.gpa}` : ''}<small>{testScoreCaption(student)}</small></> : <small>{t("No scores yet")}</small>}</td><td><b>{t("Level")} {formatNumberLocale(student.level ?? 1)}</b><small>{formatNumberLocale(student.xp_total ?? 0)} {t("XP")}</small>{student.level_up_pending && <span className="risk-note">{tx`Level ${student.eligible_level} approval pending`}</span>}</td><td><div className="student-progress-stack">{[['Tasks', student.task_progress_percent], ['Roadmap', student.roadmap_progress_percent], ['Overall', student.journey_progress_percent]].map(([title, value]) => <div key={title}><span>{t(title)}</span><div className="progress"><i style={{ width: `${value || 0}%` }} /></div><b>{formatPercentLocale(value || 0)}</b></div>)}</div></td>{hasActions && <td><div className="row-actions">{onApproveLevel && student.level_up_pending && <button className="button quiet small" onClick={() => onApproveLevel(student)}><CheckCircle2 size={15} /> {t("Approve level")}</button>}{onView && <button className="icon-button" onClick={() => onView(student)} title={t("Full profile")}><Eye size={16} /></button>}{!readOnly && onEdit && <button className="icon-button" onClick={() => onEdit(student)} title={t("Edit")}><Pencil size={16} /></button>}{!readOnly && onDeactivate && <button className="icon-button danger" onClick={() => onDeactivate(student)} title={t("Deactivate student")} aria-label={t("Deactivate student")}><UserX size={16} /></button>}</div></td>}</tr>)}</tbody></table></div>;
}
