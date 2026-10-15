// These drafts are intentionally shown in all three languages, in this order.
// The copy describes the models and role scopes; it makes no compliance promises.
export const LEGAL_LANGUAGES = ['uz', 'ru', 'en'];

export const LEGAL_DOCUMENTS = {
  privacy: {
    uz: {
      heading: 'Maxfiylik siyosati',
      language: 'O‘zbekcha',
      sections: [
        ['Nimalarni saqlaymiz?', 'Akkaunt nomi, ism, email, telefon, rol, maktab va yuklangan surat; o‘quvchi profili, ota-ona yoki vasiy aloqa ma’lumotlari, baholar va test natijalari, qiziqishlar, universitet rejalari, arizalar, hujjatlar, insholar va tavsiyanomalar saqlanadi. Vazifalar, yo‘l xaritasi, uchrashuvlar, yozishmalar, ota-ona bog‘lanishlari va rozilik holati, yordam so‘rovlari ham saqlanadi. Parollar xeshlanadi. Xavfsizlik, kirish va ma’muriy amallar jurnallari hamda ilovadagi faol vaqt yig‘indilari qayd etiladi.'],
        ['Kim ko‘radi?', 'O‘quvchi o‘z ma’lumotlarini ko‘radi. Ota-ona faqat qabul qilgan bog‘lanish orqali ruxsat berilgan farzandining qisqa ma’lumotlarini ko‘radi; farzandning maxfiy yozishmalari, insho matni va ichki izohlar ochilmaydi. Counselor o‘ziga biriktirilgan, o‘z maktabidagi o‘quvchilar bilan ishlaydi. O‘qituvchi va maktab vakili o‘z maktabi doirasida roliga ruxsat etilgan ma’lumotlarni ko‘radi. Platforma ma’murlari huquqi darajasida boshqaradi; maxfiy kontent umumiy Student 360 ko‘rinishiga kiritilmaydi. Fayllar va yozishmalar tegishli ruxsat orqali ochiladi.'],
        ['Xizmatlar va qurilmangiz', 'Hosting, fayl saqlash va xatolarni kuzatish xizmatlari sozlamalarga qarab ma’lumotlarni qayta ishlashi mumkin. AI funksiyasidan foydalanganda kerakli matn yoki qisqartirilgan kontekst sozlangan tashqi provayderga yuborilishi mumkin. Provayderlar, server joylashuvi va ularning saqlash shartlari release oldidan tasdiqlanishi kerak. Kirish uchun HttpOnly cookie, til, mavzu va ayrim qoralamalar uchun brauzer xotirasi ishlatiladi.'],
        ['Qancha vaqt saqlaymiz?', 'Profil, hujjat, yozishma, audit va zaxira nusxalari uchun yakuniy saqlash muddatlari hali tasdiqlanmagan. Akkauntni faolsizlantirish ma’lumotlarni avtomatik o‘chirmaydi. Ekran vaqti uchun koddagi standart chegara 365 kun; eski yozuvlarni tozalash alohida rejalashtirilgan ishga bog‘liq. Aniq muddatlar va zaxira nusxalaridan o‘chirish tartibi yurist va operator tomonidan tasdiqlanadi.'],
        ['O‘chirish yoki tuzatishni so‘rash', 'Akkauntingizni aniqlashga yetarli ma’lumot va qaysi yozuvni o‘chirish yoki tuzatish kerakligini yuboring. Parol yoki hujjat nusxasini birinchi xatga qo‘shmang. Jamoa so‘rov egasini va vakolatini tekshiradi; saqlanishi zarur yozuvlar, zaxira nusxalari va javob muddati alohida kelishiladi. Ota-ona bog‘lanishini uzish o‘quvchi yozuvlarini o‘chirmaydi.'],
      ],
      contact: 'Aloqa: maktabingiz administratori yoki Naseeb Edu yordam jamoasi —',
    },
    ru: {
      heading: 'Политика конфиденциальности',
      language: 'Русский',
      sections: [
        ['Что сохраняется?', 'Имя аккаунта, имя, email, телефон, роль, школа и загруженная фотография; профиль ученика, контакты родителя или опекуна, оценки и результаты тестов, интересы, планы поступления, заявки, документы, эссе и рекомендации. Также сохраняются задания, дорожная карта, встречи, переписка, связи с родителями и состояние согласия, обращения в поддержку. Пароли хешируются. Записываются журналы безопасности, входа и административных действий, а также суммарное активное время в приложении.'],
        ['Кто имеет доступ?', 'Ученик видит свои данные. Родитель видит только разрешённые краткие сведения о ребёнке по принятой связи; личная переписка ребёнка, текст эссе и внутренние заметки не раскрываются. Counselor работает с закреплёнными учениками своей школы. Учитель и представитель школы видят разрешённые для их роли данные своей школы. Администраторы платформы управляют данными в пределах своих прав; приватный контент не включается в общий Student 360. Файлы и переписка открываются по соответствующим разрешениям.'],
        ['Сервисы и ваше устройство', 'Сервисы хостинга, хранения файлов и мониторинга ошибок могут обрабатывать данные в зависимости от настроек. При использовании AI необходимый текст или сокращённый контекст может передаваться настроенному внешнему провайдеру. Список провайдеров, расположение серверов и условия хранения требуют подтверждения до release. Для входа используется HttpOnly cookie, для языка, темы и некоторых черновиков — память браузера.'],
        ['Сроки хранения', 'Окончательные сроки хранения профилей, документов, переписки, аудита и резервных копий ещё не утверждены. Деактивация аккаунта не удаляет данные автоматически. Стандартный предел для экранного времени в коде — 365 дней; очистка старых записей зависит от отдельной запланированной задачи. Точные сроки и порядок удаления из резервных копий должны быть утверждены юристом и оператором.'],
        ['Запрос удаления или исправления', 'Отправьте сведения, достаточные для определения аккаунта, и укажите записи, которые нужно удалить или исправить. Не прикладывайте пароль или копию документа к первому письму. Команда проверит личность и полномочия заявителя; необходимые для хранения записи, резервные копии и срок ответа согласуются отдельно. Отключение родительской связи не удаляет записи ученика.'],
      ],
      contact: 'Контакты: администратор вашей школы или поддержка Naseeb Edu —',
    },
    en: {
      heading: 'Privacy policy',
      language: 'English',
      sections: [
        ['What is stored?', 'Account name, name, email, phone, role, school and uploaded photo; student profile, parent or guardian contacts, grades and test results, interests, university plans, applications, documents, essays and recommendations. Tasks, roadmaps, meetings, messages, parent links and consent status, and support requests are also stored. Passwords are hashed. Security, sign-in and administration logs and aggregate active time in the app are recorded.'],
        ['Who can see it?', 'Students see their own records. Parents see only permitted summaries for a child through an accepted link; the child’s private messages, essay text and internal notes are excluded. Counselors work with assigned students in their own school. Teachers and school representatives see their school’s data as permitted by their role. Platform administrators manage records within their access tier; private content is excluded from the general Student 360 view. Files and conversations require the relevant permission.'],
        ['Services and your device', 'Hosting, file-storage and error-monitoring services may process data depending on configuration. When you use an AI feature, necessary text or reduced context may be sent to the configured external provider. Providers, server locations and their retention terms need confirmation before release. Sign-in uses an HttpOnly cookie; language, theme and some drafts use browser storage.'],
        ['How long is it kept?', 'Final retention periods for profiles, documents, messages, audit records and backups have not been approved. Deactivating an account does not automatically delete its data. The code’s default screen-time limit is 365 days; cleanup depends on a separately scheduled task. Exact periods and removal from backups require approval by the operator and lawyer.'],
        ['Request deletion or correction', 'Send enough information to identify your account and specify the records to delete or correct. Do not include a password or document copy in your first email. The team will verify the requester’s identity and authority; required retained records, backups and response time will be discussed separately. Disconnecting a parent link does not delete the student’s records.'],
      ],
      contact: 'Contact your school administrator or Naseeb Edu support —',
    },
  },
  terms: {
    uz: {
      heading: 'Foydalanish shartlari',
      language: 'O‘zbekcha',
      sections: [
        ['Xizmat va akkaunt', 'Naseeb Edu o‘quvchi, ota-ona, maktab va counselorning ta’lim hamda universitetga tayyorgarlik ishlarini tashkil qiladi. Akkauntlar xodim yoki maktab taklifi orqali beriladi; ochiq mustaqil ro‘yxatdan o‘tish yo‘q. Faqat o‘z akkauntingizdan foydalaning va kirish ma’lumotlarini boshqalarga bermang. Voyaga yetmaganlar uchun rozilik va vakillik talablari yurist bilan yakunlanadi.'],
        ['Rol va ma’lumotlar', 'Faqat sizga ruxsat etilgan ma’lumot va amallar bilan ishlang. O‘quvchi o‘z profilini, ota-ona ruxsat etilgan farzand ko‘rinishini, maktab o‘z maktabi doirasini, counselor biriktirilgan o‘quvchilarini ko‘radi. To‘g‘ri ma’lumot kiriting va yuklayotgan materialingizga ruxsatingiz bo‘lsin. Boshqa odamning ma’lumotini ruxsatsiz ulashmang, cheklovlarni chetlab o‘tmang va yozishmalarda haqorat yoki zararli kontent tarqatmang.'],
        ['Maslahat va natija', 'Katalog, test, tavsiya va AI javoblarini tekshirib foydalaning. Ular universitetga qabul, stipendiya yoki boshqa natijani kafolatlamaydi. Muhim muddatlar va universitet talablarini asl manbadan tekshiring. Xizmatda uzilish yoki xato bo‘lishi mumkin; muammoni yordam jamoasiga yuboring.'],
        ['Akkaunt, saqlash va o‘chirish', 'Ruxsatlar maktab, rol, ota-ona bog‘lanishi va tarifga qarab o‘zgarishi mumkin. Akkauntni faolsizlantirish yozuvlarni avtomatik o‘chirmaydi. Ma’lumot turlari, kim ko‘rishi, hali tasdiqlanmagan saqlash muddatlari va o‘chirish so‘rovi tartibi Maxfiylik siyosatida yozilgan. Tuzatish yoki o‘chirish uchun yordam jamoasiga murojaat qiling.'],
        ['Qoralamaning holati', 'Operatorning yuridik rekvizitlari, to‘lov va bekor qilish qoidalari, javobgarlik, nizolarni ko‘rish va voyaga yetmaganlar bo‘yicha shartlar hali yurist tomonidan tasdiqlanmagan. Bu qoralama yakuniy huquqiy shartnoma sifatida taqdim etilmaydi.'],
      ],
      contact: 'Aloqa: maktabingiz administratori yoki Naseeb Edu yordam jamoasi —',
    },
    ru: {
      heading: 'Условия использования',
      language: 'Русский',
      sections: [
        ['Сервис и аккаунт', 'Naseeb Edu помогает ученикам, родителям, школам и counselors организовать обучение и подготовку к поступлению. Аккаунты выдаются сотрудниками или по приглашению школы; открытой самостоятельной регистрации нет. Используйте только свой аккаунт и не передавайте данные входа. Требования к согласию и представительству несовершеннолетних будут уточнены с юристом.'],
        ['Роли и данные', 'Работайте только с разрешёнными данными и действиями. Ученик видит свой профиль, родитель — разрешённые сведения о ребёнке, школа — данные своей школы, counselor — закреплённых учеников. Указывайте достоверные сведения и загружайте материалы, на которые у вас есть разрешение. Не раскрывайте чужие данные без разрешения, не обходите ограничения и не распространяйте оскорбления или вредоносный контент.'],
        ['Рекомендации и результат', 'Проверяйте сведения каталога, тестов, рекомендаций и ответов AI. Они не гарантируют поступление, стипендию или иной результат. Важные сроки и требования вузов проверяйте по первоисточнику. Возможны перебои и ошибки; сообщайте о них поддержке.'],
        ['Аккаунт, хранение и удаление', 'Доступ может меняться в зависимости от школы, роли, родительской связи и тарифа. Деактивация аккаунта не удаляет записи автоматически. В Политике конфиденциальности описаны виды данных, доступ, ещё не утверждённые сроки хранения и запрос удаления. Для исправления или удаления обратитесь в поддержку.'],
        ['Статус черновика', 'Юридические реквизиты оператора, оплата и отмена, ответственность, рассмотрение споров и условия для несовершеннолетних ещё не утверждены юристом. Этот черновик не представлен как окончательный юридический договор.'],
      ],
      contact: 'Контакты: администратор вашей школы или поддержка Naseeb Edu —',
    },
    en: {
      heading: 'Terms of use',
      language: 'English',
      sections: [
        ['Service and account', 'Naseeb Edu helps students, parents, schools and counselors organize education and university preparation. Accounts are issued by staff or through school invitations; there is no open self-registration. Use only your own account and keep sign-in details private. Consent and representation requirements for minors will be finalized with a lawyer.'],
        ['Roles and data', 'Use only the records and actions you are permitted to access. Students see their own profile, parents see permitted child summaries, schools see their school’s data and counselors see assigned students. Provide accurate information and upload only materials you are authorized to use. Do not disclose another person’s data without permission, bypass restrictions or post abusive or harmful content.'],
        ['Advice and results', 'Check catalogue information, tests, recommendations and AI answers before relying on them. They do not guarantee admission, a scholarship or any other outcome. Verify important deadlines and university requirements with the original source. Interruptions and errors may occur; report problems to support.'],
        ['Account, retention and deletion', 'Access may change with school, role, parent link and plan. Deactivating an account does not automatically delete records. The Privacy policy describes data types, access, retention periods awaiting approval and deletion requests. Contact support to request correction or deletion.'],
        ['Draft status', 'The operator’s legal details, payment and cancellation rules, liability, dispute handling and terms for minors have not yet been approved by a lawyer. This draft is not presented as a final legal agreement.'],
      ],
      contact: 'Contact your school administrator or Naseeb Edu support —',
    },
  },
};
