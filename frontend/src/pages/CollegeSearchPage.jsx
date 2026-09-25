import { useState, useEffect } from 'react';
import { ownStudent, label } from '../lib/labels';
import { api } from '../api';
import { t, tp, tx, formatNumberLocale, formatPercentLocale } from '../i18n';
import { School, Globe2, X, RefreshCw, MapPin, CheckCircle2, Clock3, Check, Plus, ExternalLink, ClipboardCheck, Search } from 'lucide-react';
import { PortalTabs, FilterChip } from '../components/forms';
import { Badge, Empty } from '../components/ui';
import { money, dateText, joinParts } from '../lib/format';
import { Detail } from '../components/records';
import { matchesQuery } from '../lib/searchIndex';

export const COLLEGE_REGIONS = [
  { key: 'us', label: 'US', countries: ['usa', 'united states', 'united states of america'] },
  { key: 'canada', label: 'Canada', countries: ['canada'] },
  { key: 'china', label: 'China', countries: ['china', 'mainland china'] },
  { key: 'hong_kong', label: 'Hong Kong', countries: ['hong kong', 'hong kong sar'] },
];

export function universityRegion(university) {
  const market = String(university?.market || '').trim().toLowerCase();
  if (COLLEGE_REGIONS.some((region) => region.key === market)) return market;
  const country = String(university?.country || '').trim().toLowerCase();
  return COLLEGE_REGIONS.find((region) => region.countries.includes(country))?.key || null;
}

export function universityFit(university, student) {
  if (!student) return { score: 0, label: 'Profile needed' };
  let score = 20;
  const targets = String(student.target_countries || '').toLowerCase();
  if (targets.includes(String(university.country || '').toLowerCase())) score += 25;
  if (!university.sat_min || Number(student.sat_score || 0) >= Number(university.sat_min)) score += 25;
  if (!university.net_price_usd || !student.budget_usd || Number(university.net_price_usd) <= Number(student.budget_usd)) score += 15;
  if (!student.scholarship_needed || university.offers_international_aid || university.offers_merit_aid) score += 15;
  const bounded = Math.min(score, 100);
  return { score: bounded, label: bounded >= 80 ? 'Strong fit' : bounded >= 60 ? 'Good fit' : 'Explore' };
}

export function scholarshipRequirements(item) {
  return [
  item.requires_transcript && 'Transcript', item.requires_essay && 'Essay',
  item.requires_recommendation && 'Recommendation', item.requires_financial_documents && 'Financial documents',
  item.requires_cv && 'CV', item.requires_portfolio && 'Portfolio'].
  filter(Boolean);
}

export function eligibleScholarship(item, student) {
  if (!student) return false;
  if (item.min_gpa && Number(student.gpa || 0) < Number(item.min_gpa)) return false;
  if (item.min_ielts && Number(student.ielts_score || 0) < Number(item.min_ielts)) return false;
  if (item.min_sat && Number(student.sat_score || 0) < Number(item.min_sat)) return false;
  return !item.eligible_grades || String(item.eligible_grades).split(',').map((value) => value.trim()).includes(String(student.grade));
}

