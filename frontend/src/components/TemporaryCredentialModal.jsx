import { useState } from 'react';
import { api } from '../api';
import { t } from '../i18n';
import { Modal } from './ui';
import { Field } from './forms';
import { fullName, label } from '../lib/labels';
import { Fingerprint, ShieldAlert, ClipboardCheck, UserPlus } from 'lucide-react';
import { dateTimeText } from '../lib/format';
import { LOGIN_PATH } from '../lib/routes';

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

  return <Modal title={`${t('Reset login')} · ${fullName(account)}`} onClose={onClose}>
    <div className="credential-modal">
      <div className="credential-account"><Fingerprint size={21} /><div><b>{account.username}</b><small>{account.email || label(account.role)}</small></div></div>
      {!result ? <>
        <p>{t('This revokes existing sessions and any previous temporary password.')}</p>
        <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t('Cancel')}</button><button type="button" className="button primary" onClick={issue} disabled={saving} aria-busy={saving}><Fingerprint size={16} />{t('Generate temporary password')}</button></div>
      </> : <>
        <OneTimePassword password={result.temporary_password} expiresAt={result.credential?.expires_at} notify={notify} />
        <div className="form-actions"><button type="button" className="button primary" onClick={onClose}>{t('Close')}</button></div>
      </>}
    </div>
  </Modal>;
}

// A server-generated password, shown once with a copy button.
export function OneTimePassword({ password, expiresAt, notify }) {
  async function copyPassword() {
    if (!password) return;
    try {
      await navigator.clipboard.writeText(password);
      notify(t('Copied'));
    } catch {
      notify(t('Copy password'), 'error');
    }
  }
  return <>
    <p className="credential-delivery"><ShieldAlert size={17} />{t('The password is shown once. Send it through an approved secure channel.')}</p>
    <div className="credential-secret"><span>{t('Generated password')}</span><code>{password}</code><button type="button" className="button quiet" onClick={copyPassword}><ClipboardCheck size={16} />{t('Copy password')}</button></div>
    {expiresAt && <small>{t('expires')}: {dateTimeText(expiresAt)}</small>}
  </>;
}

// A student account staff just created: the login shown once and copied as one
// message the counselor sends to the student.
export function StudentLoginCard({ name, username, password, expiresAt, notify, onAnother, onDone }) {
  // Clipboard refused (permissions, embedded browsers): the message to copy by hand.
  const [manual, setManual] = useState(false);
  const message = [
    t('Your Naseeb Edu account'),
    `${t('Sign-in page')}: ${window.location.origin}${LOGIN_PATH}`,
    `${t('Username')}: ${username}`,
    `${t('Password')}: ${password}`,
    t('At the first sign-in you will choose your own password.'),
  ].join('\n');
  async function copy() {
    try {
      await navigator.clipboard.writeText(message);
      notify(t('Copied'));
    } catch {
      setManual(true);
      notify(t('Select the text and copy it'), 'error');
    }
  }
  return <div className="credential-modal" role="status">
    <div className="credential-account"><Fingerprint size={21} aria-hidden="true" /><div><b>{t('Login created for {name}', { name })}</b><small>{expiresAt ? t('The student signs in with this temporary password and must change it. It expires on {date}.', { date: dateTimeText(expiresAt) }) : t('The student signs in with this temporary password and must change it.')}</small></div></div>
    <div className="credential-secret"><span>{t('Username')}</span><code>{username}</code><span>{t('Password')}</span><code>{password}</code></div>
    <p className="credential-delivery"><ShieldAlert size={17} aria-hidden="true" />{t('The password is shown only now. Copy it and give it to the student.')}</p>
    {manual && <Field label="Select the text and copy it"><textarea defaultValue={message} rows={5} spellCheck={false} autoFocus onFocus={(event) => event.target.select()} /></Field>}
    <div className="form-actions">
      <button type="button" className="button quiet" onClick={onAnother}><UserPlus size={16} aria-hidden="true" />{t('Create another account')}</button>
      {onDone && <button type="button" className="button quiet" onClick={onDone}>{t('Done')}</button>}
      <button type="button" className="button primary" onClick={copy}><ClipboardCheck size={16} aria-hidden="true" />{t('Copy login and password')}</button>
    </div>
  </div>;
}
