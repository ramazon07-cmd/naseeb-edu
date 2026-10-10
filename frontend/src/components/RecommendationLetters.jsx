import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, Lightbulb, MessageSquareWarning, Plus, RefreshCw } from 'lucide-react';
import { api } from '../api';
import { formatNumberLocale, t, tp, tx } from '../i18n';
import { dateText, joinParts } from '../lib/format';
import { fullName, label } from '../lib/labels';
import { recordErrorMessage } from '../lib/recordRights';
import { CxCard, CxTag } from './counselorUi';
import { CheckboxControl, Field } from './forms';
import { Modal } from './ui';
import './recommendation-letters.css';

// A counselor writes the letter here; the student reads it only once it is
// shared (the API leaves the text out until then). While the counselor
// writes, the side panel suggests what to add from the student's profile.

const STATUSES = ['requested', 'drafting', 'submitted', 'approved'];
const STATUS_TONE = { drafting: 'warn', submitted: 'ok', approved: 'ok' };
const SOURCE_LABELS = { academics: 'Academics', honor: 'Honor', activity: 'Activity', achievement: 'Achievement', research: 'Research', internship: 'Internship', project: 'Project' };
const TIPS = {
  opening: 'Open with how long and in what role you have known {name}.',
  closing: 'End with a clear recommendation, for example “I recommend {name} without reservation.”',
  length: 'Most letters fit on one page: about 500 to 700 words.',
};
// Suggestions refresh once the counselor pauses and the draft has moved on.
const REFRESH_PAUSE_MS = 2500;
const REFRESH_MIN_CHANGE = 60;

const paragraphCount = (text) => text.split(/\n\s*\n/).filter((part) => part.trim()).length;

function changedEnough(previous, next) {
  if (previous === null) return true;
  return Math.abs(next.length - previous.length) >= REFRESH_MIN_CHANGE
    || paragraphCount(next) !== paragraphCount(previous)
    || !previous.trim() !== !next.trim();
}

function letterState(letter) {
  if (!letter.has_body) return t('Not written yet');
  if (!letter.shared_with_student) return t('Private');
  if (letter.student_review === 'confirmed') return t('Confirmed by the student');
  return letter.student_review === 'changes_requested' ? t('The student asked for changes') : t('Shared with the student');
}

// What the student answered about the shared text, shown to the counselor.
function StudentReviewNote({ letter, name }) {
  if (letter?.student_review === 'confirmed') return <p className="letter-review is-ok"><CheckCircle2 size={16} aria-hidden="true" /><span>{tx`${name} confirmed this letter on ${dateText(letter.student_reviewed_at)}.`}</span></p>;
  if (letter?.student_review !== 'changes_requested') return null;
  return <div className="letter-review is-warn" role="note">
    <MessageSquareWarning size={16} aria-hidden="true" />
    <div>
      <b>{tx`${name} asked for changes on ${dateText(letter.student_reviewed_at)}`}</b>
      <p className="letter-review-note">{letter.student_review_note}</p>
      <small>{t('Saving a new text sends the letter back to the student to check.')}</small>
    </div>
  </div>;
}

function useLetterSuggestions(studentId, form) {
  const [state, setState] = useState({ items: [], source: '', loading: true, error: '' });
  const sent = useRef(null);
  const controller = useRef(null);
  const latest = useRef(form);
  latest.current = form;

  const refresh = useCallback(async () => {
    const { body, recommender_title, relationship } = latest.current;
    const previous = sent.current;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    sent.current = body;
    setState((current) => ({ ...current, loading: true, error: '' }));
    try {
      const result = await api.letterSuggestions({ student: studentId, draft: body, recommender_title, relationship }, request.signal);
      if (!request.signal.aborted) setState({ items: result.suggestions || [], source: result.source, loading: false, error: '' });
    } catch (err) {
      if (request.signal.aborted) return;
      // Asked too soon after the last request: keep what is shown and ask at the next pause.
      if (err.status === 429) sent.current = previous;
      setState((current) => ({ ...current, loading: false, error: err.status === 429 ? '' : err.message }));
    }
  }, [studentId]);

  useEffect(() => {
    if (!changedEnough(sent.current, form.body)) return undefined;
    const timer = window.setTimeout(refresh, sent.current === null ? 0 : REFRESH_PAUSE_MS);
    return () => window.clearTimeout(timer);
  }, [form.body, refresh]);
  useEffect(() => () => controller.current?.abort(), []);
  return { ...state, refresh };
}

