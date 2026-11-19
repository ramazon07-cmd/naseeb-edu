import { useEffect, useRef, useState } from 'react';
import { Award, Camera, Search, Briefcase, ClipboardCheck, FolderGit2, Globe2, GraduationCap, Mail, MapPin, Sparkles, Star, Target, Trophy } from 'lucide-react';
import { t, tx, tp } from '../i18n';
import { api } from '../api';
import { StudentAvatar } from '../components/records';
import { BrandLogo } from '../components/brand';
import { fullName } from '../lib/labels';
import { gradeText, contactEmail } from '../lib/format';
import { listText, readinessHints } from '../lib/profileSections';
import { Modal } from '../components/ui';
import { StudentOverview } from './StudentsPage';
import { ownStudent } from '../lib/labels';
import { isPageLocked } from '../lib/routes';
import { ProfileSections } from '../components/ProfileSections';
import { AddMenu } from '../components/AddMenu';
import { ResourceForm, ResourceSection } from './ResourceSection';
import { DocumentsPage } from './DocumentsPage';
import { DownloadCvButton } from '../components/CvDocument';
import { KpiRow, KpiTile, PageHeader, PillTabs, tabId } from '../design/blue/ui';
import '../design/pages/center-blue.css';

// Each tab with several record types gets one "Add" chooser instead of an
// Add button per card. [resource, card title, menu label, hint, form title, empty text, empty link, icon]
const TAB_RESOURCES = {
  portfolio: [
    ['projects', 'Projects', 'Project', 'Something you built or organised', 'Add a project', 'No projects yet.', 'Add your first project', FolderGit2],
    ['internships', 'Internships', 'Internship', 'Work experience at an organisation', 'Add an internship', 'No internships yet.', 'Add your first internship', Briefcase],
  ],
  activities: [
    ['activities', 'Activities', 'Activity', 'A club, sport, volunteering or hobby', 'Add an activity', 'No activities yet.', 'Add your first activity', Sparkles],
    ['honors', 'Honors', 'Honor', 'An award or prize you received', 'Add an honor', 'No honors yet.', 'Add your first honor', Award],
    ['achievements', 'Achievements', 'Achievement', 'A result you are proud of', 'Add an achievement', 'No achievements yet.', 'Add your first achievement', Trophy],
    ['recommendations', 'Recommendation letters', 'Recommendation letter', 'A teacher or mentor who writes for you', 'Add a recommendation letter', 'No recommendation letters yet.', 'Add your first recommendation letter', Mail],
  ],
};

function ResourceTab({ tab, user, data, query, reload, notify }) {
  const [creating, setCreating] = useState(null);
  const entries = TAB_RESOURCES[tab];
  const current = entries.find(([resource]) => resource === creating);
  const section = ([resource, title, , , , emptyText, emptyAction]) => <ResourceSection key={resource} title={t(title)} resource={resource} onAdd={() => setCreating(resource)} emptyText={emptyText} emptyAction={t(emptyAction)} {...{ user, data, query, reload, notify }} />;
  const pairs = [];
  for (let i = 0; i < entries.length; i += 2) pairs.push(entries.slice(i, i + 2));
  return <div className="section-stack">
    <div className="student-tab-toolbar">
      <AddMenu items={entries.map(([key, , label, hint, , , , icon]) => ({ key, label: t(label), hint: t(hint), icon }))} onSelect={setCreating} />
    </div>
    {pairs.map((pair) => <div className="split-grid" key={pair[0][0]}>{pair.map(section)}</div>)}
    {current && <ResourceForm resource={current[0]} title={t(current[4])} data={data} user={user} onClose={() => setCreating(null)} onSaved={() => { setCreating(null); reload(); }} notify={notify} />}
  </div>;
}

