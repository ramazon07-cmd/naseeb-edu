"""The 55 QS subjects as our standard major list, and the words that map a student's major to them.

A student writes a target major as free text ("Computer Science, Business", "информатика",
"kompyuter injiniringi"). ``subjects_for_major`` turns it into QS subject codes by fixed keyword
rules: no AI, the same text always gives the same codes. A text with no subject keyword falls back to
a broad area when it names one ("Engineering"), else to nothing.
"""
import re

# code -> (name, area code), from the QS 2026 methodology sheet; the five AREA_* rows are the broad areas.
SUBJECTS = {
    'AREA_ART': ('Arts & Humanities', 'AREA_ART'),
    'ARC01': ('Archaeology', 'AREA_ART'),
    'ARC02': ('Architecture / Built Environment', 'AREA_ART'),
    'ART01': ('Art & Design', 'AREA_ART'),
    'CLA01': ('Classics & Ancient History', 'AREA_ART'),
    'ENG07': ('English Language & Literature', 'AREA_ART'),
    'HIS01': ('History', 'AREA_ART'),
    'HIS02': ('History of Art', 'AREA_ART'),
    'LIN01': ('Linguistics', 'AREA_ART'),
    'MOD01': ('Modern Languages', 'AREA_ART'),
    'MUS01': ('Music', 'AREA_ART'),
    'PER01': ('Performing Arts', 'AREA_ART'),
    'PHI01': ('Philosophy', 'AREA_ART'),
    'THE01': ('Theology, Divinity & Religious Studies', 'AREA_ART'),
    'AREA_ENG': ('Engineering & Technology', 'AREA_ENG'),
    'COM02': ('Computer Science & Information Systems', 'AREA_ENG'),
    'DAT01': ('Data Science and Artificial Intelligence', 'AREA_ENG'),
    'ENG01': ('Engineering - Chemical', 'AREA_ENG'),
    'ENG02': ('Engineering - Civil & Structural', 'AREA_ENG'),
    'ENG03': ('Engineering - Electrical & Electronic', 'AREA_ENG'),
    'ENG05': ('Engineering - Mechanical, Aeronautical & Manufacturing', 'AREA_ENG'),
    'ENG06': ('Engineering - Mineral & Mining', 'AREA_ENG'),
    'PET01': ('Petroleum Engineering', 'AREA_ENG'),
    'AREA_LIF': ('Life Sciences & Medicine', 'AREA_LIF'),
    'AGR01': ('Agriculture & Forestry', 'AREA_LIF'),
    'ANA01': ('Anatomy & Physiology', 'AREA_LIF'),
    'BIO01': ('Biological Sciences', 'AREA_LIF'),
    'DEN01': ('Dentistry', 'AREA_LIF'),
    'MED01': ('Medicine', 'AREA_LIF'),
    'NUR01': ('Nursing', 'AREA_LIF'),
    'PHA01': ('Pharmacy & Pharmacology', 'AREA_LIF'),
    'PSY01': ('Psychology', 'AREA_LIF'),
    'VET01': ('Veterinary Science', 'AREA_LIF'),
    'AREA_NAT': ('Natural Sciences', 'AREA_NAT'),
    'CHE01': ('Chemistry', 'AREA_NAT'),
    'EAR01': ('Earth & Marine Sciences', 'AREA_NAT'),
    'ENV01': ('Environmental Sciences', 'AREA_NAT'),
    'GEO01': ('Geography', 'AREA_NAT'),
    'GEO02': ('Geology', 'AREA_NAT'),
    'GEO03': ('Geophysics', 'AREA_NAT'),
    'MET01': ('Materials Science', 'AREA_NAT'),
    'MAT01': ('Mathematics', 'AREA_NAT'),
    'PHY01': ('Physics & Astronomy', 'AREA_NAT'),
    'AREA_SOC': ('Social Sciences & Management', 'AREA_SOC'),
    'ACC01': ('Accounting & Finance', 'AREA_SOC'),
    'ANT01': ('Anthropology', 'AREA_SOC'),
    'BUS01': ('Business & Management Studies', 'AREA_SOC'),
    'COM01': ('Communication & Media Studies', 'AREA_SOC'),
    'DEV01': ('Development Studies', 'AREA_SOC'),
    'ECO01': ('Economics & Econometrics', 'AREA_SOC'),
    'EDU01': ('Education', 'AREA_SOC'),
    'HOS01': ('Hospitality & Leisure Management', 'AREA_SOC'),
    'LAW01': ('Law', 'AREA_SOC'),
    'LIB01': ('Library & Information Management', 'AREA_SOC'),
    'MAR01': ('Marketing', 'AREA_SOC'),
    'POL01': ('Politics & International Studies', 'AREA_SOC'),
    'SOC01': ('Social Policy & Administration', 'AREA_SOC'),
    'SOC03': ('Sociology', 'AREA_SOC'),
    'SPO01': ('Sports-related Subjects', 'AREA_SOC'),
    'STA01': ('Statistics & Operational Research', 'AREA_SOC'),
}
AREAS = tuple(code for code in SUBJECTS if code.startswith('AREA_'))

