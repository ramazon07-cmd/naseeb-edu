# Essay Coach rules (Check depth)

User-facing name: Naseeb AI (internally 'essay coach').

Status: agreed with the product owner on 2026-11-20. Backend built (coach.py, views.py); see Settings below.

## What the student sees

Desktop and tablet: the essay on the left; on the right, the depth score (0-100), five criterion bars
and the change since the last check, then notes lined up beside the sentences they quote. Clicking a
note highlights its sentence and clicking a highlighted sentence opens its note. Questions are
yellow, strengths green.

Phone: the score shrinks to a one-line bar at the top (tap to expand the bars). Notes show one at a
time under their sentence, with Dismiss and Next.

Naseeb AI (the coach) asks questions and points at directions. It never writes or rewrites the essay.

## Two steps: measure first, then notes

Notes cost the most tokens, so every check measures the essay first and only asks for notes when
the score earns them.

**Step 1: score (every check).** The AI reads the essay with the rubric for its type and returns
the five criterion scores (1-4), a short overall summary, 1-3 strengths and 2-4 overall
suggestions. The server, not the AI, turns the criterion scores into 0-100 with the rubric weights
(`(2*sum(w*(s-1)) + 3) // 6`, all 1s = 0, all 4s = 100). Short output, about 300 tokens.

**Step 2: notes (only when the score is above 50).** A second call asks for at most the band's
number of notes. Each note quotes one sentence exactly as written and asks a question about it.

| Score | What the student gets |
| --- | --- |
| 0-50 | Overall feedback and suggestions only, no margin notes. Big-picture help: is the topic too common, is there one specific story, does it answer the prompt; may suggest thinking about other, more personal topics. Step 2 is skipped. |
| 51-60 | Overall feedback + 3-5 notes on the biggest problems only |
| 61-70 | Overall feedback + up to 8 notes |
| 71-80 | Overall feedback + up to 12 notes |
| 81-100 | Overall feedback + up to 25 notes |

The note count is also capped by length: at most one note per 25 words, so a 150-word supplement
gets at most 6 notes whatever its score.

**No repeats.** The server drops repeats before anything is shown:
- At most one note per sentence. If two notes quote overlapping text, keep the higher-priority one.
- A note whose question is nearly the same as another note's is dropped.
- A note's context line may not repeat its own question, nor an earlier note's context line; if it adds nothing new it is left out.
- Notes come back ordered by importance; the first three notes of a check carry the "Priority" flag. It is set once, when the check is made, and does not move as notes are resolved.
- "Sentence" does not split on decimals (3.5) or common abbreviations (Dr., Mr., Mrs., Ms., St., Prof., e.g., i.e., vs.).
Fewer, distinct notes also mean fewer output tokens.

## Interaction

- Clicking a note highlights its sentence and scrolls the essay to it. No "Show in essay" button.
- Each note has two corner icons: ✓ done and ✕ not useful. Done and dismissed notes collapse into a
  "Done (n)" row that can be reopened.
- Each piece of information appears once: the level is in the headline only, the word count in the
  top bar only, colour meaning in the filter chips only.

## Cost rules

- Both calls start with the same text in the same order (rules, rubric, then the essay) and put the
  step-specific instruction last, so the provider reuses the cached start of the prompt on step 2.
- Same essay text + type + rubric version + model = same result, served from cache with no AI call
  and not counted against the daily limit.
- 5 checks per student per day. A re-check of unchanged text does not count.
- Temperature 0 and one pinned model for scoring (no silent fallback model), so the score is stable.
- Output caps: step 1 about 400 tokens; step 2 scales with the band (about 60 tokens per note).

## Language

Notes, summary and suggestions are written in the essay's own language (an English essay gets
English feedback). The surrounding app text stays in the site language.

## Essay types

- With a 0-100 score at launch: personal statement (also free writing) and supplements (also
  scholarship essays), using the drafted rubrics in `backend/apps/admissions/essay_lab/rubrics/`.
- Other types (activity, honors, recommendation letter): notes and overall feedback without a score
  until their rubrics and calibration exist. They use the 61-70 band (up to 8 notes).

## Safety (unchanged)

