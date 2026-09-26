import { Children, cloneElement } from 'react';
import { t, tx, formatNumberLocale } from '../i18n';
import { dateText } from '../lib/format';
import { IELTS_BANDS, IELTS_SECTIONS, MAX_ATTEMPTS, SUBJECT_SCORE_MAX, canSuperscore, ieltsOverall, satSentTotal } from '../lib/testScores';

// Test-score questions for the profile form. Each block takes the shared form
// state, so it can later be dropped into an inline editor one section at a time.

export const errorText = (error) => (error ? t(error[0], Object.fromEntries(error.slice(1).map((value, i) => [i, value]))) : '');

const STATUS_LABELS = {
  ielts: [['not_taken', "I haven't taken it yet"], ['planning', 'I plan to take it'], ['scheduled', 'I have booked a test date'], ['taken', 'I have my score'], ['not_required', "I don't need IELTS"]],
  sat: [['not_taken', "I haven't taken it yet"], ['planning', 'I plan to take it'], ['scheduled', 'I have booked a test date'], ['taken', 'I have my score'], ['not_required', "I don't need the SAT"]],
};

function Question({ name, label, help, error, wide = false, children }) {
  // Help and error text are linked with aria-describedby, not read as part of the label.
  const helpId = help ? `ts-help-${name.replaceAll('.', '-')}` : null;
  const errorId = error ? `ts-error-${name.replaceAll('.', '-')}` : null;
  const control = Children.only(children);
  const described = [helpId, errorId].filter(Boolean).join(' ') || undefined;
  const id = `ts-${name.replaceAll('.', '-')}`;
  return <div className={`onboarding-field${wide ? ' is-wide' : ''}`}>
    <label htmlFor={id}>{label}</label>
    {cloneElement(control, { id, name, 'aria-describedby': described, 'aria-invalid': error ? true : undefined })}
    {help && <small className="onboarding-help" id={helpId}>{help}</small>}
    {error && <small className="onboarding-field-error" id={errorId}>{errorText(error)}</small>}
  </div>;
}

function StatusQuestion({ test, label, help, form, update, errors }) {
  const key = `${test}_status`;
  return <Question name={key} label={label} help={help} error={errors[key]}>
    <select value={form[key] || 'not_taken'} onChange={(e) => update(key, e.target.value)}>
      {STATUS_LABELS[test].map(([value, text]) => <option key={value} value={value}>{t(text)}</option>)}
    </select>
  </Question>;
}

function DateQuestion({ name, status, form, update, errors }) {
  const label = status === 'taken' ? t('Test date') : status === 'scheduled' ? t('Booked test date') : t('When do you plan to take it? (optional)');
  const help = status === 'taken' ? t('The day you sat the test. It is printed on your score report.') : status === 'scheduled' ? t('The date on your booking confirmation.') : t('A rough date is fine. You can change it later.');
  return <Question name={name} label={label} help={help} error={errors[name]}>
    <input type="date" value={form[name] || ''} min="2015-01-01" onChange={(e) => update(name, e.target.value)} />
  </Question>;
}

function AttemptsQuestion({ name, label, form, update, errors }) {
  return <Question name={name} label={label} help={t('Count every test day, including this one.')} error={errors[name]}>
    <input type="number" inputMode="numeric" min="1" max={MAX_ATTEMPTS} step="1" placeholder="1" value={form[name] ?? ''} onChange={(e) => update(name, e.target.value)} />
  </Question>;
}

function BandSelect({ value, onChange, disabled = false, ...rest }) {
  return <select value={value ?? ''} onChange={(e) => onChange(e.target.value)} disabled={disabled} {...rest}>
    <option value="">{t('Select')}</option>
    {IELTS_BANDS.map((band) => <option key={band} value={String(band)}>{formatNumberLocale(band, { minimumFractionDigits: 1 })}</option>)}
  </select>;
}