function Suggestion({ item, name, onInsert }) {
  const fill = (text) => text.replaceAll('[Student]', name);
  if (item.kind === 'tip') return <li className="letter-suggestion is-tip"><p>{t(TIPS[item.code] || '', { name })}</p></li>;
  if (item.kind === 'fact') return <li className="letter-suggestion is-fact">
    <span className="letter-suggestion-source">{t(SOURCE_LABELS[item.source] || 'Profile')}</span>
    {item.title && <b>{item.title}</b>}
    {item.detail && <p>{item.detail}</p>}
  </li>;
  return <li className={`letter-suggestion is-${item.kind}`}>
    {item.source && <span className="letter-suggestion-source">{item.source}</span>}
    <p>{fill(item.text)}</p>
    {item.kind === 'sentence' && <button type="button" className="cx-btn" onClick={() => onInsert(fill(item.text))}>{t('Insert')}</button>}
  </li>;
}

function SuggestionPanel({ items, source, loading, error, refresh, name, onInsert }) {
  const facts = items.filter((item) => item.kind === 'fact');
  const others = items.filter((item) => item.kind !== 'fact');
  const show = (item, index) => <Suggestion key={`${item.kind}-${index}-${item.title || item.code || item.text}`} item={item} name={name} onInsert={onInsert} />;
  return <aside className="letter-suggestions" aria-labelledby="letter-suggestions-title">
    <header>
      <div>
        <h3 id="letter-suggestions-title"><Lightbulb size={16} aria-hidden="true" />{t('Suggestions')}</h3>
        <small>{source === 'ai' ? t('AI, from {name}’s profile', { name }) : t('From {name}’s profile', { name })}</small>
      </div>
      <button type="button" className="icon-button" onClick={refresh} disabled={loading} aria-busy={loading} aria-label={t('Refresh suggestions')} title={t('Refresh suggestions')}><RefreshCw size={16} className={loading ? 'spin' : ''} /></button>
    </header>
    <p className="sr-only" role="status">{loading ? t('Updating suggestions…') : ''}</p>
    {error && <p className="letter-suggestions-error" role="alert">{error} <button type="button" className="link-button" onClick={refresh}>{t('Retry')}</button></p>}
    {loading && !items.length && <p className="letter-suggestions-note">{t('Reading the profile…')}</p>}
    {!loading && !error && !items.length && <p className="letter-suggestions-note">{t('Nothing new to suggest from the profile.')}</p>}
    {others.length > 0 && <ul>{others.map(show)}</ul>}
    {facts.length > 0 && <>
      <p className="letter-suggestions-group">{t('Not in the letter yet')}</p>
      <ul>{facts.map(show)}</ul>
    </>}
    <p className="letter-suggestions-note">{t('Suggestions can be wrong. Check every fact before you send the letter.')}</p>
  </aside>;
}

