from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.urls import reverse
from wallets.models import Wallet, Transaction
from wallets.services.payment_service import PaymentService
from decimal import Decimal
from unittest.mock import patch, MagicMock

User = get_user_model()

class InterWalletTransferTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number='+2348011111111',
            password='password123',
            first_name='Inter',
            last_name='Tester'
        )
        self.wallet = Wallet.objects.get(user=self.user)
        self.wallet.balance = Decimal('50000.00')
        self.wallet.save()
        
        self.service = PaymentService()

    @patch('wallets.services.payment_service.get_payment_gateway')
    def test_async_transfer_balance_deduction_bug(self, mock_get_gateway):
        """
        Test that async transfers (PENDING from gateway) might fail to deduct balance
        if not handled correctly in verify_payment or initial transfer.
        """
        # Mock gateway to return PENDING
        mock_gateway_instance = MagicMock()
        mock_get_gateway.return_value = mock_gateway_instance
        
        # Re-initialize service to pick up the mock
        self.service = PaymentService() 

        mock_gateway_instance.transfer_funds.return_value = {
            'status': True,
            'message': 'Transfer queued',
            'data': {
                'reference': 'gw_ref_123',
                'status': 'pending' # Simulating pending/queued state
            }
        }
        
        # 1. Initiate Transfer
        # We use the service directly to isolate logic, similar to how views would use it
        result = self.service.transfer_funds(
            sender=self.user,
            amount=Decimal('5000.00'),
            recipient_account='1234567890',
            recipient_bank_code='057',
            description='Test Async Transfer'
        )
        
        # Verify result is pending
        self.assertEqual(result['data']['status'], 'pending')
        
        # Check Balance - Should strictly be deducted or reserved to prevent double spend
        self.wallet.refresh_from_db()
        print(f"Balance after initiation: {self.wallet.balance}")
        
        # Get the transaction
        txn_ref = result['data']['transaction_reference']
        transaction = Transaction.objects.get(reference=txn_ref)
        self.assertEqual(transaction.status, Transaction.TransactionStatus.PENDING)

        # 2. Verify Payment (Simulate Webhook Success)
        # Mock verify to return SUCCESS
        mock_gateway_instance.verify_payment.return_value = {
            'status': True,
            'message': 'Transfer Successful',
            'data': {
                'status': 'successful',
                'reference': 'gw_ref_123'
            }
        }
        
        # Execute verification logic
        verify_result = self.service.verify_payment(txn_ref)
        
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, Transaction.TransactionStatus.COMPLETED)
        
        # Check Balance again
        self.wallet.refresh_from_db()
        print(f"Balance after failure/success: {self.wallet.balance}")
        
        # We assert what we expect correct behavior to be (balance deducted)
        self.assertEqual(self.wallet.balance, Decimal('45000.00'), "Balance should be deducted after successful transfer")
