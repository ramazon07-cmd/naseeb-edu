// Counselor shell and Notifications page (components/CounselorShell.jsx,
// pages/NotificationsPage.jsx): English key -> [Uzbek (Latin), Russian].
export const COUNSELOR_SHELL_TRANSLATIONS = {
  'What happened since your last visit': ['Oxirgi tashrifingizdan beri nima bo‘ldi', 'Что произошло с вашего последнего визита'],
  'Open in review': ['Tekshiruvda ochish', 'Открыть в проверке'],
  'Open item': ['Ochish', 'Открыть'],
  'Open chat': ['Suhbatni ochish', 'Открыть чат'],
  'You are all caught up.': ['Hammasi ko‘rib chiqilgan.', 'Вы всё просмотрели.'],
  'See all notifications': ['Barcha bildirishnomalar', 'Все уведомления'],
};

export function counselorShellMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(COUNSELOR_SHELL_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
