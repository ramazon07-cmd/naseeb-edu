"""Structured AI and explainable matching helpers for admissions workflows."""

import json
import re
import urllib.error
import urllib.request
from collections import defaultdict

from django.conf import settings


RIASEC_TRAITS = {
    'R': {'en': 'Practical', 'uz': 'Amaliy', 'ru': 'Практический'},
    'I': {'en': 'Investigative', 'uz': 'Tadqiqotchi', 'ru': 'Исследовательский'},
    'A': {'en': 'Creative', 'uz': 'Ijodiy', 'ru': 'Творческий'},
    'S': {'en': 'Social', 'uz': 'Ijtimoiy', 'ru': 'Социальный'},
    'E': {'en': 'Enterprising', 'uz': 'Tashabbuskor', 'ru': 'Предпринимательский'},
    'C': {'en': 'Structured', 'uz': 'Tizimli', 'ru': 'Системный'},
}

RIASEC_QUESTIONS = (
    ('r1', 'R', 'I enjoy building, repairing, or working with physical tools.', 'Buyum yasash, ta’mirlash yoki amaliy vositalar bilan ishlashni yoqtiraman.', 'Мне нравится создавать, ремонтировать и работать с практическими инструментами.'),
    ('r2', 'R', 'I prefer learning by doing rather than only reading about a topic.', 'Mavzuni faqat o‘qishdan ko‘ra amalda bajarib o‘rganishni afzal ko‘raman.', 'Я предпочитаю учиться на практике, а не только читать о теме.'),
    ('i1', 'I', 'I enjoy investigating difficult questions and finding evidence.', 'Murakkab savollarni o‘rganish va dalil topishni yoqtiraman.', 'Мне нравится исследовать сложные вопросы и находить доказательства.'),
    ('i2', 'I', 'Science, data, or analytical problems keep me interested.', 'Fan, ma’lumotlar yoki tahliliy masalalar meni qiziqtiradi.', 'Наука, данные и аналитические задачи удерживают мой интерес.'),
    ('a1', 'A', 'I enjoy expressing ideas through writing, design, music, or media.', 'G‘oyalarni yozuv, dizayn, musiqa yoki media orqali ifodalashni yoqtiraman.', 'Мне нравится выражать идеи через тексты, дизайн, музыку или медиа.'),
    ('a2', 'A', 'I prefer assignments that allow originality and imagination.', 'O‘ziga xoslik va tasavvurga imkon beradigan vazifalarni afzal ko‘raman.', 'Я предпочитаю задания, где можно проявить оригинальность и воображение.'),
    ('s1', 'S', 'I gain energy from helping, teaching, or supporting other people.', 'Boshqalarga yordam berish, o‘rgatish yoki qo‘llab-quvvatlash menga kuch beradi.', 'Я получаю энергию, помогая, обучая и поддерживая других.'),
    ('s2', 'S', 'I prefer collaborative learning and frequent interaction.', 'Hamkorlikda o‘rganish va tez-tez muloqot qilishni afzal ko‘raman.', 'Я предпочитаю совместное обучение и частое общение.'),
    ('e1', 'E', 'I enjoy leading projects, persuading people, or starting initiatives.', 'Loyihalarni boshqarish, odamlarni ishontirish yoki tashabbus boshlashni yoqtiraman.', 'Мне нравится руководить проектами, убеждать людей и запускать инициативы.'),
    ('e2', 'E', 'Business, leadership, or public impact opportunities interest me.', 'Biznes, liderlik yoki jamoatga ta’sir imkoniyatlari meni qiziqtiradi.', 'Меня интересуют бизнес, лидерство и общественное влияние.'),
    ('c1', 'C', 'I work best with clear expectations, plans, and deadlines.', 'Aniq talablar, rejalar va muddatlar bilan eng yaxshi ishlayman.', 'Я лучше всего работаю с ясными требованиями, планами и сроками.'),
    ('c2', 'C', 'I enjoy organizing information and checking details carefully.', 'Ma’lumotlarni tartibga solish va detallarni sinchiklab tekshirishni yoqtiraman.', 'Мне нравится систематизировать информацию и внимательно проверять детали.'),
)


def normalized_language(value):
    language = str(value or 'en').split(',')[0].split('-')[0].lower()
    return language if language in {'uz', 'ru', 'en'} else 'en'


