"""
Custom exceptions for the wallets app.
"""

class PaymentError(Exception):
    """Base exception for payment-related errors."""
    pass


class InsufficientFundsError(PaymentError):
    """Raised when a user attempts to transfer more than their available balance."""
    pass


class InvalidAccountError(PaymentError):
    """Raised when an invalid bank account is provided."""
    pass


class TransactionError(PaymentError):
    """Raised when there's an error processing a transaction."""
    pass


class GatewayError(PaymentError):
    """Raised when there's an error communicating with the payment gateway."""
    pass


class DuplicateTransactionError(PaymentError):
    """Raised when a duplicate transaction is detected."""
    pass


class InvalidTransactionStateError(PaymentError):
    """Raised when a transaction is in an invalid state for the requested operation."""
    pass


class InvalidSignatureError(PaymentError):
    """Raised when a webhook signature is invalid."""
    pass


class TransactionNotFoundError(PaymentError):
    """Raised when a transaction is not found."""
    pass


class TransactionVerificationError(PaymentError):
    """Raised when there's an error verifying a transaction."""
    pass
