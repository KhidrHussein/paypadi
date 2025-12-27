from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse
from wallets.models import Wallet
from users.models import DriverPayoutAccount
from decimal import Decimal
from unittest.mock import patch

User = get_user_model()

class AuditFixesTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_wallet_creation_signal(self):
        """Test that a wallet is automatically created when a user is created."""
        user = User.objects.create_user(
            phone_number='+2348000000888',
            password='password123',
            first_name='Signal',
            last_name='Test'
        )
        self.assertTrue(Wallet.objects.filter(user=user).exists())

    @patch('wallets.services.payment_service.PaymentService.verify_payment')
    def test_payment_verify_endpoint(self, mock_verify):
        """Test the payment verification endpoint exists and accepts GET."""
        ref = 'test-ref-123'
        url = reverse('payment-verify', args=[ref]) # Should match new name
        
        mock_verify.return_value = {
            'status': True,
            'message': 'Mock Verified',
            'data': {}
        }
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_verify.assert_called_with(ref)

    def test_driver_withdrawal_default_account(self):
        """Test withdrawal uses default driver payout account."""
        # Create Driver
        driver = User.objects.create_user(
            phone_number='+2348099999999',
            password='password123',
            first_name='Driver',
            last_name='One',
            role='driver' # Assuming this sets the role field
        )
        driver.set_transaction_pin('1234')
        driver.save()
        
        # Ensure wallet (signal check redundant but needed for balance)
        wallet = Wallet.objects.get(user=driver)
        wallet.balance = Decimal('50000.00')
        wallet.save()
        
        # Create Payout Account
        DriverPayoutAccount.objects.create(
            driver=driver,
            account_number='0123456789',
            bank_code='058',
            account_name='Driver Bank',
            is_primary=True
        )
        
        self.client.force_authenticate(user=driver)
        
        url = '/api/v1/wallets/withdraw/'
        data = {
            'amount': '1000',
            'pin': '1234'
            # No recipient details provided
        }
        
        # We need to mock the PaymentService.transfer_funds or similar if it's called
        # But WithdrawFundsView uses TransferFundsSerializer validation then logic mocking
        # Wait, the view says "# TODO: Integrate with payment gateway" and mocks success effectively
        # But `TransferFundsView` uses `payment_service.transfer_funds`, 
        # `WithdrawFundsView` (APIView) in `views.py` has its own logic that just creates Transaction
        # and mocks success.
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        # Verify transaction metadata or similar?
        # The view creates a transaction with metadata including recipient details
        # Let's check the created transaction
        from wallets.models import Transaction
        txn = Transaction.objects.get(reference=response.data['reference'])
        self.assertEqual(txn.metadata.get('recipient_account_number'), '0123456789')
        self.assertEqual(txn.metadata.get('recipient_bank_code'), '058')
