// Calendly-style meetings (pages/BookingsPage.jsx): English key -> [Uzbek (Latin), Russian].
// Russian plural keys hold "one|few|many" forms.
export const MEETING_TRANSLATIONS = {
  "Meeting duration": ["Uchrashuv davomiyligi", "Длительность встречи"],
  "Date range": ["Sana oralig‘i", "Период записи"],
  "Invitees can schedule within {summary} with at least {notice} notice": ["Taklif qilinganlar {summary} ichida, kamida {notice} oldin band qila oladi", "Приглашённые могут записаться в пределах {summary} не позднее чем за {notice}"],
  "{n} hour|{n} hours": ["{n} soat", "{n} час|{n} часа|{n} часов"],
  "{n} calendar day into the future|{n} calendar days into the future": ["kelgusi {n} kalendar kun", "{n} календарный день вперёд|{n} календарных дня вперёд|{n} календарных дней вперёд"],
  "a date range": ["sana oralig‘i", "период дат"],
  "Calendar days into the future": ["Kelgusi kalendar kunlar", "Календарных дней вперёд"],
  "calendar days into the future": ["kalendar kun oldinga", "календарных дней вперёд"],
  "Within a date range": ["Sana oralig‘ida", "В пределах периода"],
  "Choose dates": ["Sanalarni tanlang", "Выберите даты"],
  "Choose a date range": ["Sana oralig‘ini tanlang", "Выберите период дат"],
  "Choose the first day.": ["Birinchi kunni tanlang.", "Выберите первый день."],
  "Now choose the last day.": ["Endi oxirgi kunni tanlang.", "Теперь выберите последний день."],
  "Apply": ["Qo‘llash", "Применить"],
  "Enter a number of days between 1 and 365.": ["1 dan 365 gacha kun kiriting.", "Укажите число дней от 1 до 365."],
  "Choose the first and last day.": ["Birinchi va oxirgi kunni tanlang.", "Выберите первый и последний день."],
  "The last day cannot be before the first day.": ["Oxirgi kun birinchi kundan oldin bo‘lishi mumkin emas.", "Последний день не может быть раньше первого."],
  "The last day cannot be in the past.": ["Oxirgi kun o‘tmishda bo‘lishi mumkin emas.", "Последний день не может быть в прошлом."],
  "Set the hours you can meet each week. Times are in Tashkent time.": ["Har hafta uchrashuv o‘tkaza oladigan soatlaringizni belgilang. Vaqt Toshkent vaqti bilan.", "Укажите часы, когда вы можете проводить встречи каждую неделю. Время ташкентское."],
  "{booked} booked · {free} free times in this window": ["{booked} ta band · bu oraliqda {free} ta bo‘sh vaqt", "{booked} записано · {free} свободных времён в этом периоде"],
  "{booked} booked · {cancelled} cancelled this week": ["Shu hafta: {booked} ta band · {cancelled} ta bekor qilingan", "На этой неделе: {booked} записано · {cancelled} отменено"],
  "Cancelled by student": ["Talaba bekor qildi", "Отменено учеником"],
};

export function meetingMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(MEETING_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
