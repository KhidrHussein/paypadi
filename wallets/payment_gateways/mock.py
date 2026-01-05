"""
Mock payment gateway implementation for testing and development.
"""
from decimal import Decimal
from typing import Dict, Optional, Any
import uuid
from . import PaymentGateway, TransactionStatus


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
    ) -> Dict[str, Any]:
        """Mock payment initialization."""
        transaction_id = str(uuid.uuid4())
        self.transactions[reference] = {
            'id': transaction_id,
            'amount': amount,
            'email': email,
            'reference': reference,
            'status': 'pending',
            'metadata': metadata or {}
        }
        
        return {
            'status': True,
            'message': 'Payment initialized',
            'data': {
                'authorization_url': f'http://mock-payment-gateway/checkout/{reference}',
                'access_code': str(uuid.uuid4()),
                'reference': reference,
            }
        }
    
    def verify_payment(self, reference: str) -> Dict[str, Any]:
        """Mock payment verification."""
        transaction = self.transactions.get(reference)
        if not transaction:
            return {
                'status': False,
                'message': 'Transaction not found',
                'data': None
            }
            
        # Simulate a successful payment for testing
        if transaction['status'] == 'pending':
            transaction['status'] = 'successful'
            
        return {
            'status': True,
            'message': 'Verification successful',
            'data': {
                'amount': str(transaction['amount']),
                'currency': 'NGN',
                'transaction_date': '2023-01-01T00:00:00.000Z',
                'status': transaction['status'],
                'reference': reference,
                'domain': 'test',
                'metadata': transaction['metadata']
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
    ) -> Dict[str, Any]:
        """Mock funds transfer."""
        transaction_id = str(uuid.uuid4())
        self.transactions[reference] = {
            'id': transaction_id,
            'amount': amount,
            'recipient_account': recipient_account,
            'recipient_bank_code': recipient_bank_code,
            'reference': reference,
            'narration': narration,
            'status': 'pending',
            'type': 'transfer',
            'metadata': kwargs.get('metadata', {})
        }
        
        # Simulate a successful transfer after a delay
        return {
            'status': True,
            'message': 'Transfer initiated successfully',
            'data': {
                'transfer_code': str(uuid.uuid4()),
                'reference': reference,
                'status': 'pending',
                'amount': str(amount),
                'recipient': {
                    'account_number': recipient_account,
                    'bank_code': recipient_bank_code
                }
            }
        }
    
    def verify_bank_account(
        self,
        account_number: str,
        bank_code: str
    ) -> Dict[str, Any]:
        """Mock bank account verification."""
        # In a real implementation, this would call the payment gateway's API
        # For mock purposes, we'll return a success response with test data
        return {
            'status': True,
            'message': 'Account details resolved',
            'data': {
                'account_number': account_number,
                'account_name': 'Test Account Name',
                'bank_code': bank_code,
                'bank_name': 'Test Bank',
                'verified': True
            }
        }

    def create_customer(self, user) -> Dict[str, Any]:
        """Mock customer creation."""
        import uuid
        return {
            'status': True,
            'message': 'Customer created',
            'data': {
                'customer_code': f"CUS_{uuid.uuid4().hex[:8]}",
                'id': 12345,
                'email': user.email or f"{user.phone_number}@paypadi.ng"
            }
        }

    def create_virtual_account(self, customer_code: str, preferred_bank: str = 'wema-bank') -> Dict[str, Any]:
        """Mock virtual account creation."""
        import random
        return {
            'status': True,
            'message': 'Virtual account created',
            'data': {
                'account_number': f"99{random.randint(10000000, 99999999)}",
                'account_name': 'Test User Virtual',
                'bank_name': 'Wema Bank',
                'bank_code': '035',
                'currency': 'NGN',
                'assigned': True
            }
        }
