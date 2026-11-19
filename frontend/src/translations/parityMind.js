// Student design parity (Mind): English key -> [Uzbek (Latin), Russian].
export const PARITY_MIND_TRANSLATIONS = {
  'Naseeb Mind · your profile': ['Naseeb Mind · profilingiz', 'Naseeb Mind · ваш профиль'],
  'What we know about you so far': ['Hozircha siz haqingizda bilganlarimiz', 'Что мы уже знаем о вас'],
  '{a} of {b} tests done': ['{b} ta testdan {a} tasi tayyor', 'Пройдено {a} из {b} тестов'],
  '{n} questions': ['{n} ta savol', 'Вопросов: {n}'],
  '{n} puzzles': ['{n} ta topshiriq', 'Задач: {n}'],
  'Take test': ['Testni topshirish', 'Пройти тест'],
  'Fills in after “{test}”': ['«{test}» testidan keyin to‘ladi', 'Заполнится после теста «{test}»'],
  'Who could you become?': ['Kim bo‘lishingiz mumkin?', 'Кем вы можете стать?'],
  '{n} tests left': ['{n} ta test qoldi', 'Осталось тестов: {n}'],
  'Locked': ['Yopiq', 'Закрыто'],
  'Your three majors are ready': ['Uchta yo‘nalishingiz tayyor', 'Ваши три специальности готовы'],
  'When all 7 tests are done, Naseeb Mind shows the three majors that fit you best. Pick one and it becomes your study direction.': [
    '7 ta test tugagach, Naseeb Mind sizga eng mos uchta yo‘nalishni ko‘rsatadi. Bittasini tanlaysiz va u o‘qish yo‘nalishingiz bo‘ladi.',
    'Когда все 7 тестов пройдены, Naseeb Mind покажет три самые подходящие специальности. Выберите одну, и она станет вашим направлением.',
  ],
  'Answers save as you go. Take the tests in any order.': ['Javoblar o‘zi saqlanadi. Testlarni istalgan tartibda topshiring.', 'Ответы сохраняются сами. Проходите тесты в любом порядке.'],
  'A guide, not a diagnosis.': ['Bu tashxis emas, yo‘l-yo‘riq.', 'Это ориентир, а не диагноз.'],
  'A result is a picture of you today. Retake a test to update it.': ['Natija bugungi suratingiz. Testni qayta topshirib, uni yangilashingiz mumkin.', 'Результат показывает вас сегодня. Пройдите тест снова, чтобы обновить его.'],
  'Your study direction now': ['Hozirgi o‘qish yo‘nalishingiz', 'Ваше направление сейчас'],
  'Your results on one card': ['Natijalaringiz bitta kartada', 'Ваши результаты на одной карточке'],
  'Download card': ['Kartani yuklab olish', 'Скачать карточку'],
  'From “How school feels”. Not your marks.': ['«Maktab sizga qanday tuyuladi» testidan. Baholaringiz emas.', 'Из теста «Каким ощущается школа». Это не оценки.'],
  'What you want from work': ['Ishdan nimani kutasiz', 'Чего вы ждёте от работы'],
  'What matters most to you': ['Siz uchun eng muhimi', 'Что для вас важнее всего'],
  'How you reason': ['Qanday fikrlaysiz', 'Как вы рассуждаете'],
  'How you handle emotions': ['Hissiyotlar bilan qanday ishlaysiz', 'Как вы справляетесь с эмоциями'],
  'Fifty statements about how you usually are. Which ones sound like you?': ['Odatda qanday ekaningiz haqida ellikta gap. Qaysilari sizga o‘xshaydi?', 'Пятьдесят утверждений о том, какой вы обычно. Какие похожи на вас?'],
  'Which kinds of work would you enjoy? Not about ability, only about liking it.': ['Qaysi ish turlari sizga yoqadi? Qobiliyat emas, faqat yoqishi haqida.', 'Какая работа вам понравится? Не про способности, а про интерес.'],
  'Eleven school subjects. What can you do, what do you enjoy, what does it cost you?': ['O‘n bitta maktab fani. Nimani eplaysiz, nimadan zavq olasiz, nimasi qiyin?', 'Одиннадцать школьных предметов. Что получается, что нравится, чего это стоит?'],
  'What do you want from your future work?': ['Kelajakdagi ishingizdan nimani kutasiz?', 'Чего вы ждёте от будущей работы?'],
  'Twenty things a job can offer. Which matter most to you?': ['Ish bera oladigan yigirmata narsa. Siz uchun qaysilari muhim?', 'Двадцать вещей, которые может дать работа. Какие важнее для вас?'],
  'Sixteen puzzles. Can you find the pattern?': ['O‘n oltita savol. Qoidani topa olasizmi?', 'Шестнадцать задач. Найдёте закономерность?'],
  'How do you understand and manage emotions?': ['Hissiyotlarni qanday tushunasiz va boshqarasiz?', 'Как вы понимаете эмоции и управляете ими?'],
};

export function parityMindMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(PARITY_MIND_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
