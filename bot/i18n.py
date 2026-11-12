LANGUAGES = ('uz', 'ru', 'en')
DEFAULT = 'uz'
LANGUAGE_NAMES = {'uz': "O'zbekcha", 'ru': 'Русский', 'en': 'English'}

# Placeholders in {braces} must be identical in every language (checked by the tests).
STRINGS = {
    'choose_language': {
        'uz': 'Tilni tanlang',
        'ru': 'Выберите язык',
        'en': 'Choose a language',
    },
    'welcome': {
        'uz': "Naseeb Edu maslahatchi boti. Faqat maslahatchilar va ularning yordamchilari foydalana oladi.\n\nHisobingizga kiring: foydalanuvchi nomingizni yuboring.",
        'ru': 'Бот консультанта Naseeb Edu. Доступен только консультантам и их ассистентам.\n\nВойдите в аккаунт: отправьте ваш логин.',
        'en': 'Naseeb Edu counselor bot. Only counselors and their assistants can use it.\n\nLog in: send your username.',
    },
    'ask_password': {
        'uz': 'Endi parolingizni yuboring. Xabar darhol o\'chiriladi va saqlanmaydi.',
        'ru': 'Теперь отправьте пароль. Сообщение сразу удаляется и нигде не сохраняется.',
        'en': 'Now send your password. The message is deleted right away and never stored.',
    },
    'checking': {
        'uz': 'Tekshirilmoqda...',
        'ru': 'Проверяем...',
        'en': 'Checking...',
    },
    'bad_credentials': {
        'uz': "Foydalanuvchi nomi yoki parol noto'g'ri. Qayta urinish uchun foydalanuvchi nomini yuboring.",
        'ru': 'Неверный логин или пароль. Чтобы попробовать снова, отправьте логин.',
        'en': 'Wrong username or password. To try again, send your username.',
    },
    'locked': {
        'uz': "Juda ko'p urinish. {minutes} daqiqadan so'ng qayta urinib ko'ring.",
        'ru': 'Слишком много попыток. Повторите через {minutes} мин.',
        'en': 'Too many attempts. Try again in {minutes} min.',
    },
    'role_refused': {
        'uz': "Kechirasiz, bu bot faqat maslahatchilar va ularning yordamchilari uchun. Hech narsa saqlanmadi.",
        'ru': 'Извините, этот бот только для консультантов и их ассистентов. Ничего не сохранено.',
        'en': 'Sorry, this bot is only for counselors and their assistants. Nothing was saved.',
    },
    'password_change_required': {
        'uz': "Avval saytda vaqtinchalik parolni almashtiring, keyin qayta kiring.",
        'ru': 'Сначала смените временный пароль на сайте, затем войдите снова.',
        'en': 'Please change your temporary password on the website first, then log in again.',
    },
    'account_unavailable': {
        'uz': "Hisob hozir mavjud emas. Maktab administratoriga murojaat qiling.",
        'ru': 'Аккаунт сейчас недоступен. Обратитесь к администратору школы.',
        'en': 'This account is not available right now. Contact your school administrator.',
    },
    'card': {
        'uz': "Siz shu hisobmisiz?\n\n<b>{name}</b>\n{contacts}",
        'ru': 'Это ваш аккаунт?\n\n<b>{name}</b>\n{contacts}',
        'en': 'Is this your account?\n\n<b>{name}</b>\n{contacts}',
    },
    'confirm': {'uz': 'Tasdiqlash', 'ru': 'Подтвердить', 'en': 'Confirm'},
    'cancel': {'uz': 'Bekor qilish', 'ru': 'Отмена', 'en': 'Cancel'},
    'cancelled': {
        'uz': 'Bekor qilindi. Qayta boshlash uchun /start.',
        'ru': 'Отменено. Чтобы начать заново, /start.',
        'en': 'Cancelled. Send /start to begin again.',
    },
    'pending_expired': {
        'uz': 'Tasdiqlash muddati tugadi. Qayta boshlash uchun /start.',
        'ru': 'Время подтверждения истекло. Начните заново: /start.',
        'en': 'The confirmation expired. Send /start to begin again.',
    },
    'linked': {
        'uz': 'Tayyor, {name}. Hisob ulandi.',
        'ru': 'Готово, {name}. Аккаунт подключён.',
        'en': 'Done, {name}. Account linked.',
    },
    'already_linked': {
        'uz': "Siz {name} sifatida kirgansiz.\n\n/now - hozir yangilanish\n/students - o'quvchilar\n/add - yangi o'quvchi qo'shish\n/reset - o'quvchiga yangi parol\n/settings - sozlamalar\n/logout - chiqish",
        'ru': 'Вы вошли как {name}.\n\n/now - сводка сейчас\n/students - ученики\n/add - добавить ученика\n/reset - новый пароль ученику\n/settings - настройки\n/logout - выйти',
        'en': "You're logged in as {name}.\n\n/now - update now\n/students - students\n/add - add a student\n/reset - new password for a student\n/settings - settings\n/logout - log out",
    },
    'other_account': {'uz': 'Boshqa hisob', 'ru': 'Другой аккаунт', 'en': 'Other account'},
    'grade_name': {
        'uz': '{grade}-sinf',
        'ru': '{grade} класс',
        'en': 'Grade {grade}',
    },
    'grade_gap': {'uz': 'Gap year', 'ru': 'Gap year', 'en': 'Gap year'},
    'grade_unknown': {'uz': 'Sinf tanlanmagan', 'ru': 'Класс не указан', 'en': 'No grade set'},
    'students_count': {
        'uz': "Sizda {total} ta o'quvchi bor. Ro'yxat: /students",
        'ru': 'У вас {total} учеников. Список: /students',
        'en': 'You have {total} students. Open the list with /students.',
    },
    'summary_activity': {
        'uz': '\U0001F7E2 Bugun {today} · \U0001F7E1 Shu hafta {week} · \U0001F534 7+ kun {inactive} · ⚪ Kirmagan {never}',
        'ru': '\U0001F7E2 Сегодня {today} · \U0001F7E1 На неделе {week} · \U0001F534 7+ дн. {inactive} · ⚪ Не заходили {never}',
        'en': '\U0001F7E2 Today {today} · \U0001F7E1 This week {week} · \U0001F534 7+ days {inactive} · ⚪ Never {never}',
    },
    'summary_essays': {
        'uz': '\U0001F4DD Bugun tahrirlangan insholar: {count}',
        'ru': '\U0001F4DD Эссе изменено сегодня: {count}',
        'en': '\U0001F4DD Essays edited today: {count}',
    },
    'summary_streaks': {
        'uz': "\U0001F525 Seriyali o'quvchilar: {count}",
        'ru': '\U0001F525 Учеников с серией: {count}',
        'en': '\U0001F525 With a streak: {count}',
    },
    'summary_avg': {
        'uz': "\U0001F4CB O'rtacha tayyorlik: {percent}%",
        'ru': '\U0001F4CB Средняя готовность: {percent}%',
        'en': '\U0001F4CB Avg readiness: {percent}%',
    },
    'sort_attention': {'uz': "Avval e'tibor kerak", 'ru': 'Сначала требуют внимания', 'en': 'Needs attention first'},
    'sort_az': {'uz': 'A-Z', 'ru': 'А-Я', 'en': 'A-Z'},
    'filter_all': {'uz': "Hamma o'quvchilar", 'ru': 'Все ученики', 'en': 'All students'},
    'filter_inactive': {'uz': '7+ kun kirmaganlar', 'ru': 'Не заходили 7+ дней', 'en': 'Inactive 7+ days'},
    'btn_sort_az': {'uz': '\U0001F524 A-Z', 'ru': '\U0001F524 А-Я', 'en': '\U0001F524 A-Z'},
    'btn_sort_attention': {'uz': "⚠ E'tibor kerak", 'ru': '⚠ Внимание', 'en': '⚠ Needs attention'},
    'btn_filter_inactive': {'uz': '\U0001F534 7+ kun kirmagan', 'ru': '\U0001F534 Не заходили 7+ дн.', 'en': '\U0001F534 Inactive 7+ days'},
    'btn_filter_all': {'uz': "\U0001F465 Hammasi", 'ru': '\U0001F465 Все', 'en': '\U0001F465 Everyone'},
    'btn_back': {'uz': "⬅ Ro'yxatga qaytish", 'ru': '⬅ К списку', 'en': '⬅ Back to list'},
    'list_empty_filter': {
        'uz': "Bu filtrga mos o'quvchi yo'q.",
        'ru': 'Под этот фильтр учеников нет.',
        'en': 'No students match this filter.',
    },
    'student_gone': {
        'uz': "Bu o'quvchi endi ro'yxatingizda yo'q. Yangi ro'yxat: /now",
        'ru': 'Этого ученика больше нет в вашем списке. Свежий список: /now',
        'en': 'This student is no longer in your list. Send /now for a fresh one.',
    },
    'seen_today': {'uz': 'bugun', 'ru': 'сегодня', 'en': 'today'},
    'seen_yesterday': {'uz': 'kecha', 'ru': 'вчера', 'en': 'yesterday'},
    'seen_days': {'uz': '{days} kun oldin', 'ru': '{days} дн. назад', 'en': '{days} days ago'},
    'seen_never': {'uz': 'hali kirmagan', 'ru': 'ещё не заходил', 'en': 'never opened'},
    'seen_expired': {'uz': 'yaqinda kirmagan', 'ru': 'давно не заходил', 'en': 'no recent activity'},
    'detail_seen': {'uz': 'Oxirgi kirish: {when}', 'ru': 'Последний вход: {when}', 'en': 'Last seen: {when}'},
    'omitted_line': {
        'uz': "...yana {omitted} ta o'quvchi ko'rsatilmadi",
        'ru': '...ещё {omitted} учеников не показано',
        'en': '...{omitted} more students not shown',
    },
    'no_students': {
        'uz': "Hozircha o'quvchilar yo'q.",
        'ru': 'Пока нет учеников.',
        'en': 'No students yet.',
    },
    'setup_time': {
        'uz': "Har kuni qaysi vaqtda yangilanish yuboray? (Toshkent vaqti)",
        'ru': 'В какое время присылать сводку каждый день? (время Ташкента)',
        'en': 'What time each day should I send the update? (Tashkent time)',
    },
    'custom_time': {'uz': 'Boshqa vaqt', 'ru': 'Другое время', 'en': 'Other time'},
    'skip_time': {'uz': 'Yubormaslik', 'ru': 'Не присылать', 'en': 'No daily update'},
    'ask_custom_time': {
        'uz': 'Vaqtni SS:DD ko\'rinishida yuboring, masalan 18:30.',
        'ru': 'Отправьте время в формате ЧЧ:ММ, например 18:30.',
        'en': 'Send the time as HH:MM, for example 18:30.',
    },
    'bad_time': {
        'uz': "Vaqt tushunarsiz. SS:DD ko'rinishida yuboring, masalan 18:30.",
        'ru': 'Не понял время. Отправьте в формате ЧЧ:ММ, например 18:30.',
        'en': "I couldn't read that time. Send it as HH:MM, for example 18:30.",
    },
    'settings_title': {
        'uz': "<b>Sozlamalar</b>\nYangilanish vaqti: {time}\nTilni va nimalar kelishini shu yerda o'zgartiring.",
        'ru': '<b>Настройки</b>\nВремя сводки: {time}\nЗдесь можно изменить язык и состав сводки.',
        'en': '<b>Settings</b>\nUpdate time: {time}\nChange the language and what the update includes.',
    },
    'time_off': {'uz': 'yoqilmagan', 'ru': 'выключено', 'en': 'off'},
    'setup_parts': {
        'uz': "Yangilanishda nimalar bo'lsin? Tugmalar bilan yoqing/o'chiring.",
        'ru': 'Что включать в сводку? Включайте и выключайте кнопками.',
        'en': 'What should the update include? Toggle with the buttons.',
    },
    'part_essays': {'uz': 'Insholar', 'ru': 'Эссе', 'en': 'Essays'},
    'part_streak': {'uz': 'Yozish seriyasi', 'ru': 'Серия письма', 'en': 'Writing streak'},
    'part_application': {'uz': "To'liq ariza", 'ru': 'Вся заявка', 'en': 'Full application'},
    'button_time': {'uz': 'Vaqt: {time}', 'ru': 'Время: {time}', 'en': 'Time: {time}'},
    'button_language': {'uz': 'Til', 'ru': 'Язык', 'en': 'Language'},
    'done': {'uz': 'Tayyor', 'ru': 'Готово', 'en': 'Done'},
    'saved': {
        'uz': "Saqlandi. Yangilanish: {time}. Hozir olish uchun /now.",
        'ru': 'Сохранено. Сводка: {time}. Получить сейчас: /now.',
        'en': 'Saved. Update: {time}. Get one now with /now.',
    },
    'not_linked': {
        'uz': 'Avval kiring: /start',
        'ru': 'Сначала войдите: /start',
        'en': 'Please log in first: /start',
    },
    'logged_out': {
        'uz': "Chiqdingiz. Bu chatdagi barcha ma'lumotlar o'chirildi. Qayta kirish uchun /start.",
        'ru': 'Вы вышли. Все данные этого чата удалены. Чтобы войти снова, /start.',
        'en': 'Logged out. Everything for this chat was removed. Send /start to log in again.',
    },
    'preparing': {'uz': 'Tayyorlanmoqda...', 'ru': 'Готовлю...', 'en': 'Preparing...'},
    'digest_title': {
        'uz': '<b>Kunlik yangilanish</b> - {date} - {total} ta o\'quvchi',
        'ru': '<b>Сводка за день</b> - {date} - учеников: {total}',
        'en': '<b>Daily update</b> - {date} - {total} students',
    },
    'digest_student': {
        'uz': '<b>{name}</b> - {grade}',
        'ru': '<b>{name}</b> - {grade}',
        'en': '<b>{name}</b> - {grade}',
    },
    'essays_line': {
        'uz': 'Insholar: {total}, bugun tahrirlangan: {edited}',
        'ru': 'Эссе: {total}, изменено сегодня: {edited}',
        'en': 'Essays: {total}, edited today: {edited}',
    },
    'streak_days': {
        'uz': 'Seriya: {days} kun',
        'ru': 'Серия: {days} дн.',
        'en': 'Streak: {days} days',
    },
    'streak_none': {'uz': 'Seriya yo\'q', 'ru': 'Серии нет', 'en': 'No streak'},
    'streak_not_shared': {
        'uz': 'Seriya: barcha insholar ulashilganda ko\'rsatiladi',
        'ru': 'Серия: видна, когда переданы все эссе',
        'en': 'Streak: shown once all essays are shared',
    },
    'application_line': {
        'uz': 'Ariza: {percent}%',
        'ru': 'Заявка: {percent}%',
        'en': 'Application: {percent}%',
    },
    'section_personal': {'uz': 'Shaxsiy', 'ru': 'Личное', 'en': 'Personal'},
    'section_academics': {'uz': "O'qish", 'ru': 'Учёба', 'en': 'Academics'},
    'section_tests': {'uz': 'Testlar', 'ru': 'Тесты', 'en': 'Tests'},
    'section_goal': {'uz': 'Maqsad', 'ru': 'Цель', 'en': 'Goal'},
    'section_activities': {'uz': 'Faoliyatlar', 'ru': 'Активности', 'en': 'Extracurriculars'},
    'section_honors': {'uz': 'Yutuqlar', 'ru': 'Достижения', 'en': 'Honors'},
    'application_counts': {
        'uz': 'Faoliyatlar {activities}, yutuqlar {honors}, hujjatlar {docs_done}/{docs_total}, arizalar {apps_done}/{apps_total}, tavsiyalar {rec_done}/{rec_total}',
        'ru': 'Активности {activities}, достижения {honors}, документы {docs_done}/{docs_total}, заявки {apps_done}/{apps_total}, рекомендации {rec_done}/{rec_total}',
        'en': 'Extracurriculars {activities}, honors {honors}, documents {docs_done}/{docs_total}, applications {apps_done}/{apps_total}, letters {rec_done}/{rec_total}',
    },
    'expired': {
        'uz': "Muddati o'tdi. Yangisini olish uchun /now.",
        'ru': 'Устарело. Получить новую сводку: /now.',
        'en': 'This expired. Send /now for a fresh update.',
    },
    'unavailable': {
        'uz': "Xizmat vaqtincha ishlamayapti. Birozdan so'ng qayta urinib ko'ring.",
        'ru': 'Сервис временно недоступен. Попробуйте чуть позже.',
        'en': 'The service is temporarily unavailable. Please try again shortly.',
    },
    'add_prompt': {
        'uz': "Yangi o'quvchi ma'lumotlarini bitta xabarda yuboring:\n\n<i>Familiya Ism\nemail@gmail.com\n+998 90 123 45 67</i>",
        'ru': 'Отправьте данные нового ученика одним сообщением:\n\n<i>Фамилия Имя\nemail@gmail.com\n+998 90 123 45 67</i>',
        'en': "Send the new student's details in one message:\n\n<i>Last name First name\nemail@gmail.com\n+998 90 123 45 67</i>",
    },
    'add_missing': {
        'uz': "Topilmadi: {missing}. Ism, email va telefonni bitta xabarda qayta yuboring yoki /cancel.",
        'ru': 'Не найдено: {missing}. Отправьте имя, email и телефон одним сообщением ещё раз или /cancel.',
        'en': 'Missing: {missing}. Send the name, email and phone again in one message, or /cancel.',
    },
    'field_full_name': {'uz': 'ism', 'ru': 'имя', 'en': 'name'},
    'field_email': {'uz': 'email', 'ru': 'email', 'en': 'email'},
    'field_phone': {'uz': 'telefon', 'ru': 'телефон', 'en': 'phone'},
    'add_card': {
        'uz': "Yangi o'quvchi qo'shilsinmi?\n\n<b>{name}</b>\n{email}\n{phone}\n\nMaktab: sizning maktabingiz. Vaqtinchalik parol avtomatik yaratiladi.",
        'ru': 'Добавить нового ученика?\n\n<b>{name}</b>\n{email}\n{phone}\n\nШкола: ваша школа. Временный пароль создаётся автоматически.',
        'en': 'Add this new student?\n\n<b>{name}</b>\n{email}\n{phone}\n\nSchool: your school. A temporary password is made automatically.',
    },
    'add_yes': {'uz': "✅ Qo'shish", 'ru': '✅ Добавить', 'en': '✅ Add'},
    'add_no': {'uz': '✖ Bekor qilish', 'ru': '✖ Отмена', 'en': '✖ Cancel'},
    'add_adding': {
        'uz': "Qo'shilmoqda...",
        'ru': 'Добавляем...',
        'en': 'Adding...',
    },
    'add_done': {
        'uz': "✅ O'quvchi qo'shildi: <b>{name}</b>\n\nLogin: <code>{username}</code>\nVaqtinchalik parol: <code>{password}</code>\nAmal qiladi: {expires} gacha\nSayt: {url}\n\nShu ma'lumotni o'quvchiga yuboring. Birinchi kirishda o'z parolini o'rnatadi. Yuborgach, bu xabarni o'chirib qo'ying.",
        'ru': '✅ Ученик добавлен: <b>{name}</b>\n\nЛогин: <code>{username}</code>\nВременный пароль: <code>{password}</code>\nДействует до: {expires}\nСайт: {url}\n\nПередайте эти данные ученику. При первом входе он задаст свой пароль. После отправки удалите это сообщение.',
        'en': '✅ Student added: <b>{name}</b>\n\nLogin: <code>{username}</code>\nTemporary password: <code>{password}</code>\nValid until: {expires}\nWebsite: {url}\n\nSend these to the student. They set their own password at first login. Delete this message once sent.',
    },
    'add_cancelled': {
        'uz': "Bekor qilindi. Hech narsa qo'shilmadi.",
        'ru': 'Отменено. Ничего не добавлено.',
        'en': 'Cancelled. Nothing was added.',
    },
    'add_invalid_name': {
        'uz': "Ism noto'g'ri. Qayta yuboring: /add",
        'ru': 'Неверное имя. Отправьте заново: /add',
        'en': 'The name is not valid. Try again: /add',
    },
    'add_invalid_email': {
        'uz': "Email noto'g'ri. Qayta yuboring: /add",
        'ru': 'Неверный email. Отправьте заново: /add',
        'en': 'The email is not valid. Try again: /add',
    },
    'add_invalid_phone': {
        'uz': "Telefon raqami noto'g'ri. Qayta yuboring: /add",
        'ru': 'Неверный номер телефона. Отправьте заново: /add',
        'en': 'The phone number is not valid. Try again: /add',
    },
    'add_exists': {
        'uz': "Bu o'quvchi allaqachon bor: <b>{name}</b> (login: <code>{username}</code>). Yangi hisob ochilmadi.",
        'ru': 'Этот ученик уже есть: <b>{name}</b> (логин: <code>{username}</code>). Новый аккаунт не создан.',
        'en': 'This student already exists: <b>{name}</b> (login: <code>{username}</code>). No new account was made.',
    },
    'add_exists_elsewhere': {
        'uz': "Bu email yoki telefon bilan maktabingizda boshqa maslahatchining o'quvchisi bor. Yangi hisob ochilmadi. Maktab administratoriga murojaat qiling.",
        'ru': 'С этим email или телефоном в вашей школе уже есть ученик другого консультанта. Новый аккаунт не создан. Обратитесь к администратору школы.',
        'en': "A student with this email or phone already belongs to another counselor at your school. No new account was made. Contact your school administrator.",
    },
    'add_seat_limit': {
        'uz': "Maktabingiz tarifidagi o'quvchilar soni to'lgan. Yangi o'quvchi qo'shilmadi.",
        'ru': 'Лимит учеников по тарифу вашей школы исчерпан. Ученик не добавлен.',
        'en': "Your school's plan has no free student seats. The student was not added.",
    },
    'add_too_many': {
        'uz': "Bir soatda juda ko'p o'quvchi qo'shildi. Birozdan so'ng qayta urinib ko'ring.",
        'ru': 'Слишком много учеников за час. Попробуйте позже.',
        'en': 'Too many students added this hour. Please try again later.',
    },
    'btn_new_password': {'uz': '🔑 Yangi parol', 'ru': '🔑 Новый пароль', 'en': '🔑 New password'},
    'reset_prompt': {
        'uz': "Kimga yangi parol kerak? O'quvchining ismi, familiyasi yoki loginini yuboring.",
        'ru': 'Кому нужен новый пароль? Отправьте имя, фамилию или логин ученика.',
        'en': "Who needs a new password? Send the student's name, last name or login.",
    },
    'reset_short': {
        'uz': "Kamida 2 ta harf yuboring yoki /cancel.",
        'ru': 'Отправьте хотя бы 2 буквы или /cancel.',
        'en': 'Send at least 2 letters, or /cancel.',
    },
    'reset_none': {
        'uz': "\"{query}\" bo'yicha o'quvchingiz topilmadi. Boshqacha yozib ko'ring yoki /cancel.",
        'ru': 'Ученик по запросу «{query}» не найден. Попробуйте иначе или /cancel.',
        'en': 'No student of yours matches "{query}". Try another spelling, or /cancel.',
    },
    'reset_pick': {
        'uz': "Qaysi o'quvchi?",
        'ru': 'Какой ученик?',
        'en': 'Which student?',
    },
    'reset_more': {
        'uz': "Hammasi ko'rsatilmadi: aniqroq yozing (ism va familiya).",
        'ru': 'Показаны не все: уточните запрос (имя и фамилия).',
        'en': 'Not all are shown: be more specific (first and last name).',
    },
    'reset_card': {
        'uz': "<b>{name}</b> (login: <code>{username}</code>) uchun yangi vaqtinchalik parol yaratilsinmi?\n\nEski parol darhol ishlamay qoladi.",
        'ru': 'Создать новый временный пароль для <b>{name}</b> (логин: <code>{username}</code>)?\n\nСтарый пароль сразу перестанет работать.',
        'en': 'Make a new temporary password for <b>{name}</b> (login: <code>{username}</code>)?\n\nThe old password stops working at once.',
    },
    'reset_card_no_login': {
        'uz': "<b>{name}</b> uchun yangi vaqtinchalik parol yaratilsinmi?\n\nEski parol darhol ishlamay qoladi.",
        'ru': 'Создать новый временный пароль для <b>{name}</b>?\n\nСтарый пароль сразу перестанет работать.',
        'en': 'Make a new temporary password for <b>{name}</b>?\n\nThe old password stops working at once.',
    },
    'reset_yes': {'uz': '🔑 Yangi parol', 'ru': '🔑 Новый пароль', 'en': '🔑 New password'},
    'reset_working': {
        'uz': 'Yangi parol yaratilmoqda...',
        'ru': 'Создаём новый пароль...',
        'en': 'Making a new password...',
    },
    'reset_done': {
        'uz': "🔑 Yangi parol tayyor: <b>{name}</b>\n\nLogin: <code>{username}</code>\nVaqtinchalik parol: <code>{password}</code>\nAmal qiladi: {expires} gacha\nSayt: {url}\n\nShu ma'lumotni o'quvchiga yuboring. Kirgach, o'z parolini o'rnatadi. Yuborgach, bu xabarni o'chirib qo'ying.",
        'ru': '🔑 Новый пароль готов: <b>{name}</b>\n\nЛогин: <code>{username}</code>\nВременный пароль: <code>{password}</code>\nДействует до: {expires}\nСайт: {url}\n\nПередайте эти данные ученику. После входа он задаст свой пароль. После отправки удалите это сообщение.',
        'en': '🔑 New password ready: <b>{name}</b>\n\nLogin: <code>{username}</code>\nTemporary password: <code>{password}</code>\nValid until: {expires}\nWebsite: {url}\n\nSend these to the student. They set their own password after signing in. Delete this message once sent.',
    },
    'reset_cancelled': {
        'uz': "Bekor qilindi. Parol o'zgarmadi.",
        'ru': 'Отменено. Пароль не изменён.',
        'en': 'Cancelled. The password was not changed.',
    },
    'reset_not_found': {
        'uz': "Bu o'quvchi endi ro'yxatingizda yo'q. Parol o'zgarmadi.",
        'ru': 'Этого ученика больше нет в вашем списке. Пароль не изменён.',
        'en': 'This student is no longer on your list. The password was not changed.',
    },
    'reset_too_many': {
        'uz': "Bir soatda juda ko'p parol yangilandi. Birozdan so'ng qayta urinib ko'ring.",
        'ru': 'Слишком много новых паролей за час. Попробуйте позже.',
        'en': 'Too many passwords reset this hour. Please try again later.',
    },
    'student_code': {
        'uz': "\U0001F511 Kodingiz: <code>{code}</code>\n\nUni Naseeb saytidagi <b>Meetings</b> sahifasiga kiriting. Kod {minutes} daqiqa amal qiladi.\n{url}\n\nShundan so'ng uchrashuv xabarlari va eslatmalar shu yerga keladi.",
        'ru': '\U0001F511 Ваш код: <code>{code}</code>\n\nВведите его на странице <b>Meetings</b> на сайте Naseeb. Код действует {minutes} мин.\n{url}\n\nПосле этого сообщения и напоминания о встречах будут приходить сюда.',
        'en': '\U0001F511 Your code: <code>{code}</code>\n\nEnter it on the <b>Meetings</b> page of the Naseeb website. It is valid for {minutes} minutes.\n{url}\n\nAfter that, meeting messages and reminders come here.',
    },
    'student_code_linked': {
        'uz': 'Bu chat hozir ulangan: <b>{name}</b>.',
        'ru': 'Этот чат сейчас привязан: <b>{name}</b>.',
        'en': 'This chat is linked now: <b>{name}</b>.',
    },
    'btn_new_code': {'uz': '\U0001F504 Yangi kod', 'ru': '\U0001F504 Новый код', 'en': '\U0001F504 New code'},
    'student_code_too_many': {
        'uz': "Juda ko'p kod so'raldi. Birozdan so'ng qayta urinib ko'ring.",
        'ru': 'Слишком много кодов. Попробуйте позже.',
        'en': 'Too many codes requested. Please try again later.',
    },
    'error': {
        'uz': "Xatolik yuz berdi. Qayta urinib ko'ring.",
        'ru': 'Произошла ошибка. Попробуйте ещё раз.',
        'en': 'Something went wrong. Please try again.',
    },
    'help': {
        'uz': "/start - kirish\n/now - hozir yangilanish\n/students - o'quvchilar\n/add - yangi o'quvchi qo'shish\n/reset - o'quvchiga yangi parol\n/settings - vaqt, til, nimalar kelishi\n/logout - chiqish va ma'lumotlarni o'chirish\n/help - yordam",
        'ru': '/start - вход\n/now - сводка сейчас\n/students - ученики\n/add - добавить ученика\n/reset - новый пароль ученику\n/settings - время, язык, состав сводки\n/logout - выйти и удалить данные\n/help - помощь',
        'en': '/start - log in\n/now - update now\n/students - list students\n/add - add a student\n/reset - new password for a student\n/settings - time, language, contents\n/logout - log out and wipe data\n/help - this help',
    },
}

# The command list behind Telegram's "Menu" button.
MENU = {
    'uz': [
        ('add', "Yangi o'quvchi qo'shish"), ('reset', "O'quvchiga yangi parol"), ('students', "O'quvchilar"),
        ('now', 'Hozirgi holat'), ('settings', 'Sozlamalar'), ('help', 'Yordam'), ('logout', 'Chiqish'),
        ('code', "O'quvchi: saytga ulash kodi"),
    ],
    'ru': [
        ('add', 'Добавить ученика'), ('reset', 'Новый пароль ученику'), ('students', 'Ученики'),
        ('now', 'Сводка сейчас'), ('settings', 'Настройки'), ('help', 'Помощь'), ('logout', 'Выйти'),
        ('code', 'Ученик: код для сайта'),
    ],
    'en': [
        ('add', 'Add a student'), ('reset', 'New password for a student'), ('students', 'Students'),
        ('now', 'Update now'), ('settings', 'Settings'), ('help', 'Help'), ('logout', 'Log out'),
        ('code', 'Student: code for the website'),
    ],
}


def t(lang, key, **values):
    entry = STRINGS[key]
    text = entry.get(lang) or entry[DEFAULT]
    return text.format(**values) if values else text
