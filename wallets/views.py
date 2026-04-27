import logging
from decimal import Decimal
from rest_framework import status, permissions, generics, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import Wallet, Transaction, Beneficiary
from .serializers import (
    WalletSerializer, TransactionSerializer, BeneficiarySerializer,
    BankAccountVerificationSerializer, TransferFundsSerializer,
    RecentBeneficiarySerializer
)
from core.models import AuditLog, Notification
from users.models import User, DriverPayoutAccount

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
                'name': instance.account_name,
                'type': instance.beneficiary_type
            }
        )
        instance.delete()
    
    @swagger_auto_schema(
        request_body=BankAccountVerificationSerializer,
        responses={200: 'Account verified', 400: 'Invalid input'},
        operation_description="Verify a bank account number and get its holder name."
    )
    @action(detail=False, methods=['post'])
    def verify_account(self, request):
        """Verify a bank account number."""
        serializer = BankAccountVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        account_number = serializer.validated_data['account_number']
        bank_code = serializer.validated_data['bank_code']
        
        try:
            from wallets.services.payment_service import PaymentService
            from wallets.exceptions import PaymentError
            payment_service = PaymentService()
            result = payment_service.verify_bank_account(
                account_number=account_number,
                bank_code=bank_code
            )
            return Response(result, status=status.HTTP_200_OK)
        except PaymentError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error verifying account: {str(e)}", exc_info=True)
            return Response({'detail': 'An error occurred during verification.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        responses={200: RecentBeneficiarySerializer(many=True)},
        operation_description="Get 5 most recent unique recipients from your completed transfers or withdrawals."
    )
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get 5 most recent unique recipients from completed transfers/withdrawals."""
        user = request.user
        
        # Get last 50 completed outgoing transactions to ensure we find enough unique recipients
        transactions = Transaction.objects.filter(
            wallet__user=user,
            transaction_type__in=[Transaction.TransactionType.TRANSFER, Transaction.TransactionType.WITHDRAWAL],
            status=Transaction.TransactionStatus.COMPLETED
        ).select_related('recipient').order_by('-created_at')[:50]
        
        recent_recipients = []
        seen = set()
        
        # Pre-fetch saved beneficiaries for matching to avoid N+1 queries
        saved_beneficiaries = Beneficiary.objects.filter(owner=user)
        beneficiary_map = {}
        for b in saved_beneficiaries:
            # Key by (account_number, bank_code)
            key = (b.account_number, b.bank_code)
            beneficiary_map[key] = b

        for txn in transactions:
            if len(recent_recipients) >= 5:
                break
                
            rec_data = None
            
            if txn.recipient: # Internal transfer to another Paypadi user
                # Primary identifier for users is their phone number (acting as account number)
                phone = str(txn.recipient.phone_number)
                # Normalize to 10 digits if needed, but here we use the full number
                phone_10 = phone[-10:]
                
                # Check both full and 10-digit versions in seen/saved
                key = (phone_10, None) 
                if key in seen: continue
                seen.add(key)
                
                saved = beneficiary_map.get(key) or beneficiary_map.get((phone, None))
                if saved:
                    rec_data = {
                        'id': saved.id,
                        'beneficiary_type': saved.beneficiary_type,
                        'account_number': saved.account_number,
                        'account_name': saved.account_name,
                        'bank_code': saved.bank_code,
                        'bank_name': saved.bank_name,
                        'is_saved': True,
                    }
                else:
                    rec_data = {
                        'id': None,
                        'beneficiary_type': 'user',
                        'account_number': phone_10,
                        'account_name': txn.recipient.get_full_name() or phone_10,
                        'bank_code': None,
                        'bank_name': 'Paypadi',
                        'is_saved': False,
                    }
            
            elif 'recipient_account' in txn.metadata: # External bank transfer
                acc_no = txn.metadata.get('recipient_account')
                bank_code = txn.metadata.get('recipient_bank_code')
                
                if not acc_no: continue
                
                key = (acc_no, bank_code)
                if key in seen: continue
                seen.add(key)
                
                saved = beneficiary_map.get(key)
                if saved:
                    rec_data = {
                        'id': saved.id,
                        'beneficiary_type': saved.beneficiary_type,
                        'account_number': saved.account_number,
                        'account_name': saved.account_name,
                        'bank_code': saved.bank_code,
                        'bank_name': saved.bank_name,
                        'is_saved': True,
                    }
                else:
                    # Try to get name from description or metadata if available
                    name = txn.metadata.get('account_name')
                    if not name and txn.description:
                        # Common pattern: "Transfer to NAME" or "Withdrawal to NAME"
                        if "to " in txn.description:
                            name = txn.description.split("to ", 1)[1]
                    
                    rec_data = {
                        'id': None,
                        'beneficiary_type': 'bank',
                        'account_number': acc_no,
                        'account_name': name or 'Recipient',
                        'bank_code': bank_code,
                        'bank_name': txn.metadata.get('bank_name', 'Bank'),
                        'is_saved': False,
                    }
            
            if rec_data:
                rec_data['last_transaction_at'] = txn.created_at
                recent_recipients.append(rec_data)
                
        serializer = RecentBeneficiarySerializer(recent_recipients, many=True)
        return Response({
            'status': True,
            'message': 'Recent beneficiaries retrieved successfully',
            'data': serializer.data
        })


class DepositFundsView(APIView):
    """View to initiate a deposit into the user's wallet."""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'amount': openapi.Schema(type=openapi.TYPE_NUMBER, description='Amount to deposit'),
            },
            required=['amount']
        ),
        responses={200: 'Deposit initiated', 400: 'Bad Request'}
    )
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
        
        try:
            from wallets.services.payment_service import PaymentService
            from wallets.exceptions import PaymentError
            
            payment_service = PaymentService()
            result = payment_service.initialize_payment(
                user=request.user,
                amount=amount,
                transaction_type=Transaction.TransactionType.DEPOSIT,
                description=f"Wallet deposit of ₦{amount:,.2f}"
            )
            
            # Log the deposit initiation
            AuditLog.log_action(
                action='deposit_initiated',
                user=request.user,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                data={'amount': str(amount)}
            )
            
            return Response(result, status=status.HTTP_200_OK)
            
        except PaymentError as e:
            logger.error(f"Deposit initiation failed: {str(e)}")
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error in deposit: {str(e)}", exc_info=True)
            return Response({'detail': 'An error occurred while initiating deposit.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WithdrawFundsView(APIView):
    """View to initiate a withdrawal from the user's wallet."""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        request_body=TransferFundsSerializer,
        responses={200: 'Withdrawal completed', 400: 'Bad Request'}
    )
    def post(self, request):
        # Check for default payout account if details are missing
        data = request.data.copy()
        if not (data.get('recipient_account_number') and data.get('recipient_bank_code')):
            # Check if user is a driver (assuming 'driver' is the stored value for UserRole.DRIVER)
            if hasattr(request.user, 'role') and request.user.role == 'driver':
                payout_account = DriverPayoutAccount.objects.filter(driver=request.user, is_primary=True).first()
                if payout_account:
                    data['recipient_account_number'] = payout_account.account_number
                    data['recipient_bank_code'] = payout_account.bank_code

        serializer = TransferFundsSerializer(data=data)
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
        
        try:
            from wallets.services.payment_service import PaymentService
            from wallets.exceptions import PaymentError, InsufficientFundsError, InvalidAccountError
            
            payment_service = PaymentService()
            result = payment_service.transfer_funds(
                sender=request.user,
                amount=amount,
                recipient_account=serializer.validated_data['recipient_account_number'],
                recipient_bank_code=serializer.validated_data['recipient_bank_code'],
                description=f"Withdrawal of ₦{amount:,.2f}",
                metadata={
                    'pin_verified': True,
                    **(serializer.validated_data.get('metadata', {}))
                },
                transaction_type=Transaction.TransactionType.WITHDRAWAL
            )
            
            # Log the successful withdrawal
            AuditLog.log_action(
                action='withdrawal_completed',
                user=request.user,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                data={'amount': str(amount)}
            )
            
            return Response(result, status=status.HTTP_200_OK)
            
        except InsufficientFundsError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except InvalidAccountError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except PaymentError as e:
            logger.error(f"Withdrawal failed: {str(e)}")
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error in withdrawal: {str(e)}", exc_info=True)
            return Response({'detail': 'An error occurred while processing your withdrawal.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
