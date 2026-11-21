// Naseeb Mind results link (Mind page card): English key -> [Uzbek (Latin), Russian].
export const MIND_LINK_TRANSLATIONS = {
  'Bring my Naseeb Mind results': ['Naseeb Mind natijalarimni olib kelish', 'Перенести мои результаты Naseeb Mind'],
  'Already took the tests on naseebmind.uz? Link your account once and your results appear here, and new ones follow on their own.': [
    'Testlarni naseebmind.uz da topshirganmisiz? Hisobingizni bir marta ulang, natijalaringiz shu yerda paydo bo‘ladi, yangilari o‘zi keladi.',
    'Проходили тесты на naseebmind.uz? Свяжите аккаунт один раз, и результаты появятся здесь, а новые будут приходить сами.',
  ],
  'Connect Naseeb Mind': ['Naseeb Mind ni ulash', 'Подключить Naseeb Mind'],
  'Opening…': ['Ochilmoqda…', 'Открываем…'],
  'Naseeb Mind opened in a new tab. Share your results there, then come back and check.': [
    'Naseeb Mind yangi oynada ochildi. U yerda natijalaringizni ulashing, keyin qaytib tekshiring.',
    'Naseeb Mind открыт в новой вкладке. Поделитесь результатами там, затем вернитесь и проверьте.',
  ],
  'Open Naseeb Mind': ['Naseeb Mind ni ochish', 'Открыть Naseeb Mind'],
  'The link code expired. Start again to get a new one.': [
    'Ulanish kodi muddati tugadi. Yangi kod olish uchun qaytadan boshlang.',
    'Срок действия кода истёк. Начните заново, чтобы получить новый.',
  ],
  'Start again': ['Qaytadan boshlash', 'Начать заново'],
  'Check again': ['Qayta tekshirish', 'Проверить снова'],
  'Not linked yet.': ['Hali ulanmagan.', 'Пока не подключено.'],
  'Could not start the link. Try again.': ['Ulanishni boshlab bo‘lmadi. Qayta urinib ko‘ring.', 'Не удалось начать подключение. Попробуйте ещё раз.'],
  'Could not check the link. Try again.': ['Ulanishni tekshirib bo‘lmadi. Qayta urinib ko‘ring.', 'Не удалось проверить подключение. Попробуйте ещё раз.'],
  'Naseeb Mind linked': ['Naseeb Mind ulangan', 'Naseeb Mind подключён'],
  'Linked on {date}': ['{date} da ulangan', 'Подключено {date}'],
  'Last sync {date}': ['Oxirgi yangilanish: {date}', 'Последняя синхронизация: {date}'],
  'No results received yet': ['Hali natija kelmagan', 'Результаты ещё не получены'],
  'Stop sharing': ['Ulashishni to‘xtatish', 'Прекратить передачу'],
  'Stopping…': ['To‘xtatilmoqda…', 'Останавливаем…'],
  'Results already imported stay in your profile here.': ['Olib kelingan natijalar bu yerdagi profilingizda qoladi.', 'Уже полученные результаты остаются в вашем профиле здесь.'],
  'Sharing stopped. Results already imported stay here.': ['Ulashish to‘xtatildi. Olib kelingan natijalar shu yerda qoladi.', 'Передача остановлена. Полученные результаты остаются здесь.'],
  'Could not stop sharing. Try again.': ['Ulashishni to‘xtatib bo‘lmadi. Qayta urinib ko‘ring.', 'Не удалось остановить передачу. Попробуйте ещё раз.'],
  'Naseeb Mind linked. Your results are here.': ['Naseeb Mind ulandi. Natijalaringiz shu yerda.', 'Naseeb Mind подключён. Ваши результаты здесь.'],
  'In Naseeb Mind you chose {major}.': ['Naseeb Mind da siz {major} ni tanlagansiz.', 'В Naseeb Mind вы выбрали: {major}.'],
  'Use as my major': ['Yo‘nalishim sifatida qo‘llash', 'Использовать как моё направление'],
  '{major} saved as your study direction.': ['{major} o‘qish yo‘nalishingiz sifatida saqlandi.', '{major} сохранено как ваше направление.'],
  'Could not save your major. Try again.': ['Yo‘nalishni saqlab bo‘lmadi. Qayta urinib ko‘ring.', 'Не удалось сохранить направление. Попробуйте ещё раз.'],
  'Imported from Naseeb Mind': ['Naseeb Mind dan olingan', 'Импортировано из Naseeb Mind'],
  'Different test version': ['Test versiyasi boshqa', 'Другая версия теста'],
  '{n} imported result(s) were taken on a different version of the test. They are kept, but not scored or compared with your current results.': [
    '{n} ta olib kelingan natija testning boshqa versiyasida topshirilgan. Ular saqlanadi, lekin hozirgi natijalaringiz bilan hisoblanmaydi va solishtirilmaydi.',
    '{n} импортированных результатов пройдены на другой версии теста. Они сохранены, но не учитываются и не сравниваются с текущими.',
  ],
};

export function mindLinkMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(MIND_LINK_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
