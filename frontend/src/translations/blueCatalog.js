// Blue Programs, Essay Lab, Applications, College Search and Store pages: English key -> [Uzbek (Latin), Russian].
// One module per area, so parallel work never edits the same file.
export const BLUE_CATALOG_TRANSLATIONS = {
  'Featured · next deadline': ['Tanlangan · eng yaqin muddat', 'Рекомендуем · ближайший срок'],
  'Open programs in the catalog': ['Katalogdagi ochiq dasturlar', 'Открытые программы в каталоге'],
  'List': ['Ro\u2018yxat', 'Список'],
  'Board': ['Doska', 'Доска'],
  'View as': ['Ko\u2018rinish', 'Вид'],
  'Matched to you': ['Sizga mos', 'Подобрано для вас'],
  'University deadlines': ['Universitet muddatlari', 'Сроки университетов'],
  'No upcoming deadlines yet.': ['Yaqin muddatlar hali yo\u2018q.', 'Ближайших сроков пока нет.'],
  'Next step': ['Keyingi qadam', 'Следующий шаг'],
  'Application stage': ['Ariza bosqichi', 'Этап заявки'],
  'Matches for you': ['Siz uchun mosliklar', 'Подходит вам'],
  'All universities': ['Barcha universitetlar', 'Все университеты'],
  'University list': ['Universitetlar ro\u2018yxati', 'Список университетов'],
  'Compare universities': ['Universitetlarni solishtirish', 'Сравнение университетов'],
  'Compare up to 3 universities': ['3 tagacha universitetni solishtiring', 'Сравнивайте до 3 университетов'],
  'Compare {0}': ['{0} ni solishtirish', 'Сравнить {0}'],
  'Remove {0} from comparison': ['{0} ni solishtirishdan olib tashlash', 'Убрать {0} из сравнения'],
  'Compare': ['Solishtirish', 'Сравнить'],
  'Field': ['Maydon', 'Параметр'],
  'Your list balance': ['Ro\u2018yxatingiz muvozanati', 'Баланс вашего списка'],
  'Average acceptance rate': ['O\u2018rtacha qabul darajasi', 'Средний процент приёма'],
  'Cost': ['Narx', 'Стоимость'],
  'Essay summary': ['Esselar xulosasi', 'Сводка по эссе'],
};

export function blueCatalogMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(BLUE_CATALOG_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
