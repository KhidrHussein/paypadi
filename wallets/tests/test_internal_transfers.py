from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from wallets.models import Wallet, Beneficiary, Transaction

User = get_user_model()

class InternalTransfersTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.sender = User.objects.create_user(
            phone_number='+2348100000001',
            password='password123',
            first_name='Sender',
            last_name='User'
        )
        self.sender.set_transaction_pin('1234')
        self.sender.save()
        
        self.recipient = User.objects.create_user(
            phone_number='+2348100000002',
            password='password123',
            first_name='Recipient',
            last_name='User'
        )
        
        self.client.force_authenticate(user=self.sender)
        
        # Fund the sender's wallet directly via ORM
        self.sender_wallet = Wallet.objects.get(user=self.sender)
        self.sender_wallet.balance = Decimal('10000.00')
        self.sender_wallet.save()
        
        self.recipient_wallet = Wallet.objects.get(user=self.recipient)

    def test_transfer_direct_phone_number(self):
        """Test a valid transfer using recipient phone number."""
        url = '/api/v1/wallets/transfer/'
        data = {
            'amount': '1500.00',
            'pin': '1234',
            'recipient_phone': self.recipient.phone_number,
            'description': 'Test internal transfer'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.sender_wallet.refresh_from_db()
        self.recipient_wallet.refresh_from_db()
        
        self.assertEqual(self.sender_wallet.balance, Decimal('8495.00'))
        self.assertEqual(self.recipient_wallet.balance, Decimal('1500.00'))
        
        # Verify transaction records
        self.assertTrue(Transaction.objects.filter(reference=response.data['reference']).exists())
        self.assertTrue(Transaction.objects.filter(reference=f"REC-{response.data['reference']}").exists())

    def test_transfer_with_beneficiary_id(self):
        """Test a valid transfer using a registered beneficiary."""
        beneficiary = Beneficiary.objects.create(
            user=self.sender,
            owner=self.sender,
            beneficiary_type=Beneficiary.BeneficiaryType.USER,
            account_number=self.recipient.phone_number, # Users use phone_number
            account_name='Recipient User',
            is_verified=True
        )
        
        url = '/api/v1/wallets/transfer/'
        data = {
            'amount': '2000.00',
            'pin': '1234',
            'beneficiary_id': beneficiary.id
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.sender_wallet.refresh_from_db()
        self.recipient_wallet.refresh_from_db()
        
        self.assertEqual(self.sender_wallet.balance, Decimal('7995.00'))
        self.assertEqual(self.recipient_wallet.balance, Decimal('2000.00'))

    def test_insufficient_funds(self):
        """Test rejection when sender lacks funds."""
        url = '/api/v1/wallets/transfer/'
        data = {
            'amount': '50000.00', # Greater than balance
            'pin': '1234',
            'recipient_phone': self.recipient.phone_number
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Balances should remain untouched
        self.sender_wallet.refresh_from_db()
        self.assertEqual(self.sender_wallet.balance, Decimal('10000.00'))

    def test_self_transfer_rejection(self):
        """Test rejection when sender tries to transfer to themselves."""
        url = '/api/v1/wallets/transfer/'
        data = {
            'amount': '1000.00',
            'pin': '1234',
            'recipient_phone': self.sender.phone_number
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot transfer to yourself', str(response.data))
