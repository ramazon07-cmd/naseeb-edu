// Review queue (pages/ReviewPage.jsx): English key -> [Uzbek (Latin), Russian].
export const REVIEW_TRANSLATIONS = {
  'No proof attached': ['Dalil biriktirilmagan', 'Подтверждение не приложено'],
  'You can still approve it if you checked it another way.': ['Boshqa yo‘l bilan tekshirgan bo‘lsangiz, baribir tasdiqlashingiz mumkin.', 'Вы можете подтвердить, если проверили это другим способом.'],
  'Documents, tasks and portfolio waiting for you': ['Sizni kutayotgan hujjatlar, topshiriqlar va portfolio', 'Документы, задания и портфолио, которые ждут вас'],
  'Open in new tab': ['Yangi oynada ochish', 'Открыть в новой вкладке'],
  'No file attached yet': ['Hali fayl biriktirilmagan', 'Файл ещё не прикреплён'],
  'There is nothing to approve until the student adds it. You can send it back with a note.': ['Talaba uni qo‘shmaguncha tasdiqlanadigan narsa yo‘q. Izoh bilan qaytarishingiz mumkin.', 'Одобрять нечего, пока студент его не добавит. Можно вернуть с комментарием.'],
  'Skip for now': ['Hozircha o‘tkazib yuborish', 'Пропустить пока'],
  '{i} of {n}': ['{n} tadan {i}', '{i} из {n}'],
  'Reviewed today': ['Bugun ko‘rib chiqilgan', 'Проверено сегодня'],
  'Sent back': ['Qaytarildi', 'Возвращено'],
  'Nothing reviewed yet today.': ['Bugun hali hech narsa ko‘rib chiqilmadi.', 'Сегодня вы ещё ничего не проверили.'],
  "Today's reviews could not be loaded.": ['Bugun ko‘rib chiqilganlarni yuklab bo‘lmadi.', 'Не удалось загрузить сегодняшние проверки.'],
};

export function reviewMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(REVIEW_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
