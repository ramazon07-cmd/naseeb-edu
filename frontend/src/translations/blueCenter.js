// Blue Student Center, Roadmap and Naseeb Mind pages: English key -> [Uzbek (Latin), Russian].
// One module per area, so parallel work never edits the same file.
export const BLUE_CENTER_TRANSLATIONS = {
  // Roadmap: flight route, level path
  'You are here': ['Siz shu yerdasiz', 'Вы здесь'],
  'What to do': ['Nima qilish kerak', 'Что сделать'],
  'Next checkpoint': ['Keyingi bosqich', 'Следующий рубеж'],
  'Approved by your counselor': ['Maslahatchingiz tasdiqladi', 'Одобрено консультантом'],
  'Unlocks after mission {n} is approved': ['{n}-missiya tasdiqlangach ochiladi', 'Откроется после одобрения миссии {n}'],
  'Level {level} · {n} mission left|Level {level} · {n} missions left': ['{level}-daraja · {n} ta missiya qoldi', '{level}-й уровень · остался {n} миссия|{level}-й уровень · осталось {n} миссии|{level}-й уровень · осталось {n} миссий'],
  '{done} of {total} approved': ['{done} / {total} tasdiqlangan', '{done} из {total} одобрено'],
  // Tasks lead (roadmap and Tasks pages)
  'Start with': ['Avval shundan boshlang', 'Начните с'],
  'This task is overdue. Send your response or ask your counselor for a new date.': ['Bu vazifa muddati o‘tgan. Javobingizni yuboring yoki maslahatchidan yangi sana so‘rang.', 'Срок задачи прошёл. Отправьте ответ или попросите консультанта перенести дату.'],
  // Student Center
  'Class of {0}': ['{0}-yil bitiruvchisi', 'Выпуск {0}'],
  'Student ID': ['Talaba guvohnomasi', 'Студенческая карта'],
  'Contact and goal': ['Aloqa va maqsad', 'Контакты и цель'],
  'Discover your personality, interests and strongest subjects — and the study directions that fit you.': ['Shaxsiyatingiz, qiziqishlaringiz va kuchli fanlaringizni bilib oling — sizga mos yo‘nalishlarni toping.', 'Узнайте свою личность, интересы и сильные предметы — и подходящие вам направления.'],
  // Notifications
  'Meeting updates': ['Uchrashuv yangiliklari', 'Обновления встреч'],
  'Essay updates': ['Esse yangiliklari', 'Обновления эссе'],
  'Deadline alerts': ['Muddat ogohlantirishlari', 'Напоминания о сроках'],
  'Arrival': ['Manzil', 'Прибытие'],
};

export function blueCenterMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(BLUE_CENTER_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
