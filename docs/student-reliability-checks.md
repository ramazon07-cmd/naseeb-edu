# Student workspace reliability checks

Students must see a loading/error state when information is unavailable, keep their latest dashboard choice, and see fresh work after returning to a page.

## Automated checks

From `frontend/`, run `npm run check`. The framework-free regressions in `tests/studentReliability.test.mjs` cover:

- Failed first loads versus successful empty data; profile-dependent pages block while account security and independent tools remain reachable.
- A 60-second freshness window, in-flight deduplication, failures, invalidations made during a read, and resetting the cache between accounts.
- Essay creation, deletion, duplication, sharing and metadata invalidating summaries; text autosaves/folder writes remain local.
- An old layout GET finishing after a newer save, serialized overlapping saves, pending uploads failing after a successful GET, retry on the next visit, blocked local storage and sign-out during a read.

## Browser regressions

Start the local Vite server from `frontend/`:

```sh
npm run dev -- --host 127.0.0.1 --port 5181
```

Open [the browser checks](http://127.0.0.1:5181/tests/studentReliability.browser.html). Wait for **ALL BROWSER CHECKS PASSED**. This runs nine scenarios against the actual components, hooks and API client:

1. Dashboard task failure shows an error, then Retry restores the assigned task.
2. A changed task becomes visible on focus after the freshness window; rapid focus does not repeat the request.
3. A failed dashboard layout save keeps the selected widgets and uploads them when the online event arrives.
4. Essay Lab creation updates the shared workspace on revisit; a text autosave causes no collection fetch.
5. Creation while an older essay read is pending triggers another read after that old response.
6. My List failure disables unknown save state; Retry restores the saved program and its remove button sends DELETE.
7. Meeting availability failure retains successfully loaded staff, shows an error and retries times.
8. Rescheduling failure exposes Retry and recovers published times.
9. Unread chat failure does not show “All caught up”; Retry works with the same summary counts.

Only the fixture tab replaces fetch, supplies dummy principals/responses and controls the clock. Its fetch handler refuses requests outside the local `/api/` fixture. No backend server, real account, email or third-party service is needed. This test entry is excluded from the production build. Fixture session hints and the clock are cleaned up; the fixture URL is restored so reload starts the checks again.

Optional query parameters select the final preview: `theme=light|dark`, `language=en|uz|ru`, and `preview=dashboard|booking|notifications` (default: Programs). Verify 320, 560, 820, 1100 and 1440 px, including error text wrapping, visible Retry and keyboard focus. Restore any temporary viewport override afterwards.

## Boundary of the verification

The browser fixture proves frontend request/state/rendering behavior with deterministic API responses. Existing Django tests verify the backend contracts. Production deployment, real cross-origin cookie behavior and live counselor/student sessions require separate verification after review and deployment.
