import { Check, Columns3, Plus, X } from 'lucide-react';
import { formatNumberLocale, t, tx } from '../i18n';
import { Empty } from './ui';
import { useSubjectRankings } from '../hooks/useSubjectRankings';
import { INDICATOR_TITLES, SUBJECT_PAGE_SIZES, isTopRank, presetSubject, publishedRank, scoreText, subjectLimit, subjectRankingsQuery, weightText } from '../lib/subjectRankings';
import './subject-rankings.css';

// The subject picker: the 55 subjects under their 5 broad areas, each area also selectable as a whole.
function SubjectSelect({ areas, subject, onSubject }) {
  return <label className="college-subject-field"><span>{t('Study subject')}</span>
    <select aria-label={t('Study subject')} value={subject || ''} onChange={(event) => onSubject(event.target.value)}>
      {areas.map((area) => <optgroup key={area.code} label={area.name}>
        <option value={area.code}>{t('{area}: overall', { area: area.name })}</option>
        {area.subjects.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
      </optgroup>)}
    </select></label>;
}

function SubjectRow({ Logo, row, indicators, application, busy, compared, compareFull, onCompare, onAdd, onOpen }) {
  const top = isTopRank(row.rank, row.label);
  return <div className="uni-row subj-row" role="row">
    <div className={`uni-fit subj-rank${top ? ' is-top' : ''}`} role="cell"><b>{publishedRank(row.rank, row.label)}</b></div>
    <div className="uni-name" role="cell"><Logo university={row} /><span><button type="button" onClick={() => onOpen(row.id)}>{row.name}</button><small>{[row.city, row.country].filter(Boolean).join(', ')}</small></span></div>
    <div className="uni-facts">
      <div className="uni-value qs-score-primary" role="cell" data-label={t('Subject score')}><span className="v">{scoreText(row.score)}</span></div>
      {indicators.map((indicator, index) => <div className="uni-value" role="cell" data-label={t(INDICATOR_TITLES[indicator.key])} key={indicator.key}><span className="v">{scoreText(row.values[index])}</span></div>)}
    </div>
    <div className="uni-action" role="cell">
      <button type="button" className={`uni-compare${compared ? ' is-on' : ''}`} aria-pressed={compared} disabled={busy || (!compared && compareFull)} title={!compared && compareFull ? t('Compare up to 3 universities') : undefined} aria-label={tx`Compare ${row.name}`} onClick={() => onCompare(row)}>{compared ? <Check size={14} aria-hidden="true" /> : <Columns3 size={14} aria-hidden="true" />}</button>
      {application ? <span className="uni-added"><Check size={14} aria-hidden="true" /> {t('Added')}</span> : <button type="button" className="button quiet small" aria-label={t('Add to my list')} disabled={busy} aria-busy={busy} onClick={() => onAdd(row)}><Plus size={14} aria-hidden="true" /> {t('Add')}</button>}
    </div>
  </div>;
}

/**
 * The Subject rankings view of College Search, the QS ranking of one subject, 10, 25 or 50 universities at a
 * time. It is a separate chunk and fetches nothing until it is on screen: `pick` is the student's own
 * choice (null: their major's subject). The page hands in what it already holds (`Logo`, the subject `areas`),
 * so this chunk shares no module with the page chunk. The picker, the page size and "Show more" work like the QS rankings view; the
 * search text, country and QS filters come from the page's own toolbar.
 */
export function SubjectRankings({ Logo, areas, pick, onSubject, research, researchSettled, searchTerm, country, qsFilters, pageSize, onPageSize, chips, listed, compareMap, compareFull, busyId, onCompare, onAdd, onOpen }) {
  // Until the student picks one, the subject of their major; the request waits for the research answer that names it.
  const subject = pick ?? (researchSettled ? presetSubject(research, areas) : null);
  const limit = subjectLimit(pageSize);
  const query = subject ? subjectRankingsQuery({ subject, query: searchTerm, country, qsFilters, limit }) : null;
  const ranking = useSubjectRankings(query, subject);
  const { rows, indicators } = ranking;
  const remaining = Math.min(limit, ranking.count - rows.length);
  const year = ranking.year || 2026;
  return <>
    <section className="college-toolbar subj-toolbar" aria-label={t('Subject rankings')}>
      <div className="college-subject-row"><SubjectSelect areas={areas} subject={subject} onSubject={onSubject} /></div>
      <div className="uni-meta">
        <p className="filter-count" aria-live="polite"><b>{subject && !ranking.loading ? formatNumberLocale(ranking.count) : '…'}</b> {t('Universities')}</p>
        {chips}
        <div className="sort-control"><span>{t('Show')}</span><select aria-label={t('Universities per page')} value={limit} onChange={(event) => onPageSize(Number(event.target.value))}>{SUBJECT_PAGE_SIZES.map((size) => <option value={size} key={size}>{formatNumberLocale(size)}</option>)}</select></div>
      </div>
    </section>
    <div className={`uni-table qs-table subj-table ${ranking.loading && rows.length ? 'is-refreshing' : ''}`.trim()} role="table" aria-label={t('Subject rankings')} aria-busy={ranking.loading} style={{ '--subj-cols': indicators.length + 1 }}>
      <div className="uni-row uni-head subj-row" role="row"><span role="columnheader">{t('Rank')}</span><span role="columnheader">{t('University')}</span>
        <div className="uni-facts"><span role="columnheader">{t('Subject score')}</span>{indicators.map((indicator) => <span role="columnheader" key={indicator.key} title={t('Counts for {n} of the subject score', { n: weightText(indicator.weight) })}>{t(INDICATOR_TITLES[indicator.key])}<small>{weightText(indicator.weight)}</small></span>)}</div>
        <span role="columnheader" className="sr-only">{t('Add to my list')}</span></div>
      {rows.map((row) => <SubjectRow key={row.id} Logo={Logo} row={row} indicators={indicators} application={listed.get(row.id)} busy={busyId === row.id} compared={compareMap.has(row.id)} compareFull={compareMap.size >= 3} onCompare={onCompare} onAdd={onAdd} onOpen={onOpen} />)}
      {ranking.loading && !rows.length && <p className="uni-loading" role="status">{t('Loading universities…')}</p>}
      {!ranking.loading && !ranking.error && !rows.length && <Empty text={t('No universities match these filters.')} />}
    </div>
    {ranking.error && <div className="college-research-state error" role="alert"><X size={22} /><div><b>{t('Universities could not be loaded')}</b><p>{ranking.error}</p></div><button type="button" className="button quiet small" onClick={ranking.retry}>{t('Retry')}</button></div>}
    {ranking.nextOffset != null && remaining > 0 && <button type="button" className="button quiet uni-more" onClick={ranking.loadMore} disabled={ranking.loadingMore} aria-busy={ranking.loadingMore}>{ranking.loadingMore ? t('Loading…') : t('Show {n} more', { n: formatNumberLocale(remaining) })}</button>}
    <p className="uni-note">{t('Published QS scores out of 100.')} {t('Rankings: QS World University Rankings by Subject {year}.', { year: String(year) })}</p>
  </>;
}
