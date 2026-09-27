import { useState } from 'react'
import { Lock, UserCheck, Users } from 'lucide-react'
import { t } from '../i18n.js'
import { Dialog } from './ui.jsx'
import { essayLabApi } from './essayLabApi.js'
import { COUNSELOR_ACCESS, accessOf, isShared, setSharing, sharingFields } from './sharing.js'

// Share / unshare for the editor header and the library menu. Unsharing asks
// first, because the counselor loses access immediately.
export function useEssaySharing({ notify, onSaved }) {
  const [confirming, setConfirming] = useState(null)
  const [choosing, setChoosing] = useState(null)
  const [busyId, setBusyId] = useState(null)

  async function apply(essay, shared, access) {
    setBusyId(essay.id)
    try {
      onSaved(sharingFields(await setSharing(essayLabApi, essay, shared, access)))
      notify(!shared ? t('Your counselor can no longer see this essay.') : isShared(essay) ? t('Sharing updated.') : t('Shared with your counselor.'))
    } catch (err) {
      notify(err?.message || (shared ? t('Could not share the essay.') : t('Could not unshare the essay.')), 'error')
    } finally {
      setBusyId(null)
    }
  }

  // Sharing (or changing what the counselor may do) asks how first.
  const share = (essay) => setChoosing(essay)
  const unshare = (essay) => setConfirming(essay)
  const menuItem = (essay) => (isShared(essay)
    ? { label: t('Unshare'), icon: <Lock size={15} />, onSelect: () => unshare(essay) }
    : { label: t('Share with counselor'), icon: <Users size={15} />, onSelect: () => share(essay) })
  const dialog = <>
    {choosing && <ShareDialog essay={choosing} onClose={() => setChoosing(null)}
      onUnshare={() => { setConfirming(choosing); setChoosing(null) }}
      onConfirm={(access) => { setChoosing(null); apply(choosing, true, access) }} />}
    {confirming && <UnshareDialog essay={confirming} onClose={() => setConfirming(null)}
      onConfirm={() => { setConfirming(null); apply(confirming, false) }} />}
  </>
  return { share, unshare, busyId, menuItem, dialog }
}

export function SharedBadge({ essay }) {
  if (!isShared(essay)) return null
  return <span className="el-badge is-info el-shared-badge" title={t('Your counselor can read this essay.')}>
    <UserCheck size={12} aria-hidden="true" />{t('Shared')}
  </span>
}

export default function ShareControl({ essay, notify, onSaved }) {
  const sharing = useEssaySharing({ notify, onSaved })
  const busy = sharing.busyId === essay.id
  const shared = isShared(essay)
  // One button either way; narrow headers show only its icon.
  return <>
    <button type="button" className={`el-btn is-ghost el-share${shared ? ' is-shared' : ''}`} disabled={busy} aria-busy={busy}
      aria-label={shared ? `${t('Shared with counselor')}. ${t('Sharing settings')}` : t('Share with counselor')}
      title={shared ? t('Your counselor can read this essay.') : t('Your counselor will be able to read this essay and leave feedback.')}
      onClick={() => sharing.share(essay)}>
      {shared ? <UserCheck size={16} aria-hidden="true" /> : <Users size={16} aria-hidden="true" />}
      <span className="el-share-label" aria-hidden="true">{shared ? t('Shared with counselor') : t('Share with counselor')}</span>
      {shared && <span className="el-share-action" aria-hidden="true">{t('Change')}</span>}
    </button>
    {sharing.dialog}
  </>
}

function ShareDialog({ essay, onConfirm, onUnshare, onClose }) {
  const shared = isShared(essay)
  const [access, setAccess] = useState(() => accessOf(essay))
  const footer = <>
    {shared && <button type="button" className="el-btn is-danger el-share-unshare" onClick={onUnshare}><Lock size={16} aria-hidden="true" />{t('Unshare')}</button>}
    <button type="button" className="el-btn" onClick={onClose}>{t('Cancel')}</button>
    <button type="button" className="el-btn is-primary" data-autofocus onClick={() => onConfirm(access)}>
      {shared ? t('Save') : <><Users size={16} aria-hidden="true" />{t('Share')}</>}
    </button>
  </>
  return <Dialog title={shared ? t('Sharing “{title}”', { title: essay.title }) : t('Share “{title}” with your counselor', { title: essay.title })} onClose={onClose} footer={footer}>
    <fieldset className="el-share-options">
      <legend className="el-dialog-text">{t('What can your counselor do?')}</legend>
      {COUNSELOR_ACCESS.map((option) => <label key={option.id} className={`el-share-option${access === option.id ? ' is-selected' : ''}`}>
        <input type="radio" name="el-share-access" value={option.id} checked={access === option.id} onChange={() => setAccess(option.id)} />
        <span><strong>{t(option.label)}</strong><small>{t(option.hint)}</small></span>
      </label>)}
    </fieldset>
  </Dialog>
}

function UnshareDialog({ essay, onConfirm, onClose }) {
  const footer = <>
    <button type="button" className="el-btn" data-autofocus onClick={onClose}>{t('Cancel')}</button>
    <button type="button" className="el-btn is-danger-solid" onClick={onConfirm}><Lock size={16} aria-hidden="true" />{t('Unshare')}</button>
  </>
  return <Dialog title={t('Unshare “{title}”?', { title: essay.title })} onClose={onClose} footer={footer}>
    <p className="el-dialog-text">{t('Your counselor loses access to this essay right away. Their feedback is kept and comes back if you share it again.')}</p>
  </Dialog>
}
