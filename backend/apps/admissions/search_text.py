"""Accent-, script- and country-spelling-insensitive university search.

``University.search_text`` stores the name, city and every spelling of the
country (``countries.country_spellings``), folded: lower case, accents removed
("São Paulo" -> "sao paulo"). A search term is folded the same way and, when
it is Cyrillic, also transliterated to Latin ("Гарвард" -> "harvard"), so a plain
``contains`` matches on SQLite and PostgreSQL alike.
"""
import itertools
import unicodedata

from .countries import COUNTRY_NAMES, country_key, country_spellings

# Letters NFKD does not decompose into a base letter and a mark.
_SPECIAL = str.maketrans({
    'ı': 'i', 'ø': 'o', 'ł': 'l', 'đ': 'd', 'ð': 'd', 'þ': 'th', 'ß': 'ss', 'æ': 'ae', 'œ': 'oe',
    '‘': None, '’': None, 'ʻ': None, 'ʼ': None, "'": None, '`': None,
})

# Russian and Uzbek Cyrillic -> Latin. Several spellings where names borrow
# differently: Г is H in "Гарвард" (Harvard) but G in "Гонконг"; Я is "ia" in
# "Колумбия" (Columbia), КС is X in "Оксфорд". The first spelling is the usual one.
_CYRILLIC = {
    'а': ('a',), 'б': ('b',), 'в': ('v', 'w'), 'г': ('g', 'h'), 'д': ('d',), 'е': ('e',), 'ё': ('yo', 'e'),
    'ж': ('zh', 'j'), 'з': ('z',), 'и': ('i',), 'й': ('y', 'i'), 'к': ('k', 'c'), 'л': ('l',), 'м': ('m',),
    'н': ('n',), 'о': ('o',), 'п': ('p',), 'р': ('r',), 'с': ('s',), 'т': ('t',), 'у': ('u',), 'ф': ('f',),
    'х': ('kh', 'h', 'x'), 'ц': ('ts', 'c'), 'ч': ('ch',), 'ш': ('sh',), 'щ': ('shch',), 'ъ': ('',), 'ы': ('y',),
    'ь': ('',), 'э': ('e',), 'ю': ('yu', 'u'), 'я': ('ya', 'a'),
    'ў': ('o',), 'қ': ('q', 'k'), 'ғ': ('g',), 'ҳ': ('h',), 'і': ('i',), 'ї': ('yi',), 'є': ('ye',),
    'кс': ('ks', 'x'),
}
MAX_VARIANTS = 32


def fold(text):
    decomposed = unicodedata.normalize('NFKD', str(text or '').casefold())
    return ''.join(char for char in decomposed if not unicodedata.combining(char)).translate(_SPECIAL)


def university_search_text(name, city, country):
    spellings = {*country_spellings(country), COUNTRY_NAMES.get(country_key(country), ''), country}
    parts = [name, city, *sorted(spellings)]
    return '\n'.join(folded for folded in dict.fromkeys(fold(part).strip() for part in parts) if folded)


def _transliterations(term):
    options, index = [], 0
    while index < len(term):
        size = 2 if term[index:index + 2] in _CYRILLIC else 1
        options.append(_CYRILLIC.get(term[index:index + size], (term[index:index + size],)))
        index += size
    return (''.join(choice) for choice in itertools.product(*options))


def search_variants(term):
    """The folded forms of one search term that ``search_text`` may contain."""
    lowered = str(term).casefold()
    variants = [fold(lowered)]
    if any(char in _CYRILLIC for char in lowered):
        variants += [fold(text) for text in itertools.islice(_transliterations(lowered), MAX_VARIANTS)]
    return [variant for variant in dict.fromkeys(variants) if variant]
