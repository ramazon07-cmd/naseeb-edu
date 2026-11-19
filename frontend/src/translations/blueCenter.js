// Blue Student Center, Roadmap and Naseeb Mind pages: English key -> [Uzbek (Latin), Russian].
// One module per area, so parallel work never edits the same file.
export const BLUE_CENTER_TRANSLATIONS = {
};

export function blueCenterMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(BLUE_CENTER_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
