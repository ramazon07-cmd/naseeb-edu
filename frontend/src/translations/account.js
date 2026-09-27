// Student account settings and the server-saved dashboard layout:
// English key -> [Uzbek (Latin), Russian].
export const ACCOUNT_TRANSLATIONS = {
  'Account settings': ['Hisob sozlamalari', 'Настройки аккаунта'],
  'Password, email, language, and who can see your data': ['Parol, email, til va ma’lumotlaringizni kim ko‘ra olishi', 'Пароль, email, язык и кто видит ваши данные'],
  'Sign-in details': ['Kirish ma’lumotlari', 'Данные для входа'],
  'Your username cannot be changed.': ['Foydalanuvchi nomini o‘zgartirib bo‘lmaydi.', 'Имя пользователя изменить нельзя.'],
  'Email address': ['Email manzil', 'Адрес электронной почты'],
  'Current password': ['Joriy parol', 'Текущий пароль'],
  'Confirm it is you to change your email.': ['Emailni o‘zgartirish uchun bu siz ekaningizni tasdiqlang.', 'Подтвердите, что это вы, чтобы изменить email.'],
  'Save email': ['Emailni saqlash', 'Сохранить email'],
  'Your email address was updated.': ['Email manzilingiz yangilandi.', 'Адрес электронной почты обновлён.'],
  'Change password': ['Parolni o‘zgartirish', 'Изменить пароль'],
  'Password changed. You are still signed in here; other devices were signed out.': ['Parol o‘zgartirildi. Bu qurilmada tizimda qoldingiz, boshqa qurilmalardan chiqarildingiz.', 'Пароль изменён. Здесь вы остались в системе, на других устройствах выполнен выход.'],
  'Show password': ['Parolni ko‘rsatish', 'Показать пароль'],
  'Hide password': ['Parolni yashirish', 'Скрыть пароль'],
  'Your current password is incorrect.': ['Joriy parol noto‘g‘ri.', 'Текущий пароль указан неверно.'],
  'This email address is already used by another account.': ['Bu email manzil boshqa hisobda ishlatilmoqda.', 'Этот адрес электронной почты уже используется другим аккаунтом.'],
  'Choose a password different from your current password.': ['Joriy paroldan farqli parol tanlang.', 'Выберите пароль, отличный от текущего.'],
  'Choose the language for Naseeb Edu on this device.': ['Ushbu qurilmada Naseeb Edu tilini tanlang.', 'Выберите язык Naseeb Edu на этом устройстве.'],
  // Who can see my data
  'Who can see my data': ['Ma’lumotlarimni kim ko‘ra oladi', 'Кто видит мои данные'],
  'No parent or guardian is linked to your account.': ['Hisobingizga hech qanday ota-ona yoki vasiy bog‘lanmagan.', 'К вашему аккаунту не привязаны родители или опекуны.'],
  'Can see your data': ['Ma’lumotlaringizni ko‘ra oladi', 'Видит ваши данные'],
  'Invitation pending': ['Taklif kutilmoqda', 'Приглашение ожидает ответа'],
  'Linked since {date}': ['{date} dan beri bog‘langan', 'Привязан с {date}'],
  'Linked': ['Bog‘langan', 'Привязан'],
  'Sees nothing until they accept the invitation.': ['Taklifni qabul qilmaguncha hech narsani ko‘rmaydi.', 'Ничего не видит, пока не примет приглашение.'],
  'Sections': ['Bo‘limlar', 'Разделы'],
  'visible': ['ko‘rinadi', 'видно'],
  'hidden': ['yashirin', 'скрыто'],
  'Profile summary': ['Profil qisqacha', 'Сводка профиля'],
  'Progress and level': ['Jarayon va daraja', 'Прогресс и уровень'],
  'Tasks and deadlines': ['Vazifalar va muddatlar', 'Задачи и сроки'],
  'Counselor notes': ['Maslahatchi qaydlari', 'Заметки консультанта'],
  'Task responses': ['Vazifa javoblari', 'Ответы на задачи'],
  'Document files': ['Hujjat fayllari', 'Файлы документов'],
  'Parents never see: {list}.': ['Ota-onalar hech qachon ko‘rmaydi: {list}.', 'Родители никогда не видят: {list}.'],
  'Ask your counselor to change who can see your data or which sections they see.': ['Ma’lumotlaringizni kim ko‘rishi yoki qaysi bo‘limlarni ko‘rishini o‘zgartirish uchun maslahatchingizga murojaat qiling.', 'Чтобы изменить, кто видит ваши данные или какие разделы, обратитесь к своему консультанту.'],
  // Dashboard layout
  'Layout saved on this device. It will be saved to your account when you are back online.': ['Joylashuv shu qurilmada saqlandi. Internetga qayta ulanganingizda hisobingizga saqlanadi.', 'Расположение сохранено на этом устройстве. Оно сохранится в аккаунте, когда вы снова будете онлайн.'],
};

export function accountMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(ACCOUNT_TRANSLATIONS).map(([key, values]) => [key, values[index]]));
}
