// Student design parity (Mind): English key -> [Uzbek (Latin), Russian].
export const PARITY_MIND_TRANSLATIONS = {
};

export function parityMindMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(PARITY_MIND_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
