// File upload and attachment text: English key -> [Uzbek (Latin), Russian].
export const FILE_TRANSLATIONS = {
  'Upload a file': ['Fayl yuklash', 'Загрузить файл'],
  'PDF, Word or a photo from your device': ['Qurilmangizdagi PDF, Word yoki surat', 'PDF, Word или фото с вашего устройства'],
  'Google Docs link': ['Google Docs havolasi', 'Ссылка на Google Docs'],
  'Share a document from Google Docs': ['Google Docs’dagi hujjatni ulashing', 'Поделитесь документом из Google Docs'],
  'How do you want to add it?': ['Qanday qo‘shmoqchisiz?', 'Как вы хотите добавить?'],
  'Edit document': ['Hujjatni tahrirlash', 'Редактировать документ'],
  'Choose a file to upload.': ['Yuklash uchun fayl tanlang.', 'Выберите файл для загрузки.'],
  'File uploaded.': ['Fayl yuklandi.', 'Файл загружен.'],
  'Document updated.': ['Hujjat yangilandi.', 'Документ обновлён.'],
  'Upload cancelled.': ['Yuklash bekor qilindi.', 'Загрузка отменена.'],
  'Saving a link removes the uploaded file from this document.': ['Havola saqlansa, yuklangan fayl bu hujjatdan o‘chiriladi.', 'При сохранении ссылки загруженный файл будет удалён из этого документа.'],
  'Evidence file': ['Tasdiqlovchi fayl', 'Подтверждающий файл'],
  'Letter file': ['Tavsiyanoma fayli', 'Файл письма'],
  'Recommendation letter': ['Tavsiyanoma', 'Рекомендательное письмо'],
  Submission: ['Topshirilgan ish', 'Отправленная работа'],
  'Current file': ['Joriy fayl', 'Текущий файл'],
  'Ready to upload': ['Yuklashga tayyor', 'Готов к загрузке'],
  'Replaces {0}': ['{0} o‘rniga', 'Заменит {0}'],
  'Remove selected file': ['Tanlangan faylni olib tashlash', 'Убрать выбранный файл'],
  'Remove file': ['Faylni o‘chirish', 'Удалить файл'],
  'Will be removed when you save': ['Saqlaganingizda o‘chiriladi', 'Будет удалён при сохранении'],
  'Keep file': ['Faylni qoldirish', 'Оставить файл'],
  'Uploading…': ['Yuklanmoqda…', 'Загрузка…'],
  'Cancel upload': ['Yuklashni bekor qilish', 'Отменить загрузку'],
  'Drag a file here, or': ['Faylni shu yerga torting yoki', 'Перетащите файл сюда или'],
  'Drop another file here to replace it, or': ['Almashtirish uchun boshqa faylni shu yerga torting yoki', 'Перетащите сюда другой файл для замены или'],
  'Choose file': ['Fayl tanlash', 'Выбрать файл'],
  'Choose another file': ['Boshqa fayl tanlash', 'Выбрать другой файл'],
  'PDF, Word (.doc, .docx), JPG, PNG, WebP or HEIC · up to {0} MB': ['PDF, Word (.doc, .docx), JPG, PNG, WebP yoki HEIC · {0} MB gacha', 'PDF, Word (.doc, .docx), JPG, PNG, WebP или HEIC · до {0} МБ'],
  'This file is larger than {0} MB. Choose a smaller file.': ['Bu fayl {0} MB dan katta. Kichikroq fayl tanlang.', 'Файл больше {0} МБ. Выберите файл меньшего размера.'],
  'The selected file is empty.': ['Tanlangan fayl bo‘sh.', 'Выбранный файл пуст.'],
  'This file type is not supported. Use PDF, Word (.doc, .docx), JPG, PNG, WebP or HEIC.': ['Bu fayl turi qo‘llab-quvvatlanmaydi. PDF, Word (.doc, .docx), JPG, PNG, WebP yoki HEIC dan foydalaning.', 'Этот тип файла не поддерживается. Используйте PDF, Word (.doc, .docx), JPG, PNG, WebP или HEIC.'],
  'The upload failed. Retry.': ['Yuklab bo‘lmadi. Qayta urinib ko‘ring.', 'Не удалось загрузить. Повторите попытку.'],
  'Word files can’t be previewed in the browser. Download the file to open it in Word, Google Docs or another editor.': ['Word fayllarini brauzerda ko‘rib bo‘lmaydi. Word, Google Docs yoki boshqa muharrirda ochish uchun faylni yuklab oling.', 'Файлы Word нельзя просмотреть в браузере. Скачайте файл, чтобы открыть его в Word, Google Docs или другом редакторе.'],
  'This photo format can’t be previewed in every browser. Download the file to view it.': ['Bu surat formatini har bir brauzerda ko‘rib bo‘lmaydi. Ko‘rish uchun faylni yuklab oling.', 'Этот формат фото открывается не во всех браузерах. Скачайте файл, чтобы посмотреть его.'],
  'This file type can’t be previewed in the browser. Download it to open it in the appropriate application.': ['Bu turdagi faylni brauzerda ko‘rib bo‘lmaydi. Tegishli dasturda ochish uchun uni yuklab oling.', 'Этот тип файла нельзя просмотреть в браузере. Скачайте его, чтобы открыть в подходящем приложении.'],
}

export function fileMessages(language) {
  const index = language === 'uz' ? 0 : 1
  return Object.fromEntries(Object.entries(FILE_TRANSLATIONS).map(([key, values]) => [key, values[index]]))
}
