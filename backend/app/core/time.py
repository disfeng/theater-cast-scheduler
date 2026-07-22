from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return naive UTC while persisted columns remain MySQL DATETIME."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
