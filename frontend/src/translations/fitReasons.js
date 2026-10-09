// College Search fit reasons and watch-outs, keyed by the code the server sends
// ({code, params, text}; backend college_search.score_university). {name} is a param.
// backend test_college_fit checks that every code it can emit is listed here.
export const FIT_REASON_TEMPLATES = {
  sat_above_range: {
    en: 'SAT {score} meets or exceeds the catalog range',
    uz: 'SAT {score} katalogdagi oraliqqa teng yoki undan yuqori',
    ru: 'SAT {score} соответствует диапазону каталога или превышает его',
  },
  sat_in_range: {
    en: 'SAT {score} fits the {min}–{max} catalog range',
    uz: 'SAT {score} katalogdagi {min}–{max} oralig‘iga mos keladi',
    ru: 'SAT {score} входит в диапазон каталога {min}–{max}',
  },
  sat_near_minimum: {
    en: 'SAT is {points} points below the catalog minimum',
    uz: 'SAT katalogdagi minimumdan {points} ball past',
    ru: 'До минимума SAT по каталогу не хватает баллов: {points}',
  },
  sat_below_minimum: {
    en: 'Raise SAT toward at least {min}',
    uz: 'SAT natijasini kamida {min} ga yetkazing',
    ru: 'Поднимите SAT хотя бы до {min}',
  },
  act_above_range: {
    en: 'ACT {score} meets or exceeds the catalog range',
    uz: 'ACT {score} katalogdagi oraliqqa teng yoki undan yuqori',
    ru: 'ACT {score} соответствует диапазону каталога или превышает его',
  },
  act_in_range: {
    en: 'ACT {score} fits the {min}–{max} catalog range',
    uz: 'ACT {score} katalogdagi {min}–{max} oralig‘iga mos keladi',
    ru: 'ACT {score} входит в диапазон каталога {min}–{max}',
  },
  act_near_minimum: {
    en: 'ACT is {points} points below the catalog minimum',
    uz: 'ACT katalogdagi minimumdan {points} ball past',
    ru: 'До минимума ACT по каталогу не хватает баллов: {points}',
  },
  act_below_minimum: {
    en: 'Raise ACT toward at least {min}',
    uz: 'ACT natijasini kamida {min} ga yetkazing',
    ru: 'Поднимите ACT хотя бы до {min}',
  },
  tests_optional: {
    en: 'SAT and ACT are optional at this university',
    uz: 'Bu universitetda SAT va ACT ixtiyoriy',
    ru: 'В этом университете SAT и ACT необязательны',
  },
  tests_required: {
    en: 'This university expects an SAT or ACT score',
    uz: 'Bu universitet SAT yoki ACT natijasini kutadi',
    ru: 'Этот университет ожидает результат SAT или ACT',
  },
  test_score_missing: {
    en: 'Add an SAT or ACT score to compare with admitted students',
    uz: 'Qabul qilinganlar bilan solishtirish uchun SAT yoki ACT natijasini qo‘shing',
    ru: 'Добавьте результат SAT или ACT, чтобы сравнить его с принятыми студентами',
  },
  test_range_missing_for: {
    en: 'The {test} range is not listed in the catalog',
    uz: 'Katalogda {test} oralig‘i ko‘rsatilmagan',
    ru: 'Диапазон {test} в каталоге не указан',
  },
  test_range_missing: {
    en: 'SAT and ACT ranges are not listed in the catalog',
    uz: 'Katalogda SAT va ACT oraliqlari ko‘rsatilmagan',
    ru: 'Диапазоны SAT и ACT в каталоге не указаны',
  },
  english_strong: {
    en: '{test} {score} is a strong language score',
    uz: '{test} {score} — kuchli til natijasi',
    ru: '{test} {score} — сильный языковой результат',
  },
  english_suitable: {
    en: '{test} {score} is suitable for many programs',
    uz: '{test} {score} ko‘p dasturlar uchun yetarli',
    ru: '{test} {score} подходит для многих программ',
  },
  english_check: {
    en: 'Verify the English test requirement on the official program page',
    uz: 'Ingliz tili testi talabini dasturning rasmiy sahifasida tekshiring',
    ru: 'Проверьте требование к тесту по английскому на официальной странице программы',
  },
  english_missing: {
    en: 'Add an English test score (IELTS, TOEFL, Duolingo, PTE or Cambridge)',
    uz: 'Ingliz tili testi natijasini qo‘shing (IELTS, TOEFL, Duolingo, PTE yoki Cambridge)',
    ru: 'Добавьте результат теста по английскому (IELTS, TOEFL, Duolingo, PTE или Cambridge)',
  },
  country_match: {
    en: '{country} is one of your target countries',
    uz: '{country} siz tanlagan davlatlardan biri',
    ru: '{country} — одна из выбранных вами стран',
  },
  major_match: {
    en: '{major} matches an available field of study',
    uz: '{major} mavjud yo‘nalishlardan biriga mos keladi',
    ru: '{major} совпадает с одним из доступных направлений',
  },
  major_check: {
    en: 'Check the exact program requirements for your selected major',
    uz: 'Tanlagan yo‘nalishingiz bo‘yicha dastur talablarini aniq tekshiring',
    ru: 'Уточните требования программы по выбранной специальности',
  },
  cost_within_budget: {
    en: 'Estimated cost of attendance for international students is within your budget',
    uz: 'Xalqaro talabalar uchun taxminiy o‘qish xarajati byudjetingizga sig‘adi',
    ru: 'Ориентировочная стоимость обучения для иностранных студентов укладывается в ваш бюджет',
  },
  cost_above_budget: {
    en: 'Estimated cost of attendance for international students is above your budget',
    uz: 'Xalqaro talabalar uchun taxminiy o‘qish xarajati byudjetingizdan yuqori',
    ru: 'Ориентировочная стоимость обучения для иностранных студентов выше вашего бюджета',
  },
  cost_far_above_budget: {
    en: 'Estimated cost of attendance for international students is significantly above your budget',
    uz: 'Xalqaro talabalar uchun taxminiy o‘qish xarajati byudjetingizdan ancha yuqori',
    ru: 'Ориентировочная стоимость обучения для иностранных студентов значительно выше вашего бюджета',
  },
  cost_missing: {
    en: 'Estimated cost of attendance for international students is not available in the catalog',
    uz: 'Xalqaro talabalar uchun taxminiy o‘qish xarajati katalogda ko‘rsatilmagan',
    ru: 'Ориентировочной стоимости обучения для иностранных студентов нет в каталоге',
  },
  net_after_aid_within_budget: {
    en: 'Estimated net price after aid is within your budget',
    uz: 'Yordamdan keyingi taxminiy narx byudjetingizga sig‘adi',
    ru: 'Ориентировочная цена с учётом помощи укладывается в ваш бюджет',
  },
  net_after_aid_above_budget: {
    en: 'Estimated net price after aid is above your budget',
    uz: 'Yordamdan keyingi taxminiy narx byudjetingizdan yuqori',
    ru: 'Ориентировочная цена с учётом помощи выше вашего бюджета',
  },
  net_after_aid_far_above_budget: {
    en: 'Estimated net price after aid is significantly above your budget',
    uz: 'Yordamdan keyingi taxminiy narx byudjetingizdan ancha yuqori',
    ru: 'Ориентировочная цена с учётом помощи значительно выше вашего бюджета',
  },
  aid_available: {
    en: 'A suitable type of financial aid is available',
    uz: 'Mos moliyaviy yordam turi mavjud',
    ru: 'Есть подходящий вид финансовой помощи',
  },
  aid_not_offered: {
    en: 'The catalog lists no international, merit or need-based aid at this university',
    uz: 'Katalogga ko‘ra bu universitetda xalqaro, iqtidor yoki ehtiyojga asoslangan yordam yo‘q',
    ru: 'По данным каталога, в этом университете нет помощи иностранным студентам, за успехи или по нуждаемости',
  },
  aid_unknown: {
    en: 'Financial aid details are not listed in the catalog',
    uz: 'Moliyaviy yordam tafsilotlari katalogda ko‘rsatilmagan',
    ru: 'Сведений о финансовой помощи в каталоге нет',
  },
};

export const fitReasonKey = (code) => `fit_reason.${code}`;

export function fitReasonMessages(language) {
  return Object.fromEntries(Object.entries(FIT_REASON_TEMPLATES).map(([code, text]) => [fitReasonKey(code), text[language]]));
}
