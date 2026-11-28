import { APP_VERSION } from '../lib/appVersion';
import { t } from '../i18n';

// Small muted version line under the role in the sidebar account card.
export default function AppVersion() {
  const text = `${t('Version')} ${APP_VERSION}`;
  return <span className="app-version" title={text}><span aria-hidden="true">v{APP_VERSION}</span><span className="sr-only">{text}</span></span>;
}
