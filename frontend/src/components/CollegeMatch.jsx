// The college match: ten universities for the student's major (3 reach, 4 target, 3 safety), chosen by QS subject
// rank, aid for international students and the student's SAT (backend college_match.py). Rules only: the list
// makes no AI call. The one optional AI call is the "Why these fit you" button (one line per card, cached by the server).
import { useState } from 'react';
import { ArrowRight, Check, CheckCircle2, Clock3, Compass, GraduationCap, Plus, RefreshCw, Sparkles, X } from 'lucide-react';
import { api } from '../api';
import { formatNumberLocale, getLanguage, t, tx } from '../i18n';
import { TierBand } from './college';
import { bandLabel, rankText } from '../lib/college';
import { academicStanding, addAllBusy, beginReasons, costText, failReasons, finishReasons, idleReasons, individualAddBusy, matchFootnote, matchMessage, reasonsKey, reasonsView, satPositionText, subjectRankText } from '../lib/collegeMatch';
import { money } from '../lib/format';
import { fitReasonText } from '../lib/fitReasons';
import { BlueButton, GlassCard } from '../design/blue/ui';
import '../design/pages/college-match-blue.css';

const ACADEMICS = 'academics';
const AID_STATUS_LABELS = {
  yes: "Yes",
  need_aware: "Need-aware",
  merit: "Merit aid (check it is open to international students)",
  none: "None listed",
  unknown: "Unknown",
};

function Scores({ rubric }) {
  const score = rubric[ACADEMICS];
  return <div className="nb-match-scores-block">
    <ul className="nb-match-score-tiles">
      <li className={score == null ? 'is-pending' : ''}>
        <small>{t("Academics")}</small>
        {score == null ? <span>{t("Not checked yet")}</span> : <b>{formatNumberLocale(score, { maximumFractionDigits: 1 })}<small>/10</small></b>}
        <i aria-hidden="true" style={{ '--fill': `${(score || 0) * 10}%` }} />
      </li>
    </ul>
  </div>;
}

function MatchCard({ university, application, busy, reason, onAdd, onOpen }) {
  const fit = university.fit;
  const note = fit.reasons[0];
  const gap = fit.gaps[0];
  const standing = academicStanding(fit.chance.academic_position);
  const admitRate = fit.chance.admit_rate;
  const estimated = Boolean(fit.chance.admit_rate_estimated);
  const rank = subjectRankText(university.subject);
  const overall = rankText(university);
  return <article className="nb-match-card">
    <header>
      <span className="nb-match-card-top"><button type="button" className="nb-match-card-name" onClick={onOpen}>{university.name}</button><TierBand value={university.band} /></span>
      <small>{[university.country, overall !== '—' && !university.subject?.overall && tx`QS ${overall}`].filter(Boolean).join(' · ')}</small>
    </header>
    {rank && <p className="nb-match-subject">{rank}</p>}
    <dl className="nb-match-card-facts">
      {admitRate != null && <div><dt>{t("Admit rate")}</dt><dd title={estimated ? t("estimated from the overall rate") : undefined}>{estimated && '≈'}{formatNumberLocale(admitRate, { maximumFractionDigits: 1 })}<small>%</small>{estimated && <small className="nb-match-estimate">{t("estimated from the overall rate")}</small>}</dd></div>}
      <div><dt>{t("Cost per year")}</dt><dd>{money(university.cost_usd)}</dd></div>
      <div><dt>{t("Aid for international students")}</dt><dd>{t(AID_STATUS_LABELS[university.aid_status])}</dd></div>
    </dl>
    <div className="nb-match-factors" aria-label={t("What counts here")}>
      <span className="nb-match-factor"><GraduationCap size={13} aria-hidden="true" />{satPositionText(university.sat)}</span>
      <span className={`nb-match-factor${university.cost_vs_budget === 'over' ? ' is-over' : ''}`}>{costText(university)}</span>
      {standing && <span className="nb-match-factor">{t(standing)}</span>}
    </div>
    {reason && <p className="nb-match-why"><Sparkles size={14} aria-hidden="true" /><span>{reason}</span></p>}
    {note && <p className="nb-match-note ok"><CheckCircle2 size={14} aria-hidden="true" /><span>{fitReasonText(note)}</span></p>}
    {gap && <p className="nb-match-note gap"><Clock3 size={14} aria-hidden="true" /><span>{fitReasonText(gap)}</span></p>}
    {university.suggested_programs.length > 0 && <p className="nb-match-programs"><b>{t("Programs for your major")}</b>{university.suggested_programs.map((program) => program.name).join(' · ')}</p>}
    <footer>
      {application ? <span className="nb-match-added"><Check size={14} aria-hidden="true" /> {t("Added")}</span>
        : <BlueButton variant="ghost" size="sm" icon={Plus} disabled={busy} aria-busy={busy} onClick={onAdd}>{t("Add")}</BlueButton>}
      <button type="button" className="link-button" onClick={onOpen}>{t("Open university")} <ArrowRight size={13} aria-hidden="true" /></button>
    </footer>
  </article>;
}

