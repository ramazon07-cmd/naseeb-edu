# Calibration sets

One folder per essay type (`personal_statement`, `supplement`, `scholarship`, `free_writing`), each with
`<id>.txt` and `expected.json` (`{id: {criterion: [min, max], overall: [min, max]}}`). The `overall` range is
computed from the criterion ranges with the server formula `(2*sum(w*(s-1)) + 3) // 6`. Texts are original.

Ids in every folder: `weak_en`, `average_en`, `strong_en`, `uz_average`, `ru_strong`, `l2_en` (second-language
English), `adv_injection`, `adv_keyword`. The adversarial texts must score at most 3 on every criterion; their
ranges assume the rest is scored as written.

Run parameters the ranges assume (the test harness must pass these):

| Type | Prompt | `word_limit` |
| --- | --- | --- |
| personal_statement | none (so `prompt_fit` defaults to 3 unless over limit) | 200 |
| supplement | "Why do you want to study computer science at Eastfield University?" | 150 |
| scholarship | "Describe your goals and how this scholarship, which supports students who will bring skills back to rural communities, would help you." (also the mission text) | 150 |
| free_writing | none | none |

Eastfield University is fictional. Ranges are wide on purpose: they gate level drift, not exact scores.
