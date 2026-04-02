# Sentinel Solo - Exception Hierarchy Implementation Plan

**Date:** 2026-04-01  
**Version:** v0.4.2  
**Status:** Ready for Implementation  
**Priority:** Critical

---

## Overview

This plan implements a custom exception hierarchy to replace the inconsistent `ValueError` usage throughout the codebase. This improves error handling, makes errors more actionable, and enables better error messages.

---

## Implementation Steps

### Step 1: Create `exceptions.py` Module

**File:** [`exceptions.py`](exceptions.py)

```python
"""
Custom exceptions for Sentinel Solo.

This module defines a hierarchy of exceptions that provide more specific
error information than generic ValueError/TypeError exceptions.
"""


class SentinelError(Exception):
    """Base exception for all Sentinel Solo errors."""
    pass


class DatabaseError(SentinelError):
    """Raised when a database operation fails."""
    pass


class AuthenticationError(SentinelError):
    """Raised when authentication fails."""
    pass


class AuthorizationError(SentinelError):
    """Raised when a user lacks permission to perform an action."""
    pass


class ValidationError(SentinelError):
    """Raised when input validation fails."""
    pass


class NotFoundError(SentinelError):
    """Raised when a requested resource is not found."""
    pass


class MatterNotFoundError(NotFoundError):
    """Raised when a matter cannot be found."""
    
    def __init__(self, matter_id: int):
        super().__init__(
            f"The matter you selected is no longer available. "
            f"It may have been deleted or moved. "
            f"Please select a different matter and try again. "
            f"(Matter ID: {matter_id})"
        )
        self.matter_id = matter_id


class TimeEntryNotFoundError(NotFoundError):
    """Raised when a time entry cannot be found."""
    
    def __init__(self, entry_id: int):
        super().__init__(
            f"The time entry you selected is no longer available. "
            f"It may have been deleted or modified by another user. "
            f"Please refresh the page and try again. "
            f"(Entry ID: {entry_id})"
        )
        self.entry_id = entry_id


class UserNotFoundError(NotFoundError):
    """Raised when a user cannot be found."""
    
    def __init__(self, user_id: int):
        super().__init__(
            f"The user you selected is no longer available. "
            f"It may have been deleted. "
            f"Please select a different user and try again. "
            f"(User ID: {user_id})"
        )
        self.user_id = user_id


class RateResolutionError(SentinelError):
    """Raised when hourly rate cannot be resolved."""
    
    def __init__(self, matter_id: int):
        super().__init__(
            f"Cannot resolve hourly rate for matter ID {matter_id}. "
            f"Please ensure the matter exists and has a valid hourly rate set."
        )
        self.matter_id = matter_id


class BudgetError(SentinelError):
    """Raised when a budget operation fails."""
    pass


class BudgetExceededError(BudgetError):
    """Raised when a budget limit is exceeded."""
    
    def __init__(self, matter_id: int, total: float, budget: float):
        super().__init__(
            f"Budget exceeded for this matter: €{total:.2f} of €{budget:.2f} logged. "
            f"Please review your time entries and adjust as needed."
        )
        self.matter_id = matter_id
        self.total = total
        self.budget = budget


class PermissionError(SentinelError):
    """Raised when a user lacks permission to perform an action."""
    
    def __init__(self, action: str, resource: str):
        super().__init__(
            f"You do not have permission to {action} {resource}. "
            f"Please contact an administrator if you believe this is an error."
        )
        self.action = action
        self.resource = resource


class InvalidBackupError(SentinelError):
    """Raised when a backup file is invalid."""
    
    def __init__(self, message: str):
        super().__init__(
            f"Invalid backup file: {message}. "
            f"Please ensure the backup file is valid and try again."
        )
        self.message = message


class DatabaseIntegrityError(DatabaseError):
    """Raised when a database integrity constraint is violated."""
    
    def __init__(self, message: str):
        super().__init__(
            f"Database integrity error: {message}. "
            f"Please ensure the data is valid and try again."
        )
        self.message = message


class DatabaseConnectionError(DatabaseError):
    """Raised when a database connection fails."""
    
    def __init__(self, message: str):
        super().__init__(
            f"Database connection error: {message}. "
            f"Please ensure the database is running and try again."
        )
        self.message = message
```