export function IeltsFields({ form, update, errors = {} }) {
  const status = form.ielts_status || 'not_taken';
  const sections = IELTS_SECTIONS.map(([key]) => form[key]);
  const computed = ieltsOverall(sections);
  // A complete set of sections decides the overall band, so it follows them.
  const setSection = (key, value) => {
    update(key, value);
    const next = ieltsOverall(IELTS_SECTIONS.map(([name]) => (name === key ? value : form[name])));
    if (next != null) update('ielts_score', String(next));
  };
  return <section className="test-score-block" aria-labelledby="ts-ielts-title">
    <h3 id="ts-ielts-title">IELTS</h3>
    <p className="test-score-intro">{t('IELTS is an English test that many universities ask for.')}</p>
    <div className="onboarding-grid">
      <StatusQuestion test="ielts" label={t('Have you taken IELTS?')} form={form} update={update} errors={errors} />
      {['planning', 'scheduled'].includes(status) && <DateQuestion name="ielts_test_date" status={status} form={form} update={update} errors={errors} />}
    </div>
    {status === 'taken' && <>
      <fieldset className="test-score-sections">
        <legend>{t('Section scores')}</legend>
        <p className="onboarding-help">{t('Copy these from your score report. Each section is scored from 0 to 9 in half bands, like 6.5.')}</p>
        <div className="test-score-section-grid">
          {IELTS_SECTIONS.map(([key, label]) => <Question key={key} name={key} label={t(label)} error={errors[key]}>
            <BandSelect value={form[key]} onChange={(value) => setSection(key, value)} />
          </Question>)}
        </div>
      </fieldset>
      <div className="onboarding-grid">
        <Question name="ielts_score" label={t('Overall band')} error={errors.ielts_score}
          help={computed != null ? t('Worked out from your four section scores.') : t('Fill in the four sections and we work this out for you. If you only know your overall band, choose it here.')}>
          <BandSelect value={computed != null ? String(computed) : form.ielts_score} onChange={(value) => update('ielts_score', value)} disabled={computed != null} />
        </Question>
        <DateQuestion name="ielts_test_date" status="taken" form={form} update={update} errors={errors} />
        <AttemptsQuestion name="ielts_attempts" label={t('How many times have you taken IELTS?')} form={form} update={update} errors={errors} />
      </div>
    </>}
  </section>;
}

function SatScoreInput({ value, onChange, ...rest }) {
  return <input type="number" inputMode="numeric" min="200" max="800" step="10" value={value ?? ''} onChange={(e) => onChange(e.target.value)} {...rest} />;
}

