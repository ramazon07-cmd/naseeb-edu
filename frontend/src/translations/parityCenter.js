// Student design parity (Center): English key -> [Uzbek (Latin), Russian].
export const PARITY_CENTER_TRANSLATIONS = {
};

export function parityCenterMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(PARITY_CENTER_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
