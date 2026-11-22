"""Extra privacy rules for the recommendation letter check, run before the text goes to the model.

Besides the student's own names and school (letter_coach.anonymize) these rules replace, by cues and lists and
not by AI: family members', classmates' and staff names ("[Person]"), dates of birth ("[Date of birth]"),
student, passport and personal ID numbers ("[ID]"), and district, town and village names, with a list of
Uzbekistan's regions, districts and cities ("[Place]"). English, Russian and Uzbek (Latin) are covered.

Every function works on the folded copy of the text (letter_coach._fold_chars: NFKC, apostrophes as "'"),
so a position found here is the same position in the real text.
"""
import datetime
import re

PERSON, PLACE, ID, BIRTH = '[Person]', '[Place]', '[ID]', '[Date of birth]'
EXTRA_PLACEHOLDERS = ('Person', 'Place', 'ID', 'Date of birth')

_CAP = 'A-ZА-ЯЁЎҚҒҲ'
_NAME_WORD = rf"[{_CAP}]'?[^\W\d_]{{2,}}(?:-[{_CAP}][^\W\d_]{{2,}})?"
# One to three capitalised words on one line: "Karim", "Nodira Rahimova", "Ирина Петровна Сидорова".
_NAME = rf'(?P<name>{_NAME_WORD}(?:[ \t]+{_NAME_WORD}){{0,2}})'

_EN_CUES = (
    r"father|mother|mom|mum|dad|parents?|stepfather|stepmother|brother|sister|aunt|uncle|grandmother|grandfather|"
    r"grandma|grandpa|cousin|guardian|teacher|tutor|coach|principal|headmaster|headmistress|director|counsell?or|"
    r"colleague|mentor|supervisor|advis[eo]r|professor|instructor|classmates?|friends?|teammates?|roommate|"
    r"deputy|dean|vice[- ]principal"
)
_RU_CUES = (
    r"мам\w*|мать|матер\w+|отец|отц\w+|пап\w*|брат\w*|сестр\w*|бабушк\w*|дедушк\w*|тёт\w*|тет\w*|дяд\w*|опекун\w*|"
    r"родител\w*|учител\w*|преподавател\w*|директор\w*|завуч\w*|тренер\w*|куратор\w*|наставник\w*|руководител\w*|"
    r"одноклассни\w+|друг\w*|подруг\w*|коллег\w*"
)
_UZ_CUES = (
    r"ona\w*|ota\w*|aka\w*|opa\w*|singil\w*|uka\w*|buvi\w*|bobo\w*|xola\w*|amaki\w*|tog'a\w*|amma\w*|"
    r"vasiy\w*|o'qituvchi\w*|ustoz\w*|muallim\w*|domla\w*|direktor\w*|murabbiy\w*|sinfdosh\w*|do'st\w*|dugona\w*|"
    r"hamkasb\w*|rahbar\w*|mudir\w*"
)
_HONORIFIC = r'(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Professor|Mister|Sir)'
_UZ_AFTER = r"opa|aka|xola|amaki|dada|buvi|bobo|domla|ustoz|muallima|muallim|hoji|xonim|janob|o'qituvchi|singil"

_PERSON_PATTERNS = [re.compile(pattern) for pattern in (
    rf"(?i:(?<!\w)(?:{_EN_CUES}|{_RU_CUES}|{_UZ_CUES})(?!\w))[ \t]*[,:\-]?[ \t]*(?i:(?:named|called|по имени|ismli)[ \t]+)?"
    rf"(?:{_HONORIFIC}\.?[ \t]+)?{_NAME}",
    rf"(?<!\w){_HONORIFIC}\.?[ \t]+{_NAME}",
    rf"{_NAME}[ \t]+(?i:{_UZ_AFTER})(?!\w)",
)]

_ID_CUE = (
    r"(?:(?i:(?<!\w)(?:id|number|nomer|raqam\w*|номер|pinfl|jshshir|пинфл|жшшир|passport|паспорт\w*)(?!\w))|№|#)"
)
_ID_PATTERNS = [re.compile(pattern) for pattern in (
    rf"{_ID_CUE}[ \t]*[:=\-]*[ \t]*(?P<name>[A-Z]{{0,3}}[ \t]?\d[\w\-]{{3,}})",
    r"(?<![\w.])(?P<name>\d{14})(?![\w.])",           # PINFL
    r"(?<![\w])(?P<name>[A-Z]{2}[ ]?\d{7})(?![\w])",  # passport series and number
)]

_MONTHS = (
    r"january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec|"
    r"январ\w*|феврал\w*|март\w*|апрел\w*|ма[йяе]|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*|"
    r"yanvar\w*|fevral\w*|mart\w*|aprel\w*|iyun\w*|iyul\w*|avgust\w*|sentabr\w*|sentyabr\w*|oktabr\w*|oktyabr\w*|"
    r"noyabr\w*|dekabr\w*"
)
_DATE = (
    rf"(?:\d{{1,2}}[./-]\d{{1,2}}[./-](?:\d{{4}}|\d{{2}})|\d{{4}}[./-]\d{{1,2}}[./-]\d{{1,2}}|"
    rf"\d{{1,2}}(?:st|nd|rd|th)?[ \t]+(?:of[ \t]+)?(?i:{_MONTHS})\.?,?[ \t]+\d{{4}}|"
    rf"(?i:{_MONTHS})\.?[ \t]+\d{{1,2}}(?:st|nd|rd|th)?,?[ \t]+\d{{4}})"
)
_BIRTH_CUE = (
    r"(?i:(?<!\w)(?:born|dob|d\.o\.b\.?|date of birth|birth date|birthday|tug'ilgan|tavallud|"
    r"родил\w*|дата рождения|рождени\w+)(?!\w))"
)
_BIRTH_AFTER_CUE = re.compile(rf"{_BIRTH_CUE}[^\d\n]{{0,30}}?(?P<name>{_DATE})")
_BIRTH_YEAR = re.compile(rf"{_BIRTH_CUE}[ \t]+(?i:in|в|yilda)?[ \t]*(?P<name>(?:19|20)\d{{2}})(?!\d)")
_ANY_DATE = re.compile(rf"(?P<name>{_DATE})")

