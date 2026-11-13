# Rubrics: how the server must use these files

Status: **drafts. Not wired into `coach.py`. Do not enable for students until the items below exist.**

## Required in code before use
1. `CRITERIA = {type: {key: weight}}` and a test that parses each md weight table, asserts it sums to 100,
   and matches `CRITERIA`. A result whose `scores` keys differ from `CRITERIA[type]` is rejected, then retried once.
2. `RUBRIC_FOR_TYPE`: personal_statement and free_writing use the personal statement rubric; supplement and
   scholarship use the supplement rubric. `activity`, `honor`, `recommendation_letter` need new `EssayType` values.
   An unmapped type raises an error; it never falls back.
3. `compute_overall(type, scores)` with integer math: `(2*sum(w*(s-1)) + 3) // 6`. Unit test: all 1s is 0, all 4s is 100.
4. `validate_result`: check `mode`, `rubric_version`, `type`, per-type note kinds, and that every score above 1 has
   a `score_evidence` quote of at least 5 words that occurs in the text, with one quote used for at most 3 criteria.
   Validate quotes against the same redacted and truncated text the model saw. Strip the marker strings
   `<<<ESSAY_TEXT`, `ESSAY_TEXT>>>` from user text. Pass `truncated` and `topics` flags to the prompt.
5. A `mode: "safety"` branch that skips scoring and the retry, and is not charged as a normal check.
6. Prompt loader: `_core.md` + the type file (+ `topics.md` only when asked). Hash the loaded text into the version.
7. Determinism: temperature 0, a pinned model, and no silent fallback model for scoring. Store `model` and
   `rubric_version` with every result. Cache by `sha256(normalized text) + type + rubric_version + model` so an
   unchanged essay returns the same result with no new call and no credit charge.
8. Role checks: recommendation-letter results only for the author; students cannot request or read them.
9. Do not store essay text unredacted in logs.

## Calibration (gates each rubric)
`calibration/<type>/<id>.txt` plus `expected.json` with `{id: {criterion: [min, max], overall: [min, max]}}`.
Include texts at each level, Uzbek and Russian texts, second-language texts, and two adversarial texts.
Tests: scores inside the range; at most one level of drift over 5 runs at temperature 0; adversarial texts
score at most 3; whitespace, name and punctuation changes do not change scores. Run on every rubric,
prompt or model change, and gate deployment on it.

## Open decisions (owner)
- Who sees a distress (`safety`) flag: the student only, or also their counselor.
- The current Uzbekistan child helpline number (must be verified before it replaces the placeholder in `_core.md`).
- Credit price per type and per word band.

## Roadmap (not written yet)
Common App "additional information", UCAS-style personal statement, motivation letter for European, Korean or
Turkish programs, scholarship essay (own rubric), counselor school report, CV, and a language-clarity mode
that gives clarity notes with no scores for second-language writers.
