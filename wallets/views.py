import logging
from decimal import Decimal
from rest_framework import status, permissions, generics, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache

from .models import Wallet, Transaction, Beneficiary
from .serializers import (
    WalletSerializer, TransactionSerializer, BeneficiarySerializer,
    BankAccountVerificationSerializer, TransferFundsSerializer
)
from core.models import AuditLog, Notification
from users.models import User

logger = logging.getLogger(__name__)


class WalletView(generics.RetrieveAPIView):
    """View to retrieve wallet information."""
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        # Get or create wallet for the user
        wallet, created = Wallet.objects.get_or_create(user=self.request.user)
        return wallet


class TransactionHistoryView(generics.ListAPIView):
    """View to list user's transaction history."""
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Transaction.objects.filter(
            wallet__user=self.request.user
        ).select_related('wallet', 'recipient').order_by('-created_at')
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class TransactionDetailView(generics.RetrieveAPIView):
    """View to retrieve a specific transaction."""
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'reference'
    
    def get_queryset(self):
        return Transaction.objects.filter(
            wallet__user=self.request.user
        ).select_related('wallet', 'recipient')


class TransferFundsView(APIView):
    """View to transfer funds to another user or bank account."""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = TransferFundsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        amount = serializer.validated_data['amount']
        pin = serializer.validated_data['pin']
        description = serializer.validated_data.get('description', '')
        
        # Verify transaction PIN
        if not request.user.check_transaction_pin(pin):
            return Response(
                {"pin": ["Invalid transaction PIN"]},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Get or create wallet
            wallet = Wallet.objects.select_for_update().get(user=request.user)
            
            # Check if user has sufficient balance
            if wallet.available_balance < amount:
                return Response(
                    {"amount": ["Insufficient balance"]},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if using a saved beneficiary
            beneficiary_id = serializer.validated_data.get('beneficiary_id')
            if beneficiary_id:
                try:
                    beneficiary = Beneficiary.objects.get(
                        id=beneficiary_id,
                        user=request.user,
                        is_verified=True
                    )
                    recipient_user = None
                    recipient_account_number = beneficiary.account_number
                    recipient_bank_code = beneficiary.bank_code
                    recipient_phone = beneficiary.phone_number
                except Beneficiary.DoesNotExist:
                    return Response(
                        {"beneficiary_id": ["Invalid or unverified beneficiary"]},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                # Get recipient details from request
                recipient_phone = serializer.validated_data.get('recipient_phone')
                recipient_account_number = serializer.validated_data.get('recipient_account_number')
                recipient_bank_code = serializer.validated_data.get('recipient_bank_code')
                
                # Check if recipient is a user of the platform
                recipient_user = None
                if recipient_phone:
                    try:
                        recipient_user = User.objects.get(phone_number=recipient_phone)
                    except User.DoesNotExist:
                        pass
            
            # Generate unique reference
            reference = f"TRF-{timezone.now().strftime('%Y%m%d%H%M%S')}-{request.user.id}"
            
            # Create transaction record
            txn = Transaction.objects.create(
                wallet=wallet,
                amount=amount,
                transaction_type=Transaction.TransactionType.TRANSFER,
                status=Transaction.TransactionStatus.PENDING,
                reference=reference,
                recipient=recipient_user,
                description=description,
                metadata={
                    'recipient_phone': str(recipient_phone) if recipient_phone else None,
                    'recipient_account_number': recipient_account_number,
                    'recipient_bank_code': recipient_bank_code,
                    'initiated_by': str(request.user.phone_number)
                }
            )
            
            try:
                # For internal transfers (to another user)
                if recipient_user:
                    recipient_wallet = Wallet.objects.select_for_update().get(user=recipient_user)
                    
                    # Deduct from sender
                    wallet.balance -= amount
                    wallet.save(update_fields=['balance'])
                    
                    # Add to recipient
                    recipient_wallet.balance += amount
                    recipient_wallet.save(update_fields=['balance'])
                    
                    # Update transaction status
                    txn.status = Transaction.TransactionStatus.COMPLETED
                    txn.save(update_fields=['status'])
                    
                    # Log the successful transfer
                    AuditLog.log_action(
                        action='transfer_completed',
                        user=request.user,
                        ip_address=request.META.get('REMOTE_ADDR'),
                        user_agent=request.META.get('HTTP_USER_AGENT'),
                        data={
                            'amount': str(amount),
                            'recipient': str(recipient_user.phone_number),
                            'reference': reference
                        }
                    )
                    
                    # Create notification for recipient
                    Notification.create_notification(
                        user=recipient_user,
                        title="Funds Received",
                        message=f"You have received ₦{amount:,.2f} from {request.user.get_full_name() or request.user.phone_number}",
                        notification_type=Notification.NotificationType.TRANSACTION,
                        action_url=f"/transactions/{reference}",
                        metadata={
                            'transaction_reference': reference,
                            'amount': str(amount),
                            'sender_phone': str(request.user.phone_number),
                            'sender_name': request.user.get_full_name()
                        }
                    )
                    
                    return Response({
                        "status": "success",
                        "message": "Transfer successful",
                        "reference": reference,
                        "amount": amount,
                        "recipient": str(recipient_user.phone_number),
                        "recipient_name": recipient_user.get_full_name()
                    })
                
                # For external transfers (to bank account or mobile money)
                else:
                    # TODO: Integrate with payment gateway for external transfers
                    # This is a placeholder for the actual integration
                    
                    # For now, we'll simulate a successful transfer
                    wallet.balance -= amount
                    wallet.save(update_fields=['balance'])
                    
                    txn.status = Transaction.TransactionStatus.COMPLETED
                    txn.save(update_fields=['status'])
                    
                    # Log the successful transfer
                    recipient_info = recipient_phone or f"Bank: {recipient_account_number}"
                    AuditLog.log_action(
                        action='external_transfer_completed',
                        user=request.user,
                        ip_address=request.META.get('REMOTE_ADDR'),
                        user_agent=request.META.get('HTTP_USER_AGENT'),
                        data={
                            'amount': str(amount),
                            'recipient': recipient_info,
                            'reference': reference
                        }
                    )
                    
                    return Response({
                        "status": "success",
                        "message": "Transfer initiated successfully",
                        "reference": reference,
                        "amount": amount,
                        "recipient": recipient_info
                    })
            
            except Exception as e:
                logger.error(f"Transfer failed: {str(e)}", exc_info=True)
                
                # Update transaction status to failed
                txn.status = Transaction.TransactionStatus.FAILED
                txn.metadata['error'] = str(e)
                txn.save(update_fields=['status', 'metadata'])
                
                # Log the failed transfer
                AuditLog.log_action(
                    action='transfer_failed',
                    user=request.user,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT'),
                    data={
                        'amount': str(amount),
                        'error': str(e),
                        'reference': reference
                    },
                    status='error',
                    error_message=str(e)
                )
                
                return Response(
                    {"detail": "Transfer failed. Please try again later."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class BeneficiaryViewSet(viewsets.ModelViewSet):
    """ViewSet for managing beneficiaries."""
    serializer_class = BeneficiarySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # For schema generation, return an empty queryset
        if getattr(self, 'swagger_fake_view', False):
            return Beneficiary.objects.none()
        return Beneficiary.objects.filter(owner=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
        
        # Log the beneficiary creation
        AuditLog.log_action(
            action='beneficiary_created',
            user=self.request.user,
            ip_address=self.request.META.get('REMOTE_ADDR'),
            user_agent=self.request.META.get('HTTP_USER_AGENT'),
            data=serializer.data
        )
    
    def perform_destroy(self, instance):
        # Log the beneficiary deletion
        AuditLog.log_action(
            action='beneficiary_deleted',
            user=self.request.user,
            ip_address=self.request.META.get('REMOTE_ADDR'),
            user_agent=self.request.META.get('HTTP_USER_AGENT'),
            data={
                'beneficiary_id': str(instance.id),
                'name': instance.name,
                'type': instance.beneficiary_type
            }
        )
        instance.delete()
    
    @action(detail=False, methods=['post'])
    def verify_account(self, request):
        """Verify a bank account number."""
        serializer = BankAccountVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        account_number = serializer.validated_data['account_number']
        bank_code = serializer.validated_data['bank_code']
        
        # TODO: Integrate with a bank account verification service
        # This is a placeholder for the actual integration
        
        # For demo purposes, return a mock response
        # In a real implementation, this would call an external API
        return Response({
            "status": "success",
            "account_number": account_number,
            "account_name": "JOHN DOE",  # This would come from the API
            "bank_code": bank_code,
            "bank_name": "Test Bank"  # This would come from the API
        })


class DepositFundsView(APIView):
    """View to initiate a deposit into the user's wallet."""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        amount = request.data.get('amount')
        
        try:
            amount = Decimal(amount)
            if amount <= 0:
                raise ValueError("Amount must be greater than zero")
        except (TypeError, ValueError):
            return Response(
                {"amount": ["A valid amount greater than zero is required"]},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate a unique reference
        reference = f"DEP-{timezone.now().strftime('%Y%m%d%H%M%S')}-{request.user.id}"
        
        # Create a pending deposit transaction
        wallet = Wallet.objects.get(user=request.user)
        txn = Transaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type=Transaction.TransactionType.DEPOSIT,
            status=Transaction.TransactionStatus.PENDING,
            reference=reference,
            description=f"Wallet deposit of ₦{amount:,.2f}",
            metadata={
                'initiated_by': str(request.user.phone_number)
            }
        )
        
        # TODO: Integrate with payment gateway
        # This is a placeholder for the actual integration
        
        # For demo purposes, we'll simulate a successful deposit after a short delay
        # In a real implementation, this would redirect to a payment page or process the payment
        
        # Log the deposit initiation
        AuditLog.log_action(
            action='deposit_initiated',
            user=request.user,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            data={
                'amount': str(amount),
                'reference': reference
            }
        )
        
        return Response({
            "status": "pending",
            "message": "Deposit initiated",
            "reference": reference,
            "amount": amount,
            "payment_url": f"/api/v1/payments/{reference}/process"  # This would be the actual payment URL
        })


class WithdrawFundsView(APIView):
    """View to initiate a withdrawal from the user's wallet."""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = TransferFundsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        amount = serializer.validated_data['amount']
        pin = serializer.validated_data['pin']
        
        # Verify transaction PIN
        if not request.user.check_transaction_pin(pin):
            return Response(
                {"pin": ["Invalid transaction PIN"]},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user has sufficient balance
        wallet = Wallet.objects.select_for_update().get(user=request.user)
        if wallet.available_balance < amount:
            return Response(
                {"amount": ["Insufficient balance"]},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate a unique reference
        reference = f"WTH-{timezone.now().strftime('%Y%m%d%H%M%S')}-{request.user.id}"
        
        # Create a pending withdrawal transaction
        txn = Transaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.TransactionStatus.PENDING,
            reference=reference,
            description=f"Withdrawal of ₦{amount:,.2f}",
            metadata={
                'initiated_by': str(request.user.phone_number),
                'recipient_account_number': serializer.validated_data.get('recipient_account_number'),
                'recipient_bank_code': serializer.validated_data.get('recipient_bank_code'),
                'recipient_phone': serializer.validated_data.get('recipient_phone')
            }
        )
        
        try:
            # Reserve the funds
            wallet.balance -= amount
            wallet.save(update_fields=['balance'])
            
            # TODO: Integrate with payment gateway for processing the withdrawal
            # This is a placeholder for the actual integration
            
            # For demo purposes, we'll simulate a successful withdrawal
            txn.status = Transaction.TransactionStatus.COMPLETED
            txn.save(update_fields=['status'])
            
            # Log the successful withdrawal
            AuditLog.log_action(
                action='withdrawal_completed',
                user=request.user,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                data={
                    'amount': str(amount),
                    'reference': reference
                }
            )
            
            return Response({
                "status": "success",
                "message": "Withdrawal completed successfully",
                "reference": reference,
                "amount": amount
            })
            
        except Exception as e:
            logger.error(f"Withdrawal failed: {str(e)}", exc_info=True)
            
            # Update transaction status to failed
            txn.status = Transaction.TransactionStatus.FAILED
            txn.metadata['error'] = str(e)
            txn.save(update_fields=['status', 'metadata'])
            
            # Refund the reserved amount
            wallet.balance += amount
            wallet.save(update_fields=['balance'])
            
            # Log the failed withdrawal
            AuditLog.log_action(
                action='withdrawal_failed',
                user=request.user,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                data={
                    'amount': str(amount),
                    'reference': reference,
                    'error': str(e)
                },
                status='error',
                error_message=str(e)
            )
            
            return Response(
                {"detail": "Withdrawal failed. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
