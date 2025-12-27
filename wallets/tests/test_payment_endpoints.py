from decimal import Decimal
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from wallets.models import Wallet, Transaction

User = get_user_model()

@override_settings(PAYMENT_GATEWAY='mock')
class PaymentEndpointsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number='+2348000000000',
            password='password123',
            first_name='Test',
            last_name='User'
        )
        self.user.set_transaction_pin('1234')
        self.user.save()
        self.client.force_authenticate(user=self.user)
        self.wallet = Wallet.objects.get(user=self.user)
        
        # Fund the wallet for testing
        self.wallet.balance = Decimal('50000.00')
        self.wallet.save()

    def test_deposit_initiation(self):
        """Test initiating a deposit."""
        url = '/api/v1/wallets/deposit/'
        data = {'amount': '5000'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # response may be pending or success depending on view logic
        # View says "status": "pending" for deposit init
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(Decimal(str(response.data['amount'])), Decimal('5000'))

    def test_transfer_funds_internal(self):
        """Test transferring funds to another user."""
        recipient = User.objects.create_user(
            phone_number='+2348000000001',
            password='password123',
            first_name='Recipient',
            last_name='User'
        )
        recipient_wallet = Wallet.objects.get(user=recipient)
        
        url = '/api/v1/wallets/transfer/'
        data = {
            'amount': '1000',
            'pin': '1234',
            'recipient_phone': recipient.phone_number,
            'description': 'Test Transfer'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Refresh wallets
        self.wallet.refresh_from_db()
        recipient_wallet.refresh_from_db()
        
        self.assertEqual(self.wallet.balance, Decimal('49000.00'))
        self.assertEqual(recipient_wallet.balance, Decimal('1000.00'))

    def test_transfer_insufficient_funds(self):
        """Test transfer with insufficient funds."""
        url = '/api/v1/wallets/transfer/'
        data = {
            'amount': '60000',  # More than balance
            'pin': '1234',
            'recipient_phone': '+2348000000001',
            'description': 'Fail Transfer'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_pin(self):
        """Test transfer with invalid PIN."""
        url = '/api/v1/wallets/transfer/'
        data = {
            'amount': '1000',
            'pin': '0000',  # Wrong PIN
            'recipient_phone': '+2348000000001'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_payment_initiation(self):
        """Test initializing a payment via PaymentInitiationView."""
        url = '/api/v1/wallets/payments/initiate/'
        data = {
            'amount': '2000',
            'transaction_type': 'deposit', # This should match usage in serializer
            'email': 'test@example.com',
            'callback_url': 'https://example.com/callback'
        }
        response = self.client.post(url, data)
        
        print(f"Payment Init Response: {response.status_code} - {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