_PLACE_NAMES = (
    "Tashkent|Toshkent|Samarkand|Samarqand|Bukhara|Buxoro|Khorezm|Xorazm|Khiva|Xiva|Fergana|Farg'ona|Fargona|"
    "Andijan|Andijon|Namangan|Navoi|Navoiy|Kashkadarya|Qashqadaryo|Karshi|Qarshi|Surkhandarya|Surxondaryo|"
    "Termez|Termiz|Jizzakh|Jizzax|Syrdarya|Sirdaryo|Gulistan|Guliston|Karakalpakstan|Qoraqalpog'iston|Nukus|"
    "Urgench|Urganch|Kokand|Qo'qon|Margilan|Marg'ilon|Chirchik|Chirchiq|Angren|Almalyk|Olmaliq|Shahrisabz|"
    "Denau|Denov|Zarafshan|Bekabad|Bekobod|Chilanzar|Chilonzor|Yunusabad|Yunusobod|Mirzo Ulugbek|"
    "Mirzo Ulug'bek|Shaykhantakhur|Shayxontohur|Yakkasaray|Yakkasaroy|Mirabad|Mirobod|Sergeli|Uchtepa|"
    "Olmazor|Bektemir|Yashnabad|Yashnobod|Zangiota|Qibray|Parkent|Bo'stonliq|Chinoz|Yangiyo'l|Nurafshon|"
    "Kattaqo'rg'on|Urgut|Jomboy|Pastdarg'om|Shofirkon|G'ijduvon|Shahrihon|"
    "Ташкент|Самарканд|Бухара|Хорезм|Хива|Фергана|Андижан|Наманган|Навои|Кашкадарья|Карши|Сурхандарья|Термез|"
    "Джизак|Сырдарья|Гулистан|Каракалпакстан|Нукус|Ургенч|Коканд|Маргилан|Чирчик|Ангрен|Алмалык|Шахрисабз|"
    "Денау|Зарафшан|Бекабад|Чиланзар|Юнусабад|Мирзо Улугбек|Шайхантахур|Яккасарай|Мирабад|Сергели|Учтепа|"
    "Алмазар|Бектемир|Яшнабад|Янгиюль|Нурафшан|Паркент|Чиназ"
)
_PLACE_LIST = re.compile(
    '(?<!\\w)(?P<name>(?:' + '|'.join(
        r'[ \t\-]+'.join(re.escape(part) for part in re.split(r'[ \-]', name)) for name in
        sorted(_PLACE_NAMES.split('|'), key=len, reverse=True)
    ) + ')\\w{0,5})(?!\\w)', re.IGNORECASE,
)
_PLACE_TYPES = (
    r"district|region|oblast|village|town|tumani|tuman|viloyati|viloyat|shahri|qishlog'i|mahallasi|rayoni|"
    r"район\w*|област\w*|село|селе|деревн\w+|посёл\w+|поселок|поселке"
)
_PLACE_PATTERNS = [re.compile(pattern) for pattern in (
    rf"{_NAME}[ \t]+(?i:{_PLACE_TYPES})(?!\w)",
    rf"(?i:(?<!\w)(?:village|town|city|district|region|qishloq\w*|shahar\w*|село|селе|деревн\w+|посёл\w+|"
    rf"поселок|поселке|город\w*)(?:[ \t]+of)?)[ \t]+{_NAME}",
)]


def _spans(pattern, text, placeholder, group='name'):
    return [(m.start(group), m.end(group), placeholder) for m in pattern.finditer(text) if m.group(group)]


def extra_spans(folded):
    """(start, end, placeholder) for every extra private detail found in the folded text."""
    spans = []
    for pattern in _PERSON_PATTERNS:
        spans += _spans(pattern, folded, PERSON)
    for pattern in _ID_PATTERNS:
        spans += _spans(pattern, folded, ID)
    spans += _spans(_BIRTH_AFTER_CUE, folded, BIRTH) + _spans(_BIRTH_YEAR, folded, BIRTH)
    year = datetime.date.today().year
    for match in _ANY_DATE.finditer(folded):
        found = re.findall(r'\d{4}', match.group('name'))
        if found and year - 25 <= int(found[-1]) <= year - 10:
            spans.append((match.start('name'), match.end('name'), BIRTH))
    spans += _spans(_PLACE_LIST, folded, PLACE)
    for pattern in _PLACE_PATTERNS:
        spans += _spans(pattern, folded, PLACE)
    return spans


def originals(folded):
    """{placeholder: set of the texts it replaced}, to map a quote back to the real letter."""
    found = {}
    for start, end, placeholder in extra_spans(folded):
        found.setdefault(placeholder, set()).add(folded[start:end])
    return found
