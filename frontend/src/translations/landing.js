// Landing page copy. English is the source text; each entry is [Uzbek, Russian].
// The wording follows the platform description filed with IT Park: Naseeb Edu is
// a software (SaaS) product sold by subscription, not a human consulting service.
// AI claims must match the code: the AI is called "Naseeb AI" and writes essay
// feedback (quoting the essay), counselor letter ideas, major explanations and
// assistant answers. Rankings, matching, admission chance and the roadmap are
// rule-based. No RAG, citations, machine learning, eval suites or anomaly
// detection exist, so the copy must not claim them (tests/landingClaims.test.mjs).
export const LANDING_TRANSLATIONS = {
  // Brand and navigation
  'AI admission platform': ['Qabul uchun AI platforma', 'AI-платформа для поступления'],
  'How it works': ['Qanday ishlaydi', 'Как это работает'],
  'Modules': ['Modullar', 'Модули'],
  'Plans': ['Tariflar', 'Тарифы'],

  // Hero
  'University admission platform with Naseeb AI': ['Naseeb AI bilan universitetga qabul platformasi', 'Платформа для поступления в университет с Naseeb AI'],
  'Your path to university,': ['Universitetga yo‘lingiz', 'Ваш путь в университет'],
  'built from your profile.': ['profilingiz asosida quriladi.', 'строится по вашему профилю.'],
  'With Naseeb AI feedback.': ['Naseeb AI fikr-mulohazalari bilan.', 'С отзывами Naseeb AI.'],
  'Naseeb Edu brings your grades, test scores, assessment answers and essays into one profile, ranks universities and majors with clear rules, and gives Naseeb AI feedback on your essays.': ['Naseeb Edu baholaringiz, test natijalaringiz, so‘rovnoma javoblaringiz va inshongizni yagona profilga jamlaydi, universitet va yo‘nalishlarni aniq qoidalar asosida saralaydi hamda inshongiz bo‘yicha Naseeb AI fikr-mulohazasini beradi.', 'Naseeb Edu собирает ваши оценки, результаты тестов, ответы на опросники и эссе в одном профиле, ранжирует университеты и направления по понятным правилам и даёт отзывы Naseeb AI на ваши эссе.'],

  // Hero figures
  'Naseeb AI features': ['Naseeb AI funksiyalari', 'Функции Naseeb AI'],
  'Essay feedback, recommendation-letter ideas for counselors, major explanations and the assistant chat.': ['Insho bo‘yicha fikr-mulohaza, maslahatchilar uchun tavsiyanoma g‘oyalari, yo‘nalishlar izohi va yordamchi chat.', 'Отзывы на эссе, идеи рекомендательных писем для консультантов, пояснения к направлениям и чат-ассистент.'],
  'Match categories': ['Moslik toifalari', 'Категории подбора'],
  'Universities are sorted into Reach, Target and Safety by comparing your profile with their requirements.': ['Universitetlar profilingizni ularning talablari bilan solishtirish orqali Reach, Target va Safety toifalariga ajratiladi.', 'Университеты делятся на Reach, Target и Safety после сравнения вашего профиля с их требованиями.'],

  // Placement strip
  'Students using Naseeb Edu were admitted to': ['Naseeb Edu’dan foydalangan o‘quvchilar qabul qilingan universitetlar', 'Ученики, пользовавшиеся Naseeb Edu, поступили в'],

  // How it works
  'How the platform works.': ['Platforma qanday ishlaydi.', 'Как работает платформа.'],
  'Four steps from your data to a ready plan.': ['Ma’lumotlaringizdan tayyor rejagacha — to‘rt bosqich.', 'Четыре шага от ваших данных до готового плана.'],
  'Enter your data': ['Ma’lumotlaringizni kiriting', 'Введите данные'],
  'Grades, SAT/IELTS scores, psychometric test answers and essay drafts go into one profile.': ['Baholar, SAT/IELTS ballari, psixometrik test javoblari va insho qoralamalari yagona profilga jamlanadi.', 'Оценки, баллы SAT/IELTS, ответы психометрических тестов и черновики эссе собираются в одном профиле.'],
  'Get your profile': ['Profilingizni oling', 'Получите профиль'],
  'Big Five, RIASEC and ICAR-16 models calculate your personality type, interests and cognitive scores, then rank the majors that fit you.': ['Big Five, RIASEC va ICAR-16 modellari shaxsiyat tipingiz, qiziqishlaringiz va kognitiv ko‘rsatkichlaringizni hisoblaydi hamda sizga mos yo‘nalishlarni reyting asosida saralaydi.', 'Модели Big Five, RIASEC и ICAR-16 рассчитывают ваш тип личности, интересы и когнитивные показатели и ранжируют подходящие направления.'],
  'See your matches': ['Mos variantlarni ko‘ring', 'Смотрите подбор'],
  'A scoring model compares your profile with university requirements, sorts the results into Reach, Target and Safety, and lists matching scholarships.': ['Scoring modeli profilingizni universitet talablari bilan solishtirib, natijalarni Reach, Target va Safety toifalariga ajratadi hamda mos stipendiyalarni saralaydi.', 'Скоринговая модель сравнивает ваш профиль с требованиями университетов, делит результаты на Reach, Target и Safety и подбирает подходящие стипендии.'],
  'Follow the roadmap': ['Traektoriya bo‘yicha harakat qiling', 'Следуйте дорожной карте'],
  'A step-by-step mission path with due dates; your completion percentage updates as tasks are approved.': ['Muddatlari belgilangan bosqichma-bosqich vazifalar yo‘li; vazifalar tasdiqlangani sari bajarilish foizi yangilanadi.', 'Пошаговый путь заданий со сроками; процент выполнения обновляется по мере одобрения задач.'],
  'Step 4': ['4-bosqich', 'Шаг 4'],
  'Admission roadmap': ['Qabul traektoriyasi', 'Дорожная карта поступления'],
  'Approved tasks add to your completion percentage and XP level.': ['Tasdiqlangan vazifalar bajarilish foizi va XP darajangizga qo‘shiladi.', 'Одобренные задачи увеличивают процент выполнения и ваш уровень XP.'],
  'Your roadmap, deadlines and progress in one dashboard, recalculated every time you finish a task.': ['Traektoriyangiz, muddatlar va progressingiz bitta panelda — har bir vazifa bajarilganda qayta hisoblanadi.', 'Дорожная карта, сроки и прогресс на одной панели — с пересчётом после каждой выполненной задачи.'],

  // Modules
  'One platform, ten modules.': ['Bitta platforma, o‘nta modul.', 'Одна платформа, десять модулей.'],
  'Every result is produced by software algorithms.': ['Har bir natija dasturiy algoritmlar tomonidan shakllantiriladi.', 'Каждый результат формируют программные алгоритмы.'],
  'Psychometric Profiling': ['Psixometrik profillash', 'Психометрический профиль'],
  'Personality type, interests and cognitive scores calculated with the Big Five, RIASEC and ICAR-16 models.': ['Shaxsiyat tipi, qiziqishlar va kognitiv ko‘rsatkichlar Big Five, RIASEC va ICAR-16 modellari asosida hisoblanadi.', 'Тип личности, интересы и когнитивные показатели рассчитываются по моделям Big Five, RIASEC и ICAR-16.'],
  'Psychometrics': ['Psixometriya', 'Психометрия'],
  'Major Match': ['Major Match', 'Major Match'],
  'Ranks study majors from your interests, values and school subjects; Naseeb AI explains why each one fits and what to explore next.': ['Ta’lim yo‘nalishlarini qiziqishlaringiz, qadriyatlaringiz va maktab fanlaringiz asosida saralaydi; Naseeb AI har biri nega mos kelishini va keyin nimani o‘rganish kerakligini tushuntiradi.', 'Ранжирует направления обучения по вашим интересам, ценностям и школьным предметам; Naseeb AI объясняет, почему каждое подходит и что изучить дальше.'],
  'Naseeb AI explanations': ['Naseeb AI izohlari', 'Пояснения Naseeb AI'],
  'University & Scholarship Match': ['Universitet va grant moslashtirish', 'Подбор университетов и грантов'],
  'Multi-factor scoring of SAT/IELTS scores, GPA, budget and country preferences, sorted into Reach, Target and Safety.': ['SAT/IELTS ballari, GPA, byudjet va mamlakat afzalliklarini ko‘p faktorli scoring orqali solishtirib, Reach, Target va Safety toifalariga ajratadi.', 'Многофакторный скоринг баллов SAT/IELTS, GPA, бюджета и предпочтений по странам с разделением на Reach, Target и Safety.'],
  'Scoring model': ['Scoring modeli', 'Скоринговая модель'],
  'Essay Lab with Naseeb AI': ['Naseeb AI bilan Essay Lab', 'Essay Lab с Naseeb AI'],
  'Naseeb AI reads personal statements and supplements and scores reflection, specific detail, voice, structure and fit to the prompt, quoting your own words for every note. It asks questions and never rewrites your essay.': ['Naseeb AI shaxsiy insho (personal statement) va supplement matnlarini o‘qib, mulohaza, aniq tafsilotlar, ovoz, tuzilma va savolga moslikni baholaydi; har bir izohda o‘z so‘zlaringizdan iqtibos keltiradi. U savollar beradi va inshongizni hech qachon qayta yozmaydi.', 'Naseeb AI читает personal statement и supplement-тексты и оценивает рефлексию, конкретные детали, авторский голос, структуру и соответствие вопросу, цитируя ваши слова в каждом замечании. Он задаёт вопросы и никогда не переписывает ваше эссе.'],
  'Revision history': ['Versiyalar tarixi', 'История версий'],
  'Personalized Admission Roadmap': ['Shaxsiy qabul traektoriyasi', 'Персональная дорожная карта поступления'],
  'Guides you through a step-by-step mission path and tracks your completion percentage as tasks are approved.': ['Sizni bosqichma-bosqich vazifalar yo‘li bo‘ylab olib boradi va vazifalar tasdiqlangani sari bajarilish foizini kuzatadi.', 'Ведёт вас по пошаговому пути заданий и отслеживает процент выполнения по мере одобрения задач.'],
  'Step by step': ['Bosqichma-bosqich', 'Пошагово'],
  'Naseeb AI assistant': ['Naseeb AI yordamchisi', 'Ассистент Naseeb AI'],
  'Answers questions about your tasks, roadmap and applications in Uzbek, Russian or English, using only what your role can see. It suggests steps but never changes your records.': ['Vazifalaringiz, traektoriyangiz va arizalaringiz haqidagi savollarga o‘zbek, rus yoki ingliz tilida javob beradi va faqat rolingiz ko‘ra oladigan ma’lumotlardan foydalanadi. U qadamlarni taklif qiladi, lekin yozuvlaringizni hech qachon o‘zgartirmaydi.', 'Отвечает на вопросы о ваших задачах, дорожной карте и заявках на узбекском, русском или английском, используя только то, что доступно вашей роли. Он предлагает шаги, но никогда не меняет ваши записи.'],
  'Read-only': ['Faqat o‘qish', 'Только чтение'],
  'School Dashboard': ['Maktab boshqaruv paneli', 'Панель для школ'],
  'A multi-tenant panel for schools: student progress, groups and statistics, with separate student, teacher and coordinator roles.': ['Ta’lim muassasalari uchun multi-tenant panel: o‘quvchilar progressi, guruhlar va statistika; o‘quvchi, o‘qituvchi va maktab koordinatori rollari alohida.', 'Multi-tenant панель для учебных заведений: прогресс учеников, группы и статистика с отдельными ролями ученика, учителя и координатора.'],
  'For schools': ['Maktablar uchun', 'Для школ'],
  'Progress & Gamification': ['Progress va geymifikatsiya', 'Прогресс и геймификация'],
  'Visual reports of where you got stuck, an XP and level system, and Screen Time analysis of time spent on the platform.': ['Qaysi bosqichda to‘xtab qolganingizni ko‘rsatuvchi vizual hisobotlar, XP va daraja tizimi hamda platformada sarflangan vaqtni tahlil qiluvchi Ekran vaqti moduli.', 'Наглядные отчёты о том, на каком этапе вы остановились, система XP и уровней и модуль «Экранное время» для анализа времени на платформе.'],
  'API Integration': ['API integratsiya', 'API-интеграция'],
  'Connects the profiling and matching algorithms to third-party platforms, school CRM systems and mobile apps.': ['Profillash va moslashtirish algoritmlarini uchinchi tomon platformalari, maktab CRM tizimlari va mobil ilovalarga ulaydi.', 'Подключает алгоритмы профилирования и подбора к сторонним платформам, школьным CRM-системам и мобильным приложениям.'],
  'For partners': ['Hamkorlar uchun', 'Для партнёров'],
  'Data Pipeline': ['Ma’lumotlar konveyeri', 'Конвейер данных'],
  'Loads university data from official sources and stores each record’s source link and verification date.': ['Universitet ma’lumotlarini rasmiy manbalardan yuklaydi va har bir yozuvning manba havolasi hamda tekshirilgan sanasini saqlaydi.', 'Загружает данные университетов из официальных источников и хранит для каждой записи ссылку на источник и дату проверки.'],
  'Official sources': ['Rasmiy manbalar', 'Официальные источники'],
  'Coordinators and teachers see every student’s progress, deadlines and submitted work in one panel.': ['Koordinator va o‘qituvchilar har bir o‘quvchining progressi, muddatlari va topshirilgan ishlarini bitta panelda ko‘radi.', 'Координаторы и учителя видят прогресс, сроки и сданные работы каждого ученика на одной панели.'],

  // About: data and AI accuracy
  'Results built on verified data.': ['Natijalar tasdiqlangan ma’lumotlarga asoslanadi.', 'Результаты опираются на проверенные данные.'],
  'Naseeb Edu is a cloud (SaaS) platform. Rule-based models rank universities and majors, and Naseeb AI, our language-model assistant, gives essay feedback and answers questions. Users get subscription access to its software modules.': ['Naseeb Edu — bulutli (SaaS) platforma. Universitet va yo‘nalishlar qoidalarga asoslangan modellar bilan saralanadi, til modeliga asoslangan yordamchimiz Naseeb AI esa insholarga fikr-mulohaza beradi va savollarga javob beradi. Foydalanuvchilar uning dasturiy modullaridan obuna asosida foydalanadi.', 'Naseeb Edu — облачная (SaaS) платформа. Университеты и направления ранжируются моделями на основе правил, а Naseeb AI, наш ассистент на основе языковой модели, даёт отзывы на эссе и отвечает на вопросы. Пользователи получают доступ к её программным модулям по подписке.'],
  'Official sources only': ['Faqat rasmiy manbalar', 'Только официальные источники'],
  'Admission statistics, test requirements, tuition and scholarship terms come from universities and international education organisations, not from AI.': ['Qabul statistikasi, test talablari, o‘quv narxi va stipendiya shartlari sun’iy intellektdan emas, universitetlar va xalqaro ta’lim tashkilotlaridan olinadi.', 'Статистика приёма, требования к тестам, стоимость обучения и условия стипендий берутся у университетов и международных образовательных организаций, а не у ИИ.'],
  'Every record is traceable': ['Har bir yozuvni tekshirish mumkin', 'Каждую запись можно проверить'],
  'University records are loaded from official sources and stored with their source link and the date they were checked.': ['Universitet yozuvlari rasmiy manbalardan yuklanadi va manba havolasi hamda tekshirilgan sanasi bilan saqlanadi.', 'Записи об университетах загружаются из официальных источников и хранятся со ссылкой на источник и датой проверки.'],
  'Naseeb AI stays in bounds': ['Naseeb AI chegaradan chiqmaydi', 'Naseeb AI не выходит за рамки'],
  'Naseeb AI uses only your own profile and tasks, quotes your essay for every note, and never invents deadlines, requirements or admission chances. Without AI access, rule-based feedback takes over.': ['Naseeb AI faqat o‘z profilingiz va vazifalaringizdan foydalanadi, har bir izohda inshongizdan iqtibos keltiradi va muddatlar, talablar yoki qabul ehtimolini hech qachon o‘ylab topmaydi. AI mavjud bo‘lmaganda qoidalarga asoslangan fikr-mulohaza ishga tushadi.', 'Naseeb AI использует только ваш профиль и задачи, цитирует ваше эссе в каждом замечании и никогда не придумывает сроки, требования или шансы на поступление. Без доступа к ИИ работает отзыв на основе правил.'],
  'Usage is capped': ['Foydalanish cheklangan', 'Использование ограничено'],
  'Every Naseeb AI request counts against daily limits per user and per school, and is logged so schools can see AI usage.': ['Har bir Naseeb AI so‘rovi foydalanuvchi va maktab uchun kunlik limitlarga hisoblanadi va maktablar AI’dan foydalanishni ko‘ra olishi uchun qayd etiladi.', 'Каждый запрос к Naseeb AI учитывается в дневных лимитах на пользователя и на школу и записывается в журнал, чтобы школы видели использование ИИ.'],

  // Plans
  'One subscription, every module.': ['Bitta obuna — barcha modullar.', 'Одна подписка — все модули.'],
  'Access to the platform is provided as a software license (subscription).': ['Platformadan foydalanish huquqi dasturiy litsenziya (obuna) sifatida taqdim etiladi.', 'Доступ к платформе предоставляется как программная лицензия (подписка).'],
  'Individual subscription': ['Shaxsiy obuna', 'Личная подписка'],
  'Monthly or yearly access for individual users to the Naseeb AI assistant, Essay Lab with Naseeb AI feedback, admission roadmap, and university and scholarship matching.': ['Jismoniy shaxslar uchun Naseeb AI yordamchisi, Naseeb AI fikr-mulohazali Essay Lab, qabul traektoriyasi hamda universitet va grant moslashtirishdan oylik yoki yillik foydalanish.', 'Ежемесячный или годовой доступ для частных пользователей к ассистенту Naseeb AI, Essay Lab с отзывами Naseeb AI, дорожной карте поступления и подбору университетов и стипендий.'],
  'Monthly · yearly': ['Oylik · yillik', 'Месяц · год'],
  'School subscription': ['Maktab obunasi', 'Подписка для школ'],
  'A corporate plan for educational institutions with the multi-tenant dashboard and API integration.': ['Ta’lim muassasalari uchun multi-tenant boshqaruv paneli va API integratsiyasi bilan korporativ tarif.', 'Корпоративный тариф для учебных заведений с multi-tenant панелью и API-интеграцией.'],
  'Corporate': ['Korporativ', 'Корпоративный'],
  'API license': ['API litsenziya', 'API-лицензия'],
  'Third-party platforms use the profiling and matching algorithms through the API.': ['Uchinchi tomon platformalari profillash va moslashtirish algoritmlaridan API orqali foydalanadi.', 'Сторонние платформы используют алгоритмы профилирования и подбора через API.'],
  'Included in every plan': ['Har bir tarifda', 'Входит в каждый тариф'],
  'Tasks, guides and digital materials matched to your stage, selected and shown automatically by the platform.': ['Bosqichingizga mos vazifalar, qo‘llanmalar va raqamli materiallar platforma tomonidan avtomatik saralanadi va ko‘rsatiladi.', 'Задачи, руководства и цифровые материалы под ваш этап платформа подбирает и показывает автоматически.'],
  'Included': ['Obunaga kiradi', 'Включено'],

  // Stories
  'Hear from students who used Naseeb Edu.': ['Naseeb Edu’dan foydalangan o‘quvchilar fikri.', 'Отзывы учеников, пользовавшихся Naseeb Edu.'],

  // FAQ
  'What users ask before they subscribe.': ['Obunadan oldin beriladigan savollar.', 'Что спрашивают перед подпиской.'],
  'How the platform works, where its data comes from and how to get access.': ['Platforma qanday ishlaydi, ma’lumotlar qayerdan olinadi va undan qanday foydalanish mumkin.', 'Как работает платформа, откуда берутся данные и как получить доступ.'],
  'Naseeb Edu is a cloud (SaaS) platform for university admission. It brings your academic results, test scores, assessment answers and essays into one profile. Rule-based models rank universities, scholarships and majors and build your admission roadmap, and Naseeb AI, our language-model assistant, gives essay feedback and answers questions.': ['Naseeb Edu — universitetga qabul uchun bulutli (SaaS) platforma. U akademik natijalaringiz, test ballaringiz, so‘rovnoma javoblaringiz va insholaringizni yagona profilga jamlaydi. Qoidalarga asoslangan modellar universitetlar, stipendiyalar va yo‘nalishlarni saralaydi hamda qabul traektoriyangizni tuzadi, til modeliga asoslangan yordamchimiz Naseeb AI esa insholarga fikr-mulohaza beradi va savollarga javob beradi.', 'Naseeb Edu — облачная (SaaS) платформа для поступления в университет. Она собирает ваши академические результаты, баллы тестов, ответы на опросники и эссе в одном профиле. Модели на основе правил ранжируют университеты, стипендии и направления и строят вашу дорожную карту поступления, а Naseeb AI, наш ассистент на основе языковой модели, даёт отзывы на эссе и отвечает на вопросы.'],
  'Is Naseeb Edu a consulting service?': ['Naseeb Edu konsalting xizmatimi?', 'Naseeb Edu — это консалтинговая услуга?'],
  'No. Naseeb Edu is software. You get the right to use the platform’s software modules by subscription, and every result is produced by the platform’s algorithms.': ['Yo‘q. Naseeb Edu — dasturiy ta’minot. Siz platformaning dasturiy modullaridan obuna asosida foydalanish huquqini olasiz, har bir natija esa platforma algoritmlari tomonidan shakllantiriladi.', 'Нет. Naseeb Edu — это программное обеспечение. Вы получаете право пользоваться программными модулями платформы по подписке, а каждый результат формируют алгоритмы платформы.'],
  'How does psychometric profiling work?': ['Psixometrik profillash qanday ishlaydi?', 'Как работает психометрический профиль?'],
  'The platform calculates your personality type, interests and cognitive scores with standardised models — Big Five, RIASEC and ICAR-16. Major Match then ranks study majors from your interests, values and subjects, and Naseeb AI explains the fit.': ['Platforma shaxsiyat tipingiz, qiziqishlaringiz va kognitiv ko‘rsatkichlaringizni standartlashtirilgan modellar — Big Five, RIASEC va ICAR-16 asosida hisoblaydi. So‘ng Major Match ta’lim yo‘nalishlarini qiziqishlaringiz, qadriyatlaringiz va fanlaringiz asosida saralaydi, Naseeb AI esa ular nega mos kelishini tushuntiradi.', 'Платформа рассчитывает ваш тип личности, интересы и когнитивные показатели по стандартизированным моделям — Big Five, RIASEC и ICAR-16. Затем Major Match ранжирует направления обучения по вашим интересам, ценностям и предметам, а Naseeb AI объясняет, почему они подходят.'],
  'The profile is a starting point for exploring options, not a diagnosis.': ['Profil — variantlarni o‘rganish uchun boshlang‘ich nuqta, tashxis emas.', 'Профиль — отправная точка для изучения вариантов, а не диагноз.'],
  'How does university and scholarship matching work?': ['Universitet va grant moslashtirish qanday ishlaydi?', 'Как работает подбор университетов и грантов?'],
  'The matching algorithm compares your SAT/IELTS scores, GPA, budget and country preferences with each university’s requirements using a multi-factor scoring model. It sorts the results into Reach, Target and Safety and lists matching scholarships and financial aid programmes.': ['Moslashtirish algoritmi SAT/IELTS ballaringiz, GPA, byudjetingiz va mamlakat afzalliklaringizni har bir universitet talablari bilan ko‘p faktorli scoring modeli orqali solishtiradi. Natijalarni Reach, Target va Safety toifalariga ajratadi hamda mos stipendiya va moliyaviy yordam dasturlarini saralaydi.', 'Алгоритм подбора сравнивает ваши баллы SAT/IELTS, GPA, бюджет и предпочтения по странам с требованиями каждого университета с помощью многофакторной скоринговой модели. Он делит результаты на Reach, Target и Safety и подбирает подходящие стипендии и программы финансовой помощи.'],
  'Reach, Target and Safety show how your profile compares with a university’s requirements. They are not a guarantee of admission.': ['Reach, Target va Safety profilingiz universitet talablariga qanchalik mos kelishini ko‘rsatadi. Ular qabulni kafolatlamaydi.', 'Reach, Target и Safety показывают, как ваш профиль соотносится с требованиями университета. Они не гарантируют поступление.'],
  'What does Essay Lab check?': ['Essay Lab nimani tekshiradi?', 'Что проверяет Essay Lab?'],
  'Naseeb AI reads personal statements, supplements and scholarship essays and gives scores for reflection, specific detail, voice, structure and fit to the prompt, with every note quoting your text. It does not score grammar or rewrite your essay. Counselors also get Naseeb AI ideas for recommendation letters, drawn from the student’s profile. Essay Lab keeps your revision history.': ['Naseeb AI shaxsiy insho, supplement va stipendiya insholarini o‘qib, mulohaza, aniq tafsilotlar, ovoz, tuzilma va savolga moslik bo‘yicha baho beradi; har bir izoh matningizdan iqtibos keltiradi. U grammatikani baholamaydi va inshongizni qayta yozmaydi. Maslahatchilar ham Naseeb AI’dan o‘quvchi profiliga asoslangan tavsiyanoma g‘oyalarini oladi. Essay Lab versiyalar tarixini saqlaydi.', 'Naseeb AI читает personal statement, supplement-тексты и эссе для стипендий и оценивает рефлексию, конкретные детали, авторский голос, структуру и соответствие вопросу, причём каждое замечание цитирует ваш текст. Он не оценивает грамматику и не переписывает эссе. Консультанты также получают от Naseeb AI идеи для рекомендательных писем на основе профиля ученика. Essay Lab хранит историю версий.'],
  'Where does the university data come from?': ['Universitet ma’lumotlari qayerdan olinadi?', 'Откуда берутся данные об университетах?'],
  'From admission statistics, test requirements, tuition fees and scholarship terms published by universities and international education organisations. They are loaded from official sources, and each record shows its source link and verification date.': ['Universitetlar va xalqaro ta’lim tashkilotlari e’lon qilgan qabul statistikasi, test talablari, o‘quv narxi va stipendiya shartlaridan. Ular rasmiy manbalardan yuklanadi, har bir yozuvda esa manba havolasi va tekshirilgan sanasi ko‘rsatiladi.', 'Из статистики приёма, требований к тестам, стоимости обучения и условий стипендий, которые публикуют университеты и международные образовательные организации. Они загружаются из официальных источников, а в каждой записи указаны ссылка на источник и дата проверки.'],
  'How does Naseeb Edu reduce AI mistakes?': ['Naseeb Edu AI xatolarini qanday kamaytiradi?', 'Как Naseeb Edu снижает ошибки ИИ?'],
  'Naseeb AI works only from your own profile and essay. Every essay note must quote your text, or it is dropped. It never invents deadlines, requirements or admission chances, and university matching uses fixed rules, not AI. Daily limits apply, and if AI is unavailable you get rule-based feedback instead.': ['Naseeb AI faqat o‘z profilingiz va inshongiz bilan ishlaydi. Insho bo‘yicha har bir izoh matningizdan iqtibos keltirishi shart, aks holda u olib tashlanadi. U muddatlar, talablar yoki qabul ehtimolini hech qachon o‘ylab topmaydi, universitetlarni moslashtirish esa AI emas, qat’iy qoidalar asosida ishlaydi. Kunlik limitlar amal qiladi, AI mavjud bo‘lmasa, uning o‘rniga qoidalarga asoslangan fikr-mulohaza beriladi.', 'Naseeb AI работает только с вашим профилем и эссе. Каждое замечание к эссе должно цитировать ваш текст, иначе оно отбрасывается. Он никогда не придумывает сроки, требования или шансы на поступление, а подбор университетов работает по фиксированным правилам, а не с помощью ИИ. Действуют дневные лимиты, а если ИИ недоступен, вы получаете отзыв на основе правил.'],
  'Who can subscribe?': ['Kimlar obuna bo‘lishi mumkin?', 'Кто может оформить подписку?'],
  'Individual users can take a monthly or yearly subscription. Educational institutions use a corporate plan with the school dashboard and API integration, and third-party platforms can license the algorithms through the API. Contact our team to choose a plan.': ['Jismoniy shaxslar oylik yoki yillik obunadan foydalanishi mumkin. Ta’lim muassasalari maktab boshqaruv paneli va API integratsiyasi bilan korporativ tarifdan, uchinchi tomon platformalari esa algoritmlardan API litsenziyasi orqali foydalanadi. Tarifni tanlash uchun jamoamizga murojaat qiling.', 'Частные пользователи могут оформить ежемесячную или годовую подписку. Учебные заведения пользуются корпоративным тарифом с панелью для школ и API-интеграцией, а сторонние платформы — лицензией на алгоритмы через API. Чтобы выбрать тариф, свяжитесь с нашей командой.'],
  'Can schools track student progress?': ['Maktablar o‘quvchilar progressini kuzata oladimi?', 'Могут ли школы отслеживать прогресс учеников?'],
  'Yes. The school dashboard shows each student’s progress as a percentage based on completed tasks and application milestones, with separate access for students, teachers and school coordinators.': ['Ha. Maktab boshqaruv paneli har bir o‘quvchining progressini bajarilgan vazifalar va ariza bosqichlari asosida foizda ko‘rsatadi; o‘quvchi, o‘qituvchi va maktab koordinatori uchun kirish huquqlari alohida.', 'Да. Панель для школ показывает прогресс каждого ученика в процентах по выполненным задачам и этапам заявки, с отдельным доступом для учеников, учителей и школьных координаторов.'],
  'How do I get technical help?': ['Texnik yordamni qanday olaman?', 'Как получить техническую помощь?'],
  'Through the in-app support system: the FAQ, the support chatbot and support tickets. Technical issues are fixed as part of the platform’s technical support.': ['Ilova ichidagi yordam tizimi orqali: FAQ, support chatbot va murojaatlar (ticket) tizimi. Texnik nosozliklar platformani texnik qo‘llab-quvvatlash doirasida bartaraf etiladi.', 'Через встроенную систему поддержки: FAQ, чат-бот поддержки и систему обращений (тикетов). Технические неполадки устраняются в рамках технической поддержки платформы.'],

  // Closing and footer
  'Start with your own admission roadmap.': ['O‘z qabul traektoriyangizdan boshlang.', 'Начните со своей дорожной карты поступления.'],
  'Choose an individual or school subscription and get access to every module of the platform.': ['Shaxsiy yoki maktab obunasini tanlang va platformaning barcha modullaridan foydalaning.', 'Выберите личную или школьную подписку и получите доступ ко всем модулям платформы.'],
  'TIN': ['STIR', 'ИНН'],
}

export function landingMessages(language) {
  const index = language === 'uz' ? 0 : 1
  return Object.fromEntries(Object.entries(LANDING_TRANSLATIONS).map(([key, values]) => [key, values[index]]))
}
