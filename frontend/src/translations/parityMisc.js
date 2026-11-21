// Student design parity (Misc): English key -> [Uzbek (Latin), Russian].
export const PARITY_MISC_TRANSLATIONS = {
  'Filter': ['Saralash', 'Фильтр'],
  'Reset': ['Tozalash', 'Сбросить'],
  'University name (A–Z)': ['Universitet nomi (A–Z)', 'Название вуза (А–Я)'],
  'Room for one more': ['Yana bittasiga joy bor', 'Есть место ещё для одного'],
  'Enough here': ['Bu turda yetarli', 'Здесь достаточно'],
  '{0}: {1} on your list, about {2} recommended. Select to show only these.': ['{0}: ro‘yxatda {1} ta, taxminan {2} ta tavsiya etiladi. Tanlasangiz, faqat shular ko‘rinadi.', '{0}: в списке {1}, рекомендуется около {2}. Выберите, чтобы показать только их.'],
  'Records': ['Yozuvlar', 'Записи'],
  'No results found': ['Hech narsa topilmadi', 'Ничего не найдено'],
};

export function parityMiscMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(PARITY_MISC_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
