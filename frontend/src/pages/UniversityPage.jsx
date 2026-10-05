import { useState } from 'react';
import { ArrowLeft, ArrowRight, CalendarDays, Check, CheckCircle2, Circle, Clock3, ExternalLink, FileText, Link2, Mail, MapPin, Minus, PenLine, Plus, RefreshCw } from 'lucide-react';
import { formatNumberLocale, formatPercentLocale, t, tx } from '../i18n';
import { PortalTabs } from '../components/forms';
import { Empty } from '../components/ui';
import { QsUniversityDetails } from '../components/QsUniversityDetails';
import { qsClassification } from '../lib/qs';
import { AidTags, DeadlineCard, InfoCard, PriceMeter, SatRange, ScoreBreakdown, TierBand } from '../components/college';
import { dateText, money } from '../lib/format';
import { initials, label, ownStudent } from '../lib/labels';
import { daysUntil, dueLabel, dueTone, eligibleScholarship, essayProgress, matchingPrograms, percentText, satLabel, scalePercent, scholarshipRequirements } from '../lib/college';

function UniversityOverview({ university, result, research, researchLoading, student, application, essays, onLeave, setPage }) {
  const budget = Number(student?.budget_usd) || 0;
  const sat = Number(student?.sat_score) || 0;
  const net = university.net_price_usd;
  const rate = university.acceptance_rate;
  const programs = matchingPrograms(university, student?.target_major);
  const shownPrograms = programs.length ? programs : (university.programs || []).slice(0, 5);
  const essay = essayProgress(essays);
  return <div className="two-column">
    <div className="stack-16">
      <InfoCard title="Fit for your profile">{result ? <div className="fit-summary"><div className="fit-score"><b>{formatNumberLocale(result.match_score)}</b><span>{label(result.match_label)}</span><small>{t("Not an admission probability. It measures fit, preference and affordability.")}</small></div><ScoreBreakdown breakdown={result.score_breakdown} /></div> :
      researchLoading ? <p className="note"><RefreshCw className="spin" size={14} aria-hidden="true" /> {t("Analyzing your profile")}</p> :
      <div className="fit-missing"><p className="note">{research?.ready ? t("Detailed scoring is not available for this university yet.") : t("Complete your research profile to see how well this university fits you.")}</p>{!research?.ready && <button type="button" className="button quiet small" onClick={onLeave}>{t("Complete profile")}</button>}</div>}</InfoCard>
      {result && <div className="pair">
        <InfoCard title="Why it fits"><ul className="note-list ok">{result.reasons.map((reason) => <li key={reason}><CheckCircle2 size={15} aria-hidden="true" /><span>{reason}</span></li>)}</ul></InfoCard>
        <InfoCard title="Watch-outs"><ul className="note-list gap">{result.gaps.map((gap) => <li key={gap}><Clock3 size={15} aria-hidden="true" /><span>{gap}</span></li>)}{!result.gaps.length && <li><CheckCircle2 size={15} aria-hidden="true" /><span>{t("Nothing to watch out for.")}</span></li>}</ul></InfoCard>
      </div>}
      <QsUniversityDetails university={university} />
      <InfoCard title="Numbers that matter"><div className="numbers">
        <div><span className="k">{t("Acceptance rate")}</span><span className="v">{percentText(rate)}</span><span className="s">{rate == null ? t("Not available in the catalog.") : Number(rate) < 15 ? t("Highly selective: fewer than 15% are admitted.") : Number(rate) >= 45 ? t("Less selective: 45% or more are admitted.") : t("Moderately selective.")}</span></div>
        <div><span className="k">{t("SAT range")}</span><span className="v">{satLabel(university)}</span>{university.sat_min && <SatRange min={university.sat_min} max={university.sat_max} score={sat} />}<span className={`s ${sat && university.sat_min && sat < university.sat_min ? 'warn' : ''}`.trim()}>{!sat || !university.sat_min ? t("No SAT minimum listed.") : sat < university.sat_min ? tx`Your SAT is ${String(sat)}, ${university.sat_min - sat} below` : tx`Your SAT is ${String(sat)}, in range`}</span></div>
        <div><span className="k">{t("Tuition")}</span><span className="v">{money(university.tuition_usd)}</span><span className="s">{t("Per year, before aid.")}</span></div>
        <div><span className="k">{t("Net price")}</span><span className="v">{money(net)}</span>{net != null && <PriceMeter price={net} budget={budget} />}<span className={`s ${net != null && budget && net > budget ? 'warn' : ''}`.trim()}>{net == null || !budget ? t("Estimated per year, after aid.") : net > budget ? tx`${money(net - budget)} above your ${money(budget)} budget` : t("Within your budget")}</span></div>
        <div><span className="k">{t("Average aid")}</span><span className="v">{money(university.average_aid_usd)}</span><span className="s">{university.students_receiving_aid_percent != null ? tx`${university.students_receiving_aid_percent}% of students receive aid.` : t("Per year.")}</span></div>
        <div><span className="k">{t("Undergraduates")}</span><span className="v">{university.undergrad_enrollment != null ? formatNumberLocale(university.undergrad_enrollment) : '—'}</span><span className="s">{university.student_faculty_ratio ? tx`Student–faculty ratio ${university.student_faculty_ratio}.` : t("Not available in the catalog.")}</span></div>
      </div></InfoCard>
      <InfoCard title={student?.target_major && programs.length ? tx`Programs matching ${student.target_major}` : t("Programs")}>
        {shownPrograms.map((program) => <div className="program-line" key={program.id}><div><b>{program.name}</b><small>{[program.duration_years && tx`${program.duration_years} years`, program.teaching_language].filter(Boolean).join(' · ')}</small></div>{(program.source_url || program.application_url) && <a className="button quiet small" href={program.source_url || program.application_url} target="_blank" rel="noreferrer">{t("Source")} <ExternalLink size={14} aria-hidden="true" /></a>}</div>)}
        {!shownPrograms.length && <Empty text={t("No programs are listed for this university yet.")} />}
      </InfoCard>
    </div>
    <div className="stack-16">
      <DeadlineCard university={university} application={application} />
      {application && <InfoCard title="Your application">
        <div className="kv"><span>{t("Stage")}</span><b>{label(application.status)}</b></div>
        <div className="kv"><span>{t("Essays")}</span><span className={`tag ${essay.tone}`.trim()}><PenLine size={12} aria-hidden="true" /> {essay.text}</span></div>
        <div className="kv"><span>{t("Portal")}</span>{application.application_portal_url ? <span className="tag ok"><Link2 size={12} aria-hidden="true" /> {t("Linked")}</span> : <span className="tag warn"><Link2 size={12} aria-hidden="true" /> {t("Not linked")}</span>}</div>
        <button type="button" className="button primary small" onClick={() => setPage('applications')}>{t("Open in Applications")} <ArrowRight size={14} aria-hidden="true" /></button>
      </InfoCard>}
    </div>
  </div>;
}

