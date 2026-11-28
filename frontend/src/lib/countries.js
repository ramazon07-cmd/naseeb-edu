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

const COUNTRY_CODES = {
  us: 'US', uk: 'GB', uzbekistan: 'UZ', kazakhstan: 'KZ', kyrgyzstan: 'KG', tajikistan: 'TJ', turkmenistan: 'TM', russia: 'RU', ukraine: 'UA',
  canada: 'CA', mexico: 'MX', brazil: 'BR', argentina: 'AR', chile: 'CL', france: 'FR', germany: 'DE', italy: 'IT', spain: 'ES', portugal: 'PT',
  switzerland: 'CH', austria: 'AT', netherlands: 'NL', belgium: 'BE', luxembourg: 'LU', ireland: 'IE', iceland: 'IS', norway: 'NO', sweden: 'SE',
  finland: 'FI', denmark: 'DK', poland: 'PL', czechia: 'CZ', 'czech republic': 'CZ', hungary: 'HU', romania: 'RO', bulgaria: 'BG', greece: 'GR',
  estonia: 'EE', latvia: 'LV', lithuania: 'LT', turkey: 'TR', armenia: 'AM', georgia: 'GE', azerbaijan: 'AZ', israel: 'IL', qatar: 'QA',
  'united arab emirates': 'AE', uae: 'AE', 'saudi arabia': 'SA', kuwait: 'KW', bahrain: 'BH', oman: 'OM', jordan: 'JO', egypt: 'EG', morocco: 'MA',
  'south africa': 'ZA', kenya: 'KE', nigeria: 'NG', rwanda: 'RW', ghana: 'GH', india: 'IN', pakistan: 'PK', bangladesh: 'BD', 'sri lanka': 'LK',
  nepal: 'NP', china: 'CN', japan: 'JP', 'south korea': 'KR', korea: 'KR', singapore: 'SG', malaysia: 'MY', indonesia: 'ID', thailand: 'TH',
  vietnam: 'VN', philippines: 'PH', 'hong kong': 'HK', taiwan: 'TW', australia: 'AU', 'new zealand': 'NZ', mongolia: 'MN', cyprus: 'CY', malta: 'MT',
};

// The flag emoji for a country name ('' when unknown, so nothing odd is shown). Decorative: always pair it with the name.
export function countryFlag(value) {
  const code = COUNTRY_CODES[countryKey(value)];
  return code ? String.fromCodePoint(...[...code].map((letter) => 0x1f1a5 + letter.charCodeAt(0))) : '';
}
