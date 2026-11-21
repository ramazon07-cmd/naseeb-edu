"""Current instrument version per challenge, mirroring INSTRUMENT_VERSION in frontend/src/challenges.js.

Bump here and there together whenever a challenge's items change. An imported attempt answered under
another version is stored but flagged (ChallengeAttempt.source_version_mismatch) and never compared.
"""
INSTRUMENT_VERSION = {
    'personality': '1',
    'interests': '1',
    'subjects': '2',
    'reasoning': '3',
    'values': '1',
    'workimportance': '2',
    'eq': 'wleis-16-1',
}