# The indicators QS scores a subject by, in the order of its columns, and each subject's weights for them
# (0 = not used, so the score is not published). From the 'methodology' sheet; tests check this table against
# the snapshot (catalog_data/qs_subject_rankings_2026.json), which carries the same weights.
INDICATORS = ('academic', 'employer', 'citations', 'h_index', 'irn')
SUBJECT_WEIGHTS = {
    'AREA_ART': (0.6, 0.2, 0.075, 0.075, 0.05),
    'ARC01': (0.7, 0.1, 0.1, 0.1, 0),
    'ARC02': (0.7, 0.1, 0.1, 0.1, 0),
    'ART01': (0.9, 0.1, 0, 0, 0),
    'CLA01': (0.9, 0.1, 0, 0, 0),
    'ENG07': (0.8, 0.1, 0.1, 0, 0),
    'HIS01': (0.6, 0.1, 0.15, 0.15, 0),
    'HIS02': (0.9, 0.1, 0, 0, 0),
    'LIN01': (0.8, 0.1, 0.05, 0.05, 0),
    'MOD01': (0.7, 0.3, 0, 0, 0),
    'MUS01': (0.8, 0.2, 0, 0, 0),
    'PER01': (0.8, 0.2, 0, 0, 0),
    'PHI01': (0.75, 0.05, 0.1, 0.1, 0),
    'THE01': (0.7, 0.1, 0.1, 0.1, 0),
    'AREA_ENG': (0.4, 0.3, 0.1, 0.1, 0.1),
    'COM02': (0.4, 0.3, 0.125, 0.125, 0.05),
    'DAT01': (0.4, 0.3, 0.15, 0.15, 0),
    'ENG01': (0.4, 0.3, 0.125, 0.125, 0.05),
    'ENG02': (0.4, 0.3, 0.15, 0.15, 0),
    'ENG03': (0.4, 0.3, 0.125, 0.125, 0.05),
    'ENG05': (0.4, 0.3, 0.125, 0.125, 0.05),
    'ENG06': (0.4, 0.3, 0.15, 0.15, 0),
    'PET01': (0.4, 0.3, 0.15, 0.15, 0),
    'AREA_LIF': (0.4, 0.1, 0.2, 0.2, 0.1),
    'AGR01': (0.5, 0.1, 0.15, 0.15, 0.1),
    'ANA01': (0.4, 0.1, 0.25, 0.25, 0),
    'BIO01': (0.4, 0.1, 0.2, 0.2, 0.1),
    'DEN01': (0.3, 0.1, 0.3, 0.3, 0),
    'MED01': (0.4, 0.1, 0.2, 0.2, 0.1),
    'NUR01': (0.3, 0.1, 0.3, 0.3, 0),
    'PHA01': (0.4, 0.1, 0.2, 0.2, 0.1),
    'PSY01': (0.4, 0.2, 0.15, 0.15, 0.1),
    'VET01': (0.3, 0.1, 0.3, 0.3, 0),
    'AREA_NAT': (0.4, 0.2, 0.15, 0.15, 0.1),
    'CHE01': (0.4, 0.2, 0.15, 0.15, 0.1),
    'EAR01': (0.4, 0.1, 0.2, 0.2, 0.1),
    'ENV01': (0.4, 0.1, 0.225, 0.225, 0.05),
    'GEO01': (0.6, 0.1, 0.15, 0.15, 0),
    'GEO02': (0.3, 0.1, 0.25, 0.25, 0.1),
    'GEO03': (0.3, 0.1, 0.25, 0.25, 0.1),
    'MET01': (0.4, 0.1, 0.2, 0.2, 0.1),
    'MAT01': (0.4, 0.2, 0.15, 0.15, 0.1),
    'PHY01': (0.4, 0.2, 0.15, 0.15, 0.1),
    'AREA_SOC': (0.5, 0.3, 0.075, 0.075, 0.05),
    'ACC01': (0.5, 0.3, 0.1, 0.1, 0),
    'ANT01': (0.7, 0.1, 0.1, 0.1, 0),
    'BUS01': (0.5, 0.3, 0.1, 0.1, 0),
    'COM01': (0.5, 0.1, 0.2, 0.2, 0),
    'DEV01': (0.6, 0.1, 0.15, 0.15, 0),
    'ECO01': (0.4, 0.2, 0.2, 0.2, 0),
    'EDU01': (0.5, 0.1, 0.2, 0.2, 0),
    'HOS01': (0.45, 0.5, 0.05, 0, 0),
    'LAW01': (0.5, 0.3, 0.05, 0.15, 0),
    'LIB01': (0.7, 0.1, 0.15, 0.05, 0),
    'MAR01': (0.5, 0.3, 0.1, 0.1, 0),
    'POL01': (0.5, 0.3, 0.1, 0.1, 0),
    'SOC01': (0.7, 0.2, 0.1, 0, 0),
    'SOC03': (0.7, 0.1, 0.05, 0.15, 0),
    'SPO01': (0.6, 0.1, 0.15, 0.15, 0),
    'STA01': (0.5, 0.1, 0.2, 0.2, 0),
}


