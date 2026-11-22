# Calibration sets

One folder per rubric (`personal_statement`, `supplement`, `recommendation_letter`) with `<id>.txt` and
`expected.json` (format in `essay_lab/calibration.py`). `doc_*` texts and the letters `L1`-`L4`, `N1`, `A1`
come from the tables in `docs/naseeb-ai-rules/`; the other essay texts from PR #99; the rest were added on
2026-11-22. All texts are synthetic: no real student. Eastfield University and Westbrook University are
fictional. Level keys are the API keys.

Run `manage.py coach_calibrate --set <name>` (real gateway, spends budget, `--runs 5`) after every rubric,
prompt or model change; it exits non-zero when a text is out of range. The command always sees the levels,
even while students and counselors do not see the score. Only after it passes does the owner add the
rubric to `ESSAY_COACH_SCORED_RUBRICS`, one rubric at a time.

What a set must hold (moved from the rubric files, which no longer send it to the model):

- **Personal statement** (`personal_statement/`): at least ten texts with expected score ranges, including
  Uzbek and Russian essays, essays by second-language writers, two adversarial texts (one that asks for top
  scores, one stuffed with confession words), a past-bereavement essay (scored, never routed to safety, no
  note asks what it cost), an over-limit essay (fit 1) and a current-danger essay (`expect_safety`). Every
  case without a prompt expects `prompt_fit` 3, unless the server's length rule sets it to 1.
- **Supplement** (`supplement/`): why this school, why major, community and scholarship prompts, Uzbek and
  Russian texts, adversarial texts, a short list (`expect_score_hidden: short`), a general answer with no
  prompt (fit 3), an over-limit answer (concision 1) and a plain answer naming the wrong school (fit 1). The
  set runs with `university_name` "Eastfield University".
- **Recommendation letter** (`recommendation_letter/`): at least ten synthetic letters, including letters by
  second-language writers, short letters, a letter in Russian, a 1,000+ word letter, a gender-coded letter,
  a hardship story with no evidence and an adversarial letter with hidden text.

Level ranges are the documented level ±1; the overall range is the gate, and it always lies inside what
the level ranges can reach (tested).
