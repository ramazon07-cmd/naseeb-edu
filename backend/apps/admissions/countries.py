"""One key per country, whichever way a profile or a catalogue spells it.

Students pick target countries from onboarding.COUNTRIES ('US', 'UK', ...);
catalogue rows say 'United States', 'USA' or 'Türkiye'. Both sides compare
through ``country_key``.
"""

COUNTRY_ALIASES = {
    'usa': 'us', 'united states': 'us', 'united states of america': 'us',
    'united kingdom': 'uk', 'great britain': 'uk', 'gb': 'uk',
    'türkiye': 'turkey',
    'viet nam': 'vietnam',
    'hk': 'hong kong', 'hong kong sar': 'hong kong', 'hong kong sar, china': 'hong kong',
    'mainland china': 'china', 'china (mainland)': 'china',
}

# The catalogue's spelling of each aliased country (frontend lib/countries.js COUNTRY_NAMES).
COUNTRY_NAMES = {'us': 'United States', 'uk': 'United Kingdom', 'turkey': 'Turkey', 'vietnam': 'Vietnam', 'hong kong': 'Hong Kong', 'china': 'China'}


def country_key(name):
    value = (name or '').strip().lower()
    return COUNTRY_ALIASES.get(value, value)


def country_name(name):
    """One display name per country; a country without aliases keeps its own spelling."""
    return COUNTRY_NAMES.get(country_key(name)) or (name or '').strip()


def country_spellings(name):
    """Every lower-case spelling ``country_key`` treats as the same country as ``name``."""
    key = country_key(name)
    return {key, *(alias for alias, value in COUNTRY_ALIASES.items() if value == key)}
