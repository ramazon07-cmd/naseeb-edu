// Blue Dashboard (DashboardPage.jsx and its widgets): English key -> [Uzbek (Latin), Russian].
// One module per area, so parallel work never edits the same file.
export const BLUE_DASHBOARD_TRANSLATIONS = {
  '{n} overdue deadline|{n} overdue deadlines': ['{n} ta muddati o\u2018tgan topshiriq', '{n} просроченный дедлайн|{n} просроченных дедлайна|{n} просроченных дедлайнов'],
  'Review now': ['Hozir ko\u2018rish', 'Посмотреть'],
  'No deadlines coming up.': ['Yaqin muddatlar yo\u2018q.', 'Ближайших дедлайнов нет.'],
  '{n} task open|{n} tasks open': ['{n} ta ochiq vazifa', '{n} открытое задание|{n} открытых задания|{n} открытых заданий'],
  'My activity': ['Mening faoliyatim', 'Моя активность'],
  'avg {value}': ['o\u2018rtacha {value}', 'в среднем {value}'],
  'Unread alerts': ['O\u2018qilmagan bildirishnomalar', 'Непрочитанные уведомления'],
  'Unread chats': ['O\u2018qilmagan suhbatlar', 'Непрочитанные чаты'],
};

export function blueDashboardMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(BLUE_DASHBOARD_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
