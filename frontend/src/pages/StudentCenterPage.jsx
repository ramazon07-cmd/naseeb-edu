import { useState } from 'react';
import { PortalTabs } from '../components/forms';
import { Award, Briefcase, FolderGit2, Mail, Sparkles, Trophy } from 'lucide-react';
import { t } from '../i18n';
import { StudentOverview } from './StudentsPage';
import { ownStudent } from '../lib/labels';
import { ProfileSections } from '../components/ProfileSections';
import { AddMenu } from '../components/AddMenu';
import { ResourceForm, ResourceSection } from './ResourceSection';
import { DocumentsPage } from './DocumentsPage';

// Each tab with several record types gets one "Add" chooser instead of an
// Add button per card. [resource, card title, menu label, hint, form title, empty text, empty link, icon]
const TAB_RESOURCES = {
  portfolio: [
    ['projects', 'Projects', 'Project', 'Something you built or organised', 'Add a project', 'No projects yet.', 'Add your first project', FolderGit2],
    ['internships', 'Internships', 'Internship', 'Work experience at an organisation', 'Add an internship', 'No internships yet.', 'Add your first internship', Briefcase],
  ],
  activities: [
    ['activities', 'Activities', 'Activity', 'A club, sport, volunteering or hobby', 'Add an activity', 'No activities yet.', 'Add your first activity', Sparkles],
    ['honors', 'Honors', 'Honor', 'An award or prize you received', 'Add an honor', 'No honors yet.', 'Add your first honor', Award],
    ['achievements', 'Achievements', 'Achievement', 'A result you are proud of', 'Add an achievement', 'No achievements yet.', 'Add your first achievement', Trophy],
    ['recommendations', 'Recommendation letters', 'Recommendation letter', 'A teacher or mentor who writes for you', 'Add a recommendation letter', 'No recommendation letters yet.', 'Add your first recommendation letter', Mail],
  ],
};

function ResourceTab({ tab, user, data, query, reload, notify }) {
  const [creating, setCreating] = useState(null);
  const entries = TAB_RESOURCES[tab];
  const current = entries.find(([resource]) => resource === creating);
  const section = ([resource, title, , , , emptyText, emptyAction]) => <ResourceSection key={resource} title={t(title)} resource={resource} onAdd={() => setCreating(resource)} emptyText={emptyText} emptyAction={t(emptyAction)} {...{ user, data, query, reload, notify }} />;
  const pairs = [];
  for (let i = 0; i < entries.length; i += 2) pairs.push(entries.slice(i, i + 2));
  return <div className="section-stack">
    <div className="student-tab-toolbar">
      <AddMenu items={entries.map(([key, , label, hint, , , , icon]) => ({ key, label: t(label), hint: t(hint), icon }))} onSelect={setCreating} />
    </div>
    {pairs.map((pair) => <div className="split-grid" key={pair[0][0]}>{pair.map(section)}</div>)}
    {current && <ResourceForm resource={current[0]} title={t(current[4])} data={data} user={user} onClose={() => setCreating(null)} onSaved={() => { setCreating(null); reload(); }} notify={notify} />}
  </div>;
}

// The open tab lives in the URL (/student-center/documents), so it survives a
// reload and back/forward. Profile answers are edited in place on their cards;
// ?edit=<section> opens one card in edit mode.
export function StudentCenterPage({ user, data, query, reload, notify, tab = 'overview', onTab, editSection = null, onEditDone }) {
  const student = ownStudent(data);
  const sections = { reload, notify, onEditDone, student, data };
  return <div className="section-stack student-portal">
    <div className="student-center-head">
      <PortalTabs active={tab} onChange={onTab} items={[["overview", "Overview"], ["academics", "Academics"], ["portfolio", "Portfolio"], ["activities", "Activities & honors"], ["documents", "Documents"]]} />
    </div>
    {tab === 'overview' && <StudentOverview student={student} data={data} profile={<ProfileSections {...sections} editSection={editSection} onOpenRecords={() => onTab('activities')} />} />}
    {tab === 'academics' && <div className="section-stack"><ProfileSections {...sections} sections={['academics', 'tests']} showReadiness={false} /><ResourceSection title={t("Research & academic work")} resource="researches" {...{ user, data, query, reload, notify }} /></div>}
    {TAB_RESOURCES[tab] && <ResourceTab key={tab} tab={tab} {...{ user, data, query, reload, notify }} />}
    {tab === 'documents' && <DocumentsPage {...{ user, data, query, reload, notify }} />}
  </div>;
}
