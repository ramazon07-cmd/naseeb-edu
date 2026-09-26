# Essay Lab — build spec (v1)

Status: approved in eng review on 2026-09-24. This file is the contract between the backend and frontend work.

## Product decisions
- Students only. Counselor and organisation features stay as they are.
- English only.
- Rich text like Google Docs: bold, italic, underline, strikethrough, heading 1/2, bullet list, numbered list,
  dash list, block quote, undo/redo, clear formatting, keyboard shortcuts, markdown-style shortcuts ("- ", "1. ", "> ").
- Depth checks: no daily quota. Invisible guard: at most 1 per 15 s and 120 per hour per student, plus a global
  daily budget (`ESSAY_COACH_DAILY_BUDGET`, default 5000 checks/day). The Coach asks questions and never rewrites.
- Autosave like Google Docs: local-first, then synced to the server in the background.
- Essay types: `personal_statement`, `supplement`, `scholarship`, `free_writing`. Supplements carry a student-typed
  question (stored in `prompt`), an optional university name and an optional word limit.

## Data model (backend/apps/admissions/models.py, one migration)
`Essay` gains:
| field | type | notes |
|---|---|---|
| `essay_type` | CharField(32), choices above, default `personal_statement` | |
| `folder` | FK `EssayFolder`, null, `SET_NULL` | |
| `university_name` | CharField(220), blank | free text for supplements |
| `word_limit` | PositiveIntegerField, null | |
| `doc` | JSONField, null | ProseMirror JSON. `null` = rebuild from `content` |
| `save_seq` | PositiveIntegerField, default 0 | optimistic concurrency counter |
| `last_client_save_id` | CharField(64), blank | idempotent retries |
| `word_count` | PositiveIntegerField, default 0 | derived |
| `preview` | CharField(200), blank | derived, first ~160 chars |
| `last_cursor` | PositiveIntegerField, null | ProseMirror position |
| `last_edited_at` | DateTimeField, null | set by autosave |
| `trashed_at` | DateTimeField, null | soft delete, restorable |
`prompt` becomes `blank=True` (free writing has no question).
The migration backfills `word_count` and `preview` from `content` for existing rows.

New `EssayFolder(TimeStampedModel)`: `student` FK StudentProfile (CASCADE, related `essay_folders`),
`name` CharField(120), `parent` FK self null (one level of nesting only), `position` PositiveIntegerField.
Ordering `position, id`. Index `(student, parent, position)`.

New `EssayCheckpoint`: `essay` FK (CASCADE, related `checkpoints`), `doc` JSON, `content` Text, `word_count`,
`reason` CharField(`auto`, `depth_check`, `restore`, `manual`), `label` CharField(120) blank, `created_at`.
Ordering `-created_at`. **Separate from `EssayRevision`**, so counselor-visible `version` and revision chips don't change.
Keep at most 200 checkpoints per essay (delete the oldest `auto` ones first).

New `EssayDepthCheck`: `essay` FK (CASCADE, related `depth_checks`), `save_seq` (the seq it ran on), `result` JSON,
`model` CharField, `created_at`. Keep the latest 20 per essay.

## Legacy compatibility (the only edits to existing essay code)
- `EssaySerializer` (`/api/essays/`): switch to explicit read-only for the new fields. Make `doc`, `save_seq`,
  `last_client_save_id`, `last_cursor` write-protected **and not returned** (exclude them). Add `doc`, `preview`,
  `folder` to the organisation strip list. Response shape for counselors is otherwise unchanged.
- `EssayViewSet.perform_update`: when `content` changes through the legacy API → set `doc=None`, `save_seq += 1`,
  recompute `word_count`/`preview`, inside `transaction.atomic()` + `select_for_update()` (also fixes audit BE-M8).
- `EssayViewSet.get_queryset`: exclude `trashed_at__isnull=False`.
- The student Essay Lab page stops using the legacy `ResourceSection` form.

## Plain-text derivation (`essay_lab/doc.py`)
- Allowed nodes: `doc, paragraph, heading(level 1|2), bulletList, orderedList, listItem, blockquote, text, hardBreak`.
  Allowed marks: `bold, italic, underline, strike`. Anything else → 400 `invalid_doc`.
- Serialized JSON size ≤ 256 KB → otherwise 413 `doc_too_large`. Nesting depth ≤ 12.
- Text: block nodes joined with `\n\n`; list items prefixed `• ` / `1. ` / `– ` (dash list = bulletList with
  `attrs.style == "dash"`); `hardBreak` → `\n`. `word_count` = count of `\S+` runs in the text.
- `doc_from_text(content)`: splits on blank lines into paragraphs (used when `doc` is null).

