# Rubric: supplemental essay

rubric_version: 3 · essay_type: `supplement` · loaded with `_core.md`

Typical forms: "Why this university or major?", "Describe a community you belong to", "Tell us about
something you enjoy learning". Lengths vary a lot (often 50 to 650 words). Use the `word_limit` the server
passes; do not assume a range. The reader already has the personal statement, which the Coach does not see,
so never judge whether this essay repeats it.

## Criteria and weights

| Key | Criterion | Weight |
| --- | --- | --- |
| `fit_specificity` | Specificity to the school, program or prompt | 30 |
| `reflection` | Reflection and personal connection | 25 |
| `evidence` | Concrete evidence from the writer's life | 20 |
| `voice` | Individual voice | 15 |
| `concision` | Focus and use of the word limit | 10 |

### fit_specificity (30)

- 1: Could be pasted into any application. Praise of rankings or "world-class faculty".
- 2: Names the school, but only with facts from its homepage (location, size, famous alumni).
- 3: Names particular things (a course, lab, club, tradition, a professor's published work) and says why each matters to this writer.
- 4: Also says what only this writer would do there, with a concrete first step.
  If the prompt is not about a school, judge how precisely the answer addresses that prompt.

### reflection (25)

- 1: Lists interests or states that something matters.
- 2: Says an interest matters and gives a general reason.
- 3: Explains how one experience led to the interest and what question it left open.
- 4: Names a real tension or change in thinking that explains why this place or subject, quoted.

### evidence (20)

- 1: Claims only. 2: One example mentioned in passing.
- 3: One experience told with concrete details that support the claim.
- 4: Two experiences of different kinds that each support the claim with concrete details.

### voice (15)

Same four levels as the personal statement: 1 borrowed; 2 correct but interchangeable (and no sentence
that is plain, odd, unflattering or unfinished); 3 a recognisable way of saying things with one plain,
direct sentence only this writer would write; 4 unmistakably this person throughout. Never count
vocabulary, grammar or sentence variety.

### concision (10)

- 1: Under 50% of `word_limit`, or over it. 2: Between 50% and 75%, or visibly padded.
- 3: 75% to 89%, or no limit given (default 3, say so), with every sentence doing work.
- 4: 90% to 100% of the limit and nothing could be cut.

## Example question seeds (reword with the student's own nouns; never use verbatim)

- Which one particular thing there would you use in your first month, and how?
- What did you do before applying that shows the interest is real?
- What would you lose if you went to a different school?

## Failure patterns

1. Flattery with no link to the writer. Ask what the writer will do.
2. The résumé repeated. Ask what the activities do not show.
3. Another school's name or the wrong major left in. Flag as `clarity`; score `fit_specificity` 1.
4. Prestige as the reason. Ask for a reason that survives if the school were unknown.

## Uzbek and Russian writers

Follow `_core.md` (Language fairness). Judge ideas, events and details, never grammar, spelling or vocabulary.
A second-language English essay must not lose points in `voice` or `reflection` for plain wording, short
sentences or literal phrasing; a plain sentence that only this person would write can earn a 3 or 4. A formal
register, proverbs, a collective "we" and respect for elders are cultural rhetoric, not genericness. Essays in
Uzbek or Russian use the same scale and the same criteria, and the reply is in the essay's language. Family
work, caring duties and tutoring count as evidence the same as clubs. Never ask a student to start a new
activity.

## Calibration

`calibration/supplement/` holds the texts (why this school, community, curiosity) and expected score
ranges, including Uzbek and Russian texts and two adversarial texts. Block production use until the
calibration tests pass.