---

### Step 2: Update `database_manager.py`

**File:** [`database_manager.py`](database_manager.py:1)

**Changes:**

1. Import new exceptions
2. Replace `ValueError` with specific exceptions

```python
# Add to imports at top of file
from exceptions import (
    SentinelError,
    MatterNotFoundError,
    TimeEntryNotFoundError,
    UserNotFoundError,
    RateResolutionError,
    BudgetError,
    BudgetExceededError,
    PermissionError,
    InvalidBackupError,
    DatabaseIntegrityError,
    DatabaseConnectionError,
)
```

**Replace existing ValueError raises:**

```python
# Line 131-132: Replace ValueError with PermissionError
def _require_user(self) -> None:
    """Raise if current_user_id is not set (required for matters/time_entries)."""
    if self._current_user_id is None:
        raise PermissionError("access", "user resources")

# Line 696-697: Replace ValueError with MatterNotFoundError
if matter is None:
    raise MatterNotFoundError(matter_id)

# Line 787-788: Replace ValueError with MatterNotFoundError
if matter is None:
    raise MatterNotFoundError(matter_id)

# Line 789-790: Replace ValueError with ValidationError
if matter.parent_id is None:
    raise ValidationError("Time cannot be logged to a client; select a matter under a client.")

# Line 845-846: Replace ValueError with TimeEntryNotFoundError
if entry is None:
    raise TimeEntryNotFoundError(entry_id)

# Line 1106-1107: Replace ValueError with PermissionError
if not self._is_admin(session):
    raise PermissionError("export", "full database")

# Line 1175-1176: Replace ValueError with InvalidBackupError
if not isinstance(data, dict):
    raise InvalidBackupError("not a dict")

# Line 1177-1179: Replace ValueError with InvalidBackupError
for key in ("version", "users", "matters", "time_entries"):
    if key not in data:
        raise InvalidBackupError(f"missing '{key}'")

# Line 1180-1181: Replace ValueError with InvalidBackupError
if data.get("version") != self.BACKUP_VERSION:
    raise InvalidBackupError(f"unsupported version: {data.get('version')}")

# Line 1183-1184: Replace ValueError with PermissionError
if not self._is_admin(session):
    raise PermissionError("import", "full database")

# Line 1269-1271: Replace ValueError with ValidationError
if provided != 2:
    raise ValidationError(
        "Provide exactly two of start_time, end_time, duration_seconds."
    )

# Line 1275-1276: Replace ValueError with ValidationError
if duration_seconds < 0:
    raise ValidationError("End time must be after start time.")

# Line 1278-1279: Replace ValueError with ValidationError
if duration_seconds < 0:
    raise ValidationError("Duration must be non-negative.")

# Line 1283-1284: Replace ValueError with ValidationError
if duration_seconds < 0:
    raise ValidationError("Duration must be non-negative.")

# Line 1301-1302: Replace ValueError with TimeEntryNotFoundError
if entry is None:
    raise TimeEntryNotFoundError(entry_id)

# Line 1307-1308: Replace ValueError with MatterNotFoundError
if matter is None:
    raise MatterNotFoundError(matter_id)

# Line 1309-1310: Replace ValueError with ValidationError
if matter.parent_id is None:
    raise ValidationError("Time cannot be logged to a client.")

# Line 1316-1317: Replace ValueError with ValidationError
if duration_seconds is not None and duration_seconds < 0:
    raise ValidationError("Duration must be non-negative.")

# Line 1318-1319: Replace ValueError with ValidationError
if start_time and end_time and end_time < start_time:
    raise ValidationError("End time must be after start time.")

# Line 1337-1338: Replace ValueError with TimeEntryNotFoundError
if entry is None:
    raise TimeEntryNotFoundError(entry_id)

# Line 1355-1356: Replace ValueError with MatterNotFoundError
if matter is None:
    raise MatterNotFoundError(matter_id)

# Line 1357-1358: Replace ValueError with ValidationError
if matter.parent_id is None:
    raise ValidationError("Time cannot be logged to a client.")

# Line 1363-1364: Replace ValueError with ValidationError
if duration_seconds is not None and duration_seconds < 0:
    raise ValidationError("Duration must be non-negative.")

# Line 1365-1366: Replace ValueError with ValidationError
if start_time and end_time and end_time < start_time:
    raise ValidationError("End time must be after start time.")

# Line 1703-1704: Replace ValueError with MatterNotFoundError
if matter is None:
    raise MatterNotFoundError(matter_id)

# Line 1706-1707: Replace ValueError with ValidationError
if new_parent_id == matter_id:
    raise ValidationError("Cannot move a matter to itself.")

# Line 1711-1712: Replace ValueError with MatterNotFoundError
if parent is None:
    raise MatterNotFoundError(new_parent_id)

# Line 1713-1715: Replace ValueError with ValidationError
if self._is_descendant_of(session, new_parent_id, matter_id):
    raise ValidationError(
        "Cannot move a matter under one of its descendants."
    )

# Line 1732-1733: Replace ValueError with MatterNotFoundError
if source is None:
    raise MatterNotFoundError(source_matter_id)

# Line 1734-1735: Replace ValueError with MatterNotFoundError
if target is None:
    raise MatterNotFoundError(target_matter_id)

# Line 1736-1737: Replace ValueError with ValidationError
if source_matter_id == target_matter_id:
    raise ValidationError("Cannot merge a matter into itself.")

# Line 1739-1742: Replace ValueError with ValidationError
if self._is_descendant_of(session, target_matter_id, source_matter_id):
    raise ValidationError(
        "Cannot merge into a descendant of the source matter."
    )

# Line 1762-1763: Replace ValueError with MatterNotFoundError
if target is None or target.owner_id != self._current_user_id:
    raise MatterNotFoundError(target_matter_id)

# Line 1780-1781: Replace RuntimeError with DatabaseError
raise DatabaseError(
    "PostgreSQL function app.merge_other_matter_into is missing. "
    "Please run the PostgreSQL bootstrap script."
)

# Line 1784-1785: Replace ValueError with DatabaseError
if row and row[0] is not None:
    raise DatabaseError(row[0])

# Line 1791-1792: Replace ValueError with MatterNotFoundError
if source is None:
    raise MatterNotFoundError(source_matter_id)

# Line 1793-1794: Replace ValueError with ValidationError
if source_matter_id == target_matter_id:
    raise ValidationError("Cannot merge a matter into itself.")

# Line 1795-1797: Replace ValueError with ValidationError
if self._is_descendant_of(session, target_matter_id, source_matter_id):
    raise ValidationError(
        "Cannot merge into a descendant of the source matter."
    )

# Line 1819-1820: Replace ValueError with MatterNotFoundError
if matter is None:
    raise MatterNotFoundError(matter_id)

# Line 1821-1822: Replace ValueError with PermissionError
if matter.owner_id != self._current_user_id:
    raise PermissionError("share", f"matter {matter_id}")

# Line 1823-1824: Replace ValueError with ValidationError
if user_id == self._current_user_id:
    raise ValidationError("Cannot share with yourself.")

# Line 1840-1841: Replace ValueError with MatterNotFoundError
if matter is None:
    raise MatterNotFoundError(matter_id)

# Line 1842-1843: Replace ValueError with PermissionError
if matter.owner_id != self._current_user_id:
    raise PermissionError("remove share", f"matter {matter_id}")

# Line 1855-1856: Replace ValueError with MatterNotFoundError
if matter is None:
    raise MatterNotFoundError(matter_id)

# Line 1857-1858: Replace ValueError with PermissionError
if matter.owner_id != self._current_user_id:
    raise PermissionError("set rate", f"matter {matter_id}")

# Line 1875-1876: Replace ValueError with MatterNotFoundError
if matter is None:
    raise MatterNotFoundError(matter_id)

# Line 1924-1925: Replace RuntimeError with DatabaseError
raise DatabaseError(
    "PostgreSQL function app.list_users_for_share is missing. "
    "Please run the PostgreSQL bootstrap script."
)

# Line 1944-1945: Replace ValueError with MatterNotFoundError
if matter is None:
    raise MatterNotFoundError(matter_id)

# Line 1947-1948: Replace ValueError with MatterNotFoundError
if matter_id not in visible:
    raise MatterNotFoundError(matter_id)

# Line 1949-1950: Replace ValueError with PermissionError
if user_id != self._current_user_id and matter.owner_id != self._current_user_id:
    raise PermissionError("set rate", f"matter {matter_id}")

# Line 2231-2232: Replace ValueError with PermissionError
if not row or row[0] is None:
    raise PermissionError("create users", "the system")

# Line 2247-2248: Replace ValueError with PermissionError
if not admin:
    raise PermissionError("create users", "the system")

# Line 2289-2290: Replace ValueError with UserNotFoundError
if user is None:
    raise UserNotFoundError(user_id)

# Line 2298-2299: Replace ValueError with PermissionError
if not is_self and (not admin or not admin.is_admin):
    raise PermissionError("update is_admin", f"user {user_id}")

# Line 2300-2301: Replace ValueError with PermissionError
if not is_self and is_admin is not None:
    if not admin or not admin.is_admin:
        raise PermissionError("change is_admin", f"user {user_id}")

# Line 2331-2332: Replace ValueError with PermissionError
if not admin:
    raise PermissionError("delete users", "the system")

# Line 2334-2335: Replace ValueError with UserNotFoundError
if user is None:
    raise UserNotFoundError(user_id)
```