## API (student only, prefix `/api/essay-lab/`)
Auth: existing JWT. Non-students → 403 `students_only`. Other students' ids → 404.
Errors: `{"detail": str, "code": str}`.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `essays/?folder=<id\|none>&type=&q=&trashed=0\|1` | | `[EssaySummary]` (not paginated, max 500; no doc/content) |
| POST | `essays/` | `{title, essay_type, prompt?, university_name?, word_limit?, folder?}` | `EssayDetail` 201 |
| GET | `essays/{id}/` | | `EssayDetail` |
| PATCH | `essays/{id}/` | `{title?, prompt?, university_name?, word_limit?, folder?, essay_type?}` (metadata only) | `EssayDetail` |
| PUT | `essays/{id}/autosave/` | `{doc \| (ops, doc_hash), base_seq, client_save_id, cursor?}` | `{save_seq, saved_at, word_count, doc_hash}` 200, or 409 |
| POST | `essays/{id}/trash/` · `restore/` | | `EssaySummary` |
| DELETE | `essays/{id}/` | only if trashed | 204 |
| POST | `essays/{id}/duplicate/` | `{title?, university_name?, folder?}` | `EssayDetail` 201 |
| GET | `essays/{id}/checkpoints/` | | `[{id, reason, label, word_count, created_at}]` |
| GET | `essays/{id}/checkpoints/{cid}/` | | `{…, doc}` |
| POST | `essays/{id}/checkpoints/` | `{label?}` | manual checkpoint 201 |
| POST | `essays/{id}/checkpoints/{cid}/restore/` | `{base_seq}` | `EssayDetail` (a `restore` checkpoint of the current text is made first) |
| POST | `essays/{id}/depth-check/` | `{base_seq}` | `DepthCheck` 200 · 409 stale · 429 `slow_down` · 503 `coach_unavailable` |
| GET | `essays/{id}/depth-check/latest/` | | `DepthCheck` or 204 |
| GET/POST | `folders/` | `{name, parent?}` | `[Folder]` / `Folder` |
| PATCH/DELETE | `folders/{id}/` | `{name?, parent?}` | delete moves its essays to "no folder" and its subfolders up |
| PUT | `folders/order/` | `{parent: id\|null, ids: [id…]}` | `[Folder]` (bulk position update in one transaction) |

`EssaySummary`: `id, title, essay_type, prompt, university_name, word_limit, folder, word_count, preview,
last_edited_at, updated_at, trashed_at, status`.
`EssayDetail`: summary + `doc` (rebuilt from `content` when null), `save_seq, last_cursor`.
`Folder`: `id, name, parent, position, essay_count`.

### Autosave rules
1. `select_for_update()` the essay inside `transaction.atomic()`.
2. If `client_save_id == last_client_save_id` → return 200 with the current seq (the retry already landed).
3. If `base_seq != save_seq` → 409 `{code:"conflict", save_seq, doc, saved_at}`.
4. Validate `doc` → derive `content`, `word_count`, `preview`; `save_seq += 1`; set `last_cursor`, `last_edited_at`,
   `last_client_save_id`; `update_fields=[…]`.
5. Automatic checkpoint when the newest checkpoint is older than 10 minutes **and** the text changed since then.
6. Throttle scope `essay_autosave`: a fixed-window counter (cache `incr`), 1200 per 10 minutes per user. It doesn't use
   DRF's list-of-timestamps history.
7. Query budget: ≤ 4 queries (asserted in tests), 5 when a checkpoint is written.
8. Delta saves: instead of `doc` the client may send `ops` over the stored doc's top-level blocks
   (`{at, delete, insert}` splices and `{at, patch: [prefix, suffix, text]}` patches of one block's canonical JSON,
   ascending by `at`) and `doc_hash`, the sha256 of the resulting doc in canonical JSON (sorted keys, no spaces,
   ASCII escapes). Under the row lock and after the seq check the server applies the ops, checks the hash, then
   validates and derives as for a full doc. Ops that don't fit or a hash mismatch → 409
   `{code:"resync", save_seq, doc}` and the client resends in full. A delta that changes nothing writes nothing.
   Shared cases: `essay_lab/fixtures/doc_delta_cases.json`.

### Depth check
- Requires `base_seq == save_seq` (the client saves first). Creates a `depth_check` checkpoint.
- AI call: non-streaming JSON mode through `settings.AI_GATEWAY_URL` / `AI_GATEWAY_API_KEY`, model
  `settings.ESSAY_COACH_MODEL` (default = `AI_ASSISTANT_MODEL`), timeout `ESSAY_COACH_TIMEOUT_SECONDS` (default 40).
  Essay text goes through `redact_pii` and sits inside a delimited block marked as untrusted data.
