"""Sensitive content in a recommendation letter: health, discipline, current danger; plus reader notes.

The server decides, the model only helps. Three layers:
- a keyword pre-check (English, Russian, Uzbek) that finds health and disciplinary sentences and current
  abuse or danger in the real letter;
- the model's `safety` and `sensitive` flags from the score step (merged with the keywords);
- enforcement: a health sentence is never quoted by a note or a strength (the note is dropped), and a
  letter with current abuse or danger is not scored at all.

Health, mental health and disability are never scored, quoted as evidence or asked about; the result carries
one neutral note per kind (`result['sensitive']`, rendered in three languages by the frontend). The
reader notes (`result['reader_notes']`, at most 2) are questions about how a US or UK reader may read a
phrase; they are never scored.
"""
import re

from .essay_lab import coach

MAX_READER_NOTES = 2
KINDS = ('health', 'discipline')

STEP1_EXTRA = """
Also add these keys to the same JSON object (they are never scored):
- "reader_notes": at most 2 objects {"quote", "question"}. "quote" is one sentence copied exactly from the letter. \
"question" (at most 200 characters) asks how a reader in the US or UK may read that phrase, as a question to \
the author: lukewarm praise ("satisfactory", "tries hard", "generally"), faint praise, a rank with no stated basis, \
or a gender-coded pattern (only "caring, diligent" for a girl, only "brilliant, a leader" for a boy). Formal \
school-reference wording ("obedient, disciplined, active in school life") is raised here and never lowers any score. \
Never ask the author to add a ranking, a number of students or a stronger adjective. Use [] when nothing applies.
- "safety": true only when the letter describes current abuse, violence or danger to the student or to another \
child; otherwise false. If true, do not quote it anywhere.
- "sensitive": {"health": "", "discipline": ""}. "health" is the one sentence that names a health, mental-health \
or disability matter of the student, copied exactly, or an empty string. "discipline" is the same for a \
disciplinary event. Health, mental health and disability are never scored, never quoted as evidence or in a \
note, and never asked about.\
"""

_HEALTH_WORDS = (
    r"diagnos\w*|depress\w*|anxiety|panic attacks?|therap(?:y|ist)\w*|psychiatr\w*|mental (?:health|illness)|"
    r"adhd|autis\w*|dyslex\w*|epilep\w*|diabet\w*|cancer|chemotherap\w*|surgery|hospital(?:s|ized|ised|isation|ization)?(?![a-z])|disabilit\w*|"
    r"disabled|wheelchair|eating disorder|anorexi\w*|bulimi\w*|self[- ]harm\w*|medication|illness\w*|"
    r"(?:was|is|been|being|fell|became) (?:ill|sick)|chronic\w*|asthma\w*|hiv(?![a-z])|"
    r"диагноз\w*|депресс\w*|тревожн\w*|психотерап\w*|психиатр\w*|психическ\w*|аутизм\w*|дислекси\w*|эпилепс\w*|"
    r"диабет\w*|онколог\w*|операци\w*|больниц\w*|инвалид\w*|болезн\w*|болел\w*|заболе\w*|самоповрежд\w*|астм\w*|"
    r"сдвг|"
    r"tashxis\w*|depressiya\w*|kasal\w*|kasalxona\w*|nogiron\w*|operatsiya\w*|davolan\w*|davolash\w*|autizm\w*|"
    r"disleksiya\w*|epilepsiya\w*|diabet\w*|saraton\w*|ruhiy (?:salomatlik|holat|kasal\w*|muammo\w*)|psixiatr\w*|astma\w*"
)
_DISCIPLINE_WORDS = (
    r"suspen(?:d|ded|sion)\w*|expel\w*|detention|disciplinary|misconduct|cheat\w*|plagiari\w*|"
    r"отстран\w*|исключ[её]н\w*|исключили|выговор\w*|дисциплинар\w*|списыв\w*|плагиат\w*|"
    r"intizomiy\w*|chetlatil\w*|haydal\w*|ko'chirib|tanbeh\w*"
)
_DANGER_WORDS = (
    r"(?:is|are|keeps|continues to be|being|still being) (?:abused|beaten|molested|assaulted|hit at home)|"
    r"(?:beats|hits|abuses|molests|assaults|threatens|locks) (?:her|him|them|the student)|"
    r"threatens to (?:kill|hurt|harm)|afraid to go home|unsafe at home|not safe at home|"
    r"(?:wants|wanted|plans?) to (?:die|kill (?:herself|himself|themselves))|suicid\w*|"
    r"бь[её]т|избива\w+|(?:из)?насили\w+|домогает\w*|боится идти домой|угрожает (?:убить|расправой)|хочет умереть|суицид\w*|"
    r"kaltakla(?:ydi|nadi|nmoqda|moqda)\w*|zo'ravonlik qil(?:moqda|yapti)|uyga borishdan qo'rqadi|"
    r"o'zini o'ldirmoqchi|o'lmoqchi|tahdid qiladi"
)


