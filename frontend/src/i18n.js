import { uiMessages } from './translations/ui.js'

const LANGUAGE_KEY = 'naseeb-edu-language-v1'

export const LANGUAGE_OPTIONS = [
  { value: 'uz', label: 'O‘zbekcha', short: 'UZ' },
  { value: 'ru', label: 'Русский', short: 'RU' },
  { value: 'en', label: 'English', short: 'EN' },
]

const LOCALES = { uz: 'uz-UZ', ru: 'ru-RU', en: 'en-GB' }

export const TRANSLATIONS = {
  uz: {
    ...uiMessages('uz'),
    'Education Counseling Platform': 'Ta’lim bo‘yicha maslahat platformasi',
    'Dashboard': 'Bosh sahifa', 'Schools': 'Maktablar', 'Students': 'O‘quvchilar', 'My profile': 'Mening profilim',
    'Academics': 'Akademik ma’lumotlar', 'Portfolio': 'Portfolio', 'Activities': 'Faoliyatlar', 'Recommendations': 'Tavsiyanomalar',
    'Tasks': 'Vazifalar', 'Applications': 'Arizalar', 'Documents': 'Hujjatlar', 'Certificates': 'Sertifikatlar',
    'Essays': 'Esselar', 'Student Center': 'O‘quvchi markazi', 'Roadmap': 'Yo‘l xaritasi', 'Community': 'Hamjamiyat',
    'Meetings': 'Uchrashuvlar', 'Messages': 'Xabarlar', 'Program Usage': 'Dasturdan foydalanish', 'Programs': 'Dasturlar',
    'Resource Index': 'Resurslar', 'Essay Lab': 'Esse laboratoriyasi', 'College Search': 'Universitet qidiruvi',
    'Naseeb Store': 'Naseeb do‘koni', 'Contacts': 'Kontaktlar', 'Support': 'Yordam', 'Screen Time': 'Ekran vaqti', 'Progress': 'Jarayon',
    'A complete view of the application journey': 'Ariza jarayonining to‘liq ko‘rinishi',
    'Schools and organization accounts': 'Maktablar va tashkilot akkauntlari',
    'Student profiles and progress': 'O‘quvchi profillari va jarayoni',
    'Your personal application profile': 'Shaxsiy ariza profilingiz',
    'Academic results and research': 'Akademik natijalar va tadqiqotlar',
    'Projects and internship experience': 'Loyihalar va amaliyot tajribasi',
    'Activities, honors, and achievements': 'Faoliyatlar, mukofotlar va yutuqlar',
    'Recommendation letter progress': 'Tavsiyanomalar jarayoni',
    'Assignments and deadline tracking': 'Vazifalar va muddatlar nazorati',
    'University application pipeline': 'Universitet arizalari jarayoni',
    'Documents, uploads, and review': 'Hujjatlar, yuklash va tekshiruv',
    'Certificates and supporting files': 'Sertifikatlar va qo‘shimcha fayllar',
    'Essay drafts and revision history': 'Esse qoralamalari va tahrir tarixi',
    'Academic profile, portfolio, activities, and documents': 'Akademik profil, portfolio, faoliyat va hujjatlar',
    'Level-linked missions, milestones, and reflections': 'Darajaga bog‘langan missiyalar va bosqichlar',
    'Student discussions, questions, and shared experience': 'O‘quvchilar muhokamasi va tajriba almashuvi',
    'Schedule and manage meetings': 'Uchrashuvlarni rejalashtirish va boshqarish',
    'Direct, Group, Community, and Discussion messages': 'Shaxsiy, guruh va hamjamiyat xabarlari',
    'Services, mentors, and usage balance': 'Xizmatlar, mentorlar va foydalanish balansi',
    'National and international opportunity catalog': 'Mahalliy va xalqaro imkoniyatlar katalogi',
    'All tools and resources for students': 'O‘quvchilar uchun barcha vosita va resurslar',
    'Essay drafts, feedback, and revision history': 'Esse qoralamalari, fikrlar va tahrir tarixi',
    'Find, compare, and shortlist universities': 'Universitetlarni qidiring, solishtiring va tanlang',
    'Additional education and application services': 'Qo‘shimcha ta’lim va ariza xizmatlari',
    'Contact your counselor and school coordinator': 'Counselor va maktab koordinatori bilan bog‘laning',
    'Contact support and track your requests': 'Yordamga murojaat qiling va so‘rovlarni kuzating',
    'Active learning time without idle minutes': 'Bekor vaqtni hisoblamaydigan faol o‘qish vaqti',
    'Sign in': 'Kirish', 'Enter your username and password.': 'Login va parolingizni kiriting.',
    'Username': 'Login', 'Password': 'Parol', 'Signing in…': 'Kirilmoqda…',
    'Every opportunity.': 'Har bir imkoniyat.', 'One trusted path.': 'Bir ishonchli yo‘l.',
    'A professional counseling platform connecting students in Uzbekistan with global education opportunities.': 'O‘zbekistondagi o‘quvchilarni global ta’lim imkoniyatlari bilan bog‘lovchi professional maslahat platformasi.',
    'Bridging Uzbekistan to the World Through Education': 'O‘zbekistonni ta’lim orqali dunyo bilan bog‘laymiz',
    'Change temporary password': 'Vaqtinchalik parolni o‘zgartirish',
    'Create a permanent password before opening your cabinet.': 'Kabinetga kirishdan oldin doimiy parol yarating.',
    'New password': 'Yangi parol', 'Confirm password': 'Parolni tasdiqlang', 'Save new password': 'Yangi parolni saqlash',
    'Saving securely…': 'Xavfsiz saqlanmoqda…', 'Sign out': 'Chiqish',
    'Use at least 12 characters with upper/lowercase letters and a number.': 'Kamida 12 belgi, katta-kichik harf va raqam ishlating.',
    'Your temporary password has already been consumed. If you leave now, an administrator must reissue it.': 'Vaqtinchalik parol ishlatildi. Hozir chiqsangiz, administrator yangi parol berishi kerak.',
    'Search…': 'Qidirish…', 'Refresh': 'Yangilash', 'Logout': 'Chiqish',
    'You are offline': 'Internet aloqasi yo‘q', 'Current information remains available. Reconnect before saving changes.': 'Joriy ma’lumotlar ko‘rinadi. O‘zgarishlarni saqlashdan oldin internetga qayta ulaning.',
    'Light mode': 'Yorug‘ rejim', 'Dark mode': 'Tungi rejim', 'Switch to light mode': 'Yorug‘ rejimga o‘tish', 'Switch to dark mode': 'Tungi rejimga o‘tish',
    'Language': 'Til', 'Temporary login': 'Vaqtinchalik login', 'Reset login': 'Login parolini yangilash',
    'Issue a new one-time password': 'Yangi bir martalik parol berish', 'Generate temporary password': 'Vaqtinchalik parol yaratish',
    'Generated password': 'Yaratilgan parol', 'Copy password': 'Parolni nusxalash', 'Copied': 'Nusxalandi',
    'Close': 'Yopish', 'Cancel': 'Bekor qilish', 'expires': 'amal qilish muddati',
    'Passwords do not match.': 'Parollar bir xil emas.', 'Temporary password': 'Vaqtinchalik parol',
    'The password is shown once. Send it through an approved secure channel.': 'Parol faqat bir marta ko‘rsatiladi. Uni tasdiqlangan xavfsiz kanal orqali yuboring.',
    'This revokes existing sessions and any previous temporary password.': 'Bu mavjud sessiyalarni va avvalgi vaqtinchalik parolni bekor qiladi.',
    'Admin': 'Admin', 'School Counselor': 'Maktab counselori', 'Teacher': 'O‘qituvchi', 'Organization School': 'Maktab tashkiloti', 'Student': 'O‘quvchi', 'Parent': 'Ota-ona',
    'To do': 'Bajarish kerak', 'In progress': 'Jarayonda', 'Submitted': 'Topshirildi', 'Approved': 'Tasdiqlandi', 'Late': 'Kechikkan',
    'Required': 'Talab qilinadi', 'Uploaded': 'Yuklandi', 'Reviewing': 'Tekshirilmoqda', 'Rejected': 'Rad etildi',
    'No information available yet.': 'Hozircha ma’lumot yo‘q.', 'No students found.': 'O‘quvchilar topilmadi.',
    'Add': 'Qo‘shish', 'Edit': 'Tahrirlash', 'Delete': 'O‘chirish', 'Save': 'Saqlash', 'Saving…': 'Saqlanmoqda…',
    'Preview': 'Ko‘rish', 'Download': 'Yuklab olish', 'Approve': 'Tasdiqlash', 'View all': 'Barchasini ko‘rish',
    'Student': 'O‘quvchi', 'School': 'Maktab', 'Grade': 'Sinf', 'Counselor': 'Counselor', 'Major': 'Yo‘nalish',
    'Countries': 'Davlatlar', 'Scholarship': 'Stipendiya', 'Needed': 'Kerak', 'Not needed': 'Kerak emas',
    'Level': 'Daraja', 'Assigned tasks': 'Biriktirilgan vazifalar', 'Profile': 'Profil', 'Profile overview': 'Profil haqida',
    'Mother': 'Ona', 'Father': 'Ota', 'Guardian': 'Vasiy', 'Open': 'Ochiq', 'Closed': 'Yopiq', 'Resolved': 'Hal qilindi',
    'Pending': 'Kutilmoqda', 'Active': 'Faol', 'Completed': 'Tugallangan', 'Cancelled': 'Bekor qilingan',
    'Low': 'Past', 'Medium': 'O‘rta', 'High': 'Yuqori', 'Urgent': 'Shoshilinch', 'Draft': 'Qoralama',
    'Select university': 'Universitetni tanlang', 'General essay': 'Umumiy esse',
  },
  ru: {
    ...uiMessages('ru'),
    'Education Counseling Platform': 'Платформа образовательного консультирования',
    'Dashboard': 'Главная', 'Schools': 'Школы', 'Students': 'Ученики', 'My profile': 'Мой профиль', 'Academics': 'Учёба',
    'Portfolio': 'Портфолио', 'Activities': 'Активности', 'Recommendations': 'Рекомендации', 'Tasks': 'Задания',
    'Applications': 'Заявки', 'Documents': 'Документы', 'Certificates': 'Сертификаты', 'Essays': 'Эссе',
    'Student Center': 'Центр ученика', 'Roadmap': 'Дорожная карта', 'Community': 'Сообщество', 'Meetings': 'Встречи',
    'Messages': 'Сообщения', 'Program Usage': 'Использование программы', 'Programs': 'Программы', 'Resource Index': 'Ресурсы',
    'Essay Lab': 'Лаборатория эссе', 'College Search': 'Поиск университетов', 'Naseeb Store': 'Магазин Naseeb',
    'Contacts': 'Контакты', 'Support': 'Поддержка', 'Screen Time': 'Экранное время', 'Progress': 'Прогресс',
    'A complete view of the application journey': 'Полная картина процесса поступления',
    'Schools and organization accounts': 'Школы и аккаунты организаций', 'Student profiles and progress': 'Профили и прогресс учеников',
    'Your personal application profile': 'Ваш личный профиль поступления', 'Academic results and research': 'Учебные результаты и исследования',
    'Projects and internship experience': 'Проекты и опыт стажировок', 'Activities, honors, and achievements': 'Активности, награды и достижения',
    'Recommendation letter progress': 'Статус рекомендательных писем', 'Assignments and deadline tracking': 'Задания и контроль сроков',
    'University application pipeline': 'Процесс подачи заявок', 'Documents, uploads, and review': 'Документы, загрузка и проверка',
    'Certificates and supporting files': 'Сертификаты и дополнительные файлы', 'Essay drafts and revision history': 'Черновики эссе и история правок',
    'Academic profile, portfolio, activities, and documents': 'Учебный профиль, портфолио, активности и документы',
    'Level-linked missions, milestones, and reflections': 'Миссии, этапы и рефлексии по уровням',
    'Student discussions, questions, and shared experience': 'Обсуждения, вопросы и обмен опытом',
    'Schedule and manage meetings': 'Планирование и управление встречами', 'Direct, Group, Community, and Discussion messages': 'Личные, групповые и общие сообщения',
    'Services, mentors, and usage balance': 'Услуги, наставники и баланс использования', 'National and international opportunity catalog': 'Каталог местных и международных возможностей',
    'All tools and resources for students': 'Все инструменты и ресурсы для учеников', 'Essay drafts, feedback, and revision history': 'Черновики, отзывы и история правок',
    'Find, compare, and shortlist universities': 'Поиск, сравнение и выбор университетов', 'Additional education and application services': 'Дополнительные образовательные услуги',
    'Contact your counselor and school coordinator': 'Связь с консультантом и координатором школы', 'Contact support and track your requests': 'Обращения в поддержку и их статус',
    'Active learning time without idle minutes': 'Активное учебное время без простоя',
    'Sign in': 'Войти', 'Enter your username and password.': 'Введите логин и пароль.', 'Username': 'Логин', 'Password': 'Пароль', 'Signing in…': 'Вход…',
    'Every opportunity.': 'Каждая возможность.', 'One trusted path.': 'Один надёжный путь.',
    'A professional counseling platform connecting students in Uzbekistan with global education opportunities.': 'Профессиональная платформа, соединяющая учеников Узбекистана с мировыми образовательными возможностями.',
    'Bridging Uzbekistan to the World Through Education': 'Соединяем Узбекистан с миром через образование',
    'Change temporary password': 'Измените временный пароль', 'Create a permanent password before opening your cabinet.': 'Создайте постоянный пароль перед входом в кабинет.',
    'New password': 'Новый пароль', 'Confirm password': 'Подтвердите пароль', 'Save new password': 'Сохранить новый пароль', 'Saving securely…': 'Безопасное сохранение…',
    'Sign out': 'Выйти', 'Use at least 12 characters with upper/lowercase letters and a number.': 'Используйте минимум 12 символов, строчные и заглавные буквы и цифру.',
    'Your temporary password has already been consumed. If you leave now, an administrator must reissue it.': 'Временный пароль уже использован. Если выйти сейчас, администратор должен выдать новый.',
    'Search…': 'Поиск…', 'Refresh': 'Обновить', 'Logout': 'Выйти', 'You are offline': 'Нет подключения',
    'Current information remains available. Reconnect before saving changes.': 'Текущие данные доступны. Подключитесь к интернету перед сохранением.',
    'Light mode': 'Светлая тема', 'Dark mode': 'Тёмная тема', 'Switch to light mode': 'Переключить на светлую тему', 'Switch to dark mode': 'Переключить на тёмную тему',
    'Language': 'Язык', 'Temporary login': 'Временный вход', 'Reset login': 'Сбросить пароль', 'Issue a new one-time password': 'Выдать новый одноразовый пароль',
    'Generate temporary password': 'Создать временный пароль', 'Generated password': 'Созданный пароль', 'Copy password': 'Скопировать пароль', 'Copied': 'Скопировано',
    'Close': 'Закрыть', 'Cancel': 'Отмена', 'expires': 'действует до',
    'Passwords do not match.': 'Пароли не совпадают.', 'Temporary password': 'Временный пароль',
    'The password is shown once. Send it through an approved secure channel.': 'Пароль показывается один раз. Передайте его через утверждённый защищённый канал.',
    'This revokes existing sessions and any previous temporary password.': 'Это завершит текущие сеансы и отменит предыдущий временный пароль.',
    'Admin': 'Администратор', 'School Counselor': 'Школьный консультант', 'Teacher': 'Учитель', 'Organization School': 'Школа', 'Student': 'Ученик', 'Parent': 'Родитель',
    'To do': 'К выполнению', 'In progress': 'В процессе', 'Submitted': 'Отправлено', 'Approved': 'Одобрено', 'Late': 'Просрочено',
    'Required': 'Требуется', 'Uploaded': 'Загружено', 'Reviewing': 'На проверке', 'Rejected': 'Отклонено',
    'No information available yet.': 'Пока нет информации.', 'No students found.': 'Ученики не найдены.',
    'Add': 'Добавить', 'Edit': 'Изменить', 'Delete': 'Удалить', 'Save': 'Сохранить', 'Saving…': 'Сохранение…',
    'Preview': 'Просмотр', 'Download': 'Скачать', 'Approve': 'Одобрить', 'View all': 'Показать все',
    'Student': 'Ученик', 'School': 'Школа', 'Grade': 'Класс', 'Counselor': 'Консультант', 'Major': 'Направление',
    'Countries': 'Страны', 'Scholarship': 'Стипендия', 'Needed': 'Нужна', 'Not needed': 'Не нужна',
    'Level': 'Уровень', 'Assigned tasks': 'Назначенные задания', 'Profile': 'Профиль', 'Profile overview': 'Обзор профиля',
    'Mother': 'Мать', 'Father': 'Отец', 'Guardian': 'Опекун', 'Open': 'Открыт', 'Closed': 'Закрыт', 'Resolved': 'Решён',
    'Pending': 'Ожидается', 'Active': 'Активен', 'Completed': 'Завершён', 'Cancelled': 'Отменён',
    'Low': 'Низкий', 'Medium': 'Средний', 'High': 'Высокий', 'Urgent': 'Срочный', 'Draft': 'Черновик',
    'Select university': 'Выберите университет', 'General essay': 'Общее эссе',
  },
  en: {},
}

