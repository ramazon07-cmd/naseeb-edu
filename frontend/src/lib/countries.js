// One key per country, whichever way a profile or a catalogue spells it
// ('US', 'USA', 'United States'). Mirrors backend apps/admissions/countries.py.
const COUNTRY_ALIASES = {
  usa: 'us', 'united states': 'us', 'united states of america': 'us',
  'united kingdom': 'uk', 'great britain': 'uk', gb: 'uk',
  'türkiye': 'turkey',
  'viet nam': 'vietnam',
  hk: 'hong kong', 'hong kong sar': 'hong kong', 'hong kong sar, china': 'hong kong',
  'mainland china': 'china', 'china (mainland)': 'china'
};

// The catalogue's spelling of each aliased country.
const COUNTRY_NAMES = { us: 'United States', uk: 'United Kingdom', turkey: 'Turkey', vietnam: 'Vietnam', 'hong kong': 'Hong Kong', china: 'China' };

export function countryKey(value) {
  const name = String(value || '').trim().toLowerCase();
  return COUNTRY_ALIASES[name] || name;
}

// One display name per country; a country without aliases keeps its own spelling.
export const countryName = (value) => COUNTRY_NAMES[countryKey(value)] || String(value || '').trim();