def _compile(words):
    return re.compile(rf'(?<!\w)(?:{words})', re.IGNORECASE)


HEALTH = _compile(_HEALTH_WORDS)
DISCIPLINE = _compile(_DISCIPLINE_WORDS)
DANGER = _compile(_DANGER_WORDS)
SAFETY_MESSAGE = (
    "This letter may describe a child in current danger. It was not scored. "
    "Please follow your school's child-protection procedure."
)


def _folded(text):
    return str(text or '').translate(coach.QUOTE_TRANSLATION).replace('\u02bb', "'").replace('\u02bc', "'")


def sentences(raw_text):
    """Every sentence of the letter, normalized (the way notes quote it)."""
    found = []
    for block in coach.paragraphs(raw_text):
        block = coach.normalize(block)
        found += [block[start:end].strip() for start, end in coach.sentence_spans(block)]
    return [sentence for sentence in found if sentence]


def keyword_sentences(raw_text, pattern):
    return [sentence for sentence in sentences(raw_text) if pattern.search(_folded(sentence))]


def current_danger(raw_text):
    """True when the letter says, in so many words, that abuse or danger is happening now."""
    return bool(DANGER.search(_folded(coach.normalize(raw_text))))


def safety_result():
    """The unscored answer for a letter that names current abuse or danger (no AI call, no cost)."""
    empty = {'scores': {}, 'summary': SAFETY_MESSAGE, 'suggestions': [], 'strengths': []}
    result = coach.build_result(empty, [], rubric='recommendation_letter', overall=None, notes_locked=True)
    result.update({'safety': True, 'reader_notes': [], 'sensitive': []})
    return result


def hooks(raw_text, anon_text, restore):
    """(restore, read_extra, finish) for the CheckSpec: the quote restorer that never returns a health
    sentence, the score-step reader of the model's flags, and the closing step that adds the reader notes
    and the sensitive notes to the result."""
    paragraph_texts = [coach.normalize(block) for block in coach.paragraphs(anon_text)]
    flagged_health = []

    def is_health(sentence):
        plain = coach.normalize(sentence)
        return bool(HEALTH.search(_folded(plain))) or any(
            plain and (plain in other or other in plain) for other in flagged_health)

    def safe_restore(quote):
        sentence = restore(quote)
        return None if sentence is None or is_health(sentence) else sentence

    flagged = {}
    readers = []

    def read_extra(raw, step):
        if not isinstance(raw, dict):
            return step
        if raw.get('safety') is True:
            return {'safety': SAFETY_MESSAGE}
        for item in raw.get('reader_notes') if isinstance(raw.get('reader_notes'), list) else []:
            if len(readers) >= MAX_READER_NOTES or not isinstance(item, dict):
                continue
            quote = coach._clean_quote(item.get('quote'), paragraph_texts)
            question = coach._short_text(item.get('question'), coach.MAX_QUESTION)
            if quote and question:
                readers.append({'quote': quote, 'question': question})
        sensitive = raw.get('sensitive') if isinstance(raw.get('sensitive'), dict) else {}
        for kind in KINDS:
            quote = coach._clean_quote(sensitive.get(kind), paragraph_texts) if sensitive.get(kind) else None
            sentence = restore(quote) if quote else None
            if sentence:
                flagged[kind] = sentence
        if 'health' in flagged:
            flagged_health.append(coach.normalize(flagged['health']))
        return step

    def finish(result, step):
        if 'safety' in step:
            result.update({'safety': True, 'reader_notes': [], 'sensitive': []})
            return result
        notes = []
        for item in readers:
            sentence = safe_restore(item['quote'])
            if sentence and all(sentence != other['quote'] for other in notes):
                notes.append({'id': f'r{len(notes) + 1}', 'quote': sentence, 'question': item['question']})
        sensitive = []
        for kind, pattern in (('health', HEALTH), ('discipline', DISCIPLINE)):
            found = keyword_sentences(raw_text, pattern) + ([flagged[kind]] if kind in flagged else [])
            if found:
                sensitive.append({'kind': kind, 'quote': found[0]})
        result.update({'reader_notes': notes, 'sensitive': sensitive})
        return result

    return safe_restore, read_extra, finish
