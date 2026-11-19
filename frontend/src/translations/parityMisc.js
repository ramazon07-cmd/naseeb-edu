// Student design parity (Misc): English key -> [Uzbek (Latin), Russian].
export const PARITY_MISC_TRANSLATIONS = {
  'Records': ['Yozuvlar', 'Записи'],
  'No results found': ['Hech narsa topilmadi', 'Ничего не найдено'],
};

export function parityMiscMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(PARITY_MISC_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