def personality_questions(language='en'):
    language = normalized_language(language)
    text_index = {'en': 2, 'uz': 3, 'ru': 4}[language]
    return [
        {'id': item[0], 'trait': item[1], 'text': item[text_index], 'min': 1, 'max': 5}
        for item in RIASEC_QUESTIONS
    ]


def score_personality_answers(answers):
    grouped = defaultdict(list)
    for question_id, trait, *_ in RIASEC_QUESTIONS:
        grouped[trait].append(int(answers[question_id]))
    scores = {
        trait: round((sum(values) / len(values) - 1) / 4 * 100)
        for trait, values in grouped.items()
    }
    top_traits = sorted(scores, key=lambda trait: (-scores[trait], trait))[:2]
    return scores, top_traits


def personality_response(assessment, language='en', include_questions=True):
    language = normalized_language(language)
    payload = {
        'ready': bool(assessment),
        'framework': 'riasec-v1',
        'answers': assessment.answers if assessment else {},
        'scores': assessment.scores if assessment else {},
        'top_traits': assessment.top_traits if assessment else [],
        'trait_labels': {code: labels[language] for code, labels in RIASEC_TRAITS.items()},
        'completed_at': assessment.completed_at if assessment else None,
    }
    if include_questions:
        payload['questions'] = personality_questions(language)
    return payload


MAJOR_TRAIT_HINTS = {
    'R': ('engineering', 'architecture', 'agriculture', 'mechanical', 'construction', 'sport'),
    'I': ('science', 'computer', 'data', 'medicine', 'biology', 'chemistry', 'physics', 'economics', 'research'),
    'A': ('art', 'design', 'writing', 'media', 'communication', 'literature', 'music', 'film'),
    'S': ('education', 'psychology', 'medicine', 'nursing', 'social', 'public health', 'counseling'),
    'E': ('business', 'management', 'finance', 'law', 'economics', 'policy', 'entrepreneur'),
    'C': ('accounting', 'finance', 'information systems', 'statistics', 'operations', 'data'),
}


def university_personality_traits(university):
    explicit = {value.strip().upper() for value in university.personality_tags.split(',') if value.strip()}
    explicit &= set(RIASEC_TRAITS)
    if explicit:
        return explicit
    majors = university.popular_majors.casefold()
    inferred = {
        trait for trait, keywords in MAJOR_TRAIT_HINTS.items()
        if any(keyword in majors for keyword in keywords)
    }
    return inferred or {'I', 'S'}


def personality_university_fit(assessment, university):
    traits = university_personality_traits(university)
    scores = assessment.scores or {}
    score = round(sum(int(scores.get(trait, 50)) for trait in traits) / len(traits) / 10)
    aligned = sorted(traits, key=lambda trait: -int(scores.get(trait, 0)))[:2]
    return min(10, max(0, score)), aligned


