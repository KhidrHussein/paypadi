from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from wallets.models import Wallet, Transaction, Beneficiary
from users.models import User
from decimal import Decimal

class RecentBeneficiariesTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+2348011111111",
            password="password123",
            first_name="Sender",
            last_name="User"
        )
        self.wallet = Wallet.objects.get(user=self.user)
        self.wallet.balance = Decimal("10000.00")
        self.wallet.save()
        
        self.recipient_user = User.objects.create_user(
            phone_number="+2348022222222",
            password="password123",
            first_name="Recipient",
            last_name="User"
        )
        # Recipient wallet is created by signal or signal-like logic usually.
        # Ensure it exists and has enough balance if needed.
        
        self.client.force_authenticate(user=self.user)
        self.url = reverse('beneficiary-recent')

    def test_recent_beneficiaries_empty(self):
        """Test with no transactions."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_recent_beneficiaries_internal_transfer(self):
        """Test with an internal transfer."""
        Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal("1000.00"),
            transaction_type=Transaction.TransactionType.TRANSFER,
            status=Transaction.TransactionStatus.COMPLETED,
            recipient=self.recipient_user,
            description="Transfer to Recipient User"
        )
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['account_number'], "8022222222")
        self.assertEqual(response.data[0]['beneficiary_type'], "user")
        self.assertFalse(response.data[0]['is_saved'])

    def test_recent_beneficiaries_external_transfer(self):
        """Test with an external bank transfer."""
        Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal("2000.00"),
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.TransactionStatus.COMPLETED,
            metadata={
                'recipient_account': '0123456789',
                'recipient_bank_code': '058',
                'bank_name': 'GTBank'
            },
            description="Withdrawal to John Doe"
        )
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['account_number'], "0123456789")
        self.assertEqual(response.data[0]['account_name'], "John Doe")
        self.assertFalse(response.data[0]['is_saved'])

    def test_recent_beneficiaries_saved_match(self):
        """Test that matching saved beneficiaries are identified."""
        # Create a saved beneficiary
        beneficiary = Beneficiary.objects.create(
            owner=self.user,
            beneficiary_type=Beneficiary.BeneficiaryType.BANK,
            account_number="9876543210",
            account_name="Saved Person",
            bank_code="011",
            bank_name="First Bank"
        )
        
        # Create a transaction to this person
        Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal("500.00"),
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.TransactionStatus.COMPLETED,
            metadata={
                'recipient_account': '9876543210',
                'recipient_bank_code': '011'
            }
        )
        
        response = self.client.get(self.url)
        self.assertEqual(len(response.data), 1)
        self.assertTrue(response.data[0]['is_saved'])
        self.assertEqual(str(response.data[0]['id']), str(beneficiary.id))

    def test_recent_beneficiaries_uniqueness_and_order(self):
        """Test that duplicates are removed and order is correct (most recent first)."""
        # 1. First transfer to Bank Account A
        Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal("100.00"),
            transaction_type=Transaction.TransactionType.TRANSFER,
            status=Transaction.TransactionStatus.COMPLETED,
            metadata={'recipient_account': 'AAAAA', 'recipient_bank_code': '001'},
            description="to Alice"
        )
        # 2. Second transfer to Bank Account B
        Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal("200.00"),
            transaction_type=Transaction.TransactionType.TRANSFER,
            status=Transaction.TransactionStatus.COMPLETED,
            metadata={'recipient_account': 'BBBBB', 'recipient_bank_code': '002'},
            description="to Bob"
        )
        # 3. Third transfer (again) to Bank Account A
        Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal("300.00"),
            transaction_type=Transaction.TransactionType.TRANSFER,
            status=Transaction.TransactionStatus.COMPLETED,
            metadata={'recipient_account': 'AAAAA', 'recipient_bank_code': '001'},
            description="to Alice"
        )
        
        response = self.client.get(self.url)
        self.assertEqual(len(response.data), 2)
        # Most recent should be A (from transaction 3)
        self.assertEqual(response.data[0]['account_number'], "AAAAA")
        self.assertEqual(response.data[1]['account_number'], "BBBBB")