- Returned and validated shape (anything else is dropped):
```json
{"summary": "str ≤ 400", "strengths": ["quote-anchored str"],
 "scores": {"reflection": 1-4, "specificity": 1-4, "voice": 1-4, "structure": 1-4, "prompt_fit": 1-4},
 "notes": [{"id": "n1", "kind": "reflect|specific|clarity|strength", "quote": "exact text ≤ 300 chars",
            "question": "str ≤ 300", "why": "str ≤ 300"}]}
```
  At most 12 notes. Notes whose `quote` isn't in the normalized `content` are dropped. Normalization: NFKC, curly →
  straight quotes, whitespace runs → one space. Quotes never span paragraphs (the prompt says so, and the validator
  drops any that do). No `rewrite`/`suggestion` text fields are accepted.
- Response: `{id, save_seq, created_at, result}`. If the gateway is not configured, the local fallback
  (`essay_lab/coach.py`) returns heuristic notes (long paragraphs, "I learned" without an example, and so on) with
  `model: "local"`.
- Guards: throttle scope `essay_depth_check` = 1/15s + 120/hour per user; global daily counter in cache
  → 503 `coach_resting` when over budget.

## Frontend (frontend/src/essayLab/, lazy-loaded)
- `App.jsx` changes only: `const EssayLab = lazy(() => import('./essayLab/EssayLab.jsx'))` and the student
  `essay_lab` route renders it inside `<Suspense>`. Remove `essay_lab: ['essays']` from `PAGE_RESOURCE_KEYS`, so the
  big legacy list is no longer loaded for this page.
- Screens from the canvas: Library (folders sidebar with drag + Reorder mode ↑/↓, search, filters, "Pick up where
  you left off" card), New essay (type picker, custom question, university, word limit, folder), Editor (toolbar,
  serif page, word count vs limit, save badge, Coach panel), Focus mode (Esc exits), Welcome-back restore
  (cursor + "You were writing … on Tuesday at 21:14"), Checkpoint history with preview and restore, mobile bottom sheet.
- Coach panel = option 1 from the canvas (Grammarly-style: overall ring, 5 score bars, tabs Reflect / Specifics /
  Clarity / Strengths, note cards). Clicking a card scrolls to and selects the quote. Highlights are ProseMirror
  decorations (never marks), so they never enter the saved doc. Quotes are re-found after every change and
  dropped if missing.
- Smoothness rules:
  - `useEditor({ shouldRerenderOnTransaction: false, immediatelyRender: true })`.
  - The toolbar reads active state through `useEditorState` selectors.
  - No React state update per keystroke outside the editor.
  - Word count is debounced to 250 ms.
  - The localStorage write is throttled to 400 ms.
- Save queue (`saveQueue.js`, pure and unit-tested):
  - A local draft is written under key `naseeb-essay-draft:${userId}:${essayId}` as `{doc, base_seq, updated_at}`.
  - Server sync: 3 s after typing stops, at most every 20 s while typing continues, on editor blur, on
    `visibilitychange` → hidden, and on leaving the page.
  - Only one save is in flight per essay. Changes made during a save are queued as one follow-up.
  - After the first acknowledged save (or from the doc the editor opened with) saves are deltas
    (`docDelta.js`); a doc whose hash equals the last acknowledged one is not sent.
  - A retry reuses the same `client_save_id`. Backoff: a random wait of up to 1, 2, 5, 10, 30 s (full jitter).
  - Page hide uses a `keepalive` fetch only when the body is under 60 KB. It is best effort, and the local draft is
    the guarantee.
  - On load: if a local draft has `updated_at` after the server's `last_edited_at` and its `base_seq` equals the
    server `save_seq`, push it. If the seq differs, show "You have unsynced changes from this device — Keep mine / Use
    saved version".
  - On 409: keep the local text, show a conflict banner with "Keep mine" (re-save against the new seq) and
    "Load latest".
  - `QuotaExceededError` → drop drafts for other essays first, then show a warning.
- Save badge states: `Saving…`, `Saved`, `Offline — saved on this device`, `Couldn't save · Retry`.
- Logout: `clearTokens()` also removes every `naseeb-essay-draft:` key, after a last sync attempt.
- Fonts: the editor page uses the existing Naseeb fonts plus a serif for the page (Georgia / "Source Serif" stack,
  no new font download).

## Tests (required)
- Backend (`backend/apps/admissions/test_essay_lab.py`):
  - ownership: another student gets 404; counselor, organisation and teacher get 403;
  - CRUD for every type; autosave ok, idempotent retry, 409, invalid doc, too large;
  - checkpoint cadence and cap; restore; trash/restore/delete; duplicate;
  - folders CRUD, reorder and nesting limit;
  - depth check: ok (mocked), stale 409, throttle 429, budget 503, malformed AI JSON, quote validation, local fallback;
  - legacy PATCH clears `doc` and bumps `save_seq`;
  - `/api/essays/` counselor and organisation responses don't include the new fields (regression);
  - `assertNumQueries` on list and autosave.
- Frontend (`frontend/tests/essayLab*.test.mjs`, run with `node`): saveQueue (debounce, single flight, retry,
  idempotent id, conflict), docText (derivation matches the backend fixtures), anchors (quote finding and
  normalization).
