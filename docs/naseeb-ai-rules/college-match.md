# College match rules

The college match shows a student ten universities for their major. **Rules choose them, not the
AI, and the same profile always gets the same list.** The default match makes no AI call. The only
AI step is the optional "Why these fit you" button (one short line per card, cached, counted against
the daily limit). It reads the same facts as the cards and cannot change the list.

Code: `backend/apps/admissions/college_match.py` (rules), `subjects.py` (major to subject),
`admission_chance.py` (band, chance-v2), `student_rubric.py` (the Academics score), `match_reasons.py`
(the optional "Why these fit you" lines).

## 1. Data

- **Subject ranks:** QS World University Rankings by Subject **2026** (55 subjects and 5 broad areas),
  stored in `UniversitySubjectRank` from `catalog_data/qs_subject_rankings_2026.json`. A ranked range
  such as 201-250 is stored as 201 and shown as published. Rebuild the file with
  `scripts/build_qs_subject_catalog.py <xlsx>`; load it with `python manage.py load_qs_subject_rankings`
  (run `load_qs_rankings` first; it matches by university name and country, never creates a
  university, and is safe to run again).
- **Overall rank** (only when no major maps): QS World University Rankings 2027, already in the catalogue.
- **Admission and aid facts:** the catalogue (SAT range, admit rates, international cost, aid flags,
  need policy).
- **QS terms of use:** the rankings are QS's data. Before any commercial reuse (a paid product, a
  public page) QS's terms must be checked and permission confirmed. This file is a note, not legal advice.

## 2. Step by step

1. **Major to subjects.** The target major (free text, English, Russian or Uzbek) is split on
   `, ; / | newline & and и va hamda`. Compound names are matched whole first, so "Oil and gas",
   "Electrical & Electronic Engineering" and "Hospitality & Leisure Management" stay one major. Each part
   is matched by fixed keyword lists to a QS subject ("Computer Science", "информатика", "kompyuter
   injiniringi" are Computer Science & Information Systems; "Business, Economics" is Business & Management
   plus Economics). The subject with the longest matching keyword wins, and on a keyword-length tie every
   tied subject is kept ("Bioinformatics" is Biological Sciences and Computer Science). A broad area
   ("Engineering") is used only when no subject matches. **Decided (2026-11-22):** "liberal arts" goes to
   Arts & Humanities, not Art & Design; "sport(s) management" and "sports science" are Sports-related
   Subjects, not Business. Nothing mapped: the overall QS rank is used and the student sees "Pick your
   major for a better list".
2. **Candidates.** Universities with a QS 2026 rank in any of the student's subjects (best rank counts),
   in the student's target countries. After them, universities with no subject rank whose popular majors
   name the major or map to the same QS subject or broad area.
3. **Aid and cost gate.** Cost is the yearly cost for a student from abroad. **Decided (2026-11-22):**
   US universities: `intl_cost_usd` only (no fallback). Elsewhere: `net_price_usd`, then `tuition_usd`.
   A row counts as US by its market or, when the market is blank, by its country. A US net price is what
   US students pay after aid, so it is never used. A university "gives aid to students from abroad" when
   `offers_international_aid` is set or it has an international need policy. A university that does not is
   **dropped** when:
   - the student needs a scholarship, unless its cost is at or under the student's budget (unknown
     cost or no budget set does not count as under); or
   - its cost is more than **2 x the budget**.
   Universities that give international aid, and unknown costs for students who do not need a
   scholarship, stay; an unknown cost is flagged "Cost unknown".
4. **Band.** The band compares the student's SAT/ACT and GPA with the university's range and the
   international admit rate (published, else estimated from the overall rate: x0.5 under 25%, x0.8 under
   50%, as-is at 50%+, marked ≈). The Academics x/10 tile is a summary and does not change the band;
   activities and essays are not used. A university the engine cannot place, or where the student is not
   eligible, is left out. **Decided (2026-11-22):** three left-out notes tell the student why:
   - `test_needed`: "{n} universities were left out because they expect an SAT or ACT score; add yours to
     see them" (no band, the university has an SAT or ACT range, the student has neither score);
   - `aid_unknown` / `no_intl_aid`: for a student who needs a scholarship, universities the gate dropped,
     split into "the catalogue has no aid details" (aid status unknown) and "they list no aid for students
     from abroad" (any other status);
   - `no_admission_data`: any other university without a band (no admit rate).
