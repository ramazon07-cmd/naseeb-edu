// The college match: the student's scores and a balanced list of best-fitting universities, grouped by
// admission band (backend college_search.college_match). Rules only: the list makes no AI call. The one
// optional AI call is the "Why these fit you" button (one line per card, cached by the server).
import { useState } from 'react';
import { ArrowRight, Check, CheckCircle2, Clock3, Compass, GraduationCap, Plus, RefreshCw, Sparkles, X } from 'lucide-react';
import { api } from '../api';
import { formatNumberLocale, getLanguage, t, tx } from '../i18n';
import { TierBand } from './college';
import { bandLabel, priceInfo, rankText } from '../lib/college';
import { money } from '../lib/format';
import { fitReasonText } from '../lib/fitReasons';
import { BlueButton, GlassCard } from '../design/blue/ui';
import '../design/pages/college-match-blue.css';

const SCORES = [['academics', 'Academics'], ['activities', 'Activities'], ['essays', 'Essays']];
const FACTOR_TITLES = Object.fromEntries(SCORES);

// Where the student's academics stand against the students this university admits.
function academicStanding(position) {
  if (position == null) return null;
  return position >= 0.5 ? 'Above most admitted students' : position >= -0.25 ? 'In the admitted range' : 'Below the admitted range';
}

function Scores({ rubric, onOpenEssayLab }) {
  return <div className="nb-match-scores-block">
    <ul className="nb-match-score-tiles">{SCORES.map(([key, title]) => <li key={key} className={rubric[key] == null ? 'is-pending' : ''}>
      <small>{t(title)}</small>
      {rubric[key] == null ? <span>{t("Not checked yet")}</span> : <b>{formatNumberLocale(rubric[key], { maximumFractionDigits: 1 })}<small>/10</small></b>}
      <i aria-hidden="true" style={{ '--fill': `${(rubric[key] || 0) * 10}%` }} />
    </li>)}</ul>
    {rubric.essays == null && <p className="nb-match-hint">
      {t("Check your essay in Essay Lab to include it")}
      {onOpenEssayLab && <button type="button" className="link-button" onClick={onOpenEssayLab}>{t("Open Essay Lab")} <ArrowRight size={13} aria-hidden="true" /></button>}
    </p>}
  </div>;
}

function MatchCard({ university, application, busy, reason, essaysMissing, onAdd, onOpen }) {
  const fit = university.fit;
  const note = fit.reasons[0];
  const gap = fit.gaps[0];
  const price = priceInfo(university);
  const standing = academicStanding(fit.chance.academic_position);
  const admitRate = fit.chance.admit_rate;
  return <article className="nb-match-card">
    <header>
      <button type="button" className="nb-match-card-name" onClick={onOpen}>{university.name}</button>
      <small>{[university.country, rankText(university) !== '—' && tx`QS ${rankText(university)}`].filter(Boolean).join(' · ')}</small>
    </header>
    <dl className="nb-match-card-facts">
      <div><dt>{t("Fit")}</dt><dd>{formatNumberLocale(fit.match_score)}<small>/100</small></dd></div>
      {admitRate != null && <div><dt>{t("Admit rate")}</dt><dd>{formatNumberLocale(admitRate, { maximumFractionDigits: 1 })}<small>%</small></dd></div>}
      <div><dt>{t("Cost per year")}</dt><dd>{money(price.amount)}</dd></div>
    </dl>
    <div className="nb-match-factors" aria-label={t("What counts here")}>
      {standing && <span className="nb-match-factor"><GraduationCap size={13} aria-hidden="true" />{t(standing)}</span>}
      {university.factors.map((factor) => <span key={factor.key} className="nb-match-factor">{t(FACTOR_TITLES[factor.key])} {formatNumberLocale(factor.score, { maximumFractionDigits: 1 })}<small>{formatNumberLocale(factor.share)}%</small></span>)}
      {essaysMissing && <span className="nb-match-factor is-missing">{t("Essays not checked")}</span>}
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
function useReasons() {
  const [state, setState] = useState({ status: 'idle', lines: {}, error: '' });
  async function ask() {
    setState((current) => ({ ...current, status: 'loading', error: '' }));
    try {
      const answer = await api.collegeMatchReasons(getLanguage());
      setState({ status: 'done', lines: answer.reasons, error: '' });
    } catch (error) {
      setState((current) => ({ ...current, status: 'error', error: error.message }));
    }
  }
  return [state, ask];
}

export function CollegeMatchPanel({ state, listed, busyId, addingAll, onAdd, onAddAll, onOpen, onOpenEssayLab, onRetry, onClose }) {
  const [reasons, askReasons] = useReasons();
  if (state.loading) return <div className="college-research-state match-loading" role="status"><RefreshCw className="spin" size={22} aria-hidden="true" /><div><b>{t("Finding your best-fit colleges…")}</b><p>{t("Matching your profile against every university.")}</p></div></div>;
  if (state.error) return <div className="college-research-state error" role="alert"><X size={22} aria-hidden="true" /><div><b>{t("Your college match could not be built")}</b><p>{state.error}</p></div><button type="button" className="button quiet small" onClick={onRetry}>{t("Retry")}</button></div>;
  const { data } = state;
  if (!data) return null;
  const all = data.groups.flatMap((group) => group.results);
  const toAdd = all.filter((university) => !listed.has(university.id));
  const essaysMissing = data.rubric.essays == null;
  const asking = reasons.status === 'loading';
  return <GlassCard as="section" className="nb-match-panel" aria-label={t("Your best-fit colleges")}
    title={t("Your best-fit colleges")} icon={Compass}
    action={<div className="nb-match-actions">
      {all.length > 0 && reasons.status !== 'done' && <BlueButton variant="ghost" size="sm" icon={asking ? RefreshCw : Sparkles} disabled={asking} aria-busy={asking} onClick={askReasons}>{asking ? t("Naseeb AI is writing…") : t("Why these fit you")}</BlueButton>}
      {toAdd.length > 0 && <BlueButton size="sm" icon={Plus} disabled={addingAll} aria-busy={addingAll} onClick={() => onAddAll(toAdd)}>{tx`Add all ${formatNumberLocale(toAdd.length)} to my list`}</BlueButton>}
      <button type="button" className="nb-match-close" aria-label={t("Close")} onClick={onClose}><X size={16} aria-hidden="true" /></button>
    </div>}>
    <Scores rubric={data.rubric} onOpenEssayLab={onOpenEssayLab} />
    {reasons.status === 'error' && <p className="nb-match-error" role="alert">{reasons.error}</p>}
    {data.groups.map((group) => <div className="nb-match-group" key={group.band}>
      <h3><TierBand value={group.band} /><small>{formatNumberLocale(group.results.length)}</small></h3>
      {group.results.length ? <div className="nb-match-cards">{group.results.map((university) => <MatchCard key={university.id} university={university} application={listed.get(university.id)} busy={busyId === university.id} reason={reasons.lines[university.id]} essaysMissing={essaysMissing} onAdd={() => onAdd(university)} onOpen={() => onOpen(university.id)} />)}</div>
        : <p className="nb-match-empty">{tx`No ${bandLabel(group.band)} universities match your profile yet.`}</p>}
    </div>)}
    <p className="nb-match-foot">{t("Matched with fixed rules: the same profile always gets the same list. Bands are estimates, not admission decisions.")}</p>
  </GlassCard>;
}
