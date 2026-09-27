import { useState } from 'react'
import { Lock, UserCheck, Users } from 'lucide-react'
import { t } from '../i18n.js'
import { Dialog } from './ui.jsx'
import { essayLabApi } from './essayLabApi.js'
import { isShared, setSharing, sharingFields } from './sharing.js'

// Share / unshare for the editor header and the library menu. Unsharing asks
// first, because the counselor loses access immediately.
export function useEssaySharing({ notify, onSaved }) {
  const [confirming, setConfirming] = useState(null)
  const [busyId, setBusyId] = useState(null)

  async function apply(essay, shared) {
    setBusyId(essay.id)
    try {
      onSaved(sharingFields(await setSharing(essayLabApi, essay, shared)))
      notify(shared ? t('Shared with your counselor.') : t('Your counselor can no longer see this essay.'))
    } catch (err) {
      notify(err?.message || (shared ? t('Could not share the essay.') : t('Could not unshare the essay.')), 'error')
    } finally {
      setBusyId(null)
    }
  }

  const share = (essay) => apply(essay, true)
  const unshare = (essay) => setConfirming(essay)
  const menuItem = (essay) => (isShared(essay)
    ? { label: t('Unshare'), icon: <Lock size={15} />, onSelect: () => unshare(essay) }
    : { label: t('Share with counselor'), icon: <Users size={15} />, onSelect: () => share(essay) })
  const dialog = confirming && <UnshareDialog essay={confirming} onClose={() => setConfirming(null)}
    onConfirm={() => { setConfirming(null); apply(confirming, false) }} />
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
      aria-label={shared ? `${t('Shared with counselor')}. ${t('Unshare')}` : t('Share with counselor')}
      title={shared ? t('Your counselor can read this essay.') : t('Your counselor will be able to read this essay and leave feedback.')}
      onClick={() => (shared ? sharing.unshare(essay) : sharing.share(essay))}>
      {shared ? <UserCheck size={16} aria-hidden="true" /> : <Users size={16} aria-hidden="true" />}
      <span className="el-share-label" aria-hidden="true">{shared ? t('Shared with counselor') : t('Share with counselor')}</span>
      {shared && <span className="el-share-action" aria-hidden="true">{t('Unshare')}</span>}
    </button>
    {sharing.dialog}
  </>
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
