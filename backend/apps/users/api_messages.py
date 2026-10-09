"""Uzbek and Russian text for the API error messages students see most.

The API always builds its error messages in English (see
ApiErrorLocalizationMiddleware); these tables turn a known English message into
the reader's language. A message that is not listed falls back to a generic
message for its status code, so English never leaks into a uz/ru response.

EXACT: English message -> {'uz': ..., 'ru': ...}
PATTERNS: (regex, {'uz': template, 'ru': template}); the templates use the
regex groups as {0}, {1}, ...
"""
import re

EXACT = {
    # Django REST framework and Django built-ins
    'This field may not be null.': {
        'uz': 'Bu maydonni to‘ldirish shart.',
        'ru': 'Это поле обязательно.',
    },
    'A valid integer is required.': {
        'uz': 'Butun son kiriting.',
        'ru': 'Введите целое число.',
    },
    'A valid number is required.': {
        'uz': 'Son kiriting.',
        'ru': 'Введите число.',
    },
    'Not a valid string.': {
        'uz': 'Matn kiriting.',
        'ru': 'Введите текст.',
    },
    'Must be a valid boolean.': {
        'uz': '“Ha” yoki “Yo‘q” qiymatini tanlang.',
        'ru': 'Выберите «Да» или «Нет».',
    },
    'Enter a valid URL.': {
        'uz': 'To‘g‘ri havola kiriting.',
        'ru': 'Введите корректную ссылку.',
    },
    'This list may not be empty.': {
        'uz': 'Kamida bittasini tanlang.',
        'ru': 'Выберите хотя бы один вариант.',
    },
    'No file was submitted.': {
        'uz': 'Fayl tanlanmadi.',
        'ru': 'Файл не выбран.',
    },
    'The submitted file is empty.': {
        'uz': 'Tanlangan fayl bo‘sh.',
        'ru': 'Выбранный файл пуст.',
    },
    'The submitted data was not a file. Check the encoding type on the form.': {
        'uz': 'Fayl yuborilmadi. Faylni qayta tanlang.',
        'ru': 'Файл не был отправлен. Выберите файл заново.',
    },
    'Upload a valid image. The file you uploaded was either not an image or a corrupted image.': {
        'uz': 'Rasm faylini yuklang. Tanlangan fayl rasm emas yoki shikastlangan.',
        'ru': 'Загрузите изображение. Выбранный файл не является изображением или повреждён.',
    },
    'This password is too common.': {
        'uz': 'Bu parol juda oddiy. Boshqa parol tanlang.',
        'ru': 'Этот пароль слишком простой. Выберите другой.',
    },
    'This password is entirely numeric.': {
        'uz': 'Parol faqat raqamlardan iborat bo‘lmasligi kerak.',
        'ru': 'Пароль не может состоять только из цифр.',
    },
    'Request was throttled.': {
        'uz': 'Juda ko‘p so‘rov yuborildi.',
        'ru': 'Слишком много запросов.',
    },
    'No active account found with the given credentials': {
        'uz': 'Login yoki parol noto‘g‘ri.',
        'ru': 'Неверный логин или пароль.',
    },
    'Given token not valid for any token type': {
        'uz': 'Sessiya tugagan. Qayta kiring.',
        'ru': 'Сессия истекла. Войдите снова.',
    },
    'Token is invalid or expired': {
        'uz': 'Sessiya tugagan. Qayta kiring.',
        'ru': 'Сессия истекла. Войдите снова.',
    },
    'Token is blacklisted': {
        'uz': 'Sessiya tugagan. Qayta kiring.',
        'ru': 'Сессия истекла. Войдите снова.',
    },
    'User not found': {
        'uz': 'Akkaunt topilmadi. Qayta kiring.',
        'ru': 'Аккаунт не найден. Войдите снова.',
    },
    'User is inactive': {
        'uz': 'Akkaunt faolsizlantirilgan. Administratorga murojaat qiling.',
        'ru': 'Аккаунт деактивирован. Обратитесь к администратору.',
    },
    # Sign-in and password change
    'No mandatory password change is pending.': {
        'uz': 'Parolni majburiy o‘zgartirish talab qilinmaydi.',
        'ru': 'Обязательная смена пароля не требуется.',
    },
    'Choose a password different from the temporary password.': {
        'uz': 'Vaqtinchalik paroldan farqli parol tanlang.',
        'ru': 'Выберите пароль, отличный от временного.',
    },
    'Passwords do not match.': {
        'uz': 'Parollar mos kelmadi.',
        'ru': 'Пароли не совпадают.',
    },
    # Profile, onboarding and the Student Center
    'Only students can complete their profile.': {
        'uz': 'Profilni faqat o‘quvchi to‘ldira oladi.',
        'ru': 'Заполнить профиль может только ученик.',
    },
    'Student profile not found.': {
        'uz': 'O‘quvchi profili topilmadi.',
        'ru': 'Профиль ученика не найден.',
    },
    'Complete your profile first.': {
        'uz': 'Avval profilingizni to‘ldiring.',
        'ru': 'Сначала заполните профиль.',
    },
    'Finish creating your student profile first.': {
        'uz': 'Avval o‘quvchi profilingizni to‘ldirib bo‘ling.',
        'ru': 'Сначала завершите создание профиля ученика.',
    },
    'Only the student can edit their profile.': {
        'uz': 'Profilni faqat o‘quvchining o‘zi tahrirlay oladi.',
        'ru': 'Редактировать профиль может только сам ученик.',
    },
    'This field requires counselor review.': {
        'uz': 'Bu maydonni maslahatchi ko‘rib chiqishi kerak.',
        'ru': 'Это поле должен проверить консультант.',
    },
    'There is nothing to save.': {
        'uz': 'Saqlanadigan o‘zgarish yo‘q.',
        'ru': 'Нет изменений для сохранения.',
    },
    'Select one or more supported countries.': {
        'uz': 'Ro‘yxatdan bir yoki bir nechta davlatni tanlang.',
        'ru': 'Выберите одну или несколько стран из списка.',
    },
    'GPA cannot exceed its scale.': {
        'uz': 'GPA o‘z shkalasidan oshmasligi kerak.',
        'ru': 'GPA не может превышать свою шкалу.',
    },
    'Rank cannot exceed class size.': {
        'uz': 'O‘rin sinfdagi o‘quvchilar sonidan oshmasligi kerak.',
        'ru': 'Место в рейтинге не может превышать размер класса.',
    },
    'Choose AP or IB.': {
        'uz': 'AP yoki IB ni tanlang.',
        'ru': 'Выберите AP или IB.',
    },
    'Enter the language.': {
        'uz': 'Tilni kiriting.',
        'ru': 'Укажите язык.',
    },
    'Choose a level.': {
        'uz': 'Darajani tanlang.',
        'ru': 'Выберите уровень.',
    },
    'Enter a valid link, like https://linkedin.com/in/your-name.': {
        'uz': 'To‘g‘ri havola kiriting, masalan https://linkedin.com/in/your-name.',
        'ru': 'Введите корректную ссылку, например https://linkedin.com/in/your-name.',
    },
    'Enter the subject.': {
        'uz': 'Fanni kiriting.',
        'ru': 'Укажите предмет.',
    },
    'Scores start at 1.': {
        'uz': 'Ball 1 dan boshlanadi.',
        'ru': 'Баллы начинаются с 1.',
    },
    'IB scores go from 1 to 7.': {
        'uz': 'IB ballari 1 dan 7 gacha bo‘ladi.',
        'ru': 'Баллы IB — от 1 до 7.',
    },
    'AP scores go from 1 to 5.': {
        'uz': 'AP ballari 1 dan 5 gacha bo‘ladi.',
        'ru': 'Баллы AP — от 1 до 5.',
    },
    'Enter a whole number.': {
        'uz': 'Butun son kiriting.',
        'ru': 'Введите целое число.',
    },
    'Use whole or half bands, like 6 or 6.5.': {
        'uz': 'Butun yoki yarim ball kiriting, masalan 6 yoki 6.5.',
        'ru': 'Используйте целые или половинные баллы, например 6 или 6.5.',
    },
    'SAT scores go up in steps of 10, like 650 or 660.': {
        'uz': 'SAT ballari 10 tadan oshadi, masalan 650 yoki 660.',
        'ru': 'Баллы SAT идут с шагом 10, например 650 или 660.',
    },
    'IELTS bands go from 0 to 9.': {
        'uz': 'IELTS ballari 0 dan 9 gacha bo‘ladi.',
        'ru': 'Баллы IELTS — от 0 до 9.',
    },
    'Enter a band like 6.5.': {
        'uz': 'Ballni kiriting, masalan 6.5.',
        'ru': 'Введите балл, например 6.5.',
    },
    'SAT totals go from 400 to 1600.': {
        'uz': 'SAT umumiy bali 400 dan 1600 gacha bo‘ladi.',
        'ru': 'Общий балл SAT — от 400 до 1600.',
    },
    'SAT section scores go from 200 to 800.': {
        'uz': 'SAT bo‘lim ballari 200 dan 800 gacha bo‘ladi.',
        'ru': 'Баллы разделов SAT — от 200 до 800.',
    },
    'Enter the date you took the test.': {
        'uz': 'Test topshirgan sanangizni kiriting.',
        'ru': 'Укажите дату сдачи теста.',
    },
    'This date is in the future. If the test has not happened yet, choose "I have booked a test date".': {
        'uz': 'Bu sana kelajakda. Agar test hali bo‘lmagan bo‘lsa, “Test sanasini band qildim” ni tanlang.',
        'ru': 'Эта дата в будущем. Если тест ещё не прошёл, выберите «Я записан(а) на тест».',
    },
    'Enter the date of your booked test.': {
        'uz': 'Band qilingan test sanasini kiriting.',
        'ru': 'Укажите дату, на которую вы записаны на тест.',
    },
    'Enter a date from 2015 or later.': {
        'uz': '2015-yil yoki undan keyingi sanani kiriting.',
        'ru': 'Укажите дату не ранее 2015 года.',
    },
    'Enter a date within the next three years.': {
        'uz': 'Keyingi uch yil ichidagi sanani kiriting.',
        'ru': 'Укажите дату в пределах следующих трёх лет.',
    },
    'Enter your overall band score.': {
        'uz': 'Umumiy ballingizni kiriting.',
        'ru': 'Укажите общий балл.',
    },
    'Enter all four section scores, or leave all four empty.': {
        'uz': 'To‘rtala bo‘lim balini kiriting yoki to‘rttasini ham bo‘sh qoldiring.',
        'ru': 'Укажите баллы всех четырёх разделов или оставьте все четыре пустыми.',
    },
    'Enter this section score.': {
        'uz': 'Bu bo‘lim balini kiriting.',
        'ru': 'Укажите балл за этот раздел.',
    },
    'Choose Yes or No.': {
        'uz': '“Ha” yoki “Yo‘q” ni tanlang.',
        'ru': 'Выберите «Да» или «Нет».',
    },
    'Enter your highest score for this section.': {
        'uz': 'Bu bo‘lim bo‘yicha eng yuqori balingizni kiriting.',
        'ru': 'Укажите свой лучший балл за этот раздел.',
    },
    'Your highest score cannot be lower than your best test day score.': {
        'uz': 'Eng yuqori ball eng yaxshi test kunidagi baldan past bo‘lmasligi kerak.',
        'ru': 'Лучший балл не может быть ниже балла за лучший день теста.',
    },
    # Other tests and certificates in the Test scores section
    'Choose the type of test or certificate.': {
        'uz': 'Test yoki sertifikat turini tanlang.',
        'ru': 'Выберите тип теста или сертификата.',
    },
    'Enter the name of the certificate.': {
        'uz': 'Sertifikat nomini kiriting.',
        'ru': 'Укажите название сертификата.',
    },
    'Enter your score or result.': {
        'uz': 'Ball yoki natijangizni kiriting.',
        'ru': 'Укажите балл или результат.',
    },
    'TOEFL iBT scores go from 0 to 120.': {
        'uz': 'TOEFL iBT ballari 0 dan 120 gacha bo‘ladi.',
        'ru': 'Баллы TOEFL iBT — от 0 до 120.',
    },
    'Duolingo English Test scores go from 10 to 160.': {
        'uz': 'Duolingo English Test ballari 10 dan 160 gacha bo‘ladi.',
        'ru': 'Баллы Duolingo English Test — от 10 до 160.',
    },
    'Duolingo scores go up in steps of 5, like 120 or 125.': {
        'uz': 'Duolingo ballari 5 tadan oshadi, masalan 120 yoki 125.',
        'ru': 'Баллы Duolingo идут с шагом 5, например 120 или 125.',
    },
    'PTE Academic scores go from 10 to 90.': {
        'uz': 'PTE Academic ballari 10 dan 90 gacha bo‘ladi.',
        'ru': 'Баллы PTE Academic — от 10 до 90.',
    },
    'ACT composite scores go from 1 to 36.': {
        'uz': 'ACT umumiy bali 1 dan 36 gacha bo‘ladi.',
        'ru': 'Общий балл ACT — от 1 до 36.',
    },
    'Cambridge English scores go from 80 to 230.': {
        'uz': 'Cambridge English ballari 80 dan 230 gacha bo‘ladi.',
        'ru': 'Баллы Cambridge English — от 80 до 230.',
    },
    'The test date cannot be in the future.': {
        'uz': 'Test sanasi kelajakda bo‘lishi mumkin emas.',
        'ru': 'Дата теста не может быть в будущем.',
    },
    # Profile photo and file uploads
    'Only the student can change their own profile photo.': {
        'uz': 'Profil rasmini faqat o‘quvchining o‘zi o‘zgartira oladi.',
        'ru': 'Изменить фото профиля может только сам ученик.',
    },
    'Choose an image to upload.': {
        'uz': 'Yuklash uchun rasm tanlang.',
        'ru': 'Выберите изображение для загрузки.',
    },
    'The photo must be 5 MB or smaller.': {
        'uz': 'Rasm hajmi 5 MB dan oshmasligi kerak.',
        'ru': 'Фото должно быть не больше 5 МБ.',
    },
    'This image is too large to process.': {
        'uz': 'Bu rasm qayta ishlash uchun juda katta.',
        'ru': 'Изображение слишком большое для обработки.',
    },
    'This file is not a valid image.': {
        'uz': 'Bu fayl yaroqli rasm emas.',
        'ru': 'Этот файл не является корректным изображением.',
    },
    'Use a PNG, JPEG or WebP image.': {
        'uz': 'PNG, JPEG yoki WebP rasm yuklang.',
        'ru': 'Загрузите изображение PNG, JPEG или WebP.',
    },
    'The selected file is empty.': {
        'uz': 'Tanlangan fayl bo‘sh.',
        'ru': 'Выбранный файл пуст.',
    },
    'This file is not a valid PDF.': {
        'uz': 'Bu fayl yaroqli PDF emas.',
        'ru': 'Этот файл не является корректным PDF.',
    },
    'This file is not a valid HEIC image.': {
        'uz': 'Bu fayl yaroqli HEIC rasm emas.',
        'ru': 'Этот файл не является корректным изображением HEIC.',
    },
    'This legacy Office file is invalid.': {
        'uz': 'Bu eski Office fayli yaroqsiz.',
        'ru': 'Этот файл старого формата Office повреждён.',
    },
    'This file is not a valid RTF document.': {
        'uz': 'Bu fayl yaroqli RTF hujjat emas.',
        'ru': 'Этот файл не является корректным документом RTF.',
    },
    'Text documents cannot contain binary data.': {
        'uz': 'Matnli hujjatda ikkilik ma’lumot bo‘lmasligi kerak.',
        'ru': 'Текстовый документ не может содержать двоичные данные.',
    },
    'The Office document structure is invalid.': {
        'uz': 'Office hujjatining tuzilishi noto‘g‘ri.',
        'ru': 'Структура документа Office повреждена.',
    },
    'Text documents must use UTF-8 encoding.': {
        'uz': 'Matnli hujjat UTF-8 kodlashda bo‘lishi kerak.',
        'ru': 'Текстовый документ должен быть в кодировке UTF-8.',
    },
    'The Office document is damaged or invalid.': {
        'uz': 'Office hujjati shikastlangan yoki yaroqsiz.',
        'ru': 'Документ Office повреждён или некорректен.',
    },
    'Use a valid https://docs.google.com/document/... link.': {
        'uz': 'To‘g‘ri https://docs.google.com/document/... havolasini kiriting.',
        'ru': 'Укажите корректную ссылку вида https://docs.google.com/document/...',
    },
    # Documents, tasks and records
    'Upload a new file to resubmit a document that is under review or approved.': {
        'uz': 'Tekshiruvdagi yoki tasdiqlangan hujjatni qayta yuborish uchun yangi fayl yuklang.',
        'ru': 'Чтобы повторно отправить документ на проверке или уже одобренный, загрузите новый файл.',
    },
    'Upload a file or add a Google Docs link before marking this document as uploaded.': {
        'uz': 'Hujjatni yuklangan deb belgilashdan oldin fayl yuklang yoki Google Docs havolasini qo‘shing.',
        'ru': 'Прежде чем отметить документ как загруженный, загрузите файл или добавьте ссылку на Google Docs.',
    },
    'Students can only submit documents for counselor review.': {
        'uz': 'O‘quvchi hujjatni faqat maslahatchi tekshiruviga yubora oladi.',
        'ru': 'Ученик может только отправить документ на проверку консультанту.',
    },
    'Students can only update task progress.': {
        'uz': 'O‘quvchi faqat vazifa holatini yangilay oladi.',
        'ru': 'Ученик может обновлять только ход выполнения задачи.',
    },
    'A self-task must start in To Do status.': {
        'uz': 'Shaxsiy vazifa “Bajarilishi kerak” holatidan boshlanadi.',
        'ru': 'Личная задача должна начинаться со статуса «К выполнению».',
    },
    'An approved task cannot be changed by a student.': {
        'uz': 'Tasdiqlangan vazifani o‘quvchi o‘zgartira olmaydi.',
        'ru': 'Ученик не может изменить одобренную задачу.',
    },
    'Only a teacher or counselor can change this field.': {
        'uz': 'Bu maydonni faqat o‘qituvchi yoki maslahatchi o‘zgartira oladi.',
        'ru': 'Это поле может изменить только учитель или консультант.',
    },
    'An approved recommendation letter cannot be reopened by a student.': {
        'uz': 'Tasdiqlangan tavsiyanomani o‘quvchi qayta ocha olmaydi.',
        'ru': 'Ученик не может заново открыть одобренное рекомендательное письмо.',
    },
    'Use true or false.': {
        'uz': '“Ha” yoki “Yo‘q” qiymatini yuboring.',
        'ru': 'Укажите «Да» или «Нет».',
    },
    'This application belongs to a different student.': {
        'uz': 'Bu ariza boshqa o‘quvchiga tegishli.',
        'ru': 'Эта заявка принадлежит другому ученику.',
    },
    # Meetings
    'Only students can request meetings.': {
        'uz': 'Uchrashuvni faqat o‘quvchi so‘ray oladi.',
        'ru': 'Запросить встречу может только ученик.',
    },
    'Choose a future meeting date and time.': {
        'uz': 'Uchrashuv uchun kelajakdagi sana va vaqtni tanlang.',
        'ru': 'Выберите дату и время встречи в будущем.',
    },
    'Choose a 30, 45, or 60 minute meeting.': {
        'uz': '30, 45 yoki 60 daqiqalik uchrashuvni tanlang.',
        'ru': 'Выберите встречу на 30, 45 или 60 минут.',
    },
    'This request expired before it was confirmed.': {
        'uz': 'Bu so‘rov tasdiqlanishidan oldin muddati tugadi.',
        'ru': 'Срок этого запроса истёк до подтверждения.',
    },
    'Only a meeting that has not started yet can be cancelled.': {
        'uz': 'Faqat hali boshlanmagan uchrashuvni bekor qilish mumkin.',
        'ru': 'Отменить можно только ещё не начавшуюся встречу.',
    },
    'Only a meeting that has not started yet can be rescheduled.': {
        'uz': 'Faqat hali boshlanmagan uchrashuvni ko‘chirish mumkin.',
        'ru': 'Перенести можно только ещё не начавшуюся встречу.',
    },
    'This staff member is no longer available. Request a new meeting instead.': {
        'uz': 'Bu xodim endi mavjud emas. Yangi uchrashuv so‘rang.',
        'ru': 'Этот сотрудник больше недоступен. Запросите новую встречу.',
    },
    # Meeting availability (staff slots students choose from)
    'Choose an available time.': {
        'uz': 'Bo‘sh vaqtlardan birini tanlang.',
        'ru': 'Выберите одно из свободных времён.',
    },
    'Choose a time from this staff member’s availability.': {
        'uz': 'Bu xodimning bo‘sh vaqtlaridan birini tanlang.',
        'ru': 'Выберите время из свободных часов этого сотрудника.',
    },
    'Only students can choose an available time.': {
        'uz': 'Bo‘sh vaqtni faqat o‘quvchi tanlay oladi.',
        'ru': 'Выбрать свободное время может только ученик.',
    },
    'This time has already been requested.': {
        'uz': 'Bu vaqt allaqachon so‘ralgan.',
        'ru': 'Это время уже запрошено.',
    },
    'This time overlaps another meeting.': {
        'uz': 'Bu vaqt boshqa uchrashuv bilan to‘qnashadi.',
        'ru': 'Это время пересекается с другой встречей.',
    },
    'This time overlaps an existing meeting.': {
        'uz': 'Bu vaqt mavjud uchrashuv bilan to‘qnashadi.',
        'ru': 'Это время пересекается с уже назначенной встречей.',
    },
    'This time overlaps an existing slot.': {
        'uz': 'Bu vaqt qo‘shilgan boshqa bo‘sh vaqt bilan to‘qnashadi.',
        'ru': 'Это время пересекается с уже добавленным свободным временем.',
    },
    'Only staff can manage availability.': {
        'uz': 'Bo‘sh vaqtlarni faqat xodimlar boshqara oladi.',
        'ru': 'Управлять свободным временем могут только сотрудники.',
    },
    'Availability is unavailable for this role.': {
        'uz': 'Bu rol uchun bo‘sh vaqtlar mavjud emas.',
        'ru': 'Для этой роли свободное время недоступно.',
    },
    'Cancel the meeting before removing this slot.': {
        'uz': 'Bu vaqtni o‘chirishdan oldin uchrashuvni bekor qiling.',
        'ru': 'Перед удалением этого времени отмените встречу.',
    },
    'Slot not found.': {
        'uz': 'Bo‘sh vaqt topilmadi.',
        'ru': 'Свободное время не найдено.',
    },
    'Choose a staff member from your school.': {
        'uz': 'Maktabingiz xodimlaridan birini tanlang.',
        'ru': 'Выберите сотрудника вашей школы.',
    },
    'A counselor has not been assigned yet.': {
        'uz': 'Sizga hali maslahatchi biriktirilmagan.',
        'ru': 'Консультант ещё не назначен.',
    },
    # Messages
    'This user is not available as a direct-message contact.': {
        'uz': 'Bu foydalanuvchiga shaxsiy xabar yozib bo‘lmaydi.',
        'ru': 'Этому пользователю нельзя написать личное сообщение.',
    },
    'This channel is invite-only.': {
        'uz': 'Bu kanalga faqat taklif orqali qo‘shilish mumkin.',
        'ru': 'В этот канал можно попасть только по приглашению.',
    },
    'Direct conversations cannot be left.': {
        'uz': 'Shaxsiy suhbatdan chiqib bo‘lmaydi.',
        'ru': 'Из личной переписки нельзя выйти.',
    },
    'Assign another owner before leaving.': {
        'uz': 'Chiqishdan oldin boshqa egani tayinlang.',
        'ru': 'Перед выходом назначьте другого владельца.',
    },
    'Join the channel before viewing its members.': {
        'uz': 'A’zolarni ko‘rish uchun avval kanalga qo‘shiling.',
        'ru': 'Чтобы увидеть участников, сначала вступите в канал.',
    },
    'Join the channel before marking it read.': {
        'uz': 'Kanalni o‘qilgan deb belgilash uchun avval unga qo‘shiling.',
        'ru': 'Чтобы отметить канал прочитанным, сначала вступите в него.',
    },
    'Join the channel before posting.': {
        'uz': 'Xabar yozish uchun avval kanalga qo‘shiling.',
        'ru': 'Чтобы писать сообщения, сначала вступите в канал.',
    },
    'Join the channel before reporting a message.': {
        'uz': 'Xabar ustidan shikoyat qilish uchun avval kanalga qo‘shiling.',
        'ru': 'Чтобы пожаловаться на сообщение, сначала вступите в канал.',
    },
    'This channel is archived.': {
        'uz': 'Bu kanal arxivlangan.',
        'ru': 'Этот канал в архиве.',
    },
    'Select a message in this conversation.': {
        'uz': 'Shu suhbatdagi xabarni tanlang.',
        'ru': 'Выберите сообщение из этой переписки.',
    },
    'Deleted messages cannot be reported.': {
        'uz': 'O‘chirilgan xabar ustidan shikoyat qilib bo‘lmaydi.',
        'ru': 'На удалённое сообщение нельзя пожаловаться.',
    },
    'You cannot report your own message.': {
        'uz': 'O‘z xabaringiz ustidan shikoyat qila olmaysiz.',
        'ru': 'Нельзя пожаловаться на своё сообщение.',
    },
    'Select a valid report reason.': {
        'uz': 'Shikoyat sababini tanlang.',
        'ru': 'Выберите причину жалобы.',
    },
    'Report details cannot exceed 2,000 characters.': {
        'uz': 'Shikoyat tafsilotlari 2 000 belgidan oshmasligi kerak.',
        'ru': 'Описание жалобы не может быть длиннее 2 000 символов.',
    },
    'You have already reported this message.': {
        'uz': 'Bu xabar ustidan allaqachon shikoyat qilgansiz.',
        'ru': 'Вы уже пожаловались на это сообщение.',
    },
    'Accepted answers are only available in Discussions.': {
        'uz': 'Javobni qabul qilish faqat muhokamalarda mavjud.',
        'ru': 'Принимать ответы можно только в обсуждениях.',
    },
    'Only a reply can be accepted as an answer.': {
        'uz': 'Faqat javob xabarini qabul qilish mumkin.',
        'ru': 'Принять как ответ можно только ответное сообщение.',
    },
    'Only the discussion owner or moderator can accept an answer.': {
        'uz': 'Javobni faqat muhokama egasi yoki moderator qabul qila oladi.',
        'ru': 'Принять ответ может только автор обсуждения или модератор.',
    },
    'Anonymous mode is only available in Community and Discussions.': {
        'uz': 'Anonim rejim faqat hamjamiyat va muhokamalarda mavjud.',
        'ru': 'Анонимный режим доступен только в сообществе и обсуждениях.',
    },
    'Reply must belong to the same channel.': {
        'uz': 'Javob shu kanalga tegishli bo‘lishi kerak.',
        'ru': 'Ответ должен относиться к этому же каналу.',
    },
    'This field cannot be changed after posting.': {
        'uz': 'Xabar yuborilgandan keyin bu maydonni o‘zgartirib bo‘lmaydi.',
        'ru': 'Это поле нельзя изменить после отправки.',
    },
    'Use the direct action to open a direct conversation.': {
        'uz': 'Shaxsiy suhbatni “Yangi xabar” orqali oching.',
        'ru': 'Откройте личную переписку через «Новое сообщение».',
    },
    'Only school staff can create Group or Community channels.': {
        'uz': 'Guruh yoki hamjamiyat kanalini faqat maktab xodimlari yarata oladi.',
        'ru': 'Создавать группы и сообщества могут только сотрудники школы.',
    },
    'A channel name or discussion title is required.': {
        'uz': 'Kanal nomi yoki muhokama sarlavhasini kiriting.',
        'ru': 'Укажите название канала или тему обсуждения.',
    },
    'Only members of a school can create channels.': {
        'uz': 'Kanalni faqat maktab a’zolari yarata oladi.',
        'ru': 'Создавать каналы могут только участники школы.',
    },
    'You can only create channels in your own school.': {
        'uz': 'Kanalni faqat o‘z maktabingizda yarata olasiz.',
        'ru': 'Создавать каналы можно только в своей школе.',
    },
    # Essay Lab
    'Essay not found.': {
        'uz': 'Insho topilmadi.',
        'ru': 'Эссе не найдено.',
    },
    'Tab not found.': {
        'uz': 'Varaq topilmadi.',
        'ru': 'Вкладка не найдена.',
    },
    'Checkpoint not found.': {
        'uz': 'Saqlangan versiya topilmadi.',
        'ru': 'Сохранённая версия не найдена.',
    },
    'Folder not found.': {
        'uz': 'Papka topilmadi.',
        'ru': 'Папка не найдена.',
    },
    'The Essay Lab is available to students only.': {
        'uz': 'Insholar laboratoriyasi faqat o‘quvchilar uchun.',
        'ru': 'Лаборатория эссе доступна только ученикам.',
    },
    'You are going a little fast. Please wait a moment and try again.': {
        'uz': 'Biroz shoshilyapsiz. Bir oz kutib, qayta urinib ko‘ring.',
        'ru': 'Слишком быстро. Подождите немного и попробуйте снова.',
    },
    'This essay is too large to save (256 KB limit).': {
        'uz': 'Insho saqlash uchun juda katta (256 KB chegarasi).',
        'ru': 'Эссе слишком большое для сохранения (лимит 256 КБ).',
    },
    'This document has several tabs. The student edits its text in the Essay Lab.': {
        'uz': 'Bu hujjatda bir nechta varaq bor. Matn Insholar laboratoriyasida tahrirlanadi.',
        'ru': 'В этом документе несколько вкладок. Текст редактируется в Лаборатории эссе.',
    },
    # Profile assessment
    'A challenge key is required.': {
        'uz': 'Test tanlanmagan.',
        'ru': 'Тест не выбран.',
    },
    'Answers must be a non-empty object.': {
        'uz': 'Kamida bitta savolga javob bering.',
        'ru': 'Ответьте хотя бы на один вопрос.',
    },
    # Support
    'Only the ticket requester can mark a response as viewed.': {
        'uz': 'Javobni ko‘rilgan deb faqat so‘rov muallifi belgilay oladi.',
        'ru': 'Отметить ответ просмотренным может только автор запроса.',
    },
}

