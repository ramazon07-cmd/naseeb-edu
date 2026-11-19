# Student design parity

Mockup: `naseeb-student-dashboard 3 updated (1).html`. App: student portal (blue design, `frontend/src`).
Status values: **done** (already matched), **built now** (closed in this branch), **skipped** (with the reason).
Paths are under `frontend/src/` unless written in full. Meetings (`BookingsPage.jsx`, `meetings-blue.css`, PR #107) and Essay Lab (`essayLab/*`) are out of scope for this branch.

Rules kept in all sections: no backend or bot change, no new requests or polling, no renamed storage keys, staff screens unchanged.

## First-visit site tour

| mockup element | app status | file |
| --- | --- | --- |
| Site tour overlay `.ng-ov`, spotlight `.ng-spot`, tip `.ng-tip` | built now | frontend/src/design/blue/SiteTour.jsx, tour.css |
| Welcome card (`.ng-center`, `.ng-hero` logo, "Start the tour" / "Maybe later") | built now (texts written for uz/ru/en; the mockup has no welcome text in its data) | SiteTour.jsx, translations/parityTour.js |
| Spotlight steps: dashboard KPI row, Naseeb Mind, Programs, Applications (sidebar), Reading mode button, profile menu | built now, over the real UI; a step whose target is missing is dropped | SiteTour.jsx, StudentShell.jsx (`data-tour` on nav items) |
| Finish card (`.ng-hero.ok`, "Got it") | built now | SiteTour.jsx |
| Progress dots, "N of M" counter, Back / Next / Skip | built now | SiteTour.jsx |
| Phone docking (`.ng-dock`, `.ng-dtop`) and drawer opened for sidebar steps | built now (checked at 375px) | SiteTour.jsx, tour.css |
| Keyboard: Esc skips, arrows move, Tab trapped inside the card, focus on the primary button, focus returned on close | built now | SiteTour.jsx |
| Reduced motion | built now | tour.css |
| uz / ru / en | built now | translations/parityTour.js |
| First-visit auto start, once per account, after onboarding and the forced password change (the shell only renders after both) | built now; new key `naseeb-site-tour-v1:<userId>`, deliberately outside USER_STORAGE so it survives sign-out; zero requests | design/blue/tourSeen.js, StudentShell.jsx |
| Replay entry (`#utour` in the profile menu) | built now as "Take the tour" in the account menu | StudentShell.jsx |
| Per-page first-visit tips and "?" help sheets (`GS.apps`, `GS.road`, `GS.msg`, ...), "Turn off tips" toggle, `#rmHelp` | skipped: not part of the requested site tour; ten page-specific step lists over each page's internals, none built | - |

## Shell polish

| mockup element | app status | file |
| --- | --- | --- |
| `.navintro` sidebar entrance animation | built now (first 1.6s after the shell mounts; off under reduced motion) | design/blue/polish.css, StudentShell.jsx |
| Pointer "flashlight" on dashboard cards and sidebar (`.dash .w::after`, `.c-side::after`) | built now for the light look only (the mockup hides it in the dark looks); off under reduced motion and for touch | polish.css, StudentShell.jsx |
| Urgent pop-up (90 s after arrival, once a day, overdue items, Ignore / Show all) | built now from the student's real open tasks that are overdue; shown only if one exists; once a day per account in new key `naseeb-urgent-day-v1:<userId>`; "Go to Tasks" is the action | design/blue/UrgentPopup.jsx, urgent.css |
| Drag-to-approve slider (`.sl`) | skipped: no student-side approve action exists (approvals belong to the counselor), so there is nothing real to wire it to | - |
| Login entrance (phoenix over mountains) | the sign-in page already uses the mountain scene; card entrance and sky drift added now (see Sign-in section); a separate flying phoenix scene skipped | pages/Login.jsx, login.css |
| `.rm-guide` / `.rm-first` | done (Roadmap and Tasks, see Student Center section) | pages/RoadmapPage.jsx |
| Account menu: language segmented, dark mode, eye comfort (reading), support, logout | done (existing language menu, theme menu with Light / Tinted / Night / Reading, Support, Logout); "Guide tips" toggle skipped with the per-page tips | design/blue/StudentShell.jsx, controls.jsx |
| Mobile drawer and bottom dock | done (existing, 820px breakpoint); drawer is opened by the tour for sidebar steps | StudentShell.jsx |
| Top bar: reading mode, search, language, theme | done (existing); Export PDF button is an app addition kept because it works today | StudentShell.jsx |
| Header inline search (`#gq`) | skipped: the app opens the Ctrl+K palette from an icon button instead | - |

## Dashboard, Notifications, Screen Time, Support, Account

| mockup element | app status | file |
| --- | --- | --- |
|---|---|---|
| Dashboard greeting + date/open-task subtitle | done | CompactDashboard.jsx |
| Customize button (top row) + dialog (move main/side, hide, lock, reset, save) | done (app is a superset: drag, keyboard, lock) | CompactDashboard.jsx, DashboardCustomizer.jsx |
| KPI row: open tasks, universities, roadmap % | done (roadmap tile hidden while roadmap is locked, as before) | CompactDashboard.jsx |
| Study goal bar: icon, goal, countries, Program usage, Edit goal | done | CompactDashboard.jsx |
| Study goal: level + stars chip | done (shown only when roadmap is open) | CompactDashboard.jsx |
| Study goal: "Next step" row (next roadmap mission + %) | skipped: roadmap page locked for students, no mission data on dashboard | - |
| Next priorities card | done | CompactDashboard.jsx |
| Deadlines card (overdue banner, date tiles, days chips, radar link) | done (radar page does not exist in app; links go to Tasks) | CompactDashboard.jsx |
| Meetings card (confirmed, pending requests, empty state) | done | CompactDashboard.jsx |
| Applications card (count, uni stack, 4 tiles, CTA) | done | CompactDashboard.jsx |
| Programs hero card (open count, featured, rows, CTA) | done | CompactDashboard.jsx |
| Screen Time card (7/30 tabs, total, avg line, bars, pick day) | done | DashboardScreenTime.jsx |
| Discovery tools card | done | CompactDashboard.jsx |
| Team card (message buttons) | done | CompactDashboard.jsx |
| Dashboard loading / error / retry states | done | CompactDashboard.jsx |
| Notifications: header, mark-all-read / all-caught-up chip | done | NotificationsPage.jsx |
| Notifications: 4 KPI tiles (alerts, meetings, essays, deadlines) | done | NotificationsPage.jsx |
| Notifications: list with date tile, kind icon, time, unread dot, chevron | done | NotificationsPage.jsx |
| Notifications: count badge on card + "N shown" footer | built now | NotificationsPage.jsx, notifications-blue.css |
| Screen Time: header + subtitle | built now | ScreenTimePage.jsx |
| Screen Time: Today / Daily average / Total KPI tiles | built now | ScreenTimePage.jsx |
| Screen Time: active time per day chart, 7/14/30 tabs, tap bar for day, avg line | built now | ScreenTimePage.jsx, screentime-blue.css |
| Screen Time: time per page card + empty state | built now (real pages data) | ScreenTimePage.jsx |
| Screen Time: privacy card | built now | ScreenTimePage.jsx |
| Support: header + New ticket button | built now | SupportPage.jsx |
| Support: tickets list with unread chip, status chips, empty state | built now | SupportPage.jsx, support-blue.css |
| Support: new ticket form (subject, message) | built now (+ category select the API requires) | SupportPage.jsx, forms-blue.css |
| Support: file attach | skipped: ticket API has no attachment field | - |
| Support: thread view (request + support replies, waiting note) | built now | SupportPage.jsx |
| Support: reply inside thread ("Add to this ticket") | skipped: no student reply endpoint | - |
| Support: how support works card | built now | SupportPage.jsx |
| Account: profile card (avatar, name, email, language) | built now | AccountSettingsPage.jsx, account-blue.css |
| Account: change photo | skipped: students edit photo in Student Center; account avatar API is not used for students | - |
| Account: security card + live password rules | built now (rules match server: 8 chars, upper+lower+digit) | AccountSettingsPage.jsx |
| Account: who sees my data, counselor row | skipped: no counselor-visibility data in myParents API; text shown instead | - |
| Account: parent sections On/Off | built now read-only | AccountSettingsPage.jsx |
| Account: parent section switches (student toggles) | skipped: backend lets only the counselor change sharing | - |

## Naseeb Mind

| mockup element | app status | file |
| --- | --- | --- |
|---|---|---|
| Header: eyebrow + "What we know about you so far" | built now | ProfileAssessmentPage.jsx |
| Segmented progress bar (done/next pulse, lock, n / 7) | built now | ProfileAssessmentPage.jsx, mind-blue.css |
| 2-column sheet of 7 test sections in mockup order | built now (replaces flip hub cards) | ProfileAssessmentPage.jsx |
| Done section: Personality bars | built now | same |
| Done section: Interests hexagon | built now (existing ProfilePolygon) | same |
| Done section: Subjects top-3 chips + note | built now | same |
| Done sections for the 4 other tests (mockup always shows locked) | built now (bars/score from existing result) | same |
| Locked section: ? watermark, title, teaser, "Fills in after", Take test | built now (opens in-app runner) | same |
| Next-step highlight (ring, primary Start/Continue) | built now | same |
| "Review answers" link | built now (opens runner) | same |
| Majors panel (deck of 3 "?" cards, tag "n tests left", hover fan) | built now | same |
| Majors ready / reveal Continue, 3 picks radiogroup, save to student target_major | kept + restyled | same |
| Current study direction chip | built now | same |
| Side: Next step card | built now | same |
| Side: progress ring + save note | built now | same |
| Side: "A guide, not a diagnosis" | built now | same |
| Side: "Your results on one card" link | built now (scrolls to existing profile card) | same |
| Side: external Naseeb Mind link | skipped: in-app tests, no external URL | - |
| Test-taking runner, save/retry/sync, pending state, load error banner | kept unchanged | same |
| Unsaved/failed save chip + Retry | kept (moved to section header) | same |
| Card flip summaries, "See the result" highlight | removed (mockup has no flip); results stack and ID card kept below | same |
| Translations uz/ru | done | parityMind.js |

## Student Center, Tasks, Roadmap, Store

| mockup element | app status | file |
| --- | --- | --- |
|---|---|---|
| Center header + Download CV | done | StudentCenterPage.jsx |
| 4 KPI tiles (level, stars, tasks, applications) | done (tasks/applications tiles are now links with chevron, as mockup go:roadmap / go:apps) | StudentCenterPage.jsx |
| ID card (logo, photo, name, grade, school, class-of, countries) | done | StudentCenterPage.jsx |
| ID photo camera button | done | StudentCenterPage.jsx |
| Photo editor modal (drag, zoom, wheel, arrow keys, preview, choose another, remove, use) | built now (saves cropped 3:4 jpeg through existing upload/remove endpoints) | StudentCenterPage.jsx, center-blue.css |
| Contact and goal chips | done | StudentCenterPage.jsx |
| Profile-ready dial + counselor + "to raise it" hint | built now (profile_readiness.percent) | StudentCenterPage.jsx, center-blue.css |
| Application-readiness dial + "N of M items finished" | built now (was mislabelled single ring on the card) | StudentCenterPage.jsx, center-blue.css |
| Tabs overview/academics/portfolio/activities/documents | done | StudentCenterPage.jsx |
| Section cards with edit pencil (personal, goal, academics, tests, honors, activities) | done (inline edit with real save; text Edit button kept) | ProfileSections.jsx |
| Test cards with part meters (IELTS /9, SAT /800) | built now (student cards only, opt-in prop) | testScores.jsx, center-blue.css |
| Overview lists: assigned tasks, college list, essays | skipped: rendered by StudentOverview in StudentsPage.jsx (shared with staff, not my file) | - |
| Portfolio / activities groups, add menus, recommendations | done | StudentCenterPage.jsx |
| Documents tab + certificates | done | DocumentsPage.jsx |
| Roadmap page (flight profile, level path, departure/arrival, guide, shortcuts, checkpoint) | done | RoadmapPage.jsx, roadmap-blue.css |
| Roadmap rm-first / rm-guide hints | done (nb-task-first, nb-rm-guide) | RoadmapPage.jsx |
| Tasks page in locked-roadmap slot (count, first-late hint, rows, full list) | done | RoadmapPage.jsx |
| Roadmap "?" help button (NGuide) | skipped: belongs to the shell/tour worker | - |
| Store lock page | done (mockup now shows only a toast for Store; app keeps a calm page with Dashboard link) | StorePage.jsx |

## Messages

| mockup element | app status | file |
| --- | --- | --- |
| Chat list card with search pill | done (existing, themed) | messages-blue.css |
| Private / Groups tabs with blue underline | done (app has All/Private/Groups + unread counts) | MessagesPage.jsx |
| Round gradient avatars (50px) | built now | messages-blue.css |
| Saved Messages row first | done | MessagesPage.jsx |
| Selected row solid blue (navy-blue mix in dark looks) | built now | messages-blue.css |
| "You:" prefix and sent tick on own last line | built now (student only; single tick, read state not in list data) | MessagesPage.jsx |
| "Channels" separator + Naseeb Edu row with verified badge, below chats | built now | MessagesPage.jsx, parityMsg.js |
| Naseeb Edu row opens external t.me link | skipped: app opens the in-app channel view (richer, kept) | - |
| No results / no groups empty text | done (existing) | MessagesPage.jsx |
| Loading skeleton / error + Retry | done (existing) | MessagesPage.jsx |
| White thread header, round icon buttons | built now | messages-blue.css |
| Header search-in-chat and more buttons | skipped: mockup buttons are placeholders ("coming soon"); app has Info panel and Close | - |
| Mobile back button and list/thread switching | done (existing) | styles.css |
| Doodle wall with gradient (light) and flat dark wall | built now | messages-blue.css |
| Sticky dark-pill day separators | built now | messages-blue.css |
| Bubbles: white in, blue-mixed out, tails, grouped corners, enter animation | built now | MessagesPage.jsx, messages-blue.css |
| Time + tick inside bubble, floated right | built now | messages-blue.css |
| Jumbo emoji (1-3 emoji, no bubble) | built now | MessagesPage.jsx, messages-blue.css |
| Empty thread card | built now (restyled) | messages-blue.css |
| "Select a chat to start messaging" pill | built now | MessagesPage.jsx, messages-blue.css, parityMsg.js |
| Composer: pill field with tail, emoji, attach, round send turning blue on text | built now | MessagesPage.jsx, messages-blue.css |
| Enter sends, Shift+Enter newline | done (existing) | MessagesPage.jsx |
| Autoscroll to newest message | done (existing) | MessagesPage.jsx |
| Reduced motion, dark/tinted/night, 375px | done (media queries, tokens) | messages-blue.css |
| Shared items / contact details panel, attachments, replies, reports | app-only, kept | ChatDetails.jsx, MessageAttachment.jsx |

## Programs, Applications (with radar), College Search

| mockup element | app status | file |
| --- | --- | --- |
| Programs: header + subtitle | done | pages/ProgramsPage.jsx |
| Programs: featured "next deadline" card (date tile, provider/category/scope, days chip) | done | pages/ProgramsPage.jsx |
| Programs: featured "Details" button (opens program page) | built now | pages/ProgramsPage.jsx |
| Programs: featured "official site" + "save to My List" | done | pages/ProgramsPage.jsx |
| Programs: "Next up" list of 4 deadlines | done | pages/ProgramsPage.jsx |
| Programs: "Deadline radar" link under Next up | skipped: radar is a separate page/route (App.jsx, other worker); radar is available in Applications | - |
| Programs: 4 KPI tiles | done | pages/ProgramsPage.jsx |
| Programs: KPI "Open for applications" filters list to open programs | built now | pages/ProgramsPage.jsx |
| Programs: KPI "Open programs in catalog" resets all filters | built now | pages/ProgramsPage.jsx |
| Programs: KPI My List / Scholarship toggles | done | pages/ProgramsPage.jsx |
| Programs: search box with clear | done | pages/ProgramsPage.jsx |
| Programs: filter pills (type, grade, delivery, category, scholarship, hide closed, clear, counts) | done | pages/ProgramsPage.jsx |
| Programs: "Free" pill with count | built now (local state, not in URL) | pages/ProgramsPage.jsx |
| Programs: multi-select grades | skipped: URL filter model (lib/programFilters.js) holds one grade; not my file and shared with tests | - |
| Programs: month-grouped timeline, rows, save, open site, requirements | done | pages/ProgramsPage.jsx |
| Programs: My List view (days-left ring) | done | pages/ProgramsPage.jsx |
| Programs: empty / saved-error / loading states | done | pages/ProgramsPage.jsx |
| Programs: mobile filter sheet | done | pages/ProgramsPage.jsx |
| Program page: back, hero, unconfirmed-date warning, about, who/format/cost/aid/requirements facts | built now (from existing catalog fields) | pages/ProgramsPage.jsx, programs-blue.css |
| Program page: deadline box with status chip (confirmed / expected / not announced) and days left | built now | pages/ProgramsPage.jsx |
| Program page: LinkedIn participants / winners search links | built now (client-side links) | pages/ProgramsPage.jsx |
| Program page: "Ready to apply" card (save + official site) | built now | pages/ProgramsPage.jsx |
| Program page: recommendations box ("Similar open programs") | built now (same category first, from loaded catalog) | pages/ProgramsPage.jsx |
| Program page: about text, prize, team, dates, official winners list | skipped: fields do not exist in the API (mock has hand-written data) | - |
| Applications: next-deadline / list / essays / letters tiles | done | pages/ApplicationsPortalPage.jsx |
| Applications: essays tile link to Essay Lab | built now | pages/ApplicationsPortalPage.jsx |
| Applications: "Your pipeline" funnel card | done (mock removed it in its last patch; app has none) | - |
| Applications: tier filter chips with counts, sort, List/Board switch, add university | done | pages/ApplicationsPortalPage.jsx |
| Applications: list rows with 5-step stepper, board columns, drag, brief popover, menu, manage plan | done | pages/ApplicationsPortalPage.jsx, components/ApplicationPlan.jsx |
| Applications: empty state | done | pages/ApplicationsPortalPage.jsx |
| Radar: urgency cards (overdue / next 14 days / next 4 months) that filter the list | built now | pages/ApplicationsPortalPage.jsx, apps-blue.css |
| Radar: type tabs All / University / Mine | built now (University + Mine) | pages/ApplicationsPortalPage.jsx |
| Radar: Program and Task tabs | skipped: programs need the saved-list request and tasks are not loaded on this page (extra API calls forbidden) | - |
| Radar: groups Overdue / This week / Next 30 days / month, late wording | built now | pages/ApplicationsPortalPage.jsx |
| Radar: "add your own" deadline (name, date, type), edit, delete, kept in localStorage `nsb-mydl` | built now | pages/ApplicationsPortalPage.jsx |
| Radar: as a full page with its own route and nav item | skipped: needs App.jsx / routes (another worker); kept as the in-page dialog | - |
| College Search: header + subtitle | done | pages/CollegeSearchPage.jsx |
| College Search: "Matched to you" profile (SAT/GPA/IELTS/major/budget, edit profile) | done | pages/CollegeSearchPage.jsx |
| College Search: university deadlines strip | done | pages/CollegeSearchPage.jsx |
| College Search: list balance with 2/3/2 goals, "Add N more" headline, progress, hint | built now | pages/CollegeSearchPage.jsx, colleges-blue.css |
| College Search: tier buttons filter results (Dream/Target/Safety) | built now | pages/CollegeSearchPage.jsx |
| College Search: tabs Matches for you / All universities | done; Matches now opens the card view | pages/CollegeSearchPage.jsx |
| College Search: match cards (fit ring, band, QS rank, SAT range vs your score, cost vs budget, acceptance, deadline, compare, details, add) | built now for Admissions & costs view (why-this-result stays in a disclosure) | pages/CollegeSearchPage.jsx, colleges-blue.css |
| College Search: sort (fit / cost / deadline / acceptance), page size, search, filters, country, public, SAT in range | done | pages/CollegeSearchPage.jsx |
| College Search: "Within my budget" filter | skipped: needs a new server query parameter (price caps exist instead) | - |
| College Search: QS table | done (QS rankings view) | pages/CollegeSearchPage.jsx |
| College Search: default view is match cards | skipped: switching the default view would fire an extra search request on load | - |
| College Search: compare up to 3, tray, compare table | done (dialog instead of a page) | pages/CollegeSearchPage.jsx |
| College Search: My List drawer, tier picker, loading/error/empty states | done | pages/CollegeSearchPage.jsx |
| University page: navy hero, add/remove, official site | built now (hero restyled) | pages/UniversityPage.jsx, colleges-blue.css |
| University page: key-facts strip (rank, fit, acceptance, cost) | built now | pages/UniversityPage.jsx |
| University page: fit, admissions numbers, SAT range, cost vs aid, programs, aid, needs tabs | done | pages/UniversityPage.jsx |
| University page: "People from this university" LinkedIn links | built now | pages/UniversityPage.jsx |
| University page: similar universities | skipped: needs another catalog request | - |
| University page: campus photo slideshow, hand-written top-10 majors, IELTS/TOEFL/living cost | skipped: no data in the API (mock placeholder content) | - |
| University page: contents sidebar (TOC) | skipped: page already uses tabs, a second navigation would duplicate them | - |
| Translations (uz + ru) for all new strings | done | translations/parityCat.js |

## Sign-in, temporary password, search palette, PDF, bell

| mockup element | app status | file |
| --- | --- | --- |
| Sign-in card: glass card, logo tile, eyebrow, greeting, tagline | done (already shared) | pages/Login.jsx, design/blue/login.css |
| Greeting by hour (5-12 / 12-17 / else) | built now (app used 0-12 / 12-18) | pages/Login.jsx |
| Sky drift animation behind the card | built now | design/blue/login.css |
| Card entrance animation (rise + scale) | built now (reduced-motion off) | design/blue/login.css |
| Username / password fields with icons | done | pages/Login.jsx |
| Field icon turns blue on focus (is-focus) | built now | design/blue/login.css |
| Password show/hide (aria-pressed, label swap, focus back to field) | done; focus return built now | pages/Login.jsx |
| Remember me with drawn check box | built now (was native checkbox) | pages/Login.jsx, login.css |
| Remember me persists username | done (existing localStorage key) | lib/rememberedUsername |
| Forgot password? toggle + info box with mail icon | built now (info box styling and icon); toggle done | pages/Login.jsx, login.css |
| First sign-in with a temporary password: dashed row, lock + arrow, hover | built now (row style); opens an info hint (real flow = normal sign-in then forced change) | pages/Login.jsx, login.css |
| Sign in button, loading state | done; spinner built now | pages/Login.jsx, login.css |
| Error state (wrong credentials) | done (role=alert box) | pages/Login.jsx |
| Card lifts away on success (off state) | built now (fades while the workspace loads; reset on failure) | pages/Login.jsx, login.css |
| Top bar: brand, language segment, theme toggle | done (shared) | pages/Login.jsx |
| Footer copyright | done | pages/Login.jsx |
| Phoenix over mountains scene / liquid glass filter | skipped: the app uses the shared mountain backdrop and glass tokens; the mockup's final login is the same mountain scene without a separate flying phoenix | - |
| First-password card: new password, repeat, rules list | done (live checks incl. server-matching rules) | pages/Login.jsx |
| First-password card: class chips 5-11 (radiogroup) | built now (native radios, required, keyboard arrows) | pages/Login.jsx, login.css |
| First-password card: error line, Continue button | done | pages/Login.jsx |
| First-password card: Back to sign in | done as header Sign out | pages/Login.jsx |
| 6-step profile wizard after first password (draft in localStorage) | skipped: prototype data (me, goal, tests); needs profile API writes beyond change-password, and Student Center already holds the profile | - |
| Ctrl/Cmd+K opens palette | done | App.jsx |
| Palette box: search icon, input, Esc hint | built now | components/SearchPalette.jsx, design/blue/search.css |
| Palette empty query lists pages | done; now keyboard-walkable for students | App.jsx |
| Palette groups Pages / Records with headings | built now | SearchPalette.jsx |
| Row icon, title, subtitle small | built now (page icon per destination) | SearchPalette.jsx |
| Arrow up/down wrap, highlighted active row, Enter opens, Esc closes | built now (highlight and aria-activedescendant were missing); wrap and Enter existed | App.jsx, SearchPalette.jsx |
| Active row scrolls into view | built now | SearchPalette.jsx |
| Empty state "No results" | built now (shows Searching... while the server query runs) | SearchPalette.jsx |
| Palette on mobile (header field opens it) | gap outside my area: shell search button already opens it; 375px layout built | design/blue/search.css |
| Header inline search dropdown (#gq) | skipped: shell owner (StudentShell.jsx); the palette serves the same results | - |
| Records from server catalogue search | done (same single request as before) | App.jsx |
| PDF export | no mockup equivalent: the mockup has no export button (only proto CV/card downloads in Student Center); app behaviour left unchanged | lib/exportPdf.js |
| Notifications drawer (bell) | skipped: students never see the popup panel, the bell opens the Notifications page (existing behaviour, other owner) | components/NotificationPanel.jsx |

## Audit follow-up (round 3)

| mockup element | app status | file |
| --- | --- | --- |
| Programs: titles of closed programs open details | built now (lookup uses every loaded program, not only open ones) | pages/ProgramsPage.jsx |
| Programs radar: university row opens Applications, "Open Applications to include university deadlines" notice with link when applications are not loaded (no new request) | built now | pages/ProgramsPage.jsx, components/DeadlineRadar.jsx |
| Programs radar: program row opens its detail, task row opens Tasks | skipped: the radar only holds university deadlines and the student's own entries; programs and tasks are not in its data, adding them means the saved-programs request | components/DeadlineRadar.jsx |
| College Search radar notice | no change needed: that page already loads applications | pages/CollegeSearchPage.jsx |
| Mobile filter sheet "Show N programs" counts every filter (Free, My List, open, grades) | built now | pages/ProgramsPage.jsx |
| Dashboard: each card, the KPI row and the goal card render as components inside their own error boundary, calculations moved inside | built now | CompactDashboard.jsx, components/CardBoundary.jsx |
| Dashboard Applications card: four tiles are real buttons to Applications (disabled when locked) | built now | CompactDashboard.jsx, design/pages/dashboard-blue.css |
| Dashboard Applications card: initials stack | partial: shown only when applications are already loaded (the dashboard never requests them, so no request added); the big count stays visible | CompactDashboard.jsx |
| Dashboard deadline rows are buttons: task to Tasks, program to its detail page (`/programs?program=<id>`) | built now | CompactDashboard.jsx, lib/routes.js, pages/ProgramsPage.jsx |
| Dashboard deadline rows: application | skipped: the dashboard deadline list has no application items | CompactDashboard.jsx |
| Page tips for Meetings (`#meetings-book`, KPI row) and Essay Lab (`.el-library`, `.el-folders`) | built now; targets that are absent are dropped; no edits to those pages | design/blue/pageTips.js |

## Audit follow-up (round 4)

| mockup element | app status | file |
| --- | --- | --- |
| Program detail closes when `?program=` is removed (Programs nav item, back) | built now | pages/ProgramsPage.jsx |
| Programs "Next up" rows open the program detail | built now (buttons) | pages/ProgramsPage.jsx, design/pages/programs-blue.css |
| College Search deadline rows open Applications | built now (buttons) | pages/CollegeSearchPage.jsx, design/pages/colleges-blue.css |
| Student Center overview: task rows with date tiles and priority chips, university rows with initials, list-header counts (tasks, colleges, essays) | built now for the student viewer only (`studentView` is set from `user.role === 'student'`; counselor Student 360 keeps the classic rows); values already loaded | pages/StudentsPage.jsx, design/pages/center-blue.css |

## Out of scope (other branches)

| mockup element | app status | file |
| --- | --- | --- |
| Meetings page | skipped: out of scope, PR #107 | BookingsPage.jsx, design/pages/meetings-blue.css |
| Essay Lab page and editor | skipped: out of scope, own branch | essayLab/* |
| Essay Lab editor modal (Draft / Notes tabs, Coach / Review / Versions, "Ask another question", task select in the footer) | skipped: user decision, keep the current editor | essayLab/* |
