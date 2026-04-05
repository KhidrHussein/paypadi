import json
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from wallets.models import Wallet, Transaction

User = get_user_model()

class WebhooksTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number='+2348100000088',
            password='password123',
            first_name='Webhook',
            last_name='Tester'
        )
        self.wallet = Wallet.objects.get(user=self.user)
        self.wallet.balance = Decimal('5000.00')
        self.wallet.save()
        
        self.url = '/api/v1/wallets/payments/paystack/webhook/'

    def test_transfer_success_webhook(self):
        """Test transfer.success correctly completes a pending transaction."""
        txn = Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('500.00'),
            transaction_type=Transaction.TransactionType.TRANSFER,
            status=Transaction.TransactionStatus.PENDING,
            reference='TRF-hook-123'
        )
        
        payload = {
            'event': 'transfer.success',
            'data': {'reference': 'TRF-hook-123'}
        }
        
        response = self.client.post(self.url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        txn.refresh_from_db()
        self.assertEqual(txn.status, Transaction.TransactionStatus.COMPLETED)
        
        # Balance shouldn't change on transfer success (deducted at initiation)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('5000.00'))

    def test_transfer_failed_webhook(self):
        """Test transfer.failed correctly refunds the wallet and fails transaction."""
        txn = Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('1000.00'),
            transaction_type=Transaction.TransactionType.TRANSFER,
            status=Transaction.TransactionStatus.PENDING,
            reference='TRF-hook-failed'
        )
        
        payload = {
            'event': 'transfer.failed',
            'data': {'reference': 'TRF-hook-failed'}
        }
        
        response = self.client.post(self.url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        txn.refresh_from_db()
        self.assertEqual(txn.status, Transaction.TransactionStatus.FAILED)
        
        # Balance should be refunded the 1000.00
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('6000.00'))

    def test_charge_success_webhook(self):
        """Test charge.success correctly tops up wallet balance."""
        txn = Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('2000.00'),
            transaction_type=Transaction.TransactionType.DEPOSIT,
            status=Transaction.TransactionStatus.PENDING,
            reference='DEP-hook-123'
        )
        
        payload = {
            'event': 'charge.success',
            'data': {
                'reference': 'DEP-hook-123',
                'amount': 200000 # Paystack sends amounts in kobo
            }
        }
        
        response = self.client.post(self.url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        txn.refresh_from_db()
        self.assertEqual(txn.status, Transaction.TransactionStatus.COMPLETED)
        
        # Balance should increase by 2000.00
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('7000.00'))

    def test_webhook_transaction_not_found(self):
        """Test webhook handles unknown transaction reference gracefully."""
        payload = {
            'event': 'transfer.success',
            'data': {'reference': 'UNKNOWN-REF'}
        }
        
        response = self.client.post(self.url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_transfer_reversed_on_completed_webhook(self):
        """Test transfer.reversed refunds the wallet even if transaction was already COMPLETED."""
        txn = Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('1500.00'),
            transaction_type=Transaction.TransactionType.TRANSFER,
            status=Transaction.TransactionStatus.COMPLETED,
            reference='TRF-hook-reversed'
        )
        
        payload = {
            'event': 'transfer.reversed',
            'data': {'reference': 'TRF-hook-reversed'}
        }
        
        response = self.client.post(self.url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        txn.refresh_from_db()
        self.assertEqual(txn.status, Transaction.TransactionStatus.FAILED)
        
        # Balance should be refunded the 1500.00
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('6500.00'))
