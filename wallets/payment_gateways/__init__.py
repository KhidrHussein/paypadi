"""
Payment gateway integration module.
This module provides an interface for different payment gateway implementations.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Optional, Tuple, Type
from enum import Enum
import importlib
from django.conf import settings


def get_payment_gateway(gateway_name: str = None) -> Type['PaymentGateway']:
    """Get a payment gateway instance by name.
    
    Args:
        gateway_name: Name of the payment gateway to use. If None, uses the default from settings.
        
    Returns:
        An instance of the specified payment gateway.
        
    Raises:
        PaymentGatewayError: If the gateway cannot be found or instantiated.
    """
    # Get gateway name from settings if not provided
    if gateway_name is None:
        gateway_name = getattr(settings, 'PAYMENT_GATEWAY', 'mock')
    
    # Map of gateway names to their module paths
    gateway_map = {
        'mock': 'wallets.payment_gateways.mock.MockPaymentGateway',
        # Add other gateways here as needed
    }
    
    if gateway_name not in gateway_map:
        raise PaymentGatewayError(f"Unknown payment gateway: {gateway_name}")
    
    # Import the gateway class
    module_path, class_name = gateway_map[gateway_name].rsplit('.', 1)
    try:
        module = importlib.import_module(module_path)
        gateway_class = getattr(module, class_name)
        return gateway_class()
    except (ImportError, AttributeError) as e:
        raise PaymentGatewayError(f"Failed to load payment gateway {gateway_name}: {str(e)}")

class PaymentGatewayError(Exception):
    """Base exception for payment gateway errors."""
    pass

class TransactionStatus(str, Enum):
    """Transaction statuses from payment gateway."""
    PENDING = 'pending'
    SUCCESSFUL = 'successful'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    REVERSED = 'reversed'

class PaymentGateway(ABC):
    """Abstract base class for payment gateway implementations."""
    
    @abstractmethod
    def initialize_payment(
        self,
        amount: Decimal,
        email: str,
        reference: str,
        callback_url: str,
        metadata: Optional[Dict] = None,
        **kwargs
    ) -> Dict:
        """Initialize a payment transaction.
        
        Args:
            amount: The amount to charge
            email: Customer's email
            reference: Unique transaction reference
            callback_url: URL to redirect to after payment
            metadata: Additional transaction metadata
            **kwargs: Additional gateway-specific parameters
            
        Returns:
            Dict containing payment initialization data (e.g., authorization URL)
        """
        pass
    
    @abstractmethod
    def verify_payment(self, reference: str) -> Dict:
        """Verify the status of a payment transaction.
        
        Args:
            reference: The transaction reference to verify
            
        Returns:
            Dict containing payment verification details
        """
        pass
    
    @abstractmethod
    def transfer_funds(
        self,
        amount: Decimal,
        recipient_account: str,
        recipient_bank_code: str,
        reference: str,
        narration: str = "",
        **kwargs
    ) -> Dict:
        """Transfer funds to a bank account.
        
        Args:
            amount: Amount to transfer
            recipient_account: Recipient's account number
            recipient_bank_code: Recipient's bank code
            reference: Unique transaction reference
            narration: Transaction description
            **kwargs: Additional gateway-specific parameters
            
        Returns:
            Dict containing transfer details
        """
        pass
    
    @abstractmethod
    def verify_bank_account(
        self,
        account_number: str,
        bank_code: str
    ) -> Dict:
        """Verify a bank account details.
        
        Args:
            account_number: Bank account number to verify
            bank_code: Bank code
            
        Returns:
            Dict containing account verification details
        """
        pass


class MockPaymentGateway(PaymentGateway):
    """Mock payment gateway for testing and development."""
    
    def __init__(self, test_mode: bool = True):
        self.test_mode = test_mode
        self.transactions = {}
    
    def initialize_payment(
        self,
        amount: Decimal,
        email: str,
        reference: str,
        callback_url: str,
        metadata: Optional[Dict] = None,
        **kwargs
    ) -> Dict:
        """Mock payment initialization."""
        self.transactions[reference] = {
            'status': TransactionStatus.PENDING,
            'amount': amount,
            'email': email,
            'metadata': metadata or {},
            'callback_url': callback_url,
            **kwargs
        }
        
        return {
            'status': True,
            'message': 'Payment initialized',
            'data': {
                'authorization_url': f'https://example.com/pay/{reference}',
                'access_code': 'mock_access_code',
                'reference': reference
            }
        }
    
    def verify_payment(self, reference: str) -> Dict:
        """Mock payment verification."""
        if reference not in self.transactions:
            raise PaymentGatewayError('Transaction not found')
        
        # In test mode, mark as successful after first verification
        if self.test_mode and self.transactions[reference]['status'] == TransactionStatus.PENDING:
            self.transactions[reference]['status'] = TransactionStatus.SUCCESSFUL
        
        return {
            'status': True,
            'message': 'Verification successful',
            'data': {
                'status': self.transactions[reference]['status'],
                'reference': reference,
                'amount': str(self.transactions[reference]['amount']),
                'metadata': self.transactions[reference]['metadata']
            }
        }
    
    def transfer_funds(
        self,
        amount: Decimal,
        recipient_account: str,
        recipient_bank_code: str,
        reference: str,
        narration: str = "",
        **kwargs
    ) -> Dict:
        """Mock funds transfer."""
        self.transactions[reference] = {
            'status': TransactionStatus.PENDING,
            'amount': amount,
            'recipient_account': recipient_account,
            'recipient_bank_code': recipient_bank_code,
            'narration': narration,
            **kwargs
        }
        
        # In test mode, mark as successful immediately
        if self.test_mode:
            self.transactions[reference]['status'] = TransactionStatus.SUCCESSFUL
        
        return {
            'status': True,
            'message': 'Transfer initiated',
            'data': {
                'status': self.transactions[reference]['status'],
                'reference': reference,
                'amount': str(amount),
                'recipient_account': recipient_account,
                'recipient_bank_code': recipient_bank_code,
                'narration': narration
            }
        }
    
    def verify_bank_account(
        self,
        account_number: str,
        bank_code: str
    ) -> Dict:
        """Mock bank account verification."""
        # In a real implementation, this would call the actual bank's API
        return {
            'status': True,
            'message': 'Account details resolved',
            'data': {
                'account_number': account_number,
                'account_name': 'TEST ACCOUNT',
                'bank_code': bank_code,
                'bank_name': 'Test Bank',
                'verified': True
            }
        }
