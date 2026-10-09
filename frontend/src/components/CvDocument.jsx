import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { FileDown } from 'lucide-react';
import { api } from '../api';
import { t } from '../i18n';
import { CV_ADDITIONAL_LABELS, CV_SECTION_TITLES, contactLine, cvDateRange, hasCvContent, linkText, safeHref } from '../lib/cv';
import './cv.css';

// A4 with ~2 cm margins, only while the CV is on the page: other prints keep the browser default.
const PAGE_STYLE = '@page { size: A4; margin: 14mm 20mm 16mm; }';

function Link({ url }) {
  const href = safeHref(url);
  return href ? <a href={href}>{linkText(url)}</a> : <span>{linkText(url)}</span>;
}

function Entry({ entry }) {
  const dates = cvDateRange(entry);
  return <div className="cv-entry">
    <div className="cv-line cv-line-org">
      <span>{entry.organization}{entry.link && <> | <Link url={entry.link} /></>}</span>
      {entry.location && <span className="cv-right">{entry.location}</span>}
    </div>
    {(entry.title || dates) && <div className="cv-line cv-line-role">
      <span>{entry.title}</span>
      {dates && <span className="cv-right">{dates}</span>}
    </div>}
    {entry.note && <p className="cv-note">{entry.note}</p>}
    {entry.bullets?.length > 0 && <ul className="cv-bullets">{entry.bullets.map((item, i) => <li key={i}>{item}</li>)}</ul>}
  </div>;
}

function Section({ title, children }) {
  return <section className="cv-section">
    <h2>{title}</h2>
    {children}
  </section>;
}

// The CV itself. The header sits in a table head, which the browser repeats at
// the top of every printed page.
export function CvDocument({ cv }) {
  const { header = {}, sections = [], additional = [] } = cv || {};
  return <article className="cv-document" lang="en">
    <table className="cv-page">
      <thead><tr><td>
        <header className="cv-header">
          <h1>{header.name}</h1>
          {contactLine(header) && <p>{contactLine(header)}</p>}
          {header.links?.length > 0 && <p className="cv-links">{header.links.map((url, i) => <span key={url}>{i > 0 && ' | '}<Link url={url} /></span>)}</p>}
        </header>
      </td></tr></thead>
      <tbody><tr><td>
        {sections.map((section) => <Section key={section.key} title={CV_SECTION_TITLES[section.key]}>
          {section.entries.map((entry, i) => <Entry key={i} entry={entry} />)}
        </Section>)}
        {additional.length > 0 && <Section title={CV_SECTION_TITLES.additional}>
          <ul className="cv-bullets cv-additional">{additional.map((row) => <li key={row.key}><b>{CV_ADDITIONAL_LABELS[row.key] || row.key}:</b> {row.value}</li>)}</ul>
        </Section>}
      </td></tr></tbody>
    </table>
  </article>;
}

// "Download CV": loads the student's CV (only résumé fields leave the server),
// puts it on the page for print only and opens the browser's print dialog,
// where "Save as PDF" writes the file. studentId: a staff member's student;
// without it, the signed-in student's own CV.
export function DownloadCvButton({ studentId = null, className = 'button secondary', notify = () => {} }) {
  const [cv, setCv] = useState(null);
  const [loading, setLoading] = useState(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    if (!cv) return undefined;
    document.body.classList.add('printing-cv');
    const done = () => { if (active.current) setCv(null); };
    window.addEventListener('afterprint', done);
    // Print once the CV is in the page; the fallback clears it if afterprint never fires.
    const frame = window.requestAnimationFrame(() => { try { window.print(); } catch { done(); } });
    const fallback = window.setTimeout(done, 60_000);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(fallback);
      window.removeEventListener('afterprint', done);
      document.body.classList.remove('printing-cv');
    };
  }, [cv]);
  async function download() {
    if (loading) return;
    setLoading(true);
    try {
      const data = await (studentId ? api.studentCv(studentId) : api.myCv());
      if (!active.current) return;
      if (!hasCvContent(data)) notify(t('Add your school, activities or honors first: the CV is still empty.'), 'error');
      else setCv(data);
    } catch (e) {
      if (active.current) notify(e.message || t('The CV could not be loaded. Try again.'), 'error');
    } finally {
      if (active.current) setLoading(false);
    }
  }
  return <>
    <button type="button" className={className} onClick={download} disabled={loading} aria-busy={loading}><FileDown size={16} aria-hidden="true" /> {loading ? t('Preparing CV…') : t('Download CV')}</button>
    {cv && createPortal(<div className="cv-print-root"><style>{PAGE_STYLE}</style><CvDocument cv={cv} /></div>, document.body)}
  </>;
}
