import { useState } from 'react';
import { t } from '../i18n';
import { CxPills, useCounselorUi } from '../components/counselorUi';
import { ResourceSection } from './ResourceSection';

const AWAITING_REVIEW = { status: 'reviewing' };

// The counselor's Essays. The sidebar badge counts shared essays in `reviewing`
// (counselor_summary.py), so the page opens on exactly those.
export function CounselorEssaysPage(props) {
  const { stats } = useCounselorUi();
  const [filter, setFilter] = useState('reviewing');
  const awaiting = filter === 'reviewing';
  return <div className="section-stack">
    <CxPills label={t('Filter essays')} active={filter} onChange={setFilter} items={[['reviewing', 'Awaiting review', stats?.review?.essays], ['all', 'All']]} />
    <ResourceSection {...props} filters={awaiting ? AWAITING_REVIEW : undefined} emptyText={awaiting ? 'No essays are waiting for your review.' : undefined} />
  </div>;
}