- Only while outbound AI is switched on (`OUTBOUND_AI_ENABLED`); otherwise the built-in rule checks run.
- Emails and phone numbers are removed before sending; the essay is untrusted data, never instructions.
- Notes whose quote is not in the essay are dropped. No essay text in logs.
- Before students see real scores, the calibration set in the rubrics README must pass
  (sample essays at each level, Uzbek and Russian texts, adversarial texts).

## Open questions

- A 50 vs 51 boundary can flip between checks of nearly the same text. Accept it, or show
  "close to the next level" near a boundary?

## Re-check rules (token saving)

"Check again" runs only when both hold:
1. **Every open note is resolved**: marked done (✓), not useful (✕) or gone (the editor cannot anchor its quote, e.g. inside a tracked suggestion; the client sends this itself), or its sentence was changed so
   its quote is no longer in the text (counts as resolved automatically). With a score of 50 or
   less there are no notes, so only rule 2 applies.
2. **The text really changed**: the fingerprint differs from the last check's and at least
   `ESSAY_COACH_MIN_CHANGED_WORDS` (default 3) words changed against the text that was checked
   (the depth-check checkpoint). Whitespace, case and punctuation-only edits do not count.

The server enforces both; the button is disabled in the UI with the reason as its tooltip
("Resolve all notes first" / "Change your essay first"). Same text (and same type, prompt, rubric and model) never reaches the AI: the
latest check is returned unchanged and nothing is charged. Rule 1 is tested before rule 2, and rule 2
compares at most the first `ESSAY_COACH_MAX_INPUT_CHARS` characters. If the checkpoint holding the checked
text is gone, rule 2 cannot be measured: only the stored fingerprint is compared (unchanged: reuse, else the check
is allowed) and an info line without text is logged.

A check that fails (provider error, timeout, unusable answer) is free: its budget unit is refunded and
the answer is 503. A check makes at most two paid calls and no call is retried, except one retry without
`reasoning_effort` when the gateway rejects it.

## Criteria colours

Each criterion has its own colour, used for its row in Overview, its notes' left edge and icon,
the filter chip dot and the underline in the essay. Strengths are always green.

| Criterion | Key | Colour |
| --- | --- | --- |
| Reflection | `reflection` | amber |
| Specific details | `specificity` | blue |
| Your voice | `voice` | violet |
| Structure | `structure` | teal |
| Answers the prompt | `prompt_fit` | coral |

## API contract (v2)

Stored in `EssayDepthCheck.result` (new checks; old checks keep their old shape and are mapped by
the frontend: kind reflect→reflection, specific→specificity, clarity→structure, strength→strength):

```json
{
  "version": 2,
  "scored": true,
  "overall": 66,
  "scores": {"reflection": 2, "specificity": 3, "voice": 3, "structure": 3, "prompt_fit": 3},
  "summary": "at most 400 chars",
  "suggestions": ["2-4 big-picture suggestions, shown when overall <= 50"],
  "strengths": [{"id": "s1", "criterion": "voice", "quote": "exact text or empty", "text": "why it works"}],
  "notes_locked": false,
  "notes": [{"id": "n1", "criterion": "reflection", "quote": "exact sentence text",
             "question": "the question", "context": "one short new line or empty", "priority": true}]
}
```

- `overall` is computed by the server from `scores` and the rubric weights; `scored` is false (and
  `overall` null) for types without a rubric yet and for the built-in rules fallback.
- Headline from `overall`: 0-50 "Early depth", 51-70 "Developing depth", 71-80 "Solid depth",
  81-100 "Strong depth". Criterion levels 1-4: Emerging, Developing, Solid, Strong.
- `notes` are ordered by importance; the first three have `priority: true` (static: set at check time).