export function CollegeSearchPage({ data, query, reload, notify }) {
  const [tab, setTab] = useState('universities');
  const [region, setRegion] = useState('us');
  const [admissionBand, setAdmissionBand] = useState('all');
  const [institutionType, setInstitutionType] = useState('all');
  const [maxPrice, setMaxPrice] = useState('all');
  const [minimumAcceptance, setMinimumAcceptance] = useState('0');
  const [aid, setAid] = useState('all');
  const [testOptional, setTestOptional] = useState(false);
  const [scoreMatch, setScoreMatch] = useState(false);
  const [scholarshipType, setScholarshipType] = useState('all');
  const [funding, setFunding] = useState('all');
  const [scope, setScope] = useState('all');
  const [eligibleOnly, setEligibleOnly] = useState(false);
  const [research, setResearch] = useState(null);
  const [researchLoading, setResearchLoading] = useState(true);
  const [researchSaving, setResearchSaving] = useState(false);
  const [researchError, setResearchError] = useState('');
  const student = ownStudent(data);
  const researchMap = new Map((research?.recommendations || []).map((item) => [item.university.id, item]));
  const added = new Set(data.applications.map((item) => item.university));

  useEffect(() => {
    let active = true;
    setResearchLoading(true);
    api.collegeResearch().then((result) => {if (active) {setResearch(result);setResearchError('');}}).catch((error) => {if (active) setResearchError(error.message);}).finally(() => {if (active) setResearchLoading(false);});
    return () => {active = false;};
  }, []);

  async function refreshResearch() {
    setResearchLoading(true);setResearchError('');
    try {setResearch(await api.collegeResearch());} catch (error) {setResearchError(error.message);} finally {setResearchLoading(false);}
  }

  async function completeResearchProfile(payload) {
    setResearchSaving(true);setResearchError('');
    try {
      const result = await api.updateCollegeResearchProfile(payload);
      setResearch(result);
      notify(t("Profile details saved and college research updated."));
      reload();
    } catch (error) {setResearchError(error.message);} finally {setResearchSaving(false);}
  }
  const items = data.universities.filter((item) => {
    const aidMatch = aid === 'all' || aid === 'need' && item.offers_need_based_aid || aid === 'merit' && item.offers_merit_aid || aid === 'international' && item.offers_international_aid || aid === 'full_need' && item.meets_full_need;
    const recommendation = researchMap.get(item.id);
    return universityRegion(item) === region && (
    admissionBand === 'all' || recommendation?.admission_band === admissionBand) && (
    institutionType === 'all' || item.institution_type === institutionType) && (
    maxPrice === 'all' || Number(item.net_price_usd || Infinity) <= Number(maxPrice)) &&
    Number(item.acceptance_rate || 0) >= Number(minimumAcceptance) && (
    !testOptional || item.test_optional) && (
    !scoreMatch || !item.sat_min || Number(student?.sat_score || 0) >= Number(item.sat_min)) &&
    aidMatch && matchesQuery(item, query);
  }).sort((a, b) => (researchMap.get(b.id)?.match_score ?? universityFit(b, student).score) - (researchMap.get(a.id)?.match_score ?? universityFit(a, student).score));
  const scholarships = data.scholarships.filter((item) => (scholarshipType === 'all' || item.scholarship_type === scholarshipType) && (
  funding === 'all' || item.funding_level === funding) && (scope === 'all' || item.scope === scope) && (
  !eligibleOnly || eligibleScholarship(item, student)) && matchesQuery(item, query));
  const universityFiltersActive = [institutionType !== 'all', maxPrice !== 'all', minimumAcceptance !== '0', aid !== 'all', testOptional, scoreMatch, admissionBand !== 'all'].filter(Boolean).length;
  function resetUniversityFilters() {setAdmissionBand('all');setInstitutionType('all');setMaxPrice('all');setMinimumAcceptance('0');setAid('all');setTestOptional(false);setScoreMatch(false);}
  async function shortlist(university) {const band = researchMap.get(university.id)?.admission_band;const tier = band === 'reach' ? 'dream' : band === 'safety' ? 'safety' : 'target';try {await api.create('applications', { student: student?.id, university: university.id, program: student?.target_major || 'Undeclared', tier, status: 'shortlisted', deadline: university.application_deadline, scholarship_deadline: university.scholarship_deadline });notify(tx`${university.name} added to your shortlist.`);reload();} catch (err) {notify(err.message, 'error');}}
  return <div className="section-stack student-portal">
    <div className="college-filter-bar">
      <div className="filter-section-tabs"><PortalTabs active={tab} onChange={setTab} items={[["universities", "Universities"], ["scholarships", "Scholarships & Aid"], ["aid", "What you need"]]} /></div>
      {tab === 'universities' && !researchLoading && research?.ready && <>
        <div className="filter-control-row filter-scope-row">
          <div className="filter-chip-row" role="group" aria-label={t("Country")}><Globe2 className="filter-group-icon" size={15} aria-hidden="true" />{COLLEGE_REGIONS.map(({ key, label: regionLabel }) => <FilterChip key={key} active={region === key} onClick={() => {setRegion(key);setAdmissionBand('all');}}>{t(regionLabel)}</FilterChip>)}</div>
          <div className="filter-chip-row" role="group" aria-label={t("Admission band")}>{[["all", "All matches", ''], ["reach", "Reach", 'tone-reach'], ["target", "Target", 'tone-target'], ["safety", "Safety", 'tone-safety']].map(([value, chipLabel, tone]) => <FilterChip key={value} tone={tone} active={admissionBand === value} onClick={() => setAdmissionBand(value)}>{t(chipLabel)}</FilterChip>)}</div>
          <p className="filter-count"><b>{formatNumberLocale(items.length)}</b> {t("universities found")}</p>
        </div>
        <div className="filter-control-row">
          <select aria-label={t("Institution type")} value={institutionType} onChange={(event) => setInstitutionType(event.target.value)}><option value="all">{t("Public & private")}</option><option value="public">{t("Public")}</option><option value="private">{t("Private")}</option></select>
          <select aria-label={t("Maximum net price")} value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)}><option value="all">{t("Any price")}</option><option value="15000">{t("Up to $15,000")}</option><option value="25000">{t("Up to $25,000")}</option><option value="40000">{t("Up to $40,000")}</option></select>
          <select aria-label={t("Minimum acceptance")} value={minimumAcceptance} onChange={(event) => setMinimumAcceptance(event.target.value)}><option value="0">{t("Any rate")}</option><option value="10">10%+</option><option value="25">25%+</option><option value="50">50%+</option></select>
          <select aria-label={t("Aid type")} value={aid} onChange={(event) => setAid(event.target.value)}><option value="all">{t("Any aid")}</option><option value="need">{t("Need-based")}</option><option value="merit">{t("Merit")}</option><option value="international">{t("International aid")}</option><option value="full_need">{t("Meets full need")}</option></select>
          <FilterChip active={testOptional} onClick={() => setTestOptional(!testOptional)}>{t("Test optional only")}</FilterChip>
          <FilterChip active={scoreMatch} onClick={() => setScoreMatch(!scoreMatch)}>{t("My SAT matches")}</FilterChip>
          {universityFiltersActive > 0 && <button type="button" className="filter-reset" onClick={resetUniversityFilters}><X size={13} /> {t("Clear")} ({universityFiltersActive})</button>}
        </div>
      </>}
      {tab === 'scholarships' && <div className="filter-control-row">
        <select aria-label={t("Scholarship type")} value={scholarshipType} onChange={(event) => setScholarshipType(event.target.value)}><option value="all">{t("All types")}</option><option value="merit">{t("Merit")}</option><option value="need_based">{t("Need-based")}</option><option value="leadership">{t("Leadership")}</option><option value="research">{t("Research")}</option><option value="full_ride">{t("Full ride")}</option></select>
        <select aria-label={t("Funding")} value={funding} onChange={(event) => setFunding(event.target.value)}><option value="all">{t("Any funding")}</option><option value="full">{t("Full funding")}</option><option value="partial">{t("Partial")}</option><option value="fixed">{t("Fixed amount")}</option></select>
        <select aria-label={t("Scope")} value={scope} onChange={(event) => setScope(event.target.value)}><option value="all">{t("National & International")}</option><option value="national">{t("National")}</option><option value="international">{t("International")}</option></select>
        <FilterChip active={eligibleOnly} onClick={() => setEligibleOnly(!eligibleOnly)}>{t("Eligible for my profile")}</FilterChip>
        <p className="filter-count"><b>{formatNumberLocale(scholarships.length)}</b> {t("scholarships found")}</p>
      </div>}
    </div>
    {tab === 'universities' && researchLoading && <div className="college-research-state"><RefreshCw className="spin" size={22} /><div><b>{t("Analyzing your profile")}</b><p>{t("Checking SAT, GPA, IELTS, major, budget, and portfolio evidence.")}</p></div></div>}
    {tab === 'universities' && researchError && <div className="college-research-state error"><X size={22} /><div><b>{t("College research could not be loaded")}</b><p>{researchError}</p></div><button className="button quiet small" onClick={refreshResearch}>{t("Retry")}</button></div>}
    {tab === 'universities' && !researchLoading && research && !research.ready && <CollegeProfileQuestions research={research} saving={researchSaving} onComplete={completeResearchProfile} />}
    {tab === 'universities' && !researchLoading && research?.ready && <><CollegeResearchOverview research={research} onRefresh={refreshResearch} />
      <section className="finder-results"><p className="finder-note">{t("The match score is not an admission probability; it measures profile, preference, and affordability fit.")}</p><div className="university-results">{items.map((uni) => {const result = researchMap.get(uni.id);const fit = result ? { score: result.match_score, label: result.match_label } : universityFit(uni, student);return <article className="university-card" key={uni.id}><header><span className="rank" title={uni.ranking ? t("Ranking") : undefined}>{uni.ranking ? `#${formatNumberLocale(uni.ranking)}` : <School size={18} aria-hidden="true" />}</span><div><h3>{uni.name}</h3><p><MapPin size={14} /> {joinParts([uni.city, uni.country].filter(Boolean).join(', '), label(uni.institution_type))}</p></div><div className="university-fit"><span className="fit-badge">{formatPercentLocale(fit.score)} {label(fit.label)}</span>{result && <Badge>{result.admission_band}</Badge>}</div></header><div className="university-metrics"><div><span>{t("Acceptance")}</span><b>{uni.acceptance_rate ? formatPercentLocale(uni.acceptance_rate) : '—'}</b></div><div><span>{t("Net price")}</span><b>{money(uni.net_price_usd)}</b></div><div><span>{t("Average aid")}</span><b>{money(uni.average_aid_usd)}</b></div><div><span>{t("SAT range")}</span><b>{uni.sat_min ? `${formatNumberLocale(uni.sat_min)}–${uni.sat_max ? formatNumberLocale(uni.sat_max) : '—'}` : uni.test_optional ? t("Test optional") : t("Not published")}</b></div></div>{result && <div className="research-breakdown">{Object.entries(result.score_breakdown).map(([name, value]) => <div key={name}><span>{label(name)}</span><div className="progress"><i style={{ width: `${Math.min(100, Number(value) * (name === 'academic' ? 2 : name === 'preferences' ? 4.5 : name === 'financial' ? 5 : 10))}%` }} /></div><b>{formatNumberLocale(value)}</b></div>)}</div>}<div className="aid-badges">{uni.offers_need_based_aid && <span>{t("Need-based")}</span>}{uni.offers_merit_aid && <span>{t("Merit")}</span>}{uni.offers_international_aid && <span>{t("International aid")}</span>}{uni.meets_full_need && <span>{t("Meets full need")}</span>}{uni.test_optional && <span>{t("Test optional")}</span>}</div>{result && <details className="research-details"><summary>{t("Why this result?")}</summary><div><ul>{result.reasons.map((reason) => <li key={reason}><CheckCircle2 size={13} /> {reason}</li>)}</ul>{result.gaps.length > 0 && <ul className="gaps">{result.gaps.map((gap) => <li key={gap}><Clock3 size={13} /> {gap}</li>)}</ul>}</div></details>}<footer><div>{uni.application_deadline && <span>{tx`Application deadline: ${dateText(uni.application_deadline)}`}</span>}{uni.scholarship_deadline && <span>{tx`Aid deadline: ${dateText(uni.scholarship_deadline)}`}</span>}</div>{added.has(uni.id) ? <span className="added"><Check size={17} /> {t("Shortlisted")}</span> : <button className="button primary small" onClick={() => shortlist(uni)}><Plus size={16} /> {t("Shortlist")}</button>}</footer></article>;})}{!items.length && <Empty text={t("No universities match these filters.")} />}</div></section>
    </>}
    {tab === 'scholarships' && <><section className="finder-results"><p className="finder-note">{t("Eligibility is not a final decision; always verify the official requirements.")}</p><div className="scholarship-grid">{scholarships.map((item) => {const eligible = eligibleScholarship(item, student);return <article className="scholarship-card" key={item.id}><header><div><span>{label(item.scholarship_type)}</span><h3>{item.title}</h3><p>{item.provider}{item.university_name ? ` · ${item.university_name}` : ''}</p></div><Badge>{item.scope}</Badge></header><strong>{item.funding_level === 'fixed' ? money(item.amount_usd) : label(item.funding_level)}</strong><p>{item.coverage}</p><div className="eligibility-row"><span className={eligible ? "eligible" : "review"}>{eligible ? t("Profile match") : t("Review requirements")}</span>{item.deadline && <span>{tx`Deadline: ${dateText(item.deadline)}`}</span>}</div><div className="score-requirements">{item.min_gpa && <span>{t("GPA")} {item.min_gpa}+</span>}{item.min_ielts && <span>{t("IELTS")} {item.min_ielts}+</span>}{item.min_sat && <span>{t("SAT")} {item.min_sat}+</span>}</div><div className="requirement-tags">{scholarshipRequirements(item).map((requirement) => <span key={requirement}>{t(requirement)}</span>)}</div>{item.application_url && <a className="button quiet small" href={item.application_url} target="_blank" rel="noreferrer">{t("Application info")} <ExternalLink size={14} /></a>}</article>;})}{!scholarships.length && <Empty text={t("No matching scholarships found.")} />}</div></section></>}
    {tab === 'aid' && <AidChecklist data={data} student={student} />}
  </div>;
}

