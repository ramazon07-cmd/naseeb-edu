// Student design parity (Dash): English key -> [Uzbek (Latin), Russian].
export const PARITY_DASH_TRANSLATIONS = {
  // Dashboard card recovery
  'This card did not load.': ['Bu karta yuklanmadi.', 'Эта карточка не загрузилась.'],
  // Notifications
  '{n} shown': ['{n} ta ko‘rsatildi', 'Показано: {n}'],
  // Screen Time
  'How much real study time you spend in the portal.': ['Portalda qancha vaqt haqiqatan o‘qishga ketayotgani.', 'Сколько реального учебного времени вы проводите в портале.'],
  'Active time per day': ['Kunlik faol vaqt', 'Активное время по дням'],
  'Minutes per day. Tap a bar to see the day.': ['Kuniga daqiqalar. Kunni ko‘rish uchun ustunga bosing.', 'Минуты в день. Нажмите на столбец, чтобы увидеть день.'],
  'Time per page': ['Sahifalar bo‘yicha vaqt', 'Время по страницам'],
  'No time per page yet': ['Sahifalar bo‘yicha vaqt hali yo‘q', 'Пока нет времени по страницам'],
  'It fills in as you use Tasks, Essay Lab, Programs and the other pages.': ['Vazifalar, Essay Lab, Dasturlar va boshqa sahifalardan foydalanganingiz sari to‘ladi.', 'Заполнится, когда вы будете пользоваться Задачами, Essay Lab, Программами и другими страницами.'],
  'Your privacy': ['Shaxsiy ma’lumotlaringiz', 'Ваша приватность'],
  'Only active time counts': ['Faqat faol vaqt hisoblanadi', 'Считается только активное время'],
  'The tab is open on screen and you used it in the last minute.': ['Sahifa ekranda ochiq va oxirgi bir daqiqada undan foydalangansiz.', 'Вкладка открыта на экране, и вы пользовались ею в последнюю минуту.'],
  'Only totals are stored': ['Faqat umumiy vaqt saqlanadi', 'Хранятся только итоги'],
  'Never your clicks or what you type.': ['Bosishlaringiz va yozganlaringiz hech qachon saqlanmaydi.', 'Никогда ваши нажатия или то, что вы печатаете.'],
  // Support
  'Support': ['Yordam', 'Поддержка'],
  'Help from the Naseeb team.': ['Naseeb jamoasidan yordam.', 'Помощь от команды Naseeb.'],
  'Your requests': ['Murojaatlaringiz', 'Ваши обращения'],
  'New response': ['Yangi javob', 'Новый ответ'],
  'Answered': ['Javob berilgan', 'Есть ответ'],
  'Waiting for a reply': ['Javob kutilmoqda', 'Ждёт ответа'],
  'No requests yet': ['Hali murojaat yo‘q', 'Обращений пока нет'],
  'Write to the Naseeb team. The reply arrives here, in the same thread.': ['Naseeb jamoasiga yozing. Javob shu yerga, o‘sha suhbatga keladi.', 'Напишите команде Naseeb. Ответ придёт сюда, в ту же ветку.'],
  'Write a subject and a message.': ['Mavzu va xabarni yozing.', 'Напишите тему и сообщение.'],
  'The Naseeb team replies here. New replies show a count next to Support in the menu.': ['Naseeb jamoasi shu yerda javob beradi. Yangi javoblar soni menyuda Yordam yonida ko‘rinadi.', 'Команда Naseeb ответит здесь. Число новых ответов видно рядом с «Поддержкой» в меню.'],
  'How support works': ['Yordam qanday ishlaydi', 'Как работает поддержка'],
  'You write a request: a subject and a few lines.': ['Murojaat yozasiz: mavzu va bir necha qator.', 'Вы пишете обращение: тема и пара строк.'],
  'The reply arrives in the same thread. Your history stays.': ['Javob o‘sha suhbatga keladi. Tarix saqlanib qoladi.', 'Ответ приходит в ту же ветку. История сохраняется.'],
  'New replies show a count next to Support in the menu.': ['Yangi javoblar soni menyuda Yordam yonida ko‘rinadi.', 'Число новых ответов видно рядом с «Поддержкой» в меню.'],
  // Account settings
  'Account settings': ['Akkaunt sozlamalari', 'Настройки аккаунта'],
  'Your email, language, password and who sees your data.': ['Email, til, parol va ma’lumotlaringizni kim ko‘rishi.', 'Email, язык, пароль и кто видит ваши данные.'],
  'Your name and class come from your school. Ask your counselor to change them.': ['Ism va sinfingiz maktabdan keladi. O‘zgartirish uchun maslahatchingizga murojaat qiling.', 'Имя и класс приходят из школы. Чтобы изменить их, обратитесь к консультанту.'],
  'Security': ['Xavfsizlik', 'Безопасность'],
  'Repeat new password': ['Yangi parolni takrorlang', 'Повторите новый пароль'],
  'Password rules': ['Parol qoidalari', 'Правила пароля'],
  'At least 8 characters': ['Kamida 8 ta belgi', 'Не менее 8 символов'],
  'Upper and lowercase letters and a number': ['Katta va kichik harflar hamda raqam', 'Заглавные и строчные буквы и цифра'],
  'Both passwords match': ['Ikkala parol bir xil', 'Пароли совпадают'],
  'done': ['bajarildi', 'выполнено'],
  'not yet': ['hali yo‘q', 'ещё нет'],
  'Your counselor sees your whole profile to help you apply. Parents see only the sections your counselor has switched on.': ['Maslahatchingiz arizaga yordam berish uchun butun profilingizni ko‘radi. Ota-onangiz faqat maslahatchingiz yoqqan bo‘limlarni ko‘radi.', 'Консультант видит весь профиль, чтобы помогать с поступлением. Родители видят только те разделы, которые включил консультант.'],
  'Sections this parent may see': ['Bu ota-ona ko‘ra oladigan bo‘limlar', 'Разделы, которые видит этот родитель'],
  'On': ['Yoqilgan', 'Вкл.'],
  'Off': ['O‘chirilgan', 'Выкл.'],
};

export function parityDashMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(PARITY_DASH_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
