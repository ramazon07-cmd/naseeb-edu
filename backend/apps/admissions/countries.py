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


def country_key(name):
    value = (name or '').strip().lower()
    return COUNTRY_ALIASES.get(value, value)
