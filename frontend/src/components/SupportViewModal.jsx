import { useState } from 'react';
import { api } from '../api';
import { t } from '../i18n';
import { Badge, Modal } from './ui';
import { Detail } from './records';
import { Field } from './forms';
import { fullName, label } from '../lib/labels';
import { dateTimeText } from '../lib/format';
import { LifeBuoy, ShieldAlert } from 'lucide-react';

// Audited, read-only account snapshot for support staff. The reason is stored
// in the audit log; nothing here signs in as the person.
export function SupportViewModal({ account, onClose, notify }) {
  const [reason, setReason] = useState('');
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(false);

  async function open(event) {
    event.preventDefault();
    setLoading(true);
    try {
      setSnapshot(await api.supportView(account.id, reason.trim()));
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  const person = snapshot?.account;
  const workspace = snapshot?.workspace;
  return <Modal title={`${t('Support view')} · ${fullName(account)}`} onClose={onClose}>
    {!snapshot ? <form className="form-grid" onSubmit={open}>
      <p className="form-note form-wide"><ShieldAlert size={16} /> {t('Opening a support view is recorded in the audit log with your reason. It shows account state only, never messages, essays or notes.')}</p>
      <Field label={t('Reason')}><textarea value={reason} onChange={(event) => setReason(event.target.value)} minLength="10" maxLength="500" rows="3" required /></Field>
      <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t('Cancel')}</button><button className="button primary" disabled={loading || reason.trim().length < 10} aria-busy={loading}><LifeBuoy size={16} /> {t('Open support view')}</button></div>
    </form> : <div className="section-stack support-view">
      <Badge tone="success">{t('Read only')}</Badge>
      <div className="detail-grid">
        <Detail label="Username" value={person.username} />
        <Detail label="Role" value={label(person.role)} />
        <Detail label="Status" value={person.is_active ? t('Active') : t('Inactive')} />
        <Detail label="School" value={person.school_name} />
        <Detail label="Login status" value={label(person.credential_status)} />
        <Detail label="Last sign-in" value={person.last_login ? dateTimeText(person.last_login) : ''} />
        {workspace && <Detail label="Plan" value={`${workspace.plan_name} · ${label(workspace.status)}`} />}
        {snapshot.student && <Detail label="Grade" value={snapshot.student.grade} />}
        {snapshot.student && <Detail label="Profile completed" value={snapshot.student.profile_completed ? t('Yes') : t('No')} />}
      </div>
      <div className="record-list">{snapshot.credential_events.map((item, index) => <article className="record" key={`${item.created_at}-${index}`}><div className="record-main"><h3>{label(item.event)}</h3><div className="record-meta"><span>{item.actor_name || t('System')}</span><span>{dateTimeText(item.created_at)}</span></div></div></article>)}</div>
      <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t('Close')}</button></div>
    </div>}
  </Modal>;
}
