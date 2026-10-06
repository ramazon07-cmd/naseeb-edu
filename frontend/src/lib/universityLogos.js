import logos from '../data/universityLogos.json';
import { countryName } from './countries.js';

const normalize = (value) => String(value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\([^)]*\)/g, '').replace(/^the\s+/, '').replace(/[^a-z0-9]/g, '');

// Match catalogue aliases without depending on a university's database ID.
export const universityLogoKey = (name, country) => `${normalize(name)}|${normalize(countryName(country))}`;

export const universityLogoSrc = (university) => logos[universityLogoKey(university.name, university.country)] || '';
