"""
Utility functions for Sentinel Solo.
"""
from datetime import date, datetime


def picker_value_to_local_date(val: date | datetime | None) -> date | None:
    """
    Convert DatePicker value to local date.
    Fixes UTC off-by-one when the picker returns a timezone-aware datetime in UTC
    (e.g. user selects March 2, picker sends March 1 23:00 UTC for UTC+1).
    """
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        if val.tzinfo is not None:
            return val.astimezone().date()
        return val.date()
    return None
