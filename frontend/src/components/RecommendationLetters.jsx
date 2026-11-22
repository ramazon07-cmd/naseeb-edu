import { useState } from 'react';
import { CheckCircle2, MessageSquareWarning, Plus } from 'lucide-react';
import { api } from '../api';
import { t, tx } from '../i18n';
import { dateText, joinParts } from '../lib/format';
import { label } from '../lib/labels';
import { recordErrorMessage } from '../lib/recordRights';
import { CxCard, CxTag } from './counselorUi';
import { Field } from './forms';
import { Modal } from './ui';
import './recommendation-letters.css';

// The counselor's list of letters and the student's read view. The student reads a letter only
// once it is shared (the API leaves the text out until then).

const STATUS_TONE = { drafting: 'warn', submitted: 'ok', approved: 'ok' };

function letterState(letter) {
  if (!letter.has_body) return t('Not written yet');
  if (!letter.shared_with_student) return t('Private');
  if (letter.student_review === 'confirmed') return t('Confirmed by the student');
  return letter.student_review === 'changes_requested' ? t('The student asked for changes') : t('Shared with the student');
}

// What the student answered about the shared text, shown to the counselor.
export function StudentReviewNote({ letter, name }) {
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

// Student 360 → Recommendations: every letter for the student. Writing and editing happen on the
// full-page workspace (src/letters), opened through `onOpen(letterId | 'new')`.
export function RecommendationLetters({ letters, loading, onOpen }) {
  return <CxCard title={t('Recommendation letters')} action={<button type="button" className="cx-btn primary" disabled={loading} onClick={() => onOpen('new')}><Plus size={15} aria-hidden="true" />{t('Write a letter')}</button>}>
    <div className="cx-list letter-list" aria-busy={loading}>
      {loading && !letters.length && <p className="cx-empty" role="status">{t('Loading recommendation letters…')}</p>}
      {letters.map((letter) => <button type="button" className="cx-row" key={letter.id} onClick={() => onOpen(letter.id)}>
        <span className="cx-row-copy"><b>{letter.recommender_name}</b><small>{joinParts(letter.recommender_title, letter.deadline && tx`Deadline: ${dateText(letter.deadline)}`, letterState(letter))}</small></span>
        {letter.shared_with_student && letter.student_review === 'changes_requested' && <CxTag tone="warn" small>{label('changes_requested')}</CxTag>}
        <CxTag tone={STATUS_TONE[letter.status] || 'quiet'} small>{label(letter.status)}</CxTag>
      </button>)}
      {!loading && !letters.length && <p className="cx-empty">{t('No recommendation letters yet.')}</p>}
    </div>
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