`DepthCheckSerializer` adds `input_hash` (what the check was made for: essay type, prompt, word limit, rubric text
and model, hashed at the start of the check) and `current_input_hash` (what a check made now would carry; on POST, PATCH
and `latest`). When they differ the prompt, type or word limit changed since the check, so the client may offer a new
check even for unchanged text. It also adds: `source` ("ai" | "rules"), `text_fingerprint`, `note_states`
(`{note_id: "done" | "dismissed" | "gone"}`), `previous_overall` (the tab's previous check, for "+10 since
last check"), `checks_left` (today) and `reused` (true when same text returned the latest check).

Endpoints (under `/api/essay-lab/essays/<id>/`):
- `POST depth-check/` `{tab, base_seq}`: 409 `notes_open` `{open: n}` when rule 1 fails;
  409 `too_small_change` when rule 2's word threshold fails; same fingerprint returns the latest
  check with `reused: true` (200, no charge).
- `PATCH depth-check/<check_id>/notes/` `{note_id, state: "done" | "dismissed" | "gone" | "open"}` returns
  the check. Only the essay's owner.
- `GET depth-check/latest/?tab=` unchanged, now with the fields above.

Fingerprint (the Python `coach.text_fingerprint` is the reference), in this order:
1. Unicode NFKC.
2. Lower-case (`str.lower()`).
3. Curly quotes to straight (U+2018 U+2019 U+201A U+201B U+2032 to `'`; U+201C U+201D U+201E U+201F U+2033 to `"`).
4. Keep a character only if Python `str.isalnum()` or `str.isspace()` is true. Letters and digits are
   the Unicode categories L* and N* (so also fullwidth and other-script digits and letters). Whitespace
   is the Python `str.isspace()` set: space, tab, line breaks, U+001C to U+001F, U+0085, U+00A0, U+1680,
   U+2000 to U+200A, U+2028, U+2029, U+202F, U+205F, U+3000. Everything else is dropped: punctuation,
   symbols, emoji, combining marks that NFKC did not compose into a letter, and format characters
   such as U+FEFF and U+200B (U+FEFF is not whitespace).
5. Split on whitespace and join with one space (this trims).
6. sha256 of the UTF-8 bytes, lower-case hex. Empty text hashes the empty string.

Shared test vectors: `docs/essay-coach-fingerprint-fixtures.json` (`name`, `text`, `sha256`); the backend and
the frontend both test against it. The frontend computes the same with `crypto.subtle` to show "Text changed".

Reuse needs more than the same text: the saved check is returned as `reused` only when the essay type,
the prompt, the word limit, the rubric text and the model also match those of the check (`input_hash`). If only the input
changed, a new check runs without the re-check rules.

## Settings (backend)

| Setting | Default | Meaning |
| --- | --- | --- |
| `ESSAY_COACH_USER_DAILY_LIMIT` | 5 | Checks per student per day. One check is one unit although it makes two AI calls; unchanged-text re-checks and refused checks are free. |
| `ESSAY_COACH_MIN_CHANGED_WORDS` | 3 | Re-check rule 2 threshold. |
| `ESSAY_COACH_TOTAL_SECONDS` | 90 | Deadline for both calls of one check together; step 2 gets only the time left (at least 5 s, else the check fails and is refunded). Per-call timeout stays `ESSAY_COACH_TIMEOUT_SECONDS` (40). The client timeout must be above 90. |
| `ESSAY_COACH_RECHECK_PER_MINUTE` | 20 | Cheap per-user limit on depth-check requests, applied before the re-check rules (reused and refused re-checks use it, not the 15-second slot or the budget). |
| `ESSAY_COACH_REASONING_EFFORT` | minimal | Sent as `reasoning_effort`; empty = not sent; dropped for one retry if the gateway answers 400 about it. |
| `ESSAY_COACH_MAX_OUTPUT_TOKENS` | 2200 | Ceiling for one call (step 1 asks for 500, step 2 for 70 per note + 150). |
| `ESSAY_COACH_MODEL` | `AI_ASSISTANT_MODEL` | Pinned scoring model; no fallback model is sent. |

The database connection is released before each provider call.

Backend notes: the supplement rubric's criteria are stored under the API keys
(`fit_specificity` = `prompt_fit`, `evidence` = `specificity`, `concision` = `structure`).
`notes_locked` is true when the score is 50 or less (step 2 skipped). A distress answer from the
rubric's safety branch is returned unscored with the message as `summary` and no notes.
Error bodies: `notes_open` also carries `open`; `too_small_change` carries `changed` and `min_words`.
