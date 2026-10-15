import { LegalLinks } from '../components/LegalLinks';
import { ArrowLeft } from 'lucide-react';
import { t } from '../i18n';
import { BrandLockup, LanguageSelector, ThemeToggle } from '../components/brand';
import { LEGAL_DOCUMENTS, LEGAL_LANGUAGES } from '../lib/legalContent';

const SUPPORT_EMAIL = (import.meta.env.VITE_SUPPORT_EMAIL || 'support@naseebedu.com').trim();

export default function LegalPage({ page, theme, toggleTheme, language, changeLanguage }) {
  const document = LEGAL_DOCUMENTS[page];
  return <main className="legal-page">
    <header className="legal-bar">
      <a className="login-return" href="/"><ArrowLeft size={17} /> {t('Home')}</a>
      <div className="login-preferences"><LanguageSelector language={language} onChange={changeLanguage} compact /><ThemeToggle theme={theme} onToggle={toggleTheme} /></div>
    </header>
    <div className="legal-document">
      <BrandLockup theme={theme} subtitle={false} />
      <p className="legal-draft" role="note">{t('Draft — pending legal review')}</p>
      <h1 lang="uz">{document.uz.heading}</h1>
      <nav className="legal-links" aria-label={t('Document languages')}>
        {LEGAL_LANGUAGES.map((code) => <a key={code} href={`#legal-${code}`} lang={code}>{document[code].language}</a>)}
      </nav>
      {LEGAL_LANGUAGES.map((code) => <article className="legal-language" id={`legal-${code}`} lang={code} key={code} aria-labelledby={`legal-heading-${code}`}>
        <h2 id={`legal-heading-${code}`}>{document[code].heading} · {document[code].language}</h2>
        {document[code].sections.map(([heading, body]) => <section key={heading}><h3>{heading}</h3><p>{body}</p></section>)}
        <p>{document[code].contact} <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>.</p>
      </article>)}
      <footer><LegalLinks /><a href="/login">{t('Sign in')}</a></footer>
    </div>
  </main>;
}
