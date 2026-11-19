// Blue student shell, sign-in page and shared primitives (design/blue/*, pages/Login.jsx): English key -> [Uzbek (Latin), Russian].
// One module per area, so parallel work never edits the same file.
export const BLUE_SHELL_TRANSLATIONS = {
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
