# Rubric: supplemental essay

rubric_version: 2 · essay_type: `supplement` (also used for `scholarship` until it gets its own rubric) · loaded with `_core.md`

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

The server reads the prompt and picks one prompt kind; only that kind's fit levels are shown below. The
other criteria never change. A supplement with no prompt is general; a scholarship essay is always
scholarship. With no prompt the server sets fit to 3, and the summary says in one sentence that fit could
not be judged because no question was given.

#### Fit: why_school

- 1: Nothing names the school, or the reasons fit any selective university (rank, prestige, "diverse").
- 2: Facts any applicant would cite (location, size, ranking), or a list of offerings not linked to the writer.
- 3: At least one particular offering (course, lab, programme, professor's work, tradition) linked to a
  specific earlier thing the writer did.
- 4: Level 3 plus a concrete first action the writer would take there that follows from it.
- Never reward campus visits or contact with admissions; online research counts the same.

#### Fit: why_major

- 1: Could be about any subject. 2: Says the subject matters, with no work of the writer's own.
- 3: A specific problem, idea, text or method the writer pursued on their own (free courses, books,
  projects, family work count) and what they did with it.
- 4: Level 3 plus a question in the field the writer cannot answer yet.

#### Fit: community

- 1: Names no community, or only a label. 2: Describes the community but not the writer's part in it.
- 3: Names the community and one thing the writer did or gave in it. A collective "we" is fine if the
  writer's own role is clear.
- 4: Level 3 plus what it changed in the writer, or what they still disagree with in it.

#### Fit: scholarship

- 1: Does not connect to the scholarship at all. 2: Says funding would help, in general terms.
- 3: What the funding makes possible in specific terms, connected to the scholarship's stated criteria.
- 4: Level 3 plus the writer's plan for after it.

#### Fit: general

- 1: Does not answer the question asked. 2: Answers in general terms any applicant could use.
- 3: Answers this exact question with one specific example.
- 4: Level 3 plus why it matters to the writer now.

#### Wrong school (every kind)

`target_school` in Essay details is the school; when it is empty, never apply Wrong school. When the
essay names a different school as the writer's destination, fit is 1, with a clarity note. Mentioning a
school the writer compared is fine.

### reflection (25)

- 1: No connection to the writer. 2: A stated reason with nothing behind it.
- 3: One experience and what changed in the writer's thinking or plans because of it.
- 4: A belief held before and what replaced it, or a tension still open, tied to this subject or place.

### evidence (20)

- 1: None. 2: An activity named without a moment. 3: One experience with two concrete details.
- 4: Two experiences of different kinds.
- Short limits (word_limit 150 or less, or no limit and text under 150 words): 3 = one experience with
  one concrete detail; 4 = one experience with two concrete details.

### voice (15)

Judge what is said, never how fluently it is said. Never count vocabulary, grammar or sentence variety.

- 1: No sentence where the writer speaks for themselves: only general statements, quotations or
  definitions.
- 2: No sentence states an opinion, admission or reaction a reader could disagree with.
- 3: One sentence stating an opinion, admission or reaction a reader could disagree with.
- 4: Two such sentences, in different paragraphs.

### concision (10)

Shown to the student as "Focus and length". The server computes the share of the word limit used and
passes it as `word_limit_share_percent`; never count words yourself. With no limit, concision is 3, set
by the server.

When word_limit is 100 or more:

- 1: Over the limit (above 100%), or under 40% of it.
- 2: 40% to 59%, or two or more sentences that only restate.
- 3: 60% or more, with at most one sentence that adds nothing.
- 4: 60% or more, and no sentence could go without losing a fact.

When word_limit is under 100 (the share of the space used does not count):

- 1: Over the limit.
- 2: Filler or restating.
- 3: Answers every part asked, with no filler.
- 4: Every sentence carries a fact.

## Scholarship essays: sensitivity

- Never score how severe the hardship is. A short factual statement of need is not a weakness.
- Never ask for income, debts, a parent's job loss, or similar details.
- Reward the plan and the contribution, not the suffering. Do not prompt "give back" promises.

## Example question seeds (reword with the student's own nouns; never use verbatim)

- Which one particular thing there would you use in your first month, and how?
- What did you do before applying that shows the interest is real?
- What would you lose if you went to a different school?

## Failure patterns

1. Flattery with no link to the writer. Ask what the writer will do.
2. The résumé repeated. Ask what the activities do not show.
3. Another school's name or the wrong major left in (only when `target_school` is given). Flag as a
   clarity question; score `fit_specificity` 1.
4. Prestige as the reason. Ask for a reason that survives if the school were unknown.