function LetterEditor({ letter, student, user, onClose, onSaved, notify }) {
  const initial = useMemo(() => ({
    recommender_name: letter?.recommender_name ?? fullName(user),
    recommender_title: letter?.recommender_title ?? (user.position || ''),
    relationship: letter?.relationship ?? '',
    deadline: letter?.deadline ?? '',
    status: letter?.status ?? 'drafting',
    body: letter?.body ?? '',
    shared_with_student: letter?.shared_with_student ?? false,
  }), [letter, user]);
  const [form, setForm] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const textRef = useRef(null);
  const suggestions = useLetterSuggestions(student.id, form);
  const name = student.user_detail?.first_name || fullName(student.user_detail);
  const dirty = Object.keys(initial).some((key) => form[key] !== initial[key]);
  const words = form.body.trim() ? form.body.trim().split(/\s+/).length : 0;
  const set = (key) => (event) => {
    const { type, checked, value } = event.target;
    setForm((current) => ({ ...current, [key]: type === 'checkbox' ? checked : value }));
  };

  function close() {
    if (saving) return;
    if (dirty && !window.confirm(t('Discard your changes to this letter?'))) return;
    onClose();
  }

  // Puts a suggested sentence where the counselor's cursor was (a textarea keeps
  // its selection while the Insert button has focus), or at the end.
  function insert(text) {
    const area = textRef.current;
    const [start, end] = area ? [area.selectionStart, area.selectionEnd] : [form.body.length, form.body.length];
    const before = form.body.slice(0, start);
    const after = form.body.slice(end);
    const lead = before && !/\s$/.test(before) ? ' ' : '';
    const trail = after && !/^\s/.test(after) ? ' ' : '';
    const position = before.length + lead.length + text.length;
    setForm((current) => ({ ...current, body: `${before}${lead}${text}${trail}${after}` }));
    window.requestAnimationFrame(() => {
      textRef.current?.focus();
      textRef.current?.setSelectionRange(position, position);
    });
  }

  async function save(event) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError('');
    const payload = { ...form, deadline: form.deadline || null };
    try {
      const saved = letter ? await api.update('recommendations', letter.id, payload) : await api.create('recommendations', { ...payload, student: student.id });
      notify(t('Letter saved.'));
      onSaved(saved);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return <Modal title={t('Recommendation letter')} onClose={close} className="letter-editor-modal">
    <form className="letter-editor" onSubmit={save}>
      <div className="letter-editor-main">
        <p className="letter-editor-for">{tx`For ${fullName(student.user_detail)}`}</p>
        <div className="letter-editor-fields">
          <Field label="Recommender name"><input value={form.recommender_name} onChange={set('recommender_name')} required maxLength={180} /></Field>
          <Field label="Position"><input value={form.recommender_title} onChange={set('recommender_title')} maxLength={180} placeholder={t('e.g. School counselor')} /></Field>
          <Field label="Deadline"><input type="date" value={form.deadline} onChange={set('deadline')} /></Field>
          <Field label="Status"><select value={form.status} onChange={set('status')}>{STATUSES.map((status) => <option key={status} value={status}>{label(status)}</option>)}</select></Field>
          <Field label="How you know the student"><input value={form.relationship} onChange={set('relationship')} maxLength={180} placeholder={t('e.g. Counselor since grade 9')} /></Field>
        </div>
        <StudentReviewNote letter={letter} name={name} />
        <Field label="Letter" hint={tp('{n} word|{n} words', words, { n: formatNumberLocale(words) })}>
          <textarea ref={textRef} className="letter-editor-text" value={form.body} onChange={set('body')} maxLength={20000} placeholder={t('Write the letter here. Suggestions from the profile follow what you write.')} />
        </Field>
        <CheckboxControl checked={form.shared_with_student} onChange={set('shared_with_student')}>{t('Show this letter to the student')}</CheckboxControl>
        <p className="letter-editor-privacy">{form.shared_with_student ? t('The student can read the letter.') : t('The student sees who writes the letter and its status, but not the text.')}</p>
      </div>
      <SuggestionPanel {...suggestions} name={name} onInsert={insert} />
      {error && <p className="alert error letter-editor-error" role="alert">{error}</p>}
      <div className="form-actions">
        <button type="button" className="button quiet" onClick={close}>{t('Cancel')}</button>
        <button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t('Saving…') : t('Save')}</button>
      </div>
    </form>
  </Modal>;
}

// Student 360 → Recommendations: every letter for the student, and the editor.
export function RecommendationLetters({ student, user, letters, loading, onSaved, notify }) {
  const [editing, setEditing] = useState(null);
  return <CxCard title={t('Recommendation letters')} action={<button type="button" className="cx-btn primary" disabled={loading} onClick={() => setEditing({})}><Plus size={15} aria-hidden="true" />{t('Write a letter')}</button>}>
    <div className="cx-list letter-list" aria-busy={loading}>
      {loading && !letters.length && <p className="cx-empty" role="status">{t('Loading recommendation letters…')}</p>}
      {letters.map((letter) => <button type="button" className="cx-row" key={letter.id} onClick={() => setEditing(letter)}>
        <span className="cx-row-copy"><b>{letter.recommender_name}</b><small>{joinParts(letter.recommender_title, letter.deadline && tx`Deadline: ${dateText(letter.deadline)}`, letterState(letter))}</small></span>
        {letter.shared_with_student && letter.student_review === 'changes_requested' && <CxTag tone="warn" small>{label('changes_requested')}</CxTag>}
        <CxTag tone={STATUS_TONE[letter.status] || 'quiet'} small>{label(letter.status)}</CxTag>
      </button>)}
      {!loading && !letters.length && <p className="cx-empty">{t('No recommendation letters yet.')}</p>}
    </div>
    {editing && <LetterEditor letter={editing.id ? editing : null} student={student} user={user} notify={notify} onClose={() => setEditing(null)} onSaved={(saved) => { setEditing(null); onSaved(saved); }} />}
  </CxCard>;
}

