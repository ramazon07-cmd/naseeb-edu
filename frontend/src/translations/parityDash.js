// Student design parity (Dash): English key -> [Uzbek (Latin), Russian].
export const PARITY_DASH_TRANSLATIONS = {
};

export function parityDashMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(PARITY_DASH_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