export function SatFields({ form, update, errors = {} }) {
  const status = form.sat_status || 'not_taken';
  const dayTotal = satSentTotal({ sat_reading: form.sat_reading, sat_math: form.sat_math });
  const superscore = canSuperscore(form);
  const superTotal = form.sat_superscore === true ? satSentTotal(form) : null;
  const setAttempts = (value) => {
    update('sat_attempts', value);
    if (!(Number(value) >= 2) && form.sat_superscore != null) update('sat_superscore', null);
  };
  return <section className="test-score-block" aria-labelledby="ts-sat-title">
    <h3 id="ts-sat-title">SAT <small>({t('optional')})</small></h3>
    <p className="test-score-intro">{t('Many universities do not require the SAT. Skip it if it does not apply to you.')}</p>
    <div className="onboarding-grid">
      <StatusQuestion test="sat" label={t('Have you taken the SAT?')} form={form} update={update} errors={errors} />
      {['planning', 'scheduled'].includes(status) && <DateQuestion name="sat_test_date" status={status} form={form} update={update} errors={errors} />}
    </div>
    {status === 'taken' && <>
      <fieldset className="test-score-sections">
        <legend>{t('Scores from your best test day')}</legend>
        <p className="onboarding-help">{t('Each section is scored from 200 to 800 in steps of 10.')}</p>
        <div className="onboarding-grid">
          <Question name="sat_reading" label={t('Reading and Writing')} error={errors.sat_reading}><SatScoreInput value={form.sat_reading} onChange={(value) => update('sat_reading', value)} /></Question>
          <Question name="sat_math" label={t('Math')} error={errors.sat_math}><SatScoreInput value={form.sat_math} onChange={(value) => update('sat_math', value)} /></Question>
          <div className="test-score-total" aria-live="polite"><span>{t('Total')}</span><b>{dayTotal != null ? formatNumberLocale(dayTotal, { useGrouping: false }) : '—'}</b><small>{t('out of 1600')}</small></div>
        </div>
      </fieldset>
      <div className="onboarding-grid">
        <DateQuestion name="sat_test_date" status="taken" form={form} update={update} errors={errors} />
        <AttemptsQuestion name="sat_attempts" label={t('How many times have you taken the SAT?')} form={form} update={(_, value) => setAttempts(value)} errors={errors} />
      </div>
      {superscore && <fieldset className="test-score-choice" aria-describedby="ts-help-sat_superscore" aria-invalid={errors.sat_superscore ? true : undefined}>
        <legend>{t('Will you send a superscore?')}</legend>
        <small className="onboarding-help" id="ts-help-sat_superscore">{t('A superscore adds your best Reading and Writing score and your best Math score, even if they came from different test days.')}</small>
        <div className="onboarding-choices">
          {[[true, 'Yes'], [false, 'No']].map(([value, text]) => <label key={text}><input type="radio" name="sat_superscore" checked={form.sat_superscore === value} onChange={() => update('sat_superscore', value)} />{t(text)}</label>)}
        </div>
        {errors.sat_superscore && <small className="onboarding-field-error">{errorText(errors.sat_superscore)}</small>}
      </fieldset>}
      {superscore && form.sat_superscore === true && <div className="onboarding-grid">
        <Question name="sat_superscore_reading" label={t('Highest Reading and Writing score (any test day)')} error={errors.sat_superscore_reading}><SatScoreInput value={form.sat_superscore_reading} onChange={(value) => update('sat_superscore_reading', value)} /></Question>
        <Question name="sat_superscore_math" label={t('Highest Math score (any test day)')} error={errors.sat_superscore_math}><SatScoreInput value={form.sat_superscore_math} onChange={(value) => update('sat_superscore_math', value)} /></Question>
        <div className="test-score-total" aria-live="polite"><span>{t('Superscore')}</span><b>{superTotal != null ? formatNumberLocale(superTotal, { useGrouping: false }) : '—'}</b><small>{t('out of 1600')}</small></div>
      </div>}
    </>}
  </section>;
}

export function SubjectScoresFields({ form, update, errors = {} }) {
  const rows = form.subjects || [];
  const change = (i, patch) => update('subjects', rows.map((row, n) => (n === i ? { ...row, ...patch } : row)));
  const setType = (i, type) => {
    const score = Number(rows[i].score) > SUBJECT_SCORE_MAX[type] ? '' : rows[i].score;
    change(i, { type, score });
  };
  return <section className="test-score-block" aria-labelledby="ts-subjects-title">
    <h3 id="ts-subjects-title">AP / IB <small>({t('optional')})</small></h3>
    <p className="test-score-intro">{t('Add one row for each AP or IB exam you have a score for. AP scores go from 1 to 5, IB scores from 1 to 7.')}</p>
    {errors.subjects && <p className="onboarding-field-error" role="alert">{errorText(errors.subjects)}</p>}
    <div className="onboarding-rows">
      {rows.map((row, i) => <fieldset key={i} className="test-score-row">
        <legend>{tx`Exam ${i + 1}`}</legend>
        <div className="onboarding-grid">
          <Question name={`subjects.${i}.type`} label={t('Exam type')} error={errors[`subjects.${i}.type`]}>
            <select value={row.type || ''} onChange={(e) => setType(i, e.target.value)}><option value="AP">AP</option><option value="IB">IB</option></select>
          </Question>
          <Question name={`subjects.${i}.subject`} label={t('Subject name')} error={errors[`subjects.${i}.subject`]}>
            <input value={row.subject || ''} maxLength={160} placeholder={t('For example, Biology')} onChange={(e) => change(i, { subject: e.target.value })} />
          </Question>
          <Question name={`subjects.${i}.score`} label={row.type === 'IB' ? t('Score (1–7)') : t('Score (1–5)')} error={errors[`subjects.${i}.score`]}>
            <select value={row.score ?? ''} onChange={(e) => change(i, { score: e.target.value })}>
              <option value="">{t('Select')}</option>
              {Array.from({ length: SUBJECT_SCORE_MAX[row.type] || 5 }, (_, n) => n + 1).map((score) => <option key={score} value={String(score)}>{score}</option>)}
            </select>
          </Question>
        </div>
        <button className="button quiet" type="button" onClick={() => update('subjects', rows.filter((_, n) => n !== i))}>{tx`Remove exam ${i + 1}`}</button>
      </fieldset>)}
      <button type="button" className="button secondary" onClick={() => update('subjects', [...rows, { type: 'AP', subject: '', score: '' }])} disabled={rows.length >= 50}>+ {t('Add an exam')}</button>
    </div>
  </section>;
}

