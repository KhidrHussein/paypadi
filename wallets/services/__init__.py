"""
Services package for the wallets app.

This package contains service classes that encapsulate business logic
related to payments, transactions, and wallet operations.
"""

# Import service classes to make them available at the package level
from .payment_service import PaymentService  # noqa

__all__ = [
    'PaymentService',
]
