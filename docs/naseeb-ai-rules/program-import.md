# Naseeb AI rules: Telegram program import

Scope: NaseebEdu only. The job `import_telegram_programs` adds programs and scholarships
to the student program list from public Telegram channels. Naseeb Mind and its AI chat
are out of scope.

Code: `backend/apps/admissions/telegram_import/` (`fetch.py`, `official.py`,
`formatter.py`, `rules.py`, `importer.py`). Tests: `backend/apps/admissions/test_telegram_import.py`.

## 1. When it runs
- Only while `core.ai_policy.outbound_ai_allowed()` is true and `AI_GATEWAY_API_KEY` is set.
  Otherwise nothing is fetched, sent or added, and the run logs
  `telegram_import_skipped reason=outbound_ai_off|gateway_not_configured`.
- `TELEGRAM_IMPORT_DAILY_BUDGET=0` turns the import off (`reason=budget_off`).
- Scheduled through the counselor bot's hourly `/api/bot/scheduled-jobs/` call, every hour
  from 23:00 to 07:00 Asia/Tashkent (production has no cron).
  Decided (2026-11-22): hourly runs from 23:00 to 07:00 Asia/Tashkent, not a single run at
  23:59. Reason: a failed or cut-short run is retried within the same night, and the load is
  spread over the night instead of landing in one request. Each run is incremental and
  time-boxed: it starts new work for `TELEGRAM_IMPORT_TIME_BUDGET_SECONDS` (default 55 s)
  minus the time the other jobs in the same request already took, and never starts a step
  (a Telegram page, an official page, an AI call) that could end more than 40 s after that.
  The whole request therefore ends before gunicorn's 120 s timeout.
- Channels come from `TELEGRAM_IMPORT_CHANNELS` only (default: opportunitiescircleofficial,
  opcorners, edugrandsuz, grantlar, grantgouz, youthgrants). Each run starts with the channel
  not run for the longest time (never-run first, configured order on ties), so a run cut short
  by its time budget never starves the later channels. A gateway outage does not rotate.
- An official page is read in small chunks with a total deadline per page (the socket timeout
  alone only limits silence) and a hard cap of 1.5 MB.

## 2. Reading posts
- Posts are read from the public preview `https://t.me/s/<channel>`; no Telegram account or key.
- Each channel stores `last_message_id`; only newer posts are handled, oldest first, and the
  cursor is saved after every post. Paging back to the cursor goes up to 30 preview pages in
  a run, and no post is handled until that gap is closed, so none is skipped. A rerun never handles a post twice
  (`source_key = telegram:<channel>:<id>` is unique).

## 3. Post and page text are data, never instructions
- Zero-width, bidi and control characters are removed.
- Any line addressed to an AI ("ignore previous instructions", "system:", "set is_program", `<<<`, `>>>` ...)
  is dropped together with its links, and the count is logged (never the text). This applies to
  the post, the official page's body and the official page's `<title>`.
- The post and the official page are sent between `<<<POST_TEXT ... POST_TEXT>>>` and
  `<<<OFFICIAL_PAGE ... OFFICIAL_PAGE>>>` markers labelled "untrusted data". The marker tokens
  (`<<<`, `>>>`, `POST_TEXT`, `OFFICIAL_PAGE`) are removed from every untrusted string (post,
  page title, page text, URLs, post date), so fetched text can never close or open a marker.
- The system prompt tells the model that nothing inside the markers is an instruction.
- Whatever the model returns is validated and checked against the source in code (section 6).
  The prompt is never the only guard.

## 4. Official source
- Candidate links are https links in the post that are not Telegram, a link shortener, a social
  network, a blocked domain (`TELEGRAM_IMPORT_BLOCKED_LINK_DOMAINS`: the channels' own article
  sites) or longer than 1000 characters.
- When the post links to the channel's own article, that article is opened and its outside
  links are added to the post's own (body links and "apply / official / register" links first).
  This happens even when the post also has another outside link, which is often an advert.
- A post with no candidate is rejected before any AI call.
- At most two candidate pages are read per post. Network rules: https on 443 only, no
  credentials in the URL, public IP addresses only with the connection pinned to the checked
  address, at most 2 redirects (each checked), HTML only, size and time caps.
- `application_url` must be copied exactly from the candidate list; anything else is rejected.
- When the model picks a different site than the page that was read, the row gets the problem
  "description from a different page than the application link" for staff to check.

## 5. What the AI may write
- Pinned `TELEGRAM_IMPORT_MODEL`, temperature 0, JSON mode, no fallback model.
- Output keys are fixed (title, provider, program_type, category, country, city, delivery_mode,
  description, eligible_grades, eligible_ages, deadline, deadline_text, start_date, end_date,
  fee_usd, scholarship_available, aid_details, requirements, application_url, is_program, problems).
