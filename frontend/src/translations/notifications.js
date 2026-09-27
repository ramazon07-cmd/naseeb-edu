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
}

export function notificationMessages(language) {
  const index = language === 'uz' ? 0 : 1
  return Object.fromEntries(Object.entries(NOTIFICATION_TRANSLATIONS).map(([key, values]) => [key, values[index]]))
}
