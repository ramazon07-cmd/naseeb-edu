import { useEffect, useRef, useState } from 'react';
import { createPortal, flushSync } from 'react-dom';
import { FileDown, Printer } from 'lucide-react';
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

// One role at an organization: role | dates, an italic note, then bullets.
function Role({ role }) {
  const dates = cvDateRange(role);
  return <div className="cv-role">
    {(role.title || dates) && <div className="cv-line cv-line-role">
      <span>{role.title}</span>
      {dates && <span className="cv-right">{dates}</span>}
    </div>}
    {role.note && <p className="cv-note">{role.note}</p>}
    {role.bullets?.length > 0 && <ul className="cv-bullets">{role.bullets.map((item, i) => <li key={i}>{item}</li>)}</ul>}
  </div>;
}

// Organization | location, then its role (or, when the student held several there, each role).
function Entry({ entry }) {
  return <div className="cv-entry">
    <div className="cv-line cv-line-org">
      <span>{entry.organization}{entry.link && <> | <Link url={entry.link} /></>}</span>
      {entry.location && <span className="cv-right">{entry.location}</span>}
    </div>
    {entry.roles?.length ? entry.roles.map((role, i) => <Role key={i} role={role} />) : <Role role={entry} />}
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

// A loaded CV is reused for this long; a click after that loads it again.
const FRESH_MS = 60_000;

// "Download CV": loads the student's CV (only résumé fields leave the server),
// puts it on the page for print only and opens the browser's print dialog,
// where "Save as PDF" writes the file. studentId: a staff member's student;
// without it, the signed-in student's own CV, loaded ahead of time and again
// whenever refreshKey changes (the page's data was reloaded after an edit).
//
// print() must run inside the click: after an await the click's user
// activation is gone and Safari blocks it. So the CV is fetched ahead (on
// hover, focus or touch, and for the student on load) and a click prints at
// once. When it is not ready yet, the click loads it and offers "Print now".
export function DownloadCvButton({ studentId = null, refreshKey = null, className = 'button secondary', notify = () => {} }) {
  const [printing, setPrinting] = useState(null);
  const [status, setStatus] = useState('idle');
  const loaded = useRef(null);
  const pending = useRef(null);
  const active = useRef(true);
  const finish = useRef(null);
  const key = studentId ?? 'me';
  useEffect(() => { active.current = true; return () => { active.current = false; finish.current?.(); }; }, []);
  const fresh = () => Boolean(loaded.current && loaded.current.key === key && Date.now() - loaded.current.at < FRESH_MS);
  function load() {
    if (fresh()) return Promise.resolve(loaded.current.data);
    if (!pending.current) {
      pending.current = (studentId ? api.studentCv(studentId) : api.myCv())
        .then((data) => { loaded.current = { data, at: Date.now(), key }; return data; })
        .finally(() => { pending.current = null; });
    }
    return pending.current;
  }
  const warm = () => { load().catch(() => {}); };
  useEffect(() => {
    loaded.current = null;
    if (!studentId) warm();
  }, [studentId, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps -- reload when the data behind the CV changes
  function printNow(data) {
    if (!hasCvContent(data)) { notify(t('Add your school, activities or honors first: the CV is still empty.'), 'error'); return; }
    flushSync(() => setPrinting(data));
    document.body.classList.add('printing-cv');
    let fallback;
    const done = () => {
      window.clearTimeout(fallback);
      window.removeEventListener('afterprint', done);
      document.body.classList.remove('printing-cv');
      finish.current = null;
      if (active.current) setPrinting(null);
    };
    finish.current = done;
    window.addEventListener('afterprint', done);
    // Clears the CV if afterprint never fires.
    fallback = window.setTimeout(done, 60_000);
    try { window.print(); } catch { done(); }
  }
  function download() {
    if (fresh()) { printNow(loaded.current.data); return; }
    setStatus('loading');
    load().then(
      (data) => {
        if (!active.current) return;
        if (hasCvContent(data)) setStatus('ready');
        else { setStatus('idle'); notify(t('Add your school, activities or honors first: the CV is still empty.'), 'error'); }
      },
      (e) => { if (active.current) { setStatus('idle'); notify(e.message || t('The CV could not be loaded. Try again.'), 'error'); } },
    );
  }
  function printReady() {
    setStatus('idle');
    printNow(loaded.current?.data);
  }
  return <>
    {status === 'ready'
      ? <button type="button" className={className} onClick={printReady} autoFocus><Printer size={16} aria-hidden="true" /> {t('Print now')}</button>
      : <button type="button" className={className} onClick={download} onPointerEnter={warm} onFocus={warm} onTouchStart={warm} disabled={status === 'loading'} aria-busy={status === 'loading'}><FileDown size={16} aria-hidden="true" /> {status === 'loading' ? t('Preparing CV…') : t('Download CV')}</button>}
    {printing && createPortal(<div className="cv-print-root"><style>{PAGE_STYLE}</style><CvDocument cv={printing} /></div>, document.body)}
  </>;
}