// Photo editor: drag and zoom inside a 3:4 frame, then the framed part is saved as the profile photo.
const FRAME_W = 600;
const FRAME_H = 800;
function PhotoEditor({ file, hasPhoto, busy, onChoose, onRemove, onSave, onClose }) {
  const frame = useRef(null);
  const drag = useRef(null);
  const [src, setSrc] = useState('');
  const [nat, setNat] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const url = URL.createObjectURL(file);
    setSrc(url); setNat(null); setZoom(1); setFailed(false);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  const box = () => ({ w: frame.current?.clientWidth || 1, h: frame.current?.clientHeight || 1 });
  const base = nat ? Math.max(box().w / nat.w, box().h / nat.h) : 1;
  const clamp = (p, z) => {
    if (!nat) return p;
    const { w, h } = box();
    return { x: Math.min(0, Math.max(w - nat.w * base * z, p.x)), y: Math.min(0, Math.max(h - nat.h * base * z, p.y)) };
  };
  function loaded(event) {
    const el = event.currentTarget;
    const size = { w: el.naturalWidth, h: el.naturalHeight };
    const { w, h } = box();
    const scale = Math.max(w / size.w, h / size.h);
    setNat(size);
    setPos({ x: (w - size.w * scale) / 2, y: Math.min(0, (h - size.h * scale) * 0.3) });
  }
  function zoomTo(next) {
    const value = Math.min(3, Math.max(1, next));
    const { w, h } = box();
    const cx = (w / 2 - pos.x) / zoom;
    const cy = (h / 2 - pos.y) / zoom;
    setPos(clamp({ x: w / 2 - cx * value, y: h / 2 - cy * value }, value));
    setZoom(value);
  }
  const zoomRef = useRef(zoomTo);
  zoomRef.current = zoomTo;
  const zoomNow = useRef(zoom);
  zoomNow.current = zoom;
  // The wheel zooms the frame instead of scrolling the page behind the dialog.
  useEffect(() => {
    const el = frame.current;
    if (!el) return undefined;
    const wheel = (event) => { event.preventDefault(); zoomRef.current(zoomNow.current - event.deltaY * 0.002); };
    el.addEventListener('wheel', wheel, { passive: false });
    return () => el.removeEventListener('wheel', wheel);
  }, []);
  function keyDown(event) {
    const step = { ArrowLeft: [8, 0], ArrowRight: [-8, 0], ArrowUp: [0, 8], ArrowDown: [0, -8] }[event.key];
    if (!step) return;
    event.preventDefault();
    setPos((p) => clamp({ x: p.x + step[0], y: p.y + step[1] }, zoom));
  }
  function save() {
    const img = frame.current?.querySelector('img');
    if (!img || !nat) return;
    const { w, h } = box();
    const k = base * zoom;
    const canvas = document.createElement('canvas');
    canvas.width = FRAME_W; canvas.height = FRAME_H;
    canvas.getContext('2d').drawImage(img, -pos.x / k, -pos.y / k, w / k, h / k, 0, 0, FRAME_W, FRAME_H);
    canvas.toBlob((blob) => { if (blob) onSave(new File([blob], 'photo.jpg', { type: 'image/jpeg' })); }, 'image/jpeg', 0.9);
  }
  const imgStyle = nat ? { width: nat.w * base * zoom, transform: `translate(${pos.x}px, ${pos.y}px)` } : undefined;
  const previewStyle = nat ? { width: `${(nat.w * base * zoom / box().w) * 100}%`, left: `${(pos.x / box().w) * 100}%`, top: `${(pos.y / box().h) * 100}%` } : undefined;
  return <Modal title={t('Place your photo')} onClose={busy ? () => {} : onClose} className="nb-photo-modal">
    <p className="nb-photo-hint">{t('Drag and zoom. Keep your face in the middle of the frame.')}</p>
    {failed ? <p className="alert error" role="alert">{t('This image could not be opened. Choose another one.')}</p> : <div className="nb-photo-ed">
      <div className="nb-photo-main">
        <div ref={frame} className="nb-photo-frame" tabIndex={0} aria-label={t('Drag and zoom. Keep your face in the middle of the frame.')} onKeyDown={keyDown}
          onPointerDown={(event) => { drag.current = { x: event.clientX - pos.x, y: event.clientY - pos.y }; event.currentTarget.setPointerCapture?.(event.pointerId); }}
          onPointerMove={(event) => { if (drag.current) setPos(clamp({ x: event.clientX - drag.current.x, y: event.clientY - drag.current.y }, zoom)); }}
          onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
          {src && <img src={src} alt="" draggable={false} style={imgStyle} onLoad={loaded} onError={() => setFailed(true)} />}
        </div>
        <label className="nb-photo-zoom"><Search size={16} aria-hidden="true" /><span className="sr-only">{t('Zoom')}</span>
          <input type="range" min="1" max="3" step="0.01" value={zoom} onChange={(event) => zoomTo(Number(event.target.value))} /></label>
      </div>
      <div className="nb-photo-side"><p>{t('How it will look')}</p>
        <div className="nb-photo-preview"><span><img src={src} alt="" style={previewStyle} /></span></div>
      </div>
    </div>}
    <div className="nb-photo-actions">
      {hasPhoto && <button type="button" className="nb-btn nb-btn-ghost nb-btn-sm" onClick={onRemove} disabled={busy}>{t('Remove photo')}</button>}
      <button type="button" className="nb-btn nb-btn-ghost nb-btn-sm" onClick={onChoose} disabled={busy}>{t('Choose another')}</button>
      <span className="nb-photo-gap" />
      <button type="button" className="nb-btn nb-btn-ghost nb-btn-sm" onClick={onClose} disabled={busy}>{t('Cancel')}</button>
      <button type="button" className="nb-btn nb-btn-sm" onClick={save} disabled={busy || !nat || failed} aria-busy={busy}>{t('Use photo')}</button>
    </div>
  </Modal>;
}

