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
    TransactionSerializer
)
from ..services.payment_service import PaymentService
from ..exceptions import (
    PaymentError,
    InsufficientFundsError,
    InvalidAccountError
)

logger = logging.getLogger(__name__)

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
        serializer = TransferFundsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            payment_service = PaymentService()
            result = payment_service.transfer_funds(
                sender=request.user,
                amount=serializer.validated_data['amount'],
                recipient_account=serializer.validated_data['recipient_account'],
                recipient_bank_code=serializer.validated_data['recipient_bank_code'],
                description=serializer.validated_data.get('description', ''),
                metadata={
                    'pin_verified': True,  # Assuming PIN was verified by the serializer
                    **(serializer.validated_data.get('metadata', {}))
                }
            )
            
            return Response(result, status=status.HTTP_200_OK)
            
        except InsufficientFundsError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except InvalidAccountError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except PaymentError as e:
            logger.error(f"Funds transfer failed: {str(e)}")
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in funds transfer: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'An error occurred while processing your request.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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


@method_decorator(csrf_exempt, name='dispatch')
class PaymentWebhookView(APIView):
    """
    Webhook endpoint for payment notifications from the payment gateway.
    """
    # This view is CSRF exempt since it will be called by an external service
    
    def post(self, request, *args, **kwargs):
        """Handle payment webhook notifications."""
        from django.http import HttpResponse
        
        try:
            # Get the raw request body for signature verification
            payload = request.body
            signature = request.headers.get('X-Paystack-Signature')  # Example for Paystack
            
            # Verify the webhook signature
            if not self._verify_webhook_signature(payload, signature):
                logger.warning("Invalid webhook signature")
                return HttpResponse(status=400)
            
            # Process the webhook event
            event = request.data
            event_type = event.get('event')
            
            if event_type == 'charge.success':
                # Handle successful charge
                reference = event.get('data', {}).get('reference')
                if reference:
                    payment_service = PaymentService()
                    payment_service.verify_payment(reference)
            
            return HttpResponse(status=200)
            
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            return HttpResponse(status=500)
    
    def _verify_webhook_signature(self, payload, signature):
        """Verify the webhook signature."""
        # In a real implementation, this would verify the signature
        # using the webhook secret from settings
        return True  # For development


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
            return page
        
        return queryset
    
    def get_paginated_response(self, data):
        """Return a paginated response."""
        from rest_framework.response import Response
        from rest_framework.pagination import PageNumberPagination
        
        paginator = PageNumberPagination()
        paginator.page_size = self.request.query_params.get('page_size', 20)
        
        return paginator.get_paginated_response(data)
