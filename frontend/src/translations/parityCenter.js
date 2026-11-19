// Student design parity (Center): English key -> [Uzbek (Latin), Russian].
export const PARITY_CENTER_TRANSLATIONS = {
  'Place your photo': ['Rasmingizni joylang', 'Расположите фото'],
  'Drag and zoom. Keep your face in the middle of the frame.': ['Suring va kattalashtiring. Yuzingiz ramka o‘rtasida tursin.', 'Перетащите и приблизьте. Лицо должно быть в центре рамки.'],
  'This image could not be opened. Choose another one.': ['Bu rasmni ochib bo‘lmadi. Boshqasini tanlang.', 'Не удалось открыть это изображение. Выберите другое.'],
  'How it will look': ['Qanday ko‘rinadi', 'Как это будет выглядеть'],
  'Choose another': ['Boshqasini tanlash', 'Выбрать другое'],
  'Use photo': ['Rasmni qo‘yish', 'Использовать фото'],
  'Photo removed.': ['Rasm olib tashlandi.', 'Фото удалено.'],
  'Zoom': ['Kattalashtirish', 'Масштаб'],
};

export function parityCenterMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(PARITY_CENTER_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
