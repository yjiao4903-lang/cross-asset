"""Timestamp normalization for the storage schema's timezone-naive TIMESTAMPs."""

from datetime import UTC, datetime


def utc_naive(value):
    """Convert aware datetimes to UTC-naive while preserving other values."""
    if value is None or not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
