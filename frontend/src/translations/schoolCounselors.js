const messages = {
  'Allow platform access': ['Platformaga kirishga ruxsat', 'Доступ к платформе'],
  'The counselor can sign in and work with students.': ['Maslahatchi tizimga kirib, o‘quvchilar bilan ishlay oladi.', 'Консультант может входить и работать с учениками.'],
  "Sign-in will be blocked. The counselor's records are kept.": ['Tizimga kirish bloklanadi. Maslahatchining ma’lumotlari saqlanadi.', 'Вход будет заблокирован. Данные консультанта сохранятся.'],
  'Changes apply when you save.': ['O‘zgarish saqlagandan keyin qo‘llanadi.', 'Изменения вступят в силу после сохранения.'],
  'Manage counselors in your school': ['Maktabingizdagi maslahatchilarni boshqarish', 'Управление консультантами вашей школы'],
  'Add counselors to your school and manage their access.': [
    'Maktabingizga maslahatchi qo‘shing va uning kirish huquqini boshqaring.',
    'Добавляйте консультантов в свою школу и управляйте их доступом.',
  ],
  'Create a login for your counselor. They will set their own password at first sign-in.': [
    'Maslahatchi uchun hisob yarating. U birinchi kirishda o‘z parolini o‘rnatadi.',
    'Создайте аккаунт консультанта. При первом входе он установит свой пароль.',
  ],
  'Share this password privately with the counselor.': [
    'Bu parolni maslahatchining o‘ziga maxfiy tarzda yetkazing.',
    'Передайте этот пароль консультанту конфиденциально.',
  ],
};

export function schoolCounselorMessages(language) {
  return Object.fromEntries(Object.entries(messages).map(([key, values]) => [key, values[language === 'uz' ? 0 : 1]]));
}
