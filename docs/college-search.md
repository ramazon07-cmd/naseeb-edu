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
| `price` | `all`, `budget`, `25000`, `40000` | `all` | Net price per year at most the student's budget or the given USD cap. Universities without a net price are left out when it is set. |
| `aid` | comma-separated subset of `offers_need_based_aid`, `offers_merit_aid`, `offers_international_aid`, `meets_full_need` | empty | Every listed flag must be true. |
| `bands` | comma-separated subset of `reach`, `target`, `safety`, `unknown` | absent (every band) | Admission band for the student. `unknown` is a university with no band (no admission data to place it). Absent means every band; present but empty (`bands=`) means none. The frontend omits it while every box, `unknown` included, is ticked, and otherwise sends exactly the ticked set. |
| `test_optional` | `true`, `false` | `false` | Test-optional universities only. |
| `sat_fit` | `true`, `false` | `false` | The student's SAT meets the listed minimum, or the university is test-optional without one. |
| `public` | `true`, `false` | `false` | Public universities only. |
| `region`, `size`, `focus`, `research` | a QS classification value (up to 40 characters) as `facets.qs` lists it | empty | QS classifications. |
| `sort` | `ranking`, `price`, `deadline`, `acceptance`, `fit` | `ranking` | `ranking` best first; `price` lowest net price first; `deadline` nearest application deadline first; `acceptance` highest acceptance rate first; `fit` best fit first. Missing values sort last. Until the student's research profile is complete, `fit` keeps the ranking order. |
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
  "facets": FACETS
}
```

`next` is the next page number, or `null` on the last page. `facets` is present
only with `facets=true`. With `ids`, the response is only `{"results": [ROW, ...]}`.

### Row

The slim list row (`UniversityRowSerializer`): `id`, `name`, `city`, `country`,
`institution_type`, `ranking`, `ranking_label`, `qs_data` (list keys and the
indicator scores only), `acceptance_rate`, `sat_min`, `sat_max`,
`test_optional`, `net_price_usd`, `application_deadline`,
`scholarship_deadline`; plus `programs` (`[{name, canonical_major}]`, open
programs international students can apply to) and, once the student's research
profile is complete, `fit`. The full record is `GET /api/universities/{id}/`.

```json
"fit": {
  "match_score": 78,
  "match_label": "Good match",
  "admission_band": "target",
  "score_breakdown": {"academic": 40, "preferences": 18, "financial": 12, "profile_strength": 8},
  "reasons": [{"code": "sat_in_range", "params": {"sat": 1450, "min": 1400, "max": 1550}, "text": "SAT 1450 fits the 1400–1550 catalog range"}],
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

### Facets

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

`bands` counts are for the student and are all 0 until the research profile is
complete; `unknown` counts the universities with no band.

## Performance

Scoring the catalogue is needed only to sort by fit, filter by band or count
bands. The first such request for a student builds the fit map and caches it per
student, profile answers and catalogue version; later pages reuse it. Numbers
and the Redis requirement are in [scaling.md](scaling.md#college-search-measured).