export function TestScoresFields(props) {
  return <div className="onboarding-tests"><IeltsFields {...props} /><SatFields {...props} /><SubjectScoresFields {...props} /></div>;
}

// Read-only summary for the student, counselors and school staff.
const band = (value) => (value == null || value === '' ? null : formatNumberLocale(Number(value), { minimumFractionDigits: 1 }));
const STATUS_SUMMARY = { not_taken: 'Not taken yet', planning: 'Planning to take', scheduled: 'Test date booked', not_required: 'Not required' };

function statusLine(status, date) {
  const text = t(STATUS_SUMMARY[status] || 'Not taken yet');
  return date ? `${text} · ${dateText(date)}` : text;
}

export function TestScoreSummary({ student }) {
  if (!student) return null;
  const ieltsTaken = student.ielts_score != null;
  const satTaken = student.sat_score != null;
  const hasIeltsSections = IELTS_SECTIONS.every(([key]) => student[key] != null);
  const subjects = student.application_profile?.subjects || [];
  return <div className="test-score-summary">
    <article>
      <header><span>IELTS</span><b>{ieltsTaken ? band(student.ielts_score) : '—'}</b></header>
      {ieltsTaken ? <>
        {hasIeltsSections && <dl className="test-score-parts">{IELTS_SECTIONS.map(([key, label]) => <div key={key}><dt>{t(label)}</dt><dd>{band(student[key])}</dd></div>)}</dl>}
        <p>{[student.ielts_test_date && dateText(student.ielts_test_date), student.ielts_attempts && tx`Attempts: ${student.ielts_attempts}`].filter(Boolean).join(' · ') || t('Overall band only')}</p>
      </> : <p>{statusLine(student.ielts_status, student.ielts_test_date)}</p>}
    </article>
    <article>
      <header><span>SAT</span><b>{satTaken ? formatNumberLocale(student.sat_score, { useGrouping: false }) : '—'}</b></header>
      {satTaken ? <>
        {student.sat_reading != null && <dl className="test-score-parts"><div><dt>{t('Reading and Writing')}</dt><dd>{student.sat_reading}</dd></div><div><dt>{t('Math')}</dt><dd>{student.sat_math}</dd></div></dl>}
        <p>{[student.sat_test_date && dateText(student.sat_test_date), student.sat_attempts && tx`Attempts: ${student.sat_attempts}`].filter(Boolean).join(' · ') || t('Total only')}</p>
        {student.sat_superscore === true && <p className="test-score-note">{tx`Sends a superscore: Reading and Writing ${student.sat_superscore_reading}, Math ${student.sat_superscore_math}`}</p>}
        {student.sat_superscore === false && <p className="test-score-note">{t('Sends scores from one test day')}</p>}
      </> : <p>{statusLine(student.sat_status, student.sat_test_date)}</p>}
    </article>
    {subjects.length > 0 && <article>
      <header><span>AP / IB</span><b>{formatNumberLocale(subjects.length)}</b></header>
      <dl className="test-score-parts">{subjects.map((row, i) => <div key={i}><dt>{row.type} · {row.subject}</dt><dd>{row.score}</dd></div>)}</dl>
    </article>}
  </div>;
}
