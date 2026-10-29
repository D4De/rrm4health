"""Small, centralised parsers for framework-provided application parameters."""

import math


def split_parameter(value):
    """Split a framework ``-`` separated parameter into non-empty tokens."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [token.strip() for token in str(value).split("-") if token.strip()]


def positive_float(value, name):
    """Return a finite positive float or raise a clear configuration error."""
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite number greater than zero.") from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{name} must be a finite number greater than zero.")
    return parsed


def non_negative_float(value, name):
    """Return a finite non-negative float or raise a clear configuration error."""
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite number greater than or equal to zero.") from error
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{name} must be a finite number greater than or equal to zero.")
    return parsed


def positive_int(value, name):
    """Return a finite positive integer without silently truncating decimals."""
    parsed = positive_float(value, name)
    if not parsed.is_integer():
        raise ValueError(f"{name} must be a finite integer greater than zero.")
    return int(parsed)


def non_negative_int(value, name):
    """Return a finite non-negative integer without silently truncating decimals."""
    parsed = non_negative_float(value, name)
    if not parsed.is_integer():
        raise ValueError(f"{name} must be a finite integer greater than or equal to zero.")
    return int(parsed)


def as_bool(value):
    """Parse the boolean spellings accepted by framework parameters."""
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in {"true", "1", "yes", "on"}:
        return True
    if token in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")
