import logos from '../data/universityLogos.json';

const normalize = (value) => String(value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\([^)]*\)/g, '').replace(/^the\s+/, '').replace(/[^a-z0-9]/g, '');
const countryAliases = { usa: 'unitedstates', us: 'unitedstates', uk: 'unitedkingdom' };

// Match catalogue aliases without depending on a university's database ID.
export const universityLogoKey = (name, country) => {
  const countryKey = normalize(country);
  return `${normalize(name)}|${countryAliases[countryKey] || countryKey}`;
};

export const universityLogoSrc = (university) => logos[universityLogoKey(university.name, university.country)] || '';
