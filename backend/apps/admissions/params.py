"""Strict parsing of id-like request parameters.

A non-numeric value such as ``?student=abc`` must be a 400, not a ValueError
(500) from the ORM filter.
"""
from rest_framework.exceptions import ValidationError


MAX_ID = 2 ** 63 - 1


def int_param(source, name):
    """Return ``source[name]`` as an int, ``None`` when absent/blank, or raise 400."""
    value = source.get(name)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValidationError({name: ['A valid integer is required.']})
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError({name: ['A valid integer is required.']})
    # Ids are 64-bit; larger values would overflow the database driver (500).
    if not -MAX_ID <= number <= MAX_ID:
        raise ValidationError({name: ['A valid integer is required.']})
    return number


def int_list_param(source, name):
    values = source.get(name) or []
    if not isinstance(values, (list, tuple)):
        raise ValidationError({name: ['Provide a list of integer ids.']})
    try:
        numbers = [int(str(value).strip()) for value in values if not isinstance(value, bool)]
    except (TypeError, ValueError):
        raise ValidationError({name: ['Provide a list of integer ids.']})
    if any(not -MAX_ID <= number <= MAX_ID for number in numbers):
        raise ValidationError({name: ['Provide a list of integer ids.']})
    return numbers