export function CollegeProfileQuestions({ research, saving, onComplete }) {
  const [answers, setAnswers] = useState(() => Object.fromEntries(research.questions.map((question) => [question.field, research.profile_snapshot?.[question.field] ?? ''])));
  function submit(event) {
    event.preventDefault();
    onComplete(answers);
  }
  return <section className="college-profile-questions"><div className="research-question-copy"><span><ClipboardCheck size={20} /></span><div><span className="eyebrow">{t("PROFILE DATA REQUIRED")}</span><h2>{t("A few details are missing from your research profile")}</h2><p>{t("Your answers will be saved to your student profile and used to rank universities for you.")}</p></div></div><form onSubmit={submit}><div className="research-question-grid">{research.questions.map((question) => <label key={question.field}><span>{question.label}</span><input type={question.type} min={question.min} max={question.max} step={question.step || (question.type === 'number' ? '1' : undefined)} placeholder={question.placeholder} value={answers[question.field] ?? ''} onChange={(event) => setAnswers((current) => ({ ...current, [question.field]: event.target.value }))} required /></label>)}</div><footer><small>{tp('{n} answer required|{n} answers required', research.questions.length, { n: research.questions.length })}</small><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? <><RefreshCw className="spin" size={16} /> {t("Researching…")}</> : <><Search size={16} /> {t("Save & research")}</>}</button></footer></form></section>;
}

