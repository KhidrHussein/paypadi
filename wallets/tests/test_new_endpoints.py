from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from wallets.models import Wallet
from decimal import Decimal

User = get_user_model()

@override_settings(PAYMENT_GATEWAY='mock')
class NewEndpointsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number='+2348000000000',
            password='password123',
            first_name='Test',
            last_name='User',
            role='rider' # ensure role exists
        )
        self.client.force_authenticate(user=self.user)
        self.wallet = Wallet.objects.get(user=self.user)

    def test_user_lookup_success(self):
        """Test looking up an existing user."""
        url = '/api/v1/wallets/payments/lookup/'
        data = {'phone_number': '8000000000'} # Partial match
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['first_name'], 'Test')
        self.assertEqual(response.data['last_name'], 'User')
        self.assertIn('+2348000000000', response.data['phone_number'])

    def test_user_lookup_not_found(self):
        """Test looking up a non-existent user."""
        url = '/api/v1/wallets/payments/lookup/'
        data = {'phone_number': '9999999999'}
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_deposit_account_create_new(self):
        """Test requesting a deposit account when one doesn't exist."""
        # Ensure wallet has no virtual account initially
        self.assertIsNone(self.wallet.virtual_account_number)
        
        url = '/api/v1/wallets/deposit/account/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK, f"Response: {response.data}")
        self.assertIn('account_number', response.data)
        self.assertIn('bank_name', response.data)
        
        # Verify wallet was updated
        self.wallet.refresh_from_db()
        self.assertIsNotNone(self.wallet.virtual_account_number)
        self.assertEqual(self.wallet.virtual_bank_name, 'Wema Bank')

    def test_get_deposit_account_existing(self):
        """Test retrieving an existing deposit account."""
        # Setup existing account
        self.wallet.virtual_account_number = '1234567890'
        self.wallet.virtual_bank_code = '035'
        self.wallet.virtual_bank_name = 'Wema Bank'
        self.wallet.save()
        
        url = '/api/v1/wallets/deposit/account/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return existing without calling gateway (mock returns random usually)
        self.assertEqual(response.data['account_number'], '1234567890')