function ScholarshipItem({ item, university, student }) {
  const eligible = eligibleScholarship(item, student);
  const requirements = [item.min_gpa && `${t("GPA")} ${item.min_gpa}+`, item.min_ielts && `${t("IELTS")} ${item.min_ielts}+`, item.min_sat && `${t("SAT")} ${item.min_sat}+`, ...scholarshipRequirements(item).map((requirement) => t(requirement))].filter(Boolean);
  return <article className="info-card scholarship-item">
    <div className="scholarship-top"><div><h3>{item.title}</h3><p>{item.provider}{item.university ? ` · ${tx`linked to ${university.name}`}` : ''}</p></div><div className="scholarship-amount"><b>{item.amount_usd ? money(item.amount_usd) : label(item.funding_level)}</b><span>{label(item.funding_level)}</span></div></div>
    <div className="tag-row"><span className="tag">{label(item.scholarship_type)}</span><span className="tag">{label(item.funding_level)}</span><span className="tag">{label(item.scope)}</span>{!item.university && <span className="tag budget">{t("Open to any university")}</span>}</div>
    {item.coverage && <p className="scholarship-coverage">{item.coverage}</p>}
    {requirements.length > 0 && <div className="tag-row">{requirements.map((requirement) => <span className="tag" key={requirement}>{requirement}</span>)}</div>}
    <footer><span><CalendarDays size={14} aria-hidden="true" /> {tx`Deadline ${dateText(item.deadline)}`}</span>{eligible ? <span className="tag ok"><Check size={12} aria-hidden="true" /> {t("Profile match")}</span> : <span className="tag warn">{t("Review requirements")}</span>}{item.application_url && <a className="button quiet small" href={item.application_url} target="_blank" rel="noreferrer">{t("Application info")} <ExternalLink size={14} aria-hidden="true" /></a>}</footer>
  </article>;
}