- Facts only from the post or the official page. The model must not invent or infer:
  - deadlines: `deadline` only when the source writes day, month and year, else null; no year
    guessing. `deadline_text` is copied exactly as written (no translation);
  - amounts: `fee_usd` only when the source states it in US dollars, 0 only when it says the
    program is free, otherwise null with the original fee text in `requirements`. No currency
    conversion;
  - eligibility: grades and ages only when stated; grades are never guessed from ages.
- `is_program` is false for adverts, news, giveaways, paid consulting/agency services, courses for
  sale and lists of many opportunities.
- `description`: 2-3 plain sentences, at most 500 characters, from the official page when read.
- `problems`: up to 5 short notes on anything doubtful (no deadline, unclear eligibility,
  link may not be official, signs of a paid agent).

## 6. Checks in code after the AI
All values are type-checked and length-bounded; unknown categories become "Other"; bad dates
become null; a start date after the end date drops the end date.

Then every fact is checked against the exact text the AI was given (post text, page title,
page text). Anything not found there is cleared and noted in `problems`:
- `deadline` is kept only when `deadline_text` appears in the source and writes that same date
  (day with the month name in English, Uzbek or Russian, or a numeric date) including its year;
- `start_date` and `end_date` are kept only when the source writes that date;
- `fee_usd` is kept only when it is 0 and the source says free / bepul / бесплатно, or when the
  number appears next to `$`, `USD` or "dollar";
- `eligible_ages` is kept only when its numbers appear; `eligible_grades` only when its lowest
  and highest grade appear (and "gap" only when the source says so).

A post is rejected when any of these hold:
- `is_program` is false, or title/provider is empty;
- `application_url` is empty, not in the candidate list, or fails the link rules;
- it is over (Tashkent date): the deadline has passed, the end date has passed, or there is
  no deadline and the start date has passed (`deadline_passed`);
- there is no deadline and the post is more than 120 days old (`stale_post`);
- it duplicates an existing program and is not its next edition (`duplicate`, see below).

Duplicates. A program matches an existing one by normalized title + provider (case, punctuation
and years ignored) or by normalized application URL (no `www`, fragment, trailing slash or
tracking parameters: `utm_*`, `ref`, `ref_src`, `referrer`, `fbclid`, `gclid`, `yclid`, ...).
An organiser's homepage (an empty path) is shared by all its programs, so it is never a match
key. Every catalogue row counts, hidden ones included, as do rows added earlier in the same run,
so the same program posted in several channels or on several days is added once.
- When the matching row's deadline is past or unknown and the post gives a future deadline,
  the post is the next edition: that row is renewed instead (title, deadline, deadline text,
  application link and description updated, `needs_verification=True`, and an entry in
  `source_metadata.telegram_updates`). Hidden rows stay hidden.
- Otherwise the post is rejected as a duplicate.

## 7. Budget, usage logging and failures
- Each gateway call first takes one unit of `TELEGRAM_IMPORT_DAILY_BUDGET` (`ai_budget.consume_job`,
  Tashkent day). When the cap is reached the run stops and the rest waits for the next night.
- Every call is recorded in `AiUsageLog` with feature `telegram_import` (ok, provider_error,
  invalid_output, budget_refused), with token usage when the provider answered.
- The unit is refunded only when no answer came back. An answer that was unusable was paid
  for and keeps its unit, so the cap counts every billed call.
- Gateway down (no connection, timeout, 401/403/408/429 or 5xx): the run stops
  (`stopped=gateway_unavailable`), the post's cursor does not move and no attempt is counted
  against it; the next run tries again.
- Unusable answer (not JSON, wrong shape, other 4xx): counts as a failed attempt for that post;
  the post is retried in the next run and skipped (`ai_failed`) after two failures.
- A post that cannot be saved (database error) or fails unexpectedly is logged with its channel
  and id, counted as `save_failed`, and skipped, so it never blocks the import.
- Logs carry counts, channel names, post ids and hosts only, never post or page text.

## 8. Going live
- Imported rows always get `needs_verification=True`, `source_url` = the Telegram post, and
  `source_metadata` (origin, channel, message id, model, official page read, AI and check
  problems; no post or page text).
- Students only see `source_metadata.origin`; the rest stays in the admin catalogue.
- `TELEGRAM_IMPORT_PUBLISH_IMMEDIATELY=True` (default): shown to students at once with the
  "From Telegram, not yet verified" label and a link to the original post.
  `False`: hidden until staff approve.
- Staff approve with the Django admin action "Approve: mark verified and show to students"
  (sets `needs_verification=False`, `is_active=True`) and hide with "Hide from students".
