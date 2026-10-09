import { formatNumberLocale, t } from '../i18n';

export const QS_INDICATORS = [
  ['AR', 'Academic reputation'],
  ['ER', 'Employer reputation'],
  ['FSR', 'Faculty–student ratio score'],
  ['CPF', 'Citations per faculty'],
  ['IFR', 'International faculty score'],
  ['ISR', 'International students score'],
  ['IRN', 'International research network'],
  ['EO', 'Employment outcomes'],
  ['SUS', 'Sustainability'],
];

export const QS_TABLE_COLUMNS = [
  ['overall', 'QS score'], ['AR', 'Academic reputation'], ['ER', 'Employer reputation'],
  ['CPF', 'Citations per faculty'], ['ISR', 'International students score'], ['SUS', 'Sustainability'],
];

export const QS_CLASSIFICATIONS = [
  ['region', 'Region', { Americas: 'Americas', Europe: 'Europe', Asia: 'Asia', Africa: 'Africa', Oceania: 'Oceania' }],
  ['size', 'Institution size', { S: 'Small', M: 'Medium', L: 'Large', XL: 'Extra large' }],
  ['focus', 'Subject range', { FC: 'Fully comprehensive', CO: 'Comprehensive', FO: 'Focused', SP: 'Specialist institution' }],
  ['research', 'Research intensity', { VH: 'Very high', HI: 'High', MD: 'Medium', LO: 'Low' }],
  ['status', 'Institution status', { Public: 'Public university', 'Private not for Profit': 'Private nonprofit', 'Private for Profit': 'Private for-profit' }],
];

export function qsClassification(key, value) {
  if (!value) return '—';
  const labels = QS_CLASSIFICATIONS.find(([field]) => field === key)?.[2];
  return t(labels?.[value] || value);
}

export function qsScoreText(value) {
  return typeof value === 'number' && Number.isFinite(value) ? formatNumberLocale(value) : '—';
}

export function qsScore(data, code) {
  return code === 'overall' ? data?.overall_score : data?.indicators?.[code]?.score;
}

// QS rows carry their own status, and a blank one is unknown: institution_type
// then only holds the model default. Other rows show their institution type.
export function institutionStatus(university, typeLabel) {
  const data = university?.qs_data;
  if (data && 'status' in data) return data.status ? qsClassification('status', data.status) : '';
  return university?.institution_type ? typeLabel(university.institution_type) : '';
}
