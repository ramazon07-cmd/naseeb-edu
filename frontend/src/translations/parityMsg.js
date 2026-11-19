// Student design parity (Msg): English key -> [Uzbek (Latin), Russian].
export const PARITY_MSG_TRANSLATIONS = {
  'Channels': ['Kanallar', 'Каналы'],
  'Select a chat to start messaging': ['Yozishni boshlash uchun chatni tanlang', 'Выберите чат, чтобы начать переписку'],
};

export function parityMsgMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(PARITY_MSG_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
