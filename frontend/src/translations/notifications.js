// Notification bell and message history text: English key -> [Uzbek (Latin), Russian].
export const NOTIFICATION_TRANSLATIONS = {
  'Alerts about your work and unread conversations.': ['Ishlaringiz bo‘yicha ogohlantirishlar va o‘qilmagan suhbatlar.', 'Уведомления о ваших задачах и непрочитанные переписки.'],
  'Mark all as read': ['Hammasini o‘qilgan deb belgilash', 'Отметить все как прочитанные'],
  'Notifications, {0} unread': ['Bildirishnomalar, {0} ta o‘qilmagan', 'Уведомления, непрочитанных: {0}'],
  'Load older messages': ['Avvalgi xabarlarni yuklash', 'Загрузить более ранние сообщения'],
  'From your counselor': ['Maslahatchingizdan', 'От вашего консультанта'],
  'Messages sent before chats were available': ['Chatlar paydo bo‘lishidan oldin yuborilgan xabarlar', 'Сообщения, отправленные до появления чатов'],
  'Replies to these messages now go through chat.': ['Bu xabarlarga endi chat orqali javob beriladi.', 'Теперь на эти сообщения отвечают в чате.'],
  'Continue in chat': ['Chatda davom etish', 'Продолжить в чате'],
  // Titles of the notices the server writes.
  'Late tasks require attention': ['Muddati o‘tgan vazifalar e’tibor talab qiladi', 'Просроченные задачи требуют внимания'],
  'Required documents are missing': ['Kerakli hujjatlar yetishmayapti', 'Не хватает обязательных документов'],
  'University deadline approaching': ['Universitet muddati yaqinlashmoqda', 'Приближается дедлайн университета'],
  'Essay shared with counselor': ['Insho maslahatchi bilan ulashildi', 'Эссе отправлено консультанту'],
  'Deadline alert': ['Muddat haqida ogohlantirish', 'Напоминание о сроке'],
  'Meeting approved': ['Uchrashuv tasdiqlandi', 'Встреча подтверждена'],
  'Meeting rejected': ['Uchrashuv rad etildi', 'Встреча отклонена'],
  'Meeting completed': ['Uchrashuv yakunlandi', 'Встреча завершена'],
  'Meeting cancelled': ['Uchrashuv bekor qilindi', 'Встреча отменена'],
  'Meeting reschedule requested': ['Uchrashuvni ko‘chirish so‘raldi', 'Запрошен перенос встречи'],
  // Bodies of the notices the server writes (see lib/notificationText.js).
  '{n} task is past its deadline.|{n} tasks are past their deadline.': ['{n} ta vazifaning muddati o‘tib ketgan.', '{n} задача просрочена.|{n} задачи просрочены.|{n} задач просрочено.'],
  '{n} required document still needs to be uploaded.|{n} required documents still need to be uploaded.': ['{n} ta majburiy hujjat hali yuklanmagan.', 'Нужно загрузить ещё {n} обязательный документ.|Нужно загрузить ещё {n} обязательных документа.|Нужно загрузить ещё {n} обязательных документов.'],
  'The {university} deadline is {date}.': ['{university} uchun topshirish muddati: {date}.', 'Срок подачи в {university}: {date}'],
  '{name} shared an essay for review.': ['{name} inshoni tekshirish uchun ulashdi.', '{name} отправил(а) эссе на проверку.'],
  'Your meeting with {name} on {time} was approved.': ['{name} bilan uchrashuvingiz ({time}) tasdiqlandi.', 'Ваша встреча с {name} ({time}) подтверждена.'],
  'Your meeting with {name} on {time} was declined.': ['{name} bilan uchrashuvingiz ({time}) rad etildi.', 'Ваша встреча с {name} ({time}) отклонена.'],
  'Your meeting with {name} on {time} is marked as completed.': ['{name} bilan uchrashuvingiz ({time}) yakunlangan deb belgilandi.', 'Ваша встреча с {name} ({time}) отмечена как завершённая.'],
  'Your meeting with {name} on {time} was cancelled.': ['{name} bilan uchrashuvingiz ({time}) bekor qilindi.', 'Ваша встреча с {name} ({time}) отменена.'],
  '{name} cancelled the meeting “{topic}” on {time}.': ['{name} “{topic}” uchrashuvini ({time}) bekor qildi.', '{name} отменил(а) встречу «{topic}» ({time}).'],
  '{name} asked to move “{topic}” to {time}.': ['{name} “{topic}” uchrashuvini {time} vaqtiga ko‘chirishni so‘radi.', '{name} просит перенести встречу «{topic}» на {time}.'],
  'your meeting participant': ['uchrashuv ishtirokchisi', 'участником встречи'],
  'Profile section approved': ['Profil bo‘limi tasdiqlandi', 'Раздел профиля одобрен'],
  'Profile section needs changes': ['Profil bo‘limiga o‘zgartirish kerak', 'Раздел профиля нужно исправить'],
  'New feedback on your essay': ['Inshongiz bo‘yicha yangi fikr-mulohaza', 'Новый отзыв на ваше эссе'],
  'New reply to your comment': ['Izohingizga yangi javob', 'Новый ответ на ваш комментарий'],
  'Comment resolved': ['Izoh hal qilindi', 'Комментарий решён'],
  'Suggestions reviewed': ['Takliflar ko‘rib chiqildi', 'Предложения рассмотрены'],
}

export function notificationMessages(language) {
  const index = language === 'uz' ? 0 : 1
  return Object.fromEntries(Object.entries(NOTIFICATION_TRANSLATIONS).map(([key, values]) => [key, values[index]]))
}