// A progress dial with its percent inside.
function IdDial({ percent, label }) {
  return <span className="nb-id-dial" role="img" aria-label={`${label}: ${percent}%`} style={{ '--pct': `${percent}%` }}><b aria-hidden="true">{percent}%</b></span>;
}

// The student ID card, the contact and goal chips and the two readiness dials, from the profile the student already has.
function StudentIdCard({ student, user, reload, notify }) {
  const fileInput = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [picked, setPicked] = useState(null);
  if (!student) return null;
  function choosePhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (file) setPicked(file);
  }
  // The photo is saved at once with the request the profile's own photo field makes (students/<id>/photo/).
  async function savePhoto(file) {
    if (uploading) return;
    setUploading(true);
    try { await api.uploadStudentPhoto(student.id, file); notify?.(t('Photo updated.')); setPicked(null); reload?.(); }
    catch (err) { notify?.(err.message, 'error'); }
    finally { setUploading(false); }
  }
  async function removePhoto() {
    if (uploading) return;
    setUploading(true);
    try { await api.removeStudentPhoto(student.id); notify?.(t('Photo removed.')); setPicked(null); reload?.(); }
    catch (err) { notify?.(err.message, 'error'); }
    finally { setUploading(false); }
  }
  const readyDone = Number(student.readiness_items_done) || 0;
  const readyTotal = Number(student.readiness_items_total) || 0;
  const readyPercent = readyTotal ? Math.round((readyDone / readyTotal) * 100) : null;
  const profile = student.profile_readiness;
  const profilePercent = profile ? Math.max(0, Math.min(100, Math.round(Number(profile.percent) || 0))) : null;
  const hints = readinessHints(profile);
  const answers = student.application_profile || {};
  const name = fullName(student.user_detail) || fullName(user);
  const countries = listText(student.target_countries);
  const email = contactEmail(student.user_detail?.email);
  const chips = [[Mail, email], [Target, student.target_major], [Globe2, countries], [MapPin, student.school_name]].filter(([, value]) => value);
  return <section className="nb-id-wrap" aria-label={t('Student ID')}>
    <article className="nb-id-card">
      <p className="nb-id-head"><BrandLogo className="nb-id-logo" />{t('Naseeb Edu')} · {t('Student')}</p>
      <div className="nb-id-body">
        <span className="nb-id-photo-wrap">
          <StudentAvatar student={student} className="nb-id-photo" />
          <button type="button" className="nb-id-photo-edit" onClick={() => fileInput.current?.click()} disabled={uploading} aria-busy={uploading} aria-label={t('Change photo')} title={t('Change photo')}><Camera size={16} aria-hidden="true" /></button>
          <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" tabIndex={-1} aria-hidden="true" onChange={choosePhoto} />
        </span>
        <div className="nb-id-text">
          <h2>{name}</h2>
          <dl>
            {student.grade != null && student.grade !== '' && <div><dt>{t('Grade')}</dt><dd>{gradeText(student.grade)}</dd></div>}
            {student.school_name && <div><dt>{t('School')}</dt><dd>{student.school_name}</dd></div>}
          </dl>
        </div>
      </div>
      <p className="nb-id-foot"><span>{answers.graduation_year ? tx`Class of ${String(answers.graduation_year)}` : ''}</span><span>{countries}</span></p>
    </article>
    <div className="nb-id-right">
      {chips.length > 0 && <div className="nb-id-chips"><p className="eyebrow">{t('Contact and goal')}</p><div>{chips.map(([Icon, value]) => <span key={value}><Icon size={16} aria-hidden="true" />{value}</span>)}</div></div>}
      {(profilePercent != null || readyPercent != null) && <div className="nb-id-dials">
        {profilePercent != null && <div className="nb-id-dialblk"><IdDial percent={profilePercent} label={t('Profile ready')} />
          <div><b>{t('Profile ready')}</b>{student.counselor_name && <small>{tx`Counselor: ${student.counselor_name}`}</small>}{hints.length > 0 && <small className="nb-id-raise">{t('To raise it:')} {hints.map((hint) => t(hint.text)).join(', ')}.</small>}</div></div>}
        {readyPercent != null && <div className="nb-id-dialblk"><IdDial percent={readyPercent} label={t('Application readiness')} />
          <div><b>{t('Application readiness')}</b><small>{tp('{done} of {n} item finished|{done} of {n} items finished', readyTotal, { done: readyDone, n: readyTotal })}</small></div></div>}
      </div>}
    </div>
    {picked && <PhotoEditor file={picked} hasPhoto={Boolean(student.has_photo)} busy={uploading} onChoose={() => fileInput.current?.click()} onRemove={removePhoto} onSave={savePhoto} onClose={() => setPicked(null)} />}
  </section>;
}