5. **Order inside a band:** subject rank (lower first; no subject rank last), then aid for international
   students (yes, need-aware, merit, none, unknown), then the higher international admit rate (the same
   rate as the band, published or estimated; none last), then overall QS rank, then name, then id.
6. **Ten cards: 3 reach, 4 target, 3 safety.** **Decided (2026-11-22):** reach takes reach entries first
   and at most **one far reach**. Still short, it is filled from target, then safety, and only then from a
   second far reach. Far-reach universities never fill other groups. A short group is filled from the
   nearest group (reach from target then safety; target from reach then safety; safety from target then
   reach), each card keeps its own band, and the list says so. Fewer than ten fit: the list is shorter and
   says so.

## 3. What each card says

Band; subject and rank ("#12 in Computer Science, QS 2026"); SAT position (below, inside or above the
university's range with both numbers, "no SAT range listed", or "Compared using your ACT 31" when the
student has only an ACT); where the student's academics stand ("Below most admitted students" under the
25th percentile, "Inside the middle 50%", "Above most admitted students" from the 75th); aid for
international students; yearly cost against the budget; admit rate (with ≈ and "estimated from the overall
rate" when estimated); up to two suggested programs (a program matches when its major text matches the
student's, or both map to the same QS subject); Add and Add all. The footnote names the ranking used: QS
subject rankings 2026, or the overall QS World University Rankings 2027 when no major mapped.

**Decided (2026-11-22): aid status**, the first rule that applies:

1. need-blind, or international aid plus meets full need: **yes**;
2. need-aware policy: **need-aware**;
3. international aid: **yes**;
4. merit aid: **merit** ("Merit aid (check it is open to international students)");
5. aid details but none of these: **none listed**;
6. else **unknown**.

## 4. Why these fit you

**Decided (2026-11-22).** The one AI step, only when the student presses the button: one call writes one
sentence per card (up to 10), cached for the same list, profile and language, and counted as one unit of
the daily limit (a failed call gives it back).

- **Facts it sees.** Per card: name, country, band, QS rank, subject and subject rank, SAT position with the
  student's score and the university's SAT range (or the ACT score), aid status, admit rate and whether it
  is estimated, cost and cost against budget, suggested programs, and the fit's first two strengths and
  watch-outs. For the student: the stated majors (anonymized and redacted), the Academics score and the
  budget. Never essay or letter text, activities, or the student's name; no fit score.
- **Number check.** For each card the server collects the numbers in that card's facts and the student
  facts (digits with commas removed and trailing dots stripped). A line with any other number (a made-up
  admit rate, another card's rank) is replaced by an empty line, and the card shows no line. A missing
  card is a failed call.
- The footnote says: "Why these fit you lines are written by Naseeb AI from these facts only."

## 5. Calibration

**Decided (2026-11-22).** Five sample profiles run against one small catalogue in
`test_college_match_rules.py` (`SampleProfileTests`). Catalogue (target country US): MIT, Ohio State, six
open CS colleges, three selective CS universities (SAT required), one elite CS university, one merit-only and
one no-aid-details CS college, and one engineering school ranked only in the broad area.

| Profile | Reach / target / safety | Notes |
|---|---|---|
| No SAT | 3 / 4 / 3 (one far reach) | filled_from x2, test_needed (3) |
| SAT 1500, needs a scholarship, $10k budget | 3 / 4 / 3 (one far reach) | filled_from x2, aid_unknown (1), no_intl_aid (1) |
| "Engineering" | 0 / 0 / 1 | short_list; hint broad_area |
| "информатика" | 3 / 4 / 3 | filled_from |
| "Undecided" | 1 / 0 / 1 (overall QS rank) | short_list; hint pick_major |

The same 12 universities inserted in reverse order give the same ids in the same order, and tied keys
are broken by name, then id.
