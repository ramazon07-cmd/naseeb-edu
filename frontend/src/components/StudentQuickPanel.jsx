import { useEffect, useId, useRef, useState } from 'react';
import { ArrowRight, Lock, MessageCircle, X } from 'lucide-react';
import { api } from '../api';
import { t, tp } from '../i18n';
import { CxAvatar, CxTag } from './counselorUi';
import { dayMonthText, gradeOrPending, joinParts, localDateKey } from '../lib/format';
import { fullName } from '../lib/labels';
import { splitList } from '../lib/profileSections';
import { attentionItems, quickRecordEndpoints, weekDeadlines } from '../lib/studentQuickLook';

// Only what the quick look lists. Essays, notes and letter files are never loaded here;
// achievements only while they wait for review, as the list's "To review" counts them.
const ATTENTION_LIMIT = 6;

function useQuickRecords(studentId, user) {
  const endpoints = quickRecordEndpoints(user);
  const [state, setState] = useState({ studentId: null, records: {}, loading: true, error: '' });
  useEffect(() => {
    let current = true;
    setState({ studentId, records: {}, loading: true, error: '' });
    const student = `student=${encodeURIComponent(studentId)}`;
    Promise.allSettled(endpoints.map((endpoint) => api.list(endpoint, endpoint === 'achievements' ? `?awaiting_review=true&${student}` : `?${student}`))).then((settled) => {
      if (!current) return;
      const records = {};
      let error = '';
      settled.forEach((result, index) => {
        if (result.status === 'fulfilled') records[endpoints[index]] = result.value || [];
        else error ||= result.reason?.message || t('Some information could not be loaded');
      });
      setState({ studentId, records, loading: false, error });
    });
    return () => {current = false;};
  }, [studentId, endpoints]);
  return state.studentId === studentId ? state : { records: {}, loading: true, error: '' };
}

function attentionText(item) {
  if (item.kind === 'late_task') return t('Late task: {title}', { title: item.title });
  if (item.kind === 'missing_document') return t('{title} not uploaded', { title: item.title });
  return t('To review: {title}', { title: item.title });
}

function deadlineTitle(item) {
  if (item.kind === 'application') return t('{name} application', { name: item.title || t('University') });
  if (item.kind === 'letter') return item.title ? t('Letter from {name}', { name: item.title }) : t('Recommendation letter');
  return item.title;
}

const ATTENTION_TONE = { late_task: 'late', missing_document: 'late', review: 'warn' };
const ATTENTION_TAG = { late_task: 'Late', missing_document: 'Missing', review: 'To review' };

// A side panel (a bottom sheet on phones) with one student's urgent work and this
// week's deadlines; Student 360 stays one click away.
export function StudentQuickPanel({ user, student, onClose, onOpen, onDirect }) {
  const titleId = useId();
  const closeRef = useRef(null);
  const { records, loading, error } = useQuickRecords(student.id, user);
  const today = localDateKey();
  const attention = attentionItems(records, today);
  const deadlines = weekDeadlines(records, today);
  const name = fullName(student.user_detail);
  const meta = joinParts(gradeOrPending(student.grade), splitList(student.target_countries).map((country) => t(country)).join(', '));

  useEffect(() => {
    const previous = document.activeElement;
    closeRef.current?.focus();
    const onKey = (event) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      if (previous && typeof previous.focus === 'function') previous.focus();
    };
  }, [onClose]);

  return <div className="cs-panel-layer">
    <div className="cs-panel-scrim" onClick={onClose} aria-hidden="true" />
    <aside className="cs-panel" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <header className="cs-panel-head">
        <CxAvatar name={name} className="cs-panel-avatar" />
        <div>
          <span className="cs-kicker">{t("Quick look")}</span>
          <h2 id={titleId}>{name}</h2>
          {meta && <p>{meta}</p>}
        </div>
        <button type="button" ref={closeRef} className="cs-icon-btn" onClick={onClose} aria-label={t("Close")}><X size={18} aria-hidden="true" /></button>
      </header>

      {error && <div className="alert error" role="alert">{error}</div>}

      <section className="cs-panel-section">
        <h3>{t("What needs attention")}</h3>
        {loading ? <p className="cs-panel-muted" aria-busy="true">{t("Loading…")}</p> : attention.length ? <ul className="cs-panel-list">
          {attention.slice(0, ATTENTION_LIMIT).map((item) => <li key={item.key}>
            <CxTag tone={ATTENTION_TONE[item.kind]} small>{t(ATTENTION_TAG[item.kind])}</CxTag>
            <span className="cs-panel-copy">{attentionText(item)}{item.due && <small>{t('due {date}', { date: dayMonthText(item.due) })}</small>}</span>
          </li>)}
          {attention.length > ATTENTION_LIMIT && <li className="cs-panel-more">{tp('{n} more in Student 360|{n} more in Student 360', attention.length - ATTENTION_LIMIT, { n: attention.length - ATTENTION_LIMIT })}</li>}
        </ul> : <p className="cs-panel-muted">{t("Nothing needs your attention right now.")}</p>}
      </section>

      <section className="cs-panel-section">
        <h3>{t("Their deadlines this week")}</h3>
        {loading ? <p className="cs-panel-muted" aria-busy="true">{t("Loading…")}</p> : deadlines.length ? <ul className="cs-panel-list cs-panel-deadlines">
          {deadlines.map((item) => <li key={item.key}>
            <span className="cs-panel-copy">{deadlineTitle(item)}<small>{dayMonthText(item.due)}</small></span>
            {item.late && <CxTag tone="late" small>{t("Late")}</CxTag>}
          </li>)}
        </ul> : <p className="cs-panel-muted">{t("No deadlines this week.")}</p>}
      </section>

      <p className="cs-panel-note"><Lock size={16} aria-hidden="true" /><span>{t("Private notes and drafts are never shown here.")}</span></p>

      <div className="cs-panel-actions">
        <button type="button" className="cx-btn" onClick={() => onDirect?.(student.user_detail?.id)} disabled={!onDirect || !student.user_detail?.id}><MessageCircle size={15} aria-hidden="true" />{t("Message")}</button>
        <button type="button" className="cx-btn primary" onClick={() => onOpen(student)}>{t("Open student")}<ArrowRight size={15} aria-hidden="true" /></button>
      </div>
    </aside>
  </div>;
}
