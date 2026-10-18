import { useMemo, useState } from 'react';
import { ChevronRight, Search } from 'lucide-react';
import { t, tp, tx } from '../i18n';
import { CxAvatar, CxHead, CxPills, CxTag, useCounselorUi } from '../components/counselorUi';
import { counselorPageDescription } from '../components/CounselorShell';
import { LoadMore, PagedListError, firstPageLoading } from '../components/paged';
import { useRecordList } from '../hooks/useRecordList';
import { ESSAY_STATUS_TONE } from '../lib/essayReview';
import { groupByStudent } from '../lib/essayGroups';
import { dayMonthText, joinParts } from '../lib/format';
import { label } from '../lib/labels';
import './counselor-groups.css';

const AWAITING_REVIEW = { status: 'reviewing' };

function EssayRow({ item, onOpen }) {
  return <button type="button" className="cx-row" onClick={() => onOpen(item.id)}>
    <span className="cx-row-copy"><b>{item.title}</b><small>{joinParts(item.university_name || t("General essay"), tx`Version ${item.version}`)}</small></span>
    <CxTag tone={ESSAY_STATUS_TONE[item.status] || 'quiet'}>{label(item.status)}</CxTag>
    <span className="cg-date">{dayMonthText(item.updated_at)}</span>
    <ChevronRight className="cx-row-go" size={16} aria-hidden="true" />
  </button>;
}

// The counselor's Essays, grouped by student. The sidebar badge counts shared essays in
// `reviewing` (counselor_summary.py), so the page opens on exactly those. An essay opens
// on its own page (CounselorEssayReview) where it is read, commented on and decided.
export function CounselorEssaysPage({ user, data, onOpen }) {
  const { stats } = useCounselorUi();
  const [filter, setFilter] = useState('reviewing');
  const [search, setSearch] = useState('');
  const awaiting = filter === 'reviewing';
  const list = useRecordList({ user, data, endpoint: 'essays', query: search, filters: awaiting ? AWAITING_REVIEW : undefined, ordering: '-updated' });
  const groups = useMemo(() => groupByStudent(list.items), [list.items]);
  const emptyText = search.trim() ? 'No essays match your search.' : awaiting ? 'No essays are waiting for your review.' : 'No shared essays yet. Students choose which essays to share.';
  return <div className="section-stack">
    <CxHead title={t("Essays")} subtitle={t(counselorPageDescription('essays') || 'Essay drafts and revision history')} />
    <div className="cx-list-bar">
      <CxPills label={t('Filter essays')} active={filter} onChange={setFilter} items={[['reviewing', 'Awaiting review', stats?.review?.essays], ['all', 'All']]} />
      <label className="cx-search">
        <Search size={16} aria-hidden="true" />
        <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('Search essays…')} aria-label={t('Search essays…')} autoComplete="off" />
      </label>
    </div>
    <div className="cg-groups">
      {groups.map((group) => <section key={group.student} className="cg-group" aria-label={group.name}>
        <header className="cg-head">
          <CxAvatar name={group.name} />
          <b>{group.name}</b>
          <small>{tp('{n} essay|{n} essays', group.essays.length, { n: group.essays.length })}</small>
        </header>
        {group.essays.map((item) => <EssayRow key={item.id} item={item} onOpen={onOpen} />)}
      </section>)}
      {firstPageLoading(list) && <p className="paged-list-loading" role="status">{t("Loading…")}</p>}
      {list.loaded && !groups.length && <p className="cx-empty">{t(emptyText)}</p>}
    </div>
    <PagedListError list={list} />
    <LoadMore list={list} />
  </div>;
}
