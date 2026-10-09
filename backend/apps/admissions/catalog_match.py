"""Finding a catalogue university by a name another source spells differently."""
import re

from .countries import country_key

# QS spellings of curated universities (catalog_v1) that university_key cannot match.
NAME_ALIASES = {'University of Michigan-Ann Arbor': 'University of Michigan'}


def university_key(name, country):
    """'Massachusetts Institute of Technology (MIT)' matches '... Technology', and
    'Nanyang Technological University, Singapore' matches '... University' in Singapore."""
    value = re.sub(r'\s*\([^)]*\)', '', NAME_ALIASES.get(name, name)).strip().lower()
    value = re.sub(r'^the\s+', '', value).removesuffix(f', {country.strip().lower()}')
    return value, country_key(country)
