// Blue Programs, Essay Lab, Applications, College Search and Store pages: English key -> [Uzbek (Latin), Russian].
// One module per area, so parallel work never edits the same file.
export const BLUE_CATALOG_TRANSLATIONS = {
  'Featured · next deadline': ['Tanlangan · eng yaqin muddat', 'Рекомендуем · ближайший срок'],
  'Open programs in the catalog': ['Katalogdagi ochiq dasturlar', 'Открытые программы в каталоге'],
  'Essay summary': ['Esselar xulosasi', 'Сводка по эссе'],
};

export function blueCatalogMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(BLUE_CATALOG_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