export function CollegeResearchOverview({ research, onRefresh }) {
  const profile = research.profile_snapshot || {};
  const evidence = Object.values(profile.evidence || {}).reduce((total, value) => total + Number(value || 0), 0);
  return <section className="college-research-overview"><div><span className="research-status-icon"><CheckCircle2 size={21} /></span><div><span className="eyebrow">{t("RESEARCH READY")}</span><h3>{t("Results calculated from your student profile")}</h3><p>{research.methodology}</p></div></div><div className="research-profile-chips">{[[t("SAT"), profile.sat_score], [t("GPA"), profile.gpa], [t("IELTS"), profile.ielts_score], [t("Major"), profile.target_major], [t("Budget"), profile.budget_usd == null ? null : money(profile.budget_usd)], [t("Portfolio items"), evidence]].filter(([, value]) => value !== null && value !== undefined && value !== '').map(([name, value]) => <span key={name}>{name} <b>{value}</b></span>)}</div><button className="button quiet small" onClick={onRefresh}><RefreshCw size={15} /> {t("Refresh")}</button></section>;
}

export function AidChecklist({ data, student }) {
  const shortlisted = data.applications.map((item) => data.universities.find((uni) => uni.id === item.university)).filter(Boolean);
  const needsCss = shortlisted.some((uni) => uni.css_profile_required);
  const needsFafsa = shortlisted.some((uni) => uni.fafsa_required);
  const checklist = [
  ['Academic transcript', 'Official grades and school records', true],
  ['Family financial documents', 'Income, tax or employer statements requested by the institution', student?.scholarship_needed],
  ['Bank or sponsor statement', 'Proof of available funds for international study', true],
  ['Scholarship essays', 'Motivation, impact and financial-need responses', true],
  ['Recommendation letters', 'Teacher or counselor recommendations where requested', true],
  ['CSS Profile', 'Only for shortlisted universities that require it', needsCss],
  ['FAFSA', 'Only where eligibility and university requirements apply', needsFafsa]];

  return <div className="aid-checklist"><section className="aid-intro"><div><span className="eyebrow">{t("AID PREPARATION")}</span><h2>{t("Prepare for financial aid")}</h2><p>{t("Core documents based on your shortlist and profile. Verify final requirements on each university’s official financial aid page.")}</p></div><div className="aid-profile-summary"><Detail label={t("Budget")} value={money(student?.budget_usd)} /><Detail label={t("Scholarship")} value={student?.scholarship_needed ? t("Needed") : t("Optional")} /><Detail label={t("Shortlisted")} value={data.applications.length} /></div></section><div className="checklist-cards">{checklist.map(([title, description, needed]) => <article key={title} className={needed ? "needed" : ''}><span className="checklist-icon" aria-hidden="true">{needed ? <CheckCircle2 size={20} /> : <Clock3 size={20} />}</span><div><h3>{t(title)}</h3><p>{t(description)}</p></div><span className="checklist-status">{needed ? t("Prepare") : t("If required")}</span></article>)}</div></div>;
}