---

### Step 3: Update `main.py`

**File:** [`main.py`](main.py:1)

**Changes:**

1. Import new exceptions
2. Update error handling to use new exceptions

```python
# Add to imports at top of file
from exceptions import (
    MatterNotFoundError,
    TimeEntryNotFoundError,
    UserNotFoundError,
    RateResolutionError,
    BudgetError,
    BudgetExceededError,
    PermissionError,
    InvalidBackupError,
    DatabaseIntegrityError,
    DatabaseConnectionError,
    ValidationError,
)
```

**Update error handling in methods:**

```python
# Line 234-236: Update ValueError handling
except MatterNotFoundError as e:
    page.snack_bar = ft.SnackBar(ft.Text(str(e)), open=True)
    page.update()
    return
except ValidationError as e:
    page.snack_bar = ft.SnackBar(ft.Text(str(e)), open=True)
    page.update()
    return

# Line 651-653: Update ValueError handling
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
    page.update()

# Line 937-939: Update ValueError handling
except MatterNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 957-959: Update ValueError handling
except TimeEntryNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 963-965: Update ValueError handling
except TimeEntryNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 980-981: Update ValueError handling
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 988-990: Update ValueError handling
except TimeEntryNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 993-995: Update ValueError handling
except TimeEntryNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 1012-1014: Update ValueError handling
except TimeEntryNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 1019-1021: Update ValueError handling
except TimeEntryNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 1029-1031: Update ValueError handling
except TimeEntryNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 1142-1144: Update ValueError handling
except TimeEntryNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 1194-1196: Update ValueError handling
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 1214-1216: Update ValueError handling
except TimeEntryNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 1474-1476: Update ValueError handling
except MatterNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 1566-1568: Update ValueError handling
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 1560-1561: Update ValueError handling
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2237-2239: Update ValueError handling
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2279-2281: Update ValueError handling
except MatterNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2363-2365: Update ValueError handling
except MatterNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except PermissionError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2375-2377: Update ValueError handling
except MatterNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except PermissionError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2399-2401: Update ValueError handling
except MatterNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except PermissionError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2438-2440: Update ValueError handling
except TimeEntryNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2448-2450: Update ValueError handling
except TimeEntryNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2494-2496: Update ValueError handling
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2514-2516: Update ValueError handling
except TimeEntryNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2640-2642: Update ValueError handling
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2683-2685: Update ValueError handling
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2817-2819: Update ValueError handling
except MatterNotFoundError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2839-2841: Update ValueError handling
except RateResolutionError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
except ValidationError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 2926-2928: Update IntegrityError handling
except DatabaseIntegrityError as err:
    page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)

# Line 4405-4407: Update ValueError handling
except InvalidBackupError as err:
    page.snack_bar = ft.SnackBar(content=ft.Text(str(err)))
except DatabaseError as err:
    page.snack_bar = ft.SnackBar(content=ft.Text(str(err)))

# Line 4453-4455: Update ValueError handling
except (OSError, json.JSONDecodeError) as err:
    page.snack_bar = ft.SnackBar(content=ft.Text(f"Invalid backup file: {err}"))

# Line 4460-4462: Update ValueError handling
except InvalidBackupError as err:
    page.snack_bar = ft.SnackBar(content=ft.Text(str(err)))
except DatabaseError as err:
    page.snack_bar = ft.SnackBar(content=ft.Text(str(err)))

# Line 4465-4467: Update Exception handling
except Exception as err:
    page.snack_bar = ft.SnackBar(content=ft.Text(f"Import failed: {err}"))
```

