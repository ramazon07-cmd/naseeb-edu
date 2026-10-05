import { ExternalLink } from 'lucide-react';
import { t } from '../i18n';
import { QS_CLASSIFICATIONS, QS_INDICATORS, qsClassification, qsScoreText } from '../lib/qs';
import './qs.css';

export function QsUniversityDetails({ university }) {
  const data = university.qs_data;
  if (!data?.year) return null;
  return <section className="qs-details" aria-label={t('QS rankings')}>
    <header className="qs-details-heading"><div><span className="eyebrow">QS WORLD UNIVERSITY RANKINGS {data.year}</span><h3>{t('Ranking indicators')}</h3><p>{t('Published QS scores out of 100.')}</p></div><div className="qs-overall"><span>{t('QS score')}</span><b>{qsScoreText(data.overall_score)}</b></div></header>
    <dl className="qs-classifications">
      {QS_CLASSIFICATIONS.map(([key, title]) => <div key={key}><dt>{t(title)}</dt><dd>{qsClassification(key, data[key])}{data[key] && ['size', 'focus', 'research'].includes(key) && <small> ({data[key]})</small>}</dd></div>)}
      <div><dt>{t('Previous rank')} · {data.year - 1}</dt><dd>{data.previous_rank || '—'}</dd></div>
    </dl>
    <div className="qs-indicator-grid">{QS_INDICATORS.map(([code, title]) => {
      const metric = data.indicators?.[code];
      return <div className="qs-indicator" key={code}><div><span>{t(title)}</span><b>{qsScoreText(metric?.score)}</b></div><div className="qs-indicator-track" aria-hidden="true"><i style={{ width: `${typeof metric?.score === 'number' ? Math.min(100, Math.max(0, metric.score)) : 0}%` }} /></div><small>{t('Rank')}: {metric?.rank || '—'} <span>{code}</span></small></div>;
    })}</div>
    <footer className="qs-source"><span>{t('QS indicator scores are not admission requirements.')}</span><a href="https://www.topuniversities.com/world-university-rankings" target="_blank" rel="noreferrer">{t('Source')}: QS <ExternalLink size={12} aria-hidden="true" /></a></footer>
  </section>;
}