// The optional "Why these fit you" lines: idle until asked; the one place the match can reach an AI.
// The state is keyed by match generation + language: a new list, a reopened panel or another language starts idle,
// and an answer to an earlier ask is ignored.
function useReasons(generation) {
  const language = getLanguage();
  const key = reasonsKey(generation, language);
  const [state, setState] = useState(() => idleReasons(key));
  async function ask() {
    setState((current) => beginReasons(current, key));
    try {
      const answer = await api.collegeMatchReasons(language);
      setState((current) => finishReasons(current, key, answer.reasons));
    } catch (error) {
      setState((current) => failReasons(current, key, error.message));
    }
  }
  return [reasonsView(state, key), ask];
}

export function CollegeMatchPanel({ state, listed, busyId, addingAll, onAdd, onAddAll, onOpen, onRetry, onClose }) {
  const [reasons, askReasons] = useReasons(state.generation);
  if (state.loading) return <div className="college-research-state match-loading" role="status"><RefreshCw className="spin" size={22} aria-hidden="true" /><div><b>{t("Finding your best-fit colleges…")}</b><p>{t("Matching your profile against every university.")}</p></div></div>;
  if (state.error) return <div className="college-research-state error" role="alert"><X size={22} aria-hidden="true" /><div><b>{t("Your college match could not be built")}</b><p>{state.error}</p></div><button type="button" className="button quiet small" onClick={onRetry}>{t("Retry")}</button></div>;
  const { data } = state;
  if (!data) return null;
  const all = data.groups.flatMap((group) => group.results);
  const toAdd = all.filter((university) => !listed.has(university.id));
  const messages = [...(data.hints || []), ...(data.notes || [])];
  const subjects = (data.subjects || []).map((subject) => subject.name).join(', ');
  const asking = reasons.status === 'loading';
  return <GlassCard as="section" className="nb-match-panel" aria-label={t("Your best-fit colleges")}
    title={t("Your best-fit colleges")} icon={Compass}
    action={<div className="nb-match-actions">
      {all.length > 0 && reasons.status !== 'done' && <BlueButton variant="ghost" size="sm" icon={asking ? RefreshCw : Sparkles} disabled={asking} aria-busy={asking} onClick={askReasons}>{asking ? t("Naseeb AI is writing…") : t("Why these fit you")}</BlueButton>}
      {toAdd.length > 0 && <BlueButton size="sm" icon={Plus} disabled={addAllBusy({ busyId, addingAll })} aria-busy={addingAll} onClick={() => onAddAll(toAdd)}>{tx`Add all ${formatNumberLocale(toAdd.length)} to my list`}</BlueButton>}
      <button type="button" className="nb-match-close" aria-label={t("Close")} onClick={onClose}><X size={16} aria-hidden="true" /></button>
    </div>}>
    <Scores rubric={data.rubric} />
    {subjects && <p className="nb-match-hint">{tx`Ranked by QS 2026 for: ${subjects}`}</p>}
    {messages.map((entry, index) => <p className="nb-match-hint" key={`${entry.code}-${index}`} role="note">{matchMessage(entry)}</p>)}
    {reasons.status === 'error' && <p className="nb-match-error" role="alert">{reasons.error}</p>}
    {data.groups.map((group) => <div className="nb-match-group" key={group.band}>
      <h3><TierBand value={group.band} /><small>{formatNumberLocale(group.results.length)}</small></h3>
      {group.results.length ? <div className="nb-match-cards">{group.results.map((university) => <MatchCard key={university.id} university={university} application={listed.get(university.id)} busy={individualAddBusy({ busyId, addingAll }, university.id)} reason={reasons.lines[university.id]} onAdd={() => onAdd(university)} onOpen={() => onOpen(university.id)} />)}</div>
        : <p className="nb-match-empty">{tx`No ${bandLabel(group.band)} universities match your profile yet.`}</p>}
    </div>)}
    <p className="nb-match-foot">{matchFootnote(data, reasons.status === 'done')}</p>
  </GlassCard>;
}
