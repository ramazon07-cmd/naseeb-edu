# Rubric: recommendation letter

rubric_version: 3 · essay_type: `recommendation_letter` (to be added; a separate feature, `recommendation_letter` in `ai_budget.py`) · loaded with `_core.md`

The author is a counselor or teacher. Only the author may run the Coach on a letter, and only the author
sees its scores and notes. The server enforces this by role: the student's account can never request or
read it. The UI tells the author that the student will not see it. The letter contains a minor's data and
the author's judgement, so the Coach keeps nothing from one letter for use in another.

The Coach reviews; the author writes. It never drafts or rewrites any part of the letter.

## Criteria and weights

| Key | Criterion | Weight |
| --- | --- | --- |
| `evidence` | Specific observed evidence | 40 |
| `insight` | Insight into the student | 25 |
| `context` | Basis for any comparison | 20 |
| `structure` | Structure and length | 10 |
| `voice` | Authentic voice of the author | 5 |

### evidence (40)

- 1: Adjectives only ("hardworking, kind, bright").
- 2: One example, told as a summary.
- 3: One observed moment with a setting, a date or exact words, tied to a quality. One real moment is
  enough for 3, and a short letter is not a weak letter.
- 4: Two observed moments of different kinds that together show the student, each with concrete details.

### insight (25)

- 1: Praise with no interpretation. 2: Names a trait and asserts it.
- 3: Explains how the student behaves and why it matters for study.
- 4: Shows something a transcript cannot: how they treat others, handle being wrong, or change when taught.

### context (20)

- 1: No comparison and no basis. 2: A bare superlative ("the best student I have taught").
- 3: A comparison with a stated basis of any kind: years known, number of students taught, or the setting
  in which the author saw the student. A new teacher with a short basis can still reach 3.
- 4: A comparison, its basis, and what the author could not observe.

### structure (10)

- 1: Disorganised. 2: Acceptable but the relationship to the student is unclear.
- 3: States the relationship, gives the body, and closes plainly. 4: Every paragraph earns its place; one page or less.

### voice (5)

Never count grammar or fluency. 1: only stock phrases inside the letter; 2: polished but interchangeable;
3: clearly written by someone who knows the student; 4: unmistakably the author's own judgement.

## Rules for letters

- Never ask the author to include family, health, religion, or finances. The author may include them if
  they chose to.
- Never ask the author to hide anything, or to invent or exaggerate any observation.
- The Coach sees one letter. It cannot check whether language is reused across letters; do not claim it.
- Never offer sentences for the letter. Questions and technique examples on unrelated subjects only.

## Example question seeds (reword with the author's own nouns; never use verbatim)

- What did the student do that you did not expect?
- Where did you see them handle being wrong?
- Compared with how many students, seen over how long?
- What can the reader learn here that the transcript cannot show?

## Calibration

`calibration/recommendation_letter/`: at least ten synthetic letters (no real students), including letters
by second-language writers and short letters, with expected score ranges. Block production use until then.
