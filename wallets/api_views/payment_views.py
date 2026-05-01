"""
API views for payment operations.
"""
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import permission_classes, api_view
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import transaction
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from ..models import Transaction, Wallet
from ..serializers import (
    PaymentInitiationSerializer,
    TransferFundsSerializer,
    BankAccountVerificationSerializer,
    TransactionSerializer,
    UserLookupRequestSerializer,
    UserLookupResponseSerializer
)
from ..services.payment_service import PaymentService
from ..exceptions import (
    PaymentError,
    InsufficientFundsError,
    InvalidAccountError
)
# Import User model to support checking recipient existence
from django.contrib.auth import get_user_model
User = get_user_model()

logger = logging.getLogger(__name__)

class UserLookupView(APIView):
    """
    API view for looking up a user/paypadi recipient.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        request_body=UserLookupRequestSerializer,
        responses={200: UserLookupResponseSerializer, 404: 'User not found', 400: 'Bad Request'}
    )
    def post(self, request):
        """Lookup user details by phone number."""
        serializer = UserLookupRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        phone_number = serializer.validated_data.get('phone_number') or serializer.validated_data.get('account_number')
        
        # Extract the core digits to ensure flexible matching (e.g., removing leading '0' or country codes)
        core_number = ''.join(filter(str.isdigit, str(phone_number)))
        if len(core_number) >= 10:
            core_number = core_number[-10:]
            
        if not core_number:
            return Response({'detail': 'Invalid phone number or account number format.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # Flexible query: search using the core 10-digit number
            user = User.objects.filter(phone_number__icontains=core_number).first()
            
            if not user:
                wallet = Wallet.objects.filter(virtual_account_number=phone_number).first()
                if wallet:
                    user = wallet.user
                    
            if not user:
                return Response(
                    {'detail': 'User not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
                
            if not user.is_active:
                return Response(
                    {'detail': 'User account is not active.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
             
            # Get 10-digit phone number (last 10 digits)
            phone_str = str(user.phone_number)
            ten_digit_phone = phone_str[-10:]
            
            # Prioritize virtual account number, fallback to 10-digit phone
            account_number = ten_digit_phone
            bank_code = None
            if hasattr(user, 'wallet'):
                if user.wallet.virtual_account_number:
                    account_number = user.wallet.virtual_account_number
                bank_code = user.wallet.virtual_bank_code
                
            # Construct response
            data = {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone_number': ten_digit_phone,
                'account_number': account_number,
                'bank_code': bank_code,
                'role': user.role,
                'profile_picture': user.profile.profile_picture.url if hasattr(user, 'profile') and user.profile.profile_picture else None
            }
            return Response(data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error checking user: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'Error performing lookup'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DepositAccountView(APIView):
    """
    API view for retrieving a virtual deposit account.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        responses={200: 'Virtual account details', 500: 'Internal server error'}
    )
    def get(self, request):
        """Get or create the virtual deposit account."""
        try:
            service = PaymentService()
            result = service.get_or_create_deposit_account(request.user)
            
            if result['status']:
                return Response(result['data'], status=status.HTTP_200_OK)
            else:
                return Response(
                    {'detail': result['message']},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Error fetching deposit account: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'An error occurred while retrieving account details.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PaymentInitiationView(APIView):
    """
    API view for initiating payments.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        request_body=PaymentInitiationSerializer,
        responses={200: 'Payment initiated', 400: 'Bad Request'}
    )
    def post(self, request):
        """Initiate a payment."""
        serializer = PaymentInitiationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            payment_service = PaymentService()
            result = payment_service.initialize_payment(
                user=request.user,
                amount=serializer.validated_data['amount'],
                transaction_type=serializer.validated_data['transaction_type'],
                description=serializer.validated_data.get('description', ''),
                metadata=serializer.validated_data.get('metadata', {})
            )
            
            return Response(result, status=status.HTTP_200_OK)
            
        except PaymentError as e:
            logger.error(f"Payment initiation failed: {str(e)}")
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in payment initiation: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'An error occurred while processing your request.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PaymentVerificationView(APIView):
    """
    API view for checking payment status (callback).
    """
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter('reference', openapi.IN_PATH, description="Transaction Reference", type=openapi.TYPE_STRING),
        ],
        responses={200: 'Payment verified', 400: 'Verification failed'}
    )
    def get(self, request, reference):
        """Verify a payment via callback."""
        try:
            payment_service = PaymentService()
            result = payment_service.verify_payment(reference)
            
            # In a real app, you might redirect to a frontend success page
            # return redirect(f"https://frontend.com/payment/status?ref={reference}")
            
            return Response(result, status=status.HTTP_200_OK)
            
        except PaymentError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in payment verification: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'An error occurred while verifying the payment.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class TransferFundsView(APIView):
    """
    API view for transferring funds to another account.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        request_body=TransferFundsSerializer,
        responses={200: 'Transfer successful', 400: 'Bad Request'}
    )
    def post(self, request):
        """Transfer funds to another account."""
        serializer = TransferFundsSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            logger.warning(f"Transfer validation failed: {serializer.errors}")
            return Response({
                "status": False,
                "message": "Validation failed",
                "data": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        amount = serializer.validated_data['amount']
        description = serializer.validated_data.get('description', '')
        beneficiary_id = serializer.validated_data.get('beneficiary_id')
        
        recipient_user = None
        recipient_account_number = None
        recipient_bank_code = None
        
        # Resolve recipient
        if beneficiary_id:
            from ..models import Beneficiary
            try:
                beneficiary = Beneficiary.objects.get(
                    id=beneficiary_id,
                    owner=request.user,
                    is_verified=True
                )
                recipient_account_number = beneficiary.account_number
                recipient_bank_code = beneficiary.bank_code
                # First try resolving as a virtual account
                wallet = Wallet.objects.filter(
                    virtual_account_number=beneficiary.account_number
                ).first()
                if wallet and (not beneficiary.bank_code or wallet.virtual_bank_code == beneficiary.bank_code):
                    recipient_user = wallet.user
                
                # If not a virtual account, check if it's an internal user by phone
                if not recipient_user:
                    is_internal_bank = not beneficiary.bank_code or str(beneficiary.bank_code).lower() in ['paypadi', 'internal']
                    if is_internal_bank or beneficiary.beneficiary_type == Beneficiary.BeneficiaryType.USER:
                        core_acc = ''.join(filter(str.isdigit, str(beneficiary.account_number)))
                        if len(core_acc) >= 10:
                            core_acc = core_acc[-10:]
                            if core_acc:
                                recipient_user = User.objects.filter(phone_number__icontains=core_acc).first()
                                
                if not recipient_user and beneficiary.beneficiary_type == Beneficiary.BeneficiaryType.USER:
                    return Response({
                        "status": False,
                        "message": "User not found.",
                        "data": None
                    }, status=status.HTTP_404_NOT_FOUND)
                    
                if recipient_user and not recipient_user.is_active:
                    return Response({
                        "status": False,
                        "message": "Recipient account is not active.",
                        "data": None
                    }, status=status.HTTP_400_BAD_REQUEST)
            except Beneficiary.DoesNotExist:
                return Response({
                    "status": False,
                    "message": "Invalid or unverified beneficiary",
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            recipient_phone = serializer.validated_data.get('recipient_phone')
            recipient_account_number = serializer.validated_data.get('recipient_account_number')
            recipient_bank_code = serializer.validated_data.get('recipient_bank_code')
            
            # 1. Try to resolve via recipient_phone
            if recipient_phone:
                core_phone = ''.join(filter(str.isdigit, str(recipient_phone)))
                if len(core_phone) >= 10:
                    core_phone = core_phone[-10:]
                
                if core_phone:
                    recipient_user = User.objects.filter(phone_number__icontains=core_phone).first()
                
                if not recipient_user:
                    wallet = Wallet.objects.filter(virtual_account_number=recipient_phone).first()
                    if wallet:
                        recipient_user = wallet.user
                
                if not recipient_user:
                    return Response({
                        "status": False,
                        "message": "User not found.",
                        "data": None
                    }, status=status.HTTP_404_NOT_FOUND)
                if not recipient_user.is_active:
                    return Response({
                        "status": False,
                        "message": "Recipient account is not active.",
                        "data": None
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # 2. If no recipient_phone, check if recipient_account_number is an internal user
            elif recipient_account_number:
                # Check if it's a virtual account belonging to a user
                wallet = Wallet.objects.filter(
                    virtual_account_number=recipient_account_number
                ).first()
                
                if wallet and (not recipient_bank_code or wallet.virtual_bank_code == recipient_bank_code):
                    recipient_user = wallet.user
                else:
                    # Check if the account number is a phone number and the bank code implies internal transfer
                    is_internal_bank = not recipient_bank_code or str(recipient_bank_code).lower() in ['paypadi', 'internal']
                    if is_internal_bank:
                        core_id = ''.join(filter(str.isdigit, str(recipient_account_number)))
                        if len(core_id) >= 10:
                            core_id = core_id[-10:]
                            if core_id:
                                recipient_user = User.objects.filter(phone_number__icontains=core_id).first()

        # Internal Transfer
        if recipient_user:
            from core.models import AuditLog, Notification
            from django.utils import timezone
            from decimal import Decimal
            
            if recipient_user == request.user:
                 return Response({
                     "status": False,
                     "message": "Cannot transfer to yourself",
                     "data": None
                 }, status=status.HTTP_400_BAD_REQUEST)
                 
            try:
                with transaction.atomic():
                    # Acquire locks in deterministic order to prevent deadlocks
                    for uid in sorted([request.user.id, recipient_user.id]):
                        Wallet.objects.select_for_update().get(user_id=uid)
                    
                    wallet = Wallet.objects.get(user=request.user)
                    recipient_wallet = Wallet.objects.get(user=recipient_user)
                    
                    transfer_fee = Decimal('5.00')
                    total_deduction = amount + transfer_fee
                    
                    if wallet.available_balance < total_deduction:
                        return Response({
                            "status": False,
                            "message": "Insufficient balance",
                            "data": None
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    reference = f"TRF-{timezone.now().strftime('%Y%m%d%H%M%S')}-{request.user.id}"
                    
                    wallet.balance -= total_deduction
                    wallet.save(update_fields=['balance'])
                    recipient_wallet.balance += amount
                    recipient_wallet.save(update_fields=['balance'])
                    
                    txn_out = Transaction.objects.create(
                        wallet=wallet, amount=amount,
                        transaction_type=Transaction.TransactionType.TRANSFER,
                        status=Transaction.TransactionStatus.COMPLETED,
                        reference=reference, recipient=recipient_user,
                        description=description or f"Transfer to {recipient_user.get_full_name() or recipient_user.phone_number}",
                        metadata={'recipient_phone': str(recipient_user.phone_number), 'initiated_by': str(request.user.phone_number)}
                    )
                    
                    txn_fee = Transaction.objects.create(
                        wallet=wallet, amount=transfer_fee,
                        transaction_type=Transaction.TransactionType.FEE,
                        status=Transaction.TransactionStatus.COMPLETED,
                        reference=f"FEE-{reference}", recipient=None,
                        description="Intra-transfer transaction fee",
                        metadata={'related_transfer_reference': reference}
                    )
                    
                    txn_in = Transaction.objects.create(
                        wallet=recipient_wallet, amount=amount,
                        transaction_type=Transaction.TransactionType.TRANSFER,
                        status=Transaction.TransactionStatus.COMPLETED,
                        reference=f"REC-{reference}", recipient=request.user,
                        description=description or f"Received from {request.user.get_full_name() or request.user.phone_number}",
                        metadata={'sender_phone': str(request.user.phone_number), 'original_reference': reference}
                    )
                    
                    # Attempt Notification
                    try:
                        AuditLog.log_action(action='transfer_completed', user=request.user, data={'amount': str(amount), 'recipient': str(recipient_user.phone_number), 'reference': reference})
                        Notification.create_notification(user=recipient_user, title="Funds Received", message=f"You received ₦{amount:,.2f} from {request.user.get_full_name() or request.user.phone_number}", notification_type='transaction', action_url=f"/transactions/{txn_in.id}")
                    except Exception as logging_error:
                        logger.warning(f"Failed to log notification: {str(logging_error)}")
                        pass
                    
                    return Response({
                        "status": "success", "message": "Transfer successful",
                        "reference": reference, "amount": amount,
                        "recipient": str(recipient_user.phone_number),
                        "recipient_name": recipient_user.get_full_name() or str(recipient_user.phone_number),
                        "created_at": txn_out.created_at.isoformat(),
                        "payment_type": txn_out.transaction_type,
                        "transaction_type": txn_out.transaction_type
                    })
            except Exception as e:
                logger.error(f"Internal Transfer failed: {str(e)}", exc_info=True)
                return Response({
                    "status": False,
                    "message": "Transfer failed",
                    "data": {"error": str(e)}
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # External Transfer
        else:
            if not recipient_account_number or not recipient_bank_code:
                 return Response({
                     "status": False,
                     "message": "Recipient account number and bank code required for external transfer.",
                     "data": None
                 }, status=status.HTTP_400_BAD_REQUEST)
                 
            try:
                payment_service = PaymentService()
                result = payment_service.transfer_funds(
                    sender=request.user,
                    amount=amount,
                    recipient_account=recipient_account_number,
                    recipient_bank_code=recipient_bank_code,
                    description=description,
                    metadata={
                        'pin_verified': True,
                    }
                )
                return Response(result, status=status.HTTP_200_OK)
                
            except InsufficientFundsError as e:
                return Response({
                    "status": False,
                    "message": str(e),
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)
            except InvalidAccountError as e:
                return Response({
                    "status": False,
                    "message": str(e),
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)
            except PaymentError as e:
                logger.error(f"Funds transfer failed: {str(e)}")
                return Response({
                    "status": False,
                    "message": str(e),
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                logger.error(f"Unexpected error in funds transfer: {str(e)}", exc_info=True)
                return Response({
                    "status": False,
                    "message": "An error occurred while processing your request.",
                    "data": None
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyBankAccountView(APIView):
    """
    API view for verifying bank account details.
    """
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        request_body=BankAccountVerificationSerializer,
        responses={200: 'Account verified', 400: 'Verification failed'}
    )
    def post(self, request):
        """Verify a bank account."""
        serializer = BankAccountVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            payment_service = PaymentService()
            result = payment_service.verify_bank_account(
                account_number=serializer.validated_data['account_number'],
                bank_code=serializer.validated_data['bank_code']
            )
            
            return Response(result, status=status.HTTP_200_OK)
            
        except PaymentError as e:
            logger.error(f"Bank account verification failed: {str(e)}")
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in bank account verification: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'An error occurred while verifying the account.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )





class TransactionHistoryView(APIView):
    """
    API view for retrieving transaction history.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        responses={200: TransactionSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter('page', openapi.IN_QUERY, description="Page number", type=openapi.TYPE_INTEGER),
            openapi.Parameter('page_size', openapi.IN_QUERY, description="Page size", type=openapi.TYPE_INTEGER),
        ]
    )
    def get(self, request):
        """Get transaction history for the authenticated user."""
        try:
            wallet = Wallet.objects.get(user=request.user)
            transactions = Transaction.objects.filter(wallet=wallet).order_by('-created_at')
            
            page = self.paginate_queryset(transactions)
            if page is not None:
                serializer = TransactionSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = TransactionSerializer(transactions, many=True)
            return Response(serializer.data)
            
        except Wallet.DoesNotExist:
            return Response(
                {'detail': 'Wallet not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except getattr(__import__('rest_framework').exceptions, 'NotFound') as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error retrieving transaction history: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'An error occurred while retrieving your transaction history.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def paginate_queryset(self, queryset):
        """Paginate the queryset."""
        from rest_framework.pagination import PageNumberPagination
        
        paginator = PageNumberPagination()
        paginator.page_size = self.request.query_params.get('page_size', 20)
        page = paginator.paginate_queryset(queryset, self.request)
        
        if page is not None:
            self.paginator = paginator
            return page
        
        return queryset
    
    def get_paginated_response(self, data):
        """Return a paginated response."""
        return self.paginator.get_paginated_response(data)
