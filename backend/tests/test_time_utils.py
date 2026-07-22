from datetime import datetime

from app.core.time import utc_now


def test_utc_now_returns_naive_utc_for_mysql_datetime_compatibility():
    value = utc_now()
    assert isinstance(value, datetime)
    assert value.tzinfo is None
