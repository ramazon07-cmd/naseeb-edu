from . import api_messages

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
    'workspace_read_only': {
        'uz': 'Ish maydoni faqat o‘qish rejimida. Obunani yangilash uchun administratorga murojaat qiling.',
        'ru': 'Рабочее пространство доступно только для чтения. Обратитесь к администратору, чтобы продлить подписку.',
        'en': 'This workspace is read-only. Contact an administrator to renew the subscription.',
    },
    'staff_tier_forbidden': {
        'uz': 'Xodim darajangiz bu amalga ruxsat bermaydi.',
        'ru': 'Ваш уровень доступа сотрудника не позволяет выполнить это действие.',
        'en': 'Your staff access level does not allow this action.',
    },
    'feature_not_in_plan': {
        'uz': 'Bu imkoniyat ish maydoningiz tarifiga kiritilmagan.',
        'ru': 'Эта функция не входит в тариф вашего рабочего пространства.',
        'en': 'This feature is not included in your workspace plan.',
    },
    'school_inactive': {
        'uz': 'Maktabingiz hisobi faolsizlantirilgan. Administratorga murojaat qiling.',
        'ru': 'Учётная запись вашей школы деактивирована. Обратитесь к администратору.',
        'en': 'Your school’s workspace has been deactivated. Contact an administrator.',
    },
    'session_revoked': {
        'uz': 'Sessiya bekor qilingan. Qayta kiring.',
        'ru': 'Сессия отозвана. Войдите снова.',
        'en': 'This session has been revoked. Sign in again.',
    },
    'invite_unavailable': {
        'uz': 'Bu taklif havolasi endi ishlamaydi. Maslahatchingizdan yangisini so‘rang.',
        'ru': 'Эта ссылка-приглашение больше не действует. Попросите у консультанта новую.',
        'en': 'This invitation link is no longer valid. Ask your counselor for a new one.',
    },
    'meeting_email_requested_subject': {
        'uz': 'Yangi uchrashuv so‘rovi: {other}',
        'ru': 'Новый запрос на встречу: {other}',
        'en': 'New meeting request from {other}',
    },
    'meeting_email_requested': {
        'uz': 'Assalomu alaykum, {name}!\n\n{other} siz bilan uchrashuv so‘radi. Naseeb Edu’da tasdiqlang yoki boshqa vaqtga ko‘chiring.',
        'ru': 'Здравствуйте, {name}!\n\n{other} просит о встрече с вами. Подтвердите её или перенесите в Naseeb Edu.',
        'en': 'Hello {name},\n\n{other} asked to meet with you. Confirm or move it on Naseeb Edu.',
    },
    'meeting_email_confirmed_subject': {
        'uz': 'Uchrashuv tasdiqlandi: {time}',
        'ru': 'Встреча подтверждена: {time}',
        'en': 'Meeting confirmed: {time}',
    },
    'meeting_email_confirmed': {
        'uz': 'Assalomu alaykum, {name}!\n\n{other} bilan uchrashuvingiz tasdiqlandi.',
        'ru': 'Здравствуйте, {name}!\n\nВаша встреча с {other} подтверждена.',
        'en': 'Hello {name},\n\nYour meeting with {other} is confirmed.',
    },
    'meeting_email_declined_subject': {
        'uz': 'Uchrashuv rad etildi',
        'ru': 'Встреча отклонена',
        'en': 'Meeting declined',
    },
    'meeting_email_declined': {
        'uz': 'Assalomu alaykum, {name}!\n\n{other} bilan uchrashuv so‘rovingiz rad etildi. Boshqa vaqtni tanlab, qayta so‘rashingiz mumkin.',
        'ru': 'Здравствуйте, {name}!\n\nВаш запрос на встречу с {other} отклонён. Вы можете выбрать другое время и отправить запрос снова.',
        'en': 'Hello {name},\n\nYour meeting request with {other} was declined. You can pick another time and ask again.',
    },
    'meeting_email_cancelled_subject': {
        'uz': 'Uchrashuv bekor qilindi',
        'ru': 'Встреча отменена',
        'en': 'Meeting cancelled',
    },
    'meeting_email_cancelled': {
        'uz': 'Assalomu alaykum, {name}!\n\n{other} bilan uchrashuv bekor qilindi.',
        'ru': 'Здравствуйте, {name}!\n\nВстреча с {other} отменена.',
        'en': 'Hello {name},\n\nThe meeting with {other} was cancelled.',
    },
    'meeting_email_invited_subject': {
        'uz': 'Uchrashuvga taklif: {other}',
        'ru': 'Приглашение на встречу: {other}',
        'en': '{other} invited you to a meeting',
    },
    'meeting_email_invited': {
        'uz': 'Assalomu alaykum, {name}!\n\n{other} sizni uchrashuvga taklif qildi. Saytda tasdiqlang yoki rad eting.',
        'ru': 'Здравствуйте, {name}!\n\n{other} приглашает вас на встречу. Подтвердите или отклоните её на сайте.',
        'en': 'Hello {name},\n\n{other} invited you to a meeting. Confirm it on the website.',
    },
    'meeting_email_invite_accepted_subject': {
        'uz': 'Uchrashuv tasdiqlandi: {time}',
        'ru': 'Встреча подтверждена: {time}',
        'en': 'Meeting confirmed: {time}',
    },
    'meeting_email_invite_accepted': {
        'uz': 'Assalomu alaykum, {name}!\n\n{other} uchrashuv taklifingizni tasdiqladi.',
        'ru': 'Здравствуйте, {name}!\n\n{other} подтвердил(а) ваше приглашение на встречу.',
        'en': 'Hello {name},\n\n{other} confirmed your meeting invitation.',
    },
    'meeting_email_invite_declined_subject': {
        'uz': 'Uchrashuv taklifi rad etildi',
        'ru': 'Приглашение на встречу отклонено',
        'en': 'Meeting invitation declined',
    },
    'meeting_email_invite_declined': {
        'uz': 'Assalomu alaykum, {name}!\n\n{other} uchrashuv taklifingizni rad etdi. Boshqa vaqtni taklif qilishingiz mumkin.',
        'ru': 'Здравствуйте, {name}!\n\n{other} отклонил(а) ваше приглашение на встречу. Вы можете предложить другое время.',
        'en': 'Hello {name},\n\n{other} declined your meeting invitation. You can propose another time.',
    },
    'meeting_email_move_requested_subject': {
        'uz': 'Uchrashuvni ko‘chirish so‘rovi',
        'ru': 'Запрос на перенос встречи',
        'en': 'Meeting reschedule requested',
    },
    'meeting_email_move_requested': {
        'uz': 'Assalomu alaykum, {name}!\n\n{other} bilan uchrashuv uchun yangi vaqt so‘raldi. U tasdiqlanishini kutmoqda.',
        'ru': 'Здравствуйте, {name}!\n\nДля встречи с {other} запрошено новое время. Оно ожидает подтверждения.',
        'en': 'Hello {name},\n\nA new time was requested for the meeting with {other}. It is waiting to be confirmed.',
    },
    'meeting_email_moved_subject': {
        'uz': 'Uchrashuv boshqa vaqtga ko‘chirildi: {time}',
        'ru': 'Встреча перенесена: {time}',
        'en': 'Meeting moved: {time}',
    },
    'meeting_email_moved': {
        'uz': 'Assalomu alaykum, {name}!\n\n{other} bilan uchrashuv yangi vaqtga ko‘chirildi.',
        'ru': 'Здравствуйте, {name}!\n\nВстреча с {other} перенесена на новое время.',
        'en': 'Hello {name},\n\nThe meeting with {other} was moved to a new time.',
    },
    'meeting_email_reminder_subject': {
        'uz': 'Eslatma: uchrashuv {time}',
        'ru': 'Напоминание: встреча {time}',
        'en': 'Reminder: meeting at {time}',
    },
    'meeting_email_reminder': {
        'uz': 'Assalomu alaykum, {name}!\n\n{other} bilan uchrashuvingiz yaqinlashmoqda.',
        'ru': 'Здравствуйте, {name}!\n\nСкоро ваша встреча с {other}.',
        'en': 'Hello {name},\n\nYour meeting with {other} is coming up.',
    },
    'meeting_email_details': {
        'uz': '\n\nMavzu: {topic}\nVaqt: {time} (Toshkent vaqti), {minutes} daqiqa\nKim bilan: {other}\n\nUchrashuvlar: {link}\n\nNaseeb Edu',
        'ru': '\n\nТема: {topic}\nВремя: {time} (по Ташкенту), {minutes} мин\nС кем: {other}\n\nВстречи: {link}\n\nNaseeb Edu',
        'en': '\n\nTopic: {topic}\nTime: {time} (Tashkent time), {minutes} min\nWith: {other}\n\nMeetings: {link}\n\nNaseeb Edu',
    },
    'assistant_invite_subject': {
        'uz': '{counselor} sizni Naseeb Edu’da assistent bo‘lishga taklif qildi',
        'ru': '{counselor} приглашает вас стать ассистентом в Naseeb Edu',
        'en': '{counselor} invited you to be their assistant on Naseeb Edu',
    },
    'assistant_invite_body': {
        'uz': (
            'Assalomu alaykum, {name}!\n\n'
            '{counselor} ({school}) sizni Naseeb Edu’da counselor assistenti sifatida taklif qildi.\n'
            'Login va parolingizni o‘rnatish uchun havolani oching:\n\n{link}\n\n'
            'Havola {days} kun amal qiladi va faqat bir marta ishlaydi.'
        ),
        'ru': (
            'Здравствуйте, {name}!\n\n'
            '{counselor} ({school}) приглашает вас стать ассистентом консультанта в Naseeb Edu.\n'
            'Откройте ссылку, чтобы задать логин и пароль:\n\n{link}\n\n'
            'Ссылка действует {days} дн. и срабатывает один раз.'
        ),
        'en': (
            'Hello {name},\n\n'
            '{counselor} ({school}) invited you to Naseeb Edu as their counselor assistant.\n'
            'Open this link to set your login and password:\n\n{link}\n\n'
            'The link works once and stays valid for {days} days.'
        ),
    },
    'awaiting_confirmation': {
        'uz': 'Maslahatchingiz sizni hali tasdiqlamadi.',
        'ru': 'Ваш консультант ещё не подтвердил вас.',
        'en': 'Your counselor has not confirmed you yet.',
    },
    'invite_paused': {
        'uz': 'Bu havola hozircha yangi o‘quvchilarni qabul qilmayapti.',
        'ru': 'Эта ссылка сейчас не принимает новых учеников.',
        'en': 'This link is not accepting new students right now.',
    },
    'already_confirmed': {
        'uz': 'Bu o‘quvchi allaqachon tasdiqlangan.',
        'ru': 'Этот ученик уже подтверждён.',
        'en': 'This student was already confirmed.',
    },
    'school_full': {
        'uz': 'Bu maktabda o‘quvchilar uchun bo‘sh joy qolmagan. Maslahatchingizga murojaat qiling.',
        'ru': 'В этой школе не осталось свободных мест для учеников. Обратитесь к своему консультанту.',
        'en': 'This school has no free student places left. Contact your counselor.',
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
    'Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters.': {
        'uz': 'Foydalanuvchi nomida faqat harflar, raqamlar va @ . + - _ belgilari bo‘lishi mumkin.',
        'ru': 'Имя пользователя может содержать только буквы, цифры и символы @ . + - _.',
    },
    'This email address already has an account. Connect that student instead of inviting them.': {
        'uz': 'Bu email manzilda allaqachon hisob bor. Taklif qilish o‘rniga o‘sha o‘quvchini biriktiring.',
        'ru': 'С этим адресом электронной почты уже есть аккаунт. Привяжите этого ученика вместо приглашения.',
    },
    'Use the email address this invitation was sent to.': {
        'uz': 'Taklif yuborilgan email manzildan foydalaning.',
        'ru': 'Укажите адрес электронной почты, на который пришло приглашение.',
    },
    'This username is already in use.': {
        'uz': 'Bu foydalanuvchi nomi band.',
        'ru': 'Это имя пользователя уже занято.',
    },
    'This username or email address is already in use.': {
        'uz': 'Bu foydalanuvchi nomi yoki email manzil band.',
        'ru': 'Это имя пользователя или адрес электронной почты уже заняты.',
    },
    'This email address is already used by another account.': {
        'uz': 'Bu email manzil boshqa hisobda ishlatilmoqda.',
        'ru': 'Этот адрес электронной почты уже используется другим аккаунтом.',
    },
    'Choose the counselor these students will work with.': {
        'uz': 'O‘quvchilar ishlaydigan maslahatchini tanlang.',
        'ru': 'Выберите консультанта, с которым будут работать ученики.',
    },
    'Choose an active counselor of this school.': {
        'uz': 'Ushbu maktabning faol maslahatchisini tanlang.',
        'ru': 'Выберите активного консультанта этой школы.',
    },
    'Only counselors can invite students.': {
        'uz': 'O‘quvchilarni faqat maslahatchilar taklif qila oladi.',
        'ru': 'Приглашать учеников могут только консультанты.',
    },
    'Students get their login from their counselor. Create the student account instead.': {
        'uz': 'O‘quvchi login va parolni maslahatchisidan oladi. Taklif o‘rniga o‘quvchi hisobini yarating.',
        'ru': 'Ученик получает логин и пароль от консультанта. Вместо приглашения создайте аккаунт ученика.',
    },
    'One or more selected students are not available for assignment.': {
        'uz': 'Tanlangan o‘quvchilardan biri yoki bir nechtasi biriktirish uchun mavjud emas.',
        'ru': 'Один или несколько выбранных учеников недоступны для назначения.',
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

    known = api_messages.translate(text, selected)
    if known:
        return known

    category = status_code if status_code in API_STATUS_MESSAGES else (500 if status_code >= 500 else 400)
    return API_STATUS_MESSAGES[category][selected]
