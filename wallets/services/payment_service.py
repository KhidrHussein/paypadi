"""
Payment service for handling all payment-related operations.
This service acts as a facade to the underlying payment gateway.
"""
import logging
from decimal import Decimal
from typing import Dict, Optional, Tuple

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from ..models import Transaction, Wallet
from ..payment_gateways import get_payment_gateway, TransactionStatus
from ..exceptions import PaymentError, InsufficientFundsError

logger = logging.getLogger(__name__)

class PaymentService:
    """Service for handling payment operations."""
    
    def __init__(self, gateway_name=None):
        """Initialize the payment service with the specified gateway.
        
        Args:
            gateway_name: Name of the payment gateway to use. If None, uses the default from settings.
        """
        self.gateway = get_payment_gateway(gateway_name)
    
    def initialize_payment(
        self,
        user,
        amount: Decimal,
        transaction_type: str,
        description: str = "",
        metadata: Optional[Dict] = None,
        **kwargs
    ) -> Dict:
        """Initialize a payment transaction.
        
        Args:
            user: The user making the payment
            amount: The amount to charge
            transaction_type: Type of transaction (e.g., 'deposit', 'transfer')
            description: Description of the transaction
            metadata: Additional transaction metadata
            **kwargs: Additional parameters for the payment gateway
            
        Returns:
            Dict containing payment initialization data
        """
        wallet = Wallet.objects.get_or_create(user=user)[0]
        
        # Create a pending transaction
        reference = self._generate_reference(transaction_type.upper())
        
        with db_transaction.atomic():
            transaction = Transaction.objects.create(
                wallet=wallet,
                amount=amount,
                transaction_type=transaction_type,
                status=Transaction.TransactionStatus.PENDING,
                reference=reference,
                description=description,
                metadata=metadata or {}
            )
            
            # Initialize payment with the gateway
            try:
                callback_url = self._build_callback_url(reference)
                result = self.gateway.initialize_payment(
                    amount=amount,
                    email=user.email or f"{user.phone_number}@paypadi.ng",
                    reference=reference,
                    callback_url=callback_url,
                    metadata={
                        'user_id': str(user.id),
                        'transaction_id': str(transaction.id),
                        'type': transaction_type,
                        **(metadata or {})
                    },
                    **kwargs
                )
                
                # Update transaction with gateway reference if available
                if 'data' in result and 'reference' in result['data']:
                    transaction.gateway_reference = result['data']['reference']
                    transaction.save(update_fields=['gateway_reference'])
                
                return {
                    'status': True,
                    'message': 'Payment initialized',
                    'data': {
                        'transaction_reference': reference,
                        'authorization_url': result.get('data', {}).get('authorization_url', ''),
                        'reference': reference,
                        'amount': str(amount),
                        'transaction_id': str(transaction.id)
                    }
                }
                
            except Exception as e:
                logger.error(f"Error initializing payment: {str(e)}", exc_info=True)
                transaction.status = Transaction.TransactionStatus.FAILED
                transaction.metadata['error'] = str(e)
                transaction.save(update_fields=['status', 'metadata'])
                raise PaymentError(f"Failed to initialize payment: {str(e)}")
    
    def verify_payment(self, reference: str) -> Dict:
        """Verify the status of a payment transaction.
        
        Args:
            reference: The transaction reference to verify
            
        Returns:
            Dict containing payment verification details
        """
        try:
            transaction = Transaction.objects.select_for_update().get(reference=reference)
            
            # Skip if already completed
            if transaction.status == Transaction.TransactionStatus.COMPLETED:
                return {
                    'status': True,
                    'message': 'Payment already verified',
                    'data': {
                        'status': 'completed',
                        'reference': reference,
                        'amount': str(transaction.amount)
                    }
                }
            
            # Verify with payment gateway
            result = self.gateway.verify_payment(reference)
            
            if not result.get('status'):
                transaction.status = Transaction.TransactionStatus.FAILED
                transaction.metadata['verification_error'] = result.get('message', 'Verification failed')
                transaction.save(update_fields=['status', 'metadata'])
                
                # Refund if it was a transfer (funds were deducted at initiation)
                if transaction.transaction_type == Transaction.TransactionType.TRANSFER:
                    transaction.wallet.balance += transaction.amount
                    transaction.wallet.save(update_fields=['balance'])
                
                return {
                    'status': False,
                    'message': result.get('message', 'Payment verification failed'),
                    'data': {
                        'status': 'failed',
                        'reference': reference,
                        'amount': str(transaction.amount)
                    }
                }
            
            # Update transaction status based on gateway response
            gateway_status = result.get('data', {}).get('status', '').lower()
            
            if gateway_status == TransactionStatus.SUCCESSFUL:
                transaction.status = Transaction.TransactionStatus.COMPLETED
                transaction.metadata['completed_at'] = str(timezone.now())
                
                # Update wallet balance for successful deposits
                if transaction.transaction_type == Transaction.TransactionType.DEPOSIT:
                    transaction.wallet.balance += transaction.amount
                    transaction.wallet.save(update_fields=['balance'])
                
                transaction.save(update_fields=['status', 'metadata'])
                
                return {
                    'status': True,
                    'message': 'Payment verified successfully',
                    'data': {
                        'status': 'completed',
                        'reference': reference,
                        'amount': str(transaction.amount)
                    }
                }
            
            elif gateway_status == TransactionStatus.FAILED:
                transaction.status = Transaction.TransactionStatus.FAILED
                transaction.save(update_fields=['status'])
                
                # Refund if it was a transfer (funds were deducted at initiation)
                if transaction.transaction_type == Transaction.TransactionType.TRANSFER:
                    transaction.wallet.balance += transaction.amount
                    transaction.wallet.save(update_fields=['balance'])
                
                return {
                    'status': False,
                    'message': 'Payment failed',
                    'data': {
                        'status': 'failed',
                        'reference': reference,
                        'amount': str(transaction.amount)
                    }
                }
            
            # Still pending
            return {
                'status': True,
                'message': 'Payment is still pending',
                'data': {
                    'status': 'pending',
                    'reference': reference,
                    'amount': str(transaction.amount)
                }
            }
            
        except Transaction.DoesNotExist:
            raise PaymentError(f"Transaction with reference {reference} not found")
        except Exception as e:
            logger.error(f"Error verifying payment: {str(e)}", exc_info=True)
            raise PaymentError(f"Failed to verify payment: {str(e)}")
    
    def transfer_funds(
        self,
        sender,
        amount: Decimal,
        recipient_account: str,
        recipient_bank_code: str,
        description: str = "",
        metadata: Optional[Dict] = None,
        **kwargs
    ) -> Dict:
        """Transfer funds to a bank account.
        
        Args:
            sender: The user initiating the transfer
            amount: Amount to transfer
            recipient_account: Recipient's account number
            recipient_bank_code: Recipient's bank code
            description: Transfer description
            metadata: Additional metadata
            **kwargs: Additional parameters for the payment gateway
            
        Returns:
            Dict containing transfer details
        """
        wallet = Wallet.objects.select_for_update().get(user=sender)
        
        # Check sufficient balance
        if wallet.available_balance < amount:
            raise InsufficientFundsError("Insufficient balance")
        
        reference = self._generate_reference('TRF')
        
        with db_transaction.atomic():
            # Create a pending transaction
            transaction = Transaction.objects.create(
                wallet=wallet,
                amount=amount,
                transaction_type=Transaction.TransactionType.TRANSFER,
                status=Transaction.TransactionStatus.PENDING,
                reference=reference,
                description=description,
                metadata={
                    'recipient_account': recipient_account,
                    'recipient_bank_code': recipient_bank_code,
                    **(metadata or {})
                }
            )
            
            # Deduct funds immediately to prevent double spending
            wallet.balance -= amount
            wallet.save(update_fields=['balance'])
            
            try:
                # Initiate transfer with payment gateway
                result = self.gateway.transfer_funds(
                    amount=amount,
                    recipient_account=recipient_account,
                    recipient_bank_code=recipient_bank_code,
                    reference=reference,
                    narration=description,
                    metadata={
                        'user_id': str(sender.id),
                        'transaction_id': str(transaction.id),
                        **(metadata or {})
                    },
                    **kwargs
                )
                
                # Update transaction with gateway reference if available
                if 'data' in result and 'reference' in result['data']:
                    transaction.metadata['gateway_reference'] = result['data']['reference']
                
                # If transfer was immediately successful
                if result.get('data', {}).get('status', '').lower() == TransactionStatus.SUCCESSFUL:
                    transaction.status = Transaction.TransactionStatus.COMPLETED
                    transaction.metadata['completed_at'] = str(timezone.now())
                    # Balance already deducted
                
                transaction.save(
                    update_fields=[
                        'status', 
                        'metadata'
                    ]
                )
                
                return {
                    'status': True,
                    'message': 'Transfer initiated',
                    'data': {
                        'transaction_reference': reference,
                        'status': transaction.status,
                        'amount': str(amount),
                        'recipient_account': recipient_account,
                        'transaction_id': str(transaction.id)
                    }
                }
                
            except Exception as e:
                logger.error(f"Error initiating transfer: {str(e)}", exc_info=True)
                transaction.status = Transaction.TransactionStatus.FAILED
                transaction.metadata['error'] = str(e)
                transaction.save(update_fields=['status', 'metadata'])
                
                # Refund balance since transfer failed
                wallet.balance += amount
                wallet.save(update_fields=['balance'])
                
                raise PaymentError(f"Failed to initiate transfer: {str(e)}")
    
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
        try:
            result = self.gateway.verify_bank_account(account_number, bank_code)
            
            if not result.get('status'):
                raise PaymentError(result.get('message', 'Account verification failed'))
            
            return {
                'status': True,
                'message': 'Account verified',
                'data': result.get('data', {})
            }
            
        except Exception as e:
            logger.error(f"Error verifying bank account: {str(e)}", exc_info=True)
            raise PaymentError(f"Failed to verify bank account: {str(e)}")
    
    def _generate_reference(self, prefix: str) -> str:
        """Generate a unique transaction reference."""
        import uuid
        return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
    
    def _build_callback_url(self, reference: str) -> str:
        """Build the callback URL for payment verification."""
        from django.urls import reverse
        from django.contrib.sites.models import Site
        
        try:
            domain = Site.objects.get_current().domain
        except:
            domain = 'example.com'  # Fallback for testing
            
        path = reverse('payment-verify', kwargs={'reference': reference})
        return f"https://{domain}{path}"
