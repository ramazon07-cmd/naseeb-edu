// Student design parity (Tour): English key -> [Uzbek (Latin), Russian].
export const PARITY_TOUR_TRANSLATIONS = {
};

export function parityTourMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(PARITY_TOUR_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
