"""Masking helpers for safe logging/debugging.

These utilities avoid accidentally leaking secrets in logs.
"""


def mask_value(value: str | None) -> str:
    """Mask a value by replacing every other character with "*".

    Args:
        value: A string to mask, or None.

    Returns:
        A masked representation; empty string if value is falsy.
    """
    if not value:
        return ""
    return "".join("*" if i % 2 else c for i, c in enumerate(value))
