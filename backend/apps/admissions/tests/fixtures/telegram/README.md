Synthetic pages in the markup of the public channel preview (https://t.me/s/<channel>),
one per channel the import reads, plus one older page (`opcorners_before_7201.html`).
The posts are invented and every application link is under example.org/.com/.net.
`ai_responses.json` holds the mocked AI gateway answer for each post, keyed by a phrase in it.
Tests never fetch Telegram or call the AI gateway.
