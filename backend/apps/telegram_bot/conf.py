from decouple import config

LOGIN_MAX_ATTEMPTS = config('BOT_LOGIN_MAX_ATTEMPTS', default=5, cast=int)
LOGIN_WINDOW_SECONDS = config('BOT_LOGIN_WINDOW_SECONDS', default=900, cast=int)
# Failures per account over all chats before chats that never signed in to it are slowed down.
ACCOUNT_CEILING = config('BOT_LOGIN_ACCOUNT_CEILING', default=30, cast=int)
# A daily update still goes out this many minutes after its time (bot restarted or busy).
DUE_GRACE_MINUTES = config('BOT_DUE_GRACE_MINUTES', default=5, cast=int)
