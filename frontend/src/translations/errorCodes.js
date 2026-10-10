// Messages for API error codes ({detail, code} bodies), keyed by the code: [uz, ru].
// English uses the server's own `detail`, so only translations live here. The server's
// table for older clients (backend/apps/users/api_messages.py) must use the same
// wording; backend test_error_code_translations checks it.
export const ERROR_CODE_TRANSLATIONS = {
  essay_changed: [
    'Siz ochganingizdan keyin insho o‘zgardi. Eng so‘nggi versiyani tekshiring va tahrirni qayta saqlang.',
    'Эссе изменилось после того, как вы его открыли. Проверьте последнюю версию и сохраните правку ещё раз.',
  ],
  precondition_required: [
    'Matnni o‘zgartirishdan oldin inshoni yangilang, shunda yangiroq o‘zgarishlar ustidan yozilmaydi.',
    'Обновите эссе перед изменением текста, чтобы не затереть более новые правки.',
  ],
  student_authored: [
    'O‘z ishini faqat o‘quvchi o‘zgartira oladi. Buning o‘rniga izoh bilan qaytaring.',
    'Изменять свою работу может только ученик. Вместо этого верните её с комментарием.',
  ],
  student_authored_delete: [
    'O‘z ishini faqat o‘quvchi o‘chira oladi. Buning o‘rniga izoh bilan qaytaring.',
    'Удалить свою работу может только ученик. Вместо этого верните её с комментарием.',
  ],
  university_in_use: [
    'Bu universitetga o‘quvchilar arizalari, ta’lim dasturlari yoki stipendiyalar bog‘langan. O‘chirish o‘rniga tahrirlang.',
    'К этому университету привязаны заявки учеников, программы или стипендии. Отредактируйте его вместо удаления.',
  ],
};

export const errorCodeKey = (code) => `error_code.${code}`;

export function errorCodeMessages(language) {
  const index = language === 'uz' ? 0 : 1;
  return Object.fromEntries(Object.entries(ERROR_CODE_TRANSLATIONS).map(([code, values]) => [errorCodeKey(code), values[index]]));
}
