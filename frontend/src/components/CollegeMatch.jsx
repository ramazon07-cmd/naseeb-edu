// The AI college match: the student's four rubric scores and a balanced list of
// best-fitting universities, grouped by admission band (backend college_search.college_match).
import { ArrowRight, Check, CheckCircle2, Clock3, Plus, RefreshCw, Sparkles, X } from 'lucide-react';
import { formatNumberLocale, t, tx } from '../i18n';
import { TierBand } from './college';
import { bandLabel, priceInfo, rankText } from '../lib/college';
import { money } from '../lib/format';
import { fitReasonText } from '../lib/fitReasons';
import './college-match.css';

const RUBRIC = [['academics', 'Academics'], ['activities', 'Activities'], ['essays', 'Essays'], ['recommendations', 'Recommendations']];

function RubricScores({ rubric, aiScoring }) {
  const unscored = !rubric.essays || !rubric.recommendations;
  return <div className="match-rubric">
    <div className="match-rubric-scores">{RUBRIC.map(([key, title]) => <div key={key} className="match-rubric-score">
      <small>{t(title)}</small>
      {rubric[key] == null ? <span className="match-rubric-pending">{t("Not scored yet")}</span> : <b>{formatNumberLocale(rubric[key])}<small>/10</small></b>}
      <i aria-hidden="true" style={{ '--fill': `${(rubric[key] || 0) * 10}%` }} />
    </div>)}</div>
    {unscored && <p className="match-rubric-note">{aiScoring
      ? t("Essays and recommendations are scored by AI once your personal statement and letters are in Naseeb Edu.")
      : t("Essays and recommendations will be scored by AI once AI is turned on. Until then they neither help nor hurt your match.")}</p>}
  </div>;
}

function MatchCard({ university, application, busy, onAdd, onOpen }) {
  const fit = university.fit;
  const reason = fit.reasons[0];
  const gap = fit.gaps[0];
  const price = priceInfo(university);
  return <article className="match-card">
    <header>
      <button type="button" className="match-card-name" onClick={onOpen}>{university.name}</button>
      <small>{[university.country, rankText(university) !== '—' && tx`QS ${rankText(university)}`].filter(Boolean).join(' · ')}</small>
    </header>
    <dl className="match-card-facts">
      <div><dt>{t("Fit")}</dt><dd>{formatNumberLocale(fit.match_score)}<small>/100</small></dd></div>
      <div><dt>{t("Cost per year")}</dt><dd>{money(price.amount)}</dd></div>
    </dl>
    {reason && <p className="match-card-note ok"><CheckCircle2 size={14} aria-hidden="true" /><span>{fitReasonText(reason)}</span></p>}
    {gap && <p className="match-card-note gap"><Clock3 size={14} aria-hidden="true" /><span>{fitReasonText(gap)}</span></p>}
    <footer>
      {application ? <span className="uni-added"><Check size={14} aria-hidden="true" /> {t("Added")}</span>
        : <button type="button" className="button quiet small" disabled={busy} aria-busy={busy} onClick={onAdd}><Plus size={14} aria-hidden="true" /> {t("Add")}</button>}
      <button type="button" className="link-button" onClick={onOpen}>{t("Open university")} <ArrowRight size={13} aria-hidden="true" /></button>
    </footer>
  </article>;
}

export function CollegeMatchPanel({ state, listed, busyId, addingAll, onAdd, onAddAll, onOpen, onRetry, onClose }) {
  if (state.loading) return <section className="college-research-state match-loading" role="status"><RefreshCw className="spin" size={22} aria-hidden="true" /><div><b>{t("Finding your best-fit colleges…")}</b><p>{t("Scoring your profile once and matching it against every university.")}</p></div></section>;
  if (state.error) return <section className="college-research-state error" role="alert"><X size={22} aria-hidden="true" /><div><b>{t("Your college match could not be built")}</b><p>{state.error}</p></div><button type="button" className="button quiet small" onClick={onRetry}>{t("Retry")}</button></section>;
  const { data } = state;
  if (!data) return null;
  const all = data.groups.flatMap((group) => group.results);
  const toAdd = all.filter((university) => !listed.has(university.id));
  return <section className="college-match" aria-label={t("Your best-fit colleges")}>
    <header className="college-match-header">
      <div><span className="catalog-eyebrow"><Sparkles size={14} aria-hidden="true" /> {t("AI college match")}</span><h2>{t("Your best-fit colleges")}</h2></div>
      <div className="college-match-actions">
        {toAdd.length > 0 && <button type="button" className="button primary small" disabled={addingAll} aria-busy={addingAll} onClick={() => onAddAll(toAdd)}><Plus size={14} aria-hidden="true" /> {tx`Add all ${formatNumberLocale(toAdd.length)} to my list`}</button>}
        <button type="button" className="icon-button" aria-label={t("Close")} onClick={onClose}><X size={16} /></button>
      </div>
    </header>
    <RubricScores rubric={data.rubric} aiScoring={data.ai_scoring} />
    {data.groups.map((group) => <div className="match-group" key={group.band}>
      <h3><TierBand value={group.band} /><small>{formatNumberLocale(group.results.length)}</small></h3>
      {group.results.length ? <div className="match-cards">{group.results.map((university) => <MatchCard key={university.id} university={university} application={listed.get(university.id)} busy={busyId === university.id} onAdd={() => onAdd(university)} onOpen={() => onOpen(university.id)} />)}</div>
        : <p className="match-empty">{tx`No ${bandLabel(group.band)} universities match your profile yet.`}</p>}
    </div>)}
    <p className="uni-note">{t("Matched with fixed rules: the same profile always gets the same list. Bands are estimates, not admission decisions.")}</p>
  </section>;
}
