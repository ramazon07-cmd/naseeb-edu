# College match rules

The college match shows a student ten universities for their major. **Rules choose them, not the
AI, and the same profile always gets the same list.** The default match makes no AI call. The only
AI step is the optional "Why these fit you" button (one short line per card, cached, counted against
the daily limit). It reads the same facts as the cards and cannot change the list.

Code: `backend/apps/admissions/college_match.py` (rules), `subjects.py` (major to subject),
`admission_chance.py` (band, unchanged, chance-v2).

## 1. Data

- **Subject ranks:** QS World University Rankings by Subject **2026** (55 subjects and 5 broad areas),
  stored in `UniversitySubjectRank` from `catalog_data/qs_subject_rankings_2026.json`. A ranked range
  such as 201-250 is stored as 201 and shown as published. Rebuild the file with
  `scripts/build_qs_subject_catalog.py <xlsx>`; `build.sh` loads it on every deploy, right after the migrations
  (`load_qs_rankings`, then `load_qs_subject_rankings`; both safe to run again, about 2 s each, and a failure
  stops the deploy). By hand: the same two commands in that order. It matches by university name and country
  and never creates a university.
- **Overall rank** (only when no major maps): QS World University Rankings 2027, already in the catalogue.
- **Admission and aid facts:** the catalogue (SAT range, admit rates, international cost, aid flags,
  need policy).
- **QS terms of use:** the rankings are QS's data. Before any commercial reuse (a paid product, a
  public page) QS's terms must be checked and permission confirmed. This file is a note, not legal advice.

## 2. Step by step

1. **Major to subjects.** The target major (free text, English, Russian or Uzbek) is split on
   `, ; / newline & and и va` and each part is matched by fixed keyword lists to a QS subject
   ("Computer Science", "информатика", "kompyuter injiniringi" are Computer Science & Information
   Systems; "Business, Economics" is Business & Management plus Economics). The subject with the
   longest matching keyword wins; a broad area ("Engineering") is used only when no subject matches.
   Nothing mapped: the overall QS rank is used and the student sees "Pick your major for a better list".
2. **Candidates.** Universities with a QS 2026 rank in any of the student's subjects (best rank counts),
   in the student's target countries. After them, universities with no subject rank whose popular majors
   name the major.
3. **Aid and cost gate.** Cost is the yearly cost for a student from abroad: `intl_cost_usd`; outside the
   US `net_price_usd`, then `tuition_usd`. A US net price is what US students pay after aid, so it is never
   used. A university "gives aid to students from abroad" when `offers_international_aid` is set or it has
   an international need policy. A university that does not is **dropped** when:
   - the student needs a scholarship, unless its cost is at or under the student's budget (unknown
     cost or no budget set does not count as under); or
   - its cost is more than **2 x the budget**.
   Universities that give international aid, and unknown costs for students who do not need a
   scholarship, stay; an unknown cost is flagged "Cost unknown".
4. **Band.** The chance-v2 engine compares the student's SAT or ACT and grades with the university's
   range and admit rate for international students, and returns far reach, reach, target or safety. Only
   the **academics** score is given to it; activities and essays are neutral, so they never change who
   is listed or the band. A university the engine cannot place (no admit rate) or where the student is
   not eligible is left out.
5. **Order inside a band:** subject rank (lower first; no subject rank last), then aid for international
   students (yes, need-aware, merit only, none, unknown), then higher international admit rate, then
   overall QS rank, then name.
6. **Ten cards: 3 reach, 4 target, 3 safety.** Reach takes reach before far reach. A short group is filled
   from the nearest group (reach from target then safety; target from reach then safety; safety from
   target then reach), each card keeps its own band, and the list says so. Fewer than ten fit: the list
   is shorter and says so.

## 3. What each card says

Band; subject and rank ("#12 in Computer Science, QS 2026"); SAT position (below, inside or above the
university's range with both numbers, or "no SAT range listed"); aid for international students (yes,
need-aware, merit only, none listed, unknown); yearly cost against the budget; admit rate; up to two
suggested programs (a program matches when its major text matches the student's, or both map to the
same QS subject); Add and Add all.

Aid status: **yes** when need-blind, or it offers international aid (meeting full need counts), **need-aware**
for a need-aware policy, **merit only**, **none listed** when the catalogue has aid details but no aid for
this student, **unknown** when it has none.