// The student's last answer about the letter, in their own words.
function OwnReview({ letter }) {
  const date = dateText(letter.student_reviewed_at);
  if (letter.student_review === 'confirmed') return <p className="letter-review is-ok" role="status"><CheckCircle2 size={16} aria-hidden="true" /><span>{tx`You confirmed this letter on ${date}.`}</span></p>;
  if (letter.student_review === 'changes_requested') return <div className="letter-review is-warn" role="status">
    <MessageSquareWarning size={16} aria-hidden="true" />
    <div><b>{tx`You asked for changes on ${date}`}</b><p className="letter-review-note">{letter.student_review_note}</p></div>
  </div>;
  return <p className="letter-review-prompt">{t('Read the letter and tell your counselor whether everything in it is correct.')}</p>;
}

// The student's view of a letter their counselor shared: they confirm it or
// ask for changes, and the counselor sees the answer in Student 360.
export function LetterTextModal({ letter, onClose, onReviewed, notify }) {
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState(letter.student_review === 'changes_requested' ? letter.student_review_note : '');
  const [sending, setSending] = useState('');
  const [error, setError] = useState('');

  async function answer(decision) {
    if (sending) return;
    setSending(decision);
    setError('');
    try {
      const updated = await api.reviewLetter(letter.id, { decision, note: decision === 'changes_requested' ? note : '', reviewed_body: letter.body });
      notify(decision === 'confirmed' ? t('Your counselor will see that the letter is correct.') : t('Your request was sent to your counselor.'));
      setAsking(false);
      onReviewed(updated);
    } catch (err) {
      setError(recordErrorMessage(err));
    } finally {
      setSending('');
    }
  }

  function close() {
    if (sending) return;
    if (asking && note.trim() !== (letter.student_review_note || '').trim() && !window.confirm(t('Discard your change request?'))) return;
    onClose();
  }

  return <Modal title={t('Recommendation letter')} onClose={close} className="letter-read-modal">
    <div className="letter-read">
      <header className="letter-read-meta"><strong>{letter.recommender_name}</strong><span>{joinParts(letter.recommender_title, letter.relationship)}</span></header>
      <article className="letter-read-text" aria-label={t('Letter')}>{letter.body}</article>
      {error && <p className="alert error" role="alert">{error}</p>}
      {asking ? <form className="letter-review-form" onSubmit={(event) => { event.preventDefault(); answer('changes_requested'); }}>
        <Field label="What should your counselor change?"><textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} required autoFocus placeholder={t('e.g. My robotics award was in 2025, not 2024.')} /></Field>
        <div className="form-actions">
          <button type="button" className="button quiet" disabled={Boolean(sending)} onClick={() => setAsking(false)}>{t('Cancel')}</button>
          <button className="button primary" disabled={Boolean(sending) || !note.trim()} aria-busy={sending === 'changes_requested'}>{sending ? t('Sending…') : t('Send request')}</button>
        </div>
      </form> : <>
        <OwnReview letter={letter} />
        <div className="form-actions">
          <button type="button" className="button quiet" disabled={Boolean(sending)} onClick={close}>{t('Close')}</button>
          <button type="button" className="button quiet" disabled={Boolean(sending)} onClick={() => setAsking(true)}>{t('Ask for changes')}</button>
          {letter.student_review !== 'confirmed' && <button type="button" className="button primary" disabled={Boolean(sending)} aria-busy={sending === 'confirmed'} onClick={() => answer('confirmed')}><CheckCircle2 size={16} aria-hidden="true" /> {t('Everything is correct')}</button>}
        </div>
      </>}
    </div>
  </Modal>;
}
