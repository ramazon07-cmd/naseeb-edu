# Naseeb Edu channel in Messages

Students can open the pinned Naseeb Edu channel in Messages → Groups. The feed
opens at the latest post at the bottom, in chronological order. Older posts load
above the current page without moving the reading position. Nearby post embeds
are mounted on demand and released after moving well away from the viewport,
retaining their measured height.
The embeds follow the application’s light/dark theme.
Post content and media are rendered in Telegram's own isolated post embeds.
Subscriptions and other Telegram account actions open Telegram.

`GET /api/telegram-feed/?before=<post_id>` requires an authenticated app user.
The backend discovers post IDs from `https://t.me/s/naseeb_edu` and returns only
fixed-channel post IDs and a pagination cursor (under 1 KB, at most about 20 posts
a page). It does not accept arbitrary upstream URLs or return Telegram HTML. No
bot token, Telegram login, database migration, or additional dependency is required.

What it costs, and how the server is protected:

- Opening the channel asks for one page of IDs, not the whole channel. Older pages
  load only with the "Load older posts" button.
- The newest page is cached for 60 seconds, older pages for an hour, and every page
  is kept for a day as the answer while Telegram is slow or down.
- Only one request per page asks Telegram at a time; the others get the copy they
  already have, or wait up to 3 seconds for the new one. A failed try is not
  repeated for 10 seconds, so an outage is not retried by every student.
- At most 20 pages a minute leave for Telegram, whatever cursors are requested, and
  a cursor past the newest post is answered with the newest page.
- Each user is limited to `TELEGRAM_FEED_RATE` (60/minute). When no page can be had
  the endpoint answers 503 with `Retry-After`.

In the browser, a post's embed frame loads only after the post has stayed near the
viewport for 200 ms (fast scrolling passes posts by). Once loaded, it remains
mounted while within one viewport, with at least 600 px of margin, and is released
3 seconds after moving farther away. This avoids reloading neighboring embeds
while scrolling and stops distant media downloads. Telegram's widget may fetch
videos in full while its frame is alive, so those are the largest cost.

How loading looks: until a post's frame reports its size, the post shows an outline
of text sized to the height measured earlier in the session (300 px for a post not
seen yet), and shimmers only while its frame is loading. When the frame reports its
size the outline fades out and the post unfolds to its height. A post above what the
reader is looking at changes size at once and the scroll position is corrected by the
same amount, so the reader's place does not move; the newest post stays in view while
it unfolds. A frame that has not reported a size after 12 seconds shows "This post
could not be loaded" with Retry and the link to Telegram. With reduced motion there is
no shimmer and no unfolding, only a short fade.

The backend needs HTTPS access to `t.me`; browsers need access to Telegram and
its media hosts. Production nginx permits `https://t.me` in `frame-src`.
Deploy both the backend and rebuilt frontend together.

Telegram's public preview is not a versioned API. If the channel becomes private,
previews are restricted, or Telegram changes its markup, discovery can fail.
The UI offers retry and a direct Telegram link. Protected/unsupported post types
may require opening Telegram, as indicated by Telegram's own widget.

For local Python installations on macOS, the feed automatically adds the system
CA bundle at `/etc/ssl/cert.pem` to Python's default trust store. Explicit
`SSL_CERT_FILE` or `SSL_CERT_DIR` configuration takes precedence. Certificate and
hostname verification remain enabled; no special startup command is needed.

Verification: `python manage.py test apps.admissions.test_telegram_feed` from
`backend`; `npm test` and `npm run build` from `frontend`.

Telegram post widget documentation: https://core.telegram.org/widgets/post
