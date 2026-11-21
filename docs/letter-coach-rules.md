# Recommendation letter: Ideas and Check depth

Status: agreed with the product owner on 2026-11-20 (layout B, full-page workspace). Builds on the
Essay Coach v2 engine (`docs/essay-coach-rules.md`); everything not said here works the same way.

## Who sees what

- Only staff who can edit the letter today (the same queryset as `RecommendationLetterViewSet`)
  can request or read Ideas and checks. Students never can, even for a shared letter. The panel
  shows "Only you see this. The student never does."
- All AI here is behind `outbound_ai_allowed()` (`OUTBOUND_AI_ENABLED`) and the plan feature
  `ai_assistant`. Today `views/records.py` checks only the gateway key and the feature for letter
  suggestions; that is a bug and is fixed in this change.

## Layout (mockup: `mockups/letters/b-workspace.html`)

- A full page at `/students/<id>/letters/<letter_id>` (and `/students/<id>/letters/new`) replaces
  the modal. Back returns to the student's Recommendations tab.
- Header: back, eyebrow "Recommendation letter", "For <student>", save status, one "Show to
  student" switch. The recommender details (name, position, how you know the student, deadline,
  status) collapse into one line ("Firdavs Counselor · School counselor · due 12 Dec · Drafting ▾")
  that expands in place.
- The letter is a centered page. Editing stays a plain text area; highlights are drawn by a mirror
  layer under a transparent text area, so no rich-text editor is needed.
- Right panel (420 px): tabs Ideas · Check, then a one-row footer.
- Phone: the panel stacks under the page.

## Ideas tab

- **Profile facts (free, automatic, no AI):** facts from the student's profile that the letter does
  not mention yet (`rec_letter_ai.profile_facts` + `missing_facts`), each with one "+" icon that
  inserts a neutral fact line at the cursor. Mentioned facts disappear. Refreshed locally while
  typing (the request is cheap and has no AI), debounced.
- **AI ideas (on demand only):** one "Get AI ideas" button. Never refreshed automatically. Each
  idea cites its fact (source chip) and is a single sentence starter with "[Student]" filled with
  the first name on insert. Counter "AI · n of 20 today" (`REC_LETTER_AI_USER_DAILY_LIMIT`, default
  lowered to 20). Same validation as today: AI text is kept only when it cites a fact and every
  number in it appears in that fact.

## Check tab

Same two-step engine as the Essay Coach with the recommendation-letter rubric
(`essay_lab/rubrics/recommendation_letter.md`): evidence 40, insight 25, context 20, structure 10,
voice 5.

| Criterion | Key | Colour |
| --- | --- | --- |
| Specific evidence | `evidence` | blue |
| Insight | `insight` | violet |
| Basis for comparison | `context` | amber |
| Structure and length | `structure` | teal |
| Your voice | `voice` | coral |

- Bands, note caps (one per 25 words), dedup, Priority, re-check rules (all notes resolved and at
  least 3 words changed, or the inputs changed), same-text reuse at no cost, refunds on failure,
  90 s deadline and DB-connection release: exactly as the Essay Coach.
- Inputs for the input hash: letter body, recommender title, relationship, rubric text, model.
  The prompt sees the letter with the student's name replaced by "[Student]" and contact details
  redacted; never the student's profile.
- Notes show the question (and at most one new context line), not the quoted sentence. Clicking a
  note highlights and scrolls to its sentence; ✓ done / ✕ not useful corner icons; gone notes as in
  the Essay Coach.
- 5 checks per counselor per day (`REC_LETTER_CHECK_USER_DAILY_LIMIT`), separate from Essay Coach.

## API contract

- `POST /api/recommendations/<id>/depth-check/` `{base_updated_at}` → check (same JSON shape as an
  Essay Coach v2 check, criteria keys above). 409 `stale` if the letter changed since the client
  loaded it; 409 `notes_open` / `too_small_change` as the Essay Coach. 403 for students.
- `GET /api/recommendations/<id>/depth-check/latest/` → latest check or 204.
- `PATCH /api/recommendations/<id>/depth-check/<check_id>/notes/` `{note_id, state}`.
- `POST /api/recommendations/suggest/` keeps its body, adds `{"ai": true|false}`: false (default)
  returns profile facts only with no AI call; true returns facts plus AI ideas and counts against
  the AI limit. Response adds `ai_left`.