function UniversityAid({ university, scholarships, student }) {
  return <div className="two-column">
    <div className="stack-16">
      <InfoCard title={tx`Aid at ${university.name}`}>
        <AidTags university={university} />
        <div className="numbers">
          <div><span className="k">{t("Average aid")}</span><span className="v">{money(university.average_aid_usd)}</span><span className="s">{t("Per year.")}</span></div>
          <div><span className="k">{t("Students receiving aid")}</span><span className="v">{university.students_receiving_aid_percent != null ? formatPercentLocale(university.students_receiving_aid_percent) : '—'}</span><span className="s">{t("Of undergraduates.")}</span></div>
          <div><span className="k">{t("Need-blind")}</span><span className="v">{university.need_blind ? t("Yes") : t("No")}</span><span className="s">{university.need_blind ? t("Aid does not affect admission.") : t("Aid can affect admission.")}</span></div>
        </div>
      </InfoCard>
      {scholarships.map((item) => <ScholarshipItem key={item.id} item={item} university={university} student={student} />)}
      {!scholarships.length && <Empty text={t("No scholarships are linked to this university yet.")} />}
    </div>
    <div className="stack-16">
      <InfoCard title="Aid deadline"><div className="big-date">{university.scholarship_deadline ? dateText(university.scholarship_deadline) : '—'}</div>{daysUntil(university.scholarship_deadline) != null && <span className={`due ${dueTone(daysUntil(university.scholarship_deadline))}`.trim()}><Clock3 size={12} aria-hidden="true" /> {dueLabel(daysUntil(university.scholarship_deadline))}</span>}</InfoCard>
      <InfoCard title="Official aid page"><p className="note">{university.aid_application_notes || t("Eligibility is not a final decision; always verify the official requirements.")}</p>{university.financial_aid_url && <a className="button quiet small" href={university.financial_aid_url} target="_blank" rel="noreferrer">{t("Financial aid page")} <ExternalLink size={14} aria-hidden="true" /></a>}</InfoCard>
    </div>
  </div>;
}

function universityNeeds(data, university, application, student) {
  const transcript = data.documents.find((document) => document.document_type === 'transcript' && ['uploaded', 'reviewing', 'approved'].includes(document.status));
  const essays = application ? data.essays.filter((essay) => essay.application === application.id) : [];
  const essaysApproved = essays.filter((essay) => essay.status === 'approved').length;
  const lettersApproved = data.recommendations.filter((letter) => letter.status === 'approved').length;
  const documents = [
    { key: 'transcript', title: 'Academic transcript', detail: transcript ? `${t("Official grades and school records")} · ${tx`uploaded ${dateText(transcript.created_at)}`}` : t("Official grades and school records"), state: transcript ? 'ok' : 'open', page: 'student_center', label: transcript ? 'View' : 'Open Student Center' },
    student?.scholarship_needed && { key: 'family', title: 'Family financial documents', detail: t("Income, tax or employer statements requested by the institution"), state: 'open', page: 'student_center', label: 'Open Student Center' },
    { key: 'bank', title: 'Bank or sponsor statement', detail: t("Proof of available funds for international study"), state: 'open', page: 'student_center', label: 'Open Student Center' },
    { key: 'essays', title: 'Scholarship essays', detail: essays.length ? `${t("Motivation, impact and financial-need responses")} · ${tx`${essaysApproved} of ${essays.length} approved`}` : t("Motivation, impact and financial-need responses"), state: essays.length && essaysApproved === essays.length ? 'ok' : essays.length ? 'wait' : 'open', icon: PenLine, page: 'essay_lab', label: 'Open Essay Lab' },
    { key: 'letters', title: 'Recommendation letters', detail: data.recommendations.length ? `${t("Teacher or counselor recommendations")} · ${tx`${lettersApproved} of ${data.recommendations.length} approved`}` : t("Teacher or counselor recommendations"), state: data.recommendations.length && lettersApproved === data.recommendations.length ? 'ok' : data.recommendations.length ? 'wait' : 'open', icon: Mail, page: 'student_center', label: 'Manage letters' }
  ].filter(Boolean);
  const forms = [
    { key: 'css', title: 'CSS Profile', needed: university.css_profile_required, detail: university.css_profile_required ? tx`Required by ${university.name} for financial aid` : tx`Not required by ${university.name}` },
    { key: 'fafsa', title: 'FAFSA', needed: university.fafsa_required, detail: university.fafsa_required ? tx`Required by ${university.name} for financial aid` : tx`Not required by ${university.name} for your profile` }
  ];
  const required = [...documents, ...forms.filter((form) => form.needed)];
  return { documents, forms, total: required.length, ready: documents.filter((row) => row.state === 'ok').length, next: required.find((row) => row.state !== 'ok') };
}

