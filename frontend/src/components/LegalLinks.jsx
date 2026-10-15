import { t } from '../i18n';

export function LegalLinks() {
  return <nav className="legal-links" aria-label={t('Legal information')}>
    <a href="/privacy">{t('Privacy policy')}</a>
    <a href="/terms">{t('Terms of use')}</a>
  </nav>;
}
