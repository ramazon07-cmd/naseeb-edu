// Student design parity (Cat): English key -> [Uzbek (Latin), Russian].
export const PARITY_CAT_TRANSLATIONS = {
};

export function parityCatMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(PARITY_CAT_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
