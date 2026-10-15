import { t } from '../i18n';
import { resourceDisplayState } from '../lib/resourceState';

export function ResourceContent({ keys, statuses = {}, retry, children }) {
  const failed = keys.filter((key) => ['error', 'stale'].includes(resourceDisplayState(statuses[key])));
  const blocked = keys.some((key) => !statuses[key]?.loaded);
  return <>
    {failed.length > 0 && <div className="screen-time-error" role="alert">
      <p>{failed.map((key) => statuses[key].error).filter(Boolean).join(' · ') || t('Some information could not be loaded')}</p>
      <button type="button" className="button quiet small" onClick={() => retry(failed)}>{t('Retry')}</button>
    </div>}
    {blocked ? !failed.length && <p className="dashboard-empty" role="status">{t('Loading…')}</p> : children}
  </>;
}
