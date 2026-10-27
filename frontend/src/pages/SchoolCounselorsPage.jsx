import { useState } from 'react';
import { Pencil, Plus } from 'lucide-react';
import { Panel, Empty } from '../components/ui';
import { LoadMore, PagedListError, firstPageLoading } from '../components/paged';
import { usePagedList } from '../hooks/usePagedList';
import { fullName, initials } from '../lib/labels';
import { t } from '../i18n';
import { CounselorEditForm, CounselorProvisionForm } from './AdminPages';

export function SchoolCounselorsPage({ query, reload, notify }) {
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);
  const list = usePagedList('users/accounts', {
    search: query, filters: { role: 'counselor' }, ordering: 'name', pageSize: 50,
  });
  return <>
    <Panel className="school-counselors-panel" title={t('Counselors')} action={<button className="button primary" onClick={() => setCreating(true)}><Plus size={16} /> {t('Add counselor')}</button>}>
      <p className="counselor-roster-intro">{t('Add counselors to your school and manage their access.')}</p>
      <div className="counselor-roster" aria-busy={list.loading}>
        {list.items.map((account) => <article className="counselor-roster-row" key={account.id}>
          <span className="counselor-avatar" aria-hidden="true">{initials(fullName(account))}</span>
          <div className="counselor-roster-person">
            <h3>{fullName(account)}</h3>
            <p>{account.email || account.username}</p>
            {account.phone && <small>{account.phone}</small>}
          </div>
          <span className={`counselor-status ${account.is_active ? 'is-active' : 'is-inactive'}`}>{account.is_active ? t('Active') : t('Inactive')}</span>
          <button className="icon-button" onClick={() => setEditing(account)} title={t('Edit counselor')} aria-label={t('Edit counselor')}><Pencil size={16} /></button>
        </article>)}
        {firstPageLoading(list) && <p role="status">{t('Loading…')}</p>}
        {list.loaded && !list.items.length && <Empty text={t('No counselors found.')} />}
      </div>
      <PagedListError list={list} /><LoadMore list={list} />
    </Panel>
    {creating && <CounselorProvisionForm schoolManaged onClose={() => setCreating(false)} onSaved={() => { setCreating(false); list.reload(); reload(); }} notify={notify} />}
    {editing && <CounselorEditForm schoolManaged account={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} notify={notify} />}
  </>;
}
