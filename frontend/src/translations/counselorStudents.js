// Counselor Students list and quick look (pages/CounselorStudents.jsx, components/StudentQuickPanel.jsx):
// English key -> [Uzbek (Latin), Russian]. Russian plural keys hold "one|few|many" forms.
export const COUNSELOR_STUDENTS_TRANSLATIONS = {
  'Your students and what they need from you': ['O‘quvchilaringiz va ularga sizdan nima kerak', 'Ваши ученики и что им от вас нужно'],
  'Late work': ['Kechikkan ishlar', 'Просроченные работы'],
  'Missing documents': ['Yetishmayotgan hujjatlar', 'Недостающие документы'],
  'Needs you first': ['Avval sizga muhtojlar', 'Сначала те, кому нужны вы'],
  'Most late work': ['Eng ko‘p kechikkan ish', 'Больше всего просрочек'],
  'Name A–Z': ['Ism A–Z', 'Имя А–Я'],
  'Needs you': ['Sizga muhtoj', 'Нужна ваша помощь'],
  'Quiet': ['Faol emas', 'Неактивен'],
  'No late work': ['Kechikkan ish yo‘q', 'Просрочек нет'],
  'Quick look at {name}': ['{name}: qisqacha ko‘rish', 'Быстрый просмотр: {name}'],
  'Any level': ['Istalgan daraja', 'Любой уровень'],
  'Any grade': ['Istalgan sinf', 'Любой класс'],
  'Target country': ['Maqsad mamlakat', 'Целевая страна'],
  'Any country': ['Istalgan mamlakat', 'Любая страна'],
  'Remove filter: {name}': ['Filtrni olib tashlash: {name}', 'Убрать фильтр: {name}'],
  'Clear filters': ['Filtrlarni tozalash', 'Сбросить фильтры'],
  'Table': ['Jadval', 'Таблица'],
  'Previous': ['Oldingi', 'Назад'],
  'Cards': ['Kartalar', 'Карточки'],
  'No students match these filters.': ['Bu filtrlarga mos o‘quvchi yo‘q.', 'Нет учеников, подходящих под эти фильтры.'],
  'Showing {from}–{to} of {n} student|Showing {from}–{to} of {n} students': ['{n} ta o‘quvchidan {from}–{to} ko‘rsatilmoqda', 'Показаны {from}–{to} из {n} ученика|Показаны {from}–{to} из {n} учеников|Показаны {from}–{to} из {n} учеников'],
  'Page {p} of {total}': ['{total} sahifadan {p}-sahifa', 'Страница {p} из {total}'],
  'Click a student for a quick look; “Open student” shows their Student 360.': ['Qisqacha ko‘rish uchun o‘quvchini bosing; “O‘quvchini ochish” O‘quvchi 360 sahifasini ochadi.', 'Нажмите на ученика для быстрого просмотра; «Открыть ученика» покажет его «Ученик 360».'],
  'Quick look': ['Qisqacha ko‘rish', 'Быстрый просмотр'],
  'What needs attention': ['E’tibor talab qiladigan ishlar', 'Что требует внимания'],
  'Their deadlines this week': ['Uning shu haftadagi muddatlari', 'Сроки ученика на этой неделе'],
  'Private notes and drafts are never shown here.': ['Shaxsiy qaydlar va qoralamalar bu yerda hech qachon ko‘rsatilmaydi.', 'Личные заметки и черновики здесь никогда не показываются.'],
  'Late task: {title}': ['Kechikkan vazifa: {title}', 'Просроченная задача: {title}'],
  'Late mission: {title}': ['Kechikkan missiya: {title}', 'Просроченная миссия: {title}'],
  'To review: {title}': ['Tekshirish kerak: {title}', 'На проверку: {title}'],
  'Letter from {name}': ['{name} tavsiyanomasi', 'Письмо от {name}'],
  'due {date}': ['muddati {date}', 'срок {date}'],
  '{n} more in Student 360|{n} more in Student 360': ['O‘quvchi 360 da yana {n} ta', 'Ещё {n} в «Ученик 360»|Ещё {n} в «Ученик 360»|Ещё {n} в «Ученик 360»'],
  // Student 360 documents and essays (components/documents.jsx).
  'No file uploaded yet.': ['Hali fayl yuklanmagan.', 'Файл ещё не загружен.'],
  'Uploaded {0}': ['{0} yuklangan', 'Загружено {0}'],
  'Approved {0}': ['{0} tasdiqlangan', 'Одобрено {0}'],
  'Sent back {0}': ['{0} qaytarilgan', 'Возвращено {0}'],
  'Review history could not be loaded: {0}': ['Ko‘rib chiqish tarixini yuklab bo‘lmadi: {0}', 'Не удалось загрузить историю проверки: {0}'],
  'No comments yet.': ['Hali izohlar yo‘q.', 'Комментариев пока нет.'],
  'Suggested edits': ['Taklif qilingan tahrirlar', 'Предложенные правки'],
};

export function counselorStudentsMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(COUNSELOR_STUDENTS_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