---

### Step 4: Create Tests

**File:** [`tests/test_exceptions.py`](tests/test_exceptions.py)

```python
"""
Tests for custom exceptions.

This module tests the custom exception hierarchy to ensure:
1. All exceptions inherit from SentinelError
2. Exception messages are user-friendly
3. Exception attributes are set correctly
"""

import pytest

from exceptions import (
    SentinelError,
    MatterNotFoundError,
    TimeEntryNotFoundError,
    UserNotFoundError,
    RateResolutionError,
    BudgetError,
    BudgetExceededError,
    PermissionError,
    InvalidBackupError,
    DatabaseIntegrityError,
    DatabaseConnectionError,
    ValidationError,
)


class TestExceptionHierarchy:
    """Test that all exceptions inherit from SentinelError."""
    
    def test_sentinel_error_is_base_exception(self):
        """SentinelError should be a subclass of Exception."""
        assert issubclass(SentinelError, Exception)
    
    def test_all_exceptions_inherit_from_sentinel_error(self):
        """All custom exceptions should inherit from SentinelError."""
        assert issubclass(MatterNotFoundError, SentinelError)
        assert issubclass(TimeEntryNotFoundError, SentinelError)
        assert issubclass(UserNotFoundError, SentinelError)
        assert issubclass(RateResolutionError, SentinelError)
        assert issubclass(BudgetError, SentinelError)
        assert issubclass(BudgetExceededError, BudgetError)
        assert issubclass(PermissionError, SentinelError)
        assert issubclass(InvalidBackupError, SentinelError)
        assert issubclass(DatabaseIntegrityError, SentinelError)
        assert issubclass(DatabaseConnectionError, SentinelError)
        assert issubclass(ValidationError, SentinelError)


class TestMatterNotFoundError:
    """Test MatterNotFoundError exception."""
    
    def test_inherits_from_not_found_error(self):
        """MatterNotFoundError should inherit from NotFoundError."""
        from exceptions import NotFoundError
        assert issubclass(MatterNotFoundError, NotFoundError)
    
    def test_message_contains_matter_id(self):
        """Error message should contain the matter ID."""
        exc = MatterNotFoundError(123)
        assert "123" in str(exc)
        assert "matter" in str(exc).lower()
    
    def test_matter_id_attribute(self):
        """Exception should have matter_id attribute."""
        exc = MatterNotFoundError(456)
        assert exc.matter_id == 456


class TestTimeEntryNotFoundError:
    """Test TimeEntryNotFoundError exception."""
    
    def test_inherits_from_not_found_error(self):
        """TimeEntryNotFoundError should inherit from NotFoundError."""
        from exceptions import NotFoundError
        assert issubclass(TimeEntryNotFoundError, NotFoundError)
    
    def test_message_contains_entry_id(self):
        """Error message should contain the entry ID."""
        exc = TimeEntryNotFoundError(789)
        assert "789" in str(exc)
        assert "time entry" in str(exc).lower()
    
    def test_entry_id_attribute(self):
        """Exception should have entry_id attribute."""
        exc = TimeEntryNotFoundError(999)
        assert exc.entry_id == 999


class TestUserNotFoundError:
    """Test UserNotFoundError exception."""
    
    def test_inherits_from_not_found_error(self):
        """UserNotFoundError should inherit from NotFoundError."""
        from exceptions import NotFoundError
        assert issubclass(UserNotFoundError, NotFoundError)
    
    def test_message_contains_user_id(self):
        """Error message should contain the user ID."""
        exc = UserNotFoundError(100)
        assert "100" in str(exc)
        assert "user" in str(exc).lower()
    
    def test_user_id_attribute(self):
        """Exception should have user_id attribute."""
        exc = UserNotFoundError(200)
        assert exc.user_id == 200


class TestRateResolutionError:
    """Test RateResolutionError exception."""
    
    def test_message_contains_matter_id(self):
        """Error message should contain the matter ID."""
        exc = RateResolutionError(300)
        assert "300" in str(exc)
        assert "rate" in str(exc).lower()
    
    def test_matter_id_attribute(self):
        """Exception should have matter_id attribute."""
        exc = RateResolutionError(400)
        assert exc.matter_id == 400


class TestBudgetExceededError:
    """Test BudgetExceededError exception."""
    
    def test_inherits_from_budget_error(self):
        """BudgetExceededError should inherit from BudgetError."""
        assert issubclass(BudgetExceededError, BudgetError)
    
    def test_message_contains_budget_info(self):
        """Error message should contain budget information."""
        exc = BudgetExceededError(500, 1000.0, 800.0)
        assert "1000.00" in str(exc)
        assert "800.00" in str(exc)
        assert "budget" in str(exc).lower()
    
    def test_attributes(self):
        """Exception should have correct attributes."""
        exc = BudgetExceededError(500, 1000.0, 800.0)
        assert exc.matter_id == 500
        assert exc.total == 1000.0
        assert exc.budget == 800.0


class TestPermissionError:
    """Test PermissionError exception."""
    
    def test_message_contains_action_and_resource(self):
        """Error message should contain action and resource."""
        exc = PermissionError("delete", "matter")
        assert "delete" in str(exc)
        assert "matter" in str(exc)
    
    def test_attributes(self):
        """Exception should have action and resource attributes."""
        exc = PermissionError("update", "user")
        assert exc.action == "update"
        assert exc.resource == "user"


class TestInvalidBackupError:
    """Test InvalidBackupError exception."""
    
    def test_message_contains_message(self):
        """Error message should contain the original message."""
        exc = InvalidBackupError("invalid JSON")
        assert "invalid JSON" in str(exc)
    
    def test_message_attribute(self):
        """Exception should have message attribute."""
        exc = InvalidBackupError("test message")
        assert exc.message == "test message"


class TestDatabaseIntegrityError:
    """Test DatabaseIntegrityError exception."""
    
    def test_inherits_from_database_error(self):
        """DatabaseIntegrityError should inherit from DatabaseError."""
        from exceptions import DatabaseError
        assert issubclass(DatabaseIntegrityError, DatabaseError)
    
    def test_message_contains_message(self):
        """Error message should contain the original message."""
        exc = DatabaseIntegrityError("unique constraint failed")
        assert "unique constraint failed" in str(exc)


class TestDatabaseConnectionError:
    """Test DatabaseConnectionError exception."""
    
    def test_inherits_from_database_error(self):
        """DatabaseConnectionError should inherit from DatabaseError."""
        from exceptions import DatabaseError
        assert issubclass(DatabaseConnectionError, DatabaseError)
    
    def test_message_contains_message(self):
        """Error message should contain the original message."""
        exc = DatabaseConnectionError("connection timeout")
        assert "connection timeout" in str(exc)


class TestValidationError:
    """Test ValidationError exception."""
    
    def test_message_is_user_friendly(self):
        """Error message should be user-friendly."""
        exc = ValidationError("End time must be after start time.")
        assert "End time must be after start time." in str(exc)
```

---

## Testing Strategy

### Unit Tests
- Test each exception class
- Test exception messages
- Test exception attributes

### Integration Tests
- Test exception handling in database_manager.py
- Test exception handling in main.py
- Test error messages in UI

### Verification
- All existing tests pass
- New exception tests pass
- Error messages are user-friendly
- No `ValueError` remains in database_manager.py or main.py

---

## Implementation Timeline

| Day | Task |
|-----|------|
| 1 | Create `exceptions.py` module |
| 2 | Update `database_manager.py` to use new exceptions |
| 3 | Update `main.py` to handle new exceptions |
| 4 | Create unit tests for exceptions |
| 5 | Create integration tests for exception handling |
| 6 | Run all tests and verify |
| 7 | Update documentation |

---

## Success Criteria

- [ ] All custom exceptions created
- [ ] All `ValueError` replaced with specific exceptions
- [ ] All tests pass
- [ ] Error messages are user-friendly
- [ ] No `ValueError` remains in codebase