const CV_RECORDS = ['activities', 'internships', 'researches', 'projects', 'honors', 'achievements'];

// The open tab lives in the URL (/student-center/documents), so it survives a
// reload and back/forward. Profile answers are edited in place on their cards;
// ?edit=<section> opens one card in edit mode.
export function StudentCenterPage({ user, data, query, reload, notify, tab = 'overview', onTab, setPage, editSection = null, onEditDone }) {
  const student = ownStudent(data);
  const sections = { reload, notify, onEditDone, student, data };
  // Changes when the profile or a CV record is saved, so the prefetched CV is loaded again.
  const cvKey = [student?.updated_at, ...CV_RECORDS.map((kind) => (data?.[kind] || []).map((item) => `${item.id}:${item.updated_at}`).join(','))].join('|');
  const roadmapLocked = isPageLocked('roadmap', user);
  const taskCount = Object.values(student?.task_status_counts || {}).reduce((sum, value) => sum + (Number(value) || 0), 0);
  const applicationCount = (data?.applications || []).filter((item) => !student || Number(item.student) === Number(student.id)).length;
  const tabs = [['overview', 'Overview'], ['academics', 'Academics'], ['portfolio', 'Portfolio'], ['activities', 'Activities & honors'], ['documents', 'Documents']].map(([key, text]) => ({ key, label: t(text) }));
  return <div className="section-stack student-portal nb-center">
    <PageHeader title={t('Student Center')} subtitle={t('Academic profile, portfolio, activities, and documents')} actions={<DownloadCvButton refreshKey={cvKey} notify={notify} className="nb-btn nb-btn-ghost nb-btn-sm" />} />
    {tab === 'overview' && student && <KpiRow label={t('Student Center')} columns={roadmapLocked ? 2 : 4}>
      {!roadmapLocked && <KpiTile tone={0} icon={Trophy} value={student.level ?? 1} label={<>{t('Level')}<small className="nb-kpi-note">{t('Approved by staff')}</small></>} />}
      {!roadmapLocked && <KpiTile tone={1} icon={Star} value={student.roadmap_stars ?? 0} label={<>{t('Stars')}<small className="nb-kpi-note">{t('One per approved roadmap mission')}</small></>} />}
      <KpiTile tone={2} icon={ClipboardCheck} value={taskCount} label={t('Assigned tasks')} onClick={setPage ? () => setPage('roadmap', roadmapLocked ? undefined : { tab: 'tasks' }) : undefined} actionLabel={setPage ? `${t('Assigned tasks')}: ${taskCount}` : undefined} />
      <KpiTile tone={3} icon={GraduationCap} value={applicationCount} label={t('Applications')} onClick={setPage ? () => setPage('applications') : undefined} actionLabel={setPage ? `${t('Applications')}: ${applicationCount}` : undefined} />
    </KpiRow>}
    {tab === 'overview' && <StudentIdCard student={student} user={user} reload={reload} notify={notify} />}
    <div className="student-center-head">
      <PillTabs tabs={tabs} value={tab} onChange={onTab} label={t('Student Center')} idPrefix="center" />
    </div>
    <div role="tabpanel" aria-labelledby={tabId('center', tab)} className="section-stack nb-center-panel">
      {tab === 'overview' && <StudentOverview student={student} data={data} user={user} notify={notify} roadmapLocked={roadmapLocked} profile={<ProfileSections {...sections} editSection={editSection} onOpenRecords={() => { onTab('activities'); window.scrollTo({ top: 0, left: 0, behavior: 'auto' }); }} />} />}
      {tab === 'academics' && <div className="section-stack"><ProfileSections {...sections} sections={['academics', 'tests']} showReadiness={false} /><ResourceSection title={t("Research & academic work")} resource="researches" {...{ user, data, query, reload, notify }} /></div>}
      {TAB_RESOURCES[tab] && <ResourceTab key={tab} tab={tab} {...{ user, data, query, reload, notify }} />}
      {tab === 'documents' && <DocumentsPage {...{ user, data, query, reload, notify }} />}
    </div>
  </div>;
}
