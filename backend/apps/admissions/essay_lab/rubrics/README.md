# Rubrics: how the server must use these files

Status (2026-11-22): the personal statement, supplement and recommendation-letter rubrics are loaded and
enforced. No 0-100 score is shown for a rubric until it is in `ESSAY_COACH_SCORED_RUBRICS`, which the owner
fills one rubric at a time after `manage.py coach_calibrate --set <name>` passes. The product rules are in
`docs/naseeb-ai-rules/`; these files must follow them.

## Required in code before use

1. [built] `CRITERIA = {rubric: {key: weight}}` is parsed from each md weight table; a test asserts it sums
   to 100 and matches. A result whose `scores` keys differ from the rubric's criteria raises an error (the
   check is "Coach unavailable" and the credit is refunded).
2. [built] `RUBRIC_FOR_TYPE`: personal_statement and free_writing use the personal statement rubric;
   supplement and scholarship use the supplement rubric. Other essay types have no rubric (unscored).
3. [built] `compute_overall(rubric, scores)` with integer math: `(2*sum(w*(s-1)) + 3) // 6`. All 1s is 0,
   all 4s is 100 (a personal statement's `prompt_fit` is at most 3, so its maximum is 97).
4. [built] Validation: every level above 1 needs a `score_evidence` quote of at least 5 words that occurs in
   one paragraph of the text the model saw; otherwise the level is lowered to 1 (`evidence_lowered`), with
   no retry and no quote-reuse cap. No `truncated` or `topics` flags are sent. Every fence marker
   (`<<<NAME`, `NAME>>>`) and hidden character is removed from the text first.
5. [built] Safety: `current_danger` is unscored with a calm message and `ESSAY_SAFETY_HELPLINE`, shown to
   the student only; the first checks of a day are free. `past_hardship` is scored, with craft questions only.
6. [built] Prompt loader: `_core.md` (up to its Output contract) plus the type file (up to its Calibration
   section); for supplements only the fit levels of the prompt's kind. The loaded text is hashed into the
   input hash.
7. [built] Determinism: temperature 0, a pinned model, no fallback model for scoring. `model` is stored with
   every result. Same text + type + prompt + limit + target school + rubric text + score gate + model returns
   the saved result with no new call and no credit.
8. [built] Role checks: recommendation-letter results only for staff who can write the letter; students
   cannot request or read them.
9. [built] No essay or letter text in logs. Letters are a separate model (`RecommendationLetterCheck`) and
   feature (`recommendation_letter_check`).
- [not used] `activities_description.md`, `honors_description.md` and `topics.md` are not loaded by the
  server and not in the product yet.

## Calibration (gates each rubric)

See `calibration/README.md`. `calibration/<rubric>/<id>.txt` plus `expected.json`. Tests check the files;
`manage.py coach_calibrate` runs them against the real gateway: scores inside the range, at most one level of
drift over 5 runs, adversarial texts at most 3, grammar-fixed and translated copies within one level.

## Decisions (owner)

- Decided (2026-11-22): only the student sees a distress (`safety`) flag; telling the counselor is their
  choice.
- Decided (2026-11-22): `ESSAY_SAFETY_HELPLINE` stays empty until the owner verifies the number by phone,
  and the verification date is recorded next to the setting.
- Decided (2026-11-22): every check costs one daily unit whatever the type or length; unchanged re-checks
  are free, and failed or safety checks are refunded.

## Roadmap (not written yet)

Common App "additional information", UCAS-style personal statement, motivation letter for European, Korean or
Turkish programs, scholarship essay (own rubric), counselor school report, CV, activities and honors entries,
and a language-clarity mode that gives clarity notes with no scores for second-language writers.