_P = re.compile
PATTERNS = (
    (_P(r'^Ensure this field has no more than (\d+) characters\.$'), {
        'uz': '{0} belgidan oshmasin.',
        'ru': 'Не более {0} символов.',
    }),
    (_P(r'^Ensure this field has at least (\d+) characters\.$'), {
        'uz': 'Kamida {0} belgi kiriting.',
        'ru': 'Не менее {0} символов.',
    }),
    (_P(r'^Ensure this value is less than or equal to (-?[\d.]+)\.$'), {
        'uz': 'Qiymat {0} dan oshmasligi kerak.',
        'ru': 'Значение не должно превышать {0}.',
    }),
    (_P(r'^Ensure this value is greater than or equal to (-?[\d.]+)\.$'), {
        'uz': 'Qiymat kamida {0} bo‘lishi kerak.',
        'ru': 'Значение должно быть не меньше {0}.',
    }),
    (_P(r'^Ensure that there are no more than (\d+) digits in total\.$'), {
        'uz': 'Son {0} ta raqamdan oshmasin.',
        'ru': 'Число должно содержать не более {0} цифр.',
    }),
    (_P(r'^Ensure that there are no more than (\d+) decimal places\.$'), {
        'uz': 'Verguldan keyin {0} ta raqamdan oshmasin.',
        'ru': 'Не более {0} знаков после запятой.',
    }),
    (_P(r'^"(.*)" is not a valid choice\.$'), {
        'uz': '“{0}” ruxsat etilgan qiymat emas. Ro‘yxatdan tanlang.',
        'ru': '«{0}» — недопустимое значение. Выберите из списка.',
    }),
    (_P(r'^Date has wrong format\. Use one of these formats instead: .*$'), {
        'uz': 'Sana noto‘g‘ri kiritilgan.',
        'ru': 'Неверный формат даты.',
    }),
    (_P(r'^Datetime has wrong format\. Use one of these formats instead: .*$'), {
        'uz': 'Sana yoki vaqt noto‘g‘ri kiritilgan.',
        'ru': 'Неверный формат даты или времени.',
    }),
    (_P(r'^Expected a list of items but got type "\w+"\.$'), {
        'uz': 'Ro‘yxatdan tanlang.',
        'ru': 'Выберите значения из списка.',
    }),
    (_P(r'^This password is too short\. It must contain at least (\d+) characters?\.$'), {
        'uz': 'Parol juda qisqa: kamida {0} belgi bo‘lsin.',
        'ru': 'Пароль слишком короткий: нужно не менее {0} символов.',
    }),
    (_P(r'^The password is too similar to the [\w ]+\.$'), {
        'uz': 'Parol akkaunt ma’lumotlaringizga juda o‘xshash.',
        'ru': 'Пароль слишком похож на данные вашего аккаунта.',
    }),
    (_P(r'^File is larger than the (\d+) MB limit\.$'), {
        'uz': 'Fayl hajmi {0} MB chegarasidan katta.',
        'ru': 'Файл больше допустимых {0} МБ.',
    }),
    (_P(r'^The image must be (\d+) MB or smaller\.$'), {
        'uz': 'Rasm hajmi {0} MB dan oshmasligi kerak.',
        'ru': 'Изображение должно быть не больше {0} МБ.',
    }),
    (_P(r'^Request body exceeds the (\d+) MB limit\.$'), {
        'uz': 'Yuborilayotgan ma’lumot {0} MB chegarasidan katta.',
        'ru': 'Размер запроса превышает {0} МБ.',
    }),
    (_P(r'^Unsupported image type\. Allowed: (.+)\.$'), {
        'uz': 'Bu rasm turi qo‘llab-quvvatlanmaydi. Ruxsat etilgan: {0}.',
        'ru': 'Этот тип изображения не поддерживается. Допустимые: {0}.',
    }),
    (_P(r'^GPA cannot exceed its ([\d.]+) scale\.$'), {
        'uz': 'GPA {0} shkalasidan oshmasligi kerak.',
        'ru': 'GPA не может превышать шкалу {0}.',
    }),
    (_P(r'^Enter a number from 1 to (\d+)\.$'), {
        'uz': '1 dan {0} gacha son kiriting.',
        'ru': 'Введите число от 1 до {0}.',
    }),
    (_P(r'^With these section scores your overall band is ([\d.]+)\. Check your test report\.$'), {
        'uz': 'Bu bo‘lim ballari bilan umumiy ballingiz {0} bo‘ladi. Test natijangizni tekshiring.',
        'ru': 'С такими баллами за разделы общий балл — {0}. Проверьте результаты теста.',
    }),
    (_P(r'^You can add up to (\d+) languages\.$'), {
        'uz': 'Ko‘pi bilan {0} ta til qo‘shish mumkin.',
        'ru': 'Можно добавить не более {0} языков.',
    }),
    (_P(r'^You can add up to (\d+) skills\.$'), {
        'uz': 'Ko‘pi bilan {0} ta ko‘nikma qo‘shish mumkin.',
        'ru': 'Можно добавить не более {0} навыков.',
    }),
    (_P(r'^You can add up to (\d+) interests\.$'), {
        'uz': 'Ko‘pi bilan {0} ta qiziqish qo‘shish mumkin.',
        'ru': 'Можно добавить не более {0} интересов.',
    }),
    (_P(r'^You can add up to (\d+) other test scores or certificates\.$'), {
        'uz': 'Boshqa test natijalari yoki sertifikatlardan ko‘pi bilan {0} tasini qo‘shish mumkin.',
        'ru': 'Можно добавить не более {0} других результатов тестов или сертификатов.',
    }),
    (_P(r'^Answer .+ must be a whole number from 1 to 5\.$'), {
        'uz': 'Har bir javob 1 dan 5 gacha butun son bo‘lishi kerak.',
        'ru': 'Каждый ответ должен быть целым числом от 1 до 5.',
    }),
    (_P(r'^You are muted in this channel until .+\.$'), {
        'uz': 'Bu kanalda vaqtincha xabar yoza olmaysiz.',
        'ru': 'В этом канале вы временно не можете писать сообщения.',
    }),
    (_P(r'^An? \w+ meeting cannot be changed to \w+\.$'), {
        'uz': 'Uchrashuvning hozirgi holatida bu amalni bajarib bo‘lmaydi.',
        'ru': 'В текущем статусе встречи это действие недоступно.',
    }),
)

# DRF appends the wait to a throttled message: "...  Expected available in 30 seconds."
THROTTLE_WAIT = _P(r'^(?P<message>.*?)\s*Expected available in (?P<seconds>\d+) seconds?\.$')
THROTTLE_WAIT_TEXT = {
    'uz': '{seconds} soniyadan keyin qayta urinib ko‘ring.',
    'ru': 'Повторите через {seconds} с.',
}


def translate(text, language):
    """The uz/ru text for a known English message, or None."""
    exact = EXACT.get(text)
    if exact:
        return exact.get(language)
    for pattern, templates in PATTERNS:
        match = pattern.match(text)
        if match:
            return templates[language].format(*match.groups())
    wait = THROTTLE_WAIT.match(text)
    if wait:
        message = wait.group('message')
        head = translate(message, language) if message else None
        tail = THROTTLE_WAIT_TEXT[language].format(seconds=wait.group('seconds'))
        return f'{head} {tail}' if head else tail
    return None
