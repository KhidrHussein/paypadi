from rest_framework import serializers
from django.db import transaction
from decimal import Decimal
from .models import Wallet, Transaction, Beneficiary, TransactionStatus
from users.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone


class WalletSerializer(serializers.ModelSerializer):
    """Serializer for Wallet model."""
    balance = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    reserved_balance = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    available_balance = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    currency = serializers.CharField(read_only=True)
    
    class Meta:
        model = Wallet
        fields = [
            'id', 'balance', 'reserved_balance', 'available_balance',
            'currency', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for Transaction model."""
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=True
    )
    status = serializers.CharField(read_only=True)
    reference = serializers.CharField(read_only=True)
    recipient_phone = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Recipient's phone number (required for transfers)"
    )
    recipient_account_number = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Recipient's account number (required for bank transfers)"
    )
    recipient_bank_code = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Recipient's bank code (required for bank transfers)"
    )
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'amount', 'transaction_type', 'status', 'reference',
            'description', 'metadata', 'created_at', 'recipient_phone',
            'recipient_account_number', 'recipient_bank_code'
        ]
        read_only_fields = [
            'id', 'status', 'reference', 'metadata', 'created_at'
        ]
    
    def validate(self, attrs):
        request = self.context.get('request')
        transaction_type = attrs.get('transaction_type')
        
        # Validate transfer-specific fields
        if transaction_type == Transaction.TransactionType.TRANSFER:
            if not attrs.get('recipient_phone') and not attrs.get('recipient_account_number'):
                raise serializers.ValidationError(
                    "Either recipient_phone or recipient_account_number is required for transfers"
                )
            
            if attrs.get('recipient_account_number') and not attrs.get('recipient_bank_code'):
                raise serializers.ValidationError(
                    "recipient_bank_code is required for bank transfers"
                )
        
        # Validate amount is positive
        if attrs['amount'] <= Decimal('0'):
            raise serializers.ValidationError(
                {"amount": "Amount must be greater than zero"}
            )
        
        return attrs


class BeneficiarySerializer(serializers.ModelSerializer):
    """Serializer for Beneficiary model."""
    account_number = serializers.CharField(
        required=True,
        help_text="Account number (for bank transfers)"
    )
    bank_code = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Bank code (for bank transfers)",
        allow_null=True
    )
    bank_name = serializers.CharField(
        read_only=True,
        help_text="Bank name (auto-filled from bank code)",
        allow_blank=True
    )
    account_name = serializers.CharField(
        required=True,
        help_text="Name of the account holder"
    )
    
    class Meta:
        model = Beneficiary
        fields = [
            'id', 'beneficiary_type', 'account_number', 'account_name',
            'bank_code', 'bank_name', 'is_verified', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'bank_name', 'is_verified', 'created_at', 'updated_at'
        ]
    
    def validate(self, attrs):
        beneficiary_type = attrs.get('beneficiary_type')
        
        if beneficiary_type == Beneficiary.BeneficiaryType.BANK:
            if not attrs.get('account_number'):
                raise serializers.ValidationError(
                    {"account_number": "Account number is required for bank beneficiaries"}
                )
            if not attrs.get('bank_code'):
                raise serializers.ValidationError(
                    {"bank_code": "Bank code is required for bank beneficiaries"}
                )
        
        return attrs


class BankAccountVerificationSerializer(serializers.Serializer):
    """Serializer for bank account verification."""
    account_number = serializers.CharField(required=True)
    bank_code = serializers.CharField(required=True)
    
    class Meta:
        fields = ['account_number', 'bank_code']


class TransferFundsSerializer(serializers.Serializer):
    """Serializer for transferring funds."""
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=True,
        min_value=Decimal('0.01')
    )
    pin = serializers.CharField(
        required=True,
        write_only=True,
        min_length=4,
        max_length=6,
        help_text="User's transaction PIN"
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255
    )
    
    # For wallet-to-wallet transfers
    recipient_phone = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Recipient's phone number (for wallet transfers)"
    )
    
    # For bank transfers
    recipient_account_number = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Recipient's account number (for bank transfers)"
    )
    recipient_bank_code = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Recipient's bank code (for bank transfers)"
    )
    
    # For beneficiary transfers
    beneficiary_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="ID of a saved beneficiary (alternative to providing recipient details)"
    )
    
    def validate(self, attrs):
        """Validate the transfer request."""
        recipient_phone = attrs.get('recipient_phone')
        recipient_account = attrs.get('recipient_account_number')
        recipient_bank = attrs.get('recipient_bank_code')
        beneficiary_id = attrs.get('beneficiary_id')

        # Check if either beneficiary_id or recipient details are provided
        if not any([beneficiary_id, recipient_phone, (recipient_account and recipient_bank)]):
            raise serializers.ValidationError(
                "Either beneficiary_id or recipient details (phone or account+bank) must be provided."
            )

        # If beneficiary_id is provided, no need for other recipient details
        if beneficiary_id and any([recipient_phone, recipient_account, recipient_bank]):
            raise serializers.ValidationError(
                "Do not provide recipient details when using beneficiary_id."
            )

        # If no beneficiary_id, check for valid recipient details
        if not beneficiary_id:
            if recipient_phone and (recipient_account or recipient_bank):
                raise serializers.ValidationError(
                    "Cannot provide both phone number and bank account details."
                )
            
            if recipient_account and not recipient_bank:
                raise serializers.ValidationError("Bank code is required when providing account number.")
            
            if recipient_bank and not recipient_account:
                raise serializers.ValidationError("Account number is required when providing bank code.")

        # Verify transaction PIN
        user = self.context['request'].user
        pin = attrs.get('pin')
        if not user.check_transaction_pin(pin):
            raise serializers.ValidationError({"pin": "Invalid transaction PIN"})

        # Check if user has sufficient balance (for non-deposit transactions)
        if self.context['request'].method == 'POST':  # Only check for POST requests
            wallet = user.wallet
            if wallet.available_balance < attrs['amount']:
                raise serializers.ValidationError("Insufficient balance")

        return attrs


class PaymentInitiationSerializer(serializers.Serializer):
    """Serializer for initiating payments."""
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=True,
        min_value=Decimal('0.01'),
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    transaction_type = serializers.ChoiceField(
        choices=TransactionStatus.choices,
        required=True
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255
    )
    metadata = serializers.DictField(
        required=False,
        default=dict
    )
    
    def validate_transaction_type(self, value):
        """Validate transaction type."""
        if value not in [TransactionStatus.DEPOSIT, TransactionStatus.TRANSFER]:
            raise serializers.ValidationError(
                "Invalid transaction type. Must be 'deposit' or 'transfer'."
            )
        return value


class BankAccountVerificationSerializer(serializers.Serializer):
    """Serializer for bank account verification."""
    account_number = serializers.CharField(
        required=True,
        min_length=10,
        max_length=10,
        help_text="10-digit NUBAN account number"
    )
    bank_code = serializers.CharField(
        required=True,
        help_text="Bank code (e.g., '058' for GTBank)"
    )


class TransactionQuerySerializer(serializers.Serializer):
    """Serializer for querying transactions."""
    start_date = serializers.DateTimeField(
        required=False,
        help_text="Start date for filtering transactions (ISO 8601 format)"
    )
    end_date = serializers.DateTimeField(
        required=False,
        default=timezone.now,
        help_text="End date for filtering transactions (ISO 8601 format)"
    )
    status = serializers.ChoiceField(
        choices=TransactionStatus.choices,
        required=False,
        allow_null=True,
        help_text="Filter by transaction status"
    )
    transaction_type = serializers.ChoiceField(
        choices=TransactionStatus.choices,
        required=False,
        allow_null=True,
        help_text="Filter by transaction type"
    )
    page = serializers.IntegerField(
        min_value=1,
        default=1,
        required=False,
        help_text="Page number for pagination"
    )
    page_size = serializers.IntegerField(
        min_value=1,
        max_value=100,
        default=20,
        required=False,
        help_text="Number of items per page"
    )
    
    def validate(self, attrs):
        """Validate the query parameters."""
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')
        
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({
                'start_date': 'Start date must be before end date.'
            })
            
        return attrs
