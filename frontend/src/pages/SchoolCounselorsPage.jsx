import { useState } from 'react';
import { Pencil } from 'lucide-react';
import { Panel, Badge, Empty } from '../components/ui';
import { LoadMore, PagedListError, firstPageLoading } from '../components/paged';
import { usePagedList } from '../hooks/usePagedList';
import { fullName, initials } from '../lib/labels';
import { joinParts } from '../lib/format';
import { t } from '../i18n';
import { CounselorEditForm } from './AdminPages';

export function SchoolCounselorsPage({ query, reload, notify }) {
  const [editing, setEditing] = useState(null);
  const list = usePagedList('users/accounts', {
    search: query, filters: { role: 'counselor' }, ordering: 'name', pageSize: 50,
  });
  return <>
    <Panel title={t('Counselors')}>
      <p className="form-note">{t('Edit names, phone numbers, positions and active status. Contact Naseeb admin to add a counselor.')}</p>
      <div className="record-list" aria-busy={list.loading}>
        {list.items.map((account) => <article className="record" key={account.id}>
          <span className="avatar">{initials(fullName(account))}</span>
          <div className="record-main">
            <h3>{fullName(account)}</h3>
            <p>{joinParts(account.position, account.phone)}</p>
            <Badge tone={account.is_active ? 'success' : 'danger'}>{account.is_active ? t('Active') : t('Inactive')}</Badge>
          </div>
          <button className="icon-button" onClick={() => setEditing(account)} title={t('Edit counselor')} aria-label={t('Edit counselor')}><Pencil size={16} /></button>
        </article>)}
        {firstPageLoading(list) && <p role="status">{t('Loading…')}</p>}
        {list.loaded && !list.items.length && <Empty text={t('No counselors found.')} />}
      </div>
      <PagedListError list={list} /><LoadMore list={list} />
    </Panel>
    {editing && <CounselorEditForm schoolManaged account={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} notify={notify} />}
  </>;
}
