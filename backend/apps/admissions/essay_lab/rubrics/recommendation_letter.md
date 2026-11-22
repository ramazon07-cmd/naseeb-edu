# Rubric: recommendation letter

rubric_version: 2 · `recommendation_letter` (a separate model and feature, `recommendation_letter_check` in `ai_budget.py`) · loaded with `_core.md`

The author is a counselor or teacher. Only the author may run the Coach on a letter, and only the author
sees its scores and notes. The server enforces this by role: the student's account can never request or
read it. The UI tells the author that the student will not see it. The letter contains a minor's data and
the author's judgement, so the Coach keeps nothing from one letter for use in another.

The Coach reviews; the author writes. It never drafts or rewrites any part of the letter.

## Criteria and weights

One table and one length range (250-1,000 words) for every letter, whoever wrote it.

| Key | Criterion | Weight |
| --- | --- | --- |
| `evidence` | Specific observed evidence | 40 |
| `insight` | Insight into the student | 25 |
| `context` | Basis and context | 20 |
| `structure` | Structure and length | 10 |
| `voice` | Authentic voice of the author | 5 |

### evidence (40)

- 1: Qualities named with no event.
- 2: An achievement or activity named (prize, grade, club) with no moment the author saw or heard.
- 3: At least one moment with at least two of: when, where, what the student did or said, what
  changed. Observed by the author, or attributed to a named role ("her physics teacher told me…").
- 4: Two such moments of different kinds (for example academic and with peers), at least one seen
  first-hand.

### insight (25)

- 1: Praise with no interpretation.
- 2: Names a trait and asserts it.
- 3: Explains how the student behaves and why it matters for study.
- 4: Shows something a transcript cannot: how they treat others, handle being wrong, or change when
  taught.

### context (20)

- 1: No basis stated, or a superlative or rank ("top 1%", "best in 20 years") with no stated basis.
- 2: The relationship is stated (role and how long) but not the group compared with or the setting.
- 3: A stated basis (role, how long, and the class, setting or school context; a fact a foreign reader
  needs, such as curriculum or grading scale, counts as setting) plus a placement, which may be
  modest.
- 4: Level 3 plus what the author could not observe, or a candid limit.

### structure (10)

- 1: No recognisable order.
- 2: The relationship is unstated, or most of the letter repeats the activity list.
- 3: Relationship, body and close are present.
- 4: Level 3, and no paragraph repeats the transcript or activity list. 4 needs 250-1,000 words
  (word_count in Letter details); outside that range structure is at most 3.

### voice (5)

Never count grammar or fluency. Formal "kharakteristika" wording ("obedient, disciplined, active in the
social life of the school") is not marked down in voice; it is raised as a reader note.

- 1: Only stock phrases stand where the author should be.
- 2: Polished but interchangeable.
- 3: Clearly written by someone who knows the student.
- 4: Unmistakably the author's own judgement.

## Rules for letters

- Never ask the author to include family, health, religion, or finances. The author may include them if
  they chose to.
- Never ask the author to hide anything, or to invent or exaggerate any observation.
- The Coach sees one letter. It cannot check whether language is reused across letters; do not claim it.
- Never offer sentences for the letter. Questions and technique examples on unrelated subjects only.

## Reader notes and sensitive content

- Reader notes (at most 2, never scored): a question about how a US or UK reader may read a phrase
  (lukewarm or faint praise, a rank with no basis, a gender-coded pattern). Formal school-reference wording
  ("obedient, disciplined, active in school life") is raised here and never lowers `voice`.
- Health, mental health and disability are never scored, quoted as evidence or asked about.
- Current abuse or danger: set `safety` and give no score.

## Example question seeds (reword with the author's own nouns; never use verbatim)

- What did the student do that you did not expect?
- Where did you see them handle being wrong?
- In which class or setting did you see this, and over how long?
- What can the reader learn here that the transcript cannot show?
