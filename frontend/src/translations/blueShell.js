// Blue student shell, sign-in page and shared primitives (design/blue/*, pages/Login.jsx): English key -> [Uzbek (Latin), Russian].
// One module per area, so parallel work never edits the same file.
export const BLUE_SHELL_TRANSLATIONS = {
  'Back to top': ['Tepaga', 'Наверх'],
  'First sign-in with a temporary password': ['Vaqtinchalik parol bilan birinchi kirish', 'Первый вход с временным паролем'],
  'Enter your username and the temporary password from your counselor, then press Sign in. You will choose your own password next.': ['Login va maslahatchingiz bergan vaqtinchalik parolni kiriting, so‘ng “Kirish” tugmasini bosing. Keyingi qadamda o‘z parolingizni tanlaysiz.', 'Введите логин и временный пароль от консультанта и нажмите «Войти». Дальше вы выберете свой пароль.'],
  'Help': ['Yordam', 'Помощь'],
  'Naseeb Mind': ['Naseeb Mind', 'Naseeb Mind'],
  'MENU': ['MENYU', 'МЕНЮ'],
  'Menu': ['Menyu', 'Меню'],
  'New': ['Yangi', 'Новое'],
  'Light': ['Yorug‘', 'Светлая'],
  'Dark · Tinted': ['Qorong‘i · Tusli', 'Тёмная · Оттенок'],
  'Dark · Night': ['Qorong‘i · Tun', 'Тёмная · Ночь'],
  'Theme': ['Mavzu', 'Тема'],
  'Reading mode': ['O‘qish rejimi', 'Режим чтения'],
  'Due today': ['Bugun muddati', 'Срок сегодня'],
  'Remember me': ['Meni eslab qol', 'Запомнить меня'],
  'Forgot password?': ['Parolni unutdingizmi?', 'Забыли пароль?'],
};

export function blueShellMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(BLUE_SHELL_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
