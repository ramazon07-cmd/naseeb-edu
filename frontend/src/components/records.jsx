import { t, tp, formatNumberLocale, tx, formatPercentLocale } from '../i18n';
import { contactEmail, testScoreCaption } from '../lib/format';
import { Star, CheckCircle2, Eye, Pencil, UserX } from 'lucide-react';
import { Badge, Panel, Empty } from './ui';
import { fullName, initials } from '../lib/labels';
import { useState, useEffect } from 'react';
import { api } from '../api';
import { createBlobUrlCache } from '../lib/blobUrlCache';
import { TestScoreSummary } from './testScores';
import { CxAvatar, CxTag } from './counselorUi';
import { splitList } from '../lib/profileSections';
import '../pages/counselor-students.css';

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

export function Record({ title, meta, description, badge, extraBadge = null, attachment, actions }) {
  return <article className="record"><div className="record-main"><div><b>{title}</b>{meta && <small>{meta}</small>}</div>{(badge || extraBadge) && <span className="record-badges">{extraBadge}{badge && <Badge>{badge}</Badge>}</span>}</div>{description && <p>{description}</p>}{attachment}{actions && <div className="record-actions">{actions}</div>}</article>;
}

export function ProfileCard({ student }) {
  if (!student) return <Panel title={t("Profile")}><Empty text={t("Student profile not found.")} /></Panel>;
  return <Panel title={t("Profile overview")} className="profile-card" ><div className="profile-identity"><StudentAvatar student={student} className="large" /><div><h3>{fullName(student.user_detail)}</h3><p>{contactEmail(student.user_detail?.email)}</p></div></div><div className="detail-grid"><Detail label={t("School")} value={student.school_name} /><Detail label={t("Grade")} value={student.grade === 'gap' ? t("Gap year") : student.grade ? tx`Grade ${student.grade}` : null} /><Detail label={t("Counselor")} value={student.counselor_name} /><Detail label={t("Major")} value={student.target_major} /><Detail label={t("GPA")} value={student.gpa} /><Detail label={t("Countries")} value={student.target_countries} /><Detail label={t("Scholarship")} value={student.scholarship_needed ? t("Needed") : t("Not needed")} /></div><h3 className="test-score-heading">{t("Test scores")}</h3><TestScoreSummary student={student} /></Panel>;
}

// Shared by every avatar on screen; entries are keyed by photo version, so an
// upload shows up at once and unchanged photos are never refetched.
const studentPhotos = createBlobUrlCache({ max: 64 });
const accountPhotos = createBlobUrlCache({ max: 8 });

// The object URL of a private photo ('' while loading or when there is none).
function usePhotoSrc(cache, key, fetchBlob) {
  const [photo, setPhoto] = useState(() => ({ key, src: key ? cache.peek(key) : '' }));
  useEffect(() => {
    if (!key) return;
    let active = true;
    cache.load(key, fetchBlob).
    then((src) => {if (active) setPhoto({ key, src });}).
    catch(() => {if (active) setPhoto({ key, src: '' });});
    return () => {active = false;};
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps -- key covers id and version
  return !key ? '' : photo.key === key ? photo.src : cache.peek(key);
}

// A staff account's own photo; `account.avatar` is its versioned URL, or null.
export function useAccountPhoto(account) {
  const version = account?.avatar ? new URL(account.avatar, window.location.href).searchParams.get('v') : '';
  return usePhotoSrc(accountPhotos, version ? `${account.id}:${version}` : '', () => api.accountAvatar(account.id, version).then((result) => result.blob));
}

export function StudentAvatar({ student, className = '' }) {
  const version = student?.photo_version || student?.updated_at || '';
  const key = student?.id && student.has_photo ? `${student.id}:${version}` : '';
  const src = usePhotoSrc(studentPhotos, key, () => api.studentPhoto(student.id, student.photo_version).then((result) => result.blob));
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
  // Buttons inside a clickable row must not also open the profile.
  const act = (handler, student) => (event) => { event.stopPropagation(); handler(student); };
  return <div className="cs-table-card student-table-card"><table className="cs-table student-table"><thead><tr><th scope="col">{t("Student")}</th><th scope="col">{t("School")}</th><th scope="col">{t("Target")}</th><th scope="col">{t("Scores")}</th>{hasActions && <th scope="col"><span className="sr-only">{t("Actions")}</span></th>}</tr></thead><tbody>{rows.map((student) => {
    const name = fullName(student.user_detail);
    const email = contactEmail(student.user_detail?.email);
    return <tr key={student.id} className={onView ? '' : 'cs-static'} onClick={onView ? () => onView(student) : undefined}>
      <td><div className="cx-person"><CxAvatar name={name} /><span className="cx-row-copy">{onView ? <button type="button" className="cx-name-link" onClick={act(onView, student)}>{name}</button> : <b>{name}</b>}{email && <small>{email}</small>}{student.is_at_risk && <span><CxTag tone="late" small>{t("Needs attention")}</CxTag></span>}</span></div></td>
      <td data-label={t("School")}>{student.school_name || <span className="cx-faint">—</span>}</td>
      <td data-label={t("Target")} className="cs-col-target"><span className="cx-row-copy">{student.target_major ? <b>{student.target_major}</b> : <span className="cx-faint">—</span>}{student.target_countries && <small>{splitList(student.target_countries).map((country) => t(country)).join(', ')}</small>}</span></td>
      <td data-label={t("Scores")} className="cs-col-nowrap">{student.gpa || testScoreCaption(student) ? <span className="cx-row-copy">{student.gpa && <b>{t("GPA")} {student.gpa}</b>}<small>{testScoreCaption(student)}</small></span> : <span className="cx-faint">{t("No scores yet")}</span>}</td>
      {hasActions && <td className="cs-col-edit"><div className="row-actions">{onApproveLevel && student.level_up_pending && <button type="button" className="button quiet small" onClick={act(onApproveLevel, student)}><CheckCircle2 size={15} /> {t("Approve level")}</button>}{onView && <button type="button" className="icon-button" onClick={act(onView, student)} title={t("Full profile")} aria-label={t("Full profile")}><Eye size={16} /></button>}{!readOnly && onEdit && <button type="button" className="icon-button" onClick={act(onEdit, student)} title={t("Edit")} aria-label={tx`Edit ${name}`}><Pencil size={16} /></button>}{!readOnly && onDeactivate && <button type="button" className="icon-button danger" onClick={act(onDeactivate, student)} title={t("Deactivate student")} aria-label={tx`Deactivate ${name}`}><UserX size={16} /></button>}</div></td>}
    </tr>;
  })}</tbody></table></div>;
}
