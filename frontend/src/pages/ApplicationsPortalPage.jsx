import { t } from '../i18n';
import { Stat } from '../components/records';
import { ResourceSection } from './ResourceSection';

export function ApplicationsPortalPage({ user, data, query, reload, notify, setPage }) {
  const submitted = data.applications.filter((item) => ['submitted', 'accepted'].includes(item.status)).length;
  return <div className="section-stack student-portal"><div className="stat-grid"><Stat label={t("Universities")} value={data.applications.length} /><Stat label={t("Submitted")} value={submitted} /><Stat label={t("In progress")} value={data.applications.filter((item) => ['shortlisted', 'applying'].includes(item.status)).length} /><Stat label={t("Decisions")} value={data.applications.filter((item) => ['accepted', 'rejected', 'waitlisted'].includes(item.status)).length} /></div><ResourceSection title={t("My university list")} resource="applications" {...{ user, data, query, reload, notify }} /></div>;
}
