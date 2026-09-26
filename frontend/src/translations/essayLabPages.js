// Essay Lab page layout text (Pages view, page breaks, page setup):
// English key -> [Uzbek (Latin), Russian].
export const ESSAY_LAB_PAGES_TRANSLATIONS = {
  'Page layout': ['Sahifa ko‘rinishi', 'Вид страницы'],
  Pageless: ['Sahifasiz', 'Без страниц'],
  'Page options': ['Sahifa sozlamalari', 'Параметры страницы'],
  'Page break': ['Sahifa uzilishi', 'Разрыв страницы'],
  'Add blank page': ['Bo‘sh sahifa qo‘shish', 'Добавить пустую страницу'],
  'Page {n} of {total}': ['{n}-sahifa, jami {total}', 'Страница {n} из {total}'],
  'Page setup': ['Sahifa parametrlari', 'Параметры страницы'],
  'Page setup…': ['Sahifa parametrlari…', 'Параметры страницы…'],
  'Paper size': ['Qog‘oz o‘lchami', 'Размер бумаги'],
  'US Letter': ['US Letter (AQSh)', 'US Letter (США)'],
  Apply: ['Qo‘llash', 'Применить'],
  'Applies to this document in the Pages view, on every device.': ['“Sahifalar” ko‘rinishida shu hujjatga, barcha qurilmalarda qo‘llanadi.', 'Действует для этого документа в режиме «Страницы» на всех устройствах.'],
  'Could not change the page setup.': ['Sahifa parametrlarini o‘zgartirib bo‘lmadi.', 'Не удалось изменить параметры страницы.'],
}

export function essayLabPagesMessages(language) {
  const index = language === 'uz' ? 0 : 1
  return Object.fromEntries(Object.entries(ESSAY_LAB_PAGES_TRANSLATIONS).map(([key, values]) => [key, values[index]]))
}