def subject_indicators(code):
    """``[(indicator, weight)]`` the subject is scored by, in column order; [] for an unknown code."""
    return [(name, weight) for name, weight in zip(INDICATORS, SUBJECT_WEIGHTS.get(code, ())) if weight]

# Keywords per subject in English, Russian and Uzbek (Latin). A keyword matches from the start of a
# word, so 'информатик' also finds 'информатика' and 'kompyuter' finds 'kompyuter injiniringi'.
# A trailing '$' means the whole word only ('ai$', 'art$').
KEYWORDS = {
    'ARC01': ('archaeolog', 'археолог', 'arxeolog'),
    'ARC02': ('architect', 'urban planning', 'urbanism', 'interior design', 'архитект', 'градостроител', 'arxitektur', 'shaharsozlik'),
    'ART01': ('art$', 'arts$', 'fine art', 'graphic design', 'fashion', 'illustration', 'animation', 'design', 'дизайн',
              'искусств', 'живопис', 'график', 'dizayn', "san'at", 'rassomlik', 'grafika'),
    'CLA01': ('classics', 'classical', 'ancient history', 'latin$', 'античн', 'классическ', 'antik'),
    'ENG07': ('literature', 'english language', 'creative writing', 'английск', 'литератур', 'filolog', 'adabiyot',
              'ingliz tili', 'philology', 'филолог'),
    'HIS01': ('history', 'истори', 'tarix'),
    'HIS02': ('history of art', 'art history', 'museum', 'искусствовед', 'san\'atshunos'),
    'LIN01': ('linguist', 'translation', 'translator', 'лингвист', 'перевод', 'lingvist', 'tarjima'),
    'MOD01': ('modern languages', 'foreign language', 'german studies', 'chinese language', 'korean language',
              'иностранн', 'востоковед', 'xorijiy til', 'sharqshunos'),
    'MUS01': ('music', 'musician', 'composition', 'музык', 'musiqa', 'kompozitor'),
    'PER01': ('performing art', 'theatre', 'theater', 'drama', 'acting', 'dance', 'film$', 'cinema', 'театр', 'актер',
              'актёр', 'кино', 'танц', 'teatr', 'aktyor', 'kino', 'raqs'),
    'PHI01': ('philosoph', 'ethics', 'философ', 'falsafa'),
    'THE01': ('theolog', 'divinity', 'religio', 'islamic studies', 'islamic', 'богослов', 'религиовед', 'религи',
              'ислам', 'din shunos', 'dinshunos', 'diniy', 'islom'),
    'COM02': ('computer', 'software', 'programming', 'programmer', 'informatics', 'information system',
              'information technolog', 'cybersecurity', 'cyber security', 'web development', 'cs$', 'it$', 'cse$',
              'компьютер', 'программ', 'информатик', 'информацион', 'кибербезопасн', 'айти', 'kompyuter', 'dasturlash',
              'dasturchi', 'dasturiy', 'informatika', 'axborot', 'kiberxavfsizlik'),
    'DAT01': ('data science', 'data scien', 'data analy', 'artificial intelligence', 'machine learning', 'big data',
              'ai$', 'ml$', 'deep learning', 'data engineering', 'наука о данных', 'анализ данных', 'данных',
              'искусственный интеллект', 'машинное обучение', "sun'iy intellekt", "ma'lumotlar", 'malumotlar',
              'sun\'iy', 'mashinali o\'qitish'),
    'ENG01': ('chemical engineering', 'chemical$', 'process engineering', 'химическая технолог', 'химическая инженер',
              'химическое', 'kimyoviy muhandis', 'kimyo texnolog'),
    'ENG02': ('civil', 'structural', 'construction', 'строительств', 'гражданск', 'qurilish', 'fuqaro muhandis'),
    'ENG03': ('electrical', 'electronic', 'electric$', 'telecommunication', 'mechatronic', 'robotic', 'automation',
              'электротех', 'электрон', 'электр', 'телекоммуникац', 'робот', 'автоматизац', 'elektr', 'telekommunikats',
              'avtomatlashtirish'),
    'ENG05': ('mechanical', 'aeronautic', 'aerospace', 'aviation', 'automotive', 'manufacturing', 'industrial engineering',
              'механик', 'машиностроен', 'аэрокосмич', 'авиа', 'автомобил', 'производств', 'mexanik', 'mashinasozlik',
              'aviatsiya', 'avtomobil'),
    'ENG06': ('mining', 'mineral', 'metallurg', 'горн', 'металлург', 'konchilik', 'tog\' ish', 'tog\'-kon', 'metallurgiya'),
    'PET01': ('petroleum', 'oil and gas', 'oil & gas', 'нефт', 'neft', 'gaz$'),
    'AGR01': ('agricultur', 'agronom', 'forestry', 'horticultur', 'food science', 'сельск', 'агроном', 'лесн',
              'qishloq', 'agrar', 'o\'rmon', 'oziq-ovqat'),
    'ANA01': ('anatomy', 'physiolog', 'анатом', 'физиолог', 'anatomiya', 'fiziologiya'),
    'BIO01': ('biolog', 'biotech', 'biomedical', 'biochem', 'genetic', 'microbiolog', 'neuroscien', 'molecular',
              'биолог', 'биотех', 'биохим', 'генетик', 'микробиолог', 'biologiya', 'biotexnolog', 'biokimyo', 'genetika'),
    'DEN01': ('dentist', 'dental', 'stomatolog', 'стоматолог', 'зубн', 'stomatologiya', 'tish'),
    'MED01': ('medicine', 'medical', 'premed', 'pre-med', 'surgery', 'surgeon', 'doctor', 'physician', 'public health',
              'health science', 'медицин', 'лечебн', 'врач', 'хирург', 'здравоохран', 'tibbiyot', 'shifokor', 'davolash',
              'jarroh', 'sog\'liqni saqlash'),
    'NUR01': ('nursing', 'nurse', 'midwif', 'медсестр', 'сестринск', 'hamshira', 'hamshiralik'),
    'PHA01': ('pharmac', 'pharma$', 'фармац', 'фармаколог', 'farmatsevt', 'farmakolog', 'farmatsiya'),
    'PSY01': ('psycholog', 'psychiatr', 'cognitive science', 'психолог', 'психиатр', 'psixolog', 'psixiatr', 'psichology'),
    'VET01': ('veterinar', 'animal science', 'ветеринар', 'zootexn', 'chorvachilik'),
    'CHE01': ('chemistry', 'chemist', 'химия', 'химик', 'хими', 'kimyo'),
    'EAR01': ('earth science', 'marine', 'oceanograph', 'meteorolog', 'atmospheric', 'науки о земле', 'океанолог',
              'метеоролог', 'yer fanlari', 'okeanolog', 'meteorologiya'),
    'ENV01': ('environment', 'ecolog', 'sustainab', 'climate', 'окружающ', 'эколог', 'устойчив', 'климат', 'atrof-muhit',
              'ekolog', 'iqlim'),
    'GEO01': ('geograph', 'географ', 'geografiya'),
    'GEO02': ('geolog', 'геолог', 'geologiya'),
    'GEO03': ('geophysic', 'геофиз', 'geofizika'),
    'MET01': ('materials', 'nanotech', 'metallurgical', 'материаловед', 'нанотех', 'materialshunos', 'nanotexnolog'),
    'MAT01': ('mathematic', 'math$', 'maths$', 'applied math', 'математик', 'matematik'),
    'PHY01': ('physics', 'astronom', 'astrophysic', 'physic$', 'физик', 'астроном', 'astrofizika', 'fizika'),
    'ACC01': ('accounting', 'accountant', 'finance', 'financial', 'banking', 'audit', 'actuar', 'investment', 'бухгалтер',
              'финанс', 'банковск', 'аудит', 'актуар', 'инвестиц', 'buxgalter', 'moliya', 'bank ishi', 'bankchilik',
              'investitsiya'),
    'ANT01': ('anthropolog', 'ethnolog', 'антрополог', 'этнолог', 'antropolog', 'etnolog'),
    'BUS01': ('business', 'management', 'entrepreneur', 'administration', 'mba$', 'commerce', 'hr$', 'human resources',
              'logistics', 'supply chain', 'бизнес', 'менеджмент', 'предпринимател', 'управление', 'коммерц', 'логистик',
              'biznes', 'menejment', 'tadbirkor', 'boshqaruv', 'logistika', 'tijorat'),
    'COM01': ('communication', 'media', 'journalis', 'public relations', 'pr$', 'broadcast', 'коммуникац', 'медиа',
              'журналист', 'связи с общественн', 'kommunikats', 'jurnalist', 'ommaviy axborot'),
    'DEV01': ('development studies', 'international development', 'развити', 'taraqqiyot', 'rivojlanish'),
    'ECO01': ('econom', 'econometric', 'экономик', 'экономи', 'iqtisod'),
    'EDU01': ('education', 'teaching', 'teacher', 'pedagog', 'образован', 'педагог', 'учител', 'преподав', 'pedagogika',
              "ta'lim", 'talim', "o'qituvchi", 'oqituvchi'),
    'HOS01': ('hospitality', 'tourism', 'hotel', 'leisure', 'culinary', 'гостеприим', 'туризм', 'гостиничн', 'turizm',
              'mehmonxona', 'mehmondo'),
    'LAW01': ('law$', 'laws$', 'legal', 'jurisprudence', 'lawyer', 'юрис', 'право', 'правов', 'huquq', 'yurist'),
    'LIB01': ('library', 'librarian', 'information management', 'archival', 'библиотек', 'kutubxona', 'arxiv'),
    'MAR01': ('marketing', 'advertising', 'brand', 'маркетинг', 'реклам', 'reklama'),
    'POL01': ('politic', 'political', 'international relations', 'international studies', 'diplomacy', 'government',
              'public policy', 'политолог', 'политик', 'международные отношения', 'дипломат', 'государственн',
              'siyosat', 'xalqaro munosabat', 'diplomatiya', 'davlat boshqaruv', 'politolog'),
    'SOC01': ('social policy', 'social work', 'public administration', 'social administration', 'социальная работа',
              'социальная политика', 'ijtimoiy ish', 'ijtimoiy siyosat'),
    'SOC03': ('sociolog', 'социолог', 'sotsiolog', 'sosiolog'),
    'SPO01': ('sport', 'physical education', 'kinesiolog', 'coaching', 'спорт', 'физическая культура', 'физкультур',
              'jismoniy tarbiya', 'trener'),
    'STA01': ('statistic', 'operational research', 'operations research', 'actuarial science', 'статист',
              'исследование операций', 'statistika', 'operatsiyalarni tadqiq'),
    'AREA_ART': ('humanities', 'liberal arts', 'гуманитар', 'gumanitar'),
    'AREA_ENG': ('engineering', 'technolog', 'инженер', 'технолог', 'muhandis', 'texnolog'),
    'AREA_LIF': ('life science', 'health', 'biomedic', 'науки о жизни', 'здоровь', 'salomatlik', 'hayot fanlari'),
    'AREA_NAT': ('natural science', 'science$', 'sciences$', 'естественн', 'наук', 'tabiiy fan', 'fan$', 'fanlar$'),
    'AREA_SOC': ('social science', 'social stud', 'social', 'социальн', 'обществен', 'ijtimoiy', 'jamiyat'),
}

