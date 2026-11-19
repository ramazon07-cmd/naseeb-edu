# Rubric: scholarship essay

rubric_version: 3 · essay_type: `scholarship` · loaded with `_core.md`

A scholarship essay answers one question for a committee that reads many essays and funds few: *what will
this person do with the support, and is the case for them real?* It covers scholarship, financial-aid and
merit-award essays. It is not a personal statement and not a "why this school" essay. Lengths vary a lot
(often 150 to 650 words). Use the `word_limit` the server passes; do not assume a range. The Coach does not
see the scholarship's rules, so judge fit to the mission only from the prompt or mission text the server
passes. Without it, judge `mission_fit` as 3 (default, say so).

## Criteria and weights

| Key | Criterion | Weight |
| --- | --- | --- |
| `goals_impact` | Goals and intended impact | 25 |
| `evidence` | Evidence of merit or need, with specifics | 25 |
| `mission_fit` | Fit to the scholarship's mission | 20 |
| `reflection_voice` | Reflection and individual voice | 20 |
| `prompt_fit` | Fit to the prompt and length | 10 |

### goals_impact (25)

- 1: No goal, or only "I want to succeed" and "help my community".
- 2: A goal and a field are named, but the impact is a general wish. The text does not say who or what would
  change.
- 3: A goal with a concrete next step and a named person, group or place that would be affected (a village
  school, a family business, a clinic, younger students at the writer's school).
- 4: Also a cost, obstacle or smaller version of the goal the writer has already tried, quoted, so the plan is
  anchored in what this writer has actually done. Without it, the maximum is 3.

### evidence (25)

Merit and need count the same. Both are judged only by how specific the text is. Never ask for financial
details, never judge whether need is "real", and never require the writer to disclose need.

- 1: Claims only ("I am hardworking", "my family has difficulties").
- 2: One example or circumstance mentioned in passing, or a list of awards or hardships with no detail.
- 3: One achievement or circumstance told with at least three concrete details (a named person, an exact action,
  a number the writer gave, an object or place).
- 4: Two achievements or circumstances of different kinds, each with concrete details, or one told in enough
  detail that a stranger could picture it. At least one detail was not needed for the claim.

### mission_fit (20)

- 1: Could be sent to any scholarship. Praise of the donor or "this opportunity".
- 2: Repeats the scholarship's name or stated values without connecting them to the writer's life.
- 3: Names a particular value, field or activity of the scholarship and shows, with one event, how the writer
  already lives it.
- 4: Also says what only this writer would do with the award in a way that serves that mission, with a concrete
  first step. If no mission text was passed, the maximum is 3.

### reflection_voice (20)

Judge whether a particular person is thinking and speaking. Never count vocabulary, grammar or sentence variety.

- 1: Borrowed. Quotations, definitions or stock phrases stand where the writer should be.
- 2: Correct but interchangeable. States a lesson or a quality with no event. If there is no sentence that is
  plain, odd, unflattering or unfinished, the maximum is 2.
- 3: A real thought connected to a concrete moment, and at least one plain, direct sentence only this writer
  would write.
- 4: At least two of these, each quoted: a doubt, a cost, a changed belief, an unresolved question; at least
  one names a specific person, object or number. The voice is unmistakably this person's throughout.

### prompt_fit (10)

- 1: Ignores the prompt, or is under 50% of `word_limit`, or over it.
- 2: Touches the prompt loosely, or is visibly padded, or between 50% and 75% of the limit.
- 3: Answers the prompt directly, 75% to 100% of the limit. Default when there is no prompt or no limit (say so).
- 4: Answers every part of the prompt and uses 90% to 100% of the limit with nothing that could be cut. Without
  a prompt, the maximum is 3.

## Example question seeds (reword with the student's own nouns; never use verbatim)

- Who specifically would be different in five years if this plan worked, and what would they notice first?
- What have you already done on a small scale toward this goal?
- What happened in the ten seconds after the moment you quote?
- What would you do in the first month if the award arrived?
- Which sentence here could only be written by you, and which could be written by anyone?

## Failure patterns (use to choose notes, not to deduct)

1. The hardship list. Facts about circumstances, with no scene. Ask only craft questions about what the writer
   chose to include. Never ask for more disclosure and remind the student they choose what to share.
2. The grade and award list. Ask what the writer did that no certificate shows.
3. Gratitude and flattery of the donor. Ask what the writer will do.
4. A grand goal with no first step. Ask what the next small step is.
5. The tidy promise ("I will give back to my country"). Ask who, where and how the writer already does this.

## Uzbek and Russian writers

Follow `_core.md` (Language fairness). Judge ideas, events and details, never grammar, spelling or vocabulary.
A second-language English essay must not lose points in `reflection_voice` for plain wording, short
sentences or literal phrasing; a plain sentence that only this person would write can earn a 3 or 4. A formal
register, a collective "we" and gratitude toward family or teachers are cultural rhetoric, not genericness.
Essays in Uzbek or Russian use the same scale and the same criteria, and the reply is in the essay's language.
Family work, caring duties and tutoring count as evidence the same as competitions. Never assume or ask about
the family's finances.

## Calibration

`calibration/scholarship/` holds the texts and expected score ranges, including Uzbek, Russian,
second-language English, and two adversarial texts. Do not use this rubric in production until the
calibration tests pass.
