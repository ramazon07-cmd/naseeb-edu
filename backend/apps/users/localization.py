SUPPORTED_LANGUAGES = {'uz', 'ru', 'en'}

MESSAGES = {
    'credential_expired': {
        'uz': 'Vaqtinchalik parol muddati tugagan. Administrator yangi parol berishi kerak.',
        'ru': 'Срок действия временного пароля истёк. Администратор должен выдать новый пароль.',
        'en': 'The temporary password has expired. An administrator must issue a new one.',
    },
    'credential_used': {
        'uz': 'Bu vaqtinchalik parol allaqachon ishlatilgan. Administrator yangi parol berishi kerak.',
        'ru': 'Этот временный пароль уже использован. Администратор должен выдать новый пароль.',
        'en': 'This temporary password has already been used. An administrator must issue a new one.',
    },
    'credential_missing': {
        'uz': 'Faol vaqtinchalik login ma’lumoti topilmadi. Administratorga murojaat qiling.',
        'ru': 'Активные временные данные для входа не найдены. Обратитесь к администратору.',
        'en': 'No active temporary credential was found. Contact an administrator.',
    },
    'password_change_required': {
        'uz': 'Davom etishdan oldin vaqtinchalik parolni o‘zgartiring.',
        'ru': 'Измените временный пароль, прежде чем продолжить.',
        'en': 'Change your temporary password before continuing.',
    },
    'session_revoked': {
        'uz': 'Sessiya bekor qilingan. Qayta kiring.',
        'ru': 'Сессия отозвана. Войдите снова.',
        'en': 'This session has been revoked. Sign in again.',
    },
}

COMMON_API_MESSAGES = {
    'This field is required.': {
        'uz': 'Bu maydonni to‘ldirish shart.',
        'ru': 'Это поле обязательно.',
    },
    'This field may not be blank.': {
        'uz': 'Bu maydon bo‘sh bo‘lishi mumkin emas.',
        'ru': 'Это поле не может быть пустым.',
    },
    'Enter a valid email address.': {
        'uz': 'To‘g‘ri email manzilini kiriting.',
        'ru': 'Введите корректный адрес электронной почты.',
    },
    'Invalid input.': {
        'uz': 'Kiritilgan ma’lumot noto‘g‘ri.',
        'ru': 'Введены некорректные данные.',
    },
    'Authentication credentials were not provided.': {
        'uz': 'Kirish ma’lumotlari taqdim etilmagan.',
        'ru': 'Учётные данные не предоставлены.',
    },
    'You do not have permission to perform this action.': {
        'uz': 'Bu amalni bajarish uchun ruxsatingiz yo‘q.',
        'ru': 'У вас нет прав для выполнения этого действия.',
    },
    'Not found.': {
        'uz': 'Ma’lumot topilmadi.',
        'ru': 'Данные не найдены.',
    },
}

API_STATUS_MESSAGES = {
    400: {
        'uz': 'So‘rovni bajarib bo‘lmadi. Kiritilgan ma’lumotlarni tekshiring.',
        'ru': 'Не удалось выполнить запрос. Проверьте введённые данные.',
    },
    401: {
        'uz': 'Sessiya tugagan yoki kirish ma’lumotlari noto‘g‘ri. Qayta kiring.',
        'ru': 'Сессия истекла или данные для входа неверны. Войдите снова.',
    },
    403: {
        'uz': 'Bu amalni bajarish uchun ruxsatingiz yo‘q.',
        'ru': 'У вас нет прав для выполнения этого действия.',
    },
    404: {
        'uz': 'So‘ralgan ma’lumot topilmadi.',
        'ru': 'Запрошенные данные не найдены.',
    },
    409: {
        'uz': 'Bu amal joriy holat bilan mos kelmaydi.',
        'ru': 'Это действие конфликтует с текущим состоянием.',
    },
    429: {
        'uz': 'Juda ko‘p so‘rov yuborildi. Birozdan keyin qayta urining.',
        'ru': 'Слишком много запросов. Попробуйте немного позже.',
    },
    500: {
        'uz': 'Serverda xatolik yuz berdi. Keyinroq qayta urining.',
        'ru': 'На сервере произошла ошибка. Попробуйте позже.',
    },
}


def request_language(request):
    raw = request.headers.get('Accept-Language', '')
    if not raw:
        return 'en'
    language = str(raw).split(',')[0].split('-')[0].strip().lower()
    return language if language in SUPPORTED_LANGUAGES else 'en'


def localized_message(key, request=None, language=None):
    selected = language or (request_language(request) if request else 'en')
    translations = MESSAGES.get(key, {})
    return translations.get(selected) or translations.get('en') or key


def localized_api_error(message, status_code, request=None, language=None):
    """Return a safe localized API error without leaking an English fallback."""
    selected = language or (request_language(request) if request else 'en')
    text = str(message or '').strip()
    if selected == 'en':
        return text

    for translations in MESSAGES.values():
        if text == translations.get(selected):
            return text

    exact = COMMON_API_MESSAGES.get(text, {})
    if exact.get(selected):
        return exact[selected]

    category = status_code if status_code in API_STATUS_MESSAGES else (500 if status_code >= 500 else 400)
    return API_STATUS_MESSAGES[category][selected]
