// Blue Meetings, Messages and Notifications pages: English key -> [Uzbek (Latin), Russian].
// One module per area, so parallel work never edits the same file.
export const BLUE_MEETINGS_TRANSLATIONS = {
  'Meetings summary': ['Uchrashuvlar xulosasi', 'Сводка по встречам'],
  'Past meetings': ['O‘tgan uchrashuvlar', 'Прошедшие встречи'],
  'Minutes in meetings': ['Uchrashuvlarda o‘tkazilgan daqiqalar', 'Минут на встречах'],
  'Upcoming · {0}': ['Kelgusi · {0}', 'Предстоящие · {0}'],
  'Past meetings · {0}': ['O‘tgan uchrashuvlar · {0}', 'Прошедшие встречи · {0}'],
};

export function blueMeetingsMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(BLUE_MEETINGS_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
