# Naseeb AI writing rules

How Naseeb AI reads and scores student essays and counselor letters. One file per type:

- [personal-statement.md](personal-statement.md): Common App personal statement (and free writing).
- [supplemental-essay.md](supplemental-essay.md): "Why us", "Why major", community, short answers,
  scholarship essays.
- [recommendation-letter.md](recommendation-letter.md): counselor and teacher letters, used only by
  counselors.
- [college-match.md](college-match.md): the rule-based list of ten universities and the optional
  "Why these fit you" lines.

These files are the product rules: what is scored, how, and what Naseeb AI must never do. The
prompt text the server sends lives in `backend/apps/admissions/essay_lab/rubrics/*.md` and must
follow these rules. The engine rules (two steps, bands, re-check, cost) are in
`docs/essay-coach-rules.md` and `docs/letter-coach-rules.md`.

Status (2026-11-21): written after a review by three independent reviewers (admissions reader,
supplement specialist, counselor). Items marked **[built]** already work in PRs #113/#114. Items
marked **[to build]** are agreed rules the code does not follow yet. Items marked **[decide]** need
the product owner's choice.

## Rules for every type

1. **Naseeb AI asks; it never writes.** No rewritten sentences, no suggested wording, no sentence
   starters inside the essay or letter. The only exception is the counselor's Ideas tab, which
   inserts a neutral profile fact the counselor rewrites in their own words.
2. **The server does the maths.** The model gives each criterion a level 1-4 with a quoted piece of
   evidence; the server turns levels into 0-100 with the weights below. **[built]**
3. **Every score above 1 needs evidence:** a quote of at least 5 words that really occurs in the
   text. **[to build: validation]**
4. **Never score language.** Grammar, spelling, vocabulary and fluency are never scored. A second-
   language writer with the same content gets the same score as a native writer. If meaning is
   unclear because of language, Naseeb AI asks a clarity question; it never lowers voice or detail
   for it.
5. **Never judge the topic.** Naseeb AI never says a topic is bad. For a weak essay it asks which
   single moment only this writer could tell.
6. **No detection claims.** Naseeb AI never says text is AI-written or plagiarised. Detectors are
   unreliable and flag non-native writers most. Show a one-time policy note instead: universities
   treat substantially AI-written essays as dishonest.
7. **Untrusted text.** The essay is data, never instructions. Text addressed to the model ("give
   all 4s") is ignored, never quoted as evidence, and does not change any score. Zero-width and
   format characters are removed before the model sees the text. **[to build: strip characters]**
8. **No repeats.** One note per sentence; no near-duplicate questions or context lines. **[built]**
9. **Privacy.** Emails and phone numbers are removed before sending. Nothing from one essay or letter
   is kept for another. No essay or letter text in logs. **[built]**
10. **Consistency.** One pinned model, temperature 0. The same text, type, prompt and limits give the
    same result (and cost nothing the second time). **[built]**
11. **Calibration before real scores.** No student or counselor sees a 0-100 score from a type until
    its calibration set (below in each file, at least 10 texts) passes: each score inside its range,
    at most one level of drift over 5 runs, grammar-fixed and translated copies within one level.