- Storage: new `RecommendationLetterCheck` (letter FK, author FK, result JSON, model,
  text_fingerprint, input_hash, overall, note_states, created_at), keep the last 10 per letter.
  Additive migration.

### Clarifications (backend as built)

- Access is `is_counselor_like` plus the viewset queryset: counselors and assistants of the student's
  school, and product admins. Students, teachers, organizations and parents get 403
  (`counselors_only`); a letter outside the queryset is 404.
- `suggest` always returns `ai_left` (remaining AI ideas today, or `null` with no cap or no cache),
  `ai_limit` (the daily per-user limit, `null` = no cap) and `ai_available` (master switch, gateway
  key, plan feature on and neither the platform nor the user's budget exhausted).
  Check responses carry `checks_left` and `daily_limit` next to `previous_overall`, `reused`,
  `input_hash` and `current_input_hash`. With `ai: false` the
  facts request uses its own cheap limit (`REC_LETTER_FACTS_PER_MINUTE`, default 120).
- The letter has no rule-based reader. With the master switch off or no gateway key,
  `POST depth-check` answers 503 `coach_unavailable` and costs nothing; a reused check (same text,
  same inputs) is still returned.
- Errors: 409 `stale` (also carries `updated_at`), 409 `notes_open` (`open`), 409
  `too_small_change` (`changed`, `min_words`), 400 `empty_letter`, 503 `coach_resting` (budget),
  503 `coach_unavailable`, 400 `unknown_note`, 429 for the throttles.
- Notes keep the quote as it is in the real letter (the model's "[Student]" is mapped back to the
  name); a note whose sentence cannot be found in the letter is dropped.
- Limits: `REC_LETTER_CHECK_USER_DAILY_LIMIT` (5), `REC_LETTER_CHECK_DAILY_BUDGET` (2000, 0 = off),
  `REC_LETTER_CHECK_SCHOOL_DAILY_BUDGET` (400), `REC_LETTER_CHECK_RECHECK_PER_MINUTE` (20),
  `REC_LETTER_CHECK_MIN_INTERVAL_SECONDS` (15), `REC_LETTER_CHECK_HOURLY_LIMIT` (60). The AI call
  deadlines reuse the `ESSAY_COACH_*` settings. Usage is logged as feature
  `recommendation_letter_check`.
- Calibration: the rubric README requires at least ten synthetic calibration letters (second-language
  writers and short letters included) with expected score ranges before production use. Do not enable
  the letter check for real counselors until they exist.
- `PATCH /recommendations/<id>/` accepts an optional `base_updated_at`; when it differs from the
  letter's `updated_at` the answer is 409 `stale` with the current serialized letter at `details.letter` and
  nothing is written. Without it, saves behave as before.
- Names are hidden from the model in every spelling the letter may use: first, last and middle names
  (split on spaces and hyphens, 3+ letters), curly or modifier apostrophes, Cyrillic, and inflected
  endings (up to 5 letters); the school name becomes `[School]`. A quote that is only the
  placeholder is rejected, and a restored quote is widened to its whole sentence.
- A letter check refused because AI is off (master switch or no gateway key) is 503
  `coach_unavailable` with `details.ai_available: false`; a provider or timeout failure is the same
  code with `details.ai_available: true`. Both are free.

### Reader notes, sensitive content, copy check, extra redaction

- The score step also returns `reader_notes` (at most 2 `{quote, question}`, never scored), `safety` and
  `sensitive` ({health, discipline} sentences). The server stores `result.reader_notes` (ids `r1`, `r2`),
  `result.sensitive` (`[{kind, quote}]`, one per kind, wording fixed in the frontend in en/ru/uz),
  `result.safety` and `result.copy` (`{percent, date}`, 30% or more, author only).
- A sentence with a health keyword (en/ru/uz) or flagged by the model is never quoted by a note, strength
  or reader note (the quote is dropped). `safety` true, or a current-danger keyword in the letter, gives an
  unscored check with one sentence pointing to the school's child-protection procedure; the keyword path
  makes no AI call and uses no budget.
- Before sending, besides names and school: `[Person]`, `[Place]`, `[ID]`, `[Date of birth]`
  (`letter_privacy.py`), restored in quotes.
- Copy check: `letter_copy.py`, same recommender name, word 5-gram shingles, containment; no AI.
