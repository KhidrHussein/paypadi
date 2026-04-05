from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from wallets.models import Wallet, Transaction
from unittest.mock import patch
from wallets.exceptions import InsufficientFundsError

User = get_user_model()

class ExternalTransfersTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number='+2348100000099',
            password='password123',
            first_name='External',
            last_name='Tester'
        )
        self.user.set_transaction_pin('1234')
        self.user.save()
        
        self.client.force_authenticate(user=self.user)
        
        self.wallet = Wallet.objects.get(user=self.user)
        self.wallet.balance = Decimal('10000.00')
        self.wallet.save()

    @patch('wallets.services.payment_service.PaymentService.transfer_funds')
    def test_external_transfer_success(self, mock_transfer):
        """Test external transfer to a bank account."""
        mock_transfer.return_value = {
            'status': True,
            'message': 'Transfer initiated successfully',
            'data': {'reference': 'TRF-test-123'}
        }
        
        url = '/api/v1/wallets/transfer/'
        data = {
            'amount': '2500.00',
            'pin': '1234',
            'recipient_account_number': '0123456789',
            'recipient_bank_code': '058',
            'description': 'Test external transfer'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_transfer.assert_called_once()
        args, kwargs = mock_transfer.call_args
        self.assertEqual(kwargs['amount'], Decimal('2500.00'))
        self.assertEqual(kwargs['recipient_account'], '0123456789')
        self.assertEqual(kwargs['recipient_bank_code'], '058')

    @patch('wallets.services.payment_service.PaymentService.transfer_funds')
    def test_withdrawal_success(self, mock_transfer):
        """Test wallet withdrawal."""
        mock_transfer.return_value = {
            'status': True,
            'message': 'Withdrawal initiated successfully',
            'data': {'reference': 'WTH-test-123'}
        }
        
        url = '/api/v1/wallets/withdraw/'
        data = {
            'amount': '3000.00',
            'pin': '1234',
            'recipient_account_number': '9876543210',
            'recipient_bank_code': '044'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_transfer.assert_called_once()
        args, kwargs = mock_transfer.call_args
        self.assertEqual(kwargs['amount'], Decimal('3000.00'))
        self.assertEqual(kwargs['transaction_type'], Transaction.TransactionType.WITHDRAWAL)

    @patch('wallets.services.payment_service.PaymentService.initialize_payment')
    def test_deposit_initiation(self, mock_init):
        """Test wallet deposit initiation."""
        mock_init.return_value = {
            'status': True,
            'message': 'Payment initialized',
            'data': {'authorization_url': 'https://pay.gateway.com/123'}
        }
        
        url = '/api/v1/wallets/deposit/'
        data = {'amount': '5000.00'}
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_init.assert_called_once()
        args, kwargs = mock_init.call_args
        self.assertEqual(kwargs['amount'], Decimal('5000.00'))
        self.assertEqual(kwargs['transaction_type'], Transaction.TransactionType.DEPOSIT)

    @patch('wallets.services.payment_service.PaymentService.transfer_funds')
    def test_external_transfer_insufficient_funds(self, mock_transfer):
        """Test external transfer fails if gateway propagates insufficient funds."""
        mock_transfer.side_effect = InsufficientFundsError("Insufficient balance")
        
        url = '/api/v1/wallets/transfer/'
        data = {
            'amount': '60000.00',
            'pin': '1234',
            'recipient_account_number': '0123456789',
            'recipient_bank_code': '058'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Insufficient balance', str(response.data))