let activeLanguage = 'en'

export function getLanguage() {
  if (typeof window === 'undefined') return activeLanguage
  try {
    const stored = window.localStorage.getItem(LANGUAGE_KEY)
    if (LANGUAGE_OPTIONS.some((option) => option.value === stored)) return stored
  } catch { /* Use browser preference. */ }
  const browserLanguage = window.navigator.language?.split('-')[0]
  return LANGUAGE_OPTIONS.some((option) => option.value === browserLanguage) ? browserLanguage : 'en'
}

export function setLanguage(language) {
  activeLanguage = LANGUAGE_OPTIONS.some((option) => option.value === language) ? language : 'en'
  if (typeof document !== 'undefined') document.documentElement.lang = activeLanguage
  try { window.localStorage.setItem(LANGUAGE_KEY, activeLanguage) } catch { /* Keep session language. */ }
  return activeLanguage
}

activeLanguage = getLanguage()

export function t(key, variables = {}) {
  const source = String(key ?? '')
  const translated = TRANSLATIONS[activeLanguage]?.[source] || source
  return Object.entries(variables).reduce((value, [name, replacement]) => {
    const localized = typeof replacement === 'number' ? formatNumberLocale(replacement) : String(replacement)
    return value.replaceAll(`{${name}}`, localized)
  }, translated)
}

export function tx(strings, ...values) {
  const variables = Object.fromEntries(values.map((value, index) => [String(index), value]))
  const key = strings.reduce((result, part, index) => `${result}${part}${index < values.length ? `{${index}}` : ''}`, '')
  return t(key, variables)
}

export const locale = () => LOCALES[activeLanguage] || LOCALES.en
export const formatDateLocale = (value, options = { day: '2-digit', month: 'short', year: 'numeric' }) => value ? new Intl.DateTimeFormat(locale(), options).format(new Date(value)) : '—'
export const formatNumberLocale = (value, options = {}) => new Intl.NumberFormat(locale(), options).format(Number(value) || 0)
export const formatPercentLocale = (value, options = {}) => new Intl.NumberFormat(locale(), { style: 'percent', maximumFractionDigits: 0, ...options }).format((Number(value) || 0) / 100)
export const formatCurrencyLocale = (value, currency = 'USD') => value === null || value === undefined ? '—' : new Intl.NumberFormat(locale(), { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(value))
