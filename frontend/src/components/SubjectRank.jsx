import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { formatNumberLocale, t } from '../i18n';
import { InfoCard } from './college';
import { isTopSubjectRank, strongestSubjects, subjectName, subjectRankText } from '../lib/subjects';

// "#3 Computer Science": the rank of a university in one QS subject; gold in the world top 10.
// A range stays a range ("201-250"). `rank` is a College Search row's `subject_rank`, or nothing when unranked.
export function SubjectRankChip({ rank }) {
  if (!rank) return null;
  const name = subjectName(rank.code);
  const text = subjectRankText(rank.rank, rank.label);
  // The short head of the name ("Computer Science" for "Computer Science & Information Systems") fits the
  // chip without cutting off; the full name stays in the tooltip.
  const short = name.split(/ & | \/ | and /)[0];
  return <span className={`nb-subj-chip${isTopSubjectRank(rank.rank, rank.label) ? ' is-top' : ''}`} title={`${name}, QS ${rank.year}`}><b>{text}</b><span>{short}</span></span>;
}

function SubjectLine({ item }) {
  const top = isTopSubjectRank(item.rank, item.rank_label);
  const score = item.score == null ? null : Math.max(0, Math.min(100, Number(item.score)));
  return <li className={`nb-subj-line${item.mine ? ' is-mine' : ''}`}>
    <div className="nb-subj-main"><b>{item.name}</b>{item.mine && <span className="nb-subj-mine">{t('Your major')}</span>}
      {score != null && <span className="nb-subj-bar" role="img" aria-label={t('Score {n} of 100', { n: formatNumberLocale(score, { maximumFractionDigits: 1 }) })}><i style={{ '--fill': `${score}%` }} /></span>}</div>
    <span className={`nb-subj-rank${top ? ' is-top' : ''}`} aria-label={t('Rank {n}', { n: subjectRankText(item.rank, item.rank_label) })}>{subjectRankText(item.rank, item.rank_label)}</span>
  </li>;
}

// The university page's "Strongest subjects": the student's own major subject(s) pinned first, then the
// best five others; "Show all" opens every ranked subject grouped by broad area. It all comes from the
// university detail already loaded, so opening the list makes no request.
export function StrongestSubjects({ subjects }) {
  const [all, setAll] = useState(false);
  const items = subjects?.items || [];
  const { pinned, top, groups, total } = strongestSubjects(items);
  if (!total && !pinned.length) return null;
  const more = total > pinned.filter((item) => !item.is_area).length + top.length;
  return <InfoCard title="Strongest subjects" className="nb-subjects">
    <div className="nb-subj-grid">
      <div className="nb-subj-list">
        <p className="nb-subj-meta">{t('QS {year} · ranked in {n} subjects', { year: String(subjects.year), n: formatNumberLocale(total) })}</p>
        {!all && <ul>{[...pinned, ...top].map((item) => <SubjectLine key={item.code} item={item} />)}</ul>}
        {all && groups.map((group) => <section key={group.code} className="nb-subj-group" aria-label={group.name}>
          <h4><span>{group.name}</span>{group.rank && <span className={`nb-subj-rank${isTopSubjectRank(group.rank.rank, group.rank.rank_label) ? ' is-top' : ''}`}>{subjectRankText(group.rank.rank, group.rank.rank_label)}</span>}</h4>
          <ul>{group.items.map((item) => <SubjectLine key={item.code} item={item} />)}</ul>
        </section>)}
        {(more || all) && <button type="button" className="button quiet small" aria-expanded={all} onClick={() => setAll(!all)}>{all ? <><ChevronUp size={14} aria-hidden="true" /> {t('Show fewer')}</> : <><ChevronDown size={14} aria-hidden="true" /> {t('Show all {n} subjects', { n: formatNumberLocale(total) })}</>}</button>}
      </div>
      <aside className="nb-subj-note" aria-label={t('How to read this')}>
        <h4>{t('How to read this')}</h4>
        <p>{t('The rank compares universities worldwide in one subject. It is built from academic and employer reputation and research citations, not teaching quality or student life.')}</p>
        <p>{t('Gold = top 10 in the world for that subject.')}</p>
        <small>{t('Source: QS World University Rankings by Subject {year}', { year: String(subjects.year) })}</small>
      </aside>
    </div>
  </InfoCard>;
}

