# AI usage logging

Every paid AI call, and every call that was refused or answered locally instead, writes one row to `AiUsageLog`. The rows feed the financial model: real tokens per task instead of estimates.

## What is stored

`feature` (assistant, essay_coach, recommendation_letter, education_match), `provider` (gateway or groq), `model` the provider reports it used, `status`, input / output / cached-input / reasoning / total tokens, `latency_ms`, `language`, `fallback_used`, `role`, and the user and school (both set to null if deleted).

Statuses: `ok`; `provider_error` (no usable answer from the provider, no tokens); `invalid_output` (the provider answered and was billed, but the answer was unusable); `budget_refused` and `local_fallback` (no provider call, zero tokens). A `local_fallback` row means a request was answered locally because AI was off, not entitled, or not configured.

Tokens come from the provider's `usage` object. If a reply has none, they are estimated from characters (chars / 4) and `usage_estimated` is true. `fallback_used` is true when the reply names a different model than the one requested, which is the gateway's own fallback (nano). It is a heuristic on the model name.

## What is never stored

Prompts, essay text, student facts, drafts, replies and any other content. Only counts.

Cached education-match answers make no provider call and write no row.

## Reading it

- Admin API, support staff only: `GET /api/admin/ai-usage/?days=30&feature=essay_coach`. The `tokens` object has per-feature, per-school and per-day aggregates: calls, paid and ok calls, error and fallback rates, and sum / average / p50 / p90 / max of input, output, cached, reasoning and total tokens.
- Command: `python manage.py ai_usage_report --days 30 [--feature F] [--by feature|school|day] [--csv out.csv] [--price-input USD_PER_1M --price-output USD_PER_1M]`. No default prices: pass the rates from your gateway dashboard. Cost uses paid calls only (errors count, refusals do not).
- Retention: `python manage.py ai_usage_report --purge-older-than 365` deletes older rows. Run it on a schedule.

## Cost per student per month

1. Run the report over a full pilot month with `--by feature`, plus prices.
2. Divide each feature's `cost_usd` by the number of active students who used it, or use `cost_per_paid_call_usd` times the calls per student per month you expect.
3. Add the share of `provider_error` / `invalid_output` calls: they cost money and the student retries.
4. Check `estimated_calls`: if it is not near zero the provider is not returning usage and the tokens are estimates.