def _gateway_json(system_prompt, user_prompt, max_tokens=1200, model=None):
    if not settings.AI_GATEWAY_API_KEY:
        raise RuntimeError('AI provider is not configured.')
    selected_model = model or settings.AI_ASSISTANT_MODEL
    body = {
        'model': selected_model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'stream': False,
        'max_completion_tokens': max_tokens,
        'response_format': {'type': 'json_object'},
    }
    if settings.AI_ASSISTANT_FALLBACK_MODEL and selected_model != settings.AI_ASSISTANT_FALLBACK_MODEL:
        body['providerOptions'] = {'gateway': {'models': [settings.AI_ASSISTANT_FALLBACK_MODEL]}}
    request = urllib.request.Request(
        settings.AI_GATEWAY_URL,
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {settings.AI_GATEWAY_API_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Vercel-AI-App-Name': 'Naseeb Edu',
        },
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=settings.AI_ASSISTANT_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('AI provider returned an invalid response object.')
    choices = payload.get('choices')
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError('AI provider returned no usable response choice.')
    message = choices[0].get('message')
    if not isinstance(message, dict):
        raise ValueError('AI provider returned an invalid response message.')
    content = message.get('content', '')
    if isinstance(content, list):
        content = ''.join(item.get('text', '') for item in content if isinstance(item, dict))
    content = re.sub(r'^```(?:json)?\s*|\s*```$', '', str(content).strip(), flags=re.IGNORECASE)
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError('AI review did not return an object.')
    return result


def _clamp_score(value, maximum=100):
    try:
        return max(0, min(maximum, round(float(value))))
    except (TypeError, ValueError):
        return 0


ESSAY_REVIEW_COPY = {
    'en': {
        'disclaimer': 'AI feedback is advisory. Keep your own voice and review every suggestion with your counselor.',
        'labels': ('Prompt fit', 'Structure', 'Specificity', 'Reflection', 'Authentic voice', 'Clarity'),
        'positive': (
            'The draft addresses the prompt through relevant language and focus.',
            'The draft has a usable progression.',
            'Concrete detail supports the story.',
            'The draft shows learning or change.',
            'The student remains the subject of the story.',
            'The length is workable for revision.',
        ),
        'improve': (
            'Connect each main paragraph more directly to the prompt.',
            'Separate the context, action, result, and reflection more clearly.',
            'Add one specific scene, decision, or measurable result.',
            'Explain what changed in your thinking and why it matters now.',
            'Use first-person decisions and observations so the voice feels personal.',
            'Develop the draft further before line-level editing.',
        ),
        'summary': 'A first-pass structural review is ready. Focus on concrete evidence, reflection, and prompt alignment before polishing sentences.',
        'strength': 'A draft exists and can now be revised against a clear rubric.',
        'issues': (
            ('The story is mostly general.', 'Add a concrete moment with an action and observable result.'),
            ('Reflection is limited.', 'Add what you learned, how you changed, and how it shapes your next goal.'),
            ('The draft is too short for a useful full review.', 'Develop a complete beginning, middle, and reflective ending.'),
        ),
        'next_steps': (
            'Choose one central experience instead of covering several unrelated ideas.',
            'Add a concrete action and result.',
            'End with reflection that connects the experience to your future direction.',
        ),
    },
    'uz': {
        'disclaimer': 'AI tavsiyalari maslahat xarakterida. O‘z ovozingizni saqlang va har bir tavsiyani maslahatchingiz bilan ko‘rib chiqing.',
        'labels': ('Savolga moslik', 'Tuzilish', 'Aniqlik', 'Tahlil va xulosa', 'Shaxsiy ovoz', 'Tushunarlilik'),
        'positive': (
            'Qoralama savolga mos mazmun va yo‘nalishni saqlagan.',
            'Qoralamada foydalanish mumkin bo‘lgan mantiqiy rivoj bor.',
            'Aniq detallar hikoyani qo‘llab-quvvatlaydi.',
            'Qoralamada o‘rganish yoki o‘zgarish ko‘rsatilgan.',
            'Hikoyaning markazida o‘quvchining o‘zi turibdi.',
            'Matn hajmi tahrirlash uchun yetarli.',
        ),
        'improve': (
            'Har bir asosiy paragrafni savol bilan yanada bevosita bog‘lang.',
            'Vaziyat, harakat, natija va xulosani aniqroq ajrating.',
            'Bitta aniq voqea, qaror yoki o‘lchanadigan natija qo‘shing.',
            'Fikringiz qanday o‘zgargani va bu hozir nega muhimligini tushuntiring.',
            'Ovoz shaxsiy bo‘lishi uchun birinchi shaxsdagi qaror va kuzatuvlardan foydalaning.',
            'Jumla darajasidagi tahrirdan oldin qoralamani to‘liqroq rivojlantiring.',
        ),
        'summary': 'Dastlabki tuzilmaviy tahlil tayyor. Jumlalarni sayqallashdan oldin aniq dalil, shaxsiy xulosa va savolga moslikka e’tibor bering.',
        'strength': 'Qoralama mavjud va endi uni aniq mezonlar asosida yaxshilash mumkin.',
        'issues': (
            ('Hikoya ko‘proq umumiy fikrlardan iborat.', 'Harakat va ko‘rinadigan natijaga ega aniq bir voqeani qo‘shing.'),
            ('Shaxsiy xulosa yetarli emas.', 'Nimani o‘rganganingizni, qanday o‘zgarganingizni va bu keyingi maqsadingizga qanday ta’sir qilishini yozing.'),
            ('To‘liq tahlil uchun qoralama juda qisqa.', 'Boshlanishi, rivoji va shaxsiy xulosasi bor to‘liq matn yarating.'),
        ),
        'next_steps': (
            'Bir nechta aloqasiz fikr o‘rniga bitta markaziy tajribani tanlang.',
            'Aniq harakat va uning natijasini qo‘shing.',
            'Tajribani kelajak yo‘nalishingiz bilan bog‘laydigan xulosa bilan yakunlang.',
        ),
    },
    'ru': {
        'disclaimer': 'Рекомендации ИИ носят консультативный характер. Сохраните свой голос и обсудите каждое предложение с консультантом.',
        'labels': ('Соответствие вопросу', 'Структура', 'Конкретика', 'Рефлексия', 'Авторский голос', 'Ясность'),
        'positive': (
            'Черновик сохраняет фокус и отвечает на вопрос.',
            'В черновике есть понятное развитие мысли.',
            'Конкретные детали поддерживают историю.',
            'Черновик показывает обучение или изменение.',
            'Ученик остаётся главным действующим лицом истории.',
            'Объём подходит для дальнейшей доработки.',
        ),
        'improve': (
            'Свяжите каждый основной абзац с вопросом более напрямую.',
            'Чётче разделите контекст, действие, результат и рефлексию.',
            'Добавьте одну конкретную сцену, решение или измеримый результат.',
            'Объясните, как изменилось ваше мышление и почему это важно сейчас.',
            'Используйте личные решения и наблюдения, чтобы голос звучал естественно.',
            'Сначала развейте черновик, затем переходите к редактуре отдельных предложений.',
        ),
        'summary': 'Первичная структурная проверка готова. До редактуры предложений сосредоточьтесь на конкретных доказательствах, рефлексии и соответствии вопросу.',
        'strength': 'Черновик уже существует, и теперь его можно улучшать по ясным критериям.',
        'issues': (
            ('История остаётся слишком общей.', 'Добавьте конкретный момент с действием и наблюдаемым результатом.'),
            ('Рефлексии недостаточно.', 'Добавьте, чему вы научились, как изменились и как это влияет на следующую цель.'),
            ('Черновик слишком короткий для полной проверки.', 'Развейте полноценное начало, основную часть и рефлексивное завершение.'),
        ),
        'next_steps': (
            'Выберите один центральный опыт вместо нескольких несвязанных идей.',
            'Добавьте конкретное действие и его результат.',
            'Завершите рефлексией, связывающей опыт с вашим будущим направлением.',
        ),
    },
}


def normalize_essay_review(result, word_count, language='en'):
    language = normalized_language(language)
    rubric = []
    for item in result.get('rubric', [])[:6]:
        if not isinstance(item, dict):
            continue
        rubric.append({
            'key': str(item.get('key', 'criterion'))[:40],
            'label': str(item.get('label', 'Criterion'))[:80],
            'score': _clamp_score(item.get('score'), 10),
            'feedback': str(item.get('feedback', ''))[:600],
        })
    issues = []
    for item in result.get('issues', [])[:5]:
        if not isinstance(item, dict):
            continue
        issues.append({
            'excerpt': str(item.get('excerpt', ''))[:240],
            'problem': str(item.get('problem', ''))[:500],
            'suggestion': str(item.get('suggestion', ''))[:700],
        })
    return {
        'summary': str(result.get('summary', ''))[:1000],
        'overall_score': _clamp_score(result.get('overall_score')),
        'word_count': word_count,
        'rubric': rubric,
        'strengths': [str(item)[:500] for item in result.get('strengths', [])[:4]],
        'issues': issues,
        'next_steps': [str(item)[:500] for item in result.get('next_steps', [])[:5]],
        'disclaimer': ESSAY_REVIEW_COPY[language]['disclaimer'],
    }


def local_essay_review(prompt, content, language='en'):
    copy = ESSAY_REVIEW_COPY[normalized_language(language)]
    words = re.findall(r"\b[\w’'-]+\b", content, re.UNICODE)
    word_count = len(words)
    paragraphs = [part.strip() for part in re.split(r'\n\s*\n', content) if part.strip()]
    has_specifics = bool(re.search(r'\b\d+\b|\b(first|when|after|before|during|because|natijada|sabab|keyin)\b', content, re.IGNORECASE))
    has_reflection = bool(re.search(r'\b(learned|realized|understood|changed|growth|o‘rgandim|angladim|tushundim|изменил|понял)\b', content, re.IGNORECASE))
    prompt_words = {word.casefold() for word in re.findall(r'\b\w{5,}\b', prompt)}
    content_words = {word.casefold() for word in words}
    prompt_fit = min(10, 4 + min(6, len(prompt_words & content_words)))
    structure = min(10, 4 + min(3, len(paragraphs)) + (1 if word_count >= 250 else 0))
    specificity = 8 if has_specifics else 4
    reflection = 8 if has_reflection else 4
    voice = 7 if re.search(r'\b(I|my|me|men|menga|я|мой)\b', content, re.IGNORECASE) else 4
    clarity = 8 if 180 <= word_count <= 900 else 6 if word_count >= 100 else 3
    keys = ('prompt_fit', 'structure', 'specificity', 'reflection', 'voice', 'clarity')
    scores = (prompt_fit, structure, specificity, reflection, voice, clarity)
    positive = (prompt_fit >= 7, structure >= 7, has_specifics, has_reflection, voice >= 7, clarity >= 7)
    rubric = [
        {
            'key': key,
            'label': copy['labels'][index],
            'score': scores[index],
            'feedback': copy['positive'][index] if positive[index] else copy['improve'][index],
        }
        for index, key in enumerate(keys)
    ]
    overall = round(sum(item['score'] for item in rubric) / len(rubric) * 10)
    issues = []
    if not has_specifics:
        issues.append({'excerpt': '', 'problem': copy['issues'][0][0], 'suggestion': copy['issues'][0][1]})
    if not has_reflection:
        issues.append({'excerpt': '', 'problem': copy['issues'][1][0], 'suggestion': copy['issues'][1][1]})
    if word_count < 100:
        issues.append({'excerpt': '', 'problem': copy['issues'][2][0], 'suggestion': copy['issues'][2][1]})
    return normalize_essay_review({
        'summary': copy['summary'],
        'overall_score': overall,
        'rubric': rubric,
        'strengths': [copy['strength']],
        'issues': issues,
        'next_steps': list(copy['next_steps']),
    }, word_count, language)


def review_essay(prompt, content, language='en'):
    word_count = len(re.findall(r"\b[\w’'-]+\b", content, re.UNICODE))
    system_prompt = """You are Naseeb AI's university application essay reviewer.
Return valid JSON only. Evaluate the draft, but never rewrite the full essay and never claim admission certainty.
Preserve the student's authentic voice. Do not perform plagiarism or AI-authorship detection.
Use this schema: summary string, overall_score 0-100, rubric array with exactly six objects
(key, label, score 0-10, feedback), strengths string array, issues array
(excerpt copied from the draft, problem, suggestion), and next_steps string array.
Rubric keys: prompt_fit, structure, specificity, reflection, voice, clarity.
Respond in the requested language."""
    user_prompt = json.dumps({
        'language': normalized_language(language),
        'prompt': prompt,
        'draft': content,
    }, ensure_ascii=False)
    try:
        result = _gateway_json(system_prompt, user_prompt)
        return normalize_essay_review(result, word_count, language), 'gateway', settings.AI_ASSISTANT_MODEL
    except (
        AttributeError, IndexError, TypeError, RuntimeError, ValueError, KeyError,
        json.JSONDecodeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
    ):
        return local_essay_review(prompt, content, language), 'local-fallback', ''


COLLEGE_ADVISOR_COPY = {
    'en': {
        'answer': 'Based on your saved profile, the strongest options for this question are: {names}.',
        'reason': '{score}% match based on academics, interests, preferences and affordability.',
        'caution': 'Verify current admission and financial-aid requirements on the official university website.',
        'disclaimer': 'This is profile guidance, not an admission prediction or final financial-aid decision.',
    },
    'uz': {
        'answer': 'Saqlangan profilingiz bo‘yicha bu savolga eng mos variantlar: {names}.',
        'reason': 'Akademik natijalar, qiziqishlar, tanlovlar va byudjet asosida {score}% moslik.',
        'caution': 'Qabul va moliyaviy yordam talablarini universitetning rasmiy saytida tekshiring.',
        'disclaimer': 'Bu profilga asoslangan tavsiya. U qabul ehtimoli yoki yakuniy moliyaviy yordam qarori emas.',
    },
    'ru': {
        'answer': 'По сохранённому профилю наиболее подходящие варианты для этого вопроса: {names}.',
        'reason': 'Соответствие {score}% с учётом учёбы, интересов, предпочтений и бюджета.',
        'caution': 'Проверьте актуальные требования приёма и финансовой помощи на официальном сайте университета.',
        'disclaimer': 'Это рекомендация по профилю, а не прогноз поступления или окончательное решение о финансовой помощи.',
    },
}


def _college_advisor_candidates(question, research):
    candidates = list(research.get('recommendations', []))[:5]
    query = str(question or '').casefold()
    if any(term in query for term in ('budget', 'price', 'cheap', 'arzon', 'byudjet', 'narx', 'бюджет', 'дешев')):
        candidates.sort(key=lambda item: item['university'].get('net_price_usd') or 10**9)
    elif any(term in query for term in ('scholarship', 'aid', 'stipend', 'yordam', 'стипенд', 'помощ')):
        candidates.sort(key=lambda item: not any((
            item['university'].get('offers_international_aid'),
            item['university'].get('offers_merit_aid'),
            item['university'].get('offers_need_based_aid'),
        )))
    elif any(term in query for term in ('safe', 'realistic', 'xavfsiz', 'real', 'надёж', 'реалист')):
        candidates.sort(key=lambda item: item.get('admission_band') != 'strong_option')
    return candidates[:3]


def local_college_ai_advice(question, research, language='en'):
    language = normalized_language(language)
    copy = COLLEGE_ADVISOR_COPY[language]
    candidates = _college_advisor_candidates(question, research)
    universities = [
        {
            'name': item['university']['name'],
            'match_score': item['match_score'],
            'reason': copy['reason'].format(score=item['match_score']),
            'caution': copy['caution'],
        }
        for item in candidates
    ]
    names = ', '.join(item['name'] for item in universities)
    return {
        'answer': copy['answer'].format(names=names),
        'universities': universities,
        'disclaimer': copy['disclaimer'],
    }


def normalize_college_ai_advice(result, research, question, language='en'):
    fallback = local_college_ai_advice(question, research, language)
    allowed = {
        item['university']['name']: item
        for item in research.get('recommendations', [])[:5]
    }
    universities = []
    for item in result.get('universities', [])[:3]:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name', '')).strip()
        candidate = allowed.get(name)
        if not candidate:
            continue
        universities.append({
            'name': name,
            'match_score': candidate['match_score'],
            'reason': str(item.get('reason', ''))[:360],
            'caution': str(item.get('caution', ''))[:300],
        })
    answer = str(result.get('answer', '')).strip()[:900]
    if not answer or not universities:
        return fallback
    return {
        'answer': answer,
        'universities': universities,
        'disclaimer': COLLEGE_ADVISOR_COPY[normalized_language(language)]['disclaimer'],
    }


def college_ai_advice(question, research, language='en'):
    language = normalized_language(language)
    compact_candidates = []
    for item in research.get('recommendations', [])[:5]:
        university = item['university']
        compact_candidates.append({
            'name': university['name'],
            'country': university['country'],
            'match': item['match_score'],
            'band': item['admission_band'],
            'net_price_usd': university.get('net_price_usd'),
            'aid': bool(
                university.get('offers_international_aid')
                or university.get('offers_merit_aid')
                or university.get('offers_need_based_aid')
            ),
            'reasons': item.get('reasons', [])[:2],
            'gap': item.get('gaps', [])[:1],
        })
    profile = research.get('profile_snapshot', {})
    compact_profile = {
        'gpa': float(profile['gpa']) if profile.get('gpa') is not None else None,
        'sat': profile.get('sat_score'),
        'ielts': float(profile['ielts_score']) if profile.get('ielts_score') is not None else None,
        'major': profile.get('target_major'),
        'countries': profile.get('target_countries'),
        'budget_usd': profile.get('budget_usd'),
        'scholarship_needed': profile.get('scholarship_needed'),
        'personality_traits': profile.get('personality', {}).get('top_traits', []),
    }
    system_prompt = """You are Naseeb AI, a concise university advisor.
Use only the supplied profile and candidates. Never invent universities, rankings, prices, requirements or admission odds.
Answer the exact question in at most 120 words and in the requested language.
Return JSON only: answer string; universities array of up to 3 objects with name, reason and caution.
Names must exactly match supplied candidates. State uncertainty and tell the student to verify official sources."""
    user_prompt = json.dumps({
        'language': language,
        'question': question,
        'profile': compact_profile,
        'candidates': compact_candidates,
    }, ensure_ascii=False, separators=(',', ':'))
    try:
        result = _gateway_json(
            system_prompt,
            user_prompt,
            max_tokens=settings.AI_COLLEGE_MAX_OUTPUT_TOKENS,
            model=settings.AI_COLLEGE_MODEL,
        )
        return normalize_college_ai_advice(result, research, question, language), 'gateway', settings.AI_COLLEGE_MODEL
    except (
        AttributeError, IndexError, TypeError, RuntimeError, ValueError, KeyError,
        json.JSONDecodeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
    ):
        return local_college_ai_advice(question, research, language), 'local-fallback', ''
