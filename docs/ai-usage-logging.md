# AI usage logging

Every paid AI call, and every call that was refused or answered locally instead, writes one row to `AiUsageLog`. The rows feed the financial model: real tokens per task instead of estimates.

## What is stored

`feature` (assistant, essay_coach, recommendation_letter, education_match), `provider` (gateway or groq), `model` the provider reports it used, `status`, input / output / cached-input / reasoning / total tokens, `latency_ms`, `language`, `fallback_used`, `role`, and the user and school (both set to null if deleted).

Statuses: `ok`; `provider_error` (no usable answer from the provider, no tokens); `invalid_output` (the provider answered and was billed, but the answer was unusable); `budget_refused` and `local_fallback` (no provider call, zero tokens). A `local_fallback` row means a request was answered locally because AI was off, not entitled, or not configured.

Tokens come from the provider's `usage` object. If a reply has none, they are estimated from characters (chars / 4) and `usage_estimated` is true. `fallback_used` is true when the reply names a different model than the one requested, which is the gateway's own fallback (nano). It is a heuristic on the model name.

## What is never stored

Prompts, essay text, student facts, drafts, replies and any other content. Only counts.

Cached education-match answers make no provider call and write no row. Education match has its own daily caps (`EDUCATION_MATCH_AI_*`), charged once per real provider call.

## Guard rails and checks

- Every outbound feature (assistant, essay coach, letter suggestions, education match) is gated by `OUTBOUND_AI_ENABLED` through `core.ai_policy.outbound_ai_allowed()`. With it off nothing leaves the server and each feature serves its local fallback.
- Non-streaming calls (letter suggestions, education match) go through `ai_http.post_json`: one retry (`AI_PROVIDER_RETRIES`) on timeout, connection error, 429 or 5xx, never on other 4xx. The budget is charged once per call, not per attempt.
- Untrusted text (drafts, profile facts, task titles, assessment data) is sent between `<<<NAME` / `NAME>>>` markers; the marker characters are stripped from the data so it cannot close its own block.
- `python manage.py ai_eval` runs fixed sample inputs, including injection attempts and hostile model output, through each feature's validation layer. No provider call, exits non-zero on a failure. `--live` adds a few real calls, only with `OUTBOUND_AI_ENABLED` on and the keys set; they cost tokens and are not stored in `AiUsageLog`.
- Red-team tests: `apps/admissions/tests/test_ai_redteam.py` (mocked provider).

## Reading it

- Admin API, support staff only: `GET /api/admin/ai-usage/?days=30&feature=essay_coach`. The `tokens` object has per-feature, per-school and per-day aggregates: calls, paid and ok calls, error and fallback rates, and sum / average / p50 / p90 / max of input, output, cached, reasoning and total tokens.
- Command: `python manage.py ai_usage_report --days 30 [--feature F] [--by feature|school|day] [--csv out.csv] [--price-input USD_PER_1M --price-output USD_PER_1M]`. No default prices: pass the rates from your gateway dashboard. Cost uses paid calls only (errors count, refusals do not).
- Health page (ops staff): `GET /api/admin/health/` has an `ai` section for the last 24 hours: whether outbound AI is on, and per feature the calls, error rate, latency p50 / p95, tokens, refused / local counts and, when `AI_PRICE_INPUT_USD_PER_1M` and `AI_PRICE_OUTPUT_USD_PER_1M` are set, estimated cost. Cached for a minute. The report command also reads those two settings when `--price-*` is not passed, and prints latency p50 / p95 and the error rate.
- Retention: `python manage.py ai_usage_report --purge-older-than 365` deletes older rows. Run it on a schedule.

## Cost per student per month

1. Run the report over a full pilot month with `--by feature`, plus prices.
2. Divide each feature's `cost_usd` by the number of active students who used it, or use `cost_per_paid_call_usd` times the calls per student per month you expect.
3. Add the share of `provider_error` / `invalid_output` calls: they cost money and the student retries.
4. Check `estimated_calls`: if it is not near zero the provider is not returning usage and the tokens are estimates.
