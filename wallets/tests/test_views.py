import json
from decimal import Decimal
from django.urls import reverse
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone

from ..models import Wallet, Transaction, Beneficiary
from core.models import AuditLog, Notification

User = get_user_model()


class WalletViewTests(TestCase):
    """Test cases for Wallet views."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        
        # Create test users
        self.user1 = User.objects.create_user(
            phone_number='+2347000000001',
            password='testpass123',
            first_name='John',
            last_name='Doe',
            email='john.doe@example.com'
        )
        
        self.user2 = User.objects.create_user(
            phone_number='+2347000000002',
            password='testpass123',
            first_name='Jane',
            last_name='Doe',
            email='jane.doe@example.com'
        )
        
        # Create wallets for users
        self.wallet1 = Wallet.objects.create(user=self.user1, balance=Decimal('10000.00'))
        self.wallet2 = Wallet.objects.create(user=self.user2, balance=Decimal('5000.00'))
        
        # Authenticate the first user
        self.client.force_authenticate(user=self.user1)
        
        # Set transaction PIN for user1
        self.user1.set_transaction_pin('1234')
        
    def test_get_wallet_balance(self):
        """Test retrieving wallet balance."""
        url = reverse('wallet-detail')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['balance'], '10000.00')
        self.assertEqual(response.data['available_balance'], '10000.00')
        self.assertEqual(response.data['currency'], 'NGN')
    
    def test_transfer_funds_to_user(self):
        """Test transferring funds to another user."""
        url = reverse('transfer-funds')
        data = {
            'amount': '2000.00',
            'pin': '1234',
            'recipient_phone': '+2347000000002',
            'description': 'Test transfer'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['amount'], '2000.00')
        
        # Check if wallets were updated
        self.wallet1.refresh_from_db()
        self.wallet2.refresh_from_db()
        
        self.assertEqual(self.wallet1.balance, Decimal('8000.00'))
        self.assertEqual(self.wallet2.balance, Decimal('7000.00'))
        
        # Check if transaction was created
        transaction = Transaction.objects.filter(reference=response.data['reference']).first()
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.amount, Decimal('2000.00'))
        self.assertEqual(transaction.status, Transaction.TransactionStatus.COMPLETED)
        
        # Check if notification was created for recipient
        notification = Notification.objects.filter(
            user=self.user2,
            notification_type=Notification.NotificationType.TRANSACTION
        ).first()
        self.assertIsNotNone(notification)
        self.assertIn('2000.00', notification.message)
    
    def test_transfer_insufficient_funds(self):
        """Test transferring with insufficient funds."""
        url = reverse('transfer-funds')
        data = {
            'amount': '20000.00',  # More than user's balance
            'pin': '1234',
            'recipient_phone': '+2347000000002',
            'description': 'Test transfer with insufficient funds'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('amount', response.data)
        self.assertEqual(response.data['amount'][0], 'Insufficient balance')
    
    def test_transfer_invalid_pin(self):
        """Test transferring with invalid PIN."""
        url = reverse('transfer-funds')
        data = {
            'amount': '1000.00',
            'pin': '9999',  # Wrong PIN
            'recipient_phone': '+2347000000002',
            'description': 'Test transfer with invalid PIN'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('pin', response.data)
        self.assertEqual(response.data['pin'][0], 'Invalid transaction PIN')
    
    def test_deposit_funds(self):
        """Test initiating a deposit."""
        url = reverse('deposit-funds')
        data = {'amount': '5000.00'}
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(response.data['amount'], '5000.00')
        
        # Check if transaction was created
        transaction = Transaction.objects.filter(reference=response.data['reference']).first()
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.amount, Decimal('5000.00'))
        self.assertEqual(transaction.status, Transaction.TransactionStatus.PENDING)
    
    def test_withdraw_funds(self):
        """Test initiating a withdrawal."""
        url = reverse('withdraw-funds')
        data = {
            'amount': '3000.00',
            'pin': '1234',
            'recipient_account_number': '0123456789',
            'recipient_bank_code': '058',
            'description': 'Test withdrawal'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['amount'], '3000.00')
        
        # Check if wallet was updated
        self.wallet1.refresh_from_db()
        self.assertEqual(self.wallet1.balance, Decimal('7000.00'))
        
        # Check if transaction was created
        transaction = Transaction.objects.filter(reference=response.data['reference']).first()
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.amount, Decimal('3000.00'))
        self.assertEqual(transaction.status, Transaction.TransactionStatus.COMPLETED)
    
    def test_get_transaction_history(self):
        """Test retrieving transaction history."""
        # Create some test transactions
        Transaction.objects.create(
            wallet=self.wallet1,
            amount=Decimal('1000.00'),
            transaction_type=Transaction.TransactionType.TRANSFER,
            status=Transaction.TransactionStatus.COMPLETED,
            reference='TEST-001',
            recipient=self.user2,
            description='Test transaction 1'
        )
        
        Transaction.objects.create(
            wallet=self.wallet1,
            amount=Decimal('2000.00'),
            transaction_type=Transaction.TransactionType.DEPOSIT,
            status=Transaction.TransactionStatus.COMPLETED,
            reference='TEST-002',
            description='Test deposit 1'
        )
        
        url = reverse('transaction-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['results'][0]['reference'], 'TEST-002')
        self.assertEqual(response.data['results'][1]['reference'], 'TEST-001')
    
    def test_beneficiary_management(self):
        """Test adding and managing beneficiaries."""
        # Add a beneficiary
        url = reverse('beneficiary-list')
        data = {
            'name': 'Test Beneficiary',
            'beneficiary_type': 'bank_account',
            'account_number': '0123456789',
            'bank_code': '058',
            'bank_name': 'Guaranty Trust Bank',
            'phone_number': '+2347000000003',
            'email': 'beneficiary@example.com',
            'is_verified': True
        }
        
        # Test creating a beneficiary
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Test Beneficiary')
        
        beneficiary_id = response.data['id']
        
        # Test listing beneficiaries
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        
        # Test getting beneficiary details
        detail_url = reverse('beneficiary-detail', args=[beneficiary_id])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Test Beneficiary')
        
        # Test deleting a beneficiary
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify beneficiary was deleted
        response = self.client.get(url)
        self.assertEqual(len(response.data), 0)
    
    def test_verify_bank_account(self):
        """Test bank account verification."""
        url = reverse('beneficiary-verify-account')
        data = {
            'account_number': '0123456789',
            'bank_code': '058'  # GTBank code for testing
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['account_number'], '0123456789')
        self.assertEqual(response.data['bank_code'], '058')
        self.assertEqual(response.data['account_name'], 'JOHN DOE')  # Mocked response
        self.assertEqual(response.data['bank_name'], 'Test Bank')  # Mocked response
    
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_transaction_webhook(self):
        """Test transaction webhook for processing payments."""
        # This would test the webhook that processes payment callbacks
        # from the payment gateway
        pass  # Implement based on your payment gateway's webhook requirements


class TransactionConcurrencyTests(TestCase):
    """Test concurrent transaction handling."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number='+2347000000001',
            password='testpass123',
            first_name='Concurrent',
            last_name='Test',
            email='concurrent@example.com'
        )
        self.wallet = Wallet.objects.create(user=self.user, balance=Decimal('10000.00'))
        self.client.force_authenticate(user=self.user)
        self.user.set_transaction_pin('1234')
        
        # Create a recipient
        self.recipient = User.objects.create_user(
            phone_number='+2347000000002',
            password='testpass123',
            first_name='Recipient',
            last_name='User',
            email='recipient@example.com'
        )
        self.recipient_wallet = Wallet.objects.create(user=self.recipient, balance=Decimal('0.00'))
    
    def test_concurrent_transfers(self):
        """Test that concurrent transfers don't result in race conditions."""
        import threading
        from concurrent.futures import ThreadPoolExecutor
        
        url = reverse('transfer-funds')
        balance_before = self.wallet.balance
        num_transactions = 5
        amount = Decimal('100.00')
        
        def make_transfer():
            data = {
                'amount': str(amount),
                'pin': '1234',
                'recipient_phone': '+2347000000002',
                'description': 'Concurrent transfer test'
            }
            response = self.client.post(url, data, format='json')
            return response
        
        # Create multiple threads to simulate concurrent transfers
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_transfer) for _ in range(num_transactions)]
            responses = [future.result() for future in futures]
        
        # Check all responses were successful
        for response in responses:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Refresh wallet data
        self.wallet.refresh_from_db()
        self.recipient_wallet.refresh_from_db()
        
        # Check final balances
        total_transferred = amount * num_transactions
        self.assertEqual(self.wallet.balance, balance_before - total_transferred)
        self.assertEqual(self.recipient_wallet.balance, total_transferred)
        
        # Check transaction count
        transactions = Transaction.objects.filter(wallet=self.wallet, transaction_type='transfer')
        self.assertEqual(transactions.count(), num_transactions)
