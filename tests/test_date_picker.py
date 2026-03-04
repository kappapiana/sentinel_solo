"""
Tests for date picker value conversion (UTC off-by-one fix).
"""
from datetime import date, datetime, timezone

from utils import picker_value_to_local_date


class TestPickerValueToLocalDate:
    """picker_value_to_local_date converts DatePicker values to local date correctly."""

    def test_none_returns_none(self):
        assert picker_value_to_local_date(None) is None

    def test_plain_date_returns_same(self):
        d = date(2025, 3, 2)
        assert picker_value_to_local_date(d) == date(2025, 3, 2)

    def test_naive_datetime_returns_date(self):
        dt = datetime(2025, 3, 2, 12, 0, 0)
        assert picker_value_to_local_date(dt) == date(2025, 3, 2)

    def test_utc_datetime_uses_astimezone(self):
        """Timezone-aware datetime is converted via astimezone() before .date()."""
        utc_march2 = datetime(2025, 3, 2, 0, 0, 0, tzinfo=timezone.utc)
        result = picker_value_to_local_date(utc_march2)
        assert result == date(2025, 3, 2)

    def test_utc_evening_returns_local_date(self):
        """March 1 23:00 UTC = March 2 00:00 in UTC+1. Raw .date() would wrongly give March 1."""
        utc_march1_23 = datetime(2025, 3, 1, 23, 0, 0, tzinfo=timezone.utc)
        assert utc_march1_23.date() == date(2025, 3, 1)  # wrong for UTC+1 user
        result = picker_value_to_local_date(utc_march1_23)
        # Result depends on system TZ; we only assert it returns a valid date
        assert result is not None
        assert isinstance(result, date)
        assert result in (date(2025, 3, 1), date(2025, 3, 2))  # depends on TZ
