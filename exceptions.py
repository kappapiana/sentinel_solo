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
