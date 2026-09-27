import { useState } from 'react';
import { api } from '../api';
import { t } from '../i18n';
import { Modal } from './ui';
import { fullName, label } from '../lib/labels';
import { Fingerprint, ShieldAlert, ClipboardCheck } from 'lucide-react';
import { dateTimeText } from '../lib/format';

export function TemporaryCredentialModal({ account, onClose, notify }) {
  const [result, setResult] = useState(null);
  const [saving, setSaving] = useState(false);

  async function issue() {
    setSaving(true);
    try {
      setResult(await api.issueTemporaryCredential(account.id));
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function copyPassword() {
    if (!result?.temporary_password) return;
    try {
      await navigator.clipboard.writeText(result.temporary_password);
      notify(t('Copied'));
    } catch {
      notify(t('Copy password'), 'error');
    }
  }

  return <Modal title={`${t('Reset login')} · ${fullName(account)}`} onClose={onClose}>
    <div className="credential-modal">
      <div className="credential-account"><Fingerprint size={21} /><div><b>{account.username}</b><small>{account.email || label(account.role)}</small></div></div>
      {!result ? <>
        <p>{t('This revokes existing sessions and any previous temporary password.')}</p>
        <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t('Cancel')}</button><button type="button" className="button primary" onClick={issue} disabled={saving} aria-busy={saving}><Fingerprint size={16} />{t('Generate temporary password')}</button></div>
      </> : <>
        <p className="credential-delivery"><ShieldAlert size={17} />{t('The password is shown once. Send it through an approved secure channel.')}</p>
        <div className="credential-secret"><span>{t('Generated password')}</span><code>{result.temporary_password}</code><button type="button" className="button quiet" onClick={copyPassword}><ClipboardCheck size={16} />{t('Copy password')}</button></div>
        <small>{t('expires')}: {dateTimeText(result.credential?.expires_at)}</small>
        <div className="form-actions"><button type="button" className="button primary" onClick={onClose}>{t('Close')}</button></div>
      </>}
    </div>
  </Modal>;
}