function UniversityNeeds({ university, needs, setPage }) {
  const days = daysUntil(university.application_deadline);
  return <div className="two-column">
    <div className="stack-16">
      <InfoCard title="Ready to send"><div className="big-count"><b>{tx`${needs.ready} of ${needs.total}`}</b><span>{t("ready")}</span></div><span className="score-bar wide" aria-hidden="true"><i style={{ '--fill': scalePercent(needs.ready, 0, needs.total || 1) }} /></span>{needs.next && <p className="note">{tx`Next: ${t(needs.next.title)}`}</p>}</InfoCard>
      <InfoCard title="Documents">{needs.documents.map((row) => {const RowIcon = row.state === 'ok' ? Check : row.icon || Circle;return <div className={`need-row ${row.state}`} key={row.key}><span className="need-icon" aria-hidden="true"><RowIcon size={16} /></span><div><b>{t(row.title)}</b><small>{row.detail}</small></div><button type="button" className="button quiet small" onClick={() => setPage(row.page)}>{t(row.label)}</button></div>;})}</InfoCard>
      <InfoCard title="Forms">{needs.forms.map((form) => <div className={`need-row ${form.needed ? 'open' : 'off'}`} key={form.key}><span className="need-icon" aria-hidden="true">{form.needed ? <FileText size={16} /> : <Minus size={16} />}</span><div><b>{t(form.title)}</b><small>{form.detail}</small></div>{form.needed ? university.financial_aid_url && <a className="button quiet small" href={university.financial_aid_url} target="_blank" rel="noreferrer">{tx`Open ${t(form.title)}`} <ExternalLink size={14} aria-hidden="true" /></a> : <span className="tag">{t("Not needed")}</span>}</div>)}</InfoCard>
    </div>
    <div className="stack-16">
      <InfoCard title="Deadline"><div className="big-date">{university.application_deadline ? dateText(university.application_deadline) : '—'}</div><small className="note">{t("Application and aid")}</small>{days != null && <span className={`due ${dueTone(days)}`.trim()}><Clock3 size={12} aria-hidden="true" /> {dueLabel(days)}</span>}</InfoCard>
      <InfoCard title="Official requirements"><p className="note">{tx`This list is based on your profile and ${university.name}’s catalog data. Only documents uploaded to Naseeb Edu are counted as ready. Verify the final requirements on the official financial aid page.`}</p>{university.financial_aid_url && <a className="button quiet small" href={university.financial_aid_url} target="_blank" rel="noreferrer">{t("Financial aid page")} <ExternalLink size={14} aria-hidden="true" /></a>}</InfoCard>
    </div>
  </div>;
}

export function UniversityPage({ data, university, result, research, researchLoading, application, busy, onAdd, onRemove, onBack, setPage }) {
  const [tab, setTab] = useState('overview');
  const student = ownStudent(data);
  const scholarships = data.scholarships.filter((item) => item.is_active !== false && (item.university === university.id || item.university == null));
  const essays = application ? data.essays.filter((essay) => essay.application === application.id) : [];
  const needs = universityNeeds(data, university, application, student);
  return <div className="section-stack student-portal college-university">
    <nav className="crumb" aria-label={t("Breadcrumb")}><button type="button" className="link-button" onClick={onBack}><ArrowLeft size={14} aria-hidden="true" /> {t("College Search")}</button><span aria-hidden="true">/</span><b>{university.name}</b></nav>
    <section className="info-card university-head" aria-label={university.name}>
      <div className="university-head-top"><span className="monogram" aria-hidden="true">{initials(university.name)}</span><div><h2>{university.name}</h2>
        <p className="university-facts"><span><MapPin size={14} aria-hidden="true" /> {[university.city, university.country].filter(Boolean).join(', ')}</span><span>{university.qs_data?.status ? qsClassification('status', university.qs_data.status) : label(university.institution_type)}</span>{university.campus_setting && <span>{tx`${label(university.campus_setting)} campus`}</span>}<span>{label(university.degree_type)}</span>{result?.admission_band && <TierBand value={result.admission_band} />}</p></div></div>
      <div className="university-actions">
        {application ? <span className="tag ok large"><Check size={14} aria-hidden="true" /> {t("In my list")}</span> : <button type="button" className="button primary" disabled={busy} aria-busy={busy} onClick={onAdd}><Plus size={16} aria-hidden="true" /> {t("Add to my list")}</button>}
        {university.website && <a className="button quiet" href={university.website} target="_blank" rel="noreferrer">{t("Official site")} <ExternalLink size={14} aria-hidden="true" /></a>}
        {application && <button type="button" className="link-button push-end" disabled={busy} aria-busy={busy} onClick={onRemove}>{t("Remove from my list")}</button>}
      </div>
    </section>
    <PortalTabs active={tab} onChange={setTab} items={[['overview', 'Overview'], ['aid', 'Scholarships & Aid', scholarships.length], ['needs', 'What you need', needs.total]]} />
    {tab === 'overview' && <UniversityOverview {...{ university, result, research, researchLoading, student, application, essays, setPage }} onLeave={onBack} />}
    {tab === 'aid' && <UniversityAid {...{ university, scholarships, student }} />}
    {tab === 'needs' && <UniversityNeeds {...{ university, needs, setPage }} />}
  </div>;
}
