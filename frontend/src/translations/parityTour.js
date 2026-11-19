// Student design parity (Tour): English key -> [Uzbek (Latin), Russian].
export const PARITY_TOUR_TRANSLATIONS = {
  '{n} overdue task|{n} overdue tasks': ['{n} ta muddati o‘tgan vazifa', '{n} просроченная задача|{n} просроченные задачи|{n} просроченных задач'],
  'These need your attention first. Send your response or ask your counselor for a new date.': ['Avval shularga e’tibor bering. Javobingizni yuboring yoki maslahatchidan yangi sana so‘rang.', 'Начните с них. Отправьте ответ или попросите консультанта перенести дату.'],
  '+{n} more overdue': ['Yana {n} ta muddati o‘tgan', 'Ещё просрочено: {n}'],
  'Ignore': ['E’tiborsiz qoldirish', 'Пропустить'],
  'Go to Tasks': ['Vazifalarga o‘tish', 'Перейти к задачам'],
  'Welcome to Naseeb Edu': ['Naseeb Edu’ga xush kelibsiz', 'Добро пожаловать в Naseeb Edu'],
  'A one-minute tour of the places you will use most. You can skip it at any time and replay it from your account menu.': ['Eng ko‘p ishlatadigan joylaringiz bo‘yicha bir daqiqalik tur. Istalgan vaqt o‘tkazib yuborishingiz va profil menyusidan qayta ko‘rishingiz mumkin.', 'Минутный тур по местам, которыми вы будете пользоваться чаще всего. Его можно пропустить в любой момент и пересмотреть из меню профиля.'],
  'Welcome! Your progress at a glance': ['Xush kelibsiz! Natijalaringiz bir qarashda', 'Добро пожаловать! Прогресс с первого взгляда'],
  'Open tasks, universities on your list and how far you are on your roadmap. Tap a card to open it.': ['Ochiq vazifalar, ro‘yxatdagi universitetlar va yo‘l xaritasidagi yutug‘ingiz. Kartani bossangiz, o‘sha bo‘lim ochiladi.', 'Открытые задачи, вузы в списке и прогресс по дорожной карте. Нажмите на карточку, чтобы открыть раздел.'],
  'Take 7 short free tests to discover the majors that fit you. Not sure what to study? Start here.': ['7 ta qisqa bepul testdan o‘tib, o‘zingizga mos yo‘nalishlarni toping. Nima o‘qishni bilmasangiz, shu yerdan boshlang.', 'Пройдите 7 коротких бесплатных тестов, чтобы найти подходящие специальности. Не знаете, что изучать? Начните здесь.'],
  '150+ competitions, summer schools and scholarships for your grade. Save the ones you like to My List.': ['Sinfingizga mos 150 dan ortiq tanlov, yozgi maktab va grantlar. Yoqqanlarini «Mening ro‘yxatim»ga saqlang.', 'Более 150 конкурсов, летних школ и стипендий для вашего класса. Сохраняйте понравившиеся в «Мой список».'],
  'Track every university on your list, its stage and deadlines.': ['Ro‘yxatingizdagi har bir universitet, uning bosqichi va muddatlarini kuzating.', 'Следите за каждым вузом в списке, его этапом и сроками.'],
  'One button: calmer background, larger text and softer colors. Tap it again to go back to normal.': ['Bitta tugma: fon tinchlanadi, matn kattalashadi, ranglar ko‘zga yumshoq bo‘ladi. Yana bossangiz, hammasi avvalgi holatga qaytadi.', 'Одна кнопка: спокойный фон, крупнее текст и мягкие цвета. Нажмите ещё раз — всё вернётся как было.'],
  'Your profile menu': ['Profil menyusi', 'Меню профиля'],
  'Support, sign out — and this tour, any time you need it.': ['Yordam, chiqish — va kerak bo‘lganda shu tur.', 'Поддержка, выход — и этот тур, когда понадобится.'],
  'You are all set': ['Hammasi tayyor', 'Всё готово'],
  'That is everything you need to get going. Replay this tour any time from your account menu.': ['Boshlash uchun kerak bo‘lgan hamma narsa shu. Turni istalgan vaqt profil menyusidan qayta ko‘rishingiz mumkin.', 'Это всё, что нужно для старта. Тур можно пересмотреть в любой момент из меню профиля.'],
  '{current} of {total}': ['{current} / {total}', '{current} из {total}'],
  'Start the tour': ['Turni boshlash', 'Начать тур'],
  'Maybe later': ['Keyinroq', 'Позже'],
  'Skip': ['O‘tkazib yuborish', 'Пропустить'],
  'Back': ['Orqaga', 'Назад'],
  'Next': ['Keyingi', 'Далее'],
  'Take the tour': ['Turni ko‘rish', 'Пройти тур'],
};

export function parityTourMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(PARITY_TOUR_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
