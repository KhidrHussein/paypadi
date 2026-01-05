import uuid
from enum import Enum
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.conf import settings
from users.models import User


class TransactionType(models.TextChoices):
    """Types of transactions."""
    DEPOSIT = 'deposit', 'Deposit'
    WITHDRAWAL = 'withdrawal', 'Withdrawal'
    TRANSFER = 'transfer', 'Transfer'
    REFUND = 'refund', 'Refund'
    FEE = 'fee', 'Fee'
    REVERSAL = 'reversal', 'Reversal'


class TransactionStatus(models.TextChoices):
    """Status of a transaction."""
    PENDING = 'pending', 'Pending'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    CANCELLED = 'cancelled', 'Cancelled'
    REFUNDED = 'refunded', 'Refunded'


class Wallet(models.Model):
    """Model representing a user's wallet."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet'
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0.00)]
    )
    reserved_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0.00)],
        help_text="Amount reserved for pending transactions"
    )
    currency = models.CharField(
        max_length=3,
        default='NGN',
        help_text="ISO 4217 currency code"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Virtual Account Details
    virtual_account_number = models.CharField(max_length=50, blank=True, null=True)
    virtual_bank_name = models.CharField(max_length=100, blank=True, null=True)
    virtual_account_name = models.CharField(max_length=255, blank=True, null=True)
    virtual_bank_code = models.CharField(max_length=20, blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Wallet'
        verbose_name_plural = 'Wallets'
    
    def __str__(self):
        return f"{self.user.get_full_name()}'s Wallet ({self.currency} {self.available_balance})"
    
    @property
    def available_balance(self):
        """Calculate the available balance (total balance minus reserved amount)."""
        return self.balance - self.reserved_balance
    
    def can_withdraw(self, amount):
        """Check if the wallet has sufficient available balance for withdrawal."""
        return self.available_balance >= amount
    
    def deposit(self, amount, reference='', metadata=None):
        """Deposit funds into the wallet."""
        if amount <= 0:
            raise ValueError("Deposit amount must be greater than zero")
        
        self.balance += amount
        self.save(update_fields=['balance', 'updated_at'])
        
        # Create transaction record
        Transaction.objects.create(
            wallet=self,
            amount=amount,
            transaction_type=Transaction.TransactionType.DEPOSIT,
            status=Transaction.TransactionStatus.COMPLETED,
            reference=reference,
            metadata=metadata or {}
        )
    
    def withdraw(self, amount, reference='', metadata=None):
        """Withdraw funds from the wallet."""
        if amount <= 0:
            raise ValueError("Withdrawal amount must be greater than zero")
        
        if not self.can_withdraw(amount):
            raise ValueError("Insufficient funds")
        
        self.balance -= amount
        self.save(update_fields=['balance', 'updated_at'])
        
        # Create transaction record
        Transaction.objects.create(
            wallet=self,
            amount=amount,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.TransactionStatus.COMPLETED,
            reference=reference,
            metadata=metadata or {}
        )
    
    def reserve_funds(self, amount, reference='', metadata=None):
        """Reserve funds for a pending transaction."""
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")
        
        if not self.can_withdraw(amount):
            raise ValueError("Insufficient available balance")
        
        self.reserved_balance += amount
        self.save(update_fields=['reserved_balance', 'updated_at'])
        
        # Create transaction record
        transaction = Transaction.objects.create(
            wallet=self,
            amount=amount,
            transaction_type=Transaction.TransactionType.RESERVATION,
            status=Transaction.TransactionStatus.PENDING,
            reference=reference,
            metadata=metadata or {}
        )
        
        return transaction
    
    def release_reserved_funds(self, amount, reference='', metadata=None):
        """Release reserved funds back to available balance."""
        if amount <= 0 or amount > self.reserved_balance:
            raise ValueError("Invalid amount to release")
        
        self.reserved_balance -= amount
        self.save(update_fields=['reserved_balance', 'updated_at'])
        
        # Update the original reservation transaction
        if reference:
            try:
                reservation = Transaction.objects.get(
                    reference=reference,
                    transaction_type=Transaction.TransactionType.RESERVATION,
                    status=Transaction.TransactionStatus.PENDING
                )
                reservation.status = Transaction.TransactionStatus.CANCELLED
                reservation.metadata.update(metadata or {})
                reservation.save()
            except Transaction.DoesNotExist:
                pass
    
    def complete_reservation(self, amount, reference='', metadata=None):
        """Complete a reservation by deducting the reserved amount."""
        if amount <= 0 or amount > self.reserved_balance:
            raise ValueError("Invalid amount to complete")
        
        self.reserved_balance -= amount
        self.save(update_fields=['reserved_balance', 'updated_at'])
        
        # Update the original reservation transaction
        if reference:
            try:
                reservation = Transaction.objects.get(
                    reference=reference,
                    transaction_type=Transaction.TransactionType.RESERVATION,
                    status=Transaction.TransactionStatus.PENDING
                )
                reservation.status = Transaction.TransactionStatus.COMPLETED
                reservation.metadata.update(metadata or {})
                reservation.save()
            except Transaction.DoesNotExist:
                pass


class Transaction(models.Model):
    """Model representing a wallet transaction."""
    
    class TransactionType(models.TextChoices):
        DEPOSIT = 'deposit', 'Deposit'
        WITHDRAWAL = 'withdrawal', 'Withdrawal'
        TRANSFER = 'transfer', 'Transfer'
        REFUND = 'refund', 'Refund'
        FEE = 'fee', 'Fee'
        RESERVATION = 'reservation', 'Reservation'
        ADJUSTMENT = 'adjustment', 'Adjustment'
    
    class TransactionStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices
    )
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING
    )
    reference = models.CharField(max_length=100, unique=True, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['reference']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} {self.wallet.currency} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        """Override save to generate a reference if not provided."""
        if not self.reference:
            self.reference = f"TXN{timezone.now().strftime('%Y%m%d%H%M%S')}{str(self.id)[:8].upper()}"
        super().save(*args, **kwargs)


class Beneficiary(models.Model):
    """Model representing a beneficiary for transfers."""
    
    class BeneficiaryType(models.TextChoices):
        USER = 'user', 'User'
        BANK = 'bank', 'Bank Account'
        MOBILE = 'mobile', 'Mobile Money'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='beneficiaries'
    )
    beneficiary_type = models.CharField(
        max_length=20,
        choices=BeneficiaryType.choices,
        default=BeneficiaryType.USER
    )
    account_number = models.CharField(max_length=50)
    account_name = models.CharField(max_length=255)
    bank_code = models.CharField(max_length=10, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'Beneficiaries'
        unique_together = ['owner', 'account_number', 'bank_code']
        ordering = ['-created_at']
    
    def __str__(self):
        if self.beneficiary_type == self.BeneficiaryType.USER:
            return f"{self.account_name} (User)"
        return f"{self.account_name} - {self.bank_name or ''} ({self.account_number})"
