// Blue Meetings, Messages and Notifications pages: English key -> [Uzbek (Latin), Russian].
// One module per area, so parallel work never edits the same file.
export const BLUE_MEETINGS_TRANSLATIONS = {
  'Meetings summary': ['Uchrashuvlar xulosasi', 'Сводка по встречам'],
  'Past meetings': ['O‘tgan uchrashuvlar', 'Прошедшие встречи'],
  'Minutes in meetings': ['Uchrashuvlarda o‘tkazilgan daqiqalar', 'Минут на встречах'],
  'Upcoming · {0}': ['Kelgusi · {0}', 'Предстоящие · {0}'],
  'Past meetings · {0}': ['O‘tgan uchrashuvlar · {0}', 'Прошедшие встречи · {0}'],
  // A meeting the counselor proposed: the student confirms or declines it.
  'Waiting for your confirmation': ['Tasdiqlashingiz kutilmoqda', 'Ждёт вашего подтверждения'],
  'Confirm': ['Tasdiqlash', 'Подтвердить'],
  // Booking panel (Meetings): Time, Details, Done, then the student's own waiting requests.
  'Pick who and when. Your counselor confirms the request.': ['Kim bilan va qachon ekanini tanlang. So‘rovni maslahatchi tasdiqlaydi.', 'Выберите, с кем и когда. Консультант подтвердит запрос.'],
  'Pick a free time.': ['Bo‘sh vaqtni tanlang.', 'Выберите свободное время.'],
  '{n} free times': ['{n} ta bo‘sh vaqt', 'свободно: {n}'],
  'No free day yet': ['Hozircha bo‘sh kun yo‘q', 'Свободных дней пока нет'],
  'No free times on this day.': ['Bu kunda bo‘sh vaqt yo‘q.', 'В этот день нет свободного времени.'],
  'Your counselor confirms the request.': ['So‘rovni maslahatchingiz tasdiqlaydi.', 'Консультант подтвердит запрос.'],
  'Save new time': ['Yangi vaqtni saqlash', 'Сохранить новое время'],
  'Request sent': ['So‘rov yuborildi', 'Запрос отправлен'],
  'New time saved': ['Yangi vaqt saqlandi', 'Новое время сохранено'],
  'Book another': ['Yana band qilish', 'Записаться ещё'],
  'Your requests': ['So‘rovlaringiz', 'Ваши запросы'],
  'See free times': ['Bo‘sh vaqtlarni ko‘rish', 'Показать свободное время'],
  'Pick a counselor and a free time to request a meeting.': ['Maslahatchi va bo‘sh vaqtni tanlab, uchrashuv so‘rang.', 'Выберите консультанта и свободное время, чтобы запросить встречу.'],
  'Open meetings': ['Uchrashuvlarni ochish', 'Открыть встречи'],
  'Pending': ['Kutilmoqda', 'Ожидает'],
  'No topic': ['Mavzusiz', 'Без темы'],
  'Cancel request': ['So‘rovni bekor qilish', 'Отменить запрос'],
  'Request cancelled.': ['So‘rov bekor qilindi.', 'Запрос отменён.'],
  'Change time': ['Vaqtini o‘zgartirish', 'Изменить время'],
  'Changing the time of “{topic}” ({date}). Pick a new time.': ['«{topic}» ({date}) vaqtini o‘zgartiryapsiz. Yangi vaqtni tanlang.', 'Меняете время «{topic}» ({date}). Выберите новое время.'],
  'Keep the old time': ['Eski vaqt qolsin', 'Оставить прежнее время'],
  'Cancel this request?': ['Bu so‘rov bekor qilinsinmi?', 'Отменить этот запрос?'],
  'Yes, cancel': ['Ha, bekor qilish', 'Да, отменить'],
  'No requests yet. Pick a free time above to send your first one.': ['Hali so‘rov yo‘q. Yuqorida bo‘sh vaqtni tanlab, birinchi so‘rovni yuboring.', 'Запросов пока нет. Выберите свободное время выше.'],
  '{n} waiting for confirmation': ['{n} ta tasdiq kutilmoqda', 'ждут подтверждения: {n}'],
};

export function blueMeetingsMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(BLUE_MEETINGS_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
