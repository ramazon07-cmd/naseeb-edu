"""One switch for every call that sends user data to an outside AI provider."""
from django.conf import settings


def outbound_ai_allowed():
    """False keeps students' (minors') data on our servers: the assistant is off and
    Essay Coach and education guidance use their rule-based fallbacks (open item H8)."""
    return settings.AI_ASSISTANT_ENABLED
