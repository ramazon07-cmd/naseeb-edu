# College Search API

`GET /api/college-search/` returns one page of the university catalogue,
filtered, sorted and counted on the server, with the signed-in student's fit on
every row. The frontend builds the query in `frontend/src/lib/college.js`
(`collegeSearchQuery`); the backend is `backend/apps/admissions/college_search.py`
(`CollegeSearchParams`, `college_search`).

Only student accounts may call it: other roles get `403`, anonymous requests `401`.

## Query parameters

Every parameter is optional. A parameter the endpoint does not know is a `400`
naming it (`{"<name>": ["Unknown parameter."]}`), as is any value outside the
allowed set below.

| Parameter | Allowed values | Default | Meaning |
|---|---|---|---|
| `search` | up to 100 characters; the first 4 whitespace-separated terms count | empty | Every term must match the university's name, city or country. Matching ignores case and accents (`Sao Paulo` finds `São Paulo`), transliterates Cyrillic (`Гарвард` finds Harvard) and knows country spellings (`US`, `USA` and `United States` are one country; so are `Turkey`, `Türkiye` and `Turkiye`). |
| `country` | a country name as `facets.countries` lists it | empty (all) | One country, under any of its catalogue spellings. |
| `price` | `all`, `budget`, `25000`, `40000` | `all` | Yearly cost (see [Price](#price)) at most the student's budget or the given USD cap. Universities without a known cost stay in the results. `budget` without a budget in the profile has no cap (see [Budget rule](#budget-rule)). |
| `aid` | comma-separated subset of `offers_need_based_aid`, `offers_merit_aid`, `offers_international_aid`, `meets_full_need` | empty | Every listed flag must be true. |
| `bands` | comma-separated subset of `reach`, `target`, `safety`, `unknown` | absent (every band) | Admission band for the student. `unknown` is a university with no band (no admission data to place it). Absent means every band; present but empty (`bands=`) means none. The frontend omits it while every box, `unknown` included, is ticked, and otherwise sends exactly the ticked set. |
| `test_optional` | `true`, `false` | `false` | Test-optional universities only. |
| `sat_fit` | `true`, `false` | `false` | The student's SAT meets the listed minimum, or the university is test-optional without one. |
| `public` | `true`, `false` | `false` | Public universities only. |
| `region`, `size`, `focus`, `research` | a QS classification value (up to 40 characters) as `facets.qs` lists it | empty | QS classifications. |
| `sort` | `ranking`, `price`, `deadline`, `acceptance`, `fit` | `ranking` | `ranking` best first; `price` lowest yearly cost (see [Price](#price)) first; `deadline` nearest application deadline first; `acceptance` highest acceptance rate first; `fit` best fit first. Missing values sort last. Until the student's research profile is complete, `fit` keeps the ranking order. |
| `page` | 1–1000 | 1 | Page number. |
| `page_size` | `10`, `25`, `50`, `100` | `10` | Rows per page; anything else is a `400`. |
| `facets` | `true`, `false` | `false` | Add the facet counts to the response. |
| `ids` | comma-separated university ids, at most 100 | empty | Return exactly these universities (the student's list, an open university page), ranking order, no paging. The other filters are ignored. |

## Response

```json
{
  "count": 1506,
  "page": 1,
  "page_size": 10,
  "next": 2,
  "results": [ROW, ...],
  "unpriced_count": 1318,
  "facets": FACETS
}
```

`next` is the next page number, or `null` on the last page. `unpriced_count` is
how many of the `count` matching universities have no known cost (all pages, not
just this one). `facets` is present only with `facets=true`. With `ids`, the response is only `{"results": [ROW, ...]}`.

### Row

The slim list row (`UniversityRowSerializer`): `id`, `name`, `city`, `country`,
`market`, `institution_type`, `ranking`, `ranking_label`, `qs_data` (list keys
and the indicator scores only), `acceptance_rate`, `sat_min`, `sat_max`,
`test_optional`, `net_price_usd`, `intl_cost_usd`, `offers_international_aid`,
`application_deadline`, `scholarship_deadline`; plus `programs` (`[{name, canonical_major}]`, open
programs international students can apply to) and, once the student's research
profile is complete, `fit`. The full record is `GET /api/universities/{id}/`.

```json
"fit": {
  "match_score": 78,
  "match_label": "Good match",
  "admission_band": "target",
  "score_breakdown": {"academic": 40, "preferences": 18, "financial": 12, "profile_strength": 8},
  "reasons": [{"code": "sat_in_range", "params": {"score": 1450, "min": 1400, "max": 1550}, "text": "SAT 1450 fits the 1400–1550 catalog range"}],
  "gaps": [{"code": "...", "params": {}, "text": "..."}]
}
```

* `match_score` is 0–100 and is not an admission probability.
* `admission_band` is `reach`, `target`, `safety`, or `null` when the catalogue
  has no admission data for the university; `null` rows are what `bands=unknown`
  selects.
* `score_breakdown` parts are out of 48, 22, 20 and 10.
* `reasons` (up to 5) and `gaps` (up to 4) are `{code, params, text}`: `code` is
  stable, `params` fills the translated message, `text` is the English sentence.
  The frontend renders them with `fitReasonText` (`frontend/src/lib/fitReasons.js`)
  from the uz/ru/en messages in `frontend/src/translations/fitReasons.js`, and
  falls back to `text` for a code it does not know.
* Test scores: the higher of SAT and ACT against the catalogue range counts. The
  English score is IELTS, or TOEFL, Duolingo, PTE or Cambridge converted to an
  IELTS band by each test owner's published concordance.
* A factor with no data (no test range, no cost, no aid details) is left out of
  the score rather than guessed, and half its weight is taken off, so a row
  without data never outscores the same row with data that fits.

## Price

`cost_of_attendance` (Python) and `COST` (the SQL annotation the `price` filter
and sort use) give the yearly cost a student from abroad pays:

* **US universities** (`market = "us"`): `intl_cost_usd`, the cost of attendance
  for an international student (out-of-state tuition and fees plus on-campus
  room, board, books and other costs, from the College Scorecard snapshot).
  Scorecard's `net_price_usd` is an average for domestic aid recipients, so it is
  used instead only where `offers_international_aid` is true.
* **Everywhere else**: `net_price_usd`.

The fit's financial reasons say which one they used (`cost_*` or
`net_after_aid_*` codes). The UI (`priceInfo` in `frontend/src/lib/college.js`)
shows a US row's `intl_cost_usd` as "Estimated cost for international students"
(MIT: about $85,960, not its $20,111 domestic net price), with `net_price_usd`
as a secondary "after aid" line only when `offers_international_aid` is true;
other rows show their net price as before.

### Budget rule

* **Unknown cost stays.** Every price filter (`budget`, `25000`, `40000`) keeps
  universities with no known cost: the filter is `cost IS NULL OR cost <= cap`.
  No published price is not "too expensive". `unpriced_count` in the response
  says how many such rows the current result holds, and the page notes
  "N universities have no published price" under a price filter.
* **No budget, no cap.** `price=budget` when the profile has no budget (empty or
  0) applies no cap at all, so the list is never emptied by a missing answer. The
  page keeps "Within budget" selectable and shows "Add your budget in your
  profile to filter by price" with a link to the profile.
* **Price sort** puts universities without a cost last, after every priced one.
* **Fit is unchanged.** The fit's financial factor still treats an unknown cost
  as missing data (`cost_missing` gap, the missing-weight path above), not as
  within budget.

## Facets

Counts over the whole catalogue (the current filters do not change them):

```json
{
  "countries": {"United States": 1000, "United Kingdom": 90},
  "bands": {"reach": 120, "target": 300, "safety": 200, "unknown": 886},
  "aid": {"offers_need_based_aid": 0, "offers_merit_aid": 0, "offers_international_aid": 0, "meets_full_need": 0},
  "test_optional": 0,
  "sat_fit": 0,
  "public": 0,
  "qs": {"region": {"Europe": 0}, "size": {}, "focus": {}, "research": {}}
}
```

`bands` counts are for the student. `unknown` counts the universities with no
band; until the research profile is complete that is every university and
`reach`, `target` and `safety` are 0.

## Search folding

`University.search_text` (migration `0070_university_search_text`) holds the
name, city and every catalogue spelling of the country, lower-cased with accents
removed (`backend/apps/admissions/search_text.py`). `University.save()` keeps it
current; bulk writes that skip `save()` set it themselves (`load_qs_rankings` for
the rows it creates, `load_college_scorecard` for the rows whose city it fills).
A search term is folded the same way and, when Cyrillic, transliterated to a few
Latin spellings, and each term must be contained in `search_text`. The catalogue
list (`/api/universities/?search=`) uses the same matching (`listing.py`).

## Performance

Scoring the catalogue is needed only to sort by fit, filter by band or count
bands. The first such request for a student builds the fit map and caches it per
student, profile answers and catalogue version; later pages reuse it. Numbers
and the Redis requirement are in [scaling.md](scaling.md#college-search-measured).
