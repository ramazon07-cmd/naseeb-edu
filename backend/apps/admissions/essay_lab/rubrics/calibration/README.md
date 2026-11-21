# Calibration sets

One folder per rubric (`personal_statement`, `supplement`) with `<id>.txt` and `expected.json`
(format in `essay_lab/calibration.py`). `doc_*` texts come from the tables in `docs/naseeb-ai-rules/`; the
others from PR #99. Level keys are the API keys. Run `manage.py coach_calibrate` (real gateway, spends
budget, `--runs 5`) after every rubric, prompt or model change; it exits non-zero when a text is out of range.
Eastfield University is fictional.