PARTS = re.compile(r'[,;/\n|]+|\s+(?:and|и|va|hamda|&)\s+|\s*&\s*', re.IGNORECASE)
APOSTROPHES = re.compile("[\u2018\u2019\u02bb\u02bc\u0060\u00b4\u2032]")


def normalize(text):
    """Lower case, one apostrophe (Uzbek o‘ g‘ o` o\u2019 all become o'), Cyrillic ё as е."""
    return APOSTROPHES.sub("'", str(text or '').lower()).replace('ё', 'е').strip()


def compile_keywords():
    compiled = []
    for code, words in KEYWORDS.items():
        for word in words:
            whole = word.endswith('$')
            word = normalize(word.rstrip('$'))
            compiled.append((code, len(word), re.compile(r'(?<!\w)' + re.escape(word) + (r'(?!\w)' if whole else ''))))
    return compiled


_COMPILED = compile_keywords()


def split_majors(text):
    """The separate majors of a free-text field: split on , ; / newline, '&' and the words and / и / va."""
    return [part.strip() for part in PARTS.split(normalize(text)) if part and part.strip()]


def subjects_for_part(part):
    """The QS subject codes of one major: the subject whose keyword is longest wins (ties keep every code),
    and a broad area is used only when no subject keyword matched."""
    best = {}
    for code, length, pattern in _COMPILED:
        if pattern.search(part):
            best[code] = max(best.get(code, 0), length)
    for group in ([c for c in best if c not in AREAS], [c for c in best if c in AREAS]):
        if group:
            top = max(best[code] for code in group)
            return sorted(code for code in group if best[code] == top)
    return []


def subjects_for_major(text):
    """QS subject codes for a student's free-text major(s), in the order stated, no repeats; [] when nothing matches."""
    codes = []
    for part in split_majors(text):
        for code in subjects_for_part(part):
            if code not in codes:
                codes.append(code)
    return codes


def subject_name(code):
    return SUBJECTS[code][0]
