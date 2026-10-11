const messages = {
  'Manage counselors in your school': ['Maktabingizdagi maslahatchilarni boshqarish', 'Управление консультантами вашей школы'],
  'Edit names, phone numbers, positions and active status. Contact Naseeb admin to add a counselor.': [
    'Ism, telefon, lavozim va faollik holatini tahrirlang. Maslahatchi qo‘shish uchun Naseeb administratoriga murojaat qiling.',
    'Меняйте имена, телефоны, должности и статус активности. Чтобы добавить консультанта, обратитесь к администратору Naseeb.',
  ],
};

export function schoolCounselorMessages(language) {
  return Object.fromEntries(Object.entries(messages).map(([key, values]) => [key, values[language === 'uz' ? 0 : 1]]));
}
