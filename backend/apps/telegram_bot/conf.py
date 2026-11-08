from decouple import config

LOGIN_MAX_ATTEMPTS = config('BOT_LOGIN_MAX_ATTEMPTS', default=5, cast=int)
LOGIN_WINDOW_SECONDS = config('BOT_LOGIN_WINDOW_SECONDS', default=900, cast=int)
# A daily update still goes out this many minutes after its time (bot restarted or busy).
DUE_GRACE_MINUTES = config('BOT_DUE_GRACE_MINUTES', default=5, cast=int)
